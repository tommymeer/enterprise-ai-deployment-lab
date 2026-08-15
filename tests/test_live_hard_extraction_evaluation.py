from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
import sys
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import run_live_hard_extraction_evaluation as runner  # noqa: E402

from support_agent import ModelResponse  # noqa: E402
from support_agent.extraction_evaluation import scripted_response  # noqa: E402


class ExactClient:
    def __init__(self) -> None:
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        case = next(
            case
            for case in runner.get_hard_extraction_eval_cases()
            if case.customer_message == request.customer_message
        )
        response = scripted_response(case.expected)
        return ModelResponse(
            "anthropic",
            runner.MODEL,
            response_text=response.response_text,
            input_token_count=100,
            output_token_count=50,
            latency_ms=10,
            finish_reason="end_turn",
            synthetic=False,
        )


class LiveHardExtractionEvaluationTests(unittest.TestCase):
    def test_dry_run_makes_no_calls_and_reports_six_case_plan(self):
        constructions = []
        output = StringIO()
        self.assertEqual(
            runner.main([], client_factory=lambda: constructions.append(True), stream=output),
            0,
        )
        self.assertEqual(constructions, [])
        plan = json.loads(output.getvalue())
        self.assertEqual(plan["call_count"], 6)
        self.assertEqual(
            plan["case_ids"],
            [
                "stale_quoted_order",
                "tracking_before_order",
                "corrected_order",
                "dense_number_roles",
                "number_prose_without_ids",
                "unsupported_address_inference",
            ],
        )
        self.assertEqual(plan["model"], "claude-sonnet-5")
        self.assertEqual(plan["max_tokens_per_call"], 512)
        self.assertEqual(plan["thinking"], "disabled")
        self.assertEqual(plan["timeout_seconds"], 30)
        self.assertEqual(plan["retry_count"], 0)
        self.assertEqual(plan["authorized_estimated_spend_limit_usd"], 0.09)

    def test_exact_offline_run_calls_each_case_once_and_retains_results(self):
        client = ExactClient()
        output = StringIO()
        self.assertEqual(runner.run_live_evaluation(client, output), 0)
        self.assertEqual(len(client.requests), 6)
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(records), 7)
        for record in records[:-1]:
            self.assertEqual(record["semantic_result"], "PASS")
            self.assertIsInstance(record["actual_extraction"], dict)
            self.assertIsInstance(record["raw_model_output"], str)
        summary = records[-1]
        self.assertEqual(summary["attempted_calls"], 6)
        self.assertEqual(summary["valid_outputs"], 6)
        self.assertEqual(summary["semantic_exact_matches"], 6)
        self.assertEqual(summary["total_input_tokens"], 600)
        self.assertEqual(summary["total_output_tokens"], 300)
        self.assertEqual(summary["total_latency_ms"], 60)
        self.assertEqual(summary["total_estimated_cost_usd"], 0.0063)
        self.assertTrue(
            all(
                item["matches"] == item["total"] == 6
                for item in summary["per_field_accuracy"].values()
            )
        )

    def test_pricing_and_conservative_ceiling(self):
        self.assertEqual(runner.MAXIMUM_COST_PER_CALL_USD, 0.01368)
        self.assertEqual(runner.PRE_RUN_MAXIMUM_COST_USD, 0.08208)
        self.assertTrue(runner.spend_guard_allows_call(0, 6))


if __name__ == "__main__":
    unittest.main()
