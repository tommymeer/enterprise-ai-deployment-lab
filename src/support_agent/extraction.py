"""Deterministic validation around customer-message extraction proposals."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .modeling import ModelClient, ModelRequest, ModelResponse


EXTRACTION_PROMPT_VERSION = "customer-report-extraction-v3"
EXTRACTION_SCHEMA_NAME = "CustomerMessageExtraction"
_SUPPORTED_MISSING_FIELDS = frozenset({"order_identifier"})
_SCHEMA_KEYS = frozenset(
    {
        "original_message",
        "issue_type",
        "order_identifier",
        "tracking_identifier",
        "customer_claims_package_missing",
        "customer_claims_address_correct",
        "missing_required_fields",
        "needs_clarification",
        "clarification_reason",
    }
)
_SYSTEM_INSTRUCTIONS = """Extract exactly one customer message as raw JSON. Output all nine keys below;
do not add, remove, rename, or nest fields. Do not use Markdown fences or prose.

Required fields and exact allowed types:
- original_message: string, copied exactly from the supplied customer message
- issue_type: exactly "delivered_not_received" or "unknown"
- order_identifier: string or null
- tracking_identifier: string or null
- customer_claims_package_missing: boolean or null
- customer_claims_address_correct: boolean or null
- missing_required_fields: array containing only "order_identifier", or empty
- needs_clarification: boolean
- clarification_reason: nonempty string when clarification is needed, otherwise null

Concrete JSON template:
{"original_message":"<copy the supplied customer message exactly>","issue_type":"unknown","order_identifier":null,"tracking_identifier":null,"customer_claims_package_missing":null,"customer_claims_address_correct":null,"missing_required_fields":["order_identifier"],"needs_clarification":true,"clarification_reason":"<brief reason the order identifier is required>"}
Angle-bracket strings are instructions/placeholders. Replace them with values grounded in the
supplied message; do not copy the placeholder text literally.

Never invent identifiers; an identifier must appear literally in the customer message.
order_identifier is required for a complete extraction. When it is absent, set order_identifier to
null, include "order_identifier" in missing_required_fields, set needs_clarification to true, and
provide a nonempty clarification_reason. When clarification is not needed,
missing_required_fields must be [] and clarification_reason must be null.
Customer claim fields represent what the customer says, not verified truth.
Do not decide policy, eligibility, fraud, refund, replacement, or action."""


class ExtractionIssueType(StrEnum):
    DELIVERED_NOT_RECEIVED = "delivered_not_received"
    UNKNOWN = "unknown"


class ExtractionStatus(StrEnum):
    COMPLETE = "complete"
    NEEDS_CLARIFICATION = "needs_clarification"
    INVALID_MODEL_OUTPUT = "invalid_model_output"


@dataclass(frozen=True, slots=True)
class CustomerMessageExtraction:
    original_message: str
    issue_type: ExtractionIssueType
    order_identifier: str | None
    tracking_identifier: str | None
    customer_claims_package_missing: bool | None
    customer_claims_address_correct: bool | None
    missing_required_fields: tuple[str, ...]
    needs_clarification: bool
    clarification_reason: str | None

    def __post_init__(self) -> None:
        reason = _validate_values(
            self.original_message,
            self.issue_type,
            self.order_identifier,
            self.tracking_identifier,
            self.customer_claims_package_missing,
            self.customer_claims_address_correct,
            self.missing_required_fields,
            self.needs_clarification,
            self.clarification_reason,
        )
        if reason is not None:
            raise ValueError(reason)


@dataclass(frozen=True, slots=True)
class ExtractionTrace:
    prompt_version: str
    provider: str
    model: str
    parsing_succeeded: bool
    validation_succeeded: bool
    input_token_count: int
    output_token_count: int
    latency_ms: float
    estimated_cost_usd: float
    clarification_required: bool | None
    synthetic: bool


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    status: ExtractionStatus
    original_message: str
    extraction: CustomerMessageExtraction | None
    validation_reason: str | None
    trace: ExtractionTrace

    def __post_init__(self) -> None:
        if not isinstance(self.status, ExtractionStatus):
            raise ValueError("status must be an ExtractionStatus")
        if self.status is ExtractionStatus.INVALID_MODEL_OUTPUT:
            if self.extraction is not None or not self.validation_reason:
                raise ValueError("invalid output requires a reason and no extraction")
        elif self.extraction is None or self.validation_reason is not None:
            raise ValueError("valid output requires an extraction and no reason")
        if self.extraction is not None and self.extraction.original_message != self.original_message:
            raise ValueError("result message must match extraction")


@dataclass(frozen=True, slots=True)
class _ExtractionProposal:
    original_message: str
    issue_type: ExtractionIssueType
    order_identifier: str | None
    tracking_identifier: str | None
    customer_claims_package_missing: bool | None
    customer_claims_address_correct: bool | None
    missing_required_fields: tuple[str, ...]
    needs_clarification: bool
    clarification_reason: str | None


def build_customer_report_extraction_request(customer_message: str) -> ModelRequest:
    return ModelRequest(
        task_name="customer_message_extraction",
        prompt_version=EXTRACTION_PROMPT_VERSION,
        system_instructions=_SYSTEM_INSTRUCTIONS,
        customer_message=customer_message,
        expected_schema_name=EXTRACTION_SCHEMA_NAME,
    )


def _parse_response(response: ModelResponse) -> Mapping[str, Any]:
    if response.response_text is not None:
        parsed = json.loads(_normalize_response_text(response.response_text))
    else:
        parsed = response.structured_payload
    if not isinstance(parsed, Mapping):
        raise ValueError("model output must be a JSON object")
    return parsed


def _normalize_response_text(response_text: str) -> str:
    """Unwrap one exact whole-response JSON fence while leaving its contents intact."""
    trimmed = response_text.strip()
    match = re.fullmatch(r"```(?:json)?\r?\n([\s\S]*)\r?\n```", trimmed)
    return match.group(1) if match is not None else trimmed


def _to_proposal(value: Mapping[str, Any]) -> _ExtractionProposal:
    keys = set(value)
    if keys != _SCHEMA_KEYS:
        detail = "schema keys do not match"
        if _SCHEMA_KEYS - keys:
            detail += "; required keys are missing"
        if keys - _SCHEMA_KEYS:
            detail += "; unsupported keys are present"
        raise ValueError(detail)

    def nullable_string(name: str) -> str | None:
        item = value[name]
        if item is not None and not isinstance(item, str):
            raise ValueError(f"{name} must be a string or null")
        return item

    def nullable_bool(name: str) -> bool | None:
        item = value[name]
        if item is not None and type(item) is not bool:
            raise ValueError(f"{name} must be a boolean or null")
        return item

    if not isinstance(value["original_message"], str):
        raise ValueError("original_message must be a string")
    if not isinstance(value["issue_type"], str):
        raise ValueError("issue_type must be a string")
    try:
        issue_type = ExtractionIssueType(value["issue_type"])
    except ValueError as error:
        raise ValueError("issue_type is unsupported") from error
    missing = value["missing_required_fields"]
    if not isinstance(missing, (list, tuple)) or any(not isinstance(item, str) for item in missing):
        raise ValueError("missing_required_fields must be an array of strings")
    if type(value["needs_clarification"]) is not bool:
        raise ValueError("needs_clarification must be a boolean")
    return _ExtractionProposal(
        value["original_message"],
        issue_type,
        nullable_string("order_identifier"),
        nullable_string("tracking_identifier"),
        nullable_bool("customer_claims_package_missing"),
        nullable_bool("customer_claims_address_correct"),
        tuple(missing),
        value["needs_clarification"],
        nullable_string("clarification_reason"),
    )


def _identifier_is_grounded(identifier: str, message: str) -> bool:
    # Boundaries prevent a short ID such as 123 from matching an unrelated 12345 token.
    pattern = rf"(?<![A-Za-z0-9]){re.escape(identifier)}(?![A-Za-z0-9])"
    return re.search(pattern, message) is not None


def _validate_values(
    original_message: str,
    issue_type: object,
    order_identifier: object,
    tracking_identifier: object,
    package_missing: object,
    address_correct: object,
    missing_fields: object,
    needs_clarification: object,
    clarification_reason: object,
) -> str | None:
    if not isinstance(original_message, str) or not original_message.strip():
        return "original_message must not be empty"
    if not isinstance(issue_type, ExtractionIssueType):
        return "issue_type is unsupported"
    for name, identifier in (("order_identifier", order_identifier), ("tracking_identifier", tracking_identifier)):
        if identifier is not None:
            if not isinstance(identifier, str) or not identifier.strip():
                return f"{name} must be non-empty when present"
            if not _identifier_is_grounded(identifier, original_message):
                return f"{name} is not literally grounded in the customer message"
    for name, claim in (("customer_claims_package_missing", package_missing), ("customer_claims_address_correct", address_correct)):
        if claim is not None and type(claim) is not bool:
            return f"{name} must be a boolean or null"
    if issue_type is ExtractionIssueType.DELIVERED_NOT_RECEIVED and package_missing is False:
        return "delivered_not_received contradicts a false package-missing claim"
    if not isinstance(missing_fields, tuple) or any(not isinstance(item, str) for item in missing_fields):
        return "missing_required_fields must be an immutable tuple of strings"
    if len(set(missing_fields)) != len(missing_fields):
        return "missing_required_fields must not contain duplicates"
    unsupported = set(missing_fields) - _SUPPORTED_MISSING_FIELDS
    if unsupported:
        return "missing_required_fields contains an unsupported field"
    if type(needs_clarification) is not bool:
        return "needs_clarification must be a boolean"
    if order_identifier is None:
        if "order_identifier" not in missing_fields or not needs_clarification:
            return "missing order_identifier requires clarification"
    elif "order_identifier" in missing_fields:
        return "present order_identifier cannot also be missing"
    if needs_clarification:
        if not isinstance(clarification_reason, str) or not clarification_reason.strip():
            return "clarification_reason is required when clarification is needed"
        if not missing_fields:
            return "clarification requires missing_required_fields"
    elif missing_fields or clarification_reason is not None:
        return "complete extraction cannot contain clarification fields"
    return None


def _validate_proposal(proposal: _ExtractionProposal, supplied_message: str) -> CustomerMessageExtraction:
    if proposal.original_message != supplied_message:
        raise ValueError("original_message does not exactly match supplied input")
    reason = _validate_values(
        proposal.original_message,
        proposal.issue_type,
        proposal.order_identifier,
        proposal.tracking_identifier,
        proposal.customer_claims_package_missing,
        proposal.customer_claims_address_correct,
        proposal.missing_required_fields,
        proposal.needs_clarification,
        proposal.clarification_reason,
    )
    if reason is not None:
        raise ValueError(reason)
    return CustomerMessageExtraction(
        proposal.original_message,
        proposal.issue_type,
        proposal.order_identifier,
        proposal.tracking_identifier,
        proposal.customer_claims_package_missing,
        proposal.customer_claims_address_correct,
        proposal.missing_required_fields,
        proposal.needs_clarification,
        proposal.clarification_reason,
    )


def _trace(response: ModelResponse, parsed: bool, validated: bool, clarification: bool | None) -> ExtractionTrace:
    return ExtractionTrace(
        EXTRACTION_PROMPT_VERSION,
        response.provider,
        response.model,
        parsed,
        validated,
        response.input_token_count,
        response.output_token_count,
        response.latency_ms,
        response.estimated_cost_usd,
        clarification,
        response.synthetic,
    )


def extract_customer_message(customer_message: str, client: ModelClient) -> ExtractionResult:
    """Run the visible request, parse, convert, and validation sequence."""
    if not isinstance(customer_message, str):
        raise TypeError("customer_message must be a string")
    try:
        request = build_customer_report_extraction_request(customer_message)
    except ValueError as error:
        # No model call is made for invalid caller input, so use explicit local metadata.
        local = ModelResponse("local", "input-validation", response_text="{}")
        return ExtractionResult(
            ExtractionStatus.INVALID_MODEL_OUTPUT,
            customer_message,
            None,
            str(error),
            _trace(local, False, False, None),
        )
    response = client.complete(request)
    parsed = False
    try:
        payload = _parse_response(response)
        parsed = True
        proposal = _to_proposal(payload)
        extraction = _validate_proposal(proposal, customer_message)
    except ValueError as error:
        return ExtractionResult(
            ExtractionStatus.INVALID_MODEL_OUTPUT,
            customer_message,
            None,
            str(error),
            _trace(response, parsed, False, None),
        )
    status = (
        ExtractionStatus.NEEDS_CLARIFICATION
        if extraction.needs_clarification
        else ExtractionStatus.COMPLETE
    )
    return ExtractionResult(
        status,
        customer_message,
        extraction,
        None,
        _trace(response, True, True, extraction.needs_clarification),
    )
