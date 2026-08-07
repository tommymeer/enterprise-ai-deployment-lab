import json
import os
import unittest
from unittest.mock import patch

from support_agent import (
    AnthropicConfig,
    AnthropicModelClient,
    AnthropicProviderError,
    ModelRequest,
)


class ScriptedTransport:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


def request(message="Synthetic customer report"):
    return ModelRequest("extract", "v1", "Return JSON only", message, "Example")


def success_body(**overrides):
    value = {
        "model": "claude-returned-model",
        "content": [{"type": "text", "text": "result"}],
        "usage": {"input_tokens": 11, "output_tokens": 7},
        "stop_reason": "end_turn",
    }
    value.update(overrides)
    return json.dumps(value).encode()


class AnthropicAdapterTests(unittest.TestCase):
    def config(self):
        return AnthropicConfig("claude-configured-model", 128, 2.5)

    def client(self, transport, clock=lambda: 1.0):
        return AnthropicModelClient(self.config(), transport, clock)

    def test_missing_and_blank_key_fail_before_transport(self):
        for environment in ({}, {"ANTHROPIC_API_KEY": "  "}):
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True):
                transport = ScriptedTransport()
                with self.assertRaisesRegex(ValueError, "ANTHROPIC_API_KEY"):
                    self.client(transport).complete(request())
                self.assertEqual(transport.calls, [])

    def test_exact_request_translation(self):
        transport = ScriptedTransport((200, {}, success_body()))
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-secret"}, clear=True):
            self.client(transport).complete(request("Synthetic message"))
        self.assertEqual(len(transport.calls), 1)
        url, call = transport.calls[0]
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["timeout_seconds"], 2.5)
        self.assertEqual(call["headers"]["content-type"], "application/json")
        self.assertEqual(call["headers"]["anthropic-version"], "2023-06-01")
        self.assertIn("x-api-key", call["headers"])
        self.assertEqual(
            json.loads(call["body"]),
            {
                "model": "claude-configured-model",
                "max_tokens": 128,
                "system": "Return JSON only",
                "messages": [{"role": "user", "content": "Synthetic message"}],
                "stream": False,
            },
        )

    def test_thinking_is_unspecified_by_default_and_can_be_disabled(self):
        self.assertFalse(self.config().disable_thinking)
        for disabled, expected in (
            (False, None),
            (True, {"type": "disabled"}),
        ):
            with self.subTest(disabled=disabled):
                transport = ScriptedTransport((200, {}, success_body()))
                config = AnthropicConfig(
                    "claude-configured-model", 128, 2.5, disable_thinking=disabled
                )
                with patch.dict(
                    os.environ, {"ANTHROPIC_API_KEY": "test-secret"}, clear=True
                ):
                    AnthropicModelClient(config, transport).complete(request())
                payload = json.loads(transport.calls[0][1]["body"])
                if expected is None:
                    self.assertNotIn("thinking", payload)
                else:
                    self.assertEqual(payload["thinking"], expected)

    def test_success_becomes_neutral_response_with_measured_latency(self):
        transport = ScriptedTransport((200, {"Request-ID": "req_123"}, success_body()))
        times = iter((10.0, 10.125))
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-secret"}, clear=True):
            response = self.client(transport, lambda: next(times)).complete(request())
        self.assertEqual(response.provider, "anthropic")
        self.assertEqual(response.model, "claude-returned-model")
        self.assertEqual(response.response_text, "result")
        self.assertEqual((response.input_token_count, response.output_token_count), (11, 7))
        self.assertEqual(response.latency_ms, 125.0)
        self.assertEqual(response.estimated_cost_usd, 0.0)
        self.assertEqual(response.request_id, "req_123")
        self.assertEqual(response.finish_reason, "end_turn")
        self.assertFalse(response.synthetic)

    def test_null_stop_reason_is_retained_as_none(self):
        transport = ScriptedTransport((200, {}, success_body(stop_reason=None)))
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-secret"}, clear=True):
            response = self.client(transport).complete(request())
        self.assertIsNone(response.finish_reason)

    def test_multiple_text_blocks_are_concatenated_without_separator(self):
        body = success_body(content=[
            {"type": "text", "text": "first"},
            {"type": "tool_use", "name": "ignored"},
            {"type": "text", "text": " second"},
        ])
        transport = ScriptedTransport((200, {}, body))
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-secret"}, clear=True):
            response = self.client(transport).complete(request())
        self.assertEqual(response.response_text, "first second")

    def test_malformed_success_responses_are_provider_failures(self):
        cases = [
            b"not json",
            b"[]",
            success_body(content=[]),
            success_body(content=[{"type": "tool_use"}]),
            success_body(content="wrong"),
            success_body(model=12),
            success_body(usage=[]),
            success_body(usage={"input_tokens": True, "output_tokens": 1}),
            success_body(content=[{"type": "text", "text": 3}]),
        ]
        for body in cases:
            with self.subTest(body=body), patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-secret"}, clear=True):
                with self.assertRaises(AnthropicProviderError) as caught:
                    self.client(ScriptedTransport((200, {}, body))).complete(request())
                self.assertEqual(caught.exception.error_type, "malformed_response")
                self.assertFalse(caught.exception.retryable)

    def test_wrong_type_or_blank_stop_reason_is_malformed_provider_data(self):
        for stop_reason in (3, " "):
            with self.subTest(stop_reason=stop_reason), patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "test-secret"}, clear=True
            ):
                with self.assertRaises(AnthropicProviderError) as caught:
                    self.client(
                        ScriptedTransport((200, {}, success_body(stop_reason=stop_reason)))
                    ).complete(request())
                self.assertEqual(caught.exception.error_type, "malformed_response")
                self.assertFalse(caught.exception.retryable)

    def test_http_status_retryability(self):
        for status, expected in ((400, False), (401, False), (403, False), (429, True), (500, True), (504, True), (529, True)):
            headers = {"Request-ID": "req_error", "Retry-After": "1.5"}
            body = json.dumps({"error": {"type": "rate_limit_error", "message": "Try later"}}).encode()
            with self.subTest(status=status), patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-secret"}, clear=True):
                with self.assertRaises(AnthropicProviderError) as caught:
                    self.client(ScriptedTransport((status, headers, body))).complete(request())
                error = caught.exception
                self.assertEqual(error.status_code, status)
                self.assertEqual(error.error_type, "rate_limit_error")
                self.assertEqual(error.request_id, "req_error")
                self.assertEqual(error.retry_after_seconds, 1.5)
                self.assertEqual(error.retryable, expected)

    def test_malformed_error_body_preserves_known_metadata_only(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-secret"}, clear=True):
            with self.assertRaises(AnthropicProviderError) as caught:
                self.client(ScriptedTransport((400, {"X-Request-ID": "req_bad"}, b"<html>secret body</html>"))).complete(request())
        error = caught.exception
        self.assertEqual(error.status_code, 400)
        self.assertEqual(error.request_id, "req_bad")
        self.assertIsNone(error.error_type)
        self.assertNotIn("html", str(error))

    def test_timeout_and_connection_failure_have_no_invented_provider_metadata(self):
        for exception, error_type in ((TimeoutError(), "timeout"), (ConnectionError(), "transport_failure")):
            with self.subTest(error_type=error_type), patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-secret"}, clear=True):
                with self.assertRaises(AnthropicProviderError) as caught:
                    self.client(ScriptedTransport(error=exception)).complete(request())
                error = caught.exception
                self.assertIsNone(error.status_code)
                self.assertIsNone(error.request_id)
                self.assertEqual(error.error_type, error_type)
                self.assertTrue(error.retryable)

    def test_provider_error_messages_are_never_exposed_and_metadata_is_preserved(self):
        key = "secret-key-marker"
        message = "Customer says order SYNTH-ORDER-842 is missing from the loading dock"
        sensitive_provider_messages = (
            message,
            "missing from the loading dock",
            "Order SYNTH-ORDER-842 could not be found",
            f"Invalid credential {key}",
            "Try later",
        )
        for provider_message in sensitive_provider_messages:
            body = json.dumps(
                {"error": {"type": "rate_limit_error", "message": provider_message}}
            ).encode()
            headers = {"Request-ID": "req_private", "Retry-After": "2"}
            with self.subTest(provider_message=provider_message), patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": key}, clear=True
            ):
                with self.assertRaises(AnthropicProviderError) as caught:
                    self.client(ScriptedTransport((429, headers, body))).complete(request(message))
            error = caught.exception
            rendered = str(error) + repr(error)
            self.assertEqual(error.detail, "provider rejected the request")
            self.assertNotIn(provider_message, rendered)
            self.assertNotIn("SYNTH-ORDER-842", rendered)
            self.assertNotIn(key, rendered)
            self.assertEqual(error.status_code, 429)
            self.assertEqual(error.error_type, "rate_limit_error")
            self.assertEqual(error.request_id, "req_private")
            self.assertEqual(error.retry_after_seconds, 2.0)
            self.assertTrue(error.retryable)

    def test_unexpected_programming_type_error_propagates(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-secret"}, clear=True):
            with self.assertRaisesRegex(TypeError, "programming defect"):
                self.client(ScriptedTransport(error=TypeError("programming defect"))).complete(request())

    def test_wrong_request_type_is_rejected(self):
        with self.assertRaises(TypeError):
            self.client(ScriptedTransport()).complete("wrong")

    def test_configuration_is_validated_and_does_not_contain_key(self):
        config = self.config()
        self.assertNotIn("key", repr(config).lower())
        for kwargs in ({"model": ""}, {"max_tokens": 0}, {"timeout_seconds": 0}):
            values = {"model": "m", "max_tokens": 1, "timeout_seconds": 1.0} | kwargs
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                AnthropicConfig(**values)
        for value in (0, 1, None, "false"):
            with self.subTest(disable_thinking=value), self.assertRaisesRegex(
                ValueError, "disable_thinking must be a bool"
            ):
                AnthropicConfig("m", 1, 1.0, disable_thinking=value)

    def test_endpoint_cannot_be_configured(self):
        with self.assertRaisesRegex(TypeError, "endpoint"):
            AnthropicConfig(
                "claude-configured-model",
                128,
                2.5,
                endpoint="https://attacker.invalid/collect",
            )


if __name__ == "__main__":
    unittest.main()
