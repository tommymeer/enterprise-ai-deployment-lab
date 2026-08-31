"""Fixed localhost HTTP surface for the offline support-agent demo."""

from __future__ import annotations

import argparse
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .anthropic_adapter import AnthropicProviderError
from .demo import demo_options, eval_evidence, run_demo

_INDEX = Path(__file__).with_name("demo_static").joinpath("index.html")


class DemoHandler(BaseHTTPRequestHandler):
    live_enabled = False
    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: HTTPStatus, value: object) -> None:
        self._send(status, json.dumps(value).encode(), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/":
            self._send(HTTPStatus.OK, _INDEX.read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/demo-options":
            self._json(HTTPStatus.OK, demo_options(live_enabled=self.live_enabled))
        elif path == "/api/evidence":
            self._json(HTTPStatus.OK, eval_evidence())
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/run":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1024:
                raise ValueError("request too large")
            payload = json.loads(self.rfile.read(length))
            if set(payload) != {"scenario_id", "mode", "customer_message"}:
                raise ValueError("body must contain scenario_id, mode, and customer_message")
            if not all(isinstance(payload[key], str) for key in payload):
                raise ValueError("request values must be strings")
            self._json(HTTPStatus.OK, run_demo(payload["scenario_id"], payload["customer_message"],
                mode=payload["mode"], live_enabled=self.live_enabled))
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except AnthropicProviderError as error:
            self._json(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
        except Exception:
            logging.exception("unexpected error while running demo case")
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "The demo server could not complete this case. Check the server log."})

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the support-agent interview demo")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--enable-live", action="store_true",
        help="explicitly enable one-call live Claude extraction (requires ANTHROPIC_API_KEY)")
    args = parser.parse_args()
    DemoHandler.live_enabled = args.enable_live
    server = ThreadingHTTPServer(("127.0.0.1", args.port), DemoHandler)
    print(f"Support-agent demo: http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
