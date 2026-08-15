"""Print the offline extraction evaluation for the new hard cases only."""

from support_agent.extraction_evaluation import run_scripted_hard_extraction_eval


def _display(value: object) -> object:
    return value.value if hasattr(value, "value") else value


def run() -> str:
    lines = [f"{'case':32} {'valid_output':14} semantic_match"]
    for result in run_scripted_hard_extraction_eval():
        semantic = "PASS" if result.semantic_match else "FAIL"
        lines.append(f"{result.case_id:32} {'PASS' if result.valid_output else 'FAIL':14} {semantic}")
        for mismatch in result.differing_fields:
            lines.append(
                f"  {mismatch.field_name}: expected {_display(mismatch.expected)!r}, "
                f"actual {_display(mismatch.actual)!r}"
            )
    return "\n".join(lines)


def main() -> None:
    print(run())


if __name__ == "__main__":
    main()
