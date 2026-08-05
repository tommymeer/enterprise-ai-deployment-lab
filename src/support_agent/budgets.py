"""Hard per-run execution budgets and deterministic retry configuration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .failures import FailureKind


class BudgetDimension(StrEnum):
    TOOL_CALLS = "tool_calls"
    RETRY_ATTEMPTS = "retry_attempts"
    ELAPSED_MS = "elapsed_ms"
    ESTIMATED_COST_USD = "estimated_cost_usd"


def _non_negative_int(value: int, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _non_negative_number(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True, slots=True)
class ExecutionBudget:
    max_tool_calls: int
    max_retry_attempts: int
    max_elapsed_ms: float
    max_estimated_cost_usd: float

    def __post_init__(self) -> None:
        _non_negative_int(self.max_tool_calls, "max_tool_calls")
        _non_negative_int(self.max_retry_attempts, "max_retry_attempts")
        _non_negative_number(self.max_elapsed_ms, "max_elapsed_ms")
        _non_negative_number(
            self.max_estimated_cost_usd, "max_estimated_cost_usd"
        )


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts_per_call: int
    retryable_failure_kinds: frozenset[FailureKind]
    initial_backoff_ms: float
    backoff_multiplier: float
    max_backoff_ms: float

    def __post_init__(self) -> None:
        if type(self.max_attempts_per_call) is not int or self.max_attempts_per_call < 1:
            raise ValueError("max_attempts_per_call must be at least 1")
        kinds = frozenset(self.retryable_failure_kinds)
        if any(not isinstance(kind, FailureKind) for kind in kinds):
            raise ValueError("retryable_failure_kinds must contain FailureKind values")
        object.__setattr__(self, "retryable_failure_kinds", kinds)
        _non_negative_number(self.initial_backoff_ms, "initial_backoff_ms")
        _non_negative_number(self.max_backoff_ms, "max_backoff_ms")
        if (
            isinstance(self.backoff_multiplier, bool)
            or not isinstance(self.backoff_multiplier, (int, float))
            or self.backoff_multiplier < 1
        ):
            raise ValueError("backoff_multiplier must be at least 1")

    def backoff_ms(self, retry_number: int) -> float:
        if type(retry_number) is not int or retry_number < 1:
            raise ValueError("retry_number must be a positive integer")
        return min(
            self.initial_backoff_ms
            * self.backoff_multiplier ** (retry_number - 1),
            self.max_backoff_ms,
        )


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    tool_calls_used: int
    retries_used: int
    elapsed_ms: float
    estimated_cost_usd: float
    exhausted_dimension: BudgetDimension | None
    stopped: bool

    def __post_init__(self) -> None:
        _non_negative_int(self.tool_calls_used, "tool_calls_used")
        _non_negative_int(self.retries_used, "retries_used")
        _non_negative_number(self.elapsed_ms, "elapsed_ms")
        _non_negative_number(self.estimated_cost_usd, "estimated_cost_usd")
        if self.exhausted_dimension is not None and not isinstance(
            self.exhausted_dimension, BudgetDimension
        ):
            raise ValueError("exhausted_dimension must be a BudgetDimension or None")
        if type(self.stopped) is not bool:
            raise ValueError("stopped must be a bool")
        if self.stopped is not (self.exhausted_dimension is not None):
            raise ValueError("stopped must reflect whether a dimension is exhausted")


class ExecutionBudgetExceeded(Exception):
    """A hard per-run execution limit prevents further work."""

    def __init__(self, dimension: BudgetDimension, used: float, limit: float) -> None:
        self.dimension = dimension
        self.used = used
        self.limit = limit
        super().__init__(f"execution budget exhausted: {dimension.value}")


class RetryExhausted(Exception):
    """A retryable operational failure reached its per-call attempt limit."""

    def __init__(self, attempts: int) -> None:
        self.attempts = attempts
        super().__init__(f"retry attempts exhausted after {attempts} attempts")


class _BudgetTracker:
    """Mutable accounting for exactly one workflow run."""

    def __init__(self, budget: ExecutionBudget) -> None:
        self._budget = budget
        self._tool_calls = 0
        self._retries = 0
        self._elapsed_ms = 0.0
        self._cost = 0.0
        self._exhausted: BudgetDimension | None = None

    @property
    def snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            self._tool_calls,
            self._retries,
            self._elapsed_ms,
            self._cost,
            self._exhausted,
            self._exhausted is not None,
        )

    def start_attempt(self, *, retry: bool, estimated_cost_usd: float) -> None:
        self.ensure_attempt_allowed(
            retry=retry, estimated_cost_usd=estimated_cost_usd
        )
        self._tool_calls += 1
        if retry:
            self._retries += 1

    def ensure_attempt_allowed(
        self, *, retry: bool, estimated_cost_usd: float
    ) -> None:
        _non_negative_number(estimated_cost_usd, "estimated_cost_usd")
        if self._exhausted is not None:
            self._raise(self._exhausted)
        checks = (
            (BudgetDimension.TOOL_CALLS, self._tool_calls + 1, self._budget.max_tool_calls),
            (
                BudgetDimension.RETRY_ATTEMPTS,
                self._retries + (1 if retry else 0),
                self._budget.max_retry_attempts,
            ),
            (BudgetDimension.ELAPSED_MS, self._elapsed_ms, self._budget.max_elapsed_ms),
            (
                BudgetDimension.ESTIMATED_COST_USD,
                self._cost + estimated_cost_usd,
                self._budget.max_estimated_cost_usd,
            ),
        )
        for dimension, prospective, limit in checks:
            if prospective > limit or (
                dimension is BudgetDimension.ELAPSED_MS and prospective >= limit
            ):
                self._exhausted = dimension
                raise ExecutionBudgetExceeded(dimension, prospective, limit)

    def finish_attempt(self, *, elapsed_ms: float, estimated_cost_usd: float) -> None:
        _non_negative_number(elapsed_ms, "elapsed_ms")
        _non_negative_number(estimated_cost_usd, "estimated_cost_usd")
        self._elapsed_ms += elapsed_ms
        self._cost += estimated_cost_usd
        if self._elapsed_ms >= self._budget.max_elapsed_ms:
            self._exhausted = BudgetDimension.ELAPSED_MS
        elif self._cost > self._budget.max_estimated_cost_usd:
            self._exhausted = BudgetDimension.ESTIMATED_COST_USD

    def record_backoff(self, elapsed_ms: float) -> None:
        _non_negative_number(elapsed_ms, "elapsed_ms")
        self._elapsed_ms += elapsed_ms
        if self._elapsed_ms >= self._budget.max_elapsed_ms:
            self._exhausted = BudgetDimension.ELAPSED_MS

    def ensure_backoff_allowed(self, elapsed_ms: float) -> None:
        _non_negative_number(elapsed_ms, "elapsed_ms")
        if self._exhausted is not None:
            self._raise(self._exhausted)
        prospective_elapsed_ms = self._elapsed_ms + elapsed_ms
        if prospective_elapsed_ms >= self._budget.max_elapsed_ms:
            self._exhausted = BudgetDimension.ELAPSED_MS
            raise ExecutionBudgetExceeded(
                BudgetDimension.ELAPSED_MS,
                prospective_elapsed_ms,
                self._budget.max_elapsed_ms,
            )

    def ensure_active(self) -> None:
        if self._exhausted is not None:
            self._raise(self._exhausted)

    def _raise(self, dimension: BudgetDimension) -> None:
        used = {
            BudgetDimension.TOOL_CALLS: self._tool_calls,
            BudgetDimension.RETRY_ATTEMPTS: self._retries,
            BudgetDimension.ELAPSED_MS: self._elapsed_ms,
            BudgetDimension.ESTIMATED_COST_USD: self._cost,
        }[dimension]
        limit = {
            BudgetDimension.TOOL_CALLS: self._budget.max_tool_calls,
            BudgetDimension.RETRY_ATTEMPTS: self._budget.max_retry_attempts,
            BudgetDimension.ELAPSED_MS: self._budget.max_elapsed_ms,
            BudgetDimension.ESTIMATED_COST_USD: self._budget.max_estimated_cost_usd,
        }[dimension]
        raise ExecutionBudgetExceeded(dimension, used, limit)
