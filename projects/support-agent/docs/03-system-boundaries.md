# System Boundaries

**Status: In progress — Build stage, increment 1 (deterministic workflow model)**

## Purpose

Define a candidate **deterministic** technical design for the synthetic delivered-but-not-received
support workflow described in `02-current-workflow.md`, translated from an 11-step process
narrative into system concepts: state, records, transitions, policy inputs, human-review points,
and failure behavior. This is the first Build-stage increment and is deliberately independent of
any AI or agent implementation, so the deterministic skeleton can be reasoned about, and later
tested, on its own terms.

Epistemic labels carry over unchanged from `01-business-context.md` and `02-current-workflow.md`:

- **Reported** — directly supported by substantive public evidence already captured in the prior
  documents' evidence logs.
- **Inferred** — plausible retailer-side operational inference, not directly evidenced.
- **Synthetic** — a deliberate modeling choice made for this reference system.
- **Implemented** — not applicable in this increment; no behavior has been implemented yet.

## 1. Scope and design boundary

This document defines a **candidate deterministic workflow model** for the synthetic
delivered-but-not-received case only. It is a design artifact, not a specification of any real
retailer's system.

This document does **not** yet define:

- an LLM or model selection,
- prompts,
- agent reasoning or an agent loop,
- LangChain, LangGraph, or any orchestration framework,
- application code,
- production infrastructure or deployment topology,
- real retailer policy (refund thresholds, fraud rules, permission boundaries, wait periods),
- observed retailer schemas.

All internal records, states, and interfaces described below are **candidate models** unless
explicitly grounded in the evidence already captured in `01-business-context.md` or
`02-current-workflow.md`. Where a candidate model is not directly evidenced, it is labeled Inferred
or Synthetic in place, not presented as fact.

## 2. System boundary

### Inside the workflow boundary

- Case lifecycle and state
- References to customer, order, and shipment records (not the records themselves)
- Evidence snapshots or retrieval results
- Deterministic policy-evaluation inputs and results
- Human-review requests and decisions
- Selected disposition
- Execution and follow-up status
- Audit events

### Outside the workflow boundary

The workflow depends on the following external systems but does not own them. No vendor products
are assumed — these are categories, matching the "Systems and records" categories already named in
`02-current-workflow.md`.

| External system | What the workflow sends | What the workflow expects back | Source of truth vs. execution dependency | Common failure responses | Evidence classification |
|---|---|---|---|---|---|
| Customer-facing support channel | Case status updates, requests for information, disposition explanations | Customer replies, self-check confirmations, additional evidence | Execution dependency — the workflow only exchanges messages through it, does not own the channel | No response within an as-yet-undefined wait window; malformed, missing, or contradictory input | Synthetic |
| Customer/account system | Identifying data supplied by the customer (e.g., account or order reference) | Confirmed customer identity; optionally, prior-case/account history if the retailer chooses to use it for this case type | Source of truth for customer identity and account lookup only; whether prior-case/account history exists as a decision input, and how it would be used, is not established as a source-of-truth dependency here — it remains an unresolved, Synthetic modeling question (see `02-current-workflow.md`) | Customer not found; multiple ambiguous matches; system unavailable | Inferred (identity/account lookup) / Synthetic (availability and use of prior-case history) |
| Order-management system | Order identifier or customer/account reference | Order record: items, ship-to address on file, order value, item category | Source of truth for order data | Order not found; multiple shipments on one order; stale data; system unavailable | Inferred |
| Fulfillment or shipment system | Order reference | Shipment record(s): carrier, tracking identifier, fulfillment timestamp | Source of truth for what was shipped and when | Shipment record incomplete or delayed; system unavailable | Inferred |
| Carrier tracking / proof-of-delivery source | Tracking identifier | Delivery status, delivery timestamp, tracking event history, picture proof if available | Source of truth for delivery evidence. This is a separate external boundary from the carrier inquiry/claim process below; tracking evidence is an input to evaluation, not itself an execution dependency for carrier-claim follow-up | Tracking data unavailable or stale; no picture proof; conflicting events; system unavailable | Reported (narrow — that tracking events and picture proof exist) / Inferred (that a retailer retrieves them) |
| Refund or replacement execution system | Execution command referencing the case and selected disposition | Execution confirmation or failure/error | Execution dependency only — not a source of truth for the decision, only for whether it was carried out | Execution failure after approval; partial failure; timeout; duplicate-command risk | Synthetic |
| Carrier inquiry or claim process | Claim request with supporting documentation (e.g., invoice, merchandise description) | Claim acknowledgment/reference, and later a claim result | Execution dependency for filing; external source of truth for the claim result, not controlled by the workflow | Claim rejected; claim expired; documentation deemed insufficient; indefinitely pending; system unavailable | Reported (narrow — that a claim path exists) / Synthetic (retailer-side handling of it) |
| Outbound customer-notification system | Notification content (disposition, next steps) | Delivery confirmation or failure of the notification itself | Execution dependency | Notification delivery failure; customer does not act on it | Synthetic |

## 3. Candidate state model

A single combined enum covering lifecycle phase, disposition, and execution result would multiply
combinatorially (every phase × every disposition × every execution outcome), most of which would be
invalid. Instead this model separates four orthogonal fields on the support case:

- **`case_status`** — where the case currently is in the process.
- **`disposition`** — what outcome was selected for the case.
- **`execution_status`** — whether the selected disposition has actually been carried out.
- **`follow_up_status`** — whether the case is waiting on an external process (e.g., a carrier
  claim) beyond the workflow's own execution.

Keeping these separate is what makes distinctions like "refund approved" vs. "refund issued"
representable at all: `disposition = approve_refund` records the decision, while
`execution_status` records whether it was actually carried out. Collapsing them into one state
value would make "refund issued" indistinguishable from "refund approved but not yet executed,"
which is exactly the ambiguity this document must avoid.

### `case_status` (lifecycle phase)

Derived from steps 1–11 of `02-current-workflow.md`. All values Synthetic (the phase taxonomy is a
project modeling choice) unless otherwise noted.

| Value | Meaning | Entry condition | Allowed exits | Terminal? | Evidence classification |
|---|---|---|---|---|---|
| `intake` | Case opened; customer/order not yet confirmed | Customer contacts support (step 1) | → `linked`, → `intake_failed` | No | Synthetic |
| `intake_failed` | Customer or order could not be identified | Linkage attempt fails (step 1 exception) | → `human_review` (linkage review opened) | No | Synthetic |
| `linked` | Customer and order identified; case classified as delivered-not-received | Successful linkage + classification (steps 1–2), or a `human_review` linkage decision confirming the match | → `evidence_gathering` | No | Synthetic |
| `evidence_gathering` | Collecting customer report and order/shipment/carrier evidence | From `linked`, or return from `awaiting_customer_action`, or return from `human_review` (reviewer requests more evidence) | → `awaiting_customer_action`, → `policy_review` | No | Synthetic (that retailers perform a discrete evidence-collection phase is Inferred from the workflow narrative in `02-current-workflow.md`; this case_status value itself is a modeling choice) |
| `awaiting_customer_action` | Waiting on the customer (self-check, wait guidance, or an information request) | Evidence inconclusive and self-check/wait guidance applies (step 7), or a `human_review` linkage decision requesting more info, or `disposition_selection` sets `disposition = request_more_info` or `advise_self_check_or_wait` | → `evidence_gathering` (customer responds), → `policy_review` (wait elapsed per `CUSTOMER_RESPONSE_WAIT_POLICY`, unresolved — see §6), → `closed` (customer self-resolves) | No | Synthetic (the self-check/wait guidance content is Reported; that an agent relays it mid-case is Inferred; this case_status value itself is a modeling choice) |
| `policy_review` | Deterministic policy-context evaluation running | Evidence collection complete, or self-check step judged unnecessary (step 8) | → `human_review`, → `disposition_selection` | No | Synthetic |
| `human_review` | Case actively assigned to a human reviewer | Any trigger in §7 fires | → `linked` (linkage review confirms the match), → `awaiting_customer_action` (linkage review requests more info from the customer), → `evidence_gathering` (reviewer requests more evidence), → `disposition_selection` (non-linkage decision selecting/confirming a disposition path — including a disposition of `request_more_info`/`advise_self_check_or_wait`, which then routes on to `awaiting_customer_action` via the `disposition_selection` rules), → `awaiting_external_follow_up` (reviewer decides to keep waiting on a pending follow-up), → `closed` (linkage unresolvable, confirmed duplicate merge, or reviewer accepts a final external result), → itself (no decision yet) | No | Synthetic |
| `disposition_selection` | A disposition is being recorded (by policy result or reviewer decision) before execution starts | `policy_review` clears within frontline authority, or `human_review` produces a decision | → `executing` (disposition is `approve_refund`, `approve_replacement`, or `open_carrier_inquiry`), → `awaiting_customer_action` (disposition is `request_more_info` or `advise_self_check_or_wait`), → `closed` (disposition is `deny`) | No | Synthetic |
| `executing` | Selected disposition (`approve_refund`, `approve_replacement`, or `open_carrier_inquiry`) is being carried out | Disposition selected requiring execution and required execution data present (step 10); `execution_status` set to `not_started` on entry | → `awaiting_external_follow_up` (only `open_carrier_inquiry`, accepted), → `closed` (`approve_refund`/`approve_replacement` succeed, no follow-up required), → `human_review` (execution failure) | No | Synthetic |
| `awaiting_external_follow_up` | Waiting on an external process result (e.g., a carrier claim) | Execution accepted but final result depends on an external party (step 11), or a `human_review` decision to keep waiting after a deadline review | → `human_review` (external result received — favorable, unfavorable, rejected, or expired — or follow-up deadline exceeded per `EXTERNAL_FOLLOW_UP_DEADLINE_POLICY`, unresolved — see §6) | No | Synthetic |
| `closed` | Case resolved; no further action expected | Execution complete with no follow-up needed, disposition is `deny` (no execution required), or case abandoned/self-resolved, or a `human_review` decision closes the case (linkage unresolvable, confirmed duplicate merged, or a final external follow-up result accepted) | — | Yes | Synthetic |

### `disposition`

Derived directly from the "Workflow outcomes" branch list in `02-current-workflow.md`. The branch
set itself is Synthetic there; that classification carries over unchanged.

| Value | Meaning | Evidence classification |
|---|---|---|
| `none_selected` | Default; no disposition chosen yet | Synthetic |
| `request_more_info` | Ask the customer for additional information. Does not require execution; routes to `awaiting_customer_action` | Synthetic |
| `advise_self_check_or_wait` | Direct the customer to check the location/neighbors and/or wait (the guidance content is Reported; that an agent relays it mid-case is Inferred; this disposition value itself is a Synthetic modeling choice). Does not require execution; routes to `awaiting_customer_action` | Synthetic |
| `open_carrier_inquiry` | Open or recommend a carrier inquiry or claim (that a claim path exists is Reported, narrow; retailer-side handling of it is Inferred/Synthetic; this disposition value itself is a Synthetic modeling choice). Requires execution (files the inquiry); routes to `executing` | Synthetic |
| `approve_replacement` | Approve sending a replacement. Requires execution; routes to `executing` | Synthetic |
| `approve_refund` | Approve a refund. Requires execution; routes to `executing` | Synthetic |
| `deny` | Deny or close with explanation. Does not require execution; routes directly to `closed` | Synthetic |

Note: escalation is deliberately **not** modeled as a `disposition` value. "This case was escalated"
is a historical fact best captured as an audit event at the transition into `human_review`
(see §3's "escalated vs. actively under human review" note below), not as a persistent field that
would need to be cleared once review concludes.

### `execution_status`

| Value | Meaning | Evidence classification |
|---|---|---|
| `not_applicable` | Disposition does not require execution (`deny`, `request_more_info`, `advise_self_check_or_wait`) | Synthetic |
| `not_started` | Disposition selected but execution not yet attempted | Synthetic |
| `in_progress` | An execution attempt is underway | Synthetic |
| `succeeded` | Execution completed successfully | Synthetic |
| `failed` | Execution was attempted and failed (technical failure, not a business denial) | Synthetic |

### `follow_up_status`

| Value | Meaning | Evidence classification |
|---|---|---|
| `not_applicable` | No external process pending | Synthetic |
| `pending` | Waiting on an external result (e.g., carrier claim outcome) | Synthetic |
| `resolved_favorable` | External process resolved in the customer's/case's favor | Synthetic |
| `resolved_unfavorable` | External process resolved against the case | Synthetic |
| `expired` | External process timed out without a result (that a carrier claims process can time out is Inferred from public carrier guidance; this state value itself is a Synthetic modeling choice) | Synthetic |
| `rejected` | External process (e.g., carrier claim) was rejected (that carriers may reject claims is Inferred from public carrier guidance; this state value itself is a Synthetic modeling choice) | Synthetic |

### Required distinctions, made explicit

- **Refund/replacement approved vs. issued/created**: `disposition = approve_refund` (or
  `approve_replacement`) records the decision; `execution_status = succeeded` records that it
  actually happened. A case cannot be `closed` on the strength of `disposition` alone — see §4.
- **Carrier action selected vs. carrier result received**: `disposition = open_carrier_inquiry`
  with `execution_status = succeeded` means the claim was filed; `follow_up_status` tracks whether
  a result has come back.
- **Awaiting customer action vs. awaiting an external carrier result**: two distinct `case_status`
  values (`awaiting_customer_action` vs. `awaiting_external_follow_up`) because a different actor
  is being waited on and different failure handling applies.
- **Denied vs. closed**: `deny` is a `disposition` (why); `closed` is a `case_status` (that the
  case is done). Not all closed cases are denials — a successfully executed refund also ends in
  `closed`.
- **Escalated vs. actively under human review**: `case_status = human_review` is the live state.
  "Escalated" is represented as an audit event recorded at the moment of entry into
  `human_review`, not as a persistent field — once the case moves on, it is no longer "escalated"
  in any live sense, only historically true, which an audit trail (not a state field) is suited to.

## 4. Allowed state transitions

Named placeholders (`CUSTOMER_RESPONSE_WAIT_POLICY`, `EVIDENCE_FRESHNESS_POLICY`,
`EXTERNAL_FOLLOW_UP_DEADLINE_POLICY`, `FRONTLINE_REFUND_AUTHORITY`,
`REPLACEMENT_ELIGIBILITY_POLICY`, `CARRIER_CLAIM_ELIGIBILITY`, `RISK_REVIEW_TRIGGER_POLICY`) are
unresolved identifiers, defined in §6 — not implemented rules.

| Current phase | Trigger | Next phase | Related disposition/execution change | Actor | Required data | Failure/rejection behavior | Evidence classification |
|---|---|---|---|---|---|---|---|
| `intake` | Customer/order successfully identified and classified | `linked` | — | Frontline agent (system-assisted) | Customer reference, order reference | On failure to identify → `intake_failed` | Synthetic |
| `intake` | Customer/order cannot be identified | `intake_failed` | — | Frontline agent / system | Attempted identifiers | This transition is itself the failure path | Synthetic |
| `intake_failed` | A linkage review is opened for the case | `human_review` | `human_review_request` created, `triggered_by = "customer/order linkage uncertainty"` | System | Attempted identifiers, any partial matches | — | Synthetic |
| `human_review` | Reviewer records an explicit linkage decision (linkage-review trigger only) | `linked` (confirms the match), or `awaiting_customer_action` (requests more info from customer), or `closed` (determines unresolvable) — the reviewer's decision selects exactly one | `human_review_request.decision` set | Human reviewer | Review decision record | No response → stays `human_review` | Synthetic |
| `linked` | Order/shipment record attached | `evidence_gathering` | — | Frontline agent (system-assisted) | Order reference, shipment reference(s) | — | Inferred |
| `evidence_gathering` | Evidence inconclusive; self-check/wait guidance applies | `awaiting_customer_action` | — | Frontline agent | Evidence snapshot (or explicit "unavailable"), delivery timestamp | — | Synthetic (guidance content is Reported; trigger condition is Inferred) |
| `evidence_gathering` | Evidence collection complete, or self-check judged unnecessary | `policy_review` | — | Frontline agent (system-assisted) | Order/shipment record, evidence snapshot or unavailable marker | — | Synthetic |
| `awaiting_customer_action` | Customer responds with information or self-check result | `evidence_gathering` | — | Customer (via channel) | Customer response | — | Inferred |
| `awaiting_customer_action` | Customer confirms they found the package | `closed` | `disposition = none_selected` (self-resolved) | Customer, confirmed by frontline agent | Customer confirmation | — | Inferred |
| `awaiting_customer_action` | No response within `CUSTOMER_RESPONSE_WAIT_POLICY` | `policy_review` | — | System | Elapsed-time check against the placeholder | Until `CUSTOMER_RESPONSE_WAIT_POLICY` is resolved, no automatic elapsed-time exit is defined — see §6 safe default | Synthetic |
| `policy_review` | Evaluation flags a required-review condition (§7) | `human_review` | `policy_evaluation_result` recorded | System (policy evaluation) | Policy evaluation inputs (§6) | — | Synthetic |
| `policy_review` | Evaluation completes within frontline authority, no trigger fires | `disposition_selection` | `policy_evaluation_result` recorded | System | Policy evaluation inputs | — | Synthetic |
| `human_review` | Reviewer records a decision on a non-linkage trigger, selecting/confirming a disposition path | `disposition_selection` | `human_review_request.decision` set | Human reviewer | Review decision record | No response → case remains in `human_review`; no silent auto-progression | Synthetic |
| `human_review` | Reviewer records a decision on a non-linkage trigger, closing the case (e.g., confirmed duplicate, merged) | `closed` | `human_review_request.decision` set | Human reviewer | Review decision record | No response → case remains in `human_review` | Synthetic |
| `human_review` | Reviewer requests more evidence instead of deciding | `evidence_gathering` | — | Human reviewer | Review decision record specifying what's needed | — | Synthetic |
| `human_review` | Reviewer decides to keep waiting on a pending external follow-up (follow-up-deadline trigger only) | `awaiting_external_follow_up` | `human_review_request.decision` set | Human reviewer | Review decision record | No response → case remains in `human_review` | Synthetic |
| `disposition_selection` | Disposition selected is `approve_refund`, `approve_replacement`, or `open_carrier_inquiry`, and required execution data present | `executing` | `disposition` set; `execution_status = not_started` | System, on behalf of frontline agent/escalation/claims owner per disposition | Disposition value, execution-required fields | Required data missing → the transition is rejected under the invalid-transition/precondition guard (last row of this table): `case_status` remains `disposition_selection`, the selected disposition is unchanged, an audit event is recorded, and a separate operational integrity alert is raised — this does not route the case to `human_review`. A distinct, later `human_review` trigger may be opened if resolving the missing information requires business judgment, but that is not part of this transition | Synthetic |
| `disposition_selection` | Disposition selected is `request_more_info` or `advise_self_check_or_wait` | `awaiting_customer_action` | `disposition` set; `execution_status = not_applicable` | System | Disposition value | — | Synthetic |
| `disposition_selection` | Disposition selected is `deny` | `closed` | `disposition` set; `execution_status = not_applicable` | System, on behalf of reviewer/frontline agent per the deciding authority | Disposition value, decision rationale | — | Synthetic |
| `executing` | Execution accepted, result depends on an external process (`open_carrier_inquiry` only) | `awaiting_external_follow_up` | `execution_status = succeeded` (execution accepted), `follow_up_status = pending` | System | Execution attempt record, external reference | — | Synthetic |
| `executing` | Execution succeeds, no follow-up required (`approve_refund`/`approve_replacement`) | `closed` | `execution_status = succeeded` | System | Execution attempt record showing success | — | Synthetic |
| `executing` | Execution fails after approval | `human_review` | `execution_status = failed` | System | Execution attempt record showing failure | This transition is itself the failure path; disposition is not reverted | Synthetic |
| `awaiting_external_follow_up` | External result received (favorable, unfavorable, rejected, or expired), or follow-up deadline exceeded per `EXTERNAL_FOLLOW_UP_DEADLINE_POLICY` (unresolved — see §6) | `human_review` | `follow_up_status` set accordingly (`resolved_favorable` / `resolved_unfavorable` / `rejected` / `expired`) | System, on receipt of external result or deadline check | Follow-up result, or elapsed-time check against the placeholder | Conservative-by-design: no automatic carrier-result policy is invented, so every external result routes through an explicit reviewer decision rather than resolving itself | Inferred (that carrier processes can end in rejection or expiration, and that a deadline check is meaningful, is Inferred; the transition mechanics are Synthetic) |
| Any phase | Unexpected or invalid transition attempted, or a required-data precondition is missing | *(unchanged — `case_status` is not mutated)* | — | System (guard) | — | The attempted transition is rejected and logged as an audit event; the case's existing `case_status` is left exactly as it was; the guard raises a separate operational system-integrity alert/review, distinct from a customer-case transition into `case_status = human_review` (see note below) | Synthetic |

**Invalid-transition example, made explicit**: `executing` → `closed` is only valid when
`execution_status = succeeded`. A case with `disposition = approve_refund` and
`execution_status = not_started` or `in_progress` cannot reach `closed` — the guard on that
transition checks `execution_status`, not just `disposition`, which is precisely why the two fields
are kept separate in §3.

**Operational integrity alert vs. `human_review`, made explicit**: an unexpected or invalid
transition attempt is a system-integrity condition, not a customer-case decision point. It must not
itself perform a further state mutation — forcing the case into `case_status = human_review` would
mean malformed input (or a bug) could move a case exactly as if a legitimate trigger had fired. Instead
the guard rejects the attempt, leaves `case_status` unchanged, records an audit event, and raises an
operational alert/review outside the case's own `human_review_request` records, for an
engineer/operator to investigate. A case only ever reaches `case_status = human_review` through one of
the genuine triggers listed in §7.

## 5. Core records and candidate schemas

No code, JSON Schema, or SQL — conceptual field tables only. References use synthetic identifiers;
no real PII. For any record backed by an external system, four things are distinguished: the
external source-of-truth record (not modeled here), the workflow's own stored reference or
snapshot, the retrieval timestamp, and retrieval success/failure — via `retrieved_at` and
`retrieval_status` fields below.

Records embedded directly in the case (rather than modeled as standalone records) are noted as
such; this keeps the model lean per the design principles.

### Support case (core aggregate)

| Field | Type | Required/Optional | Source/producer | Mutable | Purpose | Classification |
|---|---|---|---|---|---|---|
| case_id | identifier | Required | System, at intake | No | Uniquely identifies the case | Synthetic |
| case_status | enum (§3) | Required | System (state machine) | Yes | Current lifecycle phase | Synthetic |
| disposition | enum (§3) | Required; initial value `none_selected` | Policy result or reviewer decision | Yes, via defined transitions only | Selected outcome | Synthetic |
| execution_status | enum (§3) | Required; initial value `not_applicable` | Execution attempt record(s) | Yes | Whether the disposition was carried out | Synthetic |
| follow_up_status | enum (§3) | Required; initial value `not_applicable` | External follow-up record | Yes | Status of a pending external process | Synthetic |
| opened_at | timestamp | Required | System, at intake | No | Case-open time | Synthetic |
| closed_at | timestamp | Optional | System, on reaching `closed` | No | Case-close time | Synthetic |
| customer_ref | reference → Customer reference | Required once linked | Frontline agent / customer-account lookup | No (relinking is a new event, not a mutation) | Links case to a customer | Inferred |
| order_ref | reference → Order reference | Required once linked | Frontline agent / order-management lookup | No | Links case to an order | Inferred |
| shipment_refs | list of reference → Shipment reference | Required once linked (may be >1) | Fulfillment/shipment lookup | Append-only | Links case to affected shipment(s) | Inferred |
| customer_report | embedded structure (see below) | Required | Customer, via agent/channel | Append-only (new entries, not overwrites) | Captures what the customer reported | Inferred |
| evidence_snapshots | list of reference → Carrier evidence snapshot | Optional (may be empty) | Carrier tracking/proof-of-delivery lookup | Append-only | Evidence attached to the case | Reported (narrow) / Inferred |
| policy_evaluation_results | list of embedded structure (see below) | Optional until `policy_review` runs | Deterministic policy layer | Append-only | Basis for routing/disposition | Synthetic |
| human_review_requests | list of reference → Human-review request & decision | Optional | System, on entering `human_review` | Append-only | Tracks escalations and outcomes | Synthetic |
| execution_attempts | list of reference → Execution attempt | Optional until executing | System, on attempting execution | Append-only | Supports idempotency and failure tracking | Synthetic |
| follow_up | reference → External follow-up | Optional | System, on opening a carrier inquiry or other pending process | Status updates only, not identity | Tracks pending external result | Synthetic |
| audit_events | list of reference → Audit event | Required (at least the open event) | System, on every state-relevant action | Append-only | Full history for auditability | Synthetic |

### Customer reference, order reference, shipment reference

Each is a small, standalone record (not embedded, since each needs its own retrieval metadata),
following the same shape:

| Field | Type | Required/Optional | Source/producer | Mutable | Purpose | Classification |
|---|---|---|---|---|---|---|
| ref_id | identifier | Required | External system lookup | No | Points to the external record (not a copy of it) | Inferred |
| match_status *(customer/order only)* | enum: matched / ambiguous / not_found | Required | Frontline agent/system, at lookup | No (a new lookup produces a new attempt, not a mutation) | Represents linkage certainty | Synthetic |
| key attributes *(e.g., order_value, item_category, ship_to_address_on_file for order; carrier, tracking_id, fulfillment_timestamp for shipment)* | conceptual, per record type | Required if match_status = matched | External system | No (re-retrieval creates a new record) | Minimal data needed for policy inputs and downstream steps | Inferred |
| retrieved_at | timestamp | Required | System | No | When the lookup occurred | Synthetic |
| retrieval_status | enum: success / failure | Required | System | No | Whether the external system responded | Synthetic |

### Customer-provided report *(embedded in support case)*

| Field | Type | Required/Optional | Source/producer | Mutable | Purpose | Classification |
|---|---|---|---|---|---|---|
| order_or_tracking_identifier_provided | conceptual string | Optional | Customer | No (superseded, not overwritten) | Basis for order linkage | Inferred |
| delivery_address_as_stated | conceptual string | Optional | Customer | No | Input to address-match comparison | Inferred |
| when_and_how_checked | conceptual string | Optional | Customer | No | Input to self-check completion | Inferred |
| other_possible_recipients_noted | conceptual string | Optional | Customer | No | Context for self-check guidance | Inferred |
| reported_at | timestamp | Required | System | No | When this report was captured | Synthetic |

### Carrier evidence snapshot

| Field | Type | Required/Optional | Source/producer | Mutable | Purpose | Classification |
|---|---|---|---|---|---|---|
| snapshot_id | identifier | Required | System | No | Identifies this retrieval | Synthetic |
| shipment_ref | reference → Shipment reference | Required | System | No | Links evidence to a shipment | Inferred |
| delivery_status | conceptual enum | Required if retrieval succeeded | Carrier tracking source | No | Basis for delivery confirmation | Reported (narrow) |
| delivery_timestamp | timestamp | Optional | Carrier tracking source | No | Basis for staleness/wait checks | Reported (narrow) |
| tracking_event_history | conceptual list | Optional | Carrier tracking source | No | Detailed evidence for review | Reported (narrow) |
| picture_proof_available | boolean | Required if retrieval succeeded | Carrier tracking source | No | Input to policy evaluation | Reported (narrow) |
| retrieved_at | timestamp | Required | System | No | When this snapshot was taken | Synthetic |
| retrieval_status | enum: success / failure | Required | System | No | Whether the carrier source responded | Synthetic |

The snapshot itself — as a discrete, timestamped artifact distinct from the live external record —
is a Synthetic modeling choice: no source describes a retailer storing evidence this way, but it is
necessary to make "stale evidence" (§8) representable at all.

### Policy-evaluation result *(embedded list on the support case)*

| Field | Type | Required/Optional | Source/producer | Mutable | Purpose | Classification |
|---|---|---|---|---|---|---|
| evaluation_id | identifier | Required | System | No | Identifies this evaluation | Synthetic |
| evaluated_at | timestamp | Required | System | No | When evaluation ran | Synthetic |
| inputs_used | conceptual reference to §6 candidate inputs | Required | System | No | Traceability for the result | Synthetic |
| unresolved_placeholders_encountered | list of placeholder identifiers | Optional (empty if none) | System | No | Records which §6 unknowns applied | Synthetic |
| recommended_route | enum: within_frontline_authority / requires_human_review / insufficient_data | Required | System | No | Drives the `policy_review` exit transition | Synthetic |

### Human-review request & decision

One record covers both the request and its eventual decision, since the decision is a direct
response to the request.

| Field | Type | Required/Optional | Source/producer | Mutable | Purpose | Classification |
|---|---|---|---|---|---|---|
| review_id | identifier | Required | System | No | Identifies the review | Synthetic |
| triggered_by | one of the §7 trigger names | Required | System | No | Why review was needed | Synthetic |
| opened_at | timestamp | Required | System | No | When review began | Synthetic |
| information_presented | conceptual reference/summary | Required | System | No | What the reviewer saw | Synthetic |
| assigned_reviewer_role | conceptual string (e.g., "escalation/risk-fraud reviewer" per `01-business-context.md` actors) | Required | System | No | Who is expected to decide | Inferred |
| decision | enum, matching permitted resulting transitions for the trigger (§7) | Optional until decided | Human reviewer | Set once | The reviewer's decision | Synthetic |
| decision_rationale | conceptual free text | Optional | Human reviewer | Set once | Auditable reasoning | Synthetic |
| decided_at | timestamp | Optional until decided | System, on decision | No | When decided | Synthetic |

### Execution attempt

| Field | Type | Required/Optional | Source/producer | Mutable | Purpose | Classification |
|---|---|---|---|---|---|---|
| attempt_id | identifier | Required | System | No | Identifies this attempt | Synthetic |
| disposition_being_executed | enum (§3) | Required | System | No | What this attempt carries out | Synthetic |
| operation_id | conceptual identifier | Required | System, assigned when a disposition is authorized for execution | No | Identifies the specific intended external business operation this attempt (and any retries of it) belongs to — distinct from `disposition_being_executed`, since a case can require more than one legitimate operation of the same disposition (e.g., separate refunds for two shipments) | Synthetic |
| idempotency_key | conceptual identifier, stable per `operation_id` (not merely per case/disposition) | Required | System | No | Prevents duplicate real-world effects on retry of the same intended operation (§8) | Synthetic |
| attempted_at | timestamp | Required | System | No | When attempted | Synthetic |
| result | enum: succeeded / failed / pending | Required | Execution system response | No (a retry creates a new attempt) | Basis for `execution_status` | Synthetic |
| failure_reason | conceptual string | Optional | Execution system response | No | Diagnostic/audit detail | Synthetic |
| external_execution_reference | conceptual identifier | Optional | Execution system response | No | Traceability to the external transaction | Synthetic |

### External follow-up / retailer-side carrier-claim reference

| Field | Type | Required/Optional | Source/producer | Mutable | Purpose | Classification |
|---|---|---|---|---|---|---|
| follow_up_id | identifier | Required | System | No | Identifies the follow-up | Synthetic |
| type | conceptual enum (e.g., carrier_claim) | Required | System | No | What kind of external process | Synthetic |
| external_reference_id | conceptual identifier (e.g., carrier claim number) | Optional | External carrier claim process | No | Traceability to the external claim | Synthetic |
| opened_at | timestamp | Required | System | No | When follow-up began | Synthetic |
| status | enum (§3 `follow_up_status`) | Required | System, updated on external result | Yes | Current follow-up state | Synthetic |
| last_checked_at | timestamp | Required | System | Yes | Supports staleness/deadline checks | Synthetic |

This record — its fields, lifecycle, and ownership — is explicitly **Synthetic**. The public
carrier evidence (e.g., UPS's supporting-documents guidance, USPS's file-a-claim guidance, both
cited in `02-current-workflow.md`) establishes that an external claim path exists; it says nothing
about how, or whether, a retailer internally represents that claim. No public source is being used
to imply otherwise.

### Audit event

| Field | Type | Required/Optional | Source/producer | Mutable | Purpose | Classification |
|---|---|---|---|---|---|---|
| event_id | identifier | Required | System | No | Identifies the event | Synthetic |
| occurred_at | timestamp | Required | System | No | When it happened | Synthetic |
| event_type | conceptual enum (e.g., transition, evaluation, review_decision, execution_attempt, escalation) | Required | System | No | What kind of event | Synthetic |
| actor | conceptual string (system / frontline agent / reviewer / customer) | Required | System | No | Who/what caused it | Synthetic |
| before_state / after_state | conceptual reference to case_status/disposition/execution_status/follow_up_status | Required for transitions | System | No | What changed | Synthetic |
| detail | conceptual free text | Optional | System | No | Additional context | Synthetic |

`disposition` itself is not modeled as a standalone record — it is a field on the support case,
since it has no independent lifecycle or attributes beyond the enum value and the transitions that
set it.

## 6. Deterministic policy inputs

### Candidate policy inputs

Only inputs supported by, or plausibly derivable from, `02-current-workflow.md`:

- delivery_status
- delivery_timestamp
- address_match_result
- picture_proof_availability
- customer_self_check_completion
- order_value
- item_category
- prior_case_information (existence/count only — not a judgment about what it means)
- documentation_availability (for a carrier claim)
- carrier_claim_eligibility_result (external)
- execution_permissions (which actor/role is authorized to execute a given disposition)

### Unresolved policy definitions

| Identifier | Decision it controls | Required inputs | Expected output shape | Current status | Safe default while unresolved |
|---|---|---|---|---|---|
| `CUSTOMER_RESPONSE_WAIT_POLICY` | When/how a case waiting on the customer (`awaiting_customer_action`) may advance without an explicit customer response | phase entry time, current time | Duration or deadline timestamp | Unresolved | No automatic deadline enforcement; a case does not silently advance — a manual staleness check via `human_review` is required instead |
| `EVIDENCE_FRESHNESS_POLICY` | When a carrier evidence snapshot (`evidence_snapshot.retrieved_at`) is considered too stale to rely on for the current evaluation | evidence_snapshot.retrieved_at, evaluation time | Staleness duration/threshold | Unresolved | No automatic staleness threshold is applied; evidence age is surfaced for manual judgment in `policy_review`/`human_review` rather than either auto-trusting or auto-discarding the snapshot |
| `EXTERNAL_FOLLOW_UP_DEADLINE_POLICY` | When an external carrier process (`awaiting_external_follow_up`) requires review because no result has arrived | follow_up.opened_at, follow_up.last_checked_at, current time | Duration or deadline timestamp | Unresolved | No automatic deadline enforcement; a case does not silently expire — a manual staleness check via `human_review` is required instead |
| `FRONTLINE_REFUND_AUTHORITY` | Whether a frontline agent may approve a refund without escalation | order_value, item_category, prior_case_information | Boolean or authority tier | Unresolved | Treat as outside frontline authority; route to `human_review` |
| `REPLACEMENT_ELIGIBILITY_POLICY` | Whether a replacement may be offered/approved | order_value, item_category, documentation_availability | Boolean or eligibility tier | Unresolved | Route to `human_review`; do not auto-approve |
| `CARRIER_CLAIM_ELIGIBILITY` | Whether/when a carrier claim can be opened, per carrier | carrier, shipment circumstances, purchased services, documentation_availability | Boolean + required documentation list | Unresolved (USPS guidance notes eligibility depends on circumstances/services without specifying them) | Route to `human_review`; do not auto-file or auto-deny claim eligibility |
| `RISK_REVIEW_TRIGGER_POLICY` | What fraud/abuse signals route a case to risk/human review | prior_case_information, order_value, other unspecified signals | Boolean trigger + reason | Unresolved | Only the explicit trigger list in §7 applies; absence of a defined signal is not treated as "no risk," and no threshold is invented — but when a candidate disposition would produce an irreversible or compensating outcome (`approve_refund`, `approve_replacement`, `open_carrier_inquiry`) and risk-policy evaluation would otherwise apply, the unresolved placeholder does not let the case proceed as though no risk condition existed: `recommended_route = requires_human_review` and the case routes to `human_review` rather than executing automatically |

Safe defaults above are deliberately conservative: route to human review, request more information,
or abstain from an irreversible action. None of them silently invent business policy.

## 7. Human-review points

"No response" always means the case remains pending in `human_review` — no timeout-based auto-action
is defined anywhere in this table, and no response-time commitment is implied.

Note: an unexpected or invalid state-transition attempt is **not** a trigger in this table — it is
not a case-status decision point at all. Per §4's guard row, it is rejected, `case_status` is left
unchanged, an audit event is recorded, and a separate operational system-integrity alert/review is
raised outside the case's own `human_review_request` records (see §4 and §8). The table below covers
only genuine case-level triggers that transition `case_status` to `human_review`. A linkage review
(opened from `intake_failed`) may only resolve to `linked`, `awaiting_customer_action`, or `closed`;
every other trigger below may only resolve to `evidence_gathering`, `disposition_selection`,
`awaiting_external_follow_up`, or `closed`.

| Trigger | Information presented | Decision reviewer must make | Permitted resulting transitions | If reviewer does not respond | Evidence classification |
|---|---|---|---|---|---|
| Customer/order linkage uncertainty | Attempted identifiers, any partial matches | Confirm the correct link, request more info, or close as unresolvable | → `linked` (confirm), → `awaiting_customer_action` (request more info), → `closed` (unresolvable) | Case remains `human_review` | Synthetic |
| Contradictory customer or carrier evidence | Customer report, all available evidence snapshots | Decide which evidence to weight, request more evidence, or proceed | → `evidence_gathering` (request more evidence), → `disposition_selection` (proceed) | Case remains `human_review` | Synthetic (that conflicting evidence is a plausible complication is Inferred; the trigger/decision mechanics are Synthetic) |
| Case outside frontline authority | `policy_evaluation_result`, order_value, item_category | Approve, deny, or modify the disposition within reviewer authority | → `disposition_selection` | Case remains `human_review` | Synthetic |
| Policy placeholder unresolved at runtime | Which §6 placeholder, inputs available | Make a manual decision standing in for the missing policy, recorded as such | → `disposition_selection` | Case remains `human_review` | Synthetic |
| Suspected duplicate compensation | Prior case reference(s), current case data | Confirm duplicate (deny/merge) or confirm distinct (proceed) | → `disposition_selection` (confirmed distinct), → `closed` (confirmed duplicate, merged) | Case remains `human_review` | Synthetic |
| High-risk or fraud review | `policy_evaluation_result`, relevant signals | Approve, deny, or request more info — each recorded as a disposition | → `disposition_selection` (the reviewer's chosen disposition, including `request_more_info`/`advise_self_check_or_wait`, is then routed onward by the `disposition_selection` rules in §4) | Case remains `human_review` | Synthetic |
| Failed refund/replacement execution | Execution attempt record(s), disposition | Retry the same intended operation (same `operation_id`/`idempotency_key`), or select a different disposition (new `operation_id`) | → `disposition_selection` (both a retry and an alternate disposition re-enter execution from here) | Case remains `human_review`; no silent auto-retry | Synthetic |
| External follow-up result received (favorable or unfavorable) | Follow-up record, result | Accept the result and close, or select an alternate disposition | → `disposition_selection` (alternate disposition), → `closed` (accept result) | Case remains `human_review` | Synthetic |
| Rejected or expired carrier action | Follow-up record, original disposition | Select an alternate disposition (including `deny`) | → `disposition_selection` | Case remains `human_review` | Inferred (that carrier claims can be rejected or expire is Inferred from public carrier guidance; the trigger/decision mechanics are Synthetic) |
| Follow-up deadline exceeded (`EXTERNAL_FOLLOW_UP_DEADLINE_POLICY` unresolved — see §6) | Follow-up record, elapsed time | Continue waiting, or select an alternate disposition | → `awaiting_external_follow_up` (continue waiting), → `disposition_selection` (alternate disposition) | Case remains `human_review`; no invented auto-expiry | Synthetic |

## 8. Failure behavior

Five failure categories are kept distinct so they cannot collapse into one another:

- **Business denial** — `disposition = deny`; a considered outcome, recorded with rationale in
  `policy_evaluation_result` or the reviewer's `decision_rationale`.
- **Technical execution failure** — an `execution_attempt` with `result = failed`; `case_status`
  moves to `human_review`; `disposition` is *not* reverted.
- **Unavailable dependency** — `retrieval_status = failure` on a customer/order/shipment/evidence
  lookup, or an execution/carrier system unreachable. This is a data-quality condition on a
  specific record, not a `case_status` value — the case stays in whatever phase it was attempting,
  and an `audit_event` records the failure.
- **Unresolved policy** — `policy_evaluation_result.unresolved_placeholders_encountered` is
  populated; routes to `human_review` per the §6 safe defaults.
- **Pending human decision** — `case_status = human_review` with a `human_review_request` whose
  `decision` is not yet set.

Mapping the required failure situations onto these categories:

| Failure situation | Category | How it's represented |
|---|---|---|
| External system unavailable | Unavailable dependency | `retrieval_status = failure`, or an `execution_attempt`/follow-up check that cannot reach the external system |
| Order/customer linkage failure | Unavailable dependency → drives a transition | `match_status = not_found`/`ambiguous` → `case_status = intake_failed` → human-review trigger |
| Incomplete customer information | Not a denial | `customer_report` fields left optional/partial; `case_status` stays `awaiting_customer_action` |
| Conflicting carrier evidence | Pending human decision | Multiple `evidence_snapshots` disagree → human-review trigger; not silently resolved by picking one |
| Stale evidence | Unresolved policy (conceptually) | `evidence_snapshot.retrieved_at` age relative to current evaluation is a candidate policy input; what counts as "stale" is governed by `EVIDENCE_FRESHNESS_POLICY` (§6), which is not fixed here — no threshold is invented, so this cannot yet trigger automatically and is a known gap (see §10) |
| Execution failure after approval | Technical execution failure | `execution_attempt.result = failed`; `execution_status = failed` (never silently reset to `succeeded` or reverted) |
| Carrier action rejected or expired | Distinct external/business result, not a bug | `follow_up_status = rejected`/`expired` → human-review trigger |
| Follow-up deadline passed | Unresolved policy | Governed by `EXTERNAL_FOLLOW_UP_DEADLINE_POLICY` (§6), which is not yet defined; currently no deadline exists to "pass," so this cannot yet trigger automatically |
| Invalid transition attempted | System-integrity condition, not business/technical | Guarded centrally (§4, last row); rejected without mutating `case_status`; an audit event is recorded and a separate operational integrity alert/review is raised (not a `case_status = human_review` transition) — distinguished because no case data caused it |
| Duplicate command or retry | Idempotency concern | See principle below |

**Idempotency principle**: retrying the same refund, replacement, or carrier-action command must
not knowingly create a duplicate real-world effect. Conceptually, an `execution_attempt` carries an
`idempotency_key` stable per the intended external business operation it represents (`operation_id`),
not merely per (case, disposition): retries of that same intended operation reuse the same
`operation_id` and `idempotency_key`, and an attempt made with a key that already has a `succeeded`
result must not re-execute — it should surface the prior result instead. A newly authorized, distinct
operation — for example, a second shipment's refund on the same case, or a re-authorized replacement
after an earlier one was denied — receives its own `operation_id` and its own `idempotency_key`, since
it is not a retry of the earlier operation. This is a conceptual constraint on the model, not an
implementation.

## 9. Worked deterministic walkthrough

All identifiers and values below are synthetic and illustrative only; the disposition reached is
**not** a claim about real retailer policy.

1. **Initial input**: Customer contacts support about order `ORDER-1001`, tracking shows delivered,
   package not received. Customer states they already checked the porch and asked a neighbor.
2. **Records created/referenced**: Support case `CASE-0001` (`case_status = intake`); Customer
   reference `CUST-0042` (`match_status = matched`); Order reference `ORDER-1001`
   (`order_value = $68.00`, `item_category = home_goods`); Shipment reference `SHIP-7788`
   (`carrier = CarrierX`, `tracking_id = TRK-555`); embedded `customer_report`
   (`when_and_how_checked = "checked porch, asked neighbor"`).
3. **Lifecycle changes**: `intake` → `linked` (customer/order matched, classified
   delivered-not-received) → `evidence_gathering`.
4. **Evidence retrieved**: Carrier evidence snapshot `EVID-01`
   (`delivery_status = delivered`, `delivery_timestamp` = previous day, `picture_proof_available = false`,
   `retrieval_status = success`). Because the customer's own report already reflects a completed
   self-check, `awaiting_customer_action` is skipped: `evidence_gathering` → `policy_review`.
5. **Policy evaluation**: `policy_evaluation_result` is created with
   `inputs_used = {delivery_status=delivered, address_match_result=match,
   picture_proof_availability=false, customer_self_check_completion=true, order_value=$68.00,
   item_category=home_goods, prior_case_information=none_found}`. Determining frontline authority
   requires `FRONTLINE_REFUND_AUTHORITY`, which is unresolved →
   `unresolved_placeholders_encountered = [FRONTLINE_REFUND_AUTHORITY]`,
   `recommended_route = requires_human_review`.
6. **Human-review point**: `case_status`: `policy_review` → `human_review`. Review request `REV-01`
   opened, `triggered_by = "policy placeholder unresolved at runtime"`.
7. **Selected disposition**: Reviewer decision (synthetic, standing in for the missing policy for
   this one case only): `decision = approve_refund`. `case_status`: `human_review` →
   `disposition_selection`; `disposition = approve_refund`. Because `approve_refund` requires
   execution, `case_status` → `executing` and `execution_status = not_started`.
8. **Execution result**: Execution attempt `EXEC-01` (`operation_id = CASE-0001-refund-SHIP-7788-1`,
   `idempotency_key = CASE-0001-refund-SHIP-7788-1`, `result = succeeded`,
   `external_execution_reference = REFUND-9001`). `execution_status = succeeded`. No external
   follow-up applies: `follow_up_status = not_applicable`. (A retry of this same operation would reuse
   `operation_id = CASE-0001-refund-SHIP-7788-1`; a distinct later operation — e.g., a refund for a
   second shipment on this case — would receive a new `operation_id`.)
9. **Final state**: `case_status`: `executing` → `closed`. Final case:
   `case_status = closed`, `disposition = approve_refund`, `execution_status = succeeded`,
   `follow_up_status = not_applicable`.

This walkthrough illustrates the model's mechanics only. The reviewer's refund approval stands in
for `FRONTLINE_REFUND_AUTHORITY`, which remains unresolved in general (§6).

## 10. Readiness conclusion

**Sufficiently defined for implementation**: the four orthogonal state fields (§3), the guarded
transition table (§4), and the core record shapes (§5) are concrete enough to implement as a
deterministic domain model with transition validation — independent of policy content, external
integrations, or AI behavior.

**Intentionally unresolved**: all seven named policy placeholders (§6), including the now-separated
`EVIDENCE_FRESHNESS_POLICY` (the "stale evidence" gap) and `EXTERNAL_FOLLOW_UP_DEADLINE_POLICY` (the
"follow-up deadline" gap) noted in §8; fraud/risk criteria beyond the explicit trigger list in §7;
documentation-completeness rules; and the real shape, ownership, or existence of any retailer-side
carrier-claim system, which remains explicitly Synthetic.

**Next increment**: implement the deterministic domain model and transition validation — the four
status fields plus the allowed-transition guards from §4 — as plain code with tests exercising both
valid and invalid transitions (including the "refund approved but not executed" guard called out in
§4). This assessment follows directly from the design above: nothing in §2–§9 requires an external
integration or AI/LLM behavior to validate, so no other increment needs to come first.

## Data safety

**This repository increment** contains only a candidate deterministic model and synthetic
illustrative values (§9). No real customer-level data of any kind appears in this document.

- Data classification of this document: none — every identifier, order, evidence, and case value in
  it is synthetic.
- Does this document contain PII or other sensitive customer data? No — but see below: the workflow
  it models would.
- Is there explicit authorization to access or use real data for this increment? Not applicable — no
  real customer or proprietary data is used or needed to produce this design document.
- May this document's content be sent to a model provider (e.g., in a prompt or API call)? Yes — all
  content here is synthetic, safe to use in prompts.
- May this document's content appear in fixtures, prompts, traces, logs, screenshots, or evaluation
  datasets? Yes, under the same condition.

**The modeled production workflow** (§2, §5) would handle PII and other sensitive customer/commerce
data, including candidate categories such as customer identity or account references, delivery
addresses, order and shipment information, customer support messages, prior-case history, and refund
or replacement activity. This document does **not** state or imply that the modeled system is
PII-free — it states only that this document's own synthetic content is. Before any real data of
these categories is used against this design — in an implementation, fixture, prompt, trace, log,
screenshot, or evaluation dataset — it would require explicit authorization, access controls,
retention rules, logging/redaction rules, and provider/data-transfer review. None of that governance
is established here; it is a prerequisite for a later increment.

- What are the retention requirements for this document? Not applicable — synthetic only. Retention
  rules for real customer/order data are a prerequisite for any later increment that would use it,
  not yet defined.
- Are there compliance constraints (regulatory, contractual, or internal policy)? Not applicable to
  this document's synthetic content; compliance review of the modeled production workflow is a
  prerequisite for any later increment that would use real data.

**Default:** this project uses synthetic, placeholder data unless use of real data has been
explicitly authorized and a safe handling plan is recorded here. That default holds for this
increment. Real customer data may not appear in fixtures, prompts, traces, logs, screenshots, or
evaluation datasets unless explicitly authorized and governed as described above; synthetic data may
be used freely.

**Authorization scope:** authorization to access or use real data in a controlled external
environment does not authorize storing or copying credentials, customer records, PII, or other
sensitive data into this Git repository. Real sensitive data must never appear in tracked
documentation, fixtures, prompts, traces, logs, screenshots, or evaluation datasets (see
`AGENTS.md`). When real-world evidence is used, repository artifacts must contain only sanitized,
aggregated, or synthetic representations that cannot identify customers or expose sensitive
information. Any controlled use of real data happens outside tracked repository artifacts, subject
to the applicable authorization and governance requirements.

## Evidence log

No new external research was conducted for this increment, per scope. Every Reported/Inferred
classification above is carried forward unchanged from the evidence already logged in
`01-business-context.md` and `02-current-workflow.md`; see those documents' evidence logs for
source, date, and confidence. All state, transition, record, and policy-placeholder modeling
choices introduced in this document are labeled Synthetic in place, as they are project modeling
decisions rather than claims about any observed system.

## Open questions

Carried forward and newly scoped to this design:

- The seven unresolved policy placeholders in §6 (`CUSTOMER_RESPONSE_WAIT_POLICY`,
  `EVIDENCE_FRESHNESS_POLICY`, `EXTERNAL_FOLLOW_UP_DEADLINE_POLICY`, `FRONTLINE_REFUND_AUTHORITY`,
  `REPLACEMENT_ELIGIBILITY_POLICY`, `CARRIER_CLAIM_ELIGIBILITY`, `RISK_REVIEW_TRIGGER_POLICY`).
- What counts as "stale" evidence (`EVIDENCE_FRESHNESS_POLICY`) and when an unresolved external
  follow-up requires review absent a result (`EXTERNAL_FOLLOW_UP_DEADLINE_POLICY`) are separate,
  still-unresolved policies (§6, §8).
- Whether a case can have more than one concurrent `follow_up` (e.g., multiple shipments each with
  their own carrier claim) — this increment models `follow_up` as a single reference per case;
  multi-shipment cases may need this revisited once the domain model is implemented.
- Whether `human_review_request.decision` values should be constrained per-trigger in the
  implemented model (this document lists permitted transitions per trigger in §7 as a starting
  point, not a finalized set).
