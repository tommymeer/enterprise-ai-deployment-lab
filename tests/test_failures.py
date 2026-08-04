from dataclasses import FrozenInstanceError, replace
import unittest

from support_agent import (
    CaseStatus,
    FailureInjection,
    FailureKind,
    FailureTarget,
    SyntheticOperationalError,
    WorkflowConfiguration,
    WorkflowResult,
    evaluate_failure_regression_case,
    get_failure_regression_case,
    get_failure_regression_cases,
    run_failure_regression_case,
)
from support_agent.failures import FailureInjectingCallable
from support_agent.execution import OperationStatus
from support_agent.scenarios import get_support_case_scenario, run_support_case_scenario


class FailureInjectionTest(unittest.TestCase):
    def injection(self, *, call: int = 2) -> FailureInjection:
        return FailureInjection(
            "injection-1", FailureTarget.CUSTOMER_LOOKUP, FailureKind.TIMEOUT,
            call, "synthetic timeout", True, CaseStatus.INTAKE,
        )

    def test_records_reject_invalid_values_and_are_immutable(self) -> None:
        valid = self.injection()
        for field, value in (("injection_id", " "), ("detail", ""), ("trigger_on_call", 0),
                             ("retryable", 1), ("target", "customer_lookup"),
                             ("kind", "timeout"), ("expected_safe_route", "intake")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(valid, **{field: value})
        with self.assertRaises(FrozenInstanceError):
            valid.detail = "changed"  # type: ignore[misc]

    def test_execution_only_failure_kinds_reject_callable_targets(self) -> None:
        for kind in (
            FailureKind.EXECUTION_FAILURE,
            FailureKind.EXECUTION_EXCEPTION,
        ):
            with self.subTest(kind=kind), self.assertRaisesRegex(
                ValueError, f"{kind.value} requires target execution"
            ):
                replace(self.injection(), kind=kind)

    def test_wrapper_triggers_exact_call_and_delegates_before_and_after(self) -> None:
        calls: list[str] = []
        wrapper = FailureInjectingCallable(lambda value: calls.append(value) or value, self.injection())
        self.assertEqual(wrapper("first"), "first")
        with self.assertRaises(SyntheticOperationalError):
            wrapper("second")
        self.assertEqual(wrapper("third"), "third")
        self.assertEqual(wrapper.invocation_count, 3)
        self.assertEqual(calls, ["first", "third"])

    def test_all_curated_regressions_pass_and_are_read_only(self) -> None:
        cases = get_failure_regression_cases()
        self.assertEqual(len(cases), 10)
        self.assertIsInstance(cases, tuple)
        failures = {}
        for case in cases:
            evaluation = evaluate_failure_regression_case(run_failure_regression_case(case))
            if not evaluation.passed:
                failures[case.regression_id] = evaluation.failure_messages
            self.assertIsInstance(evaluation.checks, tuple)
            self.assertIsInstance(evaluation.failure_messages, tuple)
        self.assertEqual(failures, {})
        with self.assertRaises(FrozenInstanceError):
            cases[0].notes = "changed"  # type: ignore[misc]

    def test_safe_stops_exclude_downstream_events(self) -> None:
        for identifier in ("customer-timeout", "order-unavailable", "carrier-timeout",
                           "address-malformed", "review-unavailable"):
            case = get_failure_regression_case(identifier)
            run = run_failure_regression_case(case)
            self.assertIsInstance(run.workflow_result, WorkflowResult)
            self.assertNotIsInstance(
                run.workflow_result, SyntheticOperationalError
            )
            names = {event.event_type for event in run.workflow_result.trace_events}
            self.assertIn("modeled_operational_failure", names)
            self.assertIn("workflow_stopped", names)
            self.assertTrue(set(case.expected_forbidden_trace_events).isdisjoint(names))

    def test_execution_result_and_exception_remain_distinct(self) -> None:
        normal = run_failure_regression_case(get_failure_regression_case("execution-result-failure"))
        raised = run_failure_regression_case(get_failure_regression_case("execution-timeout"))
        normal_events = {event.event_type for event in normal.workflow_result.trace_events}
        raised_events = {event.event_type for event in raised.workflow_result.trace_events}
        self.assertNotIn("modeled_operational_failure", normal_events)
        self.assertIn("modeled_operational_failure", raised_events)
        self.assertNotIn("successful_operation_recorded", raised_events)
        self.assertIsNotNone(raised.workflow_result.execution_operation)
        self.assertIs(
            raised.workflow_result.execution_operation.status,  # type: ignore[union-attr]
            OperationStatus.FAILED,
        )

    def test_shared_registry_suppresses_injected_duplicate_call(self) -> None:
        run = run_failure_regression_case(get_failure_regression_case("duplicate-suppresses-injection"))
        names = {event.event_type for event in run.workflow_result.trace_events}
        self.assertEqual(run.adapter_invocations, 1)
        self.assertIn("duplicate_execution_suppressed", names)
        self.assertNotIn("modeled_operational_failure", names)

    def test_unexpected_programming_exception_propagates(self) -> None:
        def broken(_: object) -> object:
            raise RuntimeError("programming defect")
        wrapper = FailureInjectingCallable(broken, self.injection(call=2))
        with self.assertRaisesRegex(RuntimeError, "programming defect"):
            wrapper("first")

        def transform(
            configuration: WorkflowConfiguration,
        ) -> WorkflowConfiguration:
            def broken_lookup(_: str) -> object:
                raise RuntimeError("workflow programming defect")
            return replace(configuration, customer_lookup=broken_lookup)

        with self.assertRaisesRegex(RuntimeError, "workflow programming defect"):
            run_support_case_scenario(
                get_support_case_scenario("refund-success"),
                configuration_transform=transform,
            )


if __name__ == "__main__":
    unittest.main()
