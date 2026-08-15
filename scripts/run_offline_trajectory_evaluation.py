"""Print the first small outcome-versus-trajectory evaluation."""

from support_agent.trajectory_evaluation import (
    check_outcome,
    check_trajectory,
    concrete_evaluation_cases,
)


def main() -> None:
    print(f"{'scenario':32} {'outcome':10} trajectory")
    for name, result, expected, event_names in concrete_evaluation_cases():
        outcome_failures = check_outcome(result, expected)
        trajectory_failures = check_trajectory(result, event_names)
        print(
            f"{name:32} "
            f"{'FAIL' if outcome_failures else 'PASS':10} "
            f"{'FAIL' if trajectory_failures else 'PASS'}"
        )
        for failure in outcome_failures + trajectory_failures:
            print(f"  - {failure}")


if __name__ == "__main__":
    main()
