"""Truthful composition and view models for the support-agent interview demo."""
from __future__ import annotations

import os
from enum import Enum
from types import MappingProxyType
from typing import Callable

from .anthropic_adapter import AnthropicConfig, AnthropicModelClient
from .extraction import ExtractionResult, extract_customer_message
from .extraction_evaluation import (evaluate_extraction_case, get_extraction_eval_cases,
    run_scripted_semantic_robustness_eval, scripted_response)
from .extraction_scenarios import get_extraction_scenarios
from .failures import (evaluate_failure_regression_case, get_failure_regression_case,
    get_failure_regression_cases, run_failure_regression_case)
from .modeling import ModelClient, ModelRequest, ModelResponse, RecordingModelClient, ScriptedModelClient
from .scenarios import get_support_case_scenario
from .synthetic_retailer import (SyntheticRetailerCarrierEvidenceLookup,
    SyntheticRetailerOrderLookup, SyntheticRetailerShipmentLookup, find_synthetic_order)
from .trajectory_evaluation import check_outcome, check_trajectory, concrete_evaluation_cases
from .domain import CustomerReference, MatchStatus, RetrievalStatus
from .workflow import (DeterministicAddressComparison, IntakeRoute, SyntheticCustomerLookup, TrustedIntakeContext,
    WorkflowConfiguration, route_customer_message_extraction)

DEMO_SCENARIO_IDS = ("refund-success", "refund-execution-failure")
DEMO_MODES = ("scripted", "live")
LIVE_MODEL, LIVE_MAX_TOKENS, LIVE_TIMEOUT_SECONDS = "claude-sonnet-5", 512, 30

# Synthetic support-channel facts are deliberately separate from retailer order records.
# Equal values represent customer confirmation, not a value copied from the order lookup.
SYNTHETIC_CUSTOMER_CONFIRMED_ADDRESSES = MappingProxyType({
    "12345": "42 Synthetic Market St",
    "24680": "42 Synthetic Market St",
    "31415": "42 Synthetic Market St",
    "27182": "42 Synthetic Market St",
})

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
    refund_amount = record.refund_amount_minor if record else 5_000
    customer = (CustomerReference(record.customer_id, MatchStatus.MATCHED, scenario.case_input.received_at,
        RetrievalStatus.SUCCESS) if record else scenario.customer_reference)
    return WorkflowConfiguration(SyntheticCustomerLookup(customer), SyntheticRetailerOrderLookup(),
        SyntheticRetailerShipmentLookup(), SyntheticRetailerCarrierEvidenceLookup(),
        DeterministicAddressComparison(), scenario.execution_results,
        scenario.selected_disposition, scenario.case_input.received_at, scenario.unresolved_policies,
        proposed_refund_amount_minor=refund_amount, proposed_refund_currency="USD",
        autonomous_refund_limit_minor=10_000, autonomous_refund_limit_currency="USD",
        derive_retailer_disposition=True)

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
    values = {"sequence": event.sequence_number, "step": event.step, "event": event.event_type,
        "tool_name": event.tool_name, "arguments": {k:_value(v) for k,v in event.tool_arguments.items()},
        "result": {k:_value(v) for k,v in event.tool_result.items()}, "state_before": _state(event.state_before),
        "state_after": _state(event.state_after), "latency_ms": event.latency_ms, "retry_count": event.retry_count,
        "detail": event.detail, "evaluation_result": event.evaluation_result, "operation_id": event.operation_id,
        "idempotency_key": event.idempotency_key, "attempt_count": event.attempt_count,
        "operation_status": event.operation_status}
    return {key: value for key, value in values.items() if value not in (None, {}, [])}

def _card_state_metadata(before, after, events):
    """Return the meaningful state transition represented by a readable card."""
    for event in reversed(events):
        if event.state_before != event.state_after and event.state_after is not None:
            return _state(event.state_before), _state(event.state_after)
    if before != after and after is not None:
        return before, after
    return None, None

def _step(category, component, action, result, why, *, input=None, output=None, status=None, before=None, after=None, events=(), logic=None):
    state_before, state_after = _card_state_metadata(before, after, events)
    return {"category": category, "component": component, "action": action, "why": why,
        "result": result, "input": input or {}, "output": output or {}, "status": status, "logic": logic,
        "state_changed": state_after is not None, "state_before": state_before, "state_after": state_after,
        "technical_details": [_technical(x) for x in events]}

def _money(amount_minor, currency):
    symbol = "$" if currency == "USD" else f"{currency} "
    return f"{symbol}{amount_minor / 100:,.2f}".replace(".00", "")

def _readable_trace(rows):
    """Add presentation labels without changing the exact trace evidence."""
    for row in rows:
        values = row["input"]
        component = row["component"]
        fields = []
        if component == "customer_message_extractor":
            fields = [("Customer message", values.get("customer_message"))]
            row["logic"] = "Bounded LLM extraction into the defined intake schema."
        elif component == "extraction_validator":
            fields = [("Issue", values.get("issue_type")), ("Order", values.get("order_identifier"))]
            row["logic"] = "Accept structured extraction only if the existing validator passes."
        elif component == "customer_lookup": fields = [("Customer", values.get("customer_id"))]
        elif component == "order_lookup": fields = [("Order", values.get("order_id"))]
        elif component in {"shipment_lookup", "carrier_lookup"}: fields = [("Shipment", values.get("shipment_id"))]
        elif component == "address_comparison":
            fields = [("Case", values.get("case_id")),
                ("Customer-confirmed support-channel address", "Present" if values.get("customer_confirmed_support_channel_address") == "value present" else "Missing"),
                ("Retailer order", values.get("internal_order_id")),
                ("Retailer shipping address", "Present" if values.get("retailer_order_shipping_address") == "value present" else "Missing")]
        elif component == "dnr_policy":
            row["logic"] = "Proceed only when required customer, order, shipment, carrier, and address evidence is complete and no unresolved policy placeholder blocks the path."
        elif component == "resolution_selector":
            fields = [("Issue", "Delivered, not received" if values.get("issue_type") == "delivered_not_received" else values.get("issue_type")),
                ("Structural evidence gate", "Passed" if values.get("structural_gate") == "proceed_to_disposition" else values.get("structural_gate")),
                ("Carrier status", str(values.get("carrier_delivery_status", "")).title()),
                ("Address", str(values.get("address_match_result", "")).title())]
            row["logic"] = "Delivered-not-received + structural gate passed + carrier says delivered + address match → select refund."
        elif component == "refund_authority":
            fields = [("Refund amount", _money(values["refund_amount_minor"], values["currency"])),
                ("Amount source", "Retailer order" if values.get("amount_source") == "matched synthetic retailer record" else values.get("amount_source")),
                ("Currency", values.get("currency")),
                ("Autonomous limit", _money(values["autonomous_limit_minor"], values["autonomous_limit_currency"])),
                ("Limit source", str(values.get("limit_source", "")).capitalize())]
            row["logic"] = "Currency matches AND refund amount ≤ configured autonomous limit → permit autonomous execution."
        elif component == "execution_adapter":
            fields = [("Order", values.get("target_order_reference")),
                ("Amount", _money(values["refund_amount_minor"], values["currency"])),
                ("Currency", values.get("currency")), ("Idempotency protection", "Enabled" if values.get("idempotency_key") else "Not recorded")]
            row["logic"] = "Execute the already-selected and authorized action using the existing idempotency key and execution registry."
        row["display_input"] = [{"label": label, "value": value} for label, value in fields if value not in (None, "")]
    return rows

def _validation_checks(extraction: ExtractionResult):
    return {"schema_parse_valid": extraction.trace.parsing_succeeded,
        "structured_extraction_valid": extraction.trace.validation_succeeded}

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
        output={"failure_reason": extraction.validation_reason, "checks": _validation_checks(extraction)}, status="passed" if extraction.trace.validation_succeeded else "failed")]
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
        "failure_reason": extraction.validation_reason, "named_checks": _validation_checks(extraction)}]
    if workflow is None:
        rows[-1]["next"] = "Downstream workflow did not begin"; return _readable_trace(rows)
    events = workflow.trace_events
    labels = {"synthetic_customer_lookup": ("customer_lookup", "Find the customer in supported synthetic retailer data."),
        "synthetic_order_lookup": ("order_lookup", "Match the extracted identifier to the supported synthetic order."),
        "synthetic_shipment_lookup": ("shipment_lookup", "Retrieve shipment state for the matched order."),
        "synthetic_carrier_evidence_lookup": ("carrier_lookup", "Retrieve delivery evidence used by deterministic policy."),
        "synthetic_address_comparison": ("address_comparison", "Compare customer-confirmed support context with the trusted order shipping address."),
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
            "carrier_lookup": (("Delivered event found · picture proof available" if result.get("picture_proof_available") else "Delivered event found · no picture proof available") if result.get("evidence_present") else "No usable carrier snapshot found"),
            "address_comparison": {"match":"Customer-confirmed address matches order shipping address","mismatch":"Customer-confirmed address does not match order shipping address"}.get(result.get("match_result"),"Customer-confirmed address missing; comparison unavailable"),
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
    meaningful = {"linkage_completed": ("STATE","case_state","Link customer and order","The orchestrator records retrieved references in trusted case state."),
        "evidence_gathering_entered": ("STATE","case_state","Enter evidence gathering","The orchestrator advances the case after linkage."),
        "policy_review_entered": ("STATE","case_state","Enter policy review","The orchestrator advances only after evidence gathering."),
        "policy_route_recorded": ("POLICY","dnr_policy","Check evidence completeness","Checks structural completeness without applying retailer disposition policy."),
        "disposition_selected": ("DISPOSITION","resolution_selector","Select resolution","Records resolution only after policy permits disposition."),
        "execution_authority_granted": ("AUTHORITY","refund_authority","Check autonomous refund authority","Prevents refunds above the configured autonomous limit."),
        "execution_authority_blocked": ("AUTHORITY","refund_authority","Check autonomous refund authority","Prevents refunds above the configured autonomous limit."),
        "execution_failure_routed": ("ESCALATION","human_review_router","Route to human review","Keeps a failed action open for a person."),
        "execution_started": ("STATE","case_state","Mark execution in progress","The orchestrator records the consequential action boundary."),
        "execution_completed": ("STATE","case_state","Close case","Execution succeeded and no follow-up is required, so the case closes."),
        "workflow_completed": ("STATE","case_state","Complete workflow","Records the terminal workflow outcome in the append-only trace.")}
    for event in events:
        if event.event_type not in meaningful: continue
        category,component,action,why = meaningful[event.event_type]
        output = {"detail": event.detail, "final_outcome": event.final_outcome}
        if event.event_type == "policy_route_recorded":
            evaluation=workflow.case.policy_evaluation_results[-1]; output={"route":event.evaluation_result,"route_reason":list(evaluation.reasons),"evidence_facts":list(evaluation.evidence_summary),"unresolved_policy_placeholders":[x.value for x in evaluation.unresolved_policies]}
        elif event.event_type == "disposition_selected": output={"disposition":workflow.final_disposition.value,"rule":event.detail,"facts_consumed":{k:_value(v) for k,v in event.tool_arguments.items()}}
        elif event.event_type in {"execution_authority_granted","execution_authority_blocked"}: output={
            "authorization":"granted" if event.event_type.endswith("granted") else "blocked",
            "proposed_refund_amount_minor":event.tool_arguments.get("refund_amount_minor"),
            "proposed_currency":event.tool_arguments.get("currency"),
            "amount_source":event.tool_arguments.get("amount_source"),
            "configured_limit_minor":event.tool_arguments.get("autonomous_limit_minor"),
            "configured_limit_currency":event.tool_arguments.get("autonomous_limit_currency"),
            "limit_source":event.tool_arguments.get("limit_source"),
            "currency_match":event.tool_arguments.get("currency_match"),
            "amount_within_limit":event.tool_arguments.get("amount_within_limit"),
            "failure_detail":event.detail}
        amount = event.tool_arguments.get("refund_amount_minor", 0)
        limit = event.tool_arguments.get("autonomous_limit_minor", 0)
        results = {"linkage_completed":"Intake → linked","evidence_gathering_entered":"Linked → evidence gathering","policy_review_entered":"Evidence gathering → policy review","policy_route_recorded":"Structural evidence complete", "disposition_selected":"Refund selected",
            "execution_authority_granted":f"Granted · ${amount / 100:g} <= ${limit / 100:g}",
            "execution_authority_blocked":"Blocked · requires authorized human review",
            "execution_failure_routed":"Human review required · case remains open", "execution_started":"Not started → in progress","execution_completed":"Execution succeeded + no follow-up → case closed","workflow_completed":f"Workflow complete · {workflow.final_case_status.value}"}
        rows.append(_step(category,component,action,results[event.event_type],why,input={k:_value(v) for k,v in event.tool_arguments.items()},
            output=output,status=event.evaluation_result or event.final_outcome or event.event_type,
            before=_state(event.state_before),after=_state(event.state_after),events=(event,)))
    rows.sort(key=lambda x: -2 if x["category"]=="MODEL" else -1 if x["category"]=="VALIDATION" else x["technical_details"][0]["sequence"])
    return _readable_trace(rows)

def _customer_outcome(route, workflow, order_id, refund_amount_minor=None, refund_currency=None):
    if workflow is None:
        values={IntakeRoute.MANUAL_INTAKE_REVIEW_REQUIRED:("Needs manual review","We could not safely interpret the request. The automated workflow did not start."),
            IntakeRoute.CLARIFICATION_REQUIRED:("More information needed","Please provide a valid order identifier so we can continue."),
            IntakeRoute.GENERAL_TRIAGE_REQUIRED:("Sent to general support","This message does not match the supported delivered-package workflow.")}
        title,message=values[route]; return {"title":title,"message":message}
    final=workflow.case.snapshot()
    if final.execution_status.value=="succeeded" and final.closed_at is not None:
        amount = f"{_money(refund_amount_minor, refund_currency)} " if refund_amount_minor is not None and refund_currency else ""
        return {"title":"Refund processed","message":f"Your {amount}refund for order {order_id} has been processed successfully."}
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
    extraction_results=tuple(evaluate_extraction_case(case,scripted_response(case.expected)) for case in get_extraction_eval_cases())
    semantic_results=run_scripted_semantic_robustness_eval()
    trajectory={name:(result,expected,altered) for name,result,expected,altered in concrete_evaluation_cases()}
    reordered,expected,altered=trajectory["correct_outcome_execution_before_disposition"]
    over_limit,over_limit_expected,over_limit_events=trajectory["over_limit_refund"]
    failure_evaluations=tuple(evaluate_failure_regression_case(run_failure_regression_case(case)) for case in get_failure_regression_cases())
    duplicate=evaluate_failure_regression_case(run_failure_regression_case(get_failure_regression_case("duplicate-suppresses-injection")))
    coverage=[
        {"title":"Extraction correctness","detail":"Checks the nine-field extraction contract against 10 synthetic messages.","passed":all(result.semantic_match for result in extraction_results),"evidence":{"cases":len(extraction_results),"fields_per_case":9}},
        {"title":"Semantic robustness","detail":"Keeps structured facts stable across paraphrase, fact order, irrelevant detail, and verbosity changes.","passed":all(result.semantic_match for result in semantic_results),"evidence":{"variants":len(semantic_results),"source_cases":5,"transformations_per_source":4}},
        {"title":"Grounding / hallucination control","detail":"Rejects an order identifier that is absent from the customer message before workflow routing.","passed":guard.status.value=="invalid_model_output","evidence":{"fixture":"invented-order","validation_reason":guard.validation_reason}},
        {"title":"Trajectory correctness","detail":"Checks event order independently of final outcome, so a correct result cannot conceal an unsafe sequence.","passed":not check_outcome(reordered,expected) and bool(check_trajectory(reordered,altered)),"evidence":{"fixture":"correct_outcome_execution_before_disposition","outcome_failures":list(check_outcome(reordered,expected)),"trajectory_failures":list(check_trajectory(reordered,altered))}},
        {"title":"Authorization safety","detail":"Blocks an over-limit refund before execution and routes it to authorized human review.","passed":not check_outcome(over_limit,over_limit_expected) and not check_trajectory(over_limit,over_limit_events),"evidence":{"fixture":"over_limit_refund","final_case_status":over_limit.final_case_status.value,"execution_status":over_limit.case.execution_status.value}},
        {"title":"Failure handling","detail":"Checks controlled dependency and execution failures for the intended safe route and forbidden downstream events.","passed":all(evaluation.passed for evaluation in failure_evaluations),"evidence":{"regression_cases":len(failure_evaluations),"all_passed":all(evaluation.passed for evaluation in failure_evaluations)}},
        {"title":"Idempotency","detail":"Verifies a shared execution registry suppresses a duplicate consequential call.","passed":duplicate.passed,"evidence":{"fixture":"duplicate-suppresses-injection","checks":[{"name":check.name,"expected":_value(check.expected),"actual":_value(check.actual),"passed":check.passed} for check in duplicate.checks]}},
    ]
    return {"coverage":coverage,"examples":[{"title":"Extraction correctness","source":"extraction fixture: complete-order","input":scenarios["complete-order"].customer_message,
        "expected":{"issue_type":"delivered_not_received","order_identifier":"12345"},"actual":_extraction(good.extraction),"passed":good.status.value=="complete"},
        {"title":"Hallucination / invalid identifier control","source":"extraction fixture: invented-order","input":scenarios["invented-order"].customer_message,
        "expected":"Validator rejects an identifier not grounded in the input","actual":guard.validation_reason,"passed":guard.status.value=="invalid_model_output"},
        {"title":"Trajectory control","source":"trajectory fixture: correct_outcome_execution_before_disposition","input":"A deliberately reordered trace puts execution before disposition.",
        "expected":"Outcome evaluator passes; trajectory evaluator fails.","actual":{"outcome_failures":list(check_outcome(reordered,expected)),"trajectory_failures":list(check_trajectory(reordered,altered))},
        "passed":not check_outcome(reordered,expected) and bool(check_trajectory(reordered,altered))},
        {"title":"Authorization boundary","source":"trajectory fixture: over_limit_refund","input":"A proposed $150 refund exceeds the configured $100 autonomous limit.",
        "expected":{"case_status":"human_review","execution_status":"not_started"},"actual":{"case_status":over_limit.final_case_status.value,"execution_status":over_limit.case.execution_status.value,"trajectory_failures":list(check_trajectory(over_limit,over_limit_events))},
        "passed":not check_outcome(over_limit,over_limit_expected) and not check_trajectory(over_limit,over_limit_events)}],
        "note":"All coverage and examples are deterministic, offline synthetic-fixture evidence. No live-provider performance result is shown, and no provider call is made."}

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
    suffix=record.order.ref_id.rsplit("-",1)[-1] if record else "unknown"
    trusted=TrustedIntakeContext(f"case-{suffix}",record.customer_id if record else scenario.case_input.customer_identifier,shipment_id,scenario.case_input.actor,scenario.case_input.received_at,
        SYNTHETIC_CUSTOMER_CONFIRMED_ADDRESSES.get(order_id or ""))
    routed=route_customer_message_extraction(extraction_result,trusted,_configuration(scenario,order_id or scenario.order_reference.ref_id))
    workflow=routed.workflow_result
    return {"scenario":{"id":scenario_id,"title":scenario.title,"description":scenario.description},
        "mode":{"id":mode,"label":"Scripted extraction" if mode=="scripted" else "Live Claude extraction","synthetic":mode=="scripted"},
        "boundaries":["Offline extraction is scripted for the locked scenario fixture." if mode=="scripted" else "Live mode makes one Claude extraction call and never falls back to scripted output.","Retailer lookups and execution are synthetic adapters, not production integrations.","Case state, execution ledger, and append-only trace are in-memory lab records; production requires durable persistence."],
        "customer_message":message,"customer_outcome":_customer_outcome(routed.route,workflow,order_id,
            record.refund_amount_minor if record else None, "USD" if record else None),
        "model":{"request":serialize_model_request(request),"response":serialize_model_response(response),
            "parsed_extraction":None if extraction_result.extraction is None else _extraction(extraction_result.extraction),
            "validation":{"status":extraction_result.status.value,"parsing_succeeded":extraction_result.trace.parsing_succeeded,
                "validation_succeeded":extraction_result.trace.validation_succeeded,"failure_reason":extraction_result.validation_reason,"named_checks":_validation_checks(extraction_result)}},
        "intake_route":routed.route.value,"execution_trace":_execution_trace(extraction_result,request,response,workflow),
        "raw_workflow_trace":[] if workflow is None else [_technical(event) for event in workflow.trace_events],
        "final_state":None if workflow is None else _state(workflow.case.snapshot()),"eval_evidence":eval_evidence()}
