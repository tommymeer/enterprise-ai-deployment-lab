import json
import unittest

from support_agent.demo import DEMO_SCENARIO_IDS, run_demo, serialize_model_request, serialize_model_response
from support_agent.modeling import ModelRequest, ModelResponse


class DemoViewTests(unittest.TestCase):
    def test_happy_path_exposes_real_layers(self) -> None:
        view = run_demo("refund-success")
        self.assertEqual(view["state"]["final"]["case_status"], "closed")
        self.assertEqual(view["execution"]["status"], "succeeded")
        self.assertEqual(view["authorization"]["event"], "execution_authority_granted")
        self.assertTrue(view["validation"]["validation_succeeded"])
        self.assertTrue(view["evidence"])
        self.assertIn("execution_result_recorded", [row["event"] for row in view["trace_rows"]])
        json.dumps(view)

    def test_execution_failure_preserves_approval_and_routes_to_review(self) -> None:
        view = run_demo("refund-execution-failure")
        final = view["state"]["final"]
        self.assertEqual(final["case_status"], "human_review")
        self.assertEqual(final["disposition"], "approve_refund")
        self.assertEqual(final["execution_status"], "failed")
        self.assertFalse(view["state"]["completed"])
        self.assertTrue(view["human_review"]["required"])
        self.assertEqual(view["authorization"]["event"], "execution_authority_granted")

    def test_demo_supports_only_two_fixed_scenarios(self) -> None:
        self.assertEqual(DEMO_SCENARIO_IDS, ("refund-success", "refund-execution-failure"))
        with self.assertRaises(KeyError):
            run_demo("replacement-success")

    def test_model_serializers_are_explicit_allowlists(self) -> None:
        request = ModelRequest("task", "v1", "instructions", "message", "Schema")
        response = ModelResponse("synthetic", "scripted", response_text="{}")
        self.assertEqual(set(serialize_model_request(request)), {"task_name", "prompt_version", "expected_schema_name", "customer_message", "system_instructions"})
        self.assertEqual(set(serialize_model_response(response)), {"provider", "model", "response_text", "synthetic", "input_token_count", "output_token_count", "latency_ms", "estimated_cost_usd", "finish_reason", "request_id"})
        self.assertNotIn("__dict__", json.dumps(serialize_model_response(response)))


if __name__ == "__main__":
    unittest.main()
