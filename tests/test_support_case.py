from dataclasses import FrozenInstanceError
from datetime import UTC
import unittest

from support_agent import (
    CaseStatus,
    Disposition,
    ExecutionStatus,
    FollowUpStatus,
    SupportCase,
    TransitionRejected,
)


class SupportCaseTest(unittest.TestCase):
    def case_at_disposition_selection(self) -> SupportCase:
        case = SupportCase("case-001")
        case.link("customer-001", "order-001", actor="agent")
        case.transition_to(CaseStatus.EVIDENCE_GATHERING, actor="agent")
        case.transition_to(CaseStatus.POLICY_REVIEW, actor="agent")
        case.transition_to(CaseStatus.DISPOSITION_SELECTION, actor="policy")
        return case

    def test_new_case_defaults_and_creation_event(self) -> None:
        case = SupportCase("case-001")

        self.assertEqual(case.case_status, CaseStatus.INTAKE)
        self.assertEqual(case.disposition, Disposition.NONE_SELECTED)
        self.assertEqual(case.execution_status, ExecutionStatus.NOT_APPLICABLE)
        self.assertEqual(case.follow_up_status, FollowUpStatus.NOT_APPLICABLE)
        self.assertEqual(case.audit_events[0].event_type, "case_created")
        self.assertIs(case.audit_events[0].before_state, case.audit_events[0].after_state)
        self.assertIs(case.opened_at.tzinfo, UTC)

    def test_valid_refund_path_requires_successful_issuance(self) -> None:
        case = self.case_at_disposition_selection()
        case.select_disposition(Disposition.APPROVE_REFUND, actor="reviewer")

        self.assertEqual(case.case_status, CaseStatus.EXECUTING)
        self.assertEqual(case.execution_status, ExecutionStatus.NOT_STARTED)
        self.assertIsNone(case.closed_at)

        case.record_execution_status(ExecutionStatus.SUCCEEDED, actor="refund-system")
        case.complete_execution(actor="refund-system")

        self.assertEqual(case.case_status, CaseStatus.CLOSED)
        self.assertEqual(case.disposition, Disposition.APPROVE_REFUND)
        self.assertEqual(case.execution_status, ExecutionStatus.SUCCEEDED)
        self.assertIsNotNone(case.closed_at)
        self.assertIs(case.closed_at.tzinfo, UTC)

    def test_refund_cannot_close_before_execution_succeeds(self) -> None:
        for status in (ExecutionStatus.NOT_STARTED, ExecutionStatus.IN_PROGRESS):
            with self.subTest(status=status):
                case = self.case_at_disposition_selection()
                case.select_disposition(Disposition.APPROVE_REFUND, actor="reviewer")
                if status is ExecutionStatus.IN_PROGRESS:
                    case.record_execution_status(status, actor="refund-system")
                before = case.snapshot()
                event_count = len(case.audit_events)

                with self.assertRaises(TransitionRejected):
                    case.complete_execution(actor="refund-system")

                self.assertEqual(case.snapshot(), before)
                self.assertEqual(case.case_status, CaseStatus.EXECUTING)
                self.assertEqual(len(case.audit_events), event_count + 1)
                self.assertEqual(case.audit_events[-1].event_type, "transition_rejected")
                self.assertEqual(len(case.integrity_alerts), 1)

    def test_customer_action_dispositions_do_not_require_execution(self) -> None:
        for disposition in (
            Disposition.REQUEST_MORE_INFO,
            Disposition.ADVISE_SELF_CHECK_OR_WAIT,
        ):
            with self.subTest(disposition=disposition):
                case = self.case_at_disposition_selection()
                case.select_disposition(disposition, actor="agent")

                self.assertEqual(
                    case.case_status, CaseStatus.AWAITING_CUSTOMER_ACTION
                )
                self.assertEqual(case.disposition, disposition)
                self.assertEqual(
                    case.execution_status, ExecutionStatus.NOT_APPLICABLE
                )

    def test_executable_disposition_without_execution_data_preserves_state(self) -> None:
        case = self.case_at_disposition_selection()
        before = case.snapshot()
        event_count = len(case.audit_events)
        alert_count = len(case.integrity_alerts)

        with self.assertRaises(TransitionRejected):
            case.select_disposition(
                Disposition.APPROVE_REFUND,
                actor="reviewer",
                execution_data_present=False,
            )

        self.assertEqual(case.snapshot(), before)
        self.assertEqual(case.case_status, CaseStatus.DISPOSITION_SELECTION)
        self.assertEqual(case.disposition, Disposition.NONE_SELECTED)
        self.assertEqual(case.execution_status, ExecutionStatus.NOT_APPLICABLE)
        self.assertEqual(case.follow_up_status, FollowUpStatus.NOT_APPLICABLE)
        self.assertIsNone(case.closed_at)
        self.assertEqual(len(case.audit_events), event_count + 1)
        self.assertEqual(case.audit_events[-1].event_type, "transition_rejected")
        self.assertEqual(case.audit_events[-1].before_state, before)
        self.assertEqual(case.audit_events[-1].after_state, before)
        self.assertEqual(len(case.integrity_alerts), alert_count + 1)

    def test_deny_closes_directly_without_execution(self) -> None:
        case = self.case_at_disposition_selection()

        case.select_disposition(Disposition.DENY, actor="reviewer")

        self.assertEqual(case.case_status, CaseStatus.CLOSED)
        self.assertEqual(case.disposition, Disposition.DENY)
        self.assertEqual(case.execution_status, ExecutionStatus.NOT_APPLICABLE)
        self.assertIsNotNone(case.closed_at)
        self.assertIs(case.closed_at.tzinfo, UTC)
        self.assertNotIn(
            CaseStatus.EXECUTING,
            (event.after_state.case_status for event in case.audit_events),
        )

    def test_carrier_filing_waits_for_external_result(self) -> None:
        case = self.case_at_disposition_selection()
        case.select_disposition(Disposition.OPEN_CARRIER_INQUIRY, actor="reviewer")
        case.record_execution_status(ExecutionStatus.SUCCEEDED, actor="carrier-adapter")
        case.complete_execution(actor="carrier-adapter")

        self.assertEqual(
            case.case_status, CaseStatus.AWAITING_EXTERNAL_FOLLOW_UP
        )
        self.assertEqual(case.execution_status, ExecutionStatus.SUCCEEDED)
        self.assertEqual(case.follow_up_status, FollowUpStatus.PENDING)
        self.assertIsNone(case.closed_at)

        case.record_follow_up_result(
            FollowUpStatus.RESOLVED_FAVORABLE, actor="carrier-adapter"
        )
        self.assertEqual(case.case_status, CaseStatus.HUMAN_REVIEW)
        self.assertEqual(
            case.follow_up_status, FollowUpStatus.RESOLVED_FAVORABLE
        )

    def test_failed_execution_can_route_to_human_review(self) -> None:
        for disposition in (
            Disposition.APPROVE_REFUND,
            Disposition.APPROVE_REPLACEMENT,
        ):
            with self.subTest(disposition=disposition):
                case = self.case_at_disposition_selection()
                case.select_disposition(disposition, actor="reviewer")
                case.record_execution_status(
                    ExecutionStatus.FAILED, actor="execution-system"
                )
                case.route_execution_failure_to_review(actor="system")

                self.assertEqual(case.case_status, CaseStatus.HUMAN_REVIEW)
                self.assertEqual(case.disposition, disposition)
                self.assertEqual(case.execution_status, ExecutionStatus.FAILED)

    def test_invalid_lifecycle_transition_preserves_state_and_records_failure(
        self,
    ) -> None:
        case = SupportCase("case-001")
        before = case.snapshot()

        with self.assertRaises(TransitionRejected):
            case.transition_to(CaseStatus.POLICY_REVIEW, actor="system")

        self.assertEqual(case.snapshot(), before)
        self.assertEqual(case.audit_events[-1].event_type, "transition_rejected")
        self.assertEqual(case.audit_events[-1].before_state, before)
        self.assertEqual(case.audit_events[-1].after_state, before)
        self.assertEqual(len(case.integrity_alerts), 1)

    def test_missing_linkage_data_preserves_state(self) -> None:
        case = SupportCase("case-001")
        before = case.snapshot()

        with self.assertRaises(TransitionRejected):
            case.link("", "order-001", actor="agent")

        self.assertEqual(case.snapshot(), before)
        self.assertEqual(len(case.integrity_alerts), 1)

    def test_unknown_disposition_is_rejected_without_closing(self) -> None:
        case = self.case_at_disposition_selection()
        before = case.snapshot()

        with self.assertRaises(TransitionRejected):
            case.select_disposition("unknown", actor="agent")  # type: ignore[arg-type]

        self.assertEqual(case.snapshot(), before)
        self.assertEqual(len(case.integrity_alerts), 1)

    def test_closed_case_cannot_transition(self) -> None:
        case = self.case_at_disposition_selection()
        case.select_disposition(Disposition.DENY, actor="reviewer")
        before = case.snapshot()

        with self.assertRaises(TransitionRejected):
            case.transition_to(CaseStatus.HUMAN_REVIEW, actor="system")

        self.assertEqual(case.snapshot(), before)
        self.assertEqual(case.case_status, CaseStatus.CLOSED)

    def test_public_state_and_audit_records_are_read_only(self) -> None:
        case = SupportCase("case-001")
        with self.assertRaises(AttributeError):
            case.case_status = CaseStatus.CLOSED  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            case.audit_events[0].detail = "changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
