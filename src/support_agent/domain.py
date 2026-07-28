"""Executable state model accepted in ``docs/03-system-boundaries.md``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


class CaseStatus(StrEnum):
    INTAKE = "intake"
    INTAKE_FAILED = "intake_failed"
    LINKED = "linked"
    EVIDENCE_GATHERING = "evidence_gathering"
    AWAITING_CUSTOMER_ACTION = "awaiting_customer_action"
    POLICY_REVIEW = "policy_review"
    HUMAN_REVIEW = "human_review"
    DISPOSITION_SELECTION = "disposition_selection"
    EXECUTING = "executing"
    AWAITING_EXTERNAL_FOLLOW_UP = "awaiting_external_follow_up"
    CLOSED = "closed"


class Disposition(StrEnum):
    NONE_SELECTED = "none_selected"
    REQUEST_MORE_INFO = "request_more_info"
    ADVISE_SELF_CHECK_OR_WAIT = "advise_self_check_or_wait"
    OPEN_CARRIER_INQUIRY = "open_carrier_inquiry"
    APPROVE_REPLACEMENT = "approve_replacement"
    APPROVE_REFUND = "approve_refund"
    DENY = "deny"


class ExecutionStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class FollowUpStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    RESOLVED_FAVORABLE = "resolved_favorable"
    RESOLVED_UNFAVORABLE = "resolved_unfavorable"
    EXPIRED = "expired"
    REJECTED = "rejected"


class RetrievalStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class MatchStatus(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


class AddressMatchResult(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


class TransitionRejected(Exception):
    """Raised after an invalid domain mutation has been recorded and rejected."""


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    case_status: CaseStatus
    disposition: Disposition
    execution_status: ExecutionStatus
    follow_up_status: FollowUpStatus
    closed_at: datetime | None


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    occurred_at: datetime
    event_type: str
    actor: str
    before_state: StateSnapshot
    after_state: StateSnapshot
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class OperationalIntegrityAlert:
    alert_id: str
    occurred_at: datetime
    case_id: str
    actor: str
    detail: str


def _require_utc_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must use UTC")


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class CustomerReport:
    order_or_tracking_identifier_provided: str
    delivery_address_as_stated: str
    when_and_how_checked: str
    other_possible_recipients_noted: str
    reported_at: datetime

    def __post_init__(self) -> None:
        _require_utc_aware(self.reported_at, "reported_at")


@dataclass(frozen=True, slots=True)
class CustomerReference:
    ref_id: str
    match_status: MatchStatus
    retrieved_at: datetime
    retrieval_status: RetrievalStatus

    def __post_init__(self) -> None:
        _require_non_empty(self.ref_id, "ref_id")
        if not isinstance(self.match_status, MatchStatus):
            raise ValueError("match_status must be a MatchStatus")
        if not isinstance(self.retrieval_status, RetrievalStatus):
            raise ValueError("retrieval_status must be a RetrievalStatus")
        if (
            self.retrieval_status is RetrievalStatus.FAILURE
            and self.match_status is MatchStatus.MATCHED
        ):
            raise ValueError("failed customer retrieval must not be matched")
        _require_utc_aware(self.retrieved_at, "retrieved_at")


@dataclass(frozen=True, slots=True)
class OrderReference:
    ref_id: str
    match_status: MatchStatus
    order_value: str | None
    item_category: str | None
    ship_to_address_on_file: str | None
    retrieved_at: datetime
    retrieval_status: RetrievalStatus

    def __post_init__(self) -> None:
        _require_non_empty(self.ref_id, "ref_id")
        if not isinstance(self.match_status, MatchStatus):
            raise ValueError("match_status must be a MatchStatus")
        if not isinstance(self.retrieval_status, RetrievalStatus):
            raise ValueError("retrieval_status must be a RetrievalStatus")
        matched_order_facts = (
            self.order_value,
            self.item_category,
            self.ship_to_address_on_file,
        )
        if self.retrieval_status is RetrievalStatus.FAILURE:
            if self.match_status is MatchStatus.MATCHED:
                raise ValueError("failed order retrieval must not be matched")
            if any(fact is not None for fact in matched_order_facts):
                raise ValueError("failed order retrieval must not contain order facts")
        elif self.match_status is MatchStatus.MATCHED and any(
            not fact for fact in matched_order_facts
        ):
            raise ValueError("matched order retrieval requires all order facts")
        _require_utc_aware(self.retrieved_at, "retrieved_at")


@dataclass(frozen=True, slots=True)
class ShipmentReference:
    ref_id: str
    carrier: str | None
    tracking_id: str | None
    fulfillment_timestamp: datetime | None
    retrieved_at: datetime
    retrieval_status: RetrievalStatus

    def __post_init__(self) -> None:
        _require_non_empty(self.ref_id, "ref_id")
        if not isinstance(self.retrieval_status, RetrievalStatus):
            raise ValueError("retrieval_status must be a RetrievalStatus")
        shipment_facts = (
            self.carrier,
            self.tracking_id,
            self.fulfillment_timestamp,
        )
        if self.retrieval_status is RetrievalStatus.FAILURE:
            if any(fact is not None for fact in shipment_facts):
                raise ValueError(
                    "failed shipment retrieval must not contain shipment facts"
                )
        elif not self.carrier or not self.tracking_id:
            raise ValueError(
                "successful shipment retrieval requires carrier and tracking_id"
            )
        if self.fulfillment_timestamp is not None:
            _require_utc_aware(
                self.fulfillment_timestamp, "fulfillment_timestamp"
            )
        _require_utc_aware(self.retrieved_at, "retrieved_at")


@dataclass(frozen=True, slots=True)
class CarrierEvidenceSnapshot:
    snapshot_id: str
    shipment_ref: str
    delivery_status: str | None
    delivery_timestamp: datetime | None
    tracking_event_history: tuple[str, ...]
    picture_proof_available: bool | None
    retrieved_at: datetime
    retrieval_status: RetrievalStatus

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "tracking_event_history", tuple(self.tracking_event_history)
        )
        _require_non_empty(self.snapshot_id, "snapshot_id")
        _require_non_empty(self.shipment_ref, "shipment_ref")
        if not isinstance(self.retrieval_status, RetrievalStatus):
            raise ValueError("retrieval_status must be a RetrievalStatus")
        if self.retrieval_status is RetrievalStatus.FAILURE:
            if (
                self.delivery_status is not None
                or self.delivery_timestamp is not None
                or self.tracking_event_history
                or self.picture_proof_available is not None
            ):
                raise ValueError(
                    "failed carrier retrieval must not contain delivery facts"
                )
        else:
            if not self.delivery_status:
                raise ValueError(
                    "successful carrier retrieval requires delivery_status"
                )
            if type(self.picture_proof_available) is not bool:
                raise ValueError(
                    "successful carrier retrieval requires boolean "
                    "picture_proof_available"
                )
        if self.delivery_timestamp is not None:
            _require_utc_aware(self.delivery_timestamp, "delivery_timestamp")
        _require_utc_aware(self.retrieved_at, "retrieved_at")


_CUSTOMER_ACTION_DISPOSITIONS = {
    Disposition.REQUEST_MORE_INFO,
    Disposition.ADVISE_SELF_CHECK_OR_WAIT,
}
_EXECUTABLE_DISPOSITIONS = {
    Disposition.APPROVE_REFUND,
    Disposition.APPROVE_REPLACEMENT,
    Disposition.OPEN_CARRIER_INQUIRY,
}
_REFUND_OR_REPLACEMENT = {
    Disposition.APPROVE_REFUND,
    Disposition.APPROVE_REPLACEMENT,
}
_EXECUTION_PROGRESSIONS = {
    ExecutionStatus.NOT_STARTED: {
        ExecutionStatus.IN_PROGRESS,
        ExecutionStatus.SUCCEEDED,
        ExecutionStatus.FAILED,
    },
    ExecutionStatus.IN_PROGRESS: {
        ExecutionStatus.SUCCEEDED,
        ExecutionStatus.FAILED,
    },
}
_FOLLOW_UP_RESULTS = {
    FollowUpStatus.RESOLVED_FAVORABLE,
    FollowUpStatus.RESOLVED_UNFAVORABLE,
    FollowUpStatus.EXPIRED,
    FollowUpStatus.REJECTED,
}
_SIMPLE_TRANSITIONS = {
    CaseStatus.INTAKE_FAILED: {CaseStatus.HUMAN_REVIEW},
    CaseStatus.LINKED: {CaseStatus.EVIDENCE_GATHERING},
    CaseStatus.EVIDENCE_GATHERING: {
        CaseStatus.AWAITING_CUSTOMER_ACTION,
        CaseStatus.POLICY_REVIEW,
    },
    CaseStatus.AWAITING_CUSTOMER_ACTION: {
        CaseStatus.EVIDENCE_GATHERING,
        CaseStatus.POLICY_REVIEW,
        CaseStatus.CLOSED,
    },
    CaseStatus.POLICY_REVIEW: {
        CaseStatus.HUMAN_REVIEW,
        CaseStatus.DISPOSITION_SELECTION,
    },
    CaseStatus.HUMAN_REVIEW: {
        CaseStatus.LINKED,
        CaseStatus.AWAITING_CUSTOMER_ACTION,
        CaseStatus.EVIDENCE_GATHERING,
        CaseStatus.DISPOSITION_SELECTION,
        CaseStatus.AWAITING_EXTERNAL_FOLLOW_UP,
        CaseStatus.CLOSED,
    },
}


class SupportCase:
    """Small aggregate that owns all workflow-state mutation."""

    def __init__(self, case_id: str, *, actor: str = "system") -> None:
        if not case_id:
            raise ValueError("case_id must not be empty")
        self._case_id = case_id
        self._case_status = CaseStatus.INTAKE
        self._disposition = Disposition.NONE_SELECTED
        self._execution_status = ExecutionStatus.NOT_APPLICABLE
        self._follow_up_status = FollowUpStatus.NOT_APPLICABLE
        self._opened_at = datetime.now(UTC)
        self._closed_at: datetime | None = None
        self._customer_report: CustomerReport | None = None
        self._customer_ref: CustomerReference | None = None
        self._order_ref: OrderReference | None = None
        self._shipment_refs: list[ShipmentReference] = []
        self._carrier_evidence_snapshots: list[CarrierEvidenceSnapshot] = []
        self._address_match_result = AddressMatchResult.UNKNOWN
        self._address_match_recorded = False
        self._audit_events: list[AuditEvent] = []
        self._integrity_alerts: list[OperationalIntegrityAlert] = []
        state = self.snapshot()
        self._append_event("case_created", actor, state, state)

    @property
    def case_id(self) -> str:
        return self._case_id

    @property
    def case_status(self) -> CaseStatus:
        return self._case_status

    @property
    def disposition(self) -> Disposition:
        return self._disposition

    @property
    def execution_status(self) -> ExecutionStatus:
        return self._execution_status

    @property
    def follow_up_status(self) -> FollowUpStatus:
        return self._follow_up_status

    @property
    def opened_at(self) -> datetime:
        return self._opened_at

    @property
    def closed_at(self) -> datetime | None:
        return self._closed_at

    @property
    def customer_report(self) -> CustomerReport | None:
        return self._customer_report

    @property
    def customer_ref(self) -> CustomerReference | None:
        return self._customer_ref

    @property
    def order_ref(self) -> OrderReference | None:
        return self._order_ref

    @property
    def shipment_refs(self) -> tuple[ShipmentReference, ...]:
        return tuple(self._shipment_refs)

    @property
    def carrier_evidence_snapshots(self) -> tuple[CarrierEvidenceSnapshot, ...]:
        return tuple(self._carrier_evidence_snapshots)

    @property
    def address_match_result(self) -> AddressMatchResult:
        return self._address_match_result

    @property
    def audit_events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._audit_events)

    @property
    def integrity_alerts(self) -> tuple[OperationalIntegrityAlert, ...]:
        return tuple(self._integrity_alerts)

    def snapshot(self) -> StateSnapshot:
        return StateSnapshot(
            self._case_status,
            self._disposition,
            self._execution_status,
            self._follow_up_status,
            self._closed_at,
        )

    def record_customer_report(
        self, report: CustomerReport, *, actor: str
    ) -> None:
        before = self.snapshot()
        if self._customer_report is not None:
            self._reject("customer report is already recorded", actor, before)
        self._customer_report = report
        self._append_event("customer_report_recorded", actor, before, self.snapshot())

    def link(
        self,
        customer_ref: CustomerReference,
        order_ref: OrderReference,
        *,
        actor: str,
    ) -> None:
        """Store successful structured references and complete intake."""
        before = self.snapshot()
        if self._case_status is not CaseStatus.INTAKE:
            self._reject("linkage is only allowed from intake", actor, before)
        if (
            customer_ref.retrieval_status is not RetrievalStatus.SUCCESS
            or customer_ref.match_status is not MatchStatus.MATCHED
        ):
            self._reject(
                "customer reference must be successfully retrieved and matched",
                actor,
                before,
            )
        if (
            order_ref.retrieval_status is not RetrievalStatus.SUCCESS
            or order_ref.match_status is not MatchStatus.MATCHED
        ):
            self._reject(
                "order reference must be successfully retrieved and matched",
                actor,
                before,
            )
        self._customer_ref = customer_ref
        self._order_ref = order_ref
        self._case_status = CaseStatus.LINKED
        self._append_event("state_transition", actor, before, self.snapshot())

    def attach_shipment(
        self, shipment_ref: ShipmentReference, *, actor: str
    ) -> None:
        before = self.snapshot()
        if any(
            existing.ref_id == shipment_ref.ref_id
            for existing in self._shipment_refs
        ):
            self._reject(
                f"shipment {shipment_ref.ref_id!r} is already attached", actor, before
            )
        self._shipment_refs.append(shipment_ref)
        self._append_event("shipment_attached", actor, before, self.snapshot())

    def attach_carrier_evidence(
        self, evidence: CarrierEvidenceSnapshot, *, actor: str
    ) -> None:
        before = self.snapshot()
        if not any(
            shipment.ref_id == evidence.shipment_ref
            for shipment in self._shipment_refs
        ):
            self._reject(
                f"carrier evidence references unknown shipment "
                f"{evidence.shipment_ref!r}",
                actor,
                before,
            )
        if any(
            existing.snapshot_id == evidence.snapshot_id
            for existing in self._carrier_evidence_snapshots
        ):
            self._reject(
                f"carrier evidence {evidence.snapshot_id!r} is already attached",
                actor,
                before,
            )
        self._carrier_evidence_snapshots.append(evidence)
        self._append_event("carrier_evidence_attached", actor, before, self.snapshot())

    def record_address_match_result(
        self, result: AddressMatchResult, *, actor: str
    ) -> None:
        before = self.snapshot()
        if not isinstance(result, AddressMatchResult):
            self._reject(f"{result!r} is not a valid address match result", actor, before)
        if self._address_match_recorded:
            self._reject("address match result is already recorded", actor, before)
        self._address_match_result = result
        self._address_match_recorded = True
        self._append_event("address_match_recorded", actor, before, self.snapshot())

    def fail_intake(self, *, actor: str, detail: str | None = None) -> None:
        before = self.snapshot()
        if self._case_status is not CaseStatus.INTAKE:
            self._reject("intake can only fail from intake", actor, before)
        self._case_status = CaseStatus.INTAKE_FAILED
        self._append_event("state_transition", actor, before, self.snapshot(), detail)

    def transition_to(
        self, target: CaseStatus, *, actor: str, detail: str | None = None
    ) -> None:
        """Perform a lifecycle transition that has no coupled status mutation."""
        before = self.snapshot()
        if target not in _SIMPLE_TRANSITIONS.get(self._case_status, set()):
            self._reject(
                f"transition from {self._case_status} to {target} is not allowed",
                actor,
                before,
            )
        self._case_status = target
        if target is CaseStatus.CLOSED:
            self._closed_at = datetime.now(UTC)
        self._append_event("state_transition", actor, before, self.snapshot(), detail)

    def select_disposition(
        self,
        disposition: Disposition,
        *,
        actor: str,
        execution_data_present: bool = True,
        detail: str | None = None,
    ) -> None:
        """Select a disposition and atomically enter its required next phase."""
        before = self.snapshot()
        if self._case_status is not CaseStatus.DISPOSITION_SELECTION:
            self._reject(
                "a disposition can only be selected during disposition_selection",
                actor,
                before,
            )
        if disposition is Disposition.NONE_SELECTED:
            self._reject("none_selected is not a selectable outcome", actor, before)
        if not isinstance(disposition, Disposition):
            self._reject(f"{disposition!r} is not a valid disposition", actor, before)
        if disposition in _EXECUTABLE_DISPOSITIONS and not execution_data_present:
            self._reject(
                f"execution data is required for {disposition}", actor, before
            )

        if disposition in _CUSTOMER_ACTION_DISPOSITIONS:
            next_case_status = CaseStatus.AWAITING_CUSTOMER_ACTION
            next_execution_status = ExecutionStatus.NOT_APPLICABLE
            next_closed_at = None
        elif disposition in _EXECUTABLE_DISPOSITIONS:
            next_case_status = CaseStatus.EXECUTING
            next_execution_status = ExecutionStatus.NOT_STARTED
            next_closed_at = None
        elif disposition is Disposition.DENY:
            next_case_status = CaseStatus.CLOSED
            next_execution_status = ExecutionStatus.NOT_APPLICABLE
            next_closed_at = datetime.now(UTC)
        else:  # Kept defensive if the enum grows without a corresponding lifecycle rule.
            self._reject(f"{disposition} has no disposition path", actor, before)

        self._disposition = disposition
        self._case_status = next_case_status
        self._execution_status = next_execution_status
        self._closed_at = next_closed_at
        self._append_event("disposition_selected", actor, before, self.snapshot(), detail)

    def record_execution_status(
        self, status: ExecutionStatus, *, actor: str, detail: str | None = None
    ) -> None:
        before = self.snapshot()
        allowed = _EXECUTION_PROGRESSIONS.get(self._execution_status, set())
        if self._case_status is not CaseStatus.EXECUTING or status not in allowed:
            self._reject(
                f"execution status cannot change from {self._execution_status} "
                f"to {status} while case is {self._case_status}",
                actor,
                before,
            )
        self._execution_status = status
        self._append_event("execution_status_changed", actor, before, self.snapshot(), detail)

    def complete_execution(self, *, actor: str, detail: str | None = None) -> None:
        """Leave executing after a successful external operation."""
        before = self.snapshot()
        if (
            self._case_status is not CaseStatus.EXECUTING
            or self._execution_status is not ExecutionStatus.SUCCEEDED
        ):
            self._reject(
                "successful execution is required before completing execution",
                actor,
                before,
            )
        if self._disposition in _REFUND_OR_REPLACEMENT:
            self._case_status = CaseStatus.CLOSED
            self._closed_at = datetime.now(UTC)
        elif self._disposition is Disposition.OPEN_CARRIER_INQUIRY:
            self._case_status = CaseStatus.AWAITING_EXTERNAL_FOLLOW_UP
            self._follow_up_status = FollowUpStatus.PENDING
        else:
            self._reject(
                f"{self._disposition} has no executable completion path", actor, before
            )
        self._append_event("state_transition", actor, before, self.snapshot(), detail)

    def route_execution_failure_to_review(
        self, *, actor: str, detail: str | None = None
    ) -> None:
        before = self.snapshot()
        if (
            self._case_status is not CaseStatus.EXECUTING
            or self._execution_status is not ExecutionStatus.FAILED
        ):
            self._reject(
                "failed execution is required before routing to human review",
                actor,
                before,
            )
        self._case_status = CaseStatus.HUMAN_REVIEW
        self._append_event("state_transition", actor, before, self.snapshot(), detail)

    def record_follow_up_result(
        self, result: FollowUpStatus, *, actor: str, detail: str | None = None
    ) -> None:
        """Record an external result and conservatively route it to human review."""
        before = self.snapshot()
        if (
            self._case_status is not CaseStatus.AWAITING_EXTERNAL_FOLLOW_UP
            or self._follow_up_status is not FollowUpStatus.PENDING
            or result not in _FOLLOW_UP_RESULTS
        ):
            self._reject(
                f"{result} is not a valid pending follow-up result", actor, before
            )
        self._follow_up_status = result
        self._case_status = CaseStatus.HUMAN_REVIEW
        self._append_event("follow_up_status_changed", actor, before, self.snapshot(), detail)

    def _reject(
        self, detail: str, actor: str, before: StateSnapshot
    ) -> None:
        now = datetime.now(UTC)
        after = self.snapshot()
        self._audit_events.append(
            AuditEvent(
                f"event-{uuid4()}",
                now,
                "transition_rejected",
                actor,
                before,
                after,
                detail,
            )
        )
        self._integrity_alerts.append(
            OperationalIntegrityAlert(
                f"alert-{uuid4()}", now, self._case_id, actor, detail
            )
        )
        raise TransitionRejected(detail)

    def _append_event(
        self,
        event_type: str,
        actor: str,
        before: StateSnapshot,
        after: StateSnapshot,
        detail: str | None = None,
    ) -> None:
        self._audit_events.append(
            AuditEvent(
                f"event-{uuid4()}",
                datetime.now(UTC),
                event_type,
                actor,
                before,
                after,
                detail,
            )
        )
