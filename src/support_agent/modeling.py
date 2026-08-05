"""Small provider-neutral records for bounded local model tasks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol, TypeAlias


ModelPayloadValue: TypeAlias = str | bool | None | tuple[str, ...]


def _non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class ModelRequest:
    task_name: str
    prompt_version: str
    system_instructions: str
    customer_message: str
    expected_schema_name: str

    def __post_init__(self) -> None:
        for name in (
            "task_name",
            "prompt_version",
            "system_instructions",
            "customer_message",
            "expected_schema_name",
        ):
            _non_empty(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class ModelResponse:
    provider: str
    model: str
    response_text: str | None = None
    structured_payload: Mapping[str, ModelPayloadValue] | None = None
    input_token_count: int = 0
    output_token_count: int = 0
    latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0
    request_id: str | None = None
    synthetic: bool = True

    def __post_init__(self) -> None:
        _non_empty(self.provider, "provider")
        _non_empty(self.model, "model")
        if (self.response_text is None) == (self.structured_payload is None):
            raise ValueError("exactly one response body must be supplied")
        if self.response_text is not None and not isinstance(self.response_text, str):
            raise ValueError("response_text must be a string")
        if self.structured_payload is not None:
            if not isinstance(self.structured_payload, Mapping):
                raise ValueError("structured_payload must be a mapping")
            copied: dict[str, ModelPayloadValue] = {}
            for key, value in self.structured_payload.items():
                if isinstance(value, list):
                    value = tuple(value)
                copied[key] = value  # type: ignore[assignment]
            object.__setattr__(self, "structured_payload", MappingProxyType(copied))
        for name in ("input_token_count", "output_token_count"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name in ("latency_ms", "estimated_cost_usd"):
            value = getattr(self, name)
            if type(value) not in (int, float) or value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.request_id is not None:
            _non_empty(self.request_id, "request_id")
        if type(self.synthetic) is not bool:
            raise ValueError("synthetic must be a bool")


class ModelClient(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse: ...


@dataclass(frozen=True, slots=True)
class ScriptedModelClient:
    """Return one predetermined response and retain requests for inspection."""

    response: ModelResponse
    _requests: list[ModelRequest] = field(default_factory=list, init=False, repr=False)

    @property
    def requests(self) -> tuple[ModelRequest, ...]:
        return tuple(self._requests)

    def complete(self, request: ModelRequest) -> ModelResponse:
        if not isinstance(request, ModelRequest):
            raise TypeError("request must be a ModelRequest")
        self._requests.append(request)
        return self.response
