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

    def test_bad_trajectory_still_has_the_correct_outcome(self) -> None:
        result, expected, _ = self.cases["correct_outcome_bad_path"]
        self.assertEqual(check_outcome(result, expected), ())

    def test_bad_trajectory_fails_for_execution_before_disposition(self) -> None:
        result, _, events = self.cases["correct_outcome_bad_path"]
        self.assertEqual(
            check_trajectory(result, events),
            ("disposition must occur before execution_started",),
        )


if __name__ == "__main__":
    unittest.main()
