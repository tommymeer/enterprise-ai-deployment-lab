from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from inspect import Parameter, signature
import unittest

from support_agent import (
    AddressMatchResult,
    CarrierEvidenceSnapshot,
    CaseStatus,
    CustomerReference,
    Disposition,
    ExecutionResult,
    ExecutionOperation,
    ExecutionRegistry,
    ExecutionStatus,
    FollowUpStatus,
    HumanReviewDecision,
    HumanReviewRequest,
    MatchStatus,
    OrderReference,
    OperationStatus,
    PolicyPlaceholder,
    PolicyRoute,
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
    TransitionRejected,
    WorkflowConfiguration,
    WorkflowResult,
    correct_unmatched_order_identifier,
    generate_idempotency_key,
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

    def order(
        self,
        retrieval: RetrievalStatus = RetrievalStatus.SUCCESS,
        match: MatchStatus = MatchStatus.MATCHED,
    ) -> OrderReference:
        if retrieval is RetrievalStatus.FAILURE or match is not MatchStatus.MATCHED:
            return OrderReference(
                "order-001", match, None, None, None, self.now, retrieval
            )
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
        execution: object | None = None,
        customer: CustomerReference | None = None,
        order: OrderReference | None = None,
        registry: ExecutionRegistry | None = None,
    ) -> WorkflowConfiguration:
        evidence_result = self.evidence() if evidence is ... else evidence
        return WorkflowConfiguration(
            SyntheticCustomerLookup(customer or self.customer()),
            SyntheticOrderLookup(order or self.order()),
            SyntheticShipmentLookup(self.shipment()),
            SyntheticCarrierEvidenceLookup(evidence_result),
            SyntheticAddressComparison(address),
            execution or self.execution(),
            disposition,
            self.now,
            unresolved,
            reviewer,
            registry or ExecutionRegistry(),
            proposed_refund_amount_minor=5_000,
            proposed_refund_currency="USD",
            autonomous_refund_limit_minor=10_000,
            autonomous_refund_limit_currency="USD",
        )

    def test_idempotency_key_uses_only_case_and_executable_disposition(self) -> None:
        refund = generate_idempotency_key("case-001", Disposition.APPROVE_REFUND)
        self.assertEqual(
            refund,
            generate_idempotency_key("case-001", Disposition.APPROVE_REFUND),
        )
        self.assertNotEqual(
            refund,
            generate_idempotency_key("case-001", Disposition.APPROVE_REPLACEMENT),
        )
        self.assertNotEqual(
            refund,
            generate_idempotency_key("case-002", Disposition.APPROVE_REFUND),
        )
        for invalid in (Disposition.DENY, Disposition.REQUEST_MORE_INFO):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                generate_idempotency_key("case-001", invalid)
        with self.assertRaises(ValueError):
            generate_idempotency_key("", Disposition.APPROVE_REFUND)

    def test_refund_authorization_inputs_are_keyword_only(self) -> None:
        parameters = signature(WorkflowConfiguration).parameters
        for field_name in (
            "proposed_refund_amount_minor",
            "proposed_refund_currency",
            "autonomous_refund_limit_minor",
            "autonomous_refund_limit_currency",
        ):
            self.assertEqual(parameters[field_name].kind, Parameter.KEYWORD_ONLY)

    def test_approve_refund_requires_all_authorization_inputs(self) -> None:
        for missing_field in (
            "proposed_refund_amount_minor",
            "proposed_refund_currency",
            "autonomous_refund_limit_minor",
            "autonomous_refund_limit_currency",
        ):
            with self.subTest(missing_field=missing_field):
                with self.assertRaisesRegex(
                    ValueError, "APPROVE_REFUND requires refund authorization inputs"
                ):
                    replace(self.configuration(), **{missing_field: None})

    def test_deny_does_not_require_refund_authorization_inputs(self) -> None:
        configuration = replace(
            self.configuration(),
            selected_disposition=Disposition.DENY,
            proposed_refund_amount_minor=None,
            proposed_refund_currency=None,
            autonomous_refund_limit_minor=None,
            autonomous_refund_limit_currency=None,
        )

        self.assertEqual(configuration.selected_disposition, Disposition.DENY)

    def test_shared_registry_suppresses_duplicate_and_reuses_result(self) -> None:
        registry = ExecutionRegistry()
        calls: list[str] = []

        def execution(
            key: str, disposition: Disposition, case: SupportCase
        ) -> ExecutionResult:
            calls.append(key)
            return ExecutionResult(True, "original refund reference")

        configuration = self.configuration(execution=execution, registry=registry)
        first = run_synthetic_support_case(self.case_input(), configuration)
        duplicate = run_synthetic_support_case(self.case_input(), configuration)
        self.assertEqual(len(calls), 1)
        self.assertEqual(first.execution_operation, duplicate.execution_operation)
        self.assertEqual(
            duplicate.execution_operation.result_detail,  # type: ignore[union-attr]
            "original refund reference",
        )
        event = next(
            e
            for e in duplicate.trace_events
            if e.event_type == "duplicate_execution_suppressed"
        )
        self.assertEqual(event.detail, "execution adapter was not called")
        self.assertIn(
            "prior_successful_result_reused",
            [e.event_type for e in duplicate.trace_events],
        )

    def test_failed_attempt_can_retry_then_success_is_suppressed(self) -> None:
        registry = ExecutionRegistry()
        calls = 0

        def execution(
            key: str, disposition: Disposition, case: SupportCase
        ) -> ExecutionResult:
            nonlocal calls
            calls += 1
            return ExecutionResult(calls > 1, f"attempt {calls}")

        configuration = self.configuration(execution=execution, registry=registry)
        failed = run_synthetic_support_case(self.case_input(), configuration)
        succeeded = run_synthetic_support_case(self.case_input(), configuration)
        suppressed = run_synthetic_support_case(self.case_input(), configuration)
        self.assertEqual(
            failed.execution_operation.status,  # type: ignore[union-attr]
            OperationStatus.FAILED,
        )
        self.assertEqual(
            succeeded.execution_operation.status,  # type: ignore[union-attr]
            OperationStatus.SUCCEEDED,
        )
        self.assertEqual(
            succeeded.execution_operation.attempt_count, 2  # type: ignore[union-attr]
        )
        self.assertEqual(
            failed.execution_operation.idempotency_key,  # type: ignore[union-attr]
            succeeded.execution_operation.idempotency_key,  # type: ignore[union-attr]
        )
        self.assertEqual(calls, 2)
        self.assertEqual(suppressed.execution_operation, succeeded.execution_operation)
        self.assertIn(
            "later_retry_attempted", [e.event_type for e in succeeded.trace_events]
        )
        self.assertIn(
            "failed_operation_recorded", [e.event_type for e in failed.trace_events]
        )

    def test_carrier_inquiry_is_idempotent(self) -> None:
        registry = ExecutionRegistry()
        calls = 0

        def execution(
            key: str, disposition: Disposition, case: SupportCase
        ) -> ExecutionResult:
            nonlocal calls
            calls += 1
            return ExecutionResult(True, "carrier inquiry reference")

        configuration = self.configuration(
            disposition=Disposition.OPEN_CARRIER_INQUIRY,
            execution=execution,
            registry=registry,
        )
        run_synthetic_support_case(self.case_input(), configuration)
        duplicate = run_synthetic_support_case(self.case_input(), configuration)
        self.assertEqual(calls, 1)
        self.assertEqual(
            duplicate.final_case_status, CaseStatus.AWAITING_EXTERNAL_FOLLOW_UP
        )

    def test_non_executable_dispositions_have_no_operation(self) -> None:
        for disposition in (
            Disposition.DENY,
            Disposition.REQUEST_MORE_INFO,
            Disposition.ADVISE_SELF_CHECK_OR_WAIT,
        ):
            with self.subTest(disposition=disposition):
                result = run_synthetic_support_case(
                    self.case_input(), self.configuration(disposition=disposition)
                )
                self.assertIsNone(result.execution_operation)

    def test_registry_rejects_wrong_identity_and_public_records_are_read_only(self) -> None:
        registry = ExecutionRegistry()
        key = generate_idempotency_key("case-001", Disposition.APPROVE_REFUND)
        operation, _ = registry.get_or_create(
            key, "case-001", Disposition.APPROVE_REFUND, self.now
        )
        with self.assertRaises(ValueError):
            registry.get_or_create(
                key, "case-002", Disposition.APPROVE_REFUND, self.now
            )
        with self.assertRaises(ValueError):
            registry.get_or_create(
                key, "case-001", Disposition.APPROVE_REPLACEMENT, self.now
            )
        with self.assertRaises(FrozenInstanceError):
            operation.status = OperationStatus.FAILED  # type: ignore[misc]
        with self.assertRaises(TypeError):
            registry.operations[key] = operation  # type: ignore[index]

    def test_execution_operation_rejects_invalid_values(self) -> None:
        valid = dict(
            operation_id="operation",
            idempotency_key=generate_idempotency_key(
                "case", Disposition.APPROVE_REFUND
            ),
            case_id="case",
            disposition=Disposition.APPROVE_REFUND,
            requested_at=self.now,
            status=OperationStatus.NOT_STARTED,
            result_detail=None,
            attempt_count=0,
        )
        for change in (
            {"operation_id": ""},
            {"idempotency_key": ""},
            {"idempotency_key": "inconsistent-key"},
            {"case_id": ""},
            {"disposition": Disposition.DENY},
            {"requested_at": datetime(2026, 7, 28)},
            {"status": "failed"},
            {"attempt_count": -1},
            {"status": OperationStatus.IN_PROGRESS, "attempt_count": 0},
            {"status": OperationStatus.SUCCEEDED, "attempt_count": 1},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                ExecutionOperation(**(valid | change))  # type: ignore[arg-type]

    def test_workflow_result_rejects_mismatched_execution_operation_identity(self) -> None:
        result = run_synthetic_support_case(self.case_input(), self.configuration())
        operation = result.execution_operation
        self.assertIsNotNone(operation)

        other_case_operation = replace(
            operation,
            case_id="case-002",
            idempotency_key=generate_idempotency_key(
                "case-002", Disposition.APPROVE_REFUND
            ),
        )
        with self.assertRaises(ValueError):
            replace(result, execution_operation=other_case_operation)

        other_disposition_operation = replace(
            operation,
            disposition=Disposition.APPROVE_REPLACEMENT,
            idempotency_key=generate_idempotency_key(
                "case-001", Disposition.APPROVE_REPLACEMENT
            ),
        )
        with self.assertRaises(ValueError):
            replace(result, execution_operation=other_disposition_operation)

        corrupted_key_operation = replace(operation)
        object.__setattr__(corrupted_key_operation, "idempotency_key", "corrupt-key")
        with self.assertRaises(ValueError):
            replace(result, execution_operation=corrupted_key_operation)

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

        def execution(
            key: str, disposition: Disposition, case: SupportCase
        ) -> ExecutionResult:
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

    def test_refund_above_autonomous_limit_routes_to_review_without_execution(self) -> None:
        calls = 0

        def execution(
            key: str, disposition: Disposition, case: SupportCase
        ) -> ExecutionResult:
            nonlocal calls
            calls += 1
            return ExecutionResult(True, "synthetic refund result")

        configuration = self.configuration(
            disposition=Disposition.APPROVE_REFUND,
            execution=execution,
        )
        configuration = replace(
            configuration,
            proposed_refund_amount_minor=15_000,
            proposed_refund_currency="USD",
            autonomous_refund_limit_minor=10_000,
            autonomous_refund_limit_currency="USD",
        )

        result = run_synthetic_support_case(self.case_input(), configuration)
        event_types = [event.event_type for event in result.trace_events]

        self.assertEqual(
            result.case.policy_evaluation_results[-1].route,
            PolicyRoute.PROCEED_TO_DISPOSITION,
        )
        self.assertEqual(result.final_disposition, Disposition.APPROVE_REFUND)
        self.assertEqual(result.final_case_status, CaseStatus.HUMAN_REVIEW)
        self.assertFalse(result.completed)
        self.assertEqual(
            result.failure_reason,
            "proposed refund exceeds autonomous refund limit",
        )
        self.assertEqual(result.case.execution_status, ExecutionStatus.NOT_STARTED)
        self.assertIsNone(result.case.closed_at)
        self.assertIsNone(result.execution_operation)
        self.assertEqual(calls, 0)
        self.assertIn("execution_authority_blocked", event_types)
        blocked = next(
            event
            for event in result.trace_events
            if event.event_type == "execution_authority_blocked"
        )
        self.assertEqual(blocked.step, "authority")
        self.assertEqual(
            blocked.detail,
            "refund_amount_minor=15000; currency=USD; autonomous_limit_minor=10000",
        )
        self.assertNotIn("execution_operation_created", event_types)
        self.assertNotIn("execution_started", event_types)
        self.assertNotIn("execution_adapter_invoked", event_types)
        self.assertFalse(
            any(
                event.event_type == "tool_called"
                and event.tool_name == "synthetic_execution_adapter"
                for event in result.trace_events
            )
        )

    def test_refund_at_or_below_autonomous_limit_executes(self) -> None:
        for amount in (10_000, 5_000):
            with self.subTest(amount=amount):
                calls = 0

                def execution(
                    key: str, disposition: Disposition, case: SupportCase
                ) -> ExecutionResult:
                    nonlocal calls
                    calls += 1
                    return ExecutionResult(True, "synthetic refund result")

                configuration = replace(
                    self.configuration(
                        disposition=Disposition.APPROVE_REFUND,
                        execution=execution,
                    ),
                    proposed_refund_amount_minor=amount,
                    autonomous_refund_limit_minor=10_000,
                )

                result = run_synthetic_support_case(
                    self.case_input(), configuration
                )

                self.assertTrue(result.completed)
                self.assertEqual(result.final_case_status, CaseStatus.CLOSED)
                self.assertEqual(
                    result.case.execution_status, ExecutionStatus.SUCCEEDED
                )
                self.assertEqual(calls, 1)

    def test_refund_currency_mismatch_routes_to_review_without_execution(self) -> None:
        calls = 0

        def execution(
            key: str, disposition: Disposition, case: SupportCase
        ) -> ExecutionResult:
            nonlocal calls
            calls += 1
            return ExecutionResult(True, "synthetic refund result")

        configuration = replace(
            self.configuration(
                disposition=Disposition.APPROVE_REFUND,
                execution=execution,
            ),
            proposed_refund_amount_minor=5_000,
            proposed_refund_currency="USD",
            autonomous_refund_limit_minor=10_000,
            autonomous_refund_limit_currency="EUR",
        )

        result = run_synthetic_support_case(self.case_input(), configuration)

        self.assertFalse(result.completed)
        self.assertEqual(
            result.failure_reason,
            "refund currency does not match autonomous refund limit currency",
        )
        self.assertEqual(result.final_case_status, CaseStatus.HUMAN_REVIEW)
        self.assertEqual(result.case.execution_status, ExecutionStatus.NOT_STARTED)
        self.assertIsNone(result.execution_operation)
        self.assertEqual(calls, 0)
        blocked = next(
            event
            for event in result.trace_events
            if event.event_type == "execution_authority_blocked"
        )
        self.assertIn("currency=USD", blocked.detail or "")
        self.assertIn("autonomous_limit_currency=EUR", blocked.detail or "")

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

    def test_order_not_found_requests_customer_correction_without_downstream_work(self) -> None:
        supplied_identifier = self.case_input().order_identifier
        result = run_synthetic_support_case(
            self.case_input(),
            self.configuration(order=self.order(match=MatchStatus.NOT_FOUND)),
        )

        self.assertFalse(result.completed)
        self.assertEqual(
            result.final_case_status, CaseStatus.AWAITING_CUSTOMER_ACTION
        )
        self.assertEqual(result.final_disposition, Disposition.NONE_SELECTED)
        self.assertEqual(result.failure_stage, "order_lookup")
        self.assertIn("could not be matched", result.failure_reason or "")
        self.assertEqual(
            result.case.customer_report.order_or_tracking_identifier_provided,
            supplied_identifier,
        )
        self.assertIsNone(result.case.order_ref)
        self.assertEqual(result.case.shipment_refs, ())
        self.assertEqual(result.case.carrier_evidence_snapshots, ())
        self.assertEqual(result.case.policy_evaluation_results, ())
        self.assertEqual(result.case.execution_status, ExecutionStatus.NOT_APPLICABLE)
        self.assertIsNone(result.case.closed_at)
        self.assertNotIn(
            "evidence_gathering_entered",
            [event.event_type for event in result.trace_events],
        )

    def test_failed_order_retrieval_remains_intake_failed(self) -> None:
        result = run_synthetic_support_case(
            self.case_input(),
            self.configuration(
                order=self.order(
                    RetrievalStatus.FAILURE, MatchStatus.NOT_FOUND
                )
            ),
        )

        self.assertFalse(result.completed)
        self.assertEqual(result.final_case_status, CaseStatus.INTAKE_FAILED)
        self.assertEqual(result.failure_stage, "order_lookup")
        self.assertEqual(result.failure_reason, "retrieval failed")

    def test_order_99999_correction_relinks_and_resumes_existing_workflow(self) -> None:
        original_input = replace(
            self.case_input(),
            customer_message=(
                "My package says delivered but is missing. Order 99999."
            ),
            order_identifier="99999",
        )
        stopped = run_synthetic_support_case(
            original_input,
            self.configuration(order=self.order(match=MatchStatus.NOT_FOUND)),
        )

        resumed = correct_unmatched_order_identifier(
            stopped,
            original_input,
            "order-001",
            self.configuration(),
        )

        self.assertIs(resumed.case, stopped.case)
        self.assertTrue(resumed.completed)
        self.assertEqual(resumed.final_case_status, CaseStatus.CLOSED)
        self.assertIsNotNone(resumed.case.customer_ref)
        self.assertIsNotNone(resumed.case.order_ref)
        audit_transitions = [
            event.after_state.case_status for event in resumed.case.audit_events
        ]
        self.assertIn(CaseStatus.LINKED, audit_transitions)
        self.assertIn(CaseStatus.EVIDENCE_GATHERING, audit_transitions)
        self.assertEqual(
            resumed.case.customer_report.order_or_tracking_identifier_provided,
            "99999",
        )
        self.assertTrue(
            any(
                event.tool_arguments.get("order_id") == "99999"
                for event in resumed.trace_events
            )
        )
        self.assertTrue(
            any(
                event.event_type == "order_identifier_correction_recorded"
                and event.detail == "corrected_order_identifier=order-001"
                for event in resumed.trace_events
            )
        )
        self.assertTrue(
            any(
                event.event_type == "order_identifier_correction_recorded"
                and "corrected_order_identifier=order-001" in (event.detail or "")
                for event in resumed.case.audit_events
            )
        )

    def test_second_unmatched_order_correction_remains_awaiting_without_policy(self) -> None:
        original_input = replace(self.case_input(), order_identifier="99999")
        not_found_configuration = self.configuration(
            order=self.order(match=MatchStatus.NOT_FOUND)
        )
        stopped = run_synthetic_support_case(
            original_input,
            not_found_configuration,
        )

        repeated = correct_unmatched_order_identifier(
            stopped,
            original_input,
            "88888",
            not_found_configuration,
        )

        self.assertFalse(repeated.completed)
        self.assertEqual(
            repeated.final_case_status, CaseStatus.AWAITING_CUSTOMER_ACTION
        )
        self.assertIsNone(repeated.case.order_ref)
        self.assertEqual(repeated.case.policy_evaluation_results, ())
        self.assertEqual(repeated.final_disposition, Disposition.NONE_SELECTED)
        self.assertEqual(repeated.case.execution_status, ExecutionStatus.NOT_APPLICABLE)
        self.assertNotIn(
            "evidence_gathering_entered",
            [event.event_type for event in repeated.trace_events],
        )

    def test_corrected_order_retrieval_failure_does_not_link_or_progress(self) -> None:
        original_input = replace(self.case_input(), order_identifier="99999")
        stopped = run_synthetic_support_case(
            original_input,
            self.configuration(order=self.order(match=MatchStatus.NOT_FOUND)),
        )

        failed = correct_unmatched_order_identifier(
            stopped,
            original_input,
            "order-001",
            self.configuration(
                order=self.order(RetrievalStatus.FAILURE, MatchStatus.NOT_FOUND)
            ),
        )

        self.assertFalse(failed.completed)
        self.assertEqual(failed.failure_reason, "retrieval failed")
        self.assertEqual(
            failed.final_case_status, CaseStatus.AWAITING_CUSTOMER_ACTION
        )
        self.assertIsNone(failed.case.order_ref)
        self.assertEqual(failed.case.policy_evaluation_results, ())
        self.assertEqual(failed.final_disposition, Disposition.NONE_SELECTED)
        self.assertEqual(failed.case.execution_status, ExecutionStatus.NOT_APPLICABLE)

    def test_mismatched_corrected_order_is_rejected_before_downstream_work(self) -> None:
        original_input = replace(self.case_input(), order_identifier="99999")
        stopped = run_synthetic_support_case(
            original_input,
            self.configuration(order=self.order(match=MatchStatus.NOT_FOUND)),
        )

        def unexpected_downstream_call(*args: object) -> object:
            self.fail("downstream work must not run after an identifier mismatch")

        configuration = self.configuration(order=self.order())
        configuration = replace(
            configuration,
            shipment_lookup=unexpected_downstream_call,
            carrier_evidence_lookup=unexpected_downstream_call,
            address_comparison=unexpected_downstream_call,
            execution=unexpected_downstream_call,
        )

        with self.assertRaisesRegex(
            TransitionRejected,
            "matched order identifier must equal the corrected identifier",
        ):
            correct_unmatched_order_identifier(
                stopped,
                original_input,
                "order-999",
                configuration,
            )

        self.assertEqual(
            stopped.case.case_status, CaseStatus.AWAITING_CUSTOMER_ACTION
        )
        self.assertIsNone(stopped.case.order_ref)
        self.assertEqual(stopped.case.shipment_refs, ())
        self.assertEqual(stopped.case.carrier_evidence_snapshots, ())
        self.assertEqual(stopped.case.policy_evaluation_results, ())
        self.assertEqual(stopped.case.disposition, Disposition.NONE_SELECTED)
        self.assertEqual(
            stopped.case.execution_status, ExecutionStatus.NOT_APPLICABLE
        )

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
        for disposition, succeeded in (
            (Disposition.APPROVE_REFUND, True),
            (Disposition.APPROVE_REPLACEMENT, False),
            (Disposition.OPEN_CARRIER_INQUIRY, True),
        ):
            with self.subTest(disposition=disposition):
                case = run_synthetic_support_case(
                    self.case_input(), self.configuration(disposition=disposition)
                ).case
                key = generate_idempotency_key(case.case_id, disposition)
                self.assertIs(adapter(key, disposition, case).succeeded, succeeded)

    def test_execution_adapter_rejects_inconsistent_identity(self) -> None:
        adapter = self.execution()
        case = run_synthetic_support_case(
            self.case_input(), self.configuration()
        ).case
        with self.assertRaises(ValueError):
            adapter("wrong-key", Disposition.APPROVE_REFUND, case)
        replacement_key = generate_idempotency_key(
            case.case_id, Disposition.APPROVE_REPLACEMENT
        )
        with self.assertRaises(ValueError):
            adapter(replacement_key, Disposition.APPROVE_REPLACEMENT, case)


if __name__ == "__main__":
    unittest.main()
