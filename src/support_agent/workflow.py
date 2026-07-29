"""Deterministic orchestration for one synthetic support case."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

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

    def __call__(self, disposition: Disposition, case: SupportCase) -> ExecutionResult:
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
ExecutionAdapter = Callable[[Disposition, SupportCase], ExecutionResult]
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


def _result(
    case: SupportCase,
    *,
    completed: bool = True,
    failure_stage: str | None = None,
    failure_reason: str | None = None,
) -> WorkflowResult:
    return WorkflowResult(
        case,
        completed,
        case.case_status,
        case.disposition,
        failure_stage,
        failure_reason,
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
) -> WorkflowResult:
    """Run one case, allowing the domain aggregate to enforce every mutation."""
    case = SupportCase(case_input.case_id, actor=case_input.actor)
    case.record_customer_report(
        CustomerReport(
            case_input.order_identifier,
            "synthetic address supplied through configured comparison",
            case_input.customer_message,
            "synthetic recipient check not specified",
            case_input.received_at,
        ),
        actor=case_input.actor,
    )

    customer = configuration.customer_lookup(case_input.customer_identifier)
    order = configuration.order_lookup(case_input.order_identifier)
    for stage, record in (("customer_lookup", customer), ("order_lookup", order)):
        reason = _lookup_failure(record)
        if reason is not None:
            case.fail_intake(actor=case_input.actor, detail=f"{stage}: {reason}")
            return _result(
                case,
                completed=False,
                failure_stage=stage,
                failure_reason=reason,
            )
    case.link(customer, order, actor=case_input.actor)

    shipment = configuration.shipment_lookup(case_input.shipment_identifier)
    case.attach_shipment(shipment, actor=case_input.actor)
    case.transition_to(CaseStatus.EVIDENCE_GATHERING, actor=case_input.actor)

    evidence = configuration.carrier_evidence_lookup(shipment)
    if evidence is not None:
        case.attach_carrier_evidence(evidence, actor=case_input.actor)
    address_result = configuration.address_comparison(case_input, order)
    case.record_address_match_result(address_result, actor=case_input.actor)
    case.transition_to(CaseStatus.POLICY_REVIEW, actor=case_input.actor)

    evaluation = evaluate_synthetic_structural_policy(
        case,
        evaluation_id=f"{case.case_id}-policy-evaluation",
        evaluated_at=configuration.evaluated_at,
        unresolved_policies=configuration.unresolved_policies,
    )
    case.record_policy_evaluation(evaluation, actor="synthetic-policy")

    if case.case_status is CaseStatus.AWAITING_CUSTOMER_ACTION:
        return _result(case)
    if case.case_status is CaseStatus.HUMAN_REVIEW:
        if configuration.human_reviewer is None:
            return _result(
                case,
                completed=False,
                failure_stage="human_review",
                failure_reason="human reviewer is not configured",
            )
        request, decision = configuration.human_reviewer(case)
        case.open_human_review(request, actor="synthetic-review")
        case.record_human_review_decision(decision, actor="synthetic-review")
    else:
        case.select_disposition(
            configuration.selected_disposition, actor=case_input.actor
        )

    if case.case_status is not CaseStatus.EXECUTING:
        return _result(case)

    case.record_execution_status(
        ExecutionStatus.IN_PROGRESS, actor="synthetic-execution"
    )
    execution = configuration.execution(case.disposition, case)
    status = (
        ExecutionStatus.SUCCEEDED
        if execution.succeeded
        else ExecutionStatus.FAILED
    )
    case.record_execution_status(
        status, actor="synthetic-execution", detail=execution.detail
    )
    if execution.succeeded:
        case.complete_execution(actor="synthetic-execution", detail=execution.detail)
        return _result(case)

    case.route_execution_failure_to_review(
        actor="synthetic-execution", detail=execution.detail
    )
    return _result(
        case,
        completed=False,
        failure_stage="execution",
        failure_reason=execution.detail,
    )
