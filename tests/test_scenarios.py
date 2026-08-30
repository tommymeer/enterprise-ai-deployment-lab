from dataclasses import FrozenInstanceError, replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
import ast
import unittest

from support_agent import (
    CaseStatus,
    Disposition,
    ExecutionStatus,
    FollowUpStatus,
    ScenarioCategory,
    ScenarioExpectation,
    evaluate_support_case_scenario,
    get_support_case_scenario,
    get_support_case_scenarios,
    run_support_case_scenario,
)
from support_agent.scenarios import _validate_dataset


class SupportCaseScenarioTest(unittest.TestCase):
    def test_dataset_has_unique_non_empty_ids_and_is_read_only(self) -> None:
        scenarios = get_support_case_scenarios()
        ids = [scenario.scenario_id for scenario in scenarios]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(identifier.strip() for identifier in ids))
        self.assertIsInstance(scenarios, tuple)
        with self.assertRaises(TypeError):
            scenarios[0] = scenarios[1]  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            scenarios[0].title = "changed"  # type: ignore[misc]

    def test_lookup_by_id_and_unknown_rejection(self) -> None:
        scenario = get_support_case_scenario("refund-success")
        self.assertEqual(scenario.title, "Successful refund")
        with self.assertRaisesRegex(KeyError, "unknown support-case scenario"):
            get_support_case_scenario("not-a-scenario")
        with self.assertRaises(ValueError):
            get_support_case_scenario("")

    def test_all_scenarios_execute_and_pass_evaluation(self) -> None:
        failures: dict[str, tuple[str, ...]] = {}
        for scenario in get_support_case_scenarios():
            with self.subTest(scenario=scenario.scenario_id):
                evaluation = evaluate_support_case_scenario(
                    run_support_case_scenario(scenario)
                )
                if not evaluation.passed:
                    failures[scenario.scenario_id] = evaluation.failure_messages
        self.assertEqual(failures, {})

    def test_supported_categories_and_major_outcomes_are_represented(self) -> None:
        scenarios = get_support_case_scenarios()
        self.assertEqual(
            {scenario.category for scenario in scenarios},
            set(ScenarioCategory),
        )
        dispositions = {scenario.expectation.disposition for scenario in scenarios}
        self.assertTrue(
            {
                Disposition.APPROVE_REFUND,
                Disposition.APPROVE_REPLACEMENT,
                Disposition.OPEN_CARRIER_INQUIRY,
                Disposition.DENY,
                Disposition.REQUEST_MORE_INFO,
                Disposition.ADVISE_SELF_CHECK_OR_WAIT,
            }.issubset(dispositions)
        )
        categories = {scenario.category for scenario in scenarios}
        self.assertTrue(
            {
                ScenarioCategory.HUMAN_REVIEW,
                ScenarioCategory.INTAKE_FAILURE,
                ScenarioCategory.EVIDENCE_FAILURE,
                ScenarioCategory.EXECUTION_FAILURE,
            }.issubset(categories)
        )

    def test_expected_trace_events_are_present_in_order(self) -> None:
        for scenario in get_support_case_scenarios():
            with self.subTest(scenario=scenario.scenario_id):
                evaluation = evaluate_support_case_scenario(
                    run_support_case_scenario(scenario)
                )
                trace_check = next(
                    check
                    for check in evaluation.checks
                    if check.name == "trace_events_in_order"
                )
                self.assertTrue(trace_check.passed)

    def test_invalid_records_and_expectations_are_rejected(self) -> None:
        scenario = get_support_case_scenario("refund-success")
        for name in ("scenario_id", "title", "description"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                replace(scenario, **{name: " "})
        with self.assertRaises(ValueError):
            replace(scenario, category="happy_path")
        with self.assertRaises(ValueError):
            replace(
                scenario.regression_metadata,
                added_at=datetime(2026, 8, 4, 12),
            )
        with self.assertRaises(ValueError):
            ScenarioExpectation(
                True,
                CaseStatus.CLOSED,
                Disposition.APPROVE_REFUND,
                ExecutionStatus.SUCCEEDED,
                FollowUpStatus.NOT_APPLICABLE,
                "execution",
                False,
                False,
                True,
                True,
                ("workflow_started",),
            )
        with self.assertRaises(ValueError):
            replace(
                scenario.expectation,
                execution_invoked=False,
                execution_succeeded=True,
            )
        with self.assertRaises(ValueError):
            replace(
                get_support_case_scenario("denial").expectation,
                execution_invoked=True,
                execution_succeeded=True,
            )
        with self.assertRaises(ValueError):
            _validate_dataset((scenario, scenario))

    def test_contradictory_expected_disposition_is_rejected(self) -> None:
        scenario = get_support_case_scenario("refund-success")
        with self.assertRaisesRegex(ValueError, "expected disposition"):
            replace(
                scenario,
                expectation=replace(
                    scenario.expectation,
                    disposition=Disposition.APPROVE_REPLACEMENT,
                ),
            )

    def test_contradictory_human_review_expectation_is_rejected(self) -> None:
        scenario = get_support_case_scenario("address-mismatch")
        with self.assertRaisesRegex(ValueError, "configured human review"):
            replace(
                scenario,
                expectation=replace(scenario.expectation, human_review=False),
            )
        scenario = get_support_case_scenario("refund-success")
        with self.assertRaisesRegex(ValueError, "supported review route"):
            replace(
                scenario,
                expectation=replace(scenario.expectation, human_review=True),
            )

    def test_contradictory_execution_success_is_rejected(self) -> None:
        scenario = get_support_case_scenario("refund-success")
        with self.assertRaisesRegex(ValueError, "expected execution success"):
            replace(
                scenario,
                expectation=replace(scenario.expectation, execution_succeeded=False),
            )

    def test_intake_failure_execution_expectation_is_rejected(self) -> None:
        scenario = get_support_case_scenario("customer-lookup-failure")
        with self.assertRaisesRegex(ValueError, "intake failure"):
            replace(
                scenario,
                expectation=replace(
                    scenario.expectation,
                    disposition=Disposition.APPROVE_REFUND,
                    execution_invoked=True,
                ),
            )

    def test_runner_delegates_to_existing_workflow(self) -> None:
        scenario = get_support_case_scenario("refund-success")
        with patch(
            "support_agent.scenarios.run_synthetic_support_case",
            wraps=__import__(
                "support_agent.scenarios", fromlist=["run_synthetic_support_case"]
            ).run_synthetic_support_case,
        ) as workflow:
            run_support_case_scenario(scenario)
        workflow.assert_called_once()

    def test_dataset_contains_only_obvious_synthetic_identifiers(self) -> None:
        for scenario in get_support_case_scenarios():
            serialized = repr(scenario).lower()
            self.assertIn("synthetic", serialized)
            self.assertNotIn("@", serialized)
            self.assertNotIn("api_key", serialized)
            self.assertNotIn("secret", serialized)

    def test_network_imports_are_isolated_to_provider_adapter(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        source_root = repository / "src" / "support_agent"

        def imports(path: Path) -> set[str]:
            imported: set[str] = set()
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            return imported

        # The demo server is an explicit localhost HTTP boundary; it does not add an
        # outbound provider dependency. All third-party network clients stay forbidden.
        allowed_standard_network_modules = {"anthropic_adapter.py", "demo_server.py"}
        forbidden_standard_network_imports = {"urllib", "socket"}
        forbidden_everywhere = {"anthropic", "openai", "requests", "httpx"}
        for path in source_root.glob("*.py"):
            if path.name not in allowed_standard_network_modules:
                self.assertTrue(
                    forbidden_standard_network_imports.isdisjoint(imports(path)),
                    path.name,
                )
            self.assertTrue(forbidden_everywhere.isdisjoint(imports(path)), path.name)


if __name__ == "__main__":
    unittest.main()
