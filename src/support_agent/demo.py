"""Truthful composition and view models for the support-agent interview demo."""
from __future__ import annotations

import os
from enum import Enum
from typing import Callable

from .anthropic_adapter import AnthropicConfig, AnthropicModelClient
from .extraction import ExtractionResult, extract_customer_message
from .extraction_scenarios import get_extraction_scenarios
from .modeling import ModelClient, ModelRequest, ModelResponse, RecordingModelClient, ScriptedModelClient
from .scenarios import get_support_case_scenario
from .synthetic_retailer import (SyntheticRetailerCarrierEvidenceLookup,
    SyntheticRetailerOrderLookup, SyntheticRetailerShipmentLookup, find_synthetic_order)
from .trajectory_evaluation import check_outcome, check_trajectory, concrete_evaluation_cases
from .workflow import (IntakeRoute, SyntheticAddressComparison, SyntheticCustomerLookup, TrustedIntakeContext,
    WorkflowConfiguration, route_customer_message_extraction)

DEMO_SCENARIO_IDS = ("refund-success", "refund-execution-failure")
DEMO_MODES = ("scripted", "live")
LIVE_MODEL, LIVE_MAX_TOKENS, LIVE_TIMEOUT_SECONDS = "claude-sonnet-5", 512, 30

def _value(value):
    if isinstance(value, Enum): return value.value
    if isinstance(value, tuple): return [_value(x) for x in value]
    return value

def _state(snapshot):
    if snapshot is None: return None
    return {"case_status": snapshot.case_status.value, "disposition": snapshot.disposition.value,
        "execution_status": snapshot.execution_status.value, "follow_up_status": snapshot.follow_up_status.value,
        "closed": snapshot.closed_at is not None}

def serialize_model_request(request: ModelRequest):
    return {"task_name": request.task_name, "prompt_version": request.prompt_version,
        "expected_schema_name": request.expected_schema_name, "customer_message": request.customer_message,
        "system_instructions": request.system_instructions}

def serialize_model_response(response: ModelResponse):
    return {"provider": response.provider, "model": response.model, "response_text": response.response_text,
        "synthetic": response.synthetic, "input_token_count": response.input_token_count,
        "output_token_count": response.output_token_count, "latency_ms": response.latency_ms,
        "estimated_cost_usd": response.estimated_cost_usd, "finish_reason": response.finish_reason,
        "request_id": response.request_id}

def _extraction(value):
    return {"original_message": value.original_message, "issue_type": value.issue_type.value,
        "order_identifier": value.order_identifier, "tracking_identifier": value.tracking_identifier,
        "customer_claims_package_missing": value.customer_claims_package_missing,
        "customer_claims_address_correct": value.customer_claims_address_correct,
        "missing_required_fields": list(value.missing_required_fields), "needs_clarification": value.needs_clarification,
        "clarification_reason": value.clarification_reason}

def _configuration(scenario, extracted_order_id):
    record = find_synthetic_order(extracted_order_id)
    address = record.address_match if record else scenario.address_match_result
    refund_amount = record.refund_amount_minor if record else 5_000
    return WorkflowConfiguration(SyntheticCustomerLookup(scenario.customer_reference), SyntheticRetailerOrderLookup(),
        SyntheticRetailerShipmentLookup(), SyntheticRetailerCarrierEvidenceLookup(),
        SyntheticAddressComparison(address), scenario.execution_results,
        scenario.selected_disposition, scenario.case_input.received_at, scenario.unresolved_policies,
        proposed_refund_amount_minor=refund_amount, proposed_refund_currency="USD",
        autonomous_refund_limit_minor=10_000, autonomous_refund_limit_currency="USD")

def demo_options(*, live_enabled=False):
    message = next(x.customer_message for x in get_extraction_scenarios() if x.scenario_id == "complete-order")
    execution_mode_labels = {
        "refund-success": "Normal execution",
        "refund-execution-failure": "Inject refund execution failure",
    }
    return {"scenarios": [{"id": sid, "title": execution_mode_labels[sid],
        "description": get_support_case_scenario(sid).description,
        "prompt": "Describe a delivered package you cannot find, including its order ID.",
        "customer_message": message} for sid in DEMO_SCENARIO_IDS],
        "modes": [{"id": "scripted", "label": "Offline — scripted extraction", "enabled": True, "message_editable": False},
            {"id": "live", "label": "Live — Claude extraction", "enabled": live_enabled, "message_editable": True}],
        "live_enabled": live_enabled, "default_mode": "live" if live_enabled else "scripted",
        "synthetic_order_examples": [
            {"order_id": "12345", "hint": "complete delivery evidence"},
            {"order_id": "24680", "hint": "a different carrier record"},
            {"order_id": "31415", "hint": "evidence needs a closer look"},
            {"order_id": "27182", "hint": "refund exceeds autonomous authority"},
        ], "unknown_order_hint": "Try an unknown ID to see the safe not-found path."}

def _technical(event):
    return {"sequence": event.sequence_number, "step": event.step, "event": event.event_type,
        "tool_name": event.tool_name, "arguments": {k:_value(v) for k,v in event.tool_arguments.items()},
        "result": {k:_value(v) for k,v in event.tool_result.items()}, "state_before": _state(event.state_before),
        "state_after": _state(event.state_after), "latency_ms": event.latency_ms, "retry_count": event.retry_count,
        "detail": event.detail, "evaluation_result": event.evaluation_result, "operation_id": event.operation_id,
        "idempotency_key": event.idempotency_key, "attempt_count": event.attempt_count,
        "operation_status": event.operation_status}

def _step(category, component, action, result, why, *, input=None, output=None, status=None, before=None, after=None, events=()):
    return {"category": category, "component": component, "action": action, "why": why,
        "result": result, "input": input or {}, "output": output or {}, "status": status,
        "state_changed": before != after and after is not None, "state_before": before, "state_after": after,
        "next": None, "technical_details": [_technical(x) for x in events]}

def _execution_trace(extraction: ExtractionResult, request, response, workflow):
    parsed = None if extraction.extraction is None else _extraction(extraction.extraction)
    if parsed is None:
        model_result = "Model output could not be accepted"
    elif parsed["needs_clarification"]:
        model_result = "Delivered-not-received issue · order ID missing"
    elif parsed["issue_type"] == "unknown":
        model_result = f'General-support issue · Order {parsed["order_identifier"]}'
    else:
        model_result = f'Delivered-not-received issue · Order {parsed["order_identifier"]}'
    rows = [_step("MODEL", "customer_message_extractor", "Interpret customer message", model_result,
        "Converts unstructured language into a bounded intake schema.",
        input={"customer_message": request.customer_message}, output=parsed or {"raw_response": response.response_text},
        status=extraction.status.value),
        _step("VALIDATION", "extraction_validator", "Validate structured extraction",
        "Passed" if extraction.trace.validation_succeeded else "Failed",
        "Prevents invalid or ungrounded model output from entering the trusted workflow.", input=parsed or {},
        output={"reason": extraction.validation_reason}, status="passed" if extraction.trace.validation_succeeded else "failed")]
    rows[0]["technical_details"] = [{"model_request": serialize_model_request(request),
        "model_response": serialize_model_response(response),
        "model_call": {"provider": response.provider, "model": response.model,
            "request_id": response.request_id, "input_tokens": response.input_token_count,
            "output_tokens": response.output_token_count, "latency_ms": response.latency_ms,
            "finish_reason": response.finish_reason}}]
    rows[1]["technical_details"] = [{"parsed_extraction": parsed,
        "validation_status": extraction.status.value,
        "parsing_succeeded": extraction.trace.parsing_succeeded,
        "validation_succeeded": extraction.trace.validation_succeeded,
        "validation_reason": extraction.validation_reason}]
    if workflow is None:
        rows[-1]["next"] = "Downstream workflow did not begin"; return rows
    events = workflow.trace_events
    labels = {"synthetic_customer_lookup": ("customer_lookup", "Find the customer in supported synthetic retailer data."),
        "synthetic_order_lookup": ("order_lookup", "Match the extracted identifier to the supported synthetic order."),
        "synthetic_shipment_lookup": ("shipment_lookup", "Retrieve shipment state for the matched order."),
        "synthetic_carrier_evidence_lookup": ("carrier_lookup", "Retrieve delivery evidence used by deterministic policy."),
        "synthetic_address_comparison": ("address_comparison", "Compare configured synthetic address evidence."),
        "synthetic_execution_adapter": ("execution_adapter", "Apply the approved action once using idempotency controls.")}
    for index,event in enumerate(events):
        if event.event_type != "tool_called": continue
        paired = next((x for x in events[index+1:] if x.tool_name == event.tool_name and x.event_type in {"tool_returned","modeled_operational_failure"}), None)
        if paired is None: continue
        component, why = labels.get(event.tool_name, (event.tool_name or event.step, "Execute the recorded dependency."))
        result = {k:_value(v) for k,v in paired.tool_result.items()}
        status = ("Succeeded" if result.get("succeeded") else "Failed") if component == "execution_adapter" else result.get("match_status") or result.get("retrieval_status") or "returned"
        readable = {"customer_lookup": "Customer found" if result.get("match_status") == "matched" else "Customer not found",
            "order_lookup": f'Order {extraction.extraction.order_identifier} found' if result.get("match_status") == "matched" else f'Order {extraction.extraction.order_identifier} not found',
            "shipment_lookup": "Shipment record found" if result.get("retrieval_status") == "success" else "Shipment record unavailable",
            "carrier_lookup": "Delivered event found · picture proof available" if result.get("evidence_present") else "No delivery evidence found",
            "address_comparison": "Address matches" if result.get("match_result") == "match" else "Address does not match",
            "execution_adapter": "Succeeded" if result.get("succeeded") else "Failed"}
        actions = {"customer_lookup":"Customer lookup", "order_lookup":"Order lookup",
            "shipment_lookup":"Shipment lookup", "carrier_lookup":"Carrier evidence lookup",
            "address_comparison":"Address comparison", "execution_adapter":"Execute refund"}
        grouped_events = [event, paired]
        if component == "execution_adapter":
            recorded = next((x for x in events[index+1:] if x.event_type == "execution_result_recorded"), None)
            if recorded is not None:
                grouped_events.append(recorded)
        rows.append(_step("ACTION" if component == "execution_adapter" else "TOOL", component,
            actions[component], readable[component], why,
            input={k:_value(v) for k,v in event.tool_arguments.items()}, output=result or {"detail": paired.detail},
            status=status, events=tuple(grouped_events)))
    meaningful = {"policy_route_recorded": ("POLICY","dnr_policy","Evaluate DNR eligibility","Checks whether required structural evidence is complete."),
        "disposition_selected": ("DISPOSITION","resolution_selector","Select resolution","Records resolution only after policy permits disposition."),
        "execution_authority_granted": ("AUTHORITY","refund_authority","Check autonomous refund authority","Prevents refunds above the configured autonomous limit."),
        "execution_authority_blocked": ("AUTHORITY","refund_authority","Check autonomous refund authority","Prevents refunds above the configured autonomous limit."),
        "execution_failure_routed": ("ESCALATION","human_review_router","Route to human review","Keeps a failed action open for a person."),
        "execution_completed": ("STATE","case_state","Close case","Closes only after successful execution.")}
    for event in events:
        if event.event_type not in meaningful: continue
        category,component,action,why = meaningful[event.event_type]
        output = {"detail": event.detail, "final_outcome": event.final_outcome}
        if event.event_type == "policy_route_recorded": output={"route":event.evaluation_result,"reason":"required structural evidence complete"}
        elif event.event_type == "disposition_selected": output={"disposition":workflow.final_disposition.value}
        elif event.event_type == "execution_authority_granted": output={"decision":"granted"}
        elif event.event_type == "execution_authority_blocked": output={"decision":"blocked","detail":event.detail}
        amount = event.tool_arguments.get("refund_amount_minor", 0)
        limit = event.tool_arguments.get("autonomous_limit_minor", 0)
        results = {"policy_route_recorded":"Eligible to proceed", "disposition_selected":"Approve refund",
            "execution_authority_granted":f"Granted · ${amount / 100:g} <= ${limit / 100:g}",
            "execution_authority_blocked":"Blocked · requires authorized human review",
            "execution_failure_routed":"Human review required · case remains open", "execution_completed":"Closed"}
        rows.append(_step(category,component,action,results[event.event_type],why,input={k:_value(v) for k,v in event.tool_arguments.items()},
            output=output,status=event.evaluation_result or event.final_outcome or event.event_type,
            before=_state(event.state_before),after=_state(event.state_after),events=(event,)))
    rows.sort(key=lambda x: -2 if x["category"]=="MODEL" else -1 if x["category"]=="VALIDATION" else x["technical_details"][0]["sequence"])
    for current,following in zip(rows,rows[1:]): current["next"] = f'{following["category"]}: {following["action"]}'
    rows[-1]["next"]="End of case run"
    # Readable rows are a projection; retain the complete underlying event stream in
    # the final row so grouping never reduces trace fidelity.
    rows[-1]["technical_details"].append({"raw_workflow_trace": [_technical(event) for event in events]})
    return rows

def _customer_outcome(route, workflow, order_id):
    if workflow is None:
        values={IntakeRoute.MANUAL_INTAKE_REVIEW_REQUIRED:("Needs manual review","We could not safely interpret the request. The automated workflow did not start."),
            IntakeRoute.CLARIFICATION_REQUIRED:("More information needed","Please provide a valid order identifier so we can continue."),
            IntakeRoute.GENERAL_TRIAGE_REQUIRED:("Sent to general support","This message does not match the supported delivered-package workflow.")}
        title,message=values[route]; return {"title":title,"message":message}
    final=workflow.case.snapshot()
    if final.execution_status.value=="succeeded" and final.closed_at is not None:
        return {"title":"Refund processed","message":f"We confirmed order {order_id} was marked delivered. Your refund was approved and processed."}
    if final.execution_status.value=="failed":
        return {"title":"Escalated for human review","message":f"The refund for order {order_id} was approved, but automatic execution failed. Your case remains open for human review."}
    if final.case_status.value == "awaiting_customer_action":
        if workflow.failure_stage == "order_lookup":
            return {"title":"Order not found","message":f"We could not find order {order_id} in the supported retailer records. No refund action was taken, and the case remains open."}
        return {"title":"More evidence needed","message":f"We found order {order_id}, but do not have enough delivery evidence to complete an automated resolution. The case remains open."}
    if workflow.failure_stage == "authority":
        return {"title":"Escalated for authorized review","message":f"The proposed refund for order {order_id} exceeds the agent's autonomous authority. No refund was executed."}
    return {"title":"Case remains open","message":f"The automated workflow for order {order_id} stopped without completing an action."}

def eval_evidence():
    scenarios={x.scenario_id:x for x in get_extraction_scenarios()}
    good=extract_customer_message(scenarios["complete-order"].customer_message,ScriptedModelClient(scenarios["complete-order"].response))
    guard=extract_customer_message(scenarios["invented-order"].customer_message,ScriptedModelClient(scenarios["invented-order"].response))
    name,result,expected,altered=concrete_evaluation_cases()[6]
    return {"examples":[{"title":"Extraction robustness","source":"extraction fixture: complete-order","input":scenarios["complete-order"].customer_message,
        "expected":{"issue_type":"delivered_not_received","order_identifier":"12345"},"actual":_extraction(good.extraction),"passed":good.status.value=="complete"},
        {"title":"Hallucination / invalid identifier control","source":"extraction fixture: invented-order","input":scenarios["invented-order"].customer_message,
        "expected":"Validator rejects an identifier not grounded in the input","actual":guard.validation_reason,"passed":guard.status.value=="invalid_model_output"},
        {"title":"Trajectory control","source":f"trajectory fixture: {name}","input":"A deliberately reordered trace puts execution before disposition.",
        "expected":"Outcome evaluator passes; trajectory evaluator fails.","actual":{"outcome_failures":list(check_outcome(result,expected)),"trajectory_failures":list(check_trajectory(result,altered))},
        "passed":not check_outcome(result,expected) and bool(check_trajectory(result,altered))}],
        "note":"Examples are computed from existing deterministic fixtures; no provider call is made."}

def _live_client():
    if not os.environ.get("ANTHROPIC_API_KEY","").strip(): raise ValueError("ANTHROPIC_API_KEY must be set and non-blank before live mode can run")
    return AnthropicModelClient(AnthropicConfig(LIVE_MODEL,LIVE_MAX_TOKENS,LIVE_TIMEOUT_SECONDS,disable_thinking=True))

def run_demo(scenario_id, customer_message=None, *, mode="scripted", live_enabled=False, live_client_factory: Callable[[],ModelClient]=_live_client):
    if scenario_id not in DEMO_SCENARIO_IDS: raise KeyError(f"unsupported demo scenario: {scenario_id}")
    if mode not in DEMO_MODES: raise ValueError(f"unsupported extraction mode: {mode}")
    scenario=get_support_case_scenario(scenario_id); fixture=next(x for x in get_extraction_scenarios() if x.scenario_id=="complete-order")
    if mode=="scripted":
        if customer_message not in (None,fixture.customer_message): raise ValueError("offline scripted mode requires the locked scenario fixture message")
        message,client=fixture.customer_message,ScriptedModelClient(fixture.response)
    else:
        if not live_enabled: raise ValueError("live Claude extraction is disabled; start the server with --enable-live")
        if not isinstance(customer_message,str) or not customer_message.strip(): raise ValueError("live mode requires a non-empty customer message")
        message,client=customer_message,live_client_factory()
    recorder=RecordingModelClient(client)
    extraction_result=extract_customer_message(message,recorder) # Provider failures stop before routing.
    request,response=recorder.calls[0]
    order_id=extraction_result.extraction.order_identifier if extraction_result.extraction else scenario.order_reference.ref_id
    record=find_synthetic_order(order_id or "")
    shipment_id=record.shipment.ref_id if record else scenario.case_input.shipment_identifier
    trusted=TrustedIntakeContext(scenario.case_input.case_id,scenario.case_input.customer_identifier,shipment_id,scenario.case_input.actor,scenario.case_input.received_at)
    routed=route_customer_message_extraction(extraction_result,trusted,_configuration(scenario,order_id or scenario.order_reference.ref_id))
    workflow=routed.workflow_result
    return {"scenario":{"id":scenario_id,"title":scenario.title,"description":scenario.description},
        "mode":{"id":mode,"label":"Scripted extraction" if mode=="scripted" else "Live Claude extraction","synthetic":mode=="scripted"},
        "boundaries":["Offline extraction is scripted for the locked scenario fixture." if mode=="scripted" else "Live mode makes one Claude extraction call and never falls back to scripted output.","Retailer lookups and execution are synthetic adapters, not production integrations."],
        "customer_message":message,"customer_outcome":_customer_outcome(routed.route,workflow,order_id),
        "model":{"request":serialize_model_request(request),"response":serialize_model_response(response),
            "parsed_extraction":None if extraction_result.extraction is None else _extraction(extraction_result.extraction),
            "validation":{"status":extraction_result.status.value,"parsing_succeeded":extraction_result.trace.parsing_succeeded,
                "validation_succeeded":extraction_result.trace.validation_succeeded,"reason":extraction_result.validation_reason}},
        "intake_route":routed.route.value,"execution_trace":_execution_trace(extraction_result,request,response,workflow),
        "final_state":None if workflow is None else _state(workflow.case.snapshot()),"eval_evidence":eval_evidence()}
