"""Run one synthetic delivered-not-received case through the full offline path."""

from __future__ import annotations

from support_agent.extraction import extract_customer_message
from support_agent.extraction_scenarios import get_extraction_scenarios
from support_agent.modeling import ScriptedModelClient
from support_agent.scenarios import get_support_case_scenario
from support_agent.workflow import (
    SyntheticAddressComparison,
    SyntheticCarrierEvidenceLookup,
    SyntheticCustomerLookup,
    SyntheticOrderLookup,
    SyntheticShipmentLookup,
    TrustedIntakeContext,
    WorkflowConfiguration,
    route_customer_message_extraction,
)


def run() -> str:
    extraction_case = next(
        case
        for case in get_extraction_scenarios()
        if case.scenario_id == "complete-order"
    )
    workflow_case = get_support_case_scenario("refund-success")
    client = ScriptedModelClient(extraction_case.response)

    extraction_result = extract_customer_message(
        extraction_case.customer_message, client
    )
    configuration = WorkflowConfiguration(
        SyntheticCustomerLookup(workflow_case.customer_reference),
        SyntheticOrderLookup(workflow_case.order_reference),
        SyntheticShipmentLookup(workflow_case.shipment_reference),
        SyntheticCarrierEvidenceLookup(workflow_case.carrier_evidence),
        SyntheticAddressComparison(workflow_case.address_match_result),
        workflow_case.execution_results,
        workflow_case.selected_disposition,
        workflow_case.case_input.received_at,
        workflow_case.unresolved_policies,
        proposed_refund_amount_minor=5_000,
        proposed_refund_currency="USD",
        autonomous_refund_limit_minor=10_000,
        autonomous_refund_limit_currency="USD",
    )
    routed = route_customer_message_extraction(
        extraction_result,
        TrustedIntakeContext(
            workflow_case.case_input.case_id,
            workflow_case.case_input.customer_identifier,
            workflow_case.case_input.shipment_identifier,
            workflow_case.case_input.actor,
            workflow_case.case_input.received_at,
        ),
        configuration,
    )

    extraction = routed.extraction
    workflow = routed.workflow_result
    if extraction is None or workflow is None:
        raise RuntimeError("the scripted delivered-not-received case did not enter the workflow")

    case = workflow.case
    transitions = [
        f"{event.state_before.case_status.value} -> {event.state_after.case_status.value}"
        for event in workflow.trace_events
        if event.state_before is not None
        and event.state_after is not None
        and event.state_before.case_status is not event.state_after.case_status
    ]
    evidence = [
        (
            f"{item.delivery_status}; events={', '.join(item.tracking_event_history)}; "
            f"picture proof={str(item.picture_proof_available).lower()}"
        )
        for item in case.carrier_evidence_snapshots
    ]
    policy = case.policy_evaluation_results[-1]
    operation = workflow.execution_operation

    lines = [
        "Offline delivered-not-received run",
        f"Original customer message: {extraction_result.original_message}",
        "Extraction outcome:",
        f"  status: {extraction_result.status.value}",
        f"  issue type: {extraction.issue_type.value}",
        f"  order identifier extracted: {'yes' if extraction.order_identifier else 'no'}",
        "  missing required fields: "
        + (", ".join(extraction.missing_required_fields) or "none"),
        f"Intake route: {routed.route.value}",
        "Full DNR workflow entered: yes",
        "Key workflow state transitions:",
        *(f"  {index}. {transition}" for index, transition in enumerate(transitions, 1)),
        "Evidence gathered:",
        *(f"  - {item}" for item in evidence),
        f"Policy result / route: {policy.route.value}",
        f"Disposition selected: {workflow.final_disposition.value}",
        "Execution result: "
        + (
            f"{operation.status.value}; {operation.result_detail}"
            if operation is not None
            else "not applicable"
        ),
        f"Follow-up / closure state: {case.follow_up_status.value}; closed={str(case.closed_at is not None).lower()}",
        f"Final case status: {workflow.final_case_status.value}",
        f"Trace/event count: {len(workflow.trace_events)}",
        "Ordered event names:",
        *(f"  {event.sequence_number}. {event.event_type}" for event in workflow.trace_events),
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(run())
