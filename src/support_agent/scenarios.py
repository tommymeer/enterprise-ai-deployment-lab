"""Versionable synthetic scenarios for deterministic support-case regression tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from .domain import (
    AddressMatchResult,
    CarrierEvidenceSnapshot,
    CaseStatus,
    CustomerReference,
    Disposition,
    ExecutionStatus,
    FollowUpStatus,
    HumanReviewDecision,
    HumanReviewRequest,
    MatchStatus,
    OrderReference,
    PolicyPlaceholder,
    RetrievalStatus,
    ShipmentReference,
)
from .execution import EXECUTABLE_DISPOSITIONS, ExecutionRegistry, OperationStatus
from .workflow import (
    ExecutionResult,
    SyntheticAddressComparison,
    SyntheticCarrierEvidenceLookup,
    SyntheticCustomerLookup,
    SyntheticExecutionAdapter,
    SyntheticHumanReviewer,
    SyntheticOrderLookup,
    SyntheticShipmentLookup,
    SyntheticSupportCaseInput,
    WorkflowConfiguration,
    WorkflowResult,
    run_synthetic_support_case,
)


class ScenarioCategory(StrEnum):
    HAPPY_PATH = "happy_path"
    CUSTOMER_ACTION = "customer_action"
    HUMAN_REVIEW = "human_review"
    INTAKE_FAILURE = "intake_failure"
    EVIDENCE_FAILURE = "evidence_failure"
    EXECUTION_FAILURE = "execution_failure"
    EXTERNAL_FOLLOW_UP = "external_follow_up"


@dataclass(frozen=True, slots=True)
class RegressionMetadata:
    source: str
    failure_category: str | None
    added_at: datetime
    fixed_in_version: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if self.source not in {"synthetic", "production_regression"}:
            raise ValueError("source must be synthetic or production_regression")
        _utc(self.added_at, "added_at")
        for name in ("failure_category", "fixed_in_version", "notes"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be non-empty when provided")


@dataclass(frozen=True, slots=True)
class ScenarioExpectation:
    completed: bool
    case_status: CaseStatus
    disposition: Disposition
    execution_status: ExecutionStatus
    follow_up_status: FollowUpStatus
    failure_stage: str | None
    escalation: bool
    human_review: bool
    execution_invoked: bool
    execution_succeeded: bool | None
    trace_events: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_events", tuple(self.trace_events))
        if type(self.completed) is not bool:
            raise ValueError("completed must be a bool")
        for name, expected_type in (
            ("case_status", CaseStatus),
            ("disposition", Disposition),
            ("execution_status", ExecutionStatus),
            ("follow_up_status", FollowUpStatus),
        ):
            if not isinstance(getattr(self, name), expected_type):
                raise ValueError(f"{name} must be a {expected_type.__name__}")
        if self.completed and self.failure_stage is not None:
            raise ValueError("completed expectations cannot have a failure stage")
        if not self.completed and not self.failure_stage:
            raise ValueError("incomplete expectations require a failure stage")
        for name in ("escalation", "human_review", "execution_invoked"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a bool")
        if self.execution_succeeded is not None and type(self.execution_succeeded) is not bool:
            raise ValueError("execution_succeeded must be a bool or None")
        if not self.execution_invoked and self.execution_succeeded is not None:
            raise ValueError("execution success cannot be expected without invocation")
        if self.execution_invoked and self.disposition not in EXECUTABLE_DISPOSITIONS:
            raise ValueError("execution cannot be expected for a non-executable disposition")
        if any(not isinstance(event, str) or not event.strip() for event in self.trace_events):
            raise ValueError("trace events must be non-empty strings")


@dataclass(frozen=True, slots=True)
class SupportCaseScenario:
    scenario_id: str
    title: str
    description: str
    category: ScenarioCategory
    case_input: SyntheticSupportCaseInput
    customer_reference: CustomerReference
    order_reference: OrderReference
    shipment_reference: ShipmentReference
    carrier_evidence: CarrierEvidenceSnapshot | None
    address_match_result: AddressMatchResult
    unresolved_policies: tuple[PolicyPlaceholder, ...]
    selected_disposition: Disposition
    human_review_request: HumanReviewRequest | None
    human_review_decision: HumanReviewDecision | None
    execution_results: SyntheticExecutionAdapter
    expectation: ScenarioExpectation
    tags: tuple[str, ...]
    regression_metadata: RegressionMetadata

    def __post_init__(self) -> None:
        for name in ("scenario_id", "title", "description"):
            _non_empty(getattr(self, name), name)
        if not isinstance(self.category, ScenarioCategory):
            raise ValueError("category must be a ScenarioCategory")
        for name, expected_type in (
            ("case_input", SyntheticSupportCaseInput),
            ("customer_reference", CustomerReference),
            ("order_reference", OrderReference),
            ("shipment_reference", ShipmentReference),
            ("address_match_result", AddressMatchResult),
            ("execution_results", SyntheticExecutionAdapter),
            ("expectation", ScenarioExpectation),
            ("regression_metadata", RegressionMetadata),
        ):
            if not isinstance(getattr(self, name), expected_type):
                raise ValueError(f"{name} must be a {expected_type.__name__}")
        if self.carrier_evidence is not None and not isinstance(
            self.carrier_evidence, CarrierEvidenceSnapshot
        ):
            raise ValueError("carrier_evidence must be a CarrierEvidenceSnapshot or None")
        object.__setattr__(self, "unresolved_policies", tuple(self.unresolved_policies))
        object.__setattr__(self, "tags", tuple(self.tags))
        if any(not isinstance(item, PolicyPlaceholder) for item in self.unresolved_policies):
            raise ValueError("unresolved_policies must contain PolicyPlaceholder values")
        if not isinstance(self.selected_disposition, Disposition):
            raise ValueError("selected_disposition must be a Disposition")
        if self.selected_disposition is Disposition.NONE_SELECTED:
            raise ValueError("selected_disposition must not be NONE_SELECTED")
        if (self.human_review_request is None) != (self.human_review_decision is None):
            raise ValueError("human review request and decision must be provided together")
        if self.human_review_request is not None and (
            self.human_review_request.review_id != self.human_review_decision.review_id
        ):
            raise ValueError("human review request and decision IDs must match")
        if any(not isinstance(tag, str) or not tag.strip() for tag in self.tags):
            raise ValueError("tags must be non-empty strings")
        intake_failure = self.category is ScenarioCategory.INTAKE_FAILURE
        if intake_failure and (
            self.expectation.execution_invoked
            or self.expectation.execution_status is not ExecutionStatus.NOT_APPLICABLE
            or self.expectation.human_review
        ):
            raise ValueError("intake failure cannot expect execution or human review")

        configured_disposition = (
            self.human_review_decision.disposition
            if self.human_review_decision is not None
            else self.selected_disposition
        )
        retains_no_disposition = intake_failure or self.carrier_evidence is None
        final_disposition = (
            Disposition.NONE_SELECTED if retains_no_disposition else configured_disposition
        )
        if self.expectation.disposition is not final_disposition:
            raise ValueError("expected disposition must match configured final disposition")

        configured_review = self.human_review_request is not None
        if configured_review and not self.expectation.human_review:
            raise ValueError("configured human review must be expected")
        execution_review = self.expectation.failure_stage == "execution"
        if self.expectation.human_review and not (configured_review or execution_review):
            raise ValueError("human review expectation requires a supported review route")
        if self.expectation.execution_invoked:
            if configured_disposition not in EXECUTABLE_DISPOSITIONS:
                raise ValueError("execution cannot be expected for a non-executable disposition")
            configured_execution = {
                Disposition.APPROVE_REFUND: self.execution_results.refund,
                Disposition.APPROVE_REPLACEMENT: self.execution_results.replacement,
                Disposition.OPEN_CARRIER_INQUIRY: self.execution_results.carrier_inquiry,
            }[configured_disposition]
            if (
                self.expectation.execution_succeeded is not None
                and self.expectation.execution_succeeded is not configured_execution.succeeded
            ):
                raise ValueError("expected execution success must match configured result")


@dataclass(frozen=True, slots=True)
class ScenarioRunResult:
    scenario: SupportCaseScenario
    workflow_result: WorkflowResult


@dataclass(frozen=True, slots=True)
class ScenarioCheck:
    name: str
    passed: bool
    expected: object
    actual: object


@dataclass(frozen=True, slots=True)
class ScenarioEvaluation:
    scenario_id: str
    passed: bool
    checks: tuple[ScenarioCheck, ...]
    failure_messages: tuple[str, ...]


def _non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _utc(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must use UTC")


_NOW = datetime(2026, 8, 4, 12, tzinfo=UTC)


def _scenario(
    scenario_id: str,
    title: str,
    description: str,
    category: ScenarioCategory,
    *,
    disposition: Disposition = Disposition.DENY,
    customer_match: MatchStatus = MatchStatus.MATCHED,
    customer_retrieval: RetrievalStatus = RetrievalStatus.SUCCESS,
    order_match: MatchStatus = MatchStatus.MATCHED,
    order_retrieval: RetrievalStatus = RetrievalStatus.SUCCESS,
    evidence: str = "available",
    address: AddressMatchResult = AddressMatchResult.MATCH,
    unresolved: tuple[PolicyPlaceholder, ...] = (),
    review_disposition: Disposition | None = None,
    execution_success: bool = True,
    expectation: ScenarioExpectation,
    tags: tuple[str, ...],
    failure_category: str | None = None,
) -> SupportCaseScenario:
    customer_id = f"synthetic-customer-{scenario_id}"
    order_id = f"synthetic-order-{scenario_id}"
    shipment_id = f"synthetic-shipment-{scenario_id}"
    customer = CustomerReference(customer_id, customer_match, _NOW, customer_retrieval)
    order_facts = ("25.00 USD", "synthetic_item", "synthetic address")
    order = OrderReference(
        order_id,
        order_match,
        *(order_facts if order_retrieval is RetrievalStatus.SUCCESS else (None, None, None)),
        _NOW,
        order_retrieval,
    )
    shipment = ShipmentReference(
        shipment_id, "Synthetic Carrier", f"synthetic-tracking-{scenario_id}", _NOW, _NOW,
        RetrievalStatus.SUCCESS,
    )
    carrier_evidence = None
    if evidence == "available":
        carrier_evidence = CarrierEvidenceSnapshot(
            f"synthetic-evidence-{scenario_id}", shipment_id, "delivered", _NOW,
            ("synthetic delivered event",), True, _NOW, RetrievalStatus.SUCCESS,
        )
    elif evidence == "failed":
        carrier_evidence = CarrierEvidenceSnapshot(
            f"synthetic-evidence-{scenario_id}", shipment_id, None, None, (), None,
            _NOW, RetrievalStatus.FAILURE,
        )
    request = decision = None
    if review_disposition is not None:
        review_id = f"synthetic-review-{scenario_id}"
        evidence_ids = (
            (carrier_evidence.snapshot_id,)
            if carrier_evidence is not None and not unresolved
            else ()
        )
        request = HumanReviewRequest(
            review_id, _NOW, "synthetic review route", unresolved, evidence_ids
        )
        decision = HumanReviewDecision(
            review_id, _NOW, "synthetic-reviewer", review_disposition,
            "synthetic deterministic review decision",
        )
    success = ExecutionResult(execution_success, "synthetic execution result")
    execution = SyntheticExecutionAdapter(success, success, success)
    return SupportCaseScenario(
        scenario_id,
        title,
        description,
        category,
        SyntheticSupportCaseInput(
            f"synthetic-case-{scenario_id}",
            "Synthetic customer reports that a delivered package is not present.",
            customer_id,
            order_id,
            shipment_id,
            "synthetic-support-agent",
            _NOW,
        ),
        customer,
        order,
        shipment,
        carrier_evidence,
        address,
        unresolved,
        disposition,
        request,
        decision,
        execution,
        expectation,
        tags,
        RegressionMetadata(
            "synthetic", failure_category, _NOW,
            notes="Created for the initial deterministic scenario dataset.",
        ),
    )


def _expected(
    status: CaseStatus,
    disposition: Disposition,
    *,
    completed: bool = True,
    execution: ExecutionStatus = ExecutionStatus.NOT_APPLICABLE,
    follow_up: FollowUpStatus = FollowUpStatus.NOT_APPLICABLE,
    failure_stage: str | None = None,
    escalation: bool = False,
    human_review: bool = False,
    invoked: bool = False,
    succeeded: bool | None = None,
    events: tuple[str, ...],
) -> ScenarioExpectation:
    return ScenarioExpectation(
        completed, status, disposition, execution, follow_up, failure_stage,
        escalation, human_review, invoked, succeeded, events,
    )


_BASE_SUCCESS = (
    "workflow_started", "customer_report_recorded", "linkage_completed",
    "policy_route_recorded", "disposition_selected",
)
_EXEC_SUCCESS = _BASE_SUCCESS + (
    "execution_started", "execution_adapter_invoked", "execution_result_recorded",
    "workflow_completed",
)
_REVIEW = (
    "workflow_started", "linkage_completed", "policy_route_recorded",
    "human_review_opened", "human_review_decided",
)


_SCENARIOS = (
    _scenario(
        "refund-success",
        "Successful refund",
        "Complete evidence permits a successful refund.",
        ScenarioCategory.HAPPY_PATH,
        disposition=Disposition.APPROVE_REFUND,
        expectation=_expected(
            CaseStatus.CLOSED,
            Disposition.APPROVE_REFUND,
            execution=ExecutionStatus.SUCCEEDED,
            invoked=True,
            succeeded=True,
            events=_EXEC_SUCCESS,
        ),
        tags=("refund", "success"),
    ),
    _scenario(
        "replacement-success",
        "Successful replacement",
        "Complete evidence permits a successful replacement.",
        ScenarioCategory.HAPPY_PATH,
        disposition=Disposition.APPROVE_REPLACEMENT,
        expectation=_expected(
            CaseStatus.CLOSED,
            Disposition.APPROVE_REPLACEMENT,
            execution=ExecutionStatus.SUCCEEDED,
            invoked=True,
            succeeded=True,
            events=_EXEC_SUCCESS,
        ),
        tags=("replacement", "success"),
    ),
    _scenario(
        "carrier-inquiry-success",
        "Carrier inquiry awaiting follow-up",
        "A successful carrier inquiry waits for an external result.",
        ScenarioCategory.EXTERNAL_FOLLOW_UP,
        disposition=Disposition.OPEN_CARRIER_INQUIRY,
        expectation=_expected(
            CaseStatus.AWAITING_EXTERNAL_FOLLOW_UP,
            Disposition.OPEN_CARRIER_INQUIRY,
            execution=ExecutionStatus.SUCCEEDED,
            follow_up=FollowUpStatus.PENDING,
            invoked=True,
            succeeded=True,
            events=_EXEC_SUCCESS,
        ),
        tags=("carrier_inquiry", "external_follow_up"),
    ),
    _scenario(
        "denial",
        "Denial without execution",
        "Complete evidence results in a deterministic denial.",
        ScenarioCategory.HAPPY_PATH,
        disposition=Disposition.DENY,
        expectation=_expected(
            CaseStatus.CLOSED,
            Disposition.DENY,
            events=_BASE_SUCCESS + ("workflow_completed",),
        ),
        tags=("denial", "no_execution"),
    ),
    _scenario(
        "request-more-info",
        "Request more information",
        "The configured customer action asks for more information.",
        ScenarioCategory.CUSTOMER_ACTION,
        disposition=Disposition.REQUEST_MORE_INFO,
        expectation=_expected(
            CaseStatus.AWAITING_CUSTOMER_ACTION,
            Disposition.REQUEST_MORE_INFO,
            events=_BASE_SUCCESS + ("workflow_completed",),
        ),
        tags=("customer_action", "more_information"),
    ),
    _scenario(
        "self-check-wait",
        "Self-check or wait guidance",
        "The configured customer action advises self-checks or waiting.",
        ScenarioCategory.CUSTOMER_ACTION,
        disposition=Disposition.ADVISE_SELF_CHECK_OR_WAIT,
        expectation=_expected(
            CaseStatus.AWAITING_CUSTOMER_ACTION,
            Disposition.ADVISE_SELF_CHECK_OR_WAIT,
            events=_BASE_SUCCESS + ("workflow_completed",),
        ),
        tags=("customer_action", "self_check"),
    ),
    _scenario(
        "customer-lookup-failure",
        "Customer lookup failure",
        "The customer system fails before linkage.",
        ScenarioCategory.INTAKE_FAILURE,
        customer_match=MatchStatus.NOT_FOUND,
        customer_retrieval=RetrievalStatus.FAILURE,
        expectation=_expected(
            CaseStatus.INTAKE_FAILED,
            Disposition.NONE_SELECTED,
            completed=False,
            failure_stage="customer_lookup",
            events=("workflow_started", "customer_report_recorded", "intake_failed", "workflow_stopped"),
        ),
        tags=("intake", "customer_lookup"),
        failure_category="retrieval_failure",
    ),
    _scenario(
        "customer-not-found",
        "Customer not found",
        "The customer lookup succeeds but finds no unambiguous match.",
        ScenarioCategory.INTAKE_FAILURE,
        customer_match=MatchStatus.NOT_FOUND,
        expectation=_expected(
            CaseStatus.INTAKE_FAILED,
            Disposition.NONE_SELECTED,
            completed=False,
            failure_stage="customer_lookup",
            events=("workflow_started", "customer_report_recorded", "intake_failed", "workflow_stopped"),
        ),
        tags=("intake", "customer_match"),
        failure_category="not_found",
    ),
    _scenario(
        "order-lookup-failure",
        "Order lookup failure",
        "The order system fails after customer lookup.",
        ScenarioCategory.INTAKE_FAILURE,
        order_match=MatchStatus.NOT_FOUND,
        order_retrieval=RetrievalStatus.FAILURE,
        expectation=_expected(
            CaseStatus.INTAKE_FAILED,
            Disposition.NONE_SELECTED,
            completed=False,
            failure_stage="order_lookup",
            events=("workflow_started", "customer_report_recorded", "intake_failed", "workflow_stopped"),
        ),
        tags=("intake", "order_lookup"),
        failure_category="retrieval_failure",
    ),
    _scenario(
        "carrier-evidence-missing",
        "Missing carrier evidence",
        "No carrier snapshot is available, so the case awaits customer action.",
        ScenarioCategory.EVIDENCE_FAILURE,
        evidence="missing",
        expectation=_expected(
            CaseStatus.AWAITING_CUSTOMER_ACTION,
            Disposition.NONE_SELECTED,
            events=("workflow_started", "linkage_completed", "carrier_evidence_missing", "policy_route_recorded", "workflow_completed"),
        ),
        tags=("evidence", "missing"),
        failure_category="missing_evidence",
    ),
    _scenario(
        "carrier-evidence-failed",
        "Carrier evidence retrieval failed",
        "Failed carrier retrieval is reviewed and denied.",
        ScenarioCategory.EVIDENCE_FAILURE,
        evidence="failed",
        review_disposition=Disposition.DENY,
        expectation=_expected(
            CaseStatus.CLOSED,
            Disposition.DENY,
            escalation=True,
            human_review=True,
            events=_REVIEW + ("workflow_completed",),
        ),
        tags=("evidence", "human_review"),
        failure_category="retrieval_failure",
    ),
    _scenario(
        "address-mismatch",
        "Address mismatch review",
        "An address mismatch is reviewed and denied.",
        ScenarioCategory.HUMAN_REVIEW,
        address=AddressMatchResult.MISMATCH,
        review_disposition=Disposition.DENY,
        expectation=_expected(
            CaseStatus.CLOSED,
            Disposition.DENY,
            escalation=True,
            human_review=True,
            events=_REVIEW + ("workflow_completed",),
        ),
        tags=("address", "human_review"),
    ),
    _scenario(
        "refund-authority-review",
        "Unresolved refund authority",
        "Frontline refund authority is unresolved and a reviewer denies.",
        ScenarioCategory.HUMAN_REVIEW,
        unresolved=(PolicyPlaceholder.FRONTLINE_REFUND_AUTHORITY,),
        review_disposition=Disposition.DENY,
        expectation=_expected(
            CaseStatus.CLOSED,
            Disposition.DENY,
            escalation=True,
            human_review=True,
            events=_REVIEW + ("workflow_completed",),
        ),
        tags=("policy", "refund_authority"),
    ),
    _scenario(
        "reviewer-approves-refund",
        "Reviewer approves refund",
        "A reviewer resolves refund authority and approves execution.",
        ScenarioCategory.HUMAN_REVIEW,
        unresolved=(PolicyPlaceholder.FRONTLINE_REFUND_AUTHORITY,),
        review_disposition=Disposition.APPROVE_REFUND,
        expectation=_expected(
            CaseStatus.CLOSED,
            Disposition.APPROVE_REFUND,
            execution=ExecutionStatus.SUCCEEDED,
            escalation=True,
            human_review=True,
            invoked=True,
            succeeded=True,
            events=_REVIEW + ("execution_started", "execution_adapter_invoked", "workflow_completed"),
        ),
        tags=("human_review", "refund", "approval"),
    ),
    _scenario(
        "reviewer-denies",
        "Reviewer denies",
        "A reviewer resolves a risk-policy question by denying the case.",
        ScenarioCategory.HUMAN_REVIEW,
        unresolved=(PolicyPlaceholder.RISK_REVIEW_TRIGGER_POLICY,),
        review_disposition=Disposition.DENY,
        expectation=_expected(
            CaseStatus.CLOSED,
            Disposition.DENY,
            escalation=True,
            human_review=True,
            events=_REVIEW + ("workflow_completed",),
        ),
        tags=("human_review", "denial"),
    ),
    _scenario(
        "refund-execution-failure",
        "Refund execution failure",
        "A failed refund operation is safely routed to human review.",
        ScenarioCategory.EXECUTION_FAILURE,
        disposition=Disposition.APPROVE_REFUND,
        execution_success=False,
        expectation=_expected(
            CaseStatus.HUMAN_REVIEW,
            Disposition.APPROVE_REFUND,
            completed=False,
            execution=ExecutionStatus.FAILED,
            failure_stage="execution",
            escalation=True,
            human_review=True,
            invoked=True,
            succeeded=False,
            events=_BASE_SUCCESS + ("execution_started", "execution_adapter_invoked", "execution_failure_routed", "workflow_stopped"),
        ),
        tags=("execution", "refund", "human_review"),
        failure_category="execution_failure",
    ),
)


def _validate_dataset(scenarios: tuple[SupportCaseScenario, ...]) -> None:
    ids = [scenario.scenario_id for scenario in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("support-case scenario IDs must be unique")


_validate_dataset(_SCENARIOS)


def get_support_case_scenarios() -> tuple[SupportCaseScenario, ...]:
    """Return the immutable, curated scenario dataset."""
    return _SCENARIOS


def get_support_case_scenario(scenario_id: str) -> SupportCaseScenario:
    _non_empty(scenario_id, "scenario_id")
    for scenario in _SCENARIOS:
        if scenario.scenario_id == scenario_id:
            return scenario
    raise KeyError(f"unknown support-case scenario: {scenario_id}")


def run_support_case_scenario(
    scenario: SupportCaseScenario,
    *,
    registry: ExecutionRegistry | None = None,
) -> ScenarioRunResult:
    """Configure and run one scenario through the existing workflow."""
    if not isinstance(scenario, SupportCaseScenario):
        raise ValueError("scenario must be a SupportCaseScenario")
    reviewer = None
    if scenario.human_review_request is not None:
        reviewer = SyntheticHumanReviewer(
            scenario.human_review_request, scenario.human_review_decision  # type: ignore[arg-type]
        )
    configuration = WorkflowConfiguration(
        SyntheticCustomerLookup(scenario.customer_reference),
        SyntheticOrderLookup(scenario.order_reference),
        SyntheticShipmentLookup(scenario.shipment_reference),
        SyntheticCarrierEvidenceLookup(scenario.carrier_evidence),
        SyntheticAddressComparison(scenario.address_match_result),
        scenario.execution_results,
        scenario.selected_disposition,
        _NOW,
        scenario.unresolved_policies,
        reviewer,
        registry if registry is not None else ExecutionRegistry(),
    )
    return ScenarioRunResult(
        scenario,
        run_synthetic_support_case(
            scenario.case_input,
            configuration,
            trace_id=f"scenario-trace-{scenario.scenario_id}",
            clock=lambda: _NOW,
        ),
    )


def evaluate_support_case_scenario(run: ScenarioRunResult) -> ScenarioEvaluation:
    """Compare one deterministic workflow result with its stored expectations."""
    if not isinstance(run, ScenarioRunResult):
        raise ValueError("run must be a ScenarioRunResult")
    expected = run.scenario.expectation
    result = run.workflow_result
    event_names = tuple(event.event_type for event in result.trace_events)
    positions: list[int] = []
    cursor = 0
    trace_ordered = True
    for required in expected.trace_events:
        try:
            position = event_names.index(required, cursor)
        except ValueError:
            trace_ordered = False
            break
        positions.append(position)
        cursor = position + 1
    escalation = any(event.escalation for event in result.trace_events)
    human_review = (
        result.final_case_status is CaseStatus.HUMAN_REVIEW
        or "human_review_opened" in event_names
    )
    invoked = "execution_adapter_invoked" in event_names
    operation_success = (
        result.execution_operation.status is OperationStatus.SUCCEEDED
        if result.execution_operation is not None
        else None
    )
    values = (
        ("completed", expected.completed, result.completed),
        ("case_status", expected.case_status, result.final_case_status),
        ("disposition", expected.disposition, result.final_disposition),
        ("execution_status", expected.execution_status, result.case.execution_status),
        ("follow_up_status", expected.follow_up_status, result.case.follow_up_status),
        ("failure_stage", expected.failure_stage, result.failure_stage),
        ("escalation", expected.escalation, escalation),
        ("human_review", expected.human_review, human_review),
        ("execution_invoked", expected.execution_invoked, invoked),
        ("execution_succeeded", expected.execution_succeeded, operation_success),
        ("trace_events_in_order", True, trace_ordered),
    )
    checks = tuple(
        ScenarioCheck(name, expected_value == actual, expected_value, actual)
        for name, expected_value, actual in values
    )
    failures = tuple(
        f"{check.name}: expected {check.expected!r}, got {check.actual!r}"
        for check in checks
        if not check.passed
    )
    return ScenarioEvaluation(run.scenario.scenario_id, not failures, checks, failures)
