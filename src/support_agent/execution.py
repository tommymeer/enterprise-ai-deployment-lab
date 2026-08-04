"""Local idempotency controls for consequential support-case execution."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
from uuid import uuid4

from .domain import Disposition


EXECUTABLE_DISPOSITIONS = frozenset(
    {
        Disposition.APPROVE_REFUND,
        Disposition.APPROVE_REPLACEMENT,
        Disposition.OPEN_CARRIER_INQUIRY,
    }
)


class OperationStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def _non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _utc(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must use UTC")


def generate_idempotency_key(case_id: str, disposition: Disposition) -> str:
    """Return the stable identity of one real-world support-case action."""
    _non_empty(case_id, "case_id")
    if not isinstance(disposition, Disposition):
        raise ValueError("disposition must be a Disposition")
    if disposition not in EXECUTABLE_DISPOSITIONS:
        raise ValueError(f"{disposition} is not executable")
    return f"support-case:{case_id}:{disposition.value}"


@dataclass(frozen=True, slots=True)
class ExecutionOperation:
    operation_id: str
    idempotency_key: str
    case_id: str
    disposition: Disposition
    requested_at: datetime
    status: OperationStatus
    result_detail: str | None
    attempt_count: int

    def __post_init__(self) -> None:
        for name in ("operation_id", "idempotency_key", "case_id"):
            _non_empty(getattr(self, name), name)
        if not isinstance(self.disposition, Disposition):
            raise ValueError("disposition must be a Disposition")
        if self.disposition not in EXECUTABLE_DISPOSITIONS:
            raise ValueError("disposition must be executable")
        if self.idempotency_key != generate_idempotency_key(
            self.case_id, self.disposition
        ):
            raise ValueError("idempotency key does not match case and disposition")
        _utc(self.requested_at, "requested_at")
        if not isinstance(self.status, OperationStatus):
            raise ValueError("status must be an OperationStatus")
        if type(self.attempt_count) is not int or self.attempt_count < 0:
            raise ValueError("attempt_count must be a non-negative integer")
        if self.status is OperationStatus.NOT_STARTED:
            if self.attempt_count != 0 or self.result_detail is not None:
                raise ValueError("not-started operations cannot have attempts or results")
        elif self.attempt_count < 1:
            raise ValueError("attempted operations require a positive attempt_count")
        if self.status in {OperationStatus.SUCCEEDED, OperationStatus.FAILED}:
            _non_empty(self.result_detail or "", "result_detail")
        elif self.result_detail is not None:
            raise ValueError("unfinished operations cannot have result detail")


class ExecutionRegistry:
    """In-process operation store with explicit, validated state changes.

    Production use needs durable storage plus an atomic uniqueness/concurrency control
    around each idempotency key. This local registry intentionally provides neither.
    """

    def __init__(self) -> None:
        self._operations: dict[str, ExecutionOperation] = {}

    @property
    def operations(self) -> Mapping[str, ExecutionOperation]:
        return MappingProxyType(dict(self._operations))

    def get(self, idempotency_key: str) -> ExecutionOperation | None:
        _non_empty(idempotency_key, "idempotency_key")
        return self._operations.get(idempotency_key)

    def get_or_create(
        self,
        idempotency_key: str,
        case_id: str,
        disposition: Disposition,
        requested_at: datetime,
    ) -> tuple[ExecutionOperation, bool]:
        expected = generate_idempotency_key(case_id, disposition)
        _non_empty(idempotency_key, "idempotency_key")
        if idempotency_key != expected:
            raise ValueError("idempotency key does not match case and disposition")
        existing = self._operations.get(idempotency_key)
        if existing is not None:
            if existing.case_id != case_id or existing.disposition is not disposition:
                raise ValueError("idempotency key is already assigned to another operation")
            return existing, False
        operation = ExecutionOperation(
            str(uuid4()), idempotency_key, case_id, disposition, requested_at,
            OperationStatus.NOT_STARTED, None, 0,
        )
        self._operations[idempotency_key] = operation
        return operation, True

    def start_attempt(self, idempotency_key: str) -> ExecutionOperation:
        operation = self._required(idempotency_key)
        if operation.status is OperationStatus.SUCCEEDED:
            raise ValueError("successful operations cannot be re-executed")
        if operation.status is OperationStatus.IN_PROGRESS:
            raise ValueError("operation already has an attempt in progress")
        updated = replace(
            operation,
            status=OperationStatus.IN_PROGRESS,
            result_detail=None,
            attempt_count=operation.attempt_count + 1,
        )
        self._operations[idempotency_key] = updated
        return updated

    def record_success(self, idempotency_key: str, detail: str) -> ExecutionOperation:
        return self._finish(idempotency_key, OperationStatus.SUCCEEDED, detail)

    def record_failure(self, idempotency_key: str, detail: str) -> ExecutionOperation:
        return self._finish(idempotency_key, OperationStatus.FAILED, detail)

    def _finish(
        self, idempotency_key: str, status: OperationStatus, detail: str
    ) -> ExecutionOperation:
        operation = self._required(idempotency_key)
        if operation.status is not OperationStatus.IN_PROGRESS:
            raise ValueError("only an in-progress operation can be completed")
        updated = replace(operation, status=status, result_detail=detail)
        self._operations[idempotency_key] = updated
        return updated

    def _required(self, idempotency_key: str) -> ExecutionOperation:
        operation = self.get(idempotency_key)
        if operation is None:
            raise KeyError(idempotency_key)
        return operation
