import io
import json
import unittest
from http import HTTPStatus
from unittest.mock import patch

from support_agent.demo_server import DemoHandler, parse_args


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
    def test_server_defaults_to_local_offline_mode(self):
        with patch.dict("os.environ", {}, clear=True):
            args = parse_args([])
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8000)
        self.assertFalse(args.enable_live)

    def test_server_accepts_explicit_public_host(self):
        self.assertEqual(parse_args(["--host", "0.0.0.0"]).host, "0.0.0.0")

    def test_port_environment_variable_is_used_unless_cli_port_is_supplied(self):
        with patch.dict("os.environ", {"PORT": "8765"}, clear=True):
            self.assertEqual(parse_args([]).port, 8765)
            self.assertEqual(parse_args(["--port", "9876"]).port, 9876)

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
