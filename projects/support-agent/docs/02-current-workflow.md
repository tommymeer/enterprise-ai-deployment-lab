# Current Workflow

**Synthetic reference workflow · Not an observed retailer process**

This document models a plausible delivered-not-received support workflow so the system can be evaluated against a concrete operating process rather than a vague “AI support agent” concept.

No real retailer’s internal workflow was observed. Public retailer and carrier guidance constrains parts of the problem, but the ordering, ownership, internal systems, policy logic, and case states below are synthetic or inferred unless noted otherwise.

→ [Business context](01-business-context.md) · [System boundaries](03-system-boundaries.md)

## Workflow at a glance

```text
1. Intake and identify customer/order
2. Confirm delivered-not-received case type
3. Capture customer report
4. Retrieve order and shipment records
5. Verify address, delivery status, and timestamp
6. Retrieve carrier evidence
7. Ask customer to self-check / wait when appropriate
8. Apply internal policy and case context
9. Select disposition or escalate
10. Execute the selected outcome
11. Communicate, document, and follow up
```

The workflow deliberately separates:

**evidence gathering → policy → disposition → authorization → execution → follow-up**

That separation is important because a correct business outcome does not automatically imply that the system has enough evidence or authority to execute it.

## Reference workflow

| Step | What happens | Main evidence / system | Output |
| --- | --- | --- | --- |
| **1. Intake** | Open the case and identify the customer and order. | Support conversation, customer/account lookup, order identifier | Case created and linked, or blocked on identification |
| **2. Classify** | Confirm that the issue is delivered-not-received rather than another order issue. | Customer report, order/fulfillment data, carrier status | DNR workflow or general triage |
| **3. Capture report** | Record what the customer says: identifier, address, what they checked, and any relevant context. | Customer message | Structured customer report |
| **4. Retrieve retailer records** | Pull order, shipment, fulfillment, and ship-to data. | Order / shipment systems | Trusted order and shipment context |
| **5. Verify delivery facts** | Compare address and delivery details; confirm delivery status and timestamp. | Order record, carrier tracking | Address / status evidence |
| **6. Retrieve carrier evidence** | Pull tracking history and proof-of-delivery evidence when available. | Carrier source | Evidence snapshot or explicit unavailable result |
| **7. Customer action** | Ask the customer to check the delivery location, household members/neighbors, correct an identifier, or wait where appropriate. | Customer-facing support channel | Customer response, continued wait, or self-resolution |
| **8. Policy review** | Evaluate the evidence against merchant rules, case context, risk, and authority constraints. | Policy inputs, order value, case history where permitted | Route or recommendation |
| **9. Select disposition** | Choose the business outcome or route to human judgment. | All validated evidence and policy results | Refund, replacement, clarification, denial, carrier action, or review |
| **10. Execute** | Carry out the selected consequential action only after authorization. | Refund/replacement/claim execution systems | Success, failure, or external follow-up |
| **11. Communicate and follow up** | Tell the customer what happened, record rationale, and keep the case open if an external process is pending. | Support channel, workflow state, trace | Closed case or pending follow-up |

## Main workflow paths

The reference workflow supports four broad paths.

### 1. Straight-through resolution

Evidence is sufficient, policy selects a permitted outcome, authorization is satisfied, and execution succeeds.

Examples:

- refund
- replacement
- denial with explanation

### 2. Human review

The system has enough information to identify the case, but judgment or authority is required.

Examples:

- contradictory evidence
- high-value or out-of-authority refund
- suspected duplicate compensation
- unresolved risk or policy condition
- failed execution
- external result requiring interpretation

### 3. Clarification / customer action

The workflow cannot proceed because the customer must provide or confirm something.

Examples:

- order identifier not found
- missing required information
- customer asked to check the delivery location or wait
- corrected identifier required

### 4. Operational fallback

A dependency or system failure prevents safe progression.

Examples:

- order or carrier lookup unavailable
- malformed external response
- execution API failure
- unknown external execution result

Fallback does not invent evidence or reinterpret failure as approval.

## Possible dispositions

The reference workflow may select:

- request more information
- advise self-check or wait
- open or recommend a carrier inquiry
- approve replacement
- approve refund
- deny with explanation
- route to human review

Human review is not treated as a business disposition in the implementation. It is a workflow state used when judgment or additional authority is required.

## Evidence sources and ownership

The workflow depends on several external systems but does not own their records.

| System category | Role |
| --- | --- |
| Support channel | Receives customer messages and sends responses |
| Customer/account system | Source of truth for customer identity and account linkage |
| Order-management system | Source of truth for order data |
| Fulfillment / shipment system | Source of truth for shipment data |
| Carrier tracking source | Source of truth for delivery status and proof-of-delivery evidence |
| Merchant policy | Source of business rules and authority limits |
| Refund / replacement system | Executes approved consequential actions |
| Carrier claim process | Handles external follow-up where applicable |

The workflow stores references, validated snapshots, state, decisions, and trace evidence around those systems rather than pretending to replace them.

## Public evidence vs. synthetic workflow

Public guidance supports a narrow set of real-world mechanics:

- customers may be asked to inspect the delivery location, check with household members or neighbors, verify the address, or wait
- carrier tracking can include delivery status, timestamps, tracking history, and sometimes picture proof
- carrier inquiry or claim paths can exist

These are supported by consumer-facing guidance from retailers and carriers such as Walmart, FedEx, UPS, USPS, and Amazon.

What public guidance does **not** establish:

- retailer-side workflow ordering
- frontline authority limits
- fraud rules
- refund or replacement thresholds
- internal case states
- system architecture
- who owns carrier claims
- how prior-case history is used

Those remain synthetic or discovery questions.

## Key exception paths

A production workflow must handle cases such as:

- customer or order cannot be identified
- corrected order identifier is required
- multiple shipments exist
- tracking is unavailable or stale
- carrier evidence conflicts with the customer report
- picture proof is unavailable
- address information conflicts
- required documentation is missing
- customer does not respond
- case exceeds frontline authority
- duplicate compensation is suspected
- carrier or retailer dependency is unavailable
- refund/replacement execution fails
- external carrier action is rejected, expires, or remains unresolved
- duplicate execution is attempted

The system should preserve the responsible failure layer rather than collapsing all of these into a generic error state.

## What the workflow intentionally does not assume

The reference workflow does not invent:

- refund thresholds
- replacement eligibility rules
- fraud scoring
- wait durations
- evidence-freshness thresholds
- frontline permission limits
- carrier-claim eligibility
- customer-specific SLAs
- production case volume or cost

Those are customer-specific operating rules that should be established through discovery, approved policy, or pilot evidence.

## What would need validation in a real deployment

Before treating this workflow as production-relevant, I would validate:

1. how DNR cases actually enter support
2. which systems agents use
3. which sources are authoritative
4. what evidence agents inspect
5. where the current workflow creates rework or delay
6. which outcomes frontline agents can approve
7. which cases require review
8. how customer clarification and follow-up work
9. what carrier-claim ownership looks like
10. real path mix, handling time, error rates, and compensation outcomes

The synthetic workflow is a starting hypothesis for those questions, not a substitute for answering them.

## Data boundary

This repository uses synthetic workflow examples and public information only.

No real customer records, PII, credentials, raw conversations, or sensitive traces belong in tracked repository artifacts.

A real implementation would require explicit authorization and governance for customer, order, shipment, support, and compensation data.

## Relationship to the implementation

The workflow above was the operating hypothesis used to derive the deterministic domain model.

The implementation now makes several of these boundaries explicit in code:

- bounded intake routing
- customer/order linkage
- evidence retrieval
- policy and disposition
- authorization
- execution
- human review
- workflow state
- append-only traces
- failure and recovery behavior

→ [System boundaries](03-system-boundaries.md) · [Project walkthrough](../README.md)
