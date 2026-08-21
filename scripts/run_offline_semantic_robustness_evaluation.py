"""Print the bounded offline semantic-robustness extraction evaluation."""

from support_agent.extraction_evaluation import run_scripted_semantic_robustness_eval


def run() -> str:
    lines = [f"{'case':54} {'valid_output':14} semantic_match"]
    for result in run_scripted_semantic_robustness_eval():
        semantic = "PASS" if result.semantic_match else "FAIL"
        lines.append(
            f"{result.case_id:54} "
            f"{'PASS' if result.valid_output else 'FAIL':14} {semantic}"
        )
    return "\n".join(lines)


def main() -> None:
    print(run())


if __name__ == "__main__":
    main()
