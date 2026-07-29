from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
import unittest

from support_agent import (
    AddressMatchResult,
    CarrierEvidenceSnapshot,
    CaseStatus,
    CustomerReference,
    Disposition,
    ExecutionResult,
    ExecutionStatus,
    FollowUpStatus,
    HumanReviewDecision,
    HumanReviewRequest,
    MatchStatus,
    OrderReference,
    PolicyPlaceholder,
    RetrievalStatus,
    ShipmentReference,
    SupportCase,
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


class WorkflowTest(unittest.TestCase):
    now = datetime(2026, 7, 28, 14, tzinfo=UTC)

    def case_input(self) -> SyntheticSupportCaseInput:
        return SyntheticSupportCaseInput(
            "case-001",
            "Tracking says delivered, but I did not receive the package.",
            "customer-001",
            "order-001",
            "shipment-001",
            "support-agent",
            self.now,
        )

    def customer(
        self,
        retrieval: RetrievalStatus = RetrievalStatus.SUCCESS,
        match: MatchStatus = MatchStatus.MATCHED,
    ) -> CustomerReference:
        return CustomerReference("customer-001", match, self.now, retrieval)

    def order(self) -> OrderReference:
        return OrderReference(
            "order-001",
            MatchStatus.MATCHED,
            "49.95 USD",
            "home_goods",
            "100 Example Ave",
            self.now,
            RetrievalStatus.SUCCESS,
        )

    def shipment(self) -> ShipmentReference:
        return ShipmentReference(
            "shipment-001",
            "Synthetic Carrier",
            "tracking-001",
            self.now,
            self.now,
            RetrievalStatus.SUCCESS,
        )

    def evidence(
        self, retrieval: RetrievalStatus = RetrievalStatus.SUCCESS
    ) -> CarrierEvidenceSnapshot:
        if retrieval is RetrievalStatus.FAILURE:
            return CarrierEvidenceSnapshot(
                "evidence-001",
                "shipment-001",
                None,
                None,
                (),
                None,
                self.now,
                retrieval,
            )
        return CarrierEvidenceSnapshot(
            "evidence-001",
            "shipment-001",
            "delivered",
            self.now,
            ("out for delivery", "delivered"),
            True,
            self.now,
            retrieval,
        )

    def execution(
        self,
        *,
        refund: bool = True,
        replacement: bool = True,
        inquiry: bool = True,
    ) -> SyntheticExecutionAdapter:
        return SyntheticExecutionAdapter(
            ExecutionResult(refund, "synthetic refund result"),
            ExecutionResult(replacement, "synthetic replacement result"),
            ExecutionResult(inquiry, "synthetic inquiry filing result"),
        )

    def reviewer(
        self,
        disposition: Disposition = Disposition.APPROVE_REFUND,
        policies: tuple[PolicyPlaceholder, ...] = (),
    ) -> SyntheticHumanReviewer:
        request = HumanReviewRequest(
            "review-001",
            self.now,
            "configured synthetic review",
            policies,
            () if policies else ("evidence-001",),
        )
        decision = HumanReviewDecision(
            "review-001",
            self.now,
            "synthetic-reviewer",
            disposition,
            "configured synthetic decision",
        )
        return SyntheticHumanReviewer(request, decision)

    def configuration(
        self,
        *,
        disposition: Disposition = Disposition.APPROVE_REFUND,
        evidence: CarrierEvidenceSnapshot | None = ...,
        address: AddressMatchResult = AddressMatchResult.MATCH,
        unresolved: tuple[PolicyPlaceholder, ...] = (),
        reviewer: SyntheticHumanReviewer | None = None,
        execution: SyntheticExecutionAdapter | None = None,
        customer: CustomerReference | None = None,
    ) -> WorkflowConfiguration:
        evidence_result = self.evidence() if evidence is ... else evidence
        return WorkflowConfiguration(
            SyntheticCustomerLookup(customer or self.customer()),
            SyntheticOrderLookup(self.order()),
            SyntheticShipmentLookup(self.shipment()),
            SyntheticCarrierEvidenceLookup(evidence_result),
            SyntheticAddressComparison(address),
            execution or self.execution(),
            disposition,
            self.now,
            unresolved,
            reviewer,
        )

    def test_refund_success_closes_case(self) -> None:
        result = run_synthetic_support_case(
            self.case_input(), self.configuration()
        )
        self.assertTrue(result.completed)
        self.assertEqual(result.final_case_status, CaseStatus.CLOSED)
        self.assertEqual(result.final_disposition, Disposition.APPROVE_REFUND)
        self.assertEqual(result.case.execution_status, ExecutionStatus.SUCCEEDED)

    def test_refund_failure_routes_to_human_review(self) -> None:
        result = run_synthetic_support_case(
            self.case_input(),
            self.configuration(execution=self.execution(refund=False)),
        )
        self.assertFalse(result.completed)
        self.assertEqual(result.final_case_status, CaseStatus.HUMAN_REVIEW)
        self.assertEqual(result.failure_stage, "execution")
        self.assertIsNone(result.case.closed_at)

    def test_denial_closes_without_execution(self) -> None:
        calls = 0

        def execution(disposition: Disposition, case: SupportCase) -> ExecutionResult:
            nonlocal calls
            calls += 1
            return ExecutionResult(True, "should not be called")

        result = run_synthetic_support_case(
            self.case_input(),
            self.configuration(disposition=Disposition.DENY, execution=execution),
        )
        self.assertEqual(result.final_case_status, CaseStatus.CLOSED)
        self.assertEqual(calls, 0)

    def test_request_more_information_awaits_customer(self) -> None:
        result = run_synthetic_support_case(
            self.case_input(),
            self.configuration(disposition=Disposition.REQUEST_MORE_INFO),
        )
        self.assertTrue(result.completed)
        self.assertEqual(
            result.final_case_status, CaseStatus.AWAITING_CUSTOMER_ACTION
        )

    def test_missing_evidence_routes_to_customer_action(self) -> None:
        result = run_synthetic_support_case(
            self.case_input(), self.configuration(evidence=None)
        )
        self.assertTrue(result.completed)
        self.assertEqual(
            result.final_case_status, CaseStatus.AWAITING_CUSTOMER_ACTION
        )
        self.assertEqual(result.case.carrier_evidence_snapshots, ())

    def test_failed_carrier_retrieval_uses_human_reviewer(self) -> None:
        result = run_synthetic_support_case(
            self.case_input(),
            self.configuration(
                evidence=self.evidence(RetrievalStatus.FAILURE),
                reviewer=self.reviewer(Disposition.DENY),
            ),
        )
        self.assertEqual(result.final_case_status, CaseStatus.CLOSED)
        self.assertEqual(result.final_disposition, Disposition.DENY)

    def test_address_mismatch_causes_human_review(self) -> None:
        result = run_synthetic_support_case(
            self.case_input(),
            self.configuration(
                address=AddressMatchResult.MISMATCH,
                reviewer=self.reviewer(Disposition.REQUEST_MORE_INFO),
            ),
        )
        self.assertEqual(
            result.final_case_status, CaseStatus.AWAITING_CUSTOMER_ACTION
        )
        self.assertEqual(len(result.case.human_review_decisions), 1)

    def test_unresolved_policy_causes_human_review(self) -> None:
        policy = PolicyPlaceholder.FRONTLINE_REFUND_AUTHORITY
        result = run_synthetic_support_case(
            self.case_input(),
            self.configuration(
                unresolved=(policy,),
                reviewer=self.reviewer(Disposition.DENY, (policy,)),
            ),
        )
        self.assertEqual(len(result.case.human_review_requests), 1)
        self.assertEqual(result.final_case_status, CaseStatus.CLOSED)

    def test_human_refund_decision_executes_and_completes(self) -> None:
        policy = PolicyPlaceholder.FRONTLINE_REFUND_AUTHORITY
        result = run_synthetic_support_case(
            self.case_input(),
            self.configuration(
                unresolved=(policy,),
                reviewer=self.reviewer(Disposition.APPROVE_REFUND, (policy,)),
            ),
        )
        self.assertEqual(result.final_case_status, CaseStatus.CLOSED)
        self.assertEqual(result.case.execution_status, ExecutionStatus.SUCCEEDED)

    def test_carrier_inquiry_waits_for_external_follow_up(self) -> None:
        result = run_synthetic_support_case(
            self.case_input(),
            self.configuration(disposition=Disposition.OPEN_CARRIER_INQUIRY),
        )
        self.assertEqual(
            result.final_case_status, CaseStatus.AWAITING_EXTERNAL_FOLLOW_UP
        )
        self.assertEqual(result.case.follow_up_status, FollowUpStatus.PENDING)
        self.assertIsNone(result.case.closed_at)

    def test_lookup_failure_returns_clear_result_without_evidence(self) -> None:
        failed = self.customer(RetrievalStatus.FAILURE, MatchStatus.NOT_FOUND)
        result = run_synthetic_support_case(
            self.case_input(), self.configuration(customer=failed)
        )
        self.assertFalse(result.completed)
        self.assertEqual(result.final_case_status, CaseStatus.INTAKE_FAILED)
        self.assertEqual(result.failure_stage, "customer_lookup")
        self.assertEqual(result.case.shipment_refs, ())
        self.assertEqual(result.case.carrier_evidence_snapshots, ())

    def test_audit_history_has_major_steps_in_order(self) -> None:
        result = run_synthetic_support_case(
            self.case_input(), self.configuration()
        )
        event_types = [event.event_type for event in result.case.audit_events]
        expected = [
            "case_created",
            "customer_report_recorded",
            "shipment_attached",
            "carrier_evidence_attached",
            "address_match_recorded",
            "policy_evaluation_recorded",
            "disposition_selected",
            "execution_status_changed",
            "execution_status_changed",
        ]
        positions = [event_types.index(event) for event in expected]
        self.assertEqual(positions, sorted(positions))

    def test_records_validate_values_timestamps_and_are_immutable(self) -> None:
        with self.assertRaises(ValueError):
            SyntheticSupportCaseInput(
                "", "message", "customer", "order", "shipment", "actor",
                datetime(2026, 7, 28),
            )
        with self.assertRaises(ValueError):
            self.configuration(disposition="deny")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            WorkflowConfiguration(
                lambda value: self.customer(),
                lambda value: self.order(),
                lambda value: self.shipment(),
                lambda value: self.evidence(),
                lambda value, order: AddressMatchResult.MATCH,
                self.execution(),
                Disposition.DENY,
                datetime(2026, 7, 28),
            )
        case = SupportCase("case")
        with self.assertRaises(ValueError):
            WorkflowResult(
                case, False, CaseStatus.INTAKE, Disposition.NONE_SELECTED
            )
        record = self.case_input()
        with self.assertRaises(FrozenInstanceError):
            record.actor = "changed"  # type: ignore[misc]

    def test_execution_adapter_supports_all_configured_outcomes(self) -> None:
        adapter = self.execution(refund=True, replacement=False, inquiry=True)
        case = SupportCase("case")
        self.assertTrue(adapter(Disposition.APPROVE_REFUND, case).succeeded)
        self.assertFalse(adapter(Disposition.APPROVE_REPLACEMENT, case).succeeded)
        self.assertTrue(adapter(Disposition.OPEN_CARRIER_INQUIRY, case).succeeded)


if __name__ == "__main__":
    unittest.main()
