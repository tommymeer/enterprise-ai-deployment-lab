"""Deterministic operational failure injection and regression cases."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Callable

from .domain import CaseStatus, Disposition, ExecutionStatus
from .execution import ExecutionRegistry

if TYPE_CHECKING:
    from .workflow import WorkflowConfiguration, WorkflowResult


class FailureKind(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    SERVICE_UNAVAILABLE = "service_unavailable"
    MALFORMED_RESULT = "malformed_result"
    EXECUTION_FAILURE = "execution_failure"
    EXECUTION_EXCEPTION = "execution_exception"


class FailureTarget(StrEnum):
    CUSTOMER_LOOKUP = "customer_lookup"
    ORDER_LOOKUP = "order_lookup"
    SHIPMENT_LOOKUP = "shipment_lookup"
    CARRIER_EVIDENCE_LOOKUP = "carrier_evidence_lookup"
    ADDRESS_COMPARISON = "address_comparison"
    HUMAN_REVIEW = "human_review"
    EXECUTION = "execution"


def _non_empty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


@dataclass(frozen=True, slots=True)
class FailureInjection:
    injection_id: str
    target: FailureTarget
    kind: FailureKind
    trigger_on_call: int
    detail: str
    retryable: bool
    expected_safe_route: CaseStatus

    def __post_init__(self) -> None:
        _non_empty(self.injection_id, "injection_id")
        _non_empty(self.detail, "detail")
        if not isinstance(self.target, FailureTarget):
            raise ValueError("target must be a FailureTarget")
        if not isinstance(self.kind, FailureKind):
            raise ValueError("kind must be a FailureKind")
        if (
            self.kind
            in {FailureKind.EXECUTION_FAILURE, FailureKind.EXECUTION_EXCEPTION}
            and self.target is not FailureTarget.EXECUTION
        ):
            raise ValueError(f"{self.kind.value} requires target execution")
        if type(self.trigger_on_call) is not int or self.trigger_on_call < 1:
            raise ValueError("trigger_on_call must be a positive integer")
        if type(self.retryable) is not bool:
            raise ValueError("retryable must be a bool")
        if not isinstance(self.expected_safe_route, CaseStatus):
            raise ValueError("expected_safe_route must be a CaseStatus")


class SyntheticOperationalError(Exception):
    """Base for explicitly modeled, sanitized dependency failures."""

    def __init__(self, injection: FailureInjection, call_number: int) -> None:
        self.injection = injection
        self.call_number = call_number
        super().__init__(injection.detail)


class SyntheticTimeoutError(SyntheticOperationalError):
    pass


class SyntheticRateLimitError(SyntheticOperationalError):
    pass


class SyntheticServiceUnavailableError(SyntheticOperationalError):
    pass


class SyntheticMalformedResultError(SyntheticOperationalError):
    pass


_ERRORS = {
    FailureKind.TIMEOUT: SyntheticTimeoutError,
    FailureKind.RATE_LIMIT: SyntheticRateLimitError,
    FailureKind.SERVICE_UNAVAILABLE: SyntheticServiceUnavailableError,
    FailureKind.MALFORMED_RESULT: SyntheticMalformedResultError,
    FailureKind.EXECUTION_EXCEPTION: SyntheticTimeoutError,
}


class FailureInjectingCallable:
    """Count calls and replace exactly one configured call with a failure."""

    def __init__(
        self, delegate: Callable[..., object], injection: FailureInjection
    ) -> None:
        if not callable(delegate):
            raise ValueError("delegate must be callable")
        self._delegate = delegate
        self._injection = injection
        self._invocation_count = 0

    @property
    def invocation_count(self) -> int:
        return self._invocation_count

    def __call__(self, *args: object, **kwargs: object) -> object:
        self._invocation_count += 1
        if self._invocation_count != self._injection.trigger_on_call:
            return self._delegate(*args, **kwargs)
        if self._injection.kind is FailureKind.EXECUTION_FAILURE:
            from .workflow import ExecutionResult
            return ExecutionResult(False, self._injection.detail)
        error = _ERRORS.get(self._injection.kind)
        if error is None:
            raise ValueError(f"{self._injection.kind} is not injectable as an exception")
        raise error(self._injection, self._invocation_count)


@dataclass(frozen=True, slots=True)
class FailureRegressionCase:
    regression_id: str
    scenario_id: str
    injection: FailureInjection
    expected_failure_stage: str | None
    expected_case_status: CaseStatus
    expected_disposition: Disposition
    expected_execution_status: ExecutionStatus
    expected_adapter_invocations: int
    expected_required_trace_events: tuple[str, ...]
    expected_forbidden_trace_events: tuple[str, ...]
    notes: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "expected_required_trace_events", tuple(self.expected_required_trace_events))
        object.__setattr__(self, "expected_forbidden_trace_events", tuple(self.expected_forbidden_trace_events))
        for name in ("regression_id", "scenario_id", "notes"):
            _non_empty(getattr(self, name), name)
        if type(self.expected_adapter_invocations) is not int or self.expected_adapter_invocations < 0:
            raise ValueError("expected_adapter_invocations must be non-negative")


@dataclass(frozen=True, slots=True)
class FailureRegressionResult:
    regression_case: FailureRegressionCase
    workflow_result: WorkflowResult
    adapter_invocations: int


@dataclass(frozen=True, slots=True)
class FailureRegressionCheck:
    name: str
    passed: bool
    expected: object
    actual: object


@dataclass(frozen=True, slots=True)
class FailureRegressionEvaluation:
    regression_id: str
    passed: bool
    checks: tuple[FailureRegressionCheck, ...]
    failure_messages: tuple[str, ...]


def _inj(
    identifier: str,
    target: FailureTarget,
    kind: FailureKind,
    *,
    call: int = 1,
) -> FailureInjection:
    route = (
        CaseStatus.HUMAN_REVIEW
        if target is FailureTarget.EXECUTION
        else CaseStatus.INTAKE
    )
    retryable = kind in {
        FailureKind.TIMEOUT,
        FailureKind.RATE_LIMIT,
        FailureKind.SERVICE_UNAVAILABLE,
        FailureKind.EXECUTION_EXCEPTION,
    }
    return FailureInjection(
        identifier,
        target,
        kind,
        call,
        f"synthetic {kind.value}",
        retryable,
        route,
    )


def _case(
    identifier: str,
    scenario: str,
    injection: FailureInjection,
    status: CaseStatus,
    disposition: Disposition = Disposition.NONE_SELECTED,
    execution: ExecutionStatus = ExecutionStatus.NOT_APPLICABLE,
    calls: int = 1,
    required: tuple[str, ...] = (),
    forbidden: tuple[str, ...] = (),
) -> FailureRegressionCase:
    injection = replace(injection, expected_safe_route=status)
    return FailureRegressionCase(
        identifier,
        scenario,
        injection,
        injection.target.value,
        status,
        disposition,
        execution,
        calls,
        ("tool_called", "modeled_operational_failure")
        + required
        + ("workflow_stopped",),
        forbidden,
        "Synthetic controlled operational regression.",
    )


_CASES = (
    _case(
        "customer-timeout",
        "refund-success",
        _inj("fi-customer", FailureTarget.CUSTOMER_LOOKUP, FailureKind.TIMEOUT),
        CaseStatus.INTAKE,
        forbidden=("linkage_completed",),
    ),
    _case(
        "order-unavailable",
        "refund-success",
        _inj(
            "fi-order",
            FailureTarget.ORDER_LOOKUP,
            FailureKind.SERVICE_UNAVAILABLE,
        ),
        CaseStatus.INTAKE,
        forbidden=("shipment_attached",),
    ),
    _case(
        "shipment-rate-limit",
        "refund-success",
        _inj("fi-shipment", FailureTarget.SHIPMENT_LOOKUP, FailureKind.RATE_LIMIT),
        CaseStatus.LINKED,
        forbidden=("evidence_gathering_entered",),
    ),
    _case(
        "carrier-timeout",
        "refund-success",
        _inj(
            "fi-carrier",
            FailureTarget.CARRIER_EVIDENCE_LOOKUP,
            FailureKind.TIMEOUT,
        ),
        CaseStatus.EVIDENCE_GATHERING,
        forbidden=("address_comparison_recorded", "policy_review_entered"),
    ),
    _case(
        "address-malformed",
        "refund-success",
        _inj(
            "fi-address",
            FailureTarget.ADDRESS_COMPARISON,
            FailureKind.MALFORMED_RESULT,
        ),
        CaseStatus.EVIDENCE_GATHERING,
        forbidden=("policy_review_entered",),
    ),
    _case(
        "review-unavailable",
        "refund-authority-review",
        _inj(
            "fi-review",
            FailureTarget.HUMAN_REVIEW,
            FailureKind.SERVICE_UNAVAILABLE,
        ),
        CaseStatus.HUMAN_REVIEW,
        forbidden=("human_review_decided",),
    ),
    FailureRegressionCase(
        "execution-result-failure",
        "refund-success",
        _inj(
            "fi-exec-result",
            FailureTarget.EXECUTION,
            FailureKind.EXECUTION_FAILURE,
        ),
        "execution",
        CaseStatus.HUMAN_REVIEW,
        Disposition.APPROVE_REFUND,
        ExecutionStatus.FAILED,
        1,
        (
            "execution_adapter_invoked",
            "failed_operation_recorded",
            "execution_failure_routed",
            "workflow_stopped",
        ),
        ("modeled_operational_failure", "successful_operation_recorded"),
        "A normal failed result follows the existing execution failure path.",
    ),
    _case(
        "execution-timeout",
        "refund-success",
        _inj("fi-exec-timeout", FailureTarget.EXECUTION, FailureKind.TIMEOUT),
        CaseStatus.HUMAN_REVIEW,
        Disposition.APPROVE_REFUND,
        ExecutionStatus.FAILED,
        required=("failed_operation_recorded", "execution_failure_routed"),
        forbidden=("successful_operation_recorded",),
    ),
    FailureRegressionCase(
        "duplicate-suppresses-injection",
        "refund-success",
        replace(
            _inj(
                "fi-duplicate",
                FailureTarget.EXECUTION,
                FailureKind.EXECUTION_EXCEPTION,
                call=2,
            ),
            expected_safe_route=CaseStatus.CLOSED,
        ),
        None,
        CaseStatus.CLOSED,
        Disposition.APPROVE_REFUND,
        ExecutionStatus.SUCCEEDED,
        1,
        ("duplicate_execution_suppressed", "workflow_completed"),
        ("modeled_operational_failure", "failed_operation_recorded"),
        "A shared registry reuses success before the injected second adapter call.",
    ),
    _case(
        "call-two-deterministic",
        "refund-success",
        _inj(
            "fi-call-two",
            FailureTarget.CUSTOMER_LOOKUP,
            FailureKind.TIMEOUT,
            call=2,
        ),
        CaseStatus.INTAKE,
        calls=2,
        forbidden=("linkage_completed",),
    ),
)


def get_failure_regression_cases() -> tuple[FailureRegressionCase, ...]:
    return _CASES


def get_failure_regression_case(regression_id: str) -> FailureRegressionCase:
    _non_empty(regression_id, "regression_id")
    for case in _CASES:
        if case.regression_id == regression_id:
            return case
    raise KeyError(f"unknown failure regression case: {regression_id}")


def run_failure_regression_case(case: FailureRegressionCase, *, registry: ExecutionRegistry | None = None) -> FailureRegressionResult:
    from .scenarios import get_support_case_scenario, run_support_case_scenario

    wrapper: FailureInjectingCallable | None = None
    target_field = {
        FailureTarget.CUSTOMER_LOOKUP: "customer_lookup", FailureTarget.ORDER_LOOKUP: "order_lookup",
        FailureTarget.SHIPMENT_LOOKUP: "shipment_lookup", FailureTarget.CARRIER_EVIDENCE_LOOKUP: "carrier_evidence_lookup",
        FailureTarget.ADDRESS_COMPARISON: "address_comparison", FailureTarget.HUMAN_REVIEW: "human_reviewer",
        FailureTarget.EXECUTION: "execution",
    }[case.injection.target]

    def transform(configuration: WorkflowConfiguration) -> WorkflowConfiguration:
        from .budgets import RetryPolicy

        nonlocal wrapper
        delegate = getattr(configuration, target_field)
        if wrapper is None:
            wrapper = FailureInjectingCallable(delegate, case.injection)
        no_retry = RetryPolicy(1, frozenset(), 0.0, 1.0, 0.0)
        return replace(
            configuration,
            retry_policy=no_retry,
            **{target_field: wrapper},
        )

    shared = registry if registry is not None else ExecutionRegistry()
    scenario = get_support_case_scenario(case.scenario_id)
    first = run_support_case_scenario(scenario, registry=shared, configuration_transform=transform)
    result = first.workflow_result
    if case.injection.trigger_on_call == 2:
        second = run_support_case_scenario(scenario, registry=shared, configuration_transform=transform)
        result = second.workflow_result
    return FailureRegressionResult(case, result, wrapper.invocation_count if wrapper else 0)


def evaluate_failure_regression_case(run: FailureRegressionResult) -> FailureRegressionEvaluation:
    result = run.workflow_result
    expected = run.regression_case
    names = tuple(event.event_type for event in result.trace_events)
    cursor = 0
    ordered = True
    for name in expected.expected_required_trace_events:
        try:
            cursor = names.index(name, cursor) + 1
        except ValueError:
            ordered = False
            break
    forbidden = tuple(name for name in expected.expected_forbidden_trace_events if name in names)
    values = (
        ("failure_stage", expected.expected_failure_stage, result.failure_stage),
        ("case_status", expected.expected_case_status, result.final_case_status),
        ("disposition", expected.expected_disposition, result.final_disposition),
        ("execution_status", expected.expected_execution_status, result.case.execution_status),
        ("adapter_invocations", expected.expected_adapter_invocations, run.adapter_invocations),
        ("required_trace_events_in_order", True, ordered),
        ("forbidden_trace_events_absent", (), forbidden),
    )
    checks = tuple(
        FailureRegressionCheck(name, expected_value == actual, expected_value, actual)
        for name, expected_value, actual in values
    )
    failures = tuple(
        f"{check.name}: expected {check.expected!r}, got {check.actual!r}"
        for check in checks
        if not check.passed
    )
    return FailureRegressionEvaluation(expected.regression_id, not failures, checks, failures)
