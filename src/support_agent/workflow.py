"""Deterministic orchestration for one synthetic support case."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from time import perf_counter
from typing import Callable, Mapping, TypeVar
from uuid import uuid4

from .domain import (
    AddressMatchResult,
    CarrierEvidenceSnapshot,
    CaseStatus,
    CustomerReference,
    CustomerReport,
    Disposition,
    ExecutionStatus,
    HumanReviewDecision,
    HumanReviewRequest,
    MatchStatus,
    OrderReference,
    PolicyPlaceholder,
    RetrievalStatus,
    ShipmentReference,
    SupportCase,
    evaluate_synthetic_structural_policy,
)
from .execution import (
    ExecutionOperation,
    ExecutionRegistry,
    OperationStatus,
    generate_idempotency_key,
)
from .budgets import (
    BudgetSnapshot,
    ExecutionBudget,
    ExecutionBudgetExceeded,
    RetryExhausted,
    RetryPolicy,
    _BudgetTracker,
)
from .failures import FailureKind, SyntheticOperationalError
from .extraction import (
    CustomerMessageExtraction,
    ExtractionIssueType,
    ExtractionResult,
    ExtractionStatus,
)
from .tracing import WorkflowTraceCollector, WorkflowTraceEvent


def _non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must use UTC")


@dataclass(frozen=True, slots=True)
class SyntheticSupportCaseInput:
    case_id: str
    customer_message: str
    customer_identifier: str
    order_identifier: str
    shipment_identifier: str
    actor: str
    received_at: datetime
    customer_confirmed_delivery_address: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "case_id",
            "customer_message",
            "customer_identifier",
            "order_identifier",
            "shipment_identifier",
            "actor",
        ):
            _non_empty(getattr(self, field_name), field_name)
        _utc(self.received_at, "received_at")
        if self.customer_confirmed_delivery_address is not None:
            _non_empty(self.customer_confirmed_delivery_address, "customer_confirmed_delivery_address")


class IntakeRoute(StrEnum):
    MANUAL_INTAKE_REVIEW_REQUIRED = "manual_intake_review_required"
    CLARIFICATION_REQUIRED = "clarification_required"
    DELIVERED_NOT_RECEIVED_WORKFLOW = "delivered_not_received_workflow"
    GENERAL_TRIAGE_REQUIRED = "general_triage_required"


@dataclass(frozen=True, slots=True)
class TrustedIntakeContext:
    case_id: str
    customer_identifier: str
    shipment_identifier: str
    actor: str
    received_at: datetime
    customer_confirmed_delivery_address: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "case_id",
            "customer_identifier",
            "shipment_identifier",
            "actor",
        ):
            _non_empty(getattr(self, field_name), field_name)
        _utc(self.received_at, "received_at")
        if self.customer_confirmed_delivery_address is not None:
            _non_empty(self.customer_confirmed_delivery_address, "customer_confirmed_delivery_address")


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    succeeded: bool
    detail: str

    def __post_init__(self) -> None:
        if type(self.succeeded) is not bool:
            raise ValueError("succeeded must be a bool")
        _non_empty(self.detail, "detail")


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    case: SupportCase
    completed: bool
    final_case_status: CaseStatus
    final_disposition: Disposition
    failure_stage: str | None = None
    failure_reason: str | None = None
    trace_id: str = ""
    trace_events: tuple[WorkflowTraceEvent, ...] = ()
    execution_operation: ExecutionOperation | None = None
    budget_snapshot: BudgetSnapshot = field(
        default_factory=lambda: BudgetSnapshot(0, 0, 0.0, 0.0, None, False)
    )

    def __post_init__(self) -> None:
        if not isinstance(self.case, SupportCase):
            raise ValueError("case must be a SupportCase")
        if type(self.completed) is not bool:
            raise ValueError("completed must be a bool")
        if not isinstance(self.final_case_status, CaseStatus):
            raise ValueError("final_case_status must be a CaseStatus")
        if not isinstance(self.final_disposition, Disposition):
            raise ValueError("final_disposition must be a Disposition")
        if self.final_case_status is not self.case.case_status:
            raise ValueError("final_case_status must match case")
        if self.final_disposition is not self.case.disposition:
            raise ValueError("final_disposition must match case")
        if (self.failure_stage is None) != (self.failure_reason is None):
            raise ValueError("failure_stage and failure_reason must be provided together")
        if self.completed and self.failure_stage is not None:
            raise ValueError("completed results must not contain a failure")
        if not self.completed and self.failure_stage is None:
            raise ValueError("non-completed results require a failure")
        if self.failure_stage is not None:
            _non_empty(self.failure_stage, "failure_stage")
            _non_empty(self.failure_reason or "", "failure_reason")
        _non_empty(self.trace_id, "trace_id")
        object.__setattr__(self, "trace_events", tuple(self.trace_events))
        if any(event.trace_id != self.trace_id for event in self.trace_events):
            raise ValueError("trace_id must match every trace event")
        if [event.sequence_number for event in self.trace_events] != list(
            range(len(self.trace_events))
        ):
            raise ValueError("trace events must be ordered and contiguous")
        if self.execution_operation is not None and not isinstance(
            self.execution_operation, ExecutionOperation
        ):
            raise ValueError("execution_operation must be an ExecutionOperation")
        if self.execution_operation is not None:
            if self.execution_operation.case_id != self.case.case_id:
                raise ValueError("execution operation case_id must match case")
            if self.execution_operation.disposition is not self.case.disposition:
                raise ValueError("execution operation disposition must match case")
            expected_key = generate_idempotency_key(
                self.case.case_id, self.case.disposition
            )
            if self.execution_operation.idempotency_key != expected_key:
                raise ValueError("execution operation idempotency key must match case")
        if not isinstance(self.budget_snapshot, BudgetSnapshot):
            raise ValueError("budget_snapshot must be a BudgetSnapshot")


@dataclass(frozen=True, slots=True)
class IntakeRoutingResult:
    route: IntakeRoute
    workflow_result: WorkflowResult | None = None
    reason: str | None = None
    missing_required_fields: tuple[str, ...] = ()
    extraction: CustomerMessageExtraction | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.route, IntakeRoute):
            raise ValueError("route must be an IntakeRoute")
        object.__setattr__(
            self, "missing_required_fields", tuple(self.missing_required_fields)
        )
        if any(
            not isinstance(field_name, str) or not field_name.strip()
            for field_name in self.missing_required_fields
        ):
            raise ValueError("missing_required_fields entries must be non-empty strings")
        if self.extraction is not None and not isinstance(
            self.extraction, CustomerMessageExtraction
        ):
            raise ValueError("extraction must be a CustomerMessageExtraction")

        enters_workflow = (
            self.route is IntakeRoute.DELIVERED_NOT_RECEIVED_WORKFLOW
        )
        if enters_workflow != (self.workflow_result is not None):
            raise ValueError("only the delivered-not-received route has a workflow result")
        if enters_workflow:
            if self.extraction is None or (
                self.extraction.issue_type
                is not ExtractionIssueType.DELIVERED_NOT_RECEIVED
            ):
                raise ValueError("workflow route requires a delivered-not-received extraction")
            if (
                self.extraction.needs_clarification
                or self.extraction.order_identifier is None
                or self.extraction.missing_required_fields
                or self.extraction.clarification_reason is not None
            ):
                raise ValueError("workflow route requires a complete extraction")
            if self.reason is not None or self.missing_required_fields:
                raise ValueError("workflow route cannot contain stop details")
        elif self.workflow_result is not None:
            raise ValueError("non-workflow routes cannot contain a workflow result")

        if self.route is IntakeRoute.MANUAL_INTAKE_REVIEW_REQUIRED:
            if not isinstance(self.reason, str) or not self.reason.strip():
                raise ValueError("manual intake review requires a reason")
            if self.extraction is not None or self.missing_required_fields:
                raise ValueError("invalid extraction cannot contain validated business data")
        elif self.route is IntakeRoute.CLARIFICATION_REQUIRED:
            if self.extraction is None or not self.extraction.needs_clarification:
                raise ValueError("clarification route requires a clarification extraction")
            if self.missing_required_fields != self.extraction.missing_required_fields:
                raise ValueError("clarification fields must match the extraction")
            if not self.missing_required_fields:
                raise ValueError("clarification route requires missing fields")
            if self.reason != self.extraction.clarification_reason:
                raise ValueError("clarification reason must match the extraction")
        elif self.route is IntakeRoute.GENERAL_TRIAGE_REQUIRED:
            if self.extraction is None or (
                self.extraction.issue_type is not ExtractionIssueType.UNKNOWN
            ):
                raise ValueError("general triage requires an unknown-issue extraction")
            if (
                self.extraction.needs_clarification
                or self.extraction.order_identifier is None
                or self.extraction.missing_required_fields
                or self.extraction.clarification_reason is not None
            ):
                raise ValueError("general triage requires a complete extraction")
            if self.reason is not None or self.missing_required_fields:
                raise ValueError("general triage cannot contain clarification details")


@dataclass(frozen=True, slots=True)
class SyntheticCustomerLookup:
    result: CustomerReference

    def __call__(self, identifier: str) -> CustomerReference:
        return self.result


@dataclass(frozen=True, slots=True)
class SyntheticOrderLookup:
    result: OrderReference

    def __call__(self, identifier: str) -> OrderReference:
        return self.result


@dataclass(frozen=True, slots=True)
class SyntheticShipmentLookup:
    result: ShipmentReference

    def __call__(self, identifier: str) -> ShipmentReference:
        return self.result


@dataclass(frozen=True, slots=True)
class SyntheticCarrierEvidenceLookup:
    result: CarrierEvidenceSnapshot | None

    def __call__(
        self, shipment: ShipmentReference
    ) -> CarrierEvidenceSnapshot | None:
        return self.result


@dataclass(frozen=True, slots=True)
class SyntheticAddressComparison:
    result: AddressMatchResult

    def __post_init__(self) -> None:
        if not isinstance(self.result, AddressMatchResult):
            raise ValueError("result must be an AddressMatchResult")

    def __call__(
        self, case_input: SyntheticSupportCaseInput, order: OrderReference
    ) -> AddressMatchResult:
        return self.result


@dataclass(frozen=True, slots=True)
class DeterministicAddressComparison:
    """Compare support-channel address context with the retailer order fact."""

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join("".join(character.lower() if character.isalnum() else " " for character in value).split())

    def __call__(self, case_input: SyntheticSupportCaseInput, order: OrderReference) -> AddressMatchResult:
        claimed = case_input.customer_confirmed_delivery_address
        trusted = order.ship_to_address_on_file
        if not claimed or not trusted:
            return AddressMatchResult.UNKNOWN
        return (AddressMatchResult.MATCH if self._normalize(claimed) == self._normalize(trusted)
                else AddressMatchResult.MISMATCH)


@dataclass(frozen=True, slots=True)
class SyntheticExecutionAdapter:
    refund: ExecutionResult
    replacement: ExecutionResult
    carrier_inquiry: ExecutionResult

    def __call__(
        self,
        idempotency_key: str,
        disposition: Disposition,
        case: SupportCase,
    ) -> ExecutionResult:
        if not isinstance(case, SupportCase):
            raise ValueError("case must be a SupportCase")
        expected_key = generate_idempotency_key(case.case_id, disposition)
        if disposition is not case.disposition:
            raise ValueError("disposition must match case")
        if idempotency_key != expected_key:
            raise ValueError("idempotency key does not match case and disposition")
        results = {
            Disposition.APPROVE_REFUND: self.refund,
            Disposition.APPROVE_REPLACEMENT: self.replacement,
            Disposition.OPEN_CARRIER_INQUIRY: self.carrier_inquiry,
        }
        if disposition not in results:
            raise ValueError(f"{disposition} is not executable")
        return results[disposition]


@dataclass(frozen=True, slots=True)
class SyntheticHumanReviewer:
    request: HumanReviewRequest
    decision: HumanReviewDecision

    def __post_init__(self) -> None:
        if self.request.review_id != self.decision.review_id:
            raise ValueError("review request and decision IDs must match")

    def __call__(
        self, case: SupportCase
    ) -> tuple[HumanReviewRequest, HumanReviewDecision]:
        return self.request, self.decision


CustomerLookup = Callable[[str], CustomerReference]
OrderLookup = Callable[[str], OrderReference]
ShipmentLookup = Callable[[str], ShipmentReference]
CarrierLookup = Callable[[ShipmentReference], CarrierEvidenceSnapshot | None]
AddressComparison = Callable[
    [SyntheticSupportCaseInput, OrderReference], AddressMatchResult
]
ExecutionAdapter = Callable[[str, Disposition, SupportCase], ExecutionResult]
HumanReviewer = Callable[
    [SupportCase], tuple[HumanReviewRequest, HumanReviewDecision]
]
ToolResult = TypeVar("ToolResult")


def _no_backoff_sleep(_: float) -> None:
    """Default deterministic backoff hook; production waiting is out of scope."""


DEFAULT_EXECUTION_BUDGET = ExecutionBudget(10, 0, 60_000.0, 0.0)
DEFAULT_RETRY_POLICY = RetryPolicy(
    1,
    frozenset(
        {
            FailureKind.TIMEOUT,
            FailureKind.RATE_LIMIT,
            FailureKind.SERVICE_UNAVAILABLE,
            FailureKind.EXECUTION_EXCEPTION,
        }
    ),
    0.0,
    2.0,
    0.0,
)


@dataclass(frozen=True, slots=True)
class WorkflowConfiguration:
    customer_lookup: CustomerLookup
    order_lookup: OrderLookup
    shipment_lookup: ShipmentLookup
    carrier_evidence_lookup: CarrierLookup
    address_comparison: AddressComparison
    execution: ExecutionAdapter
    selected_disposition: Disposition
    evaluated_at: datetime
    proposed_refund_amount_minor: int | None = field(default=None, kw_only=True)
    proposed_refund_currency: str | None = field(default=None, kw_only=True)
    autonomous_refund_limit_minor: int | None = field(default=None, kw_only=True)
    autonomous_refund_limit_currency: str | None = field(default=None, kw_only=True)
    unresolved_policies: tuple[PolicyPlaceholder, ...] = ()
    human_reviewer: HumanReviewer | None = None
    execution_registry: ExecutionRegistry = field(default_factory=ExecutionRegistry)
    execution_budget: ExecutionBudget = DEFAULT_EXECUTION_BUDGET
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY
    backoff_sleep: Callable[[float], None] = _no_backoff_sleep
    tool_estimated_cost_usd: Mapping[str, float] = field(default_factory=dict)
    derive_retailer_disposition: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "customer_lookup",
            "order_lookup",
            "shipment_lookup",
            "carrier_evidence_lookup",
            "address_comparison",
            "execution",
        ):
            if not callable(getattr(self, field_name)):
                raise ValueError(f"{field_name} must be callable")
        if not isinstance(self.selected_disposition, Disposition):
            raise ValueError("selected_disposition must be a Disposition")
        if self.selected_disposition is Disposition.NONE_SELECTED:
            raise ValueError("selected_disposition must not be NONE_SELECTED")
        _utc(self.evaluated_at, "evaluated_at")
        refund_authorization_fields = (
            "proposed_refund_amount_minor",
            "proposed_refund_currency",
            "autonomous_refund_limit_minor",
            "autonomous_refund_limit_currency",
        )
        if self.selected_disposition is Disposition.APPROVE_REFUND:
            missing_fields = tuple(
                field_name
                for field_name in refund_authorization_fields
                if getattr(self, field_name) is None
            )
            if missing_fields:
                raise ValueError(
                    "APPROVE_REFUND requires refund authorization inputs: "
                    + ", ".join(missing_fields)
                )
        for field_name in (
            "proposed_refund_amount_minor",
            "autonomous_refund_limit_minor",
        ):
            value = getattr(self, field_name)
            if value is None:
                continue
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        for field_name in (
            "proposed_refund_currency",
            "autonomous_refund_limit_currency",
        ):
            value = getattr(self, field_name)
            if value is None:
                continue
            if (
                not isinstance(value, str)
                or len(value) != 3
                or not value.isalpha()
                or value != value.upper()
            ):
                raise ValueError(f"{field_name} must be a three-letter uppercase currency")
        object.__setattr__(self, "unresolved_policies", tuple(self.unresolved_policies))
        if any(
            not isinstance(policy, PolicyPlaceholder)
            for policy in self.unresolved_policies
        ):
            raise ValueError(
                "unresolved_policies entries must be PolicyPlaceholder values"
            )
        if self.human_reviewer is not None and not callable(self.human_reviewer):
            raise ValueError("human_reviewer must be callable")
        if not isinstance(self.execution_registry, ExecutionRegistry):
            raise ValueError("execution_registry must be an ExecutionRegistry")
        if not isinstance(self.execution_budget, ExecutionBudget):
            raise ValueError("execution_budget must be an ExecutionBudget")
        if not isinstance(self.retry_policy, RetryPolicy):
            raise ValueError("retry_policy must be a RetryPolicy")
        if not callable(self.backoff_sleep):
            raise ValueError("backoff_sleep must be callable")
        costs = dict(self.tool_estimated_cost_usd)
        for tool_name, cost in costs.items():
            if not isinstance(tool_name, str) or not tool_name.strip():
                raise ValueError("tool cost names must be non-empty strings")
            if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
                raise ValueError("tool estimated costs must be non-negative")
        object.__setattr__(self, "tool_estimated_cost_usd", MappingProxyType(costs))
        if type(self.derive_retailer_disposition) is not bool:
            raise ValueError("derive_retailer_disposition must be a bool")


def _result(
    case: SupportCase,
    trace: WorkflowTraceCollector,
    *,
    completed: bool = True,
    failure_stage: str | None = None,
    failure_reason: str | None = None,
    execution_operation: ExecutionOperation | None = None,
    budget_tracker: _BudgetTracker | None = None,
) -> WorkflowResult:
    return WorkflowResult(
        case,
        completed,
        case.case_status,
        case.disposition,
        failure_stage,
        failure_reason,
        trace.trace_id,
        trace.events,
        execution_operation,
        (
            budget_tracker.snapshot
            if budget_tracker is not None
            else BudgetSnapshot(0, 0, 0.0, 0.0, None, False)
        ),
    )


def _lookup_failure(record: object) -> str | None:
    retrieval_status = getattr(record, "retrieval_status", None)
    if retrieval_status is RetrievalStatus.FAILURE:
        return "retrieval failed"
    match_status = getattr(record, "match_status", MatchStatus.MATCHED)
    if match_status is not MatchStatus.MATCHED:
        return f"match status is {match_status.value}"
    return None


def _run_synthetic_support_case(
    case_input: SyntheticSupportCaseInput,
    configuration: WorkflowConfiguration,
    *,
    trace_id: str | None = None,
    clock: Callable[[], datetime] | None = None,
    timer: Callable[[], float] | None = None,
    existing_case: SupportCase | None = None,
    existing_trace_events: tuple[WorkflowTraceEvent, ...] = (),
    corrected_order_identifier: str | None = None,
) -> WorkflowResult:
    """Run one case, allowing the domain aggregate to enforce every mutation."""
    event_clock = clock or (lambda: datetime.now(UTC))
    elapsed_clock = timer or perf_counter
    correction_run = existing_case is not None
    trace = WorkflowTraceCollector(
        trace_id if trace_id is not None else str(uuid4()),
        existing_trace_events,
    )
    case = existing_case or SupportCase(case_input.case_id, actor=case_input.actor)
    budget = _BudgetTracker(configuration.execution_budget)

    def record(step: str, event_type: str, **values: object) -> None:
        trace.append(
            occurred_at=event_clock(),
            step=step,
            event_type=event_type,
            case_id=case.case_id,
            **values,
        )

    def change(
        step: str,
        event_type: str,
        operation: Callable[[], None],
        **values: object,
    ) -> None:
        before = case.snapshot()
        operation()
        record(
            step,
            event_type,
            state_before=before,
            state_after=case.snapshot(),
            **values,
        )

    def tool_call(
        step: str,
        tool_name: str,
        arguments: dict[str, object],
        operation: Callable[[], ToolResult],
        summarize: Callable[[ToolResult], dict[str, object]],
        before_attempt: Callable[[int], None] | None = None,
        after_failure: Callable[[SyntheticOperationalError], None] | None = None,
        after_result: Callable[[ToolResult], None] | None = None,
    ) -> ToolResult:
        policy = configuration.retry_policy
        cost = configuration.tool_estimated_cost_usd.get(tool_name, 0.0)
        traced_cost = tool_name in configuration.tool_estimated_cost_usd
        for retry_count in range(policy.max_attempts_per_call):
            try:
                budget.start_attempt(
                    retry=retry_count > 0, estimated_cost_usd=cost
                )
            except ExecutionBudgetExceeded as exhausted:
                record(
                    step,
                    "budget_exhausted",
                    tool_name=tool_name,
                    retry_count=retry_count,
                    estimated_cost_usd=(
                        budget.snapshot.estimated_cost_usd if traced_cost else None
                    ),
                    detail=(
                        f"dimension={exhausted.dimension.value}; "
                        f"used={exhausted.used}; limit={exhausted.limit}"
                    ),
                )
                raise
            if retry_count:
                record(
                    step,
                    "retry_attempted",
                    tool_name=tool_name,
                    retry_count=retry_count,
                )
            if before_attempt is not None:
                before_attempt(retry_count)
            record(
                step,
                "tool_called",
                tool_name=tool_name,
                tool_arguments=arguments,
                retry_count=retry_count,
                estimated_cost_usd=(
                    budget.snapshot.estimated_cost_usd if traced_cost else None
                ),
            )
            started = elapsed_clock()
            try:
                result = operation()
            except SyntheticOperationalError as failure:
                latency_ms = (elapsed_clock() - started) * 1000
                budget.finish_attempt(elapsed_ms=latency_ms, estimated_cost_usd=cost)
                record(
                    step,
                    "modeled_operational_failure",
                    tool_name=tool_name,
                    latency_ms=latency_ms,
                    retry_count=retry_count,
                    estimated_cost_usd=(
                        budget.snapshot.estimated_cost_usd if traced_cost else None
                    ),
                    detail=(
                        f"injection_id={failure.injection.injection_id}; "
                        f"target={failure.injection.target.value}; "
                        f"kind={failure.injection.kind.value}; "
                        f"call={failure.call_number}; "
                        f"retryable={str(failure.injection.retryable).lower()}; "
                        f"detail={failure.injection.detail}"
                    ),
                )
                if after_failure is not None:
                    after_failure(failure)
                retry_allowed = (
                    failure.injection.retryable
                    and failure.injection.kind in policy.retryable_failure_kinds
                )
                if not retry_allowed:
                    raise
                if retry_count + 1 >= policy.max_attempts_per_call:
                    record(
                        step,
                        "retry_exhausted",
                        tool_name=tool_name,
                        retry_count=retry_count,
                        detail=f"attempts={retry_count + 1}",
                    )
                    raise RetryExhausted(retry_count + 1) from failure
                try:
                    budget.ensure_attempt_allowed(
                        retry=True, estimated_cost_usd=cost
                    )
                except ExecutionBudgetExceeded as exhausted:
                    record(
                        step,
                        "budget_exhausted",
                        tool_name=tool_name,
                        retry_count=retry_count,
                        detail=(
                            f"dimension={exhausted.dimension.value}; "
                            f"used={exhausted.used}; limit={exhausted.limit}"
                        ),
                    )
                    raise
                delay_ms = policy.backoff_ms(retry_count + 1)
                try:
                    budget.ensure_backoff_allowed(delay_ms)
                except ExecutionBudgetExceeded as exhausted:
                    record(
                        step,
                        "budget_exhausted",
                        tool_name=tool_name,
                        retry_count=retry_count,
                        detail=(
                            f"dimension={exhausted.dimension.value}; "
                            f"used={exhausted.used}; limit={exhausted.limit}"
                        ),
                    )
                    raise
                record(
                    step,
                    "retry_scheduled",
                    tool_name=tool_name,
                    retry_count=retry_count + 1,
                    detail=f"backoff_ms={delay_ms}",
                )
                budget.record_backoff(delay_ms)
                configuration.backoff_sleep(delay_ms / 1000.0)
                record(
                    step,
                    "backoff_applied",
                    tool_name=tool_name,
                    retry_count=retry_count + 1,
                    detail=f"backoff_ms={delay_ms}",
                )
                try:
                    budget.ensure_active()
                except ExecutionBudgetExceeded as exhausted:
                    record(
                        step,
                        "budget_exhausted",
                        tool_name=tool_name,
                        retry_count=retry_count,
                        detail=(
                            f"dimension={exhausted.dimension.value}; "
                            f"used={exhausted.used}; limit={exhausted.limit}"
                        ),
                    )
                    raise
                continue
            latency_ms = (elapsed_clock() - started) * 1000
            budget.finish_attempt(elapsed_ms=latency_ms, estimated_cost_usd=cost)
            record(
                step,
                "tool_returned",
                tool_name=tool_name,
                tool_arguments=arguments,
                tool_result=summarize(result),
                latency_ms=latency_ms,
                retry_count=retry_count,
                estimated_cost_usd=(
                    budget.snapshot.estimated_cost_usd if traced_cost else None
                ),
            )
            if after_result is not None:
                after_result(result)
            try:
                budget.ensure_active()
            except ExecutionBudgetExceeded as exhausted:
                record(
                    step,
                    "budget_exhausted",
                    tool_name=tool_name,
                    retry_count=retry_count,
                    estimated_cost_usd=(
                        budget.snapshot.estimated_cost_usd if traced_cost else None
                    ),
                    detail=(
                        f"dimension={exhausted.dimension.value}; "
                        f"used={exhausted.used}; limit={exhausted.limit}"
                    ),
                )
                raise
            return result
        raise AssertionError("bounded retry loop did not return or raise")

    def operational_stop(
        stage: str,
        failure: SyntheticOperationalError | ExecutionBudgetExceeded | RetryExhausted,
        *,
        execution_operation: ExecutionOperation | None = None,
    ) -> WorkflowResult:
        if isinstance(failure, ExecutionBudgetExceeded):
            failure_stage = f"{stage}_budget"
            reason = str(failure)
        elif isinstance(failure, RetryExhausted):
            failure_stage = f"{stage}_retry"
            reason = str(failure)
        else:
            failure_stage = stage
            reason = failure.injection.detail
        record(
            "workflow",
            "workflow_stopped",
            state_before=case.snapshot(),
            state_after=case.snapshot(),
            final_outcome=case.case_status.value,
            detail=reason,
        )
        return _result(
            case,
            trace,
            completed=False,
            failure_stage=failure_stage,
            failure_reason=reason,
            execution_operation=execution_operation,
            budget_tracker=budget,
        )

    configured_budget = configuration.execution_budget
    record(
        "workflow",
        "budget_initialized",
        detail=(
            f"tool_calls={configured_budget.max_tool_calls}; "
            f"retries={configured_budget.max_retry_attempts}; "
            f"elapsed_ms={configured_budget.max_elapsed_ms}; "
            f"cost_usd={configured_budget.max_estimated_cost_usd}"
        ),
    )
    record(
        "workflow",
        "order_identifier_correction_started" if correction_run else "workflow_started",
        state_after=case.snapshot(),
        detail=(
            f"corrected_order_identifier={corrected_order_identifier}"
            if correction_run
            else None
        ),
    )
    if correction_run:
        lookup_specs = (
            (
                "order_lookup",
                "synthetic_order_lookup",
                {"order_id": corrected_order_identifier},
                lambda: configuration.order_lookup(corrected_order_identifier),
            ),
        )
    else:
        change(
            "customer_report",
            "customer_report_recorded",
            lambda: case.record_customer_report(
                CustomerReport(
                    case_input.order_identifier,
                    case_input.customer_confirmed_delivery_address or "not supplied",
                    case_input.customer_message,
                    "synthetic recipient check not specified",
                    case_input.received_at,
                ),
                actor=case_input.actor,
            ),
            detail="customer report stored; message and address omitted from trace",
        )
        lookup_specs = (
            (
                "customer_lookup",
                "synthetic_customer_lookup",
                {"customer_id": case_input.customer_identifier},
                lambda: configuration.customer_lookup(case_input.customer_identifier),
            ),
            (
                "order_lookup",
                "synthetic_order_lookup",
                {"order_id": case_input.order_identifier},
                lambda: configuration.order_lookup(case_input.order_identifier),
            ),
        )
    records: list[object] = []
    for stage, name, arguments, operation in lookup_specs:
        try:
            found = tool_call(
                stage,
                name,
                arguments,
                operation,
                lambda value: {
                    "record_id": getattr(value, "ref_id", None),
                    "retrieval_status": getattr(value, "retrieval_status").value,
                    "match_status": getattr(value, "match_status").value,
                    "order_value": getattr(value, "order_value", None),
                    "item_category": getattr(value, "item_category", None),
                },
            )
        except (SyntheticOperationalError, ExecutionBudgetExceeded, RetryExhausted) as failure:
            return operational_stop(stage, failure)
        records.append(found)
        reason = _lookup_failure(found)
        if correction_run:
            change(
                "intake",
                "order_identifier_correction_recorded",
                lambda: case.apply_order_identifier_correction(
                    corrected_order_identifier or "",
                    found,  # type: ignore[arg-type]
                    actor=case_input.actor,
                ),
                detail=f"corrected_order_identifier={corrected_order_identifier}",
            )
            if reason is not None:
                if (
                    found.retrieval_status is RetrievalStatus.SUCCESS
                    and found.match_status is MatchStatus.NOT_FOUND
                ):
                    reason = (
                        "corrected order identifier could not be matched; ask the "
                        "customer to verify or provide another corrected identifier"
                    )
                record(
                    "workflow",
                    "workflow_stopped",
                    final_outcome=case.case_status.value,
                    detail=reason,
                )
                return _result(
                    case,
                    trace,
                    completed=False,
                    failure_stage=stage,
                    failure_reason=reason,
                    budget_tracker=budget,
                )
            order = found
            break
        if reason is not None:
            if (
                stage == "order_lookup"
                and found.retrieval_status is RetrievalStatus.SUCCESS
                and found.match_status is MatchStatus.NOT_FOUND
            ):
                reason = (
                    "order identifier could not be matched; ask the customer to "
                    "verify or provide a corrected order identifier"
                )
                change(
                    "intake",
                    "customer_correction_requested",
                    lambda: case.request_order_identifier_correction(
                        records[0],  # type: ignore[arg-type]
                        actor=case_input.actor,
                        detail=reason,
                    ),
                    detail=reason,
                )
                record(
                    "workflow",
                    "workflow_stopped",
                    final_outcome=case.case_status.value,
                    detail=reason,
                )
                return _result(
                    case,
                    trace,
                    completed=False,
                    failure_stage=stage,
                    failure_reason=reason,
                    budget_tracker=budget,
                )
            change(
                "intake",
                "intake_failed",
                lambda: case.fail_intake(
                    actor=case_input.actor, detail=f"{stage}: {reason}"
                ),
                detail=f"{stage}: {reason}",
            )
            record(
                "workflow",
                "workflow_stopped",
                final_outcome=case.case_status.value,
                detail=stage,
            )
            return _result(
                case,
                trace,
                completed=False,
                failure_stage=stage,
                failure_reason=reason,
                budget_tracker=budget,
            )
    if not correction_run:
        customer, order = records
        change(
            "intake",
            "linkage_completed",
            lambda: case.link(
                customer, order, actor=case_input.actor  # type: ignore[arg-type]
            ),
        )

    try:
        shipment = tool_call(
            "shipment_lookup",
            "synthetic_shipment_lookup",
            {"shipment_id": case_input.shipment_identifier},
            lambda: configuration.shipment_lookup(case_input.shipment_identifier),
            lambda value: {
                "shipment_id": value.ref_id,
                "retrieval_status": value.retrieval_status.value,
                "carrier": value.carrier,
                "tracking_id": value.tracking_id,
                "fulfillment_timestamp": (
                    value.fulfillment_timestamp.isoformat()
                    if value.fulfillment_timestamp is not None else None
                ),
            },
        )
    except (SyntheticOperationalError, ExecutionBudgetExceeded, RetryExhausted) as failure:
        return operational_stop("shipment_lookup", failure)
    change(
        "shipment",
        "shipment_attached",
        lambda: case.attach_shipment(
            shipment, actor=case_input.actor  # type: ignore[arg-type]
        ),
    )
    change(
        "evidence_gathering",
        "evidence_gathering_entered",
        lambda: case.transition_to(
            CaseStatus.EVIDENCE_GATHERING, actor=case_input.actor
        ),
    )

    try:
        evidence = tool_call(
            "carrier_evidence_lookup",
            "synthetic_carrier_evidence_lookup",
            {"shipment_id": shipment.ref_id},
            lambda: configuration.carrier_evidence_lookup(shipment),
            lambda value: {
                "evidence_present": value is not None,
                "snapshot_id": getattr(value, "snapshot_id", None),
                "retrieval_status": (
                    value.retrieval_status.value if value is not None else None
                ),
                "delivery_status": getattr(value, "delivery_status", None),
                "delivery_timestamp": (
                    value.delivery_timestamp.isoformat()
                    if value is not None and value.delivery_timestamp is not None else None
                ),
                "tracking_event_history": " > ".join(
                    getattr(value, "tracking_event_history", ())
                ),
                "picture_proof_available": getattr(value, "picture_proof_available", None),
            },
        )
    except (SyntheticOperationalError, ExecutionBudgetExceeded, RetryExhausted) as failure:
        return operational_stop("carrier_evidence_lookup", failure)
    if evidence is not None:
        change(
            "carrier_evidence",
            "carrier_evidence_attached",
            lambda: case.attach_carrier_evidence(evidence, actor=case_input.actor),
            detail=(
                "retrieval_failed"
                if evidence.retrieval_status is RetrievalStatus.FAILURE
                else "evidence_available"
            ),
        )
    else:
        record(
            "carrier_evidence",
            "carrier_evidence_missing",
            state_before=case.snapshot(),
            state_after=case.snapshot(),
            detail="lookup returned no evidence",
        )
    try:
        address_result = tool_call(
            "address_comparison",
            "synthetic_address_comparison",
            {"case_id": case.case_id, "internal_order_id": order.ref_id,
             "customer_confirmed_support_channel_address": "value present" if case_input.customer_confirmed_delivery_address else "missing",
             "retailer_order_shipping_address": "value present" if order.ship_to_address_on_file else "missing"},  # type: ignore[union-attr]
            lambda: configuration.address_comparison(case_input, order),  # type: ignore[arg-type]
            lambda value: {"match_result": value.value},
        )
    except (SyntheticOperationalError, ExecutionBudgetExceeded, RetryExhausted) as failure:
        return operational_stop("address_comparison", failure)
    change(
        "address_comparison",
        "address_comparison_recorded",
        lambda: case.record_address_match_result(
            address_result, actor=case_input.actor  # type: ignore[arg-type]
        ),
    )
    change(
        "policy",
        "policy_review_entered",
        lambda: case.transition_to(CaseStatus.POLICY_REVIEW, actor=case_input.actor),
    )

    evaluation = evaluate_synthetic_structural_policy(
        case,
        evaluation_id=f"{case.case_id}-policy-evaluation",
        evaluated_at=configuration.evaluated_at,
        unresolved_policies=configuration.unresolved_policies,
    )
    record(
        "policy",
        "policy_evaluation_completed",
        evaluation_result=evaluation.route.value,
        detail="deterministic structural policy",
    )
    change(
        "policy",
        "policy_route_recorded",
        lambda: case.record_policy_evaluation(evaluation, actor="synthetic-policy"),
        evaluation_result=evaluation.route.value,
        escalation=evaluation.route.value == "require_human_review",
    )

    if case.case_status is CaseStatus.AWAITING_CUSTOMER_ACTION:
        record("workflow", "workflow_completed", final_outcome=case.case_status.value)
        return _result(case, trace, budget_tracker=budget)
    if case.case_status is CaseStatus.HUMAN_REVIEW:
        if configuration.human_reviewer is None:
            record(
                "workflow",
                "workflow_stopped",
                final_outcome=case.case_status.value,
                escalation=True,
                detail="human reviewer is not configured",
            )
            return _result(
                case,
                trace,
                completed=False,
                failure_stage="human_review",
                failure_reason="human reviewer is not configured",
                budget_tracker=budget,
            )
        try:
            review_result = tool_call(
                "human_review",
                "synthetic_human_reviewer",
                {"case_id": case.case_id},
                lambda: configuration.human_reviewer(case),  # type: ignore[misc]
                lambda value: {
                    "review_id": value[0].review_id,
                    "disposition": value[1].disposition.value,
                },
            )
        except (SyntheticOperationalError, ExecutionBudgetExceeded, RetryExhausted) as failure:
            return operational_stop("human_review", failure)
        request, decision = review_result
        change(
            "human_review",
            "human_review_opened",
            lambda: case.open_human_review(request, actor="synthetic-review"),
            escalation=True,
        )
        change(
            "human_review",
            "human_review_decided",
            lambda: case.record_human_review_decision(
                decision, actor="synthetic-review"
            ),
            escalation=True,
            human_override=True,
            final_outcome=decision.disposition.value,
        )
    else:
        selected_disposition = configuration.selected_disposition
        disposition_arguments = {}
        disposition_detail = "configured regression disposition"
        if configuration.derive_retailer_disposition:
            delivered = bool(case.carrier_evidence_snapshots) and all(
                item.retrieval_status is RetrievalStatus.SUCCESS and item.delivery_status == "delivered"
                for item in case.carrier_evidence_snapshots
            )
            selected_disposition = (Disposition.APPROVE_REFUND
                if delivered and case.address_match_result is AddressMatchResult.MATCH
                else Disposition.REQUEST_MORE_INFO)
            disposition_arguments = {
                "issue_type": "delivered_not_received",
                "structural_gate": evaluation.route.value,
                "carrier_delivery_status": case.carrier_evidence_snapshots[-1].delivery_status if case.carrier_evidence_snapshots else None,
                "address_match_result": case.address_match_result.value,
            }
            disposition_detail = "rule: delivered_not_received + complete evidence + delivered + address match => refund"
        change(
            "disposition",
            "disposition_selected",
            lambda: case.select_disposition(
                selected_disposition, actor=case_input.actor
            ),
            final_outcome=selected_disposition.value,
            tool_arguments=disposition_arguments,
            detail=disposition_detail,
        )

    if case.case_status is not CaseStatus.EXECUTING:
        record("workflow", "workflow_completed", final_outcome=case.case_status.value)
        return _result(case, trace, budget_tracker=budget)

    if case.disposition is Disposition.APPROVE_REFUND:
        currencies_match = (
            configuration.proposed_refund_currency
            == configuration.autonomous_refund_limit_currency
        )
        within_limit = (
            currencies_match
            and configuration.proposed_refund_amount_minor
            <= configuration.autonomous_refund_limit_minor
        )
        if not within_limit:
            detail = (
                f"refund_amount_minor={configuration.proposed_refund_amount_minor}; "
                f"currency={configuration.proposed_refund_currency}; "
                f"autonomous_limit_minor={configuration.autonomous_refund_limit_minor}"
            )
            if not currencies_match:
                detail += (
                    "; autonomous_limit_currency="
                    f"{configuration.autonomous_refund_limit_currency}"
                )
            change(
                "authority",
                "execution_authority_blocked",
                lambda: case.block_refund_execution_for_authority(
                    actor="synthetic-authority", detail=detail
                ),
                escalation=True,
                detail=detail,
                tool_arguments={
                    "refund_amount_minor": configuration.proposed_refund_amount_minor,
                    "amount_source": "matched synthetic retailer record",
                    "currency": configuration.proposed_refund_currency,
                    "autonomous_limit_minor": configuration.autonomous_refund_limit_minor,
                    "autonomous_limit_currency": configuration.autonomous_refund_limit_currency,
                    "limit_source": "workflow configuration",
                    "currency_match": currencies_match,
                    "amount_within_limit": False,
                },
            )
            record(
                "workflow",
                "workflow_stopped",
                final_outcome=case.case_status.value,
                escalation=True,
                detail="approved refund requires authorized human review",
            )
            return _result(
                case,
                trace,
                completed=False,
                failure_stage="authority",
                failure_reason=(
                    "proposed refund exceeds autonomous refund limit"
                    if currencies_match
                    else "refund currency does not match autonomous refund limit currency"
                ),
                budget_tracker=budget,
            )
        record(
            "authority",
            "execution_authority_granted",
            tool_arguments={
                "refund_amount_minor": configuration.proposed_refund_amount_minor,
                "amount_source": "matched synthetic retailer record",
                "currency": configuration.proposed_refund_currency,
                "autonomous_limit_minor": configuration.autonomous_refund_limit_minor,
                "autonomous_limit_currency": configuration.autonomous_refund_limit_currency,
                "limit_source": "workflow configuration",
                "currency_match": currencies_match,
                "amount_within_limit": within_limit,
            },
            evaluation_result="granted",
        )

    idempotency_key = generate_idempotency_key(case.case_id, case.disposition)
    operation, created = configuration.execution_registry.get_or_create(
        idempotency_key, case.case_id, case.disposition, event_clock()
    )
    operation_trace = {
        "operation_id": operation.operation_id,
        "idempotency_key": operation.idempotency_key,
        "attempt_count": operation.attempt_count,
        "operation_status": operation.status.value,
    }
    if created:
        record("execution", "execution_operation_created", **operation_trace)

    change(
        "execution",
        "execution_started",
        lambda: case.record_execution_status(
            ExecutionStatus.IN_PROGRESS, actor="synthetic-execution"
        ),
        **operation_trace,
    )

    if operation.status is OperationStatus.SUCCEEDED:
        record(
            "execution",
            "duplicate_execution_suppressed",
            detail="execution adapter was not called",
            **operation_trace,
        )
        record(
            "execution",
            "prior_successful_result_reused",
            detail="original successful result reused",
            **operation_trace,
        )
        execution = ExecutionResult(True, operation.result_detail or "recorded success")
    else:
        was_retry = operation.status is OperationStatus.FAILED

        def start_execution_attempt(retry_count: int) -> None:
            nonlocal operation, operation_trace
            operation = configuration.execution_registry.start_attempt(idempotency_key)
            operation_trace = {
                "operation_id": operation.operation_id,
                "idempotency_key": operation.idempotency_key,
                "attempt_count": operation.attempt_count,
                "operation_status": operation.status.value,
            }
            if was_retry or retry_count:
                record("execution", "later_retry_attempted", **operation_trace)
            record(
                "execution",
                "execution_adapter_invoked",
                retry_count=retry_count,
                **operation_trace,
            )

        def fail_execution_attempt(failure: SyntheticOperationalError) -> None:
            nonlocal operation, operation_trace
            operation = configuration.execution_registry.record_failure(
                idempotency_key, failure.injection.detail
            )
            operation_trace = {
                "operation_id": operation.operation_id,
                "idempotency_key": operation.idempotency_key,
                "attempt_count": operation.attempt_count,
                "operation_status": operation.status.value,
            }
            record("execution", "failed_operation_recorded", **operation_trace)

        def finish_execution_attempt(result: ExecutionResult) -> None:
            nonlocal operation, operation_trace
            operation = (
                configuration.execution_registry.record_success(
                    idempotency_key, result.detail
                )
                if result.succeeded
                else configuration.execution_registry.record_failure(
                    idempotency_key, result.detail
                )
            )
            operation_trace = {
                "operation_id": operation.operation_id,
                "idempotency_key": operation.idempotency_key,
                "attempt_count": operation.attempt_count,
                "operation_status": operation.status.value,
            }
            record(
                "execution",
                "successful_operation_recorded"
                if result.succeeded
                else "failed_operation_recorded",
                **operation_trace,
            )

        try:
            execution = tool_call(
                "execution",
                "synthetic_execution_adapter",
                {
                    "case_id": case.case_id,
                    "disposition": case.disposition.value,
                    "idempotency_key": idempotency_key,
                    "target_order_reference": order.ref_id,
                    "refund_amount_minor": configuration.proposed_refund_amount_minor,
                    "currency": configuration.proposed_refund_currency,
                },
                lambda: configuration.execution(
                    idempotency_key, case.disposition, case
                ),
                lambda value: {
                    "succeeded": value.succeeded,
                    "outcome_detail": value.detail,
                },
                before_attempt=start_execution_attempt,
                after_failure=fail_execution_attempt,
                after_result=finish_execution_attempt,
            )
        except (SyntheticOperationalError, ExecutionBudgetExceeded, RetryExhausted) as failure:
            if operation.status is OperationStatus.SUCCEEDED:
                detail = operation.result_detail or "recorded success"
                change(
                    "execution",
                    "execution_result_recorded",
                    lambda: case.record_execution_status(
                        ExecutionStatus.SUCCEEDED,
                        actor="synthetic-execution",
                        detail=detail,
                    ),
                    final_outcome=ExecutionStatus.SUCCEEDED.value,
                    **operation_trace,
                )
                change(
                    "execution",
                    "external_follow_up_entered"
                    if case.disposition is Disposition.OPEN_CARRIER_INQUIRY
                    else "execution_completed",
                    lambda: case.complete_execution(
                        actor="synthetic-execution", detail=detail
                    ),
                )
                return operational_stop(
                    "execution", failure, execution_operation=operation
                )
            detail = (
                failure.injection.detail
                if isinstance(failure, SyntheticOperationalError)
                else str(failure)
            )
            change(
                "execution",
                "execution_result_recorded",
                lambda: case.record_execution_status(
                    ExecutionStatus.FAILED,
                    actor="synthetic-execution",
                    detail=detail,
                ),
                final_outcome=ExecutionStatus.FAILED.value,
                **operation_trace,
            )
            change(
                "execution",
                "execution_failure_routed",
                lambda: case.route_execution_failure_to_review(
                    actor="synthetic-execution", detail=detail
                ),
                escalation=True,
            )
            return operational_stop(
                "execution",
                failure,
                execution_operation=operation,
            )
    status = (
        ExecutionStatus.SUCCEEDED
        if execution.succeeded
        else ExecutionStatus.FAILED
    )
    change(
        "execution",
        "execution_result_recorded",
        lambda: case.record_execution_status(
            status, actor="synthetic-execution", detail=execution.detail
        ),
        final_outcome=status.value,
        **operation_trace,
    )
    if execution.succeeded:
        change(
            "execution",
            "external_follow_up_entered"
            if case.disposition is Disposition.OPEN_CARRIER_INQUIRY
            else "execution_completed",
            lambda: case.complete_execution(
                actor="synthetic-execution", detail=execution.detail
            ),
        )
        record("workflow", "workflow_completed", final_outcome=case.case_status.value)
        return _result(
            case,
            trace,
            execution_operation=operation,
            budget_tracker=budget,
        )

    change(
        "execution",
        "execution_failure_routed",
        lambda: case.route_execution_failure_to_review(
            actor="synthetic-execution", detail=execution.detail
        ),
        escalation=True,
    )
    record(
        "workflow",
        "workflow_stopped",
        final_outcome=case.case_status.value,
        detail="execution failed",
    )
    return _result(
        case,
        trace,
        completed=False,
        failure_stage="execution",
        failure_reason=execution.detail,
        execution_operation=operation,
        budget_tracker=budget,
    )


def run_synthetic_support_case(
    case_input: SyntheticSupportCaseInput,
    configuration: WorkflowConfiguration,
    *,
    trace_id: str | None = None,
    clock: Callable[[], datetime] | None = None,
    timer: Callable[[], float] | None = None,
) -> WorkflowResult:
    """Run a new synthetic support case from intake."""
    return _run_synthetic_support_case(
        case_input,
        configuration,
        trace_id=trace_id,
        clock=clock,
        timer=timer,
    )


def correct_unmatched_order_identifier(
    stopped_result: WorkflowResult,
    original_input: SyntheticSupportCaseInput,
    corrected_order_identifier: str,
    configuration: WorkflowConfiguration,
    *,
    clock: Callable[[], datetime] | None = None,
    timer: Callable[[], float] | None = None,
) -> WorkflowResult:
    """Apply one corrected identifier to an existing pre-linkage stopped case."""
    if not isinstance(stopped_result, WorkflowResult):
        raise TypeError("stopped_result must be a WorkflowResult")
    if stopped_result.case.case_id != original_input.case_id:
        raise ValueError("original_input case_id must match the stopped case")
    if stopped_result.completed or stopped_result.failure_stage != "order_lookup":
        raise ValueError("case must have stopped at order_lookup")
    if (
        stopped_result.case.case_status is not CaseStatus.AWAITING_CUSTOMER_ACTION
        or stopped_result.case.order_ref is not None
        or not stopped_result.case.awaiting_order_identifier_correction
    ):
        raise ValueError("case is not eligible for unmatched order correction")
    if (
        not isinstance(corrected_order_identifier, str)
        or not corrected_order_identifier.strip()
    ):
        raise ValueError("corrected_order_identifier must not be empty")
    corrected_input = replace(
        original_input,
        order_identifier=corrected_order_identifier,
    )
    return _run_synthetic_support_case(
        corrected_input,
        configuration,
        trace_id=stopped_result.trace_id,
        clock=clock,
        timer=timer,
        existing_case=stopped_result.case,
        existing_trace_events=stopped_result.trace_events,
        corrected_order_identifier=corrected_order_identifier,
    )


def route_customer_message_extraction(
    extraction_result: ExtractionResult,
    trusted_context: TrustedIntakeContext,
    configuration: WorkflowConfiguration,
) -> IntakeRoutingResult:
    """Route validated extraction output without exposing model metadata to policy."""
    if not isinstance(extraction_result, ExtractionResult):
        raise TypeError("extraction_result must be an ExtractionResult")
    if not isinstance(trusted_context, TrustedIntakeContext):
        raise TypeError("trusted_context must be a TrustedIntakeContext")
    if not isinstance(configuration, WorkflowConfiguration):
        raise TypeError("configuration must be a WorkflowConfiguration")

    if extraction_result.status is ExtractionStatus.INVALID_MODEL_OUTPUT:
        return IntakeRoutingResult(
            IntakeRoute.MANUAL_INTAKE_REVIEW_REQUIRED,
            reason=extraction_result.validation_reason,
        )

    extraction = extraction_result.extraction
    if extraction is None:
        raise ValueError("validated extraction status requires an extraction")

    if extraction_result.status is ExtractionStatus.NEEDS_CLARIFICATION:
        if not extraction.needs_clarification:
            raise ValueError("clarification status requires clarification business data")
        return IntakeRoutingResult(
            IntakeRoute.CLARIFICATION_REQUIRED,
            reason=extraction.clarification_reason,
            missing_required_fields=extraction.missing_required_fields,
            extraction=extraction,
        )

    if extraction_result.status is not ExtractionStatus.COMPLETE:
        raise ValueError("unsupported extraction status")
    if extraction.needs_clarification:
        raise ValueError("complete status cannot contain clarification business data")
    if extraction.issue_type is ExtractionIssueType.UNKNOWN:
        return IntakeRoutingResult(
            IntakeRoute.GENERAL_TRIAGE_REQUIRED,
            extraction=extraction,
        )
    if extraction.issue_type is not ExtractionIssueType.DELIVERED_NOT_RECEIVED:
        raise ValueError("complete extraction has an unsupported issue type")
    if extraction.order_identifier is None:
        raise ValueError("delivered-not-received workflow requires an order identifier")

    workflow_result = run_synthetic_support_case(
        SyntheticSupportCaseInput(
            case_id=trusted_context.case_id,
            customer_message=extraction.original_message,
            customer_identifier=trusted_context.customer_identifier,
            order_identifier=extraction.order_identifier,
            shipment_identifier=trusted_context.shipment_identifier,
            actor=trusted_context.actor,
            received_at=trusted_context.received_at,
            customer_confirmed_delivery_address=trusted_context.customer_confirmed_delivery_address,
        ),
        configuration,
    )
    return IntakeRoutingResult(
        IntakeRoute.DELIVERED_NOT_RECEIVED_WORKFLOW,
        workflow_result=workflow_result,
        extraction=extraction,
    )
