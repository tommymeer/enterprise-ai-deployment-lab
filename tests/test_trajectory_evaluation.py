import unittest

from support_agent.trajectory_evaluation import (
    check_outcome,
    check_trajectory,
    concrete_evaluation_cases,
)


class TrajectoryEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = {
            name: (result, expected, events)
            for name, result, expected, events in concrete_evaluation_cases()
        }

    def test_legitimate_scenarios_have_expected_outcomes(self) -> None:
        for name in (
            "happy_refund",
            "carrier_failure",
            "execution_failure",
            "order_correction_recovery",
        ):
            with self.subTest(scenario=name):
                result, expected, _ = self.cases[name]
                self.assertEqual(check_outcome(result, expected), ())

    def test_over_limit_refund_is_a_correct_safe_outcome_and_trajectory(self) -> None:
        result, expected, events = self.cases["over_limit_refund"]
        self.assertEqual(check_outcome(result, expected), ())
        self.assertEqual(check_trajectory(result, events), ())

    def test_currency_mismatch_is_a_safe_trajectory(self) -> None:
        result, expected, events = self.cases["currency_mismatch_refund"]
        self.assertEqual(check_outcome(result, expected), ())
        self.assertEqual(check_trajectory(result, events), ())

    def test_permitted_refund_execution_passes_trajectory_evaluation(self) -> None:
        result, _, events = self.cases["happy_refund"]
        self.assertIn(
            "execution_started", tuple(event.event_type for event in result.trace_events)
        )
        self.assertEqual(check_trajectory(result, events), ())

    def test_legitimate_scenarios_satisfy_trajectory_invariants(self) -> None:
        for name in (
            "happy_refund",
            "carrier_failure",
            "execution_failure",
            "order_correction_recovery",
        ):
            with self.subTest(scenario=name):
                result, _, events = self.cases[name]
                self.assertEqual(check_trajectory(result, events), ())

    def test_execution_before_disposition_still_has_the_correct_outcome(self) -> None:
        result, expected, _ = self.cases[
            "correct_outcome_execution_before_disposition"
        ]
        self.assertEqual(check_outcome(result, expected), ())

    def test_execution_before_disposition_fails_trajectory_invariant(self) -> None:
        result, _, events = self.cases[
            "correct_outcome_execution_before_disposition"
        ]
        self.assertEqual(
            check_trajectory(result, events),
            ("disposition must occur before execution_started",),
        )

    def test_unauthorized_execution_still_has_the_correct_outcome(self) -> None:
        result, expected, _ = self.cases[
            "correct_outcome_unauthorized_execution"
        ]
        self.assertEqual(check_outcome(result, expected), ())

    def test_unauthorized_execution_fails_the_authorization_invariant(self) -> None:
        result, _, events = self.cases[
            "correct_outcome_unauthorized_execution"
        ]
        self.assertEqual(
            check_trajectory(result, events),
            (
                "unauthorized refund execution: execution evidence is present despite "
                "insufficient refund authority",
            ),
        )


if __name__ == "__main__":
    unittest.main()
