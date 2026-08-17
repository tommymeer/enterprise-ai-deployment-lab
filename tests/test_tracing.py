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
    WorkflowTraceCollector,
    WorkflowTraceEvent,
    run_synthetic_support_case,
)


class TracingTest(unittest.TestCase):
    now = datetime(2026, 8, 4, 12, tzinfo=UTC)
    raw_message = "RAW PRIVATE CUSTOMER MESSAGE"
    full_address = "9876 Private Full Address, Secret City"

    def case_input(self) -> SyntheticSupportCaseInput:
        return SyntheticSupportCaseInput(
            "case-trace",
            self.raw_message,
            "customer-trace",
            "order-trace",
            "shipment-trace",
            "support-agent",
            self.now,
        )

    def configuration(
        self,
        *,
        customer: CustomerReference | None = None,
        evidence: CarrierEvidenceSnapshot | None = ...,
        disposition: Disposition = Disposition.APPROVE_REFUND,
        reviewer: SyntheticHumanReviewer | None = None,
        unresolved: tuple[PolicyPlaceholder, ...] = (),
    ) -> WorkflowConfiguration:
        customer_result = customer or CustomerReference(
            "customer-trace", MatchStatus.MATCHED, self.now, RetrievalStatus.SUCCESS
        )
        order = OrderReference(
            "order-trace",
            MatchStatus.MATCHED,
            "25.00 USD",
            "synthetic_item",
            self.full_address,
            self.now,
            RetrievalStatus.SUCCESS,
        )
        shipment = ShipmentReference(
            "shipment-trace",
            "Synthetic Carrier",
            "tracking-trace",
            self.now,
            self.now,
            RetrievalStatus.SUCCESS,
        )
        default_evidence = CarrierEvidenceSnapshot(
            "evidence-trace",
            "shipment-trace",
            "delivered",
            self.now,
            ("delivered",),
            True,
            self.now,
            RetrievalStatus.SUCCESS,
        )
        evidence_result = default_evidence if evidence is ... else evidence
        execution = SyntheticExecutionAdapter(
            ExecutionResult(True, "refund recorded"),
            ExecutionResult(True, "replacement recorded"),
            ExecutionResult(True, "inquiry recorded"),
        )
        return WorkflowConfiguration(
            SyntheticCustomerLookup(customer_result),
            SyntheticOrderLookup(order),
            SyntheticShipmentLookup(shipment),
            SyntheticCarrierEvidenceLookup(evidence_result),
            SyntheticAddressComparison(AddressMatchResult.MATCH),
            execution,
            disposition,
            self.now,
            unresolved,
            reviewer,
            proposed_refund_amount_minor=5_000,
            proposed_refund_currency="USD",
            autonomous_refund_limit_minor=10_000,
            autonomous_refund_limit_currency="USD",
        )

    def execute(self, **kwargs: object) -> WorkflowResult:
        return run_synthetic_support_case(
            self.case_input(), self.configuration(**kwargs), trace_id="trace-fixed"
        )

    def test_trace_id_is_generated_and_caller_value_is_preserved(self) -> None:
        generated = run_synthetic_support_case(self.case_input(), self.configuration())
        supplied = self.execute()
        self.assertTrue(generated.trace_id)
        self.assertEqual(supplied.trace_id, "trace-fixed")
        self.assertTrue(all(e.trace_id == supplied.trace_id for e in supplied.trace_events))

    def test_sequence_is_ordered_contiguous_and_success_has_major_events(self) -> None:
        result = self.execute()
        self.assertEqual(
            [event.sequence_number for event in result.trace_events],
            list(range(len(result.trace_events))),
        )
        types = [event.event_type for event in result.trace_events]
        expected = [
            "workflow_started",
            "customer_report_recorded",
            "linkage_completed",
            "shipment_attached",
            "evidence_gathering_entered",
            "carrier_evidence_attached",
            "policy_evaluation_completed",
            "policy_route_recorded",
            "disposition_selected",
            "execution_started",
            "execution_result_recorded",
            "execution_completed",
            "workflow_completed",
        ]
        positions = [types.index(name) for name in expected]
        self.assertEqual(positions, sorted(positions))

    def test_lookup_failure_stops_at_intake_without_downstream_calls(self) -> None:
        failed = CustomerReference(
            "customer-trace",
            MatchStatus.NOT_FOUND,
            self.now,
            RetrievalStatus.FAILURE,
        )
        result = self.execute(customer=failed)
        types = [event.event_type for event in result.trace_events]
        steps = [event.step for event in result.trace_events]
        self.assertEqual(types[-2:], ["intake_failed", "workflow_stopped"])
        self.assertNotIn("order_lookup", steps)
        self.assertNotIn("shipment_lookup", steps)

    def test_missing_evidence_differs_from_failed_retrieval(self) -> None:
        missing = self.execute(evidence=None)
        failed_evidence = CarrierEvidenceSnapshot(
            "evidence-failed",
            "shipment-trace",
            None,
            None,
            (),
            None,
            self.now,
            RetrievalStatus.FAILURE,
        )
        reviewer = SyntheticHumanReviewer(
            HumanReviewRequest(
                "review-trace", self.now, "review failure", (), ("evidence-failed",)
            ),
            HumanReviewDecision(
                "review-trace", self.now, "reviewer", Disposition.DENY, "deny"
            ),
        )
        failed = self.execute(evidence=failed_evidence, reviewer=reviewer)
        self.assertIn(
            "carrier_evidence_missing", [e.event_type for e in missing.trace_events]
        )
        attached = [
            e for e in failed.trace_events if e.event_type == "carrier_evidence_attached"
        ]
        self.assertEqual(attached[0].detail, "retrieval_failed")

    def test_human_review_decision_is_one_state_changing_trace_event(self) -> None:
        policy = PolicyPlaceholder.FRONTLINE_REFUND_AUTHORITY
        reviewer = SyntheticHumanReviewer(
            HumanReviewRequest("review-trace", self.now, "authority", (policy,), ()),
            HumanReviewDecision(
                "review-trace", self.now, "reviewer", Disposition.DENY, "deny"
            ),
        )
        reviewed = self.execute(unresolved=(policy,), reviewer=reviewer)
        review_types = [e.event_type for e in reviewed.trace_events]
        self.assertIn("human_review_opened", review_types)
        decisions = [
            event
            for event in reviewed.trace_events
            if event.event_type == "human_review_decided"
        ]
        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.state_before.case_status, CaseStatus.HUMAN_REVIEW)
        self.assertEqual(decision.state_after.case_status, CaseStatus.CLOSED)
        self.assertEqual(decision.state_after.disposition, Disposition.DENY)
        self.assertTrue(decision.escalation)
        self.assertTrue(decision.human_override)
        self.assertEqual(decision.final_outcome, Disposition.DENY.value)
        self.assertNotIn("disposition_selected", review_types)

    def test_non_human_disposition_and_carrier_follow_up_are_traced(self) -> None:
        normal = self.execute()
        selected = [
            event
            for event in normal.trace_events
            if event.event_type == "disposition_selected"
        ]
        self.assertEqual(len(selected), 1)
        self.assertNotEqual(selected[0].state_before, selected[0].state_after)

        inquiry = self.execute(disposition=Disposition.OPEN_CARRIER_INQUIRY)
        self.assertEqual(inquiry.final_case_status, CaseStatus.AWAITING_EXTERNAL_FOLLOW_UP)
        self.assertEqual(inquiry.trace_events[-2].event_type, "external_follow_up_entered")
        self.assertEqual(inquiry.trace_events[-1].final_outcome, "awaiting_external_follow_up")

    def test_state_changes_have_before_and_after_snapshots(self) -> None:
        result = self.execute()
        linkage = next(e for e in result.trace_events if e.event_type == "linkage_completed")
        execution = next(e for e in result.trace_events if e.event_type == "execution_started")
        self.assertEqual(linkage.state_before.case_status, CaseStatus.INTAKE)
        self.assertEqual(linkage.state_after.case_status, CaseStatus.LINKED)
        self.assertNotEqual(execution.state_before, execution.state_after)

    def test_tool_records_are_sanitized_timed_and_model_fields_are_empty(self) -> None:
        times = iter(float(value) for value in range(20))
        result = run_synthetic_support_case(
            self.case_input(),
            self.configuration(),
            trace_id="timed",
            clock=lambda: self.now,
            timer=lambda: next(times),
        )
        returned = [e for e in result.trace_events if e.event_type == "tool_returned"]
        self.assertTrue(returned)
        for event in returned:
            self.assertTrue(event.tool_name)
            self.assertTrue(event.tool_arguments)
            self.assertTrue(event.tool_result)
            self.assertEqual(event.latency_ms, 1000.0)
            self.assertEqual(event.retry_count, 0)
        for event in result.trace_events:
            self.assertIsNone(event.model_provider)
            self.assertIsNone(event.model_name)
            self.assertIsNone(event.prompt_version)
            self.assertIsNone(event.input_tokens)
            self.assertIsNone(event.output_tokens)
            self.assertIsNone(event.estimated_cost_usd)
            serialized = repr(event)
            self.assertNotIn(self.raw_message, serialized)
            self.assertNotIn(self.full_address, serialized)

    def test_records_collections_and_tool_mappings_are_immutable(self) -> None:
        result = self.execute()
        event = next(e for e in result.trace_events if e.event_type == "tool_returned")
        with self.assertRaises(FrozenInstanceError):
            event.step = "changed"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            event.tool_result["changed"] = True  # type: ignore[index]
        with self.assertRaises(TypeError):
            result.trace_events[0] = event  # type: ignore[index]

    def test_invalid_event_and_collector_values_are_rejected(self) -> None:
        snapshot = SupportCase("validation-case").snapshot()
        valid = dict(
            trace_id="trace",
            sequence_number=0,
            occurred_at=self.now,
            step="step",
            event_type="event",
            case_id="case",
        )
        for change in (
            {"trace_id": ""},
            {"step": ""},
            {"event_type": ""},
            {"case_id": ""},
            {"sequence_number": -1},
            {"occurred_at": datetime(2026, 8, 4)},
            {"latency_ms": -0.1},
            {"retry_count": -1},
            {"input_tokens": -1},
            {"output_tokens": -1},
            {"estimated_cost_usd": -0.01},
            {"state_before": "not a snapshot"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                WorkflowTraceEvent(**(valid | change))  # type: ignore[arg-type]
        collector = WorkflowTraceCollector("trace")
        with self.assertRaises(ValueError):
            WorkflowTraceCollector("")
        with self.assertRaises(ValueError):
            collector.append(
                trace_id="other",
                occurred_at=self.now,
                step="step",
                event_type="event",
                case_id="case",
            )
        event = WorkflowTraceEvent(**valid, state_before=snapshot)
        case = SupportCase("case")
        with self.assertRaises(ValueError):
            WorkflowResult(
                case,
                True,
                case.case_status,
                case.disposition,
                trace_id="other",
                trace_events=(event,),
            )


if __name__ == "__main__":
    unittest.main()
