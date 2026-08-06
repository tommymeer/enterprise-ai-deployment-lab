"""Bounded Anthropic Messages adapter with an injectable HTTP transport."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from time import perf_counter
from typing import Protocol
from urllib import error as urllib_error
from urllib import request as urllib_request

from .modeling import ModelRequest, ModelResponse


_PROVIDER = "anthropic"
_MESSAGES_ENDPOINT = "https://api.anthropic.com/v1/messages"


@dataclass(frozen=True, slots=True)
class AnthropicConfig:
    model: str
    max_tokens: int
    timeout_seconds: float
    api_version: str = "2023-06-01"

    def __post_init__(self) -> None:
        for name in ("model", "api_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if type(self.max_tokens) is not int or self.max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        if type(self.timeout_seconds) not in (int, float) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class AnthropicProviderError(Exception):
    provider: str
    status_code: int | None
    error_type: str | None
    request_id: str | None
    retry_after_seconds: float | None
    retryable: bool
    detail: str

    def __str__(self) -> str:
        parts = [f"{self.provider} provider failure", self.detail]
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        if self.error_type is not None:
            parts.append(f"type={self.error_type}")
        if self.request_id is not None:
            parts.append(f"request_id={self.request_id}")
        return "; ".join(parts)


class _Transport(Protocol):
    def __call__(
        self,
        url: str,
        *,
        method: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> tuple[int, Mapping[str, str], bytes]: ...


def _urllib_transport(
    url: str,
    *,
    method: str,
    headers: Mapping[str, str],
    body: bytes,
    timeout_seconds: float,
) -> tuple[int, Mapping[str, str], bytes]:
    request = urllib_request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib_error.HTTPError as error:
        return error.code, dict(error.headers.items()) if error.headers else {}, error.read()
    except TimeoutError as error:
        raise TimeoutError("Anthropic transport timed out") from error
    except urllib_error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise TimeoutError("Anthropic transport timed out") from error
        raise ConnectionError("Anthropic transport connection failed") from error


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered and isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _retry_after(headers: Mapping[str, str]) -> float | None:
    value = _header(headers, "retry-after")
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def _retryable_status(status: int, error_type: str | None) -> bool:
    return status in (408, 429, 529) or 500 <= status <= 599 or error_type == "overloaded_error"


def _http_error(
    status: int,
    headers: Mapping[str, str],
    body: bytes,
) -> AnthropicProviderError:
    error_type: str | None = None
    try:
        envelope = json.loads(body)
        if isinstance(envelope, dict) and isinstance(envelope.get("error"), dict):
            error = envelope["error"]
            if isinstance(error.get("type"), str):
                error_type = error["type"]
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    return AnthropicProviderError(
        provider=_PROVIDER,
        status_code=status,
        error_type=error_type,
        request_id=_header(headers, "request-id") or _header(headers, "x-request-id"),
        retry_after_seconds=_retry_after(headers),
        retryable=_retryable_status(status, error_type),
        detail="provider rejected the request",
    )


def _malformed(detail: str, request_id: str | None) -> AnthropicProviderError:
    return AnthropicProviderError(
        provider=_PROVIDER,
        status_code=None,
        error_type="malformed_response",
        request_id=request_id,
        retry_after_seconds=None,
        retryable=False,
        detail=detail,
    )


def _parse_success(body: bytes, request_id: str | None) -> tuple[str | None, str, int, int]:
    try:
        value = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise _malformed("provider returned malformed JSON", request_id) from error
    if not isinstance(value, dict):
        raise _malformed("provider response must be a JSON object", request_id)
    model = value.get("model")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise _malformed("provider model must be a non-empty string", request_id)
    content = value.get("content")
    if not isinstance(content, list):
        raise _malformed("provider content must be an array", request_id)
    text_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            raise _malformed("provider content blocks must be objects", request_id)
        if block.get("type") == "text":
            text = block.get("text")
            if not isinstance(text, str):
                raise _malformed("provider text blocks must contain string text", request_id)
            if text:
                text_parts.append(text)
    if not text_parts:
        raise _malformed("provider response contained no usable text", request_id)
    usage = value.get("usage")
    if not isinstance(usage, dict):
        raise _malformed("provider usage must be an object", request_id)
    counts: list[int] = []
    for name in ("input_tokens", "output_tokens"):
        count = usage.get(name)
        if type(count) is not int or count < 0:
            raise _malformed(f"provider {name} must be a non-negative integer", request_id)
        counts.append(count)
    # Anthropic emits ordered text blocks; joining without a separator preserves their exact text.
    return model, "".join(text_parts), counts[0], counts[1]


@dataclass(frozen=True, slots=True)
class AnthropicModelClient:
    config: AnthropicConfig
    _transport: _Transport = field(default=_urllib_transport, repr=False)
    _clock: Callable[[], float] = field(default=perf_counter, repr=False)

    def complete(self, request: ModelRequest) -> ModelResponse:
        if not isinstance(request, ModelRequest):
            raise TypeError("request must be a ModelRequest")
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key is None or not api_key.strip():
            raise ValueError("ANTHROPIC_API_KEY must be set and non-blank")
        payload = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "system": request.system_instructions,
            "messages": [{"role": "user", "content": request.customer_message}],
            "stream": False,
        }
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers = {
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": self.config.api_version,
        }
        started = self._clock()
        try:
            status, response_headers, response_body = self._transport(
                _MESSAGES_ENDPOINT,
                method="POST",
                headers=headers,
                body=body,
                timeout_seconds=self.config.timeout_seconds,
            )
        except TimeoutError as error:
            raise AnthropicProviderError(
                _PROVIDER, None, "timeout", None, None, True, "transport timed out"
            ) from error
        except ConnectionError as error:
            raise AnthropicProviderError(
                _PROVIDER, None, "transport_failure", None, None, True, "transport connection failed"
            ) from error
        elapsed_ms = max(0.0, (self._clock() - started) * 1000)
        request_id = _header(response_headers, "request-id") or _header(response_headers, "x-request-id")
        if not 200 <= status <= 299:
            raise _http_error(status, response_headers, response_body)
        model, text, input_tokens, output_tokens = _parse_success(response_body, request_id)
        return ModelResponse(
            provider=_PROVIDER,
            model=model or self.config.model,
            response_text=text,
            input_token_count=input_tokens,
            output_token_count=output_tokens,
            latency_ms=elapsed_ms,
            # Pricing is deliberately omitted in this increment; no speculative catalog is embedded.
            estimated_cost_usd=0.0,
            request_id=request_id,
            synthetic=False,
        )
