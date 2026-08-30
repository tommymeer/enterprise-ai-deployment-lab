"""Allowlisted composition for the two-case offline interview demo."""

from __future__ import annotations

from enum import Enum

from .extraction import extract_customer_message
from .extraction_evaluation import (
    run_scripted_extraction_eval,
    run_scripted_hard_extraction_eval,
    run_scripted_semantic_robustness_eval,
)
from .extraction_scenarios import get_extraction_scenarios
from .modeling import ModelRequest, ModelResponse, RecordingModelClient, ScriptedModelClient
from .scenarios import get_support_case_scenario
from .trajectory_evaluation import check_outcome, check_trajectory, concrete_evaluation_cases
from .workflow import (
    SyntheticAddressComparison, SyntheticCarrierEvidenceLookup,
    SyntheticCustomerLookup, SyntheticOrderLookup, SyntheticShipmentLookup,
    TrustedIntakeContext, WorkflowConfiguration, route_customer_message_extraction,
)

DEMO_SCENARIO_IDS = ("refund-success", "refund-execution-failure")


def _value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_value(item) for item in value]
    return value


def _state(snapshot: object | None) -> dict[str, object] | None:
    if snapshot is None:
        return None
    return {
        "case_status": snapshot.case_status.value,
        "disposition": snapshot.disposition.value,
        "execution_status": snapshot.execution_status.value,
        "follow_up_status": snapshot.follow_up_status.value,
        "closed": snapshot.closed_at is not None,
    }


def serialize_model_request(request: ModelRequest) -> dict[str, object]:
    return {
        "task_name": request.task_name,
        "prompt_version": request.prompt_version,
        "expected_schema_name": request.expected_schema_name,
        "customer_message": request.customer_message,
        "system_instructions": request.system_instructions,
    }


def serialize_model_response(response: ModelResponse) -> dict[str, object]:
    return {
        "provider": response.provider, "model": response.model,
        "response_text": response.response_text,
        "synthetic": response.synthetic, "input_token_count": response.input_token_count,
        "output_token_count": response.output_token_count, "latency_ms": response.latency_ms,
        "estimated_cost_usd": response.estimated_cost_usd,
        "finish_reason": response.finish_reason, "request_id": response.request_id,
    }


def _extraction(value: object) -> dict[str, object]:
    return {
        "original_message": value.original_message, "issue_type": value.issue_type.value,
        "order_identifier": value.order_identifier, "tracking_identifier": value.tracking_identifier,
        "customer_claims_package_missing": value.customer_claims_package_missing,
        "customer_claims_address_correct": value.customer_claims_address_correct,
        "missing_required_fields": list(value.missing_required_fields),
        "needs_clarification": value.needs_clarification,
        "clarification_reason": value.clarification_reason,
    }


def _configuration(scenario):
    return WorkflowConfiguration(
        SyntheticCustomerLookup(scenario.customer_reference),
        SyntheticOrderLookup(scenario.order_reference),
        SyntheticShipmentLookup(scenario.shipment_reference),
        SyntheticCarrierEvidenceLookup(scenario.carrier_evidence),
        SyntheticAddressComparison(scenario.address_match_result),
        scenario.execution_results, scenario.selected_disposition,
        scenario.case_input.received_at, scenario.unresolved_policies,
        proposed_refund_amount_minor=5_000, proposed_refund_currency="USD",
        autonomous_refund_limit_minor=10_000, autonomous_refund_limit_currency="USD",
    )


def demo_options() -> dict[str, object]:
    return {"scenarios": [
        {"id": item, "title": get_support_case_scenario(item).title,
         "description": get_support_case_scenario(item).description}
        for item in DEMO_SCENARIO_IDS
    ], "mode": "scripted/offline", "input_editable": False}


def eval_evidence() -> dict[str, object]:
    extraction = run_scripted_extraction_eval()
    hard = run_scripted_hard_extraction_eval()
    semantic = run_scripted_semantic_robustness_eval()
    trajectory = concrete_evaluation_cases()
    trajectory_passes = sum(
        not check_outcome(result, expected) and not check_trajectory(result, event_names)
        for _, result, expected, event_names in trajectory
    )
    return {
        "computed_now_offline": True,
        "items": [
            {"label": "Extraction contract + validation", "result": f"{sum(x.valid_output and x.semantic_match is True for x in extraction)}/{len(extraction)} pass"},
            {"label": "Hard extraction cases", "result": f"{sum(x.valid_output and x.semantic_match is True for x in hard)}/{len(hard)} pass"},
            {"label": "Semantic robustness", "result": f"{sum(x.valid_output and x.semantic_match is True for x in semantic)}/{len(semantic)} pass"},
            {"label": "Outcome vs trajectory + authorization controls + safe stops", "result": f"{trajectory_passes}/{len(trajectory)} pass"},
        ],
        "note": "These are deterministic offline checks computed in-process; no live evaluation or full unit-test subprocess runs here.",
    }


def run_demo(scenario_id: str) -> dict[str, object]:
    if scenario_id not in DEMO_SCENARIO_IDS:
        raise KeyError(f"unsupported demo scenario: {scenario_id}")
    scenario = get_support_case_scenario(scenario_id)
    extraction_case = next(x for x in get_extraction_scenarios() if x.scenario_id == "complete-order")
    recorder = RecordingModelClient(ScriptedModelClient(extraction_case.response))
    extraction_result = extract_customer_message(extraction_case.customer_message, recorder)
    request, response = recorder.calls[0]
    routed = route_customer_message_extraction(
        extraction_result,
        TrustedIntakeContext(scenario.case_input.case_id, scenario.case_input.customer_identifier,
            scenario.case_input.shipment_identifier, scenario.case_input.actor, scenario.case_input.received_at),
        _configuration(scenario),
    )
    workflow = routed.workflow_result
    if workflow is None or extraction_result.extraction is None:
        raise RuntimeError("fixed demo extraction did not enter the workflow")
    case = workflow.case
    trace_rows = []
    for event in workflow.trace_events:
        trace_rows.append({
            "source": "workflow_trace", "sequence": event.sequence_number,
            "step": event.step, "event": event.event_type,
            "input": {key: _value(value) for key, value in event.tool_arguments.items()},
            "output": {key: _value(value) for key, value in event.tool_result.items()},
            "state_before": _state(event.state_before), "state_after": _state(event.state_after),
            "status": event.evaluation_result or event.operation_status,
            "latency_ms": event.latency_ms, "detail": event.detail,
            "operation_id": event.operation_id, "idempotency_key": event.idempotency_key,
            "attempt_count": event.attempt_count,
        })
    transitions = [row for row in trace_rows if row["state_before"] != row["state_after"] and row["state_after"]]
    evidence = [row for row in trace_rows if row["event"] == "tool_returned"]
    policy = case.policy_evaluation_results[-1]
    authority = next(row for row in trace_rows if row["step"] == "authority")
    operation = workflow.execution_operation
    return {
        "scenario": {"id": scenario_id, "title": scenario.title, "description": scenario.description},
        "honesty": ["Extraction is scripted/offline in this demo.", "It uses the same ModelClient boundary as the real Anthropic adapter.", "Synthetic evidence and adapters stand in for retailer systems; this is not a production retailer integration.", "The customer message is fixed by the selected scenario and is not presented as arbitrary LLM interpretation."],
        "raw_input": extraction_case.customer_message,
        "model_request": serialize_model_request(request), "raw_model_output": serialize_model_response(response),
        "structured_extraction": _extraction(extraction_result.extraction),
        "validation": {"status": extraction_result.status.value, "parsing_succeeded": extraction_result.trace.parsing_succeeded, "validation_succeeded": extraction_result.trace.validation_succeeded, "reason": extraction_result.validation_reason},
        "intake_route": routed.route.value,
        "state": {"final": _state(case.snapshot()), "completed": workflow.completed, "failure_stage": workflow.failure_stage, "failure_reason": workflow.failure_reason, "transitions": transitions},
        "evidence": evidence,
        "policy": {"route": policy.route.value, "reasons": list(policy.reasons), "unresolved_policies": [x.value for x in policy.unresolved_policies]},
        "disposition": workflow.final_disposition.value,
        "authorization": authority,
        "execution": None if operation is None else {"operation_id": operation.operation_id, "idempotency_key": operation.idempotency_key, "status": operation.status.value, "attempt_count": operation.attempt_count, "result_detail": operation.result_detail},
        "human_review": {"required": case.case_status.value == "human_review", "requests": len(case.human_review_requests), "decisions": len(case.human_review_decisions)},
        "trace_rows": trace_rows, "eval_evidence": eval_evidence(),
    }
