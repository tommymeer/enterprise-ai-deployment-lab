import json
import unittest

from support_agent.demo import (
    DEMO_SCENARIO_IDS,
    demo_options,
    eval_evidence,
    run_demo,
    serialize_model_request,
    serialize_model_response,
)
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
        self.assertEqual(
            [item["label"] for item in view["decision_timeline"]],
            [
                "Customer message received", "Extraction validated",
                "Order and shipment evidence retrieved", "Policy allowed disposition",
                "Refund approved", "Authority granted", "Refund execution succeeded",
                "Case closed",
            ],
        )
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
        labels = [item["label"] for item in view["decision_timeline"]]
        self.assertEqual(labels[-3:], [
            "Refund execution failed", "Failure routed to human review", "Case remained open",
        ])

    def test_eval_evidence_counts_expected_controls_not_naive_passes(self) -> None:
        evidence = eval_evidence()
        self.assertEqual(
            [item["result"] for item in evidence["items"]],
            [
                "10/10 behaved as expected", "12/12 behaved as expected",
                "20/20 behaved as expected", "8/8 behaved as expected",
            ],
        )
        self.assertEqual(
            evidence["items"][0]["breakdown"],
            ["5/5 correct outputs accepted", "5/5 invalid or incorrect outputs detected"],
        )
        self.assertEqual(
            evidence["items"][3]["breakdown"],
            [
                "6/6 valid scenario outcomes and trajectories satisfied",
                "2/2 deliberately invalid trajectories rejected",
            ],
        )

    def test_demo_supports_only_two_fixed_scenarios(self) -> None:
        self.assertEqual(DEMO_SCENARIO_IDS, ("refund-success", "refund-execution-failure"))
        with self.assertRaises(KeyError):
            run_demo("replacement-success")

    def test_demo_options_include_message_for_ready_state(self) -> None:
        options = demo_options()
        self.assertEqual([item["id"] for item in options["scenarios"]], list(DEMO_SCENARIO_IDS))
        self.assertTrue(all(item["customer_message"] for item in options["scenarios"]))
        self.assertFalse(options["input_editable"])

    def test_static_ui_starts_ready_and_resets_without_auto_run(self) -> None:
        index = __import__("pathlib").Path(__file__).parents[1] / "src/support_agent/demo_static/index.html"
        source = index.read_text()
        self.assertIn("Ready to run", source)
        self.assertIn("Running case…", source)
        self.assertIn("Run complete", source)
        self.assertIn("scenario').onchange=reset", source)
        self.assertNotIn(".then(o=>{$('#scenario').innerHTML=o.scenarios", source)
        self.assertIn("<details class=\"trace-section\">", source)
        self.assertNotIn("setTimeout", source)

    def test_model_serializers_are_explicit_allowlists(self) -> None:
        request = ModelRequest("task", "v1", "instructions", "message", "Schema")
        response = ModelResponse("synthetic", "scripted", response_text="{}")
        self.assertEqual(set(serialize_model_request(request)), {"task_name", "prompt_version", "expected_schema_name", "customer_message", "system_instructions"})
        self.assertEqual(set(serialize_model_response(response)), {"provider", "model", "response_text", "synthetic", "input_token_count", "output_token_count", "latency_ms", "estimated_cost_usd", "finish_reason", "request_id"})
        self.assertNotIn("__dict__", json.dumps(serialize_model_response(response)))


if __name__ == "__main__":
    unittest.main()
