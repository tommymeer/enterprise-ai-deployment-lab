from __future__ import annotations

from dataclasses import fields, replace
from io import StringIO
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import run_live_semantic_robustness_evaluation as live_runner  # noqa: E402

from support_agent import ModelResponse  # noqa: E402
from support_agent.extraction import CustomerMessageExtraction, ExtractionIssueType  # noqa: E402
from support_agent.extraction_evaluation import (  # noqa: E402
    attribute_extraction_failure,
    evaluate_extraction_case,
    get_extraction_eval_cases,
    get_semantic_robustness_eval_cases,
    run_scripted_semantic_robustness_eval,
    scripted_response,
)


class ExactClient:
    def __init__(self) -> None:
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        case = next(
            item
            for item in get_semantic_robustness_eval_cases()
            if item.customer_message == request.customer_message
        )
        response = scripted_response(case.expected)
        return ModelResponse(
            "anthropic",
            live_runner.MODEL,
            response_text=response.response_text,
            input_token_count=100,
            output_token_count=50,
            latency_ms=10,
            finish_reason="end_turn",
            synthetic=False,
        )


class SemanticRobustnessEvaluationTests(unittest.TestCase):
    def test_five_sources_have_exactly_four_named_variants(self):
        cases = get_semantic_robustness_eval_cases()
        self.assertEqual(len(cases), 20)
        self.assertEqual(len({case.case_id for case in cases}), 20)
        self.assertEqual(
            {case.source_case_id for case in cases},
            {
                "missing_order",
                "unknown_issue",
                "order_and_tracking",
                "multiple_identifiers",
                "explicit_address_correct",
            },
        )
        for source_case_id in {case.source_case_id for case in cases}:
            source_variants = [
                case for case in cases if case.source_case_id == source_case_id
            ]
            self.assertEqual(
                {case.transformation for case in source_variants},
                {
                    "paraphrased",
                    "facts_reordered",
                    "irrelevant_detail",
                    "different_verbosity",
                },
            )

    def test_variants_reuse_all_canonical_facts_except_original_message(self):
        canonical = {case.case_id: case for case in get_extraction_eval_cases()}
        for variant in get_semantic_robustness_eval_cases():
            source = canonical[variant.source_case_id]
            self.assertEqual(variant.expected.original_message, variant.customer_message)
            for field in fields(CustomerMessageExtraction):
                if field.name != "original_message":
                    self.assertEqual(
                        getattr(variant.expected, field.name),
                        getattr(source.expected, field.name),
                    )

    def test_exact_semantic_variants_pass_all_nine_fields_offline(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network attempted")):
            results = run_scripted_semantic_robustness_eval()
        self.assertEqual(len(results), 20)
        self.assertTrue(all(result.valid_output for result in results))
        self.assertTrue(all(result.semantic_match for result in results))
        self.assertTrue(all(len(result.field_comparisons) == 9 for result in results))

    def test_failure_attribution_records_layer_evidence_and_remedy(self):
        case = next(
            case
            for case in get_semantic_robustness_eval_cases()
            if case.case_id == "unknown_issue__paraphrased"
        )
        wrong = replace(
            case.expected,
            issue_type=ExtractionIssueType.DELIVERED_NOT_RECEIVED,
            customer_claims_package_missing=True,
        )
        result = evaluate_extraction_case(case, scripted_response(wrong))
        attribution = attribute_extraction_failure(result)
        self.assertIsNotNone(attribution)
        self.assertEqual(attribution.primary_failure_layer, "model interpretation")
        self.assertIn("issue_type", attribution.supporting_evidence)
        self.assertIn("grader", attribution.likely_remedy)

    def test_live_runner_is_dry_by_default_and_reports_cost_bound(self):
        constructions = []
        output = StringIO()
        self.assertEqual(
            live_runner.main(
                [], client_factory=lambda: constructions.append(True), stream=output
            ),
            0,
        )
        self.assertEqual(constructions, [])
        plan = json.loads(output.getvalue())
        self.assertEqual(plan["call_count"], 20)
        self.assertEqual(plan["pre_run_maximum_cost_usd"], 0.2736)
        self.assertEqual(plan["authorized_estimated_spend_limit_usd"], 0.28)

    def test_live_mechanics_call_each_variant_once_and_retain_outputs(self):
        client = ExactClient()
        output = StringIO()
        self.assertEqual(live_runner.run_live_evaluation(client, output), 0)
        self.assertEqual(len(client.requests), 20)
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(records), 21)
        self.assertTrue(all(record["semantic_result"] == "PASS" for record in records[:-1]))
        self.assertTrue(all(record["failure_attribution"] is None for record in records[:-1]))
        self.assertTrue(all(isinstance(record["raw_model_output"], str) for record in records[:-1]))
        self.assertEqual(records[-1]["semantic_exact_matches"], 20)


if __name__ == "__main__":
    unittest.main()
