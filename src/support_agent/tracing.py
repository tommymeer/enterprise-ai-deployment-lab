"""Small immutable, in-process workflow traces."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import TypeAlias

from .domain import StateSnapshot

TraceScalar: TypeAlias = str | int | float | bool | None
TraceValue: TypeAlias = TraceScalar | tuple[TraceScalar, ...]


def _empty_mapping() -> Mapping[str, TraceValue]:
    return MappingProxyType({})


def _immutable_mapping(
    value: Mapping[str, TraceValue], field_name: str
) -> Mapping[str, TraceValue]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    copied: dict[str, TraceValue] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if isinstance(item, list):
            item = tuple(item)
        if isinstance(item, tuple):
            if any(
                not isinstance(part, (str, int, float, bool, type(None)))
                for part in item
            ):
                raise ValueError(f"{field_name} values must be sanitized scalars")
        elif not isinstance(item, (str, int, float, bool, type(None))):
            raise ValueError(f"{field_name} values must be sanitized scalars")
        copied[key] = item
    return MappingProxyType(copied)


@dataclass(frozen=True, slots=True)
class WorkflowTraceEvent:
    trace_id: str
    sequence_number: int
    occurred_at: datetime
    step: str
    event_type: str
    case_id: str
    state_before: StateSnapshot | None = None
    state_after: StateSnapshot | None = None
    tool_name: str | None = None
    tool_arguments: Mapping[str, TraceValue] = field(default_factory=_empty_mapping)
    tool_result: Mapping[str, TraceValue] = field(default_factory=_empty_mapping)
    latency_ms: float | None = None
    retry_count: int = 0
    model_provider: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    evaluation_result: str | None = None
    escalation: bool | None = None
    human_override: bool | None = None
    final_outcome: str | None = None
    detail: str | None = None
    operation_id: str | None = None
    idempotency_key: str | None = None
    attempt_count: int | None = None
    operation_status: str | None = None

    def __post_init__(self) -> None:
        for name in ("trace_id", "step", "event_type", "case_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        for name in ("operation_id", "idempotency_key", "operation_status"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must not be empty when present")
        if self.attempt_count is not None and (
            type(self.attempt_count) is not int or self.attempt_count < 0
        ):
            raise ValueError("attempt_count must be non-negative when present")
        if type(self.sequence_number) is not int or self.sequence_number < 0:
            raise ValueError("sequence_number must be a non-negative integer")
        if not isinstance(self.occurred_at, datetime):
            raise ValueError("occurred_at must be a datetime")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.occurred_at.utcoffset() != UTC.utcoffset(self.occurred_at):
            raise ValueError("occurred_at must use UTC")
        if self.latency_ms is not None and (
            isinstance(self.latency_ms, bool)
            or not isinstance(self.latency_ms, (int, float))
            or self.latency_ms < 0
        ):
            raise ValueError("latency_ms must be non-negative when present")
        if type(self.retry_count) is not int or self.retry_count < 0:
            raise ValueError("retry_count must be a non-negative integer")
        for name in ("input_tokens", "output_tokens"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a non-negative integer when present")
        if self.estimated_cost_usd is not None and (
            isinstance(self.estimated_cost_usd, bool)
            or not isinstance(self.estimated_cost_usd, (int, float))
            or self.estimated_cost_usd < 0
        ):
            raise ValueError("estimated_cost_usd must be non-negative when present")
        for name in ("state_before", "state_after"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, StateSnapshot):
                raise ValueError(f"{name} must be a StateSnapshot when present")
        object.__setattr__(
            self,
            "tool_arguments",
            _immutable_mapping(self.tool_arguments, "tool_arguments"),
        )
        object.__setattr__(
            self, "tool_result", _immutable_mapping(self.tool_result, "tool_result")
        )


class WorkflowTraceCollector:
    """Append-only collector whose public event view is an immutable tuple."""

    def __init__(self, trace_id: str) -> None:
        if not isinstance(trace_id, str) or not trace_id.strip():
            raise ValueError("trace_id must not be empty")
        self._trace_id = trace_id
        self._events: list[WorkflowTraceEvent] = []

    @property
    def trace_id(self) -> str:
        return self._trace_id

    @property
    def events(self) -> tuple[WorkflowTraceEvent, ...]:
        return tuple(self._events)

    def append(
        self,
        *,
        occurred_at: datetime,
        step: str,
        event_type: str,
        case_id: str,
        **values: object,
    ) -> WorkflowTraceEvent:
        supplied_trace_id = values.pop("trace_id", self._trace_id)
        if supplied_trace_id != self._trace_id:
            raise ValueError("event trace_id must match collector trace_id")
        event = WorkflowTraceEvent(
            trace_id=self._trace_id,
            sequence_number=len(self._events),
            occurred_at=occurred_at,
            step=step,
            event_type=event_type,
            case_id=case_id,
            **values,  # type: ignore[arg-type]
        )
        self._events.append(event)
        return event
