import io
import json
import unittest
from http import HTTPStatus
from unittest.mock import patch

from support_agent.demo_server import DemoHandler


FIXTURE_MESSAGE = "My package says delivered, but I cannot find it. Order 12345."


def post_case(scenario_id: str) -> tuple[int, dict]:
    payload = json.dumps({
        "scenario_id": scenario_id,
        "mode": "scripted",
        "customer_message": FIXTURE_MESSAGE,
    }).encode()
    handler = object.__new__(DemoHandler)
    handler.path = "/api/run"
    handler.headers = {"Content-Length": str(len(payload))}
    handler.rfile = io.BytesIO(payload)
    handler.wfile = io.BytesIO()
    handler.send_response = lambda status: setattr(handler, "response_status", status)
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None
    handler.do_POST()
    return handler.response_status, json.loads(handler.wfile.getvalue())


class DemoServerContractTests(unittest.TestCase):
    def test_browser_payload_runs_both_scripted_execution_modes(self):
        expected = {
            "refund-success": ("closed", "succeeded"),
            "refund-execution-failure": ("human_review", "failed"),
        }
        for scenario_id, final_state in expected.items():
            with self.subTest(scenario_id=scenario_id):
                status, body = post_case(scenario_id)
                self.assertEqual(status, HTTPStatus.OK)
                self.assertEqual(
                    (body["final_state"]["case_status"], body["final_state"]["execution_status"]),
                    final_state,
                )
                self.assertTrue(body["mode"]["synthetic"])

    def test_unexpected_backend_error_returns_safe_json_diagnostic(self):
        with patch("support_agent.demo_server.run_demo", side_effect=RuntimeError("private detail")):
            with self.assertLogs(level="ERROR") as captured:
                status, body = post_case("refund-success")
        self.assertEqual(status, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertEqual(body, {
            "error": "The demo server could not complete this case. Check the server log."
        })
        self.assertNotIn("private detail", json.dumps(body))
        self.assertIn("private detail", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
