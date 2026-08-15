"""Tiny offline field-level evaluation for customer-message extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, replace

from .extraction import (
    CustomerMessageExtraction,
    ExtractionIssueType,
    ExtractionResult,
    ExtractionStatus,
    extract_customer_message,
)
from .modeling import ModelResponse, ScriptedModelClient


@dataclass(frozen=True, slots=True)
class ExtractionEvalCase:
    case_id: str
    customer_message: str
    expected: CustomerMessageExtraction


@dataclass(frozen=True, slots=True)
class FieldComparison:
    field_name: str
    expected: object
    actual: object

    @property
    def matched(self) -> bool:
        return self.expected == self.actual


@dataclass(frozen=True, slots=True)
class ExtractionEvalResult:
    case_id: str
    extraction_result: ExtractionResult
    field_comparisons: tuple[FieldComparison, ...]

    @property
    def valid_output(self) -> bool:
        return self.extraction_result.status is not ExtractionStatus.INVALID_MODEL_OUTPUT

    @property
    def semantic_match(self) -> bool | None:
        if not self.valid_output:
            return None
        return all(comparison.matched for comparison in self.field_comparisons)

    @property
    def differing_fields(self) -> tuple[FieldComparison, ...]:
        return tuple(item for item in self.field_comparisons if not item.matched)


def _expected(
    message: str,
    *,
    issue_type: ExtractionIssueType = ExtractionIssueType.DELIVERED_NOT_RECEIVED,
    order_identifier: str | None,
    tracking_identifier: str | None = None,
    package_missing: bool | None = True,
    address_correct: bool | None = None,
) -> CustomerMessageExtraction:
    missing_order = order_identifier is None
    return CustomerMessageExtraction(
        original_message=message,
        issue_type=issue_type,
        order_identifier=order_identifier,
        tracking_identifier=tracking_identifier,
        customer_claims_package_missing=package_missing,
        customer_claims_address_correct=address_correct,
        missing_required_fields=("order_identifier",) if missing_order else (),
        needs_clarification=missing_order,
        clarification_reason=(
            "Order identifier was not provided." if missing_order else None
        ),
    )


def get_extraction_eval_cases() -> tuple[ExtractionEvalCase, ...]:
    """Return ten synthetic cases whose expected fields were chosen by inspection."""
    messages = {
        "clear_dnr_order": "Order ORD-1001 says delivered, but the package is not here.",
        "missing_order": "The carrier says delivered, but my package is missing.",
        "unknown_issue": "Please change the size for order ORD-1003.",
        "vague_with_order": "Something is wrong with order ORD-1004.",
        "order_and_tracking": "Order ORD-1005, tracking TRK-5005, says delivered; I do not have it.",
        "multiple_identifiers": "Customer 7712 asks about order A-9006; invoice 4408 says its package is missing.",
        "explicit_missing": "I am explicitly reporting that package for order ORD-1007 is missing.",
        "explicit_address_correct": "Order ORD-1008 was delivered elsewhere even though the address I gave was correct.",
        "no_address_claim": "My package for order ORD-1009 shows delivered and is not here.",
        "no_inference": "The courier photographed a blue door for order ORD-1010; my package is not here.",
    }
    return (
        ExtractionEvalCase("clear_dnr_order", messages["clear_dnr_order"], _expected(messages["clear_dnr_order"], order_identifier="ORD-1001")),
        ExtractionEvalCase("missing_order", messages["missing_order"], _expected(messages["missing_order"], order_identifier=None)),
        ExtractionEvalCase("unknown_issue", messages["unknown_issue"], _expected(messages["unknown_issue"], issue_type=ExtractionIssueType.UNKNOWN, order_identifier="ORD-1003", package_missing=None)),
        ExtractionEvalCase("vague_with_order", messages["vague_with_order"], _expected(messages["vague_with_order"], issue_type=ExtractionIssueType.UNKNOWN, order_identifier="ORD-1004", package_missing=None)),
        ExtractionEvalCase("order_and_tracking", messages["order_and_tracking"], _expected(messages["order_and_tracking"], order_identifier="ORD-1005", tracking_identifier="TRK-5005")),
        ExtractionEvalCase("multiple_identifiers", messages["multiple_identifiers"], _expected(messages["multiple_identifiers"], order_identifier="A-9006")),
        ExtractionEvalCase("explicit_missing", messages["explicit_missing"], _expected(messages["explicit_missing"], order_identifier="ORD-1007")),
        ExtractionEvalCase("explicit_address_correct", messages["explicit_address_correct"], _expected(messages["explicit_address_correct"], order_identifier="ORD-1008", address_correct=True)),
        ExtractionEvalCase("no_address_claim", messages["no_address_claim"], _expected(messages["no_address_claim"], order_identifier="ORD-1009")),
        ExtractionEvalCase("no_inference", messages["no_inference"], _expected(messages["no_inference"], order_identifier="ORD-1010")),
    )


def compare_extractions(
    expected: CustomerMessageExtraction, actual: CustomerMessageExtraction
) -> tuple[FieldComparison, ...]:
    """Compare every current contract field using exact equality."""
    return tuple(
        FieldComparison(field.name, getattr(expected, field.name), getattr(actual, field.name))
        for field in fields(CustomerMessageExtraction)
    )


def evaluate_extraction_case(
    case: ExtractionEvalCase, response: ModelResponse
) -> ExtractionEvalResult:
    result = extract_customer_message(case.customer_message, ScriptedModelClient(response))
    comparisons = (
        compare_extractions(case.expected, result.extraction)
        if result.extraction is not None
        else ()
    )
    return ExtractionEvalResult(case.case_id, result, comparisons)


def scripted_response(extraction: CustomerMessageExtraction) -> ModelResponse:
    payload: dict[str, object] = {}
    for field in fields(CustomerMessageExtraction):
        value = getattr(extraction, field.name)
        payload[field.name] = (
            value.value
            if isinstance(value, ExtractionIssueType)
            else list(value)
            if isinstance(value, tuple)
            else value
        )
    return ModelResponse("synthetic", "scripted-extractor-v1", response_text=json.dumps(payload))


def run_scripted_extraction_eval() -> tuple[ExtractionEvalResult, ...]:
    """Run exact answers plus intentionally invalid and semantically wrong contrasts."""
    cases = {case.case_id: case for case in get_extraction_eval_cases()}
    attempts = []
    for case_id in ("clear_dnr_order", "missing_order", "unknown_issue", "order_and_tracking", "explicit_missing"):
        case = cases[case_id]
        attempts.append(evaluate_extraction_case(case, scripted_response(case.expected)))

    case = cases["vague_with_order"]
    attempts.append(evaluate_extraction_case(case, scripted_response(replace(case.expected, issue_type=ExtractionIssueType.DELIVERED_NOT_RECEIVED, customer_claims_package_missing=True))))

    case = cases["multiple_identifiers"]
    attempts.append(evaluate_extraction_case(case, scripted_response(replace(case.expected, order_identifier="7712"))))

    case = cases["explicit_address_correct"]
    attempts.append(evaluate_extraction_case(case, scripted_response(replace(case.expected, customer_claims_address_correct=None))))

    case = cases["no_inference"]
    attempts.append(evaluate_extraction_case(case, scripted_response(replace(case.expected, customer_claims_address_correct=False))))

    case = cases["no_address_claim"]
    bad_payload = json.loads(scripted_response(case.expected).response_text or "{}")
    bad_payload["order_identifier"] = "ORD-9999"
    invalid = evaluate_extraction_case(case, ModelResponse("synthetic", "scripted-extractor-v1", response_text=json.dumps(bad_payload)))
    attempts.append(replace(invalid, case_id="hallucinated_order"))
    return tuple(attempts)
