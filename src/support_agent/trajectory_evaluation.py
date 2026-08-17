"""Small deterministic checks over the first concrete workflow traces."""

from __future__ import annotations

from dataclasses import replace

from .domain import CaseStatus, Disposition, ExecutionStatus, MatchStatus
from .execution import ExecutionRegistry
from .scenarios import get_support_case_scenario, run_support_case_scenario
from .workflow import (
    SyntheticAddressComparison,
    SyntheticCarrierEvidenceLookup,
    SyntheticCustomerLookup,
    SyntheticOrderLookup,
    SyntheticShipmentLookup,
    WorkflowConfiguration,
    WorkflowResult,
    correct_unmatched_order_identifier,
    run_synthetic_support_case,
)


ExpectedOutcome = tuple[CaseStatus, Disposition, ExecutionStatus]


def check_outcome(
    result: WorkflowResult, expected: ExpectedOutcome
) -> tuple[str, ...]:
    """Compare only the final state expected for one concrete scenario."""
    expected_status, expected_disposition, expected_execution = expected
    failures = []
    for name, actual, wanted in (
        ("final case status", result.final_case_status, expected_status),
        ("disposition", result.final_disposition, expected_disposition),
        ("execution status", result.case.execution_status, expected_execution),
    ):
        if actual is not wanted:
            failures.append(f"{name}: expected {wanted.value}, got {actual.value}")
    return tuple(failures)


def check_trajectory(
    result: WorkflowResult, event_names: tuple[str, ...] | None = None
) -> tuple[str, ...]:
    """Enforce only invariants observed in the initial concrete traces."""
    events = event_names or tuple(event.event_type for event in result.trace_events)
    failures: list[str] = []

    linkage_positions = [
        events.index(name)
        for name in ("linkage_completed", "order_identifier_correction_recorded")
        if name in events
    ]
    downstream_events = (
        "evidence_gathering_entered",
        "policy_review_entered",
        "policy_route_recorded",
        "disposition_selected",
        "execution_started",
    )
    first_downstream = min(
        (events.index(name) for name in downstream_events if name in events),
        default=None,
    )
    if first_downstream is not None and (
        not linkage_positions or min(linkage_positions) > first_downstream
    ):
        failures.append(
            "successful linkage must occur before evidence, policy, disposition, or execution"
        )

    policy_events = ("policy_review_entered", "policy_route_recorded")
    first_policy = min(
        (events.index(name) for name in policy_events if name in events),
        default=None,
    )
    if first_policy is not None and (
        "evidence_gathering_entered" not in events
        or events.index("evidence_gathering_entered") > first_policy
    ):
        failures.append("evidence gathering must occur before policy review")

    disposition_events = (
        "disposition_selected",
        "human_review_decided",
    )
    for disposition_event in disposition_events:
        if disposition_event in events and (
            "policy_route_recorded" not in events
            or events.index("policy_route_recorded") > events.index(disposition_event)
        ):
            failures.append(
                f"policy routing must occur before disposition ({disposition_event})"
            )
            break

    if "execution_started" in events:
        preceding_dispositions = [
            events.index(name) for name in disposition_events if name in events
        ]
        if not preceding_dispositions or min(preceding_dispositions) > events.index(
            "execution_started"
        ):
            failures.append("disposition must occur before execution_started")

    if (
        result.case.execution_status is ExecutionStatus.FAILED
        and result.final_case_status is CaseStatus.CLOSED
    ):
        failures.append("failed execution must not result in a closed case")

    return tuple(failures)


def _refund_configuration(
    scenario, order_reference
) -> WorkflowConfiguration:
    return WorkflowConfiguration(
        SyntheticCustomerLookup(scenario.customer_reference),
        SyntheticOrderLookup(order_reference),
        SyntheticShipmentLookup(scenario.shipment_reference),
        SyntheticCarrierEvidenceLookup(scenario.carrier_evidence),
        SyntheticAddressComparison(scenario.address_match_result),
        scenario.execution_results,
        scenario.selected_disposition,
        scenario.case_input.received_at,
        scenario.unresolved_policies,
        None,
        ExecutionRegistry(),
        proposed_refund_amount_minor=5_000,
        proposed_refund_currency="USD",
        autonomous_refund_limit_minor=10_000,
        autonomous_refund_limit_currency="USD",
    )


def concrete_evaluation_cases() -> tuple[
    tuple[str, WorkflowResult, ExpectedOutcome, tuple[str, ...] | None], ...
]:
    """Run the four inspected scenarios and construct one bad trace contrast."""
    refund = get_support_case_scenario("refund-success")
    happy = run_support_case_scenario(refund).workflow_result
    carrier_failure = run_support_case_scenario(
        get_support_case_scenario("carrier-evidence-failed")
    ).workflow_result
    execution_failure = run_support_case_scenario(
        get_support_case_scenario("refund-execution-failure")
    ).workflow_result

    original_input = replace(refund.case_input, order_identifier="99999")
    unmatched_order = replace(
        refund.order_reference, match_status=MatchStatus.NOT_FOUND
    )
    stopped = run_synthetic_support_case(
        original_input,
        _refund_configuration(refund, unmatched_order),
        trace_id="evaluation-trace-order-correction-recovery",
        clock=lambda: refund.case_input.received_at,
    )
    recovered = correct_unmatched_order_identifier(
        stopped,
        original_input,
        refund.order_reference.ref_id,
        _refund_configuration(refund, refund.order_reference),
        clock=lambda: refund.case_input.received_at,
    )

    closed_refund = (
        CaseStatus.CLOSED,
        Disposition.APPROVE_REFUND,
        ExecutionStatus.SUCCEEDED,
    )
    happy_events = [event.event_type for event in happy.trace_events]
    execution_started = happy_events.pop(happy_events.index("execution_started"))
    happy_events.insert(happy_events.index("disposition_selected"), execution_started)
    bad_events = tuple(happy_events)

    return (
        ("happy_refund", happy, closed_refund, None),
        (
            "carrier_failure",
            carrier_failure,
            (CaseStatus.CLOSED, Disposition.DENY, ExecutionStatus.NOT_APPLICABLE),
            None,
        ),
        (
            "execution_failure",
            execution_failure,
            (
                CaseStatus.HUMAN_REVIEW,
                Disposition.APPROVE_REFUND,
                ExecutionStatus.FAILED,
            ),
            None,
        ),
        ("order_correction_recovery", recovered, closed_refund, None),
        ("correct_outcome_bad_path", happy, closed_refund, bad_events),
    )
