from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from support_agent import (
    CustomerMessageExtraction,
    ExtractionIssueType,
    ExtractionStatus,
    ModelResponse,
    ScriptedModelClient,
    build_customer_report_extraction_request,
    extract_customer_message,
)
from support_agent.extraction_scenarios import get_extraction_scenarios


def proposal(message: str, **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "original_message": message,
        "issue_type": "delivered_not_received",
        "order_identifier": "ORD-12345",
        "tracking_identifier": None,
        "customer_claims_package_missing": True,
        "customer_claims_address_correct": None,
        "missing_required_fields": [],
        "needs_clarification": False,
        "clarification_reason": None,
    }
    value.update(changes)
    return value


class ExtractionTest(unittest.TestCase):
    message = "It says delivered but is missing. Order ORD-12345."

    def run_payload(self, value: object, **metadata: object):
        response = ModelResponse(
            "synthetic",
            "scripted-v1",
            response_text=value if isinstance(value, str) else json.dumps(value),
            **metadata,
        )
        client = ScriptedModelClient(response)
        return extract_customer_message(self.message, client), client

    def test_public_record_validates_and_is_immutable(self) -> None:
        record = CustomerMessageExtraction(
            self.message, ExtractionIssueType.DELIVERED_NOT_RECEIVED, "ORD-12345",
            None, True, None, (), False, None,
        )
        with self.assertRaises(FrozenInstanceError):
            record.issue_type = ExtractionIssueType.UNKNOWN  # type: ignore[misc]
        with self.assertRaises(ValueError):
            CustomerMessageExtraction(self.message, ExtractionIssueType.UNKNOWN, None, None, None, None, (), False, None)

    def test_prompt_is_deterministic_inspectable_and_bounded(self) -> None:
        first = build_customer_report_extraction_request(self.message)
        self.assertEqual(first, build_customer_report_extraction_request(self.message))
        self.assertEqual(first.prompt_version, "customer-report-extraction-v1")
        self.assertEqual(first.customer_message, self.message)
        for text in ("never invent identifiers", "customer claims", "null", "unknown", "refund", "final action"):
            self.assertIn(text, first.system_instructions)

    def test_scripted_client_receives_exact_request(self) -> None:
        result, client = self.run_payload(proposal(self.message))
        self.assertEqual(result.status, ExtractionStatus.COMPLETE)
        self.assertEqual(client.requests, (build_customer_report_extraction_request(self.message),))

    def test_json_parsing_is_explicit_and_complete_output_is_accepted(self) -> None:
        result, _ = self.run_payload(json.dumps(proposal(self.message)))
        self.assertEqual(result.status, ExtractionStatus.COMPLETE)
        self.assertTrue(result.trace.parsing_succeeded)
        self.assertEqual(result.extraction.order_identifier, "ORD-12345")  # type: ignore[union-attr]

    def test_structured_mapping_is_also_supported_and_copied(self) -> None:
        payload = proposal(self.message)
        response = ModelResponse("synthetic", "scripted-v1", structured_payload=payload)  # type: ignore[arg-type]
        payload["issue_type"] = "changed"
        result = extract_customer_message(self.message, ScriptedModelClient(response))
        self.assertEqual(result.status, ExtractionStatus.COMPLETE)
        with self.assertRaises(TypeError):
            response.structured_payload["x"] = "y"  # type: ignore[index,union-attr]

    def test_missing_order_requests_clarification(self) -> None:
        value = proposal(self.message, order_identifier=None, missing_required_fields=["order_identifier"], needs_clarification=True, clarification_reason="Please provide the order identifier.")
        result, _ = self.run_payload(value)
        self.assertEqual(result.status, ExtractionStatus.NEEDS_CLARIFICATION)
        self.assertTrue(result.extraction.needs_clarification)  # type: ignore[union-attr]

    def test_invented_and_substring_identifiers_are_rejected(self) -> None:
        for identifier in ("ORD-99999", "1234"):
            with self.subTest(identifier=identifier):
                result, _ = self.run_payload(proposal(self.message, order_identifier=identifier))
                self.assertEqual(result.status, ExtractionStatus.INVALID_MODEL_OUTPUT)
                self.assertIsNone(result.extraction)
                self.assertEqual(result.original_message, self.message)

    def test_malformed_json_is_rejected_safely(self) -> None:
        result, _ = self.run_payload("{broken")
        self.assertEqual(result.status, ExtractionStatus.INVALID_MODEL_OUTPUT)
        self.assertFalse(result.trace.parsing_succeeded)

    def test_wrong_types_are_rejected(self) -> None:
        for change in ({"customer_claims_package_missing": 1}, {"missing_required_fields": "order_identifier"}, {"needs_clarification": 1}):
            with self.subTest(change=change):
                result, _ = self.run_payload(proposal(self.message, **change))
                self.assertEqual(result.status, ExtractionStatus.INVALID_MODEL_OUTPUT)

    def test_unexpected_internal_type_error_propagates(self) -> None:
        client = ScriptedModelClient(
            ModelResponse("synthetic", "scripted-v1", response_text=json.dumps(proposal(self.message)))
        )
        with patch("support_agent.extraction._to_proposal", side_effect=TypeError("programming defect")):
            with self.assertRaisesRegex(TypeError, "programming defect"):
                extract_customer_message(self.message, client)

    def test_client_runtime_error_propagates(self) -> None:
        provider_error = RuntimeError("provider unavailable")

        class FailingClient:
            def complete(self, request):
                raise provider_error

        with self.assertRaises(RuntimeError) as raised:
            extract_customer_message(self.message, FailingClient())  # type: ignore[arg-type]
        self.assertIs(raised.exception, provider_error)

    def test_missing_extra_keys_and_unsupported_labels_are_rejected(self) -> None:
        missing = proposal(self.message)
        del missing["tracking_identifier"]
        for value in (missing, proposal(self.message, extra="no"), proposal(self.message, issue_type="refund_request")):
            with self.subTest(value=value):
                result, _ = self.run_payload(value)
                self.assertEqual(result.status, ExtractionStatus.INVALID_MODEL_OUTPUT)

    def test_contradictory_clarification_fields_are_rejected(self) -> None:
        values = (
            proposal(self.message, missing_required_fields=["order_identifier"]),
            proposal(self.message, needs_clarification=True, clarification_reason="reason"),
            proposal(self.message, clarification_reason="unexpected"),
            proposal(self.message, customer_claims_package_missing=False),
        )
        for value in values:
            with self.subTest(value=value):
                result, _ = self.run_payload(value)
                self.assertEqual(result.status, ExtractionStatus.INVALID_MODEL_OUTPUT)

    def test_changed_original_input_is_rejected_and_raw_input_preserved(self) -> None:
        result, _ = self.run_payload(proposal(self.message + " changed"))
        self.assertEqual(result.status, ExtractionStatus.INVALID_MODEL_OUTPUT)
        self.assertEqual(result.original_message, self.message)
        self.assertIsNone(result.extraction)

    def test_metadata_is_retained_and_synthetic_cost_is_zero(self) -> None:
        result, _ = self.run_payload(proposal(self.message), input_token_count=41, output_token_count=19, latency_ms=2.5)
        self.assertEqual(result.trace.input_token_count, 41)
        self.assertEqual(result.trace.output_token_count, 19)
        self.assertEqual(result.trace.latency_ms, 2.5)
        self.assertEqual(result.trace.estimated_cost_usd, 0.0)
        self.assertTrue(result.trace.synthetic)
        self.assertNotIn(self.message, repr(result.trace))

    def test_empty_input_is_rejected_before_model_call(self) -> None:
        client = ScriptedModelClient(ModelResponse("synthetic", "scripted-v1", response_text="{}"))
        result = extract_customer_message("   ", client)
        self.assertEqual(result.status, ExtractionStatus.INVALID_MODEL_OUTPUT)
        self.assertEqual(client.requests, ())

    def test_all_twelve_curated_scenarios_have_expected_outcomes(self) -> None:
        scenarios = get_extraction_scenarios()
        self.assertEqual(len(scenarios), 12)
        self.assertEqual({scenario.expected_status for scenario in scenarios}, set(ExtractionStatus))
        for scenario in scenarios:
            with self.subTest(scenario=scenario.scenario_id):
                result = extract_customer_message(scenario.customer_message, ScriptedModelClient(scenario.response))
                self.assertEqual(result.status, scenario.expected_status)

    def test_boundary_modules_have_no_network_or_provider_sdk_imports(self) -> None:
        import support_agent.extraction as extraction_module
        import support_agent.modeling as modeling_module
        for module in (extraction_module, modeling_module):
            source = Path(module.__file__).read_text(encoding="utf-8")
            for forbidden in ("anthropic", "openai", "requests", "httpx", "urllib", "socket", "subprocess"):
                self.assertNotIn(f"import {forbidden}", source)


if __name__ == "__main__":
    unittest.main()
