"""Curated synthetic fixtures for the deterministic extraction boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .extraction import ExtractionStatus
from .modeling import ModelResponse


@dataclass(frozen=True, slots=True)
class ExtractionScenario:
    scenario_id: str
    customer_message: str
    response: ModelResponse
    expected_status: ExtractionStatus


def _payload(message: str, **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "original_message": message,
        "issue_type": "delivered_not_received",
        "order_identifier": None,
        "tracking_identifier": None,
        "customer_claims_package_missing": True,
        "customer_claims_address_correct": None,
        "missing_required_fields": ["order_identifier"],
        "needs_clarification": True,
        "clarification_reason": "Order identifier was not provided.",
    }
    value.update(changes)
    return value


def _response(payload: object) -> ModelResponse:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return ModelResponse("synthetic", "scripted-extractor-v1", response_text=text)


_MESSAGES = {
    "clear": "My package says delivered, but I cannot find it. Order 12345.",
    "missing": "The carrier says delivered, but the package is not here.",
    "both": "Order ORD-2002 and tracking TRK-9009 show delivered; I cannot find the box.",
    "ambiguous": "Something is wrong with my package and I need help.",
    "syntax": "Delivered it says; package, nowhere. My order is ORD-3003.",
    "numbers": "I ordered 2 items on July 7. Order: ORD-7007 is missing.",
    "unsupported": "I want to change the color on order ORD-8008.",
    "invented": "My delivered package is missing. Order ORD-9009.",
    "wrong": "Order ORD-1010 says delivered, but it is missing.",
    "contradictory": "My package is missing. Order ORD-1111.",
}


EXTRACTION_SCENARIOS = (
    ExtractionScenario("complete-order", _MESSAGES["clear"], _response(_payload(_MESSAGES["clear"], order_identifier="12345", missing_required_fields=[], needs_clarification=False, clarification_reason=None)), ExtractionStatus.COMPLETE),
    ExtractionScenario("clarify-order", _MESSAGES["missing"], _response(_payload(_MESSAGES["missing"])), ExtractionStatus.NEEDS_CLARIFICATION),
    ExtractionScenario("order-and-tracking", _MESSAGES["both"], _response(_payload(_MESSAGES["both"], order_identifier="ORD-2002", tracking_identifier="TRK-9009", missing_required_fields=[], needs_clarification=False, clarification_reason=None)), ExtractionStatus.COMPLETE),
    ExtractionScenario("ambiguous-complaint", _MESSAGES["ambiguous"], _response(_payload(_MESSAGES["ambiguous"], issue_type="unknown", customer_claims_package_missing=None)), ExtractionStatus.NEEDS_CLARIFICATION),
    ExtractionScenario("difficult-syntax", _MESSAGES["syntax"], _response(_payload(_MESSAGES["syntax"], order_identifier="ORD-3003", missing_required_fields=[], needs_clarification=False, clarification_reason=None)), ExtractionStatus.COMPLETE),
    ExtractionScenario("multiple-numbers", _MESSAGES["numbers"], _response(_payload(_MESSAGES["numbers"], order_identifier="ORD-7007", missing_required_fields=[], needs_clarification=False, clarification_reason=None)), ExtractionStatus.COMPLETE),
    ExtractionScenario("unsupported-mapped-unknown", _MESSAGES["unsupported"], _response(_payload(_MESSAGES["unsupported"], issue_type="unknown", order_identifier="ORD-8008", customer_claims_package_missing=None, missing_required_fields=[], needs_clarification=False, clarification_reason=None)), ExtractionStatus.COMPLETE),
    ExtractionScenario("invented-order", _MESSAGES["invented"], _response(_payload(_MESSAGES["invented"], order_identifier="ORD-9999", missing_required_fields=[], needs_clarification=False, clarification_reason=None)), ExtractionStatus.INVALID_MODEL_OUTPUT),
    ExtractionScenario("malformed-json", "My package is missing.", _response("{not-json"), ExtractionStatus.INVALID_MODEL_OUTPUT),
    ExtractionScenario("wrong-field-type", _MESSAGES["wrong"], _response(_payload(_MESSAGES["wrong"], order_identifier=1010, missing_required_fields=[], needs_clarification=False, clarification_reason=None)), ExtractionStatus.INVALID_MODEL_OUTPUT),
    ExtractionScenario("contradictory-clarification", _MESSAGES["contradictory"], _response(_payload(_MESSAGES["contradictory"], order_identifier="ORD-1111")), ExtractionStatus.INVALID_MODEL_OUTPUT),
    ExtractionScenario("empty-message", "   ", _response({}), ExtractionStatus.INVALID_MODEL_OUTPUT),
)


def get_extraction_scenarios() -> tuple[ExtractionScenario, ...]:
    return EXTRACTION_SCENARIOS
