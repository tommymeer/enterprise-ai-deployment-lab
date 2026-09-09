# Business Context

**Synthetic reference scenario · Not an observed retailer workflow**

This project models one narrow ecommerce support problem: a customer reports that carrier tracking shows an order as delivered, but the package cannot be found.

The goal of this document is to define the business problem, the actors, the risks, and the evidence boundary clearly enough to design the workflow without pretending that synthetic assumptions are customer facts.

## Reference scenario

Synthetic retailer:

- US direct-to-consumer ecommerce company
- ordinary physical consumer goods
- shipments via UPS, FedEx, and USPS
- delivered-not-received (DNR) cases handled through customer support

Out of scope:

- marketplace sellers
- grocery / same-day delivery
- regulated or controlled goods
- international customs cases
- digital products
- extremely high-value merchandise

No real company is modeled here.

## Problem

A customer may report that a package is missing even though carrier tracking says it was delivered.

That creates an evidence-reconciliation problem across:

- the customer report
- retailer order and shipment records
- carrier tracking and proof-of-delivery evidence
- retailer policy
- execution authority
- the risk of two opposite errors

### Error 1 — incorrect denial

A legitimate non-receipt is denied or under-resolved.

Potential consequences:

- customer frustration
- repeated contacts
- loss of trust
- churn or retention risk

### Error 2 — incorrect compensation

A refund or replacement is issued when it was not warranted.

Potential consequences:

- unnecessary compensation cost
- duplicate compensation
- fraud or abuse exposure
- inconsistent policy enforcement

The system must therefore optimize neither for maximum automation nor maximum compensation avoidance. It must support a **fast, fair, and defensible resolution under uncertainty**.

## Relevant actors

These roles are plausible for the synthetic retailer; they are not claims about a specific company's organization.

| Actor | Role in the workflow | Primary concern |
| --- | --- | --- |
| Customer | Reports the missing package and provides information | Fast, fair resolution |
| Frontline support agent | Handles the inbound case | Clear evidence, consistent decisions, low unnecessary effort |
| Carrier | Provides tracking and delivery evidence | External evidence and, in some cases, claim handling |
| Risk / escalation reviewer | Reviews ambiguous, high-risk, or out-of-authority cases | Control fraud, abuse, and unsafe automation |
| Finance / operations | Bears compensation and operating cost | Predictable cost and operational efficiency |

Who owns each decision in a real retailer remains a discovery question.

## Desired outcomes

### Customer

- resolve the case quickly
- avoid unnecessary repetition or proof burden
- receive a fair explanation and outcome

### Business

- resolve legitimate cases consistently
- reduce avoidable support effort
- avoid unnecessary compensation
- preserve escalation for ambiguity and risk
- maintain auditability around consequential actions

No target SLA, cost-per-case threshold, automation rate, or error tolerance is treated as known.

## What public evidence supports

Public retailer and carrier guidance provides narrow evidence that several real-world mechanics exist:

- customers may be asked to verify the delivery location, address, household members, neighbors, or other delivery details
- some retailers recommend waiting before treating a delivered package as missing
- carriers may expose tracking history and picture proof of delivery
- missing-package and carrier-claim paths exist

Examples used in the original discovery work:

- Amazon — “Find a Missing Package That Shows As Delivered”
- Walmart — “Order Not Received”
- FedEx — “FedEx says delivered but no package”
- UPS — “Tracking Support”

These sources are **customer-facing guidance**. They do not establish the internal workflow, policy, authority model, or system architecture of any retailer.

That distinction matters: public help content can constrain the problem space, but it cannot be treated as an observed enterprise process.

## What remains synthetic or unknown

The project intentionally does **not** claim to know:

- how a real retailer receives and classifies DNR cases
- what information a frontline agent can access
- the exact investigation sequence
- refund or replacement thresholds
- frontline authority limits
- fraud or abuse rules
- prior-claim-history usage
- escalation ownership
- carrier-claim ownership
- case volume
- active handling time
- compensation error rates
- realized cost or ROI

Those inputs must come from customer discovery, approved operational data, or pilot measurement.

## Evidence model

The project uses three evidence categories:

### Reported

Supported by substantive public evidence.

Example: carrier tracking and picture proof can exist.

### Inferred

A plausible operational conclusion drawn from the structure of the problem, but not directly observed.

Example: a retailer may retrieve carrier evidence during support handling.

### Synthetic

A deliberate modeling choice made to create a coherent reference system.

Example: the synthetic retailer profile, workflow states, authority limits, and test cases.

Later implementation evidence may additionally be labeled **Implemented** or **Measured** where appropriate.

## Core discovery questions for a real deployment

Before treating this workflow as production-relevant, I would need to answer:

1. How do DNR cases enter the support operation?
2. Which systems contain the authoritative customer, order, shipment, and carrier data?
3. What evidence do agents actually inspect?
4. What policies determine refund, replacement, wait, denial, or escalation?
5. What can frontline agents approve without additional authority?
6. What exceptions create the most rework or risk?
7. How often do cases require clarification, review, or fallback?
8. What are the actual handling-time and compensation economics?
9. Which customer outcomes matter most?
10. Who owns rollout, policy, risk, security, and incident decisions?

Those questions are more important than adding model sophistication before the operating reality is known.

## Data boundary

Repository artifacts use synthetic data and public information only.

No real customer records, PII, credentials, raw conversations, or sensitive traces belong in this repository.

A production version of this workflow could involve sensitive commerce and support data, including customer identifiers, addresses, order and shipment details, support messages, prior-case history, and refund activity. Any real-data use would require explicit authorization, access controls, retention rules, redaction/logging rules, and provider/data-transfer review.

## Why this is sufficient to proceed

This context is enough to build a **clearly labeled synthetic workflow hypothesis** and test the system mechanics around it.

It is not enough to claim:

- a real retailer workflow
- production policy
- real authority thresholds
- customer-specific economics
- production-ready deployment

The next layer of the project therefore treats the workflow itself as a hypothesis to model and test, not as discovered fact.

→ [Current workflow](02-current-workflow.md) · [System boundaries](03-system-boundaries.md)
