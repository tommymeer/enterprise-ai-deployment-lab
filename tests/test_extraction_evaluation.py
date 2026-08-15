"""Focused offline tests for exact extraction evaluation mechanics."""

import unittest
from dataclasses import replace
from unittest.mock import patch

from support_agent.extraction import ExtractionIssueType
from support_agent.extraction_evaluation import (
    evaluate_extraction_case,
    get_extraction_eval_cases,
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
        wrong = replace(case.expected, order_identifier="carrier", missing_required_fields=(), needs_clarification=False, clarification_reason=None)
        result = evaluate_extraction_case(case, scripted_response(wrong))
        self.assertTrue(result.valid_output)
        self.assertFalse(result.semantic_match)
        self.assertEqual(
            {item.field_name for item in result.differing_fields},
            {"order_identifier", "missing_required_fields", "needs_clarification", "clarification_reason"},
        )

    def test_eval_uses_only_scripted_clients_without_network(self) -> None:
        with patch("socket.socket", side_effect=AssertionError("network access attempted")):
            results = run_scripted_extraction_eval()
        self.assertEqual(len(results), 10)
        self.assertTrue(all(result.extraction_result.trace.synthetic for result in results))


if __name__ == "__main__":
    unittest.main()
