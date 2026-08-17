from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
import unittest
from unittest.mock import patch

from support_agent import (
    AddressMatchResult,
    CarrierEvidenceSnapshot,
    CaseStatus,
    CustomerMessageExtraction,
    CustomerReference,
    Disposition,
    ExecutionResult,
    ExtractionIssueType,
    ExtractionResult,
    ExtractionStatus,
    IntakeRoute,
    IntakeRoutingResult,
    MatchStatus,
    OrderReference,
    RetrievalStatus,
    ShipmentReference,
    SyntheticAddressComparison,
    SyntheticCarrierEvidenceLookup,
    SyntheticCustomerLookup,
    SyntheticExecutionAdapter,
    SyntheticOrderLookup,
    SyntheticShipmentLookup,
    SyntheticSupportCaseInput,
    TrustedIntakeContext,
    WorkflowConfiguration,
    route_customer_message_extraction,
    run_synthetic_support_case,
)
from support_agent.extraction import ExtractionTrace


class IntakeRoutingTest(unittest.TestCase):
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    message = "Tracking says delivered, but it is missing. Order ORD-12345."

    def trace(self, *, clarification: bool | None = False) -> ExtractionTrace:
        return ExtractionTrace(
            "customer-report-extraction-v3",
            "synthetic",
            "scripted-v1",
            True,
            True,
            0,
            0,
            0.0,
            0.0,
            clarification,
            True,
        )

    def extraction(
        self,
        *,
        issue_type: ExtractionIssueType = ExtractionIssueType.DELIVERED_NOT_RECEIVED,
        order_identifier: str | None = "ORD-12345",
        missing: tuple[str, ...] = (),
        clarification_reason: str | None = None,
    ) -> CustomerMessageExtraction:
        return CustomerMessageExtraction(
            self.message,
            issue_type,
            order_identifier,
            None,
            True if issue_type is ExtractionIssueType.DELIVERED_NOT_RECEIVED else None,
            None,
            missing,
            bool(missing),
            clarification_reason,
        )

    def context(self) -> TrustedIntakeContext:
        return TrustedIntakeContext(
            "case-001", "customer-001", "shipment-001", "intake-router", self.now
        )

    def configuration(self) -> WorkflowConfiguration:
        return WorkflowConfiguration(
            SyntheticCustomerLookup(
                CustomerReference(
                    "customer-001", MatchStatus.MATCHED, self.now, RetrievalStatus.SUCCESS
                )
            ),
            SyntheticOrderLookup(
                OrderReference(
                    "ORD-12345",
                    MatchStatus.MATCHED,
                    "49.95 USD",
                    "home_goods",
                    "100 Example Ave",
                    self.now,
                    RetrievalStatus.SUCCESS,
                )
            ),
            SyntheticShipmentLookup(
                ShipmentReference(
                    "shipment-001",
                    "Synthetic Carrier",
                    "TRACK-001",
                    self.now,
                    self.now,
                    RetrievalStatus.SUCCESS,
                )
            ),
            SyntheticCarrierEvidenceLookup(
                CarrierEvidenceSnapshot(
                    "evidence-001",
                    "shipment-001",
                    "delivered",
                    self.now,
                    ("delivered",),
                    False,
                    self.now,
                    RetrievalStatus.SUCCESS,
                )
            ),
            SyntheticAddressComparison(AddressMatchResult.MATCH),
            SyntheticExecutionAdapter(
                ExecutionResult(True, "synthetic refund result"),
                ExecutionResult(True, "synthetic replacement result"),
                ExecutionResult(True, "synthetic inquiry result"),
            ),
            Disposition.APPROVE_REFUND,
            self.now,
            proposed_refund_amount_minor=5_000,
            proposed_refund_currency="USD",
            autonomous_refund_limit_minor=10_000,
            autonomous_refund_limit_currency="USD",
        )

    def workflow_result(self):
        return run_synthetic_support_case(
            SyntheticSupportCaseInput(
                "case-001", self.message, "customer-001", "ORD-12345",
                "shipment-001", "intake-router", self.now,
            ),
            self.configuration(),
        )

    def test_invalid_output_requires_manual_intake_review_without_workflow(self) -> None:
        result = ExtractionResult(
            ExtractionStatus.INVALID_MODEL_OUTPUT,
            self.message,
            None,
            "schema keys do not match",
            replace(self.trace(), validation_succeeded=False),
        )
        with patch("support_agent.workflow.run_synthetic_support_case") as workflow:
            routed = route_customer_message_extraction(
                result, self.context(), self.configuration()
            )
        self.assertEqual(routed.route, IntakeRoute.MANUAL_INTAKE_REVIEW_REQUIRED)
        self.assertEqual(routed.reason, "schema keys do not match")
        self.assertIsNone(routed.workflow_result)
        self.assertIsNone(routed.extraction)
        workflow.assert_not_called()

    def test_missing_order_requires_clarification_without_workflow(self) -> None:
        reason = "Please provide the order identifier."
        extraction = self.extraction(
            order_identifier=None,
            missing=("order_identifier",),
            clarification_reason=reason,
        )
        result = ExtractionResult(
            ExtractionStatus.NEEDS_CLARIFICATION,
            self.message,
            extraction,
            None,
            self.trace(clarification=True),
        )
        with patch("support_agent.workflow.run_synthetic_support_case") as workflow:
            routed = route_customer_message_extraction(
                result, self.context(), self.configuration()
            )
        self.assertEqual(routed.route, IntakeRoute.CLARIFICATION_REQUIRED)
        self.assertEqual(routed.missing_required_fields, ("order_identifier",))
        self.assertEqual(routed.reason, reason)
        self.assertIsNone(routed.workflow_result)
        workflow.assert_not_called()

    def test_complete_delivered_not_received_enters_existing_workflow_once(self) -> None:
        extraction = self.extraction()
        result = ExtractionResult(
            ExtractionStatus.COMPLETE,
            self.message,
            extraction,
            None,
            self.trace(),
        )
        configuration = self.configuration()
        direct = run_synthetic_support_case(
            SyntheticSupportCaseInput(
                "case-001",
                self.message,
                "customer-001",
                "ORD-12345",
                "shipment-001",
                "intake-router",
                self.now,
            ),
            self.configuration(),
        )
        with patch(
            "support_agent.workflow.run_synthetic_support_case",
            wraps=run_synthetic_support_case,
        ) as workflow:
            routed = route_customer_message_extraction(
                result, self.context(), configuration
            )
        workflow.assert_called_once()
        routed_input = workflow.call_args.args[0]
        self.assertEqual(routed_input.customer_message, extraction.original_message)
        self.assertEqual(routed_input.order_identifier, extraction.order_identifier)
        self.assertEqual(routed_input.customer_identifier, "customer-001")
        self.assertEqual(routed_input.shipment_identifier, "shipment-001")
        self.assertEqual(routed_input.actor, "intake-router")
        self.assertEqual(routed_input.received_at, self.now)
        self.assertEqual(routed.route, IntakeRoute.DELIVERED_NOT_RECEIVED_WORKFLOW)
        self.assertEqual(routed.workflow_result.final_case_status, CaseStatus.CLOSED)
        self.assertEqual(
            routed.workflow_result.final_disposition, Disposition.APPROVE_REFUND
        )
        self.assertEqual(
            routed.workflow_result.final_case_status, direct.final_case_status
        )
        self.assertEqual(
            routed.workflow_result.final_disposition, direct.final_disposition
        )
        self.assertEqual(
            len(routed.workflow_result.case.carrier_evidence_snapshots),
            len(direct.case.carrier_evidence_snapshots),
        )
        self.assertEqual(
            len(routed.workflow_result.case.policy_evaluation_results),
            len(direct.case.policy_evaluation_results),
        )

    def test_order_99999_lookup_not_found_requests_customer_correction(self) -> None:
        message = "My package says delivered but is missing. Order 99999."
        extraction = replace(
            self.extraction(),
            original_message=message,
            order_identifier="99999",
        )
        extraction_result = ExtractionResult(
            ExtractionStatus.COMPLETE,
            message,
            extraction,
            None,
            self.trace(),
        )
        configuration = replace(
            self.configuration(),
            order_lookup=SyntheticOrderLookup(
                OrderReference(
                    "99999",
                    MatchStatus.NOT_FOUND,
                    None,
                    None,
                    None,
                    self.now,
                    RetrievalStatus.SUCCESS,
                )
            ),
        )

        routed = route_customer_message_extraction(
            extraction_result, self.context(), configuration
        )

        self.assertEqual(routed.route, IntakeRoute.DELIVERED_NOT_RECEIVED_WORKFLOW)
        workflow = routed.workflow_result
        self.assertIsNotNone(workflow)
        self.assertFalse(workflow.completed)  # type: ignore[union-attr]
        self.assertEqual(
            workflow.final_case_status,  # type: ignore[union-attr]
            CaseStatus.AWAITING_CUSTOMER_ACTION,
        )
        self.assertEqual(
            workflow.case.customer_report.order_or_tracking_identifier_provided,  # type: ignore[union-attr]
            "99999",
        )
        self.assertIsNone(workflow.case.order_ref)  # type: ignore[union-attr]

    def test_complete_unknown_routes_to_general_triage_without_workflow(self) -> None:
        extraction = self.extraction(issue_type=ExtractionIssueType.UNKNOWN)
        result = ExtractionResult(
            ExtractionStatus.COMPLETE,
            self.message,
            extraction,
            None,
            self.trace(),
        )
        with patch("support_agent.workflow.run_synthetic_support_case") as workflow:
            routed = route_customer_message_extraction(
                result, self.context(), self.configuration()
            )
        self.assertEqual(routed.route, IntakeRoute.GENERAL_TRIAGE_REQUIRED)
        self.assertIs(routed.extraction.issue_type, ExtractionIssueType.UNKNOWN)
        self.assertIsNone(routed.workflow_result)
        workflow.assert_not_called()

    def test_routing_result_invariants_reject_impossible_combinations(self) -> None:
        extraction = self.extraction()
        workflow_result = self.workflow_result()
        invalid_values = (
            dict(route=IntakeRoute.DELIVERED_NOT_RECEIVED_WORKFLOW, extraction=extraction),
            dict(route=IntakeRoute.GENERAL_TRIAGE_REQUIRED, workflow_result=workflow_result),
            dict(route=IntakeRoute.CLARIFICATION_REQUIRED, extraction=extraction),
            dict(route=IntakeRoute.MANUAL_INTAKE_REVIEW_REQUIRED),
            dict(
                route=IntakeRoute.DELIVERED_NOT_RECEIVED_WORKFLOW,
                workflow_result=workflow_result,
                extraction=self.extraction(issue_type=ExtractionIssueType.UNKNOWN),
            ),
        )
        for values in invalid_values:
            with self.subTest(values=values), self.assertRaises(ValueError):
                IntakeRoutingResult(**values)

    def test_workflow_route_rejects_extraction_requiring_clarification(self) -> None:
        extraction = self.extraction(
            order_identifier=None,
            missing=("order_identifier",),
            clarification_reason="Please provide the order identifier.",
        )
        with self.assertRaises(ValueError):
            IntakeRoutingResult(
                IntakeRoute.DELIVERED_NOT_RECEIVED_WORKFLOW,
                workflow_result=self.workflow_result(),
                extraction=extraction,
            )

    def test_workflow_route_rejects_missing_order_identifier(self) -> None:
        extraction = self.extraction(
            order_identifier=None,
            missing=("order_identifier",),
            clarification_reason="Please provide the order identifier.",
        )
        with self.assertRaises(ValueError):
            IntakeRoutingResult(
                IntakeRoute.DELIVERED_NOT_RECEIVED_WORKFLOW,
                workflow_result=self.workflow_result(),
                extraction=extraction,
            )

    def test_general_triage_rejects_extraction_requiring_clarification(self) -> None:
        extraction = self.extraction(
            issue_type=ExtractionIssueType.UNKNOWN,
            order_identifier=None,
            missing=("order_identifier",),
            clarification_reason="Please provide the order identifier.",
        )
        with self.assertRaises(ValueError):
            IntakeRoutingResult(
                IntakeRoute.GENERAL_TRIAGE_REQUIRED,
                extraction=extraction,
            )

    def test_valid_workflow_and_general_triage_results_construct(self) -> None:
        workflow = IntakeRoutingResult(
            IntakeRoute.DELIVERED_NOT_RECEIVED_WORKFLOW,
            workflow_result=self.workflow_result(),
            extraction=self.extraction(),
        )
        general_triage = IntakeRoutingResult(
            IntakeRoute.GENERAL_TRIAGE_REQUIRED,
            extraction=self.extraction(issue_type=ExtractionIssueType.UNKNOWN),
        )

        self.assertIs(workflow.route, IntakeRoute.DELIVERED_NOT_RECEIVED_WORKFLOW)
        self.assertIs(general_triage.route, IntakeRoute.GENERAL_TRIAGE_REQUIRED)

    def test_trusted_context_and_routing_result_are_immutable(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            self.context().actor = "changed"  # type: ignore[misc]
        routed = IntakeRoutingResult(
            IntakeRoute.GENERAL_TRIAGE_REQUIRED,
            extraction=self.extraction(issue_type=ExtractionIssueType.UNKNOWN),
        )
        with self.assertRaises(FrozenInstanceError):
            routed.route = IntakeRoute.CLARIFICATION_REQUIRED  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
