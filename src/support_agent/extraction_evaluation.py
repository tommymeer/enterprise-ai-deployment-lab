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
    source_case_id: str | None = None
    transformation: str | None = None


@dataclass(frozen=True, slots=True)
class FieldComparison:
    field_name: str
    expected: object
    actual: object
    matched: bool


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


@dataclass(frozen=True, slots=True)
class ExtractionFailureAttribution:
    primary_failure_layer: str
    supporting_evidence: str
    likely_remedy: str


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


def get_hard_extraction_eval_cases() -> tuple[ExtractionEvalCase, ...]:
    """Return manually specified cases for identifier roles and literal claims."""
    messages = {
        "stale_quoted_order": (
            "My current order ORD-2401 shows delivered, but it is not here. "
            'Previous email: "Order ORD-1399 was delivered last month."'
        ),
        "tracking_before_order": (
            "Tracking **TRK-2402** says delivered; the order is (ORD-2402), "
            "and I cannot find the package."
        ),
        "corrected_order": (
            "Order ORD-2403—sorry, that is the wrong number. The correct order is "
            "ORD-2404; it says delivered and is missing."
        ),
        "dense_number_roles": (
            "Customer ID 884211 called on 08/14 about 3 items; phone ending 0199. "
            "Tracking TRK-2405 belongs to order ORD-2405, which shows delivered, "
            "but the package is missing."
        ),
        "number_prose_without_ids": (
            "I do not have the order or tracking number. Customer 4821 called on "
            "August 14 about 3 items; the package shows delivered but is not here."
        ),
        "unsupported_address_inference": (
            "Order ORD-2406 shows delivered to 18 Pine St, but the package is not "
            "here. I never said whether the address on my order was correct."
        ),
    }
    return (
        ExtractionEvalCase("stale_quoted_order", messages["stale_quoted_order"], _expected(messages["stale_quoted_order"], order_identifier="ORD-2401")),
        ExtractionEvalCase("tracking_before_order", messages["tracking_before_order"], _expected(messages["tracking_before_order"], order_identifier="ORD-2402", tracking_identifier="TRK-2402")),
        ExtractionEvalCase("corrected_order", messages["corrected_order"], _expected(messages["corrected_order"], order_identifier="ORD-2404")),
        ExtractionEvalCase("dense_number_roles", messages["dense_number_roles"], _expected(messages["dense_number_roles"], order_identifier="ORD-2405", tracking_identifier="TRK-2405")),
        ExtractionEvalCase("number_prose_without_ids", messages["number_prose_without_ids"], _expected(messages["number_prose_without_ids"], order_identifier=None)),
        ExtractionEvalCase("unsupported_address_inference", messages["unsupported_address_inference"], _expected(messages["unsupported_address_inference"], order_identifier="ORD-2406")),
    )


def get_semantic_robustness_eval_cases() -> tuple[ExtractionEvalCase, ...]:
    """Return four meaning-preserving variants of five frozen canonical cases."""
    canonical = {case.case_id: case for case in get_extraction_eval_cases()}
    variants = {
        "missing_order": {
            "paraphrased": "My parcel never arrived, although the carrier marked it delivered.",
            "facts_reordered": "My package is missing, but the carrier says it was delivered.",
            "irrelevant_detail": (
                "The carrier says delivered, but my package is missing. I noticed while making coffee."
            ),
            "different_verbosity": "Marked delivered; package missing.",
        },
        "unknown_issue": {
            "paraphrased": "Could you swap the size on order ORD-1003?",
            "facts_reordered": "For order ORD-1003, please change the size.",
            "irrelevant_detail": (
                "Please change the size for order ORD-1003. The item arrived in a blue box."
            ),
            "different_verbosity": (
                "I am contacting support because I would like the size of the item associated with "
                "order ORD-1003 changed to a different size."
            ),
        },
        "order_and_tracking": {
            "paraphrased": (
                "I cannot locate the parcel for order ORD-1005 even though tracking TRK-5005 marks it delivered."
            ),
            "facts_reordered": (
                "I do not have it; tracking TRK-5005 says delivered for order ORD-1005."
            ),
            "irrelevant_detail": (
                "Order ORD-1005, tracking TRK-5005, says delivered; I do not have it. It was due before lunch."
            ),
            "different_verbosity": "ORD-1005 / TRK-5005: delivered, but missing.",
        },
        "multiple_identifiers": {
            "paraphrased": (
                "Customer 7712 reports that the parcel on invoice 4408 for order A-9006 has not arrived."
            ),
            "facts_reordered": (
                "The package for invoice 4408 is missing; this is customer 7712 asking about order A-9006."
            ),
            "irrelevant_detail": (
                "Customer 7712 asks about order A-9006; invoice 4408 says its package is missing. The box was brown."
            ),
            "different_verbosity": (
                "I am customer 7712, and I am reaching out about the shipment connected to invoice "
                "4408 and order A-9006 because the package has not arrived."
            ),
        },
        "explicit_address_correct": {
            "paraphrased": (
                "Order ORD-1008 went to the wrong place despite my having supplied the correct address."
            ),
            "facts_reordered": (
                "The address I provided was correct, yet order ORD-1008 was delivered elsewhere."
            ),
            "irrelevant_detail": (
                "Order ORD-1008 was delivered elsewhere even though my address was correct. I checked after dinner."
            ),
            "different_verbosity": (
                "I carefully reviewed the address that I entered for order ORD-1008 and confirmed it was "
                "correct, but the shipment was nevertheless delivered to a different location."
            ),
        },
    }
    cases = []
    for source_case_id, transformations in variants.items():
        source = canonical[source_case_id]
        for transformation, message in transformations.items():
            cases.append(
                ExtractionEvalCase(
                    case_id=f"{source_case_id}__{transformation}",
                    customer_message=message,
                    expected=replace(source.expected, original_message=message),
                    source_case_id=source_case_id,
                    transformation=transformation,
                )
            )
    return tuple(cases)


def compare_extractions(
    expected: CustomerMessageExtraction, actual: CustomerMessageExtraction
) -> tuple[FieldComparison, ...]:
    """Compare contract fields, allowing only the reason's specified wording variance."""
    return tuple(
        FieldComparison(
            field.name,
            getattr(expected, field.name),
            getattr(actual, field.name),
            (
                clarification_reason_matches(
                    expected.needs_clarification,
                    expected.order_identifier,
                    actual.clarification_reason,
                )
                if field.name == "clarification_reason"
                else getattr(expected, field.name) == getattr(actual, field.name)
            ),
        )
        for field in fields(CustomerMessageExtraction)
    )


def clarification_reason_matches(
    needs_clarification: bool,
    order_identifier: str | None,
    clarification_reason: str | None,
) -> bool:
    """Apply the contract's deterministic rule for clarification-reason grading."""
    if not needs_clarification:
        return clarification_reason is None
    if order_identifier is not None:
        return False
    reason = clarification_reason
    if not isinstance(reason, str) or not reason.strip():
        return False
    words = set(reason.lower().replace("-", " ").split())
    refers_to_order_identifier = {"order", "identifier"} <= words
    explains_missing_or_required = bool(
        words & {"missing", "absent", "required"}
        or "not provided" in reason.lower()
        or ("needed" in words and "not needed" not in reason.lower())
    )
    return refers_to_order_identifier and explains_missing_or_required


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


def attribute_extraction_failure(
    result: ExtractionEvalResult,
) -> ExtractionFailureAttribution | None:
    """Give a small preliminary attribution for an observed extraction failure."""
    if result.semantic_match is True:
        return None
    if not result.valid_output:
        return ExtractionFailureAttribution(
            primary_failure_layer="model interpretation",
            supporting_evidence=(
                "The model response failed the extraction contract: "
                f"{result.extraction_result.validation_reason}"
            ),
            likely_remedy=(
                "Inspect the raw response and prompt adherence; change the task specification "
                "only if multiple failures show the instruction is ambiguous."
            ),
        )
    mismatches = ", ".join(item.field_name for item in result.differing_fields)
    return ExtractionFailureAttribution(
        primary_failure_layer="model interpretation",
        supporting_evidence=f"Valid output disagreed with ground truth on: {mismatches}.",
        likely_remedy=(
            "Inspect the message, expected value, and raw response together; repair the grader "
            "only if the actual value is semantically valid under the nine-field contract."
        ),
    )


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


def run_scripted_hard_extraction_eval() -> tuple[ExtractionEvalResult, ...]:
    """Run exact hard-case answers and grounded, schema-valid semantic mistakes."""
    cases = {case.case_id: case for case in get_hard_extraction_eval_cases()}
    attempts = [
        evaluate_extraction_case(case, scripted_response(case.expected))
        for case in cases.values()
    ]
    wrong = (
        ("wrong_stale_quoted_order", "stale_quoted_order", {"order_identifier": "ORD-1399"}),
        ("wrong_swapped_identifier_roles", "tracking_before_order", {"order_identifier": "TRK-2402", "tracking_identifier": "ORD-2402"}),
        ("wrong_retracted_order", "corrected_order", {"order_identifier": "ORD-2403"}),
        ("wrong_customer_as_order", "dense_number_roles", {"order_identifier": "884211"}),
        ("wrong_number_as_order", "number_prose_without_ids", {"order_identifier": "4821", "missing_required_fields": (), "needs_clarification": False, "clarification_reason": None}),
        ("wrong_address_inference", "unsupported_address_inference", {"customer_claims_address_correct": True}),
    )
    for attempt_id, case_id, changes in wrong:
        case = cases[case_id]
        result = evaluate_extraction_case(
            case, scripted_response(replace(case.expected, **changes))
        )
        attempts.append(replace(result, case_id=attempt_id))
    return tuple(attempts)


def run_scripted_semantic_robustness_eval() -> tuple[ExtractionEvalResult, ...]:
    """Run all semantic variants with their unchanged canonical structured facts."""
    return tuple(
        evaluate_extraction_case(case, scripted_response(case.expected))
        for case in get_semantic_robustness_eval_cases()
    )
