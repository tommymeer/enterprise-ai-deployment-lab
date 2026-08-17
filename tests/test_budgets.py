from dataclasses import FrozenInstanceError, replace
import unittest

from support_agent import (
    BudgetDimension,
    CaseStatus,
    ExecutionBudget,
    FailureInjection,
    FailureKind,
    FailureTarget,
    RetryPolicy,
    run_synthetic_support_case,
)
from support_agent.execution import ExecutionRegistry
from support_agent.failures import FailureInjectingCallable
from support_agent.scenarios import get_support_case_scenario
from support_agent.workflow import (
    SyntheticAddressComparison,
    SyntheticCarrierEvidenceLookup,
    SyntheticCustomerLookup,
    SyntheticHumanReviewer,
    SyntheticOrderLookup,
    SyntheticShipmentLookup,
    WorkflowConfiguration,
)


class BudgetAndRetryTest(unittest.TestCase):
    def configuration(self, scenario_id: str = "refund-success") -> tuple[object, WorkflowConfiguration]:
        scenario = get_support_case_scenario(scenario_id)
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
            scenario.case_input.received_at,
            scenario.unresolved_policies,
            reviewer,
            ExecutionRegistry(),
            proposed_refund_amount_minor=5_000,
            proposed_refund_currency="USD",
            autonomous_refund_limit_minor=10_000,
            autonomous_refund_limit_currency="USD",
        )
        return scenario, configuration

    def injection(
        self,
        target: FailureTarget,
        kind: FailureKind,
        *,
        retryable: bool = True,
        call: int = 1,
    ) -> FailureInjection:
        return FailureInjection(
            f"budget-{target.value}-{kind.value}",
            target,
            kind,
            call,
            f"synthetic {kind.value}",
            retryable,
            CaseStatus.HUMAN_REVIEW if target is FailureTarget.EXECUTION else CaseStatus.INTAKE,
        )

    def execute(self, scenario: object, configuration: WorkflowConfiguration, **kwargs: object):
        return run_synthetic_support_case(
            scenario.case_input, configuration, trace_id="budget-test", **kwargs  # type: ignore[attr-defined,arg-type]
        )

    def test_records_validate_and_are_immutable(self) -> None:
        budget = ExecutionBudget(1, 0, 0, 0)
        policy = RetryPolicy(1, frozenset({FailureKind.TIMEOUT}), 0, 1, 0)
        with self.assertRaises(FrozenInstanceError):
            budget.max_tool_calls = 2  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            policy.max_attempts_per_call = 2  # type: ignore[misc]
        for values in ((-1, 0, 0, 0), (1, -1, 0, 0), (1, 0, -1, 0), (1, 0, 0, -1)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                ExecutionBudget(*values)
        with self.assertRaises(ValueError):
            RetryPolicy(0, frozenset(), 0, 1, 0)
        with self.assertRaises(ValueError):
            RetryPolicy(1, frozenset(), 0, 0.5, 0)
        self.assertEqual(policy.retryable_failure_kinds, frozenset({FailureKind.TIMEOUT}))

    def test_timeout_succeeds_on_second_attempt_with_deterministic_backoff(self) -> None:
        scenario, configuration = self.configuration()
        wrapper = FailureInjectingCallable(
            configuration.customer_lookup,
            self.injection(FailureTarget.CUSTOMER_LOOKUP, FailureKind.TIMEOUT),
        )
        slept: list[float] = []
        policy = RetryPolicy(2, frozenset({FailureKind.TIMEOUT}), 25, 2, 100)
        result = self.execute(
            scenario,
            replace(
                configuration,
                customer_lookup=wrapper,
                retry_policy=policy,
                execution_budget=ExecutionBudget(10, 2, 60_000, 0),
                backoff_sleep=slept.append,
            ),
        )
        self.assertTrue(result.completed)
        self.assertEqual(wrapper.invocation_count, 2)
        self.assertEqual(slept, [0.025])
        self.assertEqual(result.budget_snapshot.retries_used, 1)
        self.assertGreaterEqual(result.budget_snapshot.elapsed_ms, 25)
        retry = next(e for e in result.trace_events if e.event_type == "retry_attempted")
        self.assertEqual(retry.retry_count, 1)
        self.assertIn("backoff_ms=25", next(e.detail for e in result.trace_events if e.event_type == "backoff_applied"))

    def test_rate_limit_retries_but_malformed_result_does_not(self) -> None:
        for kind, retryable, expected_calls, completed in (
            (FailureKind.RATE_LIMIT, True, 2, True),
            (FailureKind.MALFORMED_RESULT, False, 1, False),
        ):
            with self.subTest(kind=kind):
                scenario, configuration = self.configuration()
                wrapper = FailureInjectingCallable(
                    configuration.customer_lookup,
                    self.injection(FailureTarget.CUSTOMER_LOOKUP, kind, retryable=retryable),
                )
                policy = RetryPolicy(2, frozenset({kind}), 0, 1, 0)
                result = self.execute(
                    scenario,
                    replace(
                        configuration,
                        customer_lookup=wrapper,
                        retry_policy=policy,
                        execution_budget=ExecutionBudget(10, 2, 60_000, 0),
                    ),
                )
                self.assertIs(result.completed, completed)
                self.assertEqual(wrapper.invocation_count, expected_calls)

    def test_service_unavailable_exhausts_per_call_attempts(self) -> None:
        scenario, configuration = self.configuration()
        first = FailureInjectingCallable(
            configuration.customer_lookup,
            self.injection(FailureTarget.CUSTOMER_LOOKUP, FailureKind.SERVICE_UNAVAILABLE),
        )
        second = FailureInjectingCallable(
            first,
            self.injection(FailureTarget.CUSTOMER_LOOKUP, FailureKind.SERVICE_UNAVAILABLE, call=2),
        )
        result = self.execute(
            scenario,
            replace(
                configuration,
                customer_lookup=second,
                retry_policy=RetryPolicy(2, frozenset({FailureKind.SERVICE_UNAVAILABLE}), 0, 1, 0),
                execution_budget=ExecutionBudget(10, 2, 60_000, 0),
            ),
        )
        self.assertFalse(result.completed)
        self.assertEqual(result.failure_stage, "customer_lookup_retry")
        self.assertIn("retry_exhausted", [event.event_type for event in result.trace_events])

    def test_total_retry_budget_prevents_retry_and_backoff(self) -> None:
        scenario, configuration = self.configuration()
        wrapper = FailureInjectingCallable(
            configuration.customer_lookup,
            self.injection(FailureTarget.CUSTOMER_LOOKUP, FailureKind.TIMEOUT),
        )
        slept: list[float] = []
        result = self.execute(
            scenario,
            replace(
                configuration,
                customer_lookup=wrapper,
                retry_policy=RetryPolicy(2, frozenset({FailureKind.TIMEOUT}), 10, 1, 10),
                execution_budget=ExecutionBudget(10, 0, 60_000, 0),
                backoff_sleep=slept.append,
            ),
        )
        self.assertEqual(wrapper.invocation_count, 1)
        self.assertEqual(slept, [])
        self.assertEqual(result.budget_snapshot.exhausted_dimension, BudgetDimension.RETRY_ATTEMPTS)

    def test_elapsed_budget_prevents_disallowed_backoff_before_sleep(self) -> None:
        scenario, configuration = self.configuration()
        wrapper = FailureInjectingCallable(
            configuration.customer_lookup,
            self.injection(FailureTarget.CUSTOMER_LOOKUP, FailureKind.TIMEOUT),
        )
        slept: list[float] = []
        times = iter((0.0, 0.0))
        result = self.execute(
            scenario,
            replace(
                configuration,
                customer_lookup=wrapper,
                retry_policy=RetryPolicy(
                    2, frozenset({FailureKind.TIMEOUT}), 10, 1, 10
                ),
                execution_budget=ExecutionBudget(10, 2, 10, 0),
                backoff_sleep=slept.append,
            ),
            timer=lambda: next(times),
        )

        event_types = [event.event_type for event in result.trace_events]
        self.assertFalse(result.completed)
        self.assertEqual(wrapper.invocation_count, 1)
        self.assertEqual(slept, [])
        self.assertEqual(
            result.budget_snapshot.exhausted_dimension,
            BudgetDimension.ELAPSED_MS,
        )
        self.assertIn("budget_exhausted", event_types)
        self.assertIn("workflow_stopped", event_types)
        self.assertNotIn("backoff_applied", event_types)
        self.assertNotIn("retry_attempted", event_types)

    def test_tool_call_budget_stops_downstream_without_invocation(self) -> None:
        scenario, configuration = self.configuration()
        calls = 0

        def order(_: str):
            nonlocal calls
            calls += 1
            return scenario.order_reference

        result = self.execute(
            scenario,
            replace(
                configuration,
                order_lookup=order,
                execution_budget=ExecutionBudget(1, 0, 60_000, 0),
            ),
        )
        self.assertEqual(calls, 0)
        self.assertEqual(result.budget_snapshot.tool_calls_used, 1)
        self.assertEqual(result.budget_snapshot.exhausted_dimension, BudgetDimension.TOOL_CALLS)
        self.assertEqual(result.final_case_status, CaseStatus.INTAKE)

    def test_latency_budget_prevents_next_attempt(self) -> None:
        scenario, configuration = self.configuration()
        times = iter((0.0, 0.010))
        result = self.execute(
            scenario,
            replace(configuration, execution_budget=ExecutionBudget(10, 0, 10, 0)),
            timer=lambda: next(times),
        )
        self.assertFalse(result.completed)
        self.assertEqual(result.budget_snapshot.tool_calls_used, 1)
        self.assertEqual(result.budget_snapshot.exhausted_dimension, BudgetDimension.ELAPSED_MS)

    def test_synthetic_cost_budget_prevents_downstream_call(self) -> None:
        scenario, configuration = self.configuration()
        result = self.execute(
            scenario,
            replace(
                configuration,
                execution_budget=ExecutionBudget(10, 0, 60_000, 0.50),
                tool_estimated_cost_usd={"synthetic_customer_lookup": 0.50, "synthetic_order_lookup": 0.01},
            ),
        )
        self.assertEqual(result.budget_snapshot.tool_calls_used, 1)
        self.assertEqual(result.budget_snapshot.estimated_cost_usd, 0.50)
        self.assertEqual(result.budget_snapshot.exhausted_dimension, BudgetDimension.ESTIMATED_COST_USD)

    def test_execution_timeout_reuses_key_and_succeeds_once(self) -> None:
        scenario, configuration = self.configuration()
        keys: list[str] = []
        delegate = configuration.execution

        def capture(key: str, disposition: object, case: object):
            keys.append(key)
            return delegate(key, disposition, case)  # type: ignore[arg-type]

        wrapper = FailureInjectingCallable(
            capture,
            self.injection(FailureTarget.EXECUTION, FailureKind.TIMEOUT),
        )
        result = self.execute(
            scenario,
            replace(
                configuration,
                execution=wrapper,
                retry_policy=RetryPolicy(2, frozenset({FailureKind.TIMEOUT}), 0, 1, 0),
                execution_budget=ExecutionBudget(10, 2, 60_000, 0),
            ),
        )
        self.assertTrue(result.completed)
        self.assertEqual(wrapper.invocation_count, 2)
        self.assertEqual(keys, [result.execution_operation.idempotency_key])  # type: ignore[union-attr]
        self.assertEqual(result.execution_operation.attempt_count, 2)  # type: ignore[union-attr]
        self.assertEqual(result.budget_snapshot.retries_used, 1)

    def test_execution_retry_exhaustion_routes_to_review(self) -> None:
        scenario, configuration = self.configuration()
        first = FailureInjectingCallable(
            configuration.execution,
            self.injection(FailureTarget.EXECUTION, FailureKind.TIMEOUT),
        )
        second = FailureInjectingCallable(
            first,
            self.injection(FailureTarget.EXECUTION, FailureKind.TIMEOUT, call=2),
        )
        result = self.execute(
            scenario,
            replace(
                configuration,
                execution=second,
                retry_policy=RetryPolicy(2, frozenset({FailureKind.TIMEOUT}), 0, 1, 0),
                execution_budget=ExecutionBudget(10, 2, 60_000, 0),
            ),
        )
        self.assertFalse(result.completed)
        self.assertEqual(result.final_case_status, CaseStatus.HUMAN_REVIEW)
        self.assertEqual(result.execution_operation.attempt_count, 2)  # type: ignore[union-attr]
        self.assertEqual(result.failure_stage, "execution_retry")

    def test_duplicate_success_and_programming_error_do_not_retry(self) -> None:
        scenario, configuration = self.configuration()
        first = self.execute(scenario, configuration)
        duplicate = self.execute(scenario, configuration)
        self.assertEqual(first.execution_operation, duplicate.execution_operation)
        self.assertEqual(duplicate.budget_snapshot.tool_calls_used, 5)

        def broken(_: str):
            raise RuntimeError("programming defect")

        with self.assertRaisesRegex(RuntimeError, "programming defect"):
            self.execute(scenario, replace(configuration, customer_lookup=broken))


if __name__ == "__main__":
    unittest.main()
