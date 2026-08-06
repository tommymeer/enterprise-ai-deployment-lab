from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import run_live_extraction_validation as runner  # noqa: E402

from support_agent import AnthropicProviderError, ModelResponse  # noqa: E402


def response_for(message: str, *, request_id: str = "req-secret-123") -> ModelResponse:
    order_identifier = None
    issue_type = "unknown"
    package_missing = None
    missing = ["order_identifier"]
    clarification = True
    reason = "Please provide the synthetic order identifier."
    if "SYNTH-ORDER-41001" in message:
        order_identifier = "SYNTH-ORDER-41001"
        issue_type = "delivered_not_received"
        package_missing = True
        missing = []
        clarification = False
        reason = None
    elif "tracking page" in message:
        issue_type = "delivered_not_received"
        package_missing = True
    elif "SYNTH-ORDER-41003" in message:
        order_identifier = "SYNTH-ORDER-41003"
        missing = []
        clarification = False
        reason = None
    payload = {
        "original_message": message,
        "issue_type": issue_type,
        "order_identifier": order_identifier,
        "tracking_identifier": None,
        "customer_claims_package_missing": package_missing,
        "customer_claims_address_correct": None,
        "missing_required_fields": missing,
        "needs_clarification": clarification,
        "clarification_reason": reason,
    }
    return ModelResponse(
        "anthropic",
        runner.MODEL,
        response_text=json.dumps(payload),
        input_token_count=100,
        output_token_count=50,
        latency_ms=12.5,
        request_id=request_id,
        synthetic=False,
    )


class FakeClient:
    def __init__(self, fail_on_call: int | None = None) -> None:
        self.requests = []
        self.fail_on_call = fail_on_call

    def complete(self, request):
        self.requests.append(request)
        if self.fail_on_call == len(self.requests):
            raise AnthropicProviderError(
                "anthropic", 429, "rate_limit_error", "req-private", None, True,
                "provider rejected the request",
            )
        return response_for(request.customer_message)


class LiveExtractionValidationTests(unittest.TestCase):
    def test_without_confirmation_prints_plan_and_constructs_no_client(self):
        output = StringIO()
        constructions = []
        result = runner.main(
            [], client_factory=lambda: constructions.append(True), stream=output
        )
        self.assertEqual(result, 0)
        self.assertEqual(constructions, [])
        plan = json.loads(output.getvalue())
        self.assertEqual(plan["call_count"], 3)
        self.assertNotIn("customer_message", plan)

    def test_inconsistent_case_count_fails_before_client_construction_or_call(self):
        client = FakeClient()
        constructions = []

        def construct_client():
            constructions.append(True)
            return client

        with patch.object(runner, "CASES", runner.CASES[:-1]):
            with self.assertRaisesRegex(RuntimeError, "exactly three"):
                runner.main(
                    ["--confirm-live-call"],
                    client_factory=construct_client,
                    stream=StringIO(),
                )

        self.assertEqual(constructions, [])
        self.assertEqual(client.requests, [])

    def test_normal_three_case_plan_succeeds_offline(self):
        client = FakeClient()
        constructions = []

        def construct_client():
            constructions.append(True)
            return client

        result = runner.main(
            ["--confirm-live-call"],
            client_factory=construct_client,
            stream=StringIO(),
        )

        self.assertEqual(result, 0)
        self.assertEqual(constructions, [True])
        self.assertEqual(len(client.requests), 3)

    def test_dry_run_constructs_no_client_and_makes_no_calls(self):
        client = FakeClient()
        constructions = []

        def construct_client():
            constructions.append(True)
            return client

        self.assertEqual(
            runner.main([], client_factory=construct_client, stream=StringIO()), 0
        )
        self.assertEqual(constructions, [])
        self.assertEqual(client.requests, [])

    def test_plan_has_exactly_three_fixed_synthetic_cases(self):
        self.assertEqual(len(runner.CASES), 3)
        self.assertEqual(len({case.case_id for case in runner.CASES}), 3)
        self.assertTrue(all("synthetic" in case.customer_message.lower() for case in runner.CASES))
        self.assertIn("SYNTH-ORDER-41001", runner.CASES[0].customer_message)
        self.assertNotIn("ORDER-", runner.CASES[1].customer_message)
        self.assertIn("SYNTH-ORDER-41003", runner.CASES[2].customer_message)

    def test_pricing_arithmetic_and_pre_run_maximum(self):
        self.assertAlmostEqual(runner.estimated_cost_usd(2_000, 256), 0.00656)
        self.assertAlmostEqual(runner.PRE_RUN_MAXIMUM_COST_USD, 0.01968)

    def test_spend_guard_prevents_disallowed_call(self):
        self.assertTrue(runner.spend_guard_allows_call(0.0, 3))
        self.assertFalse(
            runner.spend_guard_allows_call(0.094, 1, ceiling_usd=0.10)
        )

    def test_sanitized_output_excludes_sensitive_values(self):
        client = FakeClient()
        output = StringIO()
        self.assertEqual(runner.run_live_validation(client, output), 0)
        rendered = output.getvalue()
        for forbidden in (
            "This is a synthetic test",
            "SYNTH-ORDER-41001",
            "SYNTH-ORDER-41003",
            "req-secret-123",
            "test-api-key-secret",
        ):
            self.assertNotIn(forbidden, rendered)
        self.assertIn('"request_id_present":true', rendered)
        self.assertIn('"order_identifier_extracted":true', rendered)

    def test_provider_error_stops_calls_without_retry_or_sensitive_metadata(self):
        client = FakeClient(fail_on_call=2)
        output = StringIO()
        self.assertEqual(runner.run_live_validation(client, output), 1)
        self.assertEqual(len(client.requests), 2)
        rendered = output.getvalue()
        self.assertIn('"error_type":"rate_limit_error"', rendered)
        self.assertIn('"request_id_present":true', rendered)
        self.assertNotIn("req-private", rendered)
        self.assertNotIn(runner.CASES[1].customer_message, rendered)


if __name__ == "__main__":
    unittest.main()
