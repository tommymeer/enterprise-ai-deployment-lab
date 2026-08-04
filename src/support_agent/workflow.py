"""Deterministic orchestration for one synthetic support case."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Callable
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
    unresolved_policies: tuple[PolicyPlaceholder, ...] = ()
    human_reviewer: HumanReviewer | None = None
    execution_registry: ExecutionRegistry = field(default_factory=ExecutionRegistry)

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


def _result(
    case: SupportCase,
    trace: WorkflowTraceCollector,
    *,
    completed: bool = True,
    failure_stage: str | None = None,
    failure_reason: str | None = None,
    execution_operation: ExecutionOperation | None = None,
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
    )


def _lookup_failure(record: object) -> str | None:
    retrieval_status = getattr(record, "retrieval_status", None)
    if retrieval_status is RetrievalStatus.FAILURE:
        return "retrieval failed"
    match_status = getattr(record, "match_status", MatchStatus.MATCHED)
    if match_status is not MatchStatus.MATCHED:
        return f"match status is {match_status.value}"
    return None


def run_synthetic_support_case(
    case_input: SyntheticSupportCaseInput,
    configuration: WorkflowConfiguration,
    *,
    trace_id: str | None = None,
    clock: Callable[[], datetime] | None = None,
    timer: Callable[[], float] | None = None,
) -> WorkflowResult:
    """Run one case, allowing the domain aggregate to enforce every mutation."""
    event_clock = clock or (lambda: datetime.now(UTC))
    elapsed_clock = timer or perf_counter
    trace = WorkflowTraceCollector(
        trace_id if trace_id is not None else str(uuid4())
    )
    case = SupportCase(case_input.case_id, actor=case_input.actor)

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
        operation: Callable[[], object],
        summarize: Callable[[object], dict[str, object]],
    ) -> object:
        record(
            step,
            "tool_called",
            tool_name=tool_name,
            tool_arguments=arguments,
            retry_count=0,
        )
        started = elapsed_clock()
        result = operation()
        latency_ms = (elapsed_clock() - started) * 1000
        record(
            step,
            "tool_returned",
            tool_name=tool_name,
            tool_arguments=arguments,
            tool_result=summarize(result),
            latency_ms=latency_ms,
            retry_count=0,
        )
        return result

    record("workflow", "workflow_started", state_after=case.snapshot())
    change(
        "customer_report",
        "customer_report_recorded",
        lambda: case.record_customer_report(
            CustomerReport(
                case_input.order_identifier,
                "synthetic address supplied through configured comparison",
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
        found = tool_call(
            stage,
            name,
            arguments,
            operation,
            lambda value: {
                "record_id": getattr(value, "ref_id", None),
                "retrieval_status": getattr(value, "retrieval_status").value,
                "match_status": getattr(value, "match_status").value,
            },
        )
        records.append(found)
        reason = _lookup_failure(found)
        if reason is not None:
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
            )
    customer, order = records
    change(
        "intake",
        "linkage_completed",
        lambda: case.link(
            customer, order, actor=case_input.actor  # type: ignore[arg-type]
        ),
    )

    shipment = tool_call(
        "shipment_lookup",
        "synthetic_shipment_lookup",
        {"shipment_id": case_input.shipment_identifier},
        lambda: configuration.shipment_lookup(case_input.shipment_identifier),
        lambda value: {
            "shipment_id": getattr(value, "ref_id"),
            "retrieval_status": getattr(value, "retrieval_status").value,
        },
    )
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

    evidence = tool_call(
        "carrier_evidence_lookup",
        "synthetic_carrier_evidence_lookup",
        {"shipment_id": shipment.ref_id},  # type: ignore[union-attr]
        lambda: configuration.carrier_evidence_lookup(shipment),  # type: ignore[arg-type]
        lambda value: {
            "evidence_present": value is not None,
            "snapshot_id": getattr(value, "snapshot_id", None),
            "retrieval_status": (
                getattr(value, "retrieval_status").value if value is not None else None
            ),
        },
    )
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
    address_result = tool_call(
        "address_comparison",
        "synthetic_address_comparison",
        {"case_id": case.case_id, "order_id": order.ref_id},  # type: ignore[union-attr]
        lambda: configuration.address_comparison(case_input, order),  # type: ignore[arg-type]
        lambda value: {"match_result": value.value},
    )
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
        return _result(case, trace)
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
            )
        request, decision = tool_call(
            "human_review",
            "synthetic_human_reviewer",
            {"case_id": case.case_id},
            lambda: configuration.human_reviewer(case),  # type: ignore[misc]
            lambda value: {
                "review_id": value[0].review_id,
                "disposition": value[1].disposition.value,
            },
        )  # type: ignore[misc]
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
        change(
            "disposition",
            "disposition_selected",
            lambda: case.select_disposition(
                configuration.selected_disposition, actor=case_input.actor
            ),
            final_outcome=configuration.selected_disposition.value,
        )

    if case.case_status is not CaseStatus.EXECUTING:
        record("workflow", "workflow_completed", final_outcome=case.case_status.value)
        return _result(case, trace)

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
        operation = configuration.execution_registry.start_attempt(idempotency_key)
        operation_trace = {
            "operation_id": operation.operation_id,
            "idempotency_key": operation.idempotency_key,
            "attempt_count": operation.attempt_count,
            "operation_status": operation.status.value,
        }
        if was_retry:
            record("execution", "later_retry_attempted", **operation_trace)
        record("execution", "execution_adapter_invoked", **operation_trace)
        execution = tool_call(
            "execution",
            "synthetic_execution_adapter",
            {
                "case_id": case.case_id,
                "disposition": case.disposition.value,
                "idempotency_key": idempotency_key,
            },
            lambda: configuration.execution(idempotency_key, case.disposition, case),
            lambda value: {
                "succeeded": value.succeeded,
                "detail_present": bool(value.detail),
            },
        )
        operation = (
            configuration.execution_registry.record_success(
                idempotency_key, execution.detail
            )
            if execution.succeeded
            else configuration.execution_registry.record_failure(
                idempotency_key, execution.detail
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
            if execution.succeeded
            else "failed_operation_recorded",
            **operation_trace,
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
        return _result(case, trace, execution_operation=operation)

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
    )
