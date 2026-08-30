"""Fixed localhost HTTP surface for the offline support-agent demo."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .demo import demo_options, eval_evidence, run_demo

_INDEX = Path(__file__).with_name("demo_static").joinpath("index.html")


class DemoHandler(BaseHTTPRequestHandler):
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
            self._json(HTTPStatus.OK, demo_options())
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
            if set(payload) != {"scenario_id"} or not isinstance(payload["scenario_id"], str):
                raise ValueError("body must contain only scenario_id")
            self._json(HTTPStatus.OK, run_demo(payload["scenario_id"]))
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline support-agent demo")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
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
