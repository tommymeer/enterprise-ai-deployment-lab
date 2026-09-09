# Production Rollout

**30-60-90 deployment plan · Not a production-readiness claim**

This plan describes how I would move the delivered-not-received support workflow from a lab prototype toward production.

The governing rule is simple:

> **Autonomy expands only when evidence supports it. Time does not automatically unlock authority.**

The prototype currently proves a bounded workflow against synthetic cases. Production deployment would need to validate three things separately:

1. **Technical correctness** — does the system behave safely and predictably?
2. **Operational adoption** — does it fit the real support workflow?
3. **Customer/business value** — does it improve outcomes enough to justify cost and complexity?

## Rollout path

**Discovery → Shadow mode → Human-reviewed pilot → Limited autonomy → Controlled expansion**

| Phase | What happens | Gate to advance |
| --- | --- | --- |
| **Discovery + readiness** | Validate the real workflow, policies, systems, authority boundaries, security, failure modes, and baseline economics. | Reliable sources of truth, explicit authority limits, recoverable state design, safe consequential APIs, and agreed success/stop criteria. |
| **Shadow mode** | Run real cases through the system without autonomous consequential action. Compare system outputs with human decisions and later outcomes. | Stable extraction/linkage, reconstructable traces, acceptable dependency behavior, and no unresolved severe trajectory or authorization failures. |
| **Human-reviewed pilot** | Put recommendations into the live workflow while humans approve consequential actions. Measure overrides, review time, fallback, execution, adoption, and value. | Acceptable reviewer agreement, workflow outcomes, recovery behavior, incident profile, and evidence of business value. |
| **Limited autonomy** | Enable execution only for narrowly defined low-risk slices that have earned it. | Slice-specific evaluation evidence, safe authorization, idempotent execution/recovery, acceptable incidents and customer outcomes, and explicit owner approval. |
| **Controlled expansion** | Expand one meaningful dimension at a time. | The new slice passes evaluation and regression gates, observability is ready, and rollback criteria are explicit. |

Approximate sequencing:

- **0–30 days:** discovery, readiness, shadow preparation
- **30–60 days:** shadow mode and reviewed pilot
- **60–90 days:** limited autonomy, only if gates are met
- **Afterward:** controlled expansion

## Autonomy boundary

Policy and execution authority are separate.

A policy may determine that a refund is the correct resolution. Authorization determines whether the system may execute it.

If policy approves a **$150 refund** but the autonomous authority limit is **$100**, the case goes to human review. Execution does not begin.

The system must preserve this sequence:

**evidence → policy → disposition → authorization → execution**

A correct disposition does not imply permission to act.

## What must be true before autonomy expands

Evidence must support the exact slice receiving more authority.

That means:

- reliable customer, order, shipment, and carrier linkage
- correct workflow trajectory, not just correct final outcomes
- explicit and satisfied authorization rules
- idempotent execution and duplicate suppression
- durable recovery from retries, restarts, and unknown execution outcomes
- acceptable review, fallback, clarification, and incident behavior
- usable, reconstructable traces
- demonstrated value after residual human work and operating cost
- explicit approval from the relevant policy, support, risk, security, and operational owners

Thresholds should come from the real risk owners and pilot evidence rather than being invented in advance.

## Rollback behavior

Autonomous execution should be independently disableable without taking down intake, recommendations, human review, or the established manual workflow.

| Signal | Immediate behavior |
| --- | --- |
| Model/extraction degradation | Stop autonomous progression; route to validated structure or manual review. |
| Carrier/evidence dependency degradation | Safe-stop or use operational fallback; do not infer missing evidence. |
| Authorization anomaly | Disable autonomous execution for the affected authority envelope. |
| Execution API error or unknown result | Preserve disposition and case state, reconcile by operation identity, and route to human review. |
| Regression-gate failure | Block the release or expansion and keep the last proven scope. |
| Duplicate-action concern | Freeze the affected execution path while preserving history and review capability. |

A serious defect can move a slice backward from autonomy to reviewed or shadow operation. Re-entry requires evidence that the defect is repaired.

## What we monitor

| Category | Highest-level signals |
| --- | --- |
| **Technical** | Model/dependency failures, latency, cost, state/execution failures, retries, duplicate-action risk |
| **Workflow** | Coverage, path mix, overrides, review/fallback/clarification rates, repeated or unresolved cases |
| **Business/customer** | Released support capacity, unnecessary compensation, cost per case, resolution outcomes, customer outcomes |

The system should support reconstruction of:

**input → evidence → policy → disposition → authorization → execution**

with versions, state transitions, retries, human overrides, and external operation references.

## Production capabilities still required

The lab prototype does **not** yet include:

- durable persistence, checkpointing, and restart recovery
- real retailer, support, order, carrier, and execution integrations
- enterprise service identity, secrets management, and PII controls
- production observability and alerting
- formal operating ownership, incident response, and on-call processes

These are production requirements, not implemented capabilities.

## Pilot measurement

A real pilot should measure:

- extraction and evidence-linkage correctness
- outcome and trajectory correctness separately
- reviewer agreement and override reasons
- residual human effort by workflow path
- clarification, fallback, and repeated-contact rates
- execution success and duplicate-action prevention
- dependency failures, retries, latency, and cost
- customer outcomes and operational incidents
- whether released support capacity becomes realizable value

A technically correct system can still fail deployment if reviewers do not trust it, the workflow creates hidden rework, customer outcomes worsen, or the economics do not hold.

→ [Deployment economics](05-deployment-arithmetic.md)

<details>
<summary><strong>Readiness details</strong></summary>

### Workflow and business discovery

Before deployment, validate the actual DNR workflow rather than treating the lab's synthetic workflow as fact.

That includes:

- eligible case volume and variation
- handling and review time
- compensation amounts and outcomes
- policies, exceptions, and risk tolerance
- actors, decision owners, and escalation paths
- current support tooling and workarounds
- sources of truth across customer, order, shipment, carrier, and ticket systems
- real refund/replacement authority limits

Synthetic ROI inputs should be replaced with approved, aggregated measurements.

### Integration and schema readiness

Confirm:

- stable identifiers across customer, order, shipment, ticket, and carrier records
- behavior for split shipments, guest orders, corrected identifiers, and conflicting records
- API contracts, rate limits, dependency SLAs, and sandbox/test environments
- behavior for missing, stale, partial, or contradictory evidence

Consequential APIs should accept a stable operation identity or equivalent deduplication control before they are eligible for autonomous execution or retries.

### Security and authorization

Production requires:

- dedicated service identity
- least-privilege credentials
- managed secrets
- approved PII handling and retention
- auditable linkage from each action to the case, policy version, and authority decision
- explicit refund/replacement authority by action, amount, currency, and approving owner

### Persistence and recovery

Production state must survive restarts.

Execution attempts should durably retain:

- operation identity
- idempotency key
- attempt result
- external reference
- state before and after execution

A restart must never turn an unknown result into assumed success or repeat a known successful effect.

</details>

<details>
<summary><strong>Expansion and regression rules</strong></summary>

Expand one meaningful dimension at a time where possible:

- case type
- compensation amount
- evidence quality
- customer segment
- carrier
- geography
- integration reliability

Each expansion should:

- add or refresh representative evaluation cases
- pass relevant regression tests
- confirm end-to-end observability and operator ownership
- define a specific rollback condition
- compare technical, workflow, customer, and business results with the prior slice
- preserve human review and operational fallback

A production regression blocks the affected release or expansion until repaired and represented by a sanitized deterministic test or evaluation case.

Outcome metrics cannot waive a trajectory or authorization failure.

</details>

## Reusable deployment patterns

Patterns that appear reusable from this project:

- **policy → disposition → authorization → execution**
- explicit workflow state plus append-only trace
- outcome vs. trajectory evaluation
- deterministic invariants around consequential actions
- failure attribution by system layer
- safe-stop and idempotency patterns
- shadow → reviewed → autonomy rollout gates
- explicit separation between technical evidence and ROI evidence

Domain-specific policy, refund limits, DNR states, carrier evidence, and retailer rules should remain domain-specific until another project proves genuine cross-domain reuse.
