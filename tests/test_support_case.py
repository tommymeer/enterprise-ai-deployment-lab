from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
import unittest

from support_agent import (
    AddressMatchResult,
    CarrierEvidenceSnapshot,
    CaseStatus,
    CustomerReference,
    CustomerReport,
    Disposition,
    ExecutionStatus,
    FollowUpStatus,
    HumanReviewDecision,
    HumanReviewRequest,
    MatchStatus,
    OrderReference,
    PolicyEvaluationResult,
    PolicyPlaceholder,
    PolicyRoute,
    RetrievalStatus,
    ShipmentReference,
    SupportCase,
    TransitionRejected,
    evaluate_synthetic_structural_policy,
)


class SupportCaseTest(unittest.TestCase):
    def matched_customer(self) -> CustomerReference:
        return CustomerReference(
            "customer-001",
            MatchStatus.MATCHED,
            datetime(2026, 7, 28, 12, tzinfo=UTC),
            RetrievalStatus.SUCCESS,
        )

    def matched_order(self) -> OrderReference:
        return OrderReference(
            "order-001",
            MatchStatus.MATCHED,
            "49.95 USD",
            "home_goods",
            "100 Example Ave",
            datetime(2026, 7, 28, 12, 1, tzinfo=UTC),
            RetrievalStatus.SUCCESS,
        )

    def shipment(self, ref_id: str = "shipment-001") -> ShipmentReference:
        return ShipmentReference(
            ref_id,
            "Synthetic Carrier",
            "tracking-001",
            datetime(2026, 7, 27, 10, tzinfo=UTC),
            datetime(2026, 7, 28, 12, 2, tzinfo=UTC),
            RetrievalStatus.SUCCESS,
        )

    def case_at_disposition_selection(self) -> SupportCase:
        case = SupportCase("case-001")
        case.link(self.matched_customer(), self.matched_order(), actor="agent")
        case.transition_to(CaseStatus.EVIDENCE_GATHERING, actor="agent")
        case.transition_to(CaseStatus.POLICY_REVIEW, actor="agent")
        case.transition_to(CaseStatus.DISPOSITION_SELECTION, actor="policy")
        return case

    def case_at_policy_review(
        self,
        *,
        evidence_status: RetrievalStatus = RetrievalStatus.SUCCESS,
        address_result: AddressMatchResult | None = AddressMatchResult.MATCH,
    ) -> SupportCase:
        case = SupportCase("case-policy")
        case.record_customer_report(
            CustomerReport(
                "tracking-001",
                "100 Example Ave",
                "Checked porch",
                "Asked household",
                datetime(2026, 7, 28, 11, tzinfo=UTC),
            ),
            actor="agent",
        )
        case.link(self.matched_customer(), self.matched_order(), actor="agent")
        case.attach_shipment(self.shipment(), actor="order-system")
        if evidence_status is RetrievalStatus.SUCCESS:
            evidence = CarrierEvidenceSnapshot(
                "snapshot-001",
                "shipment-001",
                "delivered",
                datetime(2026, 7, 28, 9, tzinfo=UTC),
                ("delivered",),
                False,
                datetime(2026, 7, 28, 12, 3, tzinfo=UTC),
                evidence_status,
            )
        else:
            evidence = CarrierEvidenceSnapshot(
                "snapshot-001",
                "shipment-001",
                None,
                None,
                (),
                None,
                datetime(2026, 7, 28, 12, 3, tzinfo=UTC),
                evidence_status,
            )
        case.attach_carrier_evidence(evidence, actor="carrier-system")
        if address_result is not None:
            case.record_address_match_result(address_result, actor="agent")
        case.transition_to(CaseStatus.EVIDENCE_GATHERING, actor="agent")
        case.transition_to(CaseStatus.POLICY_REVIEW, actor="agent")
        return case

    def evaluation(
        self,
        case: SupportCase,
        evaluation_id: str = "evaluation-001",
        unresolved_policies: tuple[PolicyPlaceholder, ...] = (),
    ) -> PolicyEvaluationResult:
        return evaluate_synthetic_structural_policy(
            case,
            evaluation_id=evaluation_id,
            evaluated_at=datetime(2026, 7, 28, 13, tzinfo=UTC),
            unresolved_policies=unresolved_policies,
        )

    def case_with_open_authority_review(self) -> SupportCase:
        case = self.case_at_policy_review()
        result = self.evaluation(
            case,
            unresolved_policies=(PolicyPlaceholder.FRONTLINE_REFUND_AUTHORITY,),
        )
        case.record_policy_evaluation(result, actor="policy")
        case.open_human_review(
            HumanReviewRequest(
                "review-001",
                datetime(2026, 7, 28, 13, 1, tzinfo=UTC),
                "frontline refund authority is unresolved",
                (PolicyPlaceholder.FRONTLINE_REFUND_AUTHORITY,),
                (),
            ),
            actor="policy",
        )
        return case

    def test_complete_structural_evidence_can_proceed(self) -> None:
        case = self.case_at_policy_review()
        result = self.evaluation(case)

        self.assertEqual(result.route, PolicyRoute.PROCEED_TO_DISPOSITION)
        case.record_policy_evaluation(result, actor="policy")

        self.assertEqual(case.case_status, CaseStatus.DISPOSITION_SELECTION)
        self.assertEqual(case.disposition, Disposition.NONE_SELECTED)

    def test_missing_evidence_routes_to_customer_action(self) -> None:
        case = SupportCase("case-missing")
        result = self.evaluation(case)

        self.assertEqual(result.route, PolicyRoute.REQUEST_MORE_INFORMATION)
        self.assertIn("customer report", result.reasons[0])

    def test_failed_retrieval_routes_to_human_review(self) -> None:
        case = self.case_at_policy_review(evidence_status=RetrievalStatus.FAILURE)
        result = self.evaluation(case)
        case.record_policy_evaluation(result, actor="policy")

        self.assertEqual(result.route, PolicyRoute.REQUIRE_HUMAN_REVIEW)
        self.assertEqual(case.case_status, CaseStatus.HUMAN_REVIEW)

    def test_address_mismatch_routes_to_human_review(self) -> None:
        case = self.case_at_policy_review(
            address_result=AddressMatchResult.MISMATCH
        )

        self.assertEqual(
            self.evaluation(case).route, PolicyRoute.REQUIRE_HUMAN_REVIEW
        )

    def test_unresolved_authority_routes_to_human_review(self) -> None:
        case = self.case_at_policy_review()
        result = self.evaluation(
            case,
            unresolved_policies=(PolicyPlaceholder.FRONTLINE_REFUND_AUTHORITY,),
        )

        self.assertEqual(result.route, PolicyRoute.REQUIRE_HUMAN_REVIEW)
        self.assertEqual(
            result.unresolved_policies,
            (PolicyPlaceholder.FRONTLINE_REFUND_AUTHORITY,),
        )

    def test_duplicate_policy_evaluation_is_rejected_without_mutation(self) -> None:
        case = self.case_at_policy_review()
        result = PolicyEvaluationResult(
            "evaluation-duplicate",
            PolicyRoute.REQUEST_MORE_INFORMATION,
            datetime(2026, 7, 28, 13, tzinfo=UTC),
            (),
            (),
            ("more information is needed",),
        )
        case.record_policy_evaluation(result, actor="policy")
        case.transition_to(CaseStatus.POLICY_REVIEW, actor="agent")
        before = case.snapshot()

        with self.assertRaises(TransitionRejected):
            case.record_policy_evaluation(result, actor="policy")

        self.assertEqual(case.snapshot(), before)
        self.assertEqual(case.policy_evaluation_results, (result,))
        self.assertEqual(case.audit_events[-1].event_type, "transition_rejected")
        self.assertEqual(len(case.integrity_alerts), 1)

    def test_human_review_rejects_unknown_evidence_and_stores_valid_request(
        self,
    ) -> None:
        case = self.case_at_policy_review(evidence_status=RetrievalStatus.FAILURE)
        case.record_policy_evaluation(self.evaluation(case), actor="policy")
        unknown = HumanReviewRequest(
            "review-unknown",
            datetime(2026, 7, 28, 13, 1, tzinfo=UTC),
            "inspect retrieval failure",
            (),
            ("missing-snapshot",),
        )
        before = case.snapshot()

        with self.assertRaises(TransitionRejected):
            case.open_human_review(unknown, actor="agent")

        self.assertEqual(case.snapshot(), before)
        self.assertEqual(case.human_review_requests, ())
        valid = HumanReviewRequest(
            "review-valid",
            datetime(2026, 7, 28, 13, 2, tzinfo=UTC),
            "inspect retrieval failure",
            (),
            ("snapshot-001",),
        )
        case.open_human_review(valid, actor="agent")
        self.assertEqual(case.human_review_requests, (valid,))

    def test_human_reviewer_refund_executes_without_closing(self) -> None:
        case = self.case_with_open_authority_review()
        decision = HumanReviewDecision(
            "review-001",
            datetime(2026, 7, 28, 13, 5, tzinfo=UTC),
            "senior-reviewer",
            Disposition.APPROVE_REFUND,
            "approved after manual authority review",
        )

        case.record_human_review_decision(decision, actor="review-service")

        self.assertEqual(case.case_status, CaseStatus.EXECUTING)
        self.assertEqual(case.execution_status, ExecutionStatus.NOT_STARTED)
        self.assertIsNone(case.closed_at)
        self.assertEqual(case.human_review_decisions, (decision,))

    def test_human_review_disposition_failure_is_atomic(self) -> None:
        case = self.case_with_open_authority_review()
        decision = HumanReviewDecision(
            "review-001",
            datetime(2026, 7, 28, 13, 5, tzinfo=UTC),
            "senior-reviewer",
            Disposition.APPROVE_REFUND,
            "approved after manual authority review",
        )
        before = case.snapshot()
        decisions_before = case.human_review_decisions
        event_count = len(case.audit_events)
        alert_count = len(case.integrity_alerts)

        with self.assertRaises(TransitionRejected):
            case.record_human_review_decision(
                decision,
                actor="review-service",
                execution_data_present=False,
            )

        self.assertEqual(case.snapshot(), before)
        self.assertEqual(case.human_review_decisions, decisions_before)
        self.assertEqual(len(case.audit_events), event_count + 1)
        self.assertEqual(case.audit_events[-1].event_type, "transition_rejected")
        self.assertEqual(case.audit_events[-1].before_state, before)
        self.assertEqual(case.audit_events[-1].after_state, before)
        self.assertEqual(len(case.integrity_alerts), alert_count + 1)

    def test_human_reviewer_denial_closes_directly(self) -> None:
        case = self.case_with_open_authority_review()
        case.record_human_review_decision(
            HumanReviewDecision(
                "review-001",
                datetime(2026, 7, 28, 13, 5, tzinfo=UTC),
                "senior-reviewer",
                Disposition.DENY,
                "manual review supports denial",
            ),
            actor="review-service",
        )

        self.assertEqual(case.case_status, CaseStatus.CLOSED)
        self.assertEqual(case.disposition, Disposition.DENY)

    def test_duplicate_review_decision_is_rejected(self) -> None:
        case = self.case_with_open_authority_review()
        decision = HumanReviewDecision(
            "review-001",
            datetime(2026, 7, 28, 13, 5, tzinfo=UTC),
            "senior-reviewer",
            Disposition.REQUEST_MORE_INFO,
            "need a customer statement",
        )
        case.record_human_review_decision(decision, actor="review-service")
        case.transition_to(CaseStatus.POLICY_REVIEW, actor="agent")
        case.record_policy_evaluation(
            PolicyEvaluationResult(
                "evaluation-002",
                PolicyRoute.REQUIRE_HUMAN_REVIEW,
                datetime(2026, 7, 28, 14, tzinfo=UTC),
                (),
                (PolicyPlaceholder.FRONTLINE_REFUND_AUTHORITY,),
                ("authority remains unresolved",),
            ),
            actor="policy",
        )
        before = case.snapshot()

        with self.assertRaises(TransitionRejected):
            case.record_human_review_decision(decision, actor="review-service")

        self.assertEqual(case.snapshot(), before)
        self.assertEqual(case.human_review_decisions, (decision,))

    def test_policy_and_review_records_are_immutable_and_collections_read_only(
        self,
    ) -> None:
        case = self.case_with_open_authority_review()
        evaluation = case.policy_evaluation_results[0]
        request = case.human_review_requests[0]

        with self.assertRaises(FrozenInstanceError):
            evaluation.route = PolicyRoute.PROCEED_TO_DISPOSITION  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            request.reason = "changed"  # type: ignore[misc]
        with self.assertRaises(AttributeError):
            case.policy_evaluation_results.append(evaluation)  # type: ignore[attr-defined]
        with self.assertRaises(AttributeError):
            case.human_review_requests.append(request)  # type: ignore[attr-defined]
        with self.assertRaises(AttributeError):
            case.human_review_decisions.append(None)  # type: ignore[attr-defined]

    def test_policy_and_review_records_reject_runtime_values_and_naive_time(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            PolicyEvaluationResult(
                "evaluation",
                "proceed_to_disposition",  # type: ignore[arg-type]
                datetime(2026, 7, 28, 13),
                (),
                (),
                ("complete",),
            )
        with self.assertRaises(ValueError):
            HumanReviewRequest(
                "review",
                datetime(2026, 7, 28, 13),
                "reason",
                ("FRONTLINE_REFUND_AUTHORITY",),  # type: ignore[arg-type]
                (),
            )
        with self.assertRaises(ValueError):
            HumanReviewDecision(
                "review",
                datetime(2026, 7, 28, 13, tzinfo=UTC),
                "reviewer",
                "approve_refund",  # type: ignore[arg-type]
                "rationale",
            )

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

    def test_ambiguous_customer_match_preserves_state(self) -> None:
        case = SupportCase("case-001")
        before = case.snapshot()
        customer = CustomerReference(
            "customer-lookup-001",
            MatchStatus.AMBIGUOUS,
            datetime(2026, 7, 28, 12, tzinfo=UTC),
            RetrievalStatus.SUCCESS,
        )

        with self.assertRaises(TransitionRejected):
            case.link(customer, self.matched_order(), actor="agent")

        self.assertEqual(case.snapshot(), before)
        self.assertIsNone(case.customer_ref)
        self.assertIsNone(case.order_ref)
        self.assertEqual(len(case.integrity_alerts), 1)

    def test_successful_structured_linkage_stores_references(self) -> None:
        case = SupportCase("case-001")
        customer = self.matched_customer()
        order = self.matched_order()

        case.link(customer, order, actor="agent")

        self.assertEqual(case.case_status, CaseStatus.LINKED)
        self.assertIs(case.customer_ref, customer)
        self.assertIs(case.order_ref, order)

    def test_failed_order_retrieval_preserves_state(self) -> None:
        case = SupportCase("case-001")
        before = case.snapshot()
        order = OrderReference(
            "order-lookup-001",
            MatchStatus.NOT_FOUND,
            None,
            None,
            None,
            datetime(2026, 7, 28, 12, tzinfo=UTC),
            RetrievalStatus.FAILURE,
        )

        with self.assertRaises(TransitionRejected):
            case.link(self.matched_customer(), order, actor="agent")

        self.assertEqual(case.snapshot(), before)
        self.assertIsNone(case.customer_ref)
        self.assertIsNone(case.order_ref)
        self.assertEqual(case.audit_events[-1].event_type, "transition_rejected")
        self.assertEqual(len(case.integrity_alerts), 1)

    def test_customer_report_and_address_match_are_recorded(self) -> None:
        case = SupportCase("case-001")
        report = CustomerReport(
            "tracking-001",
            "100 Example Ave",
            "Checked porch and mailroom at 11:00 UTC",
            "Household members and neighbors",
            datetime(2026, 7, 28, 11, tzinfo=UTC),
        )

        case.record_customer_report(report, actor="agent")
        case.record_address_match_result(AddressMatchResult.MATCH, actor="agent")

        self.assertIs(case.customer_report, report)
        self.assertEqual(case.address_match_result, AddressMatchResult.MATCH)
        self.assertTrue(case.address_match_recorded)

    def test_structural_policy_distinguishes_unrecorded_from_recorded_unknown(
        self,
    ) -> None:
        unrecorded = self.case_at_policy_review(address_result=None)

        self.assertEqual(
            self.evaluation(unrecorded).route,
            PolicyRoute.REQUEST_MORE_INFORMATION,
        )

        recorded_unknown = self.case_at_policy_review(
            address_result=AddressMatchResult.UNKNOWN
        )
        result = self.evaluation(recorded_unknown)

        self.assertTrue(recorded_unknown.address_match_recorded)
        self.assertEqual(result.route, PolicyRoute.PROCEED_TO_DISPOSITION)
        self.assertIn("address result recorded: unknown", result.evidence_summary)

    def test_invalid_address_match_is_audited_without_changing_case(self) -> None:
        case = SupportCase("case-001")
        before = case.snapshot()
        event_count = len(case.audit_events)

        with self.assertRaises(TransitionRejected):
            case.record_address_match_result("match", actor="agent")  # type: ignore[arg-type]

        self.assertEqual(case.snapshot(), before)
        self.assertEqual(case.address_match_result, AddressMatchResult.UNKNOWN)
        self.assertEqual(len(case.audit_events), event_count + 1)
        self.assertEqual(case.audit_events[-1].event_type, "transition_rejected")
        self.assertEqual(case.audit_events[-1].before_state, before)
        self.assertEqual(case.audit_events[-1].after_state, before)
        self.assertEqual(len(case.integrity_alerts), 1)

    def test_shipment_attachment_and_duplicate_rejection(self) -> None:
        case = SupportCase("case-001")
        shipment = self.shipment()
        case.attach_shipment(shipment, actor="order-system")
        before = case.snapshot()

        self.assertEqual(case.shipment_refs, (shipment,))
        with self.assertRaises(TransitionRejected):
            case.attach_shipment(shipment, actor="order-system")

        self.assertEqual(case.snapshot(), before)
        self.assertEqual(case.shipment_refs, (shipment,))
        self.assertEqual(case.audit_events[-1].event_type, "transition_rejected")
        self.assertEqual(len(case.integrity_alerts), 1)

    def test_carrier_evidence_requires_known_shipment(self) -> None:
        case = SupportCase("case-001")
        evidence = CarrierEvidenceSnapshot(
            "snapshot-001",
            "shipment-missing",
            None,
            None,
            (),
            None,
            datetime(2026, 7, 28, 12, tzinfo=UTC),
            RetrievalStatus.FAILURE,
        )

        with self.assertRaises(TransitionRejected):
            case.attach_carrier_evidence(evidence, actor="carrier-system")

        self.assertEqual(case.carrier_evidence_snapshots, ())
        self.assertEqual(len(case.integrity_alerts), 1)

    def test_failed_carrier_retrieval_needs_no_delivery_evidence(self) -> None:
        case = SupportCase("case-001")
        case.attach_shipment(self.shipment(), actor="order-system")
        evidence = CarrierEvidenceSnapshot(
            "snapshot-001",
            "shipment-001",
            None,
            None,
            (),
            None,
            datetime(2026, 7, 28, 12, 3, tzinfo=UTC),
            RetrievalStatus.FAILURE,
        )

        case.attach_carrier_evidence(evidence, actor="carrier-system")

        self.assertEqual(case.carrier_evidence_snapshots, (evidence,))
        self.assertIsNone(evidence.delivery_status)
        self.assertEqual(evidence.tracking_event_history, ())

    def test_successful_carrier_evidence_stores_retrieved_facts(self) -> None:
        case = SupportCase("case-001")
        case.attach_shipment(self.shipment(), actor="order-system")
        delivered_at = datetime(2026, 7, 28, 9, 30, tzinfo=UTC)
        evidence = CarrierEvidenceSnapshot(
            "snapshot-001",
            "shipment-001",
            "delivered",
            delivered_at,
            ("out_for_delivery", "delivered"),
            True,
            datetime(2026, 7, 28, 12, 3, tzinfo=UTC),
            RetrievalStatus.SUCCESS,
        )

        case.attach_carrier_evidence(evidence, actor="carrier-system")

        stored = case.carrier_evidence_snapshots[0]
        self.assertEqual(stored.delivery_status, "delivered")
        self.assertEqual(stored.delivery_timestamp, delivered_at)
        self.assertEqual(
            stored.tracking_event_history, ("out_for_delivery", "delivered")
        )
        self.assertTrue(stored.picture_proof_available)

    def test_duplicate_carrier_evidence_snapshot_is_not_added(self) -> None:
        case = SupportCase("case-001")
        case.attach_shipment(self.shipment(), actor="order-system")
        evidence = CarrierEvidenceSnapshot(
            "snapshot-001",
            "shipment-001",
            None,
            None,
            (),
            None,
            datetime(2026, 7, 28, 12, 3, tzinfo=UTC),
            RetrievalStatus.FAILURE,
        )
        case.attach_carrier_evidence(evidence, actor="carrier-system")

        with self.assertRaises(TransitionRejected):
            case.attach_carrier_evidence(evidence, actor="carrier-system")

        self.assertEqual(case.carrier_evidence_snapshots, (evidence,))
        self.assertEqual(case.audit_events[-1].event_type, "transition_rejected")
        self.assertEqual(len(case.integrity_alerts), 1)

    def test_plain_string_retrieval_status_cannot_bypass_invariants(self) -> None:
        with self.assertRaises(ValueError):
            ShipmentReference(
                "shipment-001",
                "Synthetic Carrier",
                "tracking-001",
                None,
                datetime(2026, 7, 28, 12, tzinfo=UTC),
                "failure",  # type: ignore[arg-type]
            )

    def test_plain_string_match_status_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CustomerReference(
                "customer-001",
                "matched",  # type: ignore[arg-type]
                datetime(2026, 7, 28, 12, tzinfo=UTC),
                RetrievalStatus.SUCCESS,
            )

    def test_whitespace_only_evidence_identifiers_are_rejected(self) -> None:
        constructors = (
            lambda: CustomerReference(
                " \t", MatchStatus.NOT_FOUND, datetime(2026, 7, 28, 12, tzinfo=UTC),
                RetrievalStatus.SUCCESS,
            ),
            lambda: OrderReference(
                "\n", MatchStatus.NOT_FOUND, None, None, None,
                datetime(2026, 7, 28, 12, tzinfo=UTC), RetrievalStatus.SUCCESS,
            ),
            lambda: ShipmentReference(
                "  ", None, None, None, datetime(2026, 7, 28, 12, tzinfo=UTC),
                RetrievalStatus.FAILURE,
            ),
            lambda: CarrierEvidenceSnapshot(
                "\t", "shipment-001", None, None, (), None,
                datetime(2026, 7, 28, 12, tzinfo=UTC), RetrievalStatus.FAILURE,
            ),
            lambda: CarrierEvidenceSnapshot(
                "snapshot-001", "\n", None, None, (), None,
                datetime(2026, 7, 28, 12, tzinfo=UTC), RetrievalStatus.FAILURE,
            ),
        )

        for constructor in constructors:
            with self.subTest(constructor=constructor):
                with self.assertRaises(ValueError):
                    constructor()

    def test_failed_carrier_retrieval_with_delivery_facts_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CarrierEvidenceSnapshot(
                "snapshot-001",
                "shipment-001",
                "delivered",
                None,
                (),
                None,
                datetime(2026, 7, 28, 12, tzinfo=UTC),
                RetrievalStatus.FAILURE,
            )

    def test_successful_carrier_retrieval_without_status_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CarrierEvidenceSnapshot(
                "snapshot-001",
                "shipment-001",
                None,
                None,
                (),
                False,
                datetime(2026, 7, 28, 12, tzinfo=UTC),
                RetrievalStatus.SUCCESS,
            )

    def test_failed_order_retrieval_with_details_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            OrderReference(
                "order-001",
                MatchStatus.NOT_FOUND,
                "49.95 USD",
                None,
                None,
                datetime(2026, 7, 28, 12, tzinfo=UTC),
                RetrievalStatus.FAILURE,
            )

    def test_matched_order_without_minimum_facts_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            OrderReference(
                "order-001",
                MatchStatus.MATCHED,
                "49.95 USD",
                "",
                "100 Example Ave",
                datetime(2026, 7, 28, 12, tzinfo=UTC),
                RetrievalStatus.SUCCESS,
            )

    def test_failed_shipment_retrieval_with_tracking_facts_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            ShipmentReference(
                "shipment-001",
                "Synthetic Carrier",
                "tracking-001",
                None,
                datetime(2026, 7, 28, 12, tzinfo=UTC),
                RetrievalStatus.FAILURE,
            )

    def test_public_evidence_collections_are_read_only(self) -> None:
        case = SupportCase("case-001")
        case.attach_shipment(self.shipment(), actor="order-system")

        with self.assertRaises(AttributeError):
            case.shipment_refs.append(self.shipment("shipment-002"))  # type: ignore[attr-defined]
        with self.assertRaises(AttributeError):
            case.carrier_evidence_snapshots.append(None)  # type: ignore[attr-defined]

    def test_evidence_records_are_immutable_and_require_utc(self) -> None:
        customer = self.matched_customer()
        with self.assertRaises(FrozenInstanceError):
            customer.ref_id = "changed"  # type: ignore[misc]

        with self.assertRaises(ValueError):
            CustomerReference(
                "customer-001",
                MatchStatus.MATCHED,
                datetime(2026, 7, 28, 12),
                RetrievalStatus.SUCCESS,
            )
        with self.assertRaises(ValueError):
            CustomerReference(
                "customer-001",
                MatchStatus.MATCHED,
                datetime(
                    2026, 7, 28, 12, tzinfo=timezone(timedelta(hours=-4))
                ),
                RetrievalStatus.SUCCESS,
            )

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
