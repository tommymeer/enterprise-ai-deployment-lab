"""Focused offline tests for exact extraction evaluation mechanics."""

import unittest
from dataclasses import fields, replace
from types import SimpleNamespace
from unittest.mock import patch

from support_agent.extraction import ExtractionIssueType
from support_agent.extraction_evaluation import (
    clarification_reason_matches,
    compare_extractions,
    evaluate_extraction_case,
    get_extraction_eval_cases,
    get_hard_extraction_eval_cases,
    run_scripted_hard_extraction_eval,
    run_scripted_extraction_eval,
    scripted_response,
)


class ExtractionEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = {case.case_id: case for case in get_extraction_eval_cases()}

    def test_exact_expected_extraction_passes_all_fields(self) -> None:
        case = self.cases["clear_dnr_order"]
        result = evaluate_extraction_case(case, scripted_response(case.expected))
        self.assertTrue(result.valid_output)
        self.assertTrue(result.semantic_match)
        self.assertEqual(result.differing_fields, ())
        self.assertEqual(len(result.field_comparisons), 9)

    def test_schema_invalid_output_is_a_validation_failure(self) -> None:
        result = run_scripted_extraction_eval()[-1]
        self.assertFalse(result.valid_output)
        self.assertIsNone(result.semantic_match)
        self.assertIn("not literally grounded", result.extraction_result.validation_reason or "")

    def test_schema_valid_semantically_wrong_output_fails_field_comparison(self) -> None:
        case = self.cases["vague_with_order"]
        wrong = replace(case.expected, issue_type=ExtractionIssueType.DELIVERED_NOT_RECEIVED, customer_claims_package_missing=True)
        result = evaluate_extraction_case(case, scripted_response(wrong))
        self.assertTrue(result.valid_output)
        self.assertFalse(result.semantic_match)
        self.assertEqual({item.field_name for item in result.differing_fields}, {"issue_type", "customer_claims_package_missing"})

    def test_grounded_but_wrong_identifier_is_caught_semantically(self) -> None:
        result = run_scripted_extraction_eval()[6]
        self.assertTrue(result.valid_output)
        self.assertFalse(result.semantic_match)
        self.assertEqual(tuple(item.field_name for item in result.differing_fields), ("order_identifier",))

    def test_clarification_field_mistakes_are_caught(self) -> None:
        case = self.cases["missing_order"]
        wrong = SimpleNamespace(
            **{
                field_name: getattr(case.expected, field_name)
                for field_name in (field.name for field in fields(case.expected))
            },
        )
        wrong.needs_clarification = False
        wrong.clarification_reason = None
        comparisons = compare_extractions(case.expected, wrong)
        self.assertEqual(
            {item.field_name for item in comparisons if not item.matched},
            {"needs_clarification", "clarification_reason"},
        )

    def clarification_match(self, case_id: str, **changes) -> bool:
        expected = self.cases[case_id].expected
        actual = replace(expected, **changes)
        return next(
            item.matched
            for item in compare_extractions(expected, actual)
            if item.field_name == "clarification_reason"
        )

    def test_original_expected_clarification_wording_passes(self) -> None:
        self.assertTrue(self.clarification_match("missing_order"))

    def test_live_claude_clarification_wording_passes(self) -> None:
        self.assertTrue(
            self.clarification_match(
                "missing_order",
                clarification_reason=(
                    "The order identifier is required to locate the order but was not "
                    "provided in the message."
                ),
            )
        )

    def test_retained_semantic_run_clarification_wordings_pass(self) -> None:
        reasons = (
            "The order identifier is needed to locate the order and investigate the delivery issue.",
            "The order identifier is needed to locate and investigate this delivery issue.",
            "The customer did not provide an order identifier needed to locate the order.",
        )
        self.assertTrue(
            all(
                self.clarification_match(
                    "missing_order", clarification_reason=reason
                )
                for reason in reasons
            )
        )

    def test_negated_needed_clarification_text_fails(self) -> None:
        self.assertFalse(
            self.clarification_match(
                "missing_order",
                clarification_reason="The order identifier is not needed.",
            )
        )

    def test_unrelated_nonempty_clarification_text_fails(self) -> None:
        self.assertFalse(
            self.clarification_match(
                "missing_order", clarification_reason="More information is needed."
            )
        )

    def test_null_clarification_reason_fails_when_required(self) -> None:
        self.assertFalse(
            clarification_reason_matches(True, None, None)
        )

    def test_non_null_clarification_reason_fails_when_not_required(self) -> None:
        self.assertFalse(
            clarification_reason_matches(False, "ORD-1001", "Order identifier is required.")
        )

    def test_null_clarification_reason_passes_when_not_required(self) -> None:
        self.assertTrue(
            self.clarification_match("clear_dnr_order", clarification_reason=None)
        )

    def test_other_fields_still_use_exact_equality(self) -> None:
        expected = self.cases["missing_order"].expected
        actual = replace(
            expected,
            issue_type=ExtractionIssueType.UNKNOWN,
            clarification_reason=(
                "The order identifier is required to locate the order but was not "
                "provided in the message."
            ),
        )
        comparisons = {
            item.field_name: item.matched
            for item in compare_extractions(expected, actual)
        }
        self.assertTrue(comparisons["clarification_reason"])
        self.assertFalse(comparisons["issue_type"])
        self.assertTrue(
            all(
                matched
                for field_name, matched in comparisons.items()
                if field_name not in {"issue_type", "clarification_reason"}
            )
        )

    def test_eval_uses_only_scripted_clients_without_network(self) -> None:
        with patch("socket.socket", side_effect=AssertionError("network access attempted")):
            results = run_scripted_extraction_eval()
        self.assertEqual(len(results), 10)
        self.assertTrue(all(result.extraction_result.trace.synthetic for result in results))

    def test_hard_case_expected_outputs_are_exact_and_offline(self) -> None:
        with patch("socket.socket", side_effect=AssertionError("network access attempted")):
            results = run_scripted_hard_extraction_eval()
        exact_results = results[: len(get_hard_extraction_eval_cases())]
        self.assertEqual(len(exact_results), 6)
        self.assertTrue(all(result.valid_output for result in exact_results))
        self.assertTrue(all(result.semantic_match for result in exact_results))
        self.assertTrue(all(result.extraction_result.trace.synthetic for result in results))

    def test_hard_case_semantic_mistakes_are_valid_but_caught(self) -> None:
        results = run_scripted_hard_extraction_eval()[6:]
        self.assertEqual(len(results), 6)
        self.assertTrue(all(result.valid_output for result in results))
        self.assertTrue(all(result.semantic_match is False for result in results))
        self.assertEqual(
            [tuple(item.field_name for item in result.differing_fields) for result in results],
            [
                ("order_identifier",),
                ("order_identifier", "tracking_identifier"),
                ("order_identifier",),
                ("order_identifier",),
                ("order_identifier", "missing_required_fields", "needs_clarification", "clarification_reason"),
                ("customer_claims_address_correct",),
            ],
        )


if __name__ == "__main__":
    unittest.main()
