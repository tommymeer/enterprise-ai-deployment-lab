# Production Rollout / 30-60-90 Deployment Plan

**Scope:** delivered-not-received (DNR) support cases. **Evidence boundary:** this is a production
deployment plan for the current lab prototype, not a claim that the prototype is production-ready
and not an infrastructure build.

> **Autonomy expands only when evidence supports it. Time does not automatically unlock authority.**

## What are we deploying?

A bounded DNR support workflow that links evidence, applies policy, proposes a disposition, checks
authorization, and either executes safely or routes the case to a person. The lab currently validates
this flow against synthetic cases using bounded extraction, deterministic controls, and in-process
traces. Production deployment would connect the workflow to real support operations and validate
technical correctness, adoption, and customer/business value separately.

## How rollout progresses

**Discovery → Shadow mode → Human-reviewed pilot → Limited autonomy → Controlled expansion**

| Phase | What happens | Gate to advance |
| --- | --- | --- |
| Discovery + readiness | Validate real workflow, policies, data, integrations, authority boundaries, security, and baseline economics. | Reliable sources of truth, explicit authority limits, recoverable state design, safe consequential APIs, and agreed success/stop criteria. |
| Shadow mode | Run real cases through the system without autonomous consequential action; compare system outputs with human decisions and later outcomes. | Stable extraction/linkage, no unresolved severe trajectory or authorization failures, reconstructable traces, and acceptable dependency behavior. |
| Human-reviewed pilot | Put recommendations into the live workflow while humans approve consequential actions. Measure overrides, review time, fallback, execution, adoption, and value. | Acceptable reviewer agreement, workflow outcomes, recovery, operational incidents, and evidence of business value. |
| Limited autonomy | Enable execution only for narrowly defined low-risk slices that have earned it. | Slice-specific evaluation evidence, safe authorization, idempotent execution/recovery, acceptable incidents and customer outcomes, and explicit owner approval. |
| Controlled expansion | Expand one meaningful dimension at a time. | The new slice passes evaluation and regression gates, observability is ready, and rollback criteria are explicit. |

Approximate sequencing, not automatic calendar promotion:

- **~0–30 days:** discovery/readiness and shadow preparation
- **~30–60 days:** shadow mode and reviewed pilot
- **~60–90 days:** limited autonomy, if gates are met
- **Afterward:** controlled expansion

## What must be true before autonomy expands?

Evidence must support the exact slice receiving more authority: correct linkage and workflow
trajectory, acceptable customer and operational outcomes, safe authorization, recoverable and
idempotent execution, usable traces, demonstrated value after residual human work and operating
cost, and explicit owner approval. Thresholds belong to the real risk owners and pilot evidence;
this plan does not invent them.

### Authority boundary

- Policy may approve a refund.
- Authorization determines whether the system may execute it.
- An approved **$150 refund** with **$100 autonomous authority** goes to human review; execution
  does not begin.

## What happens when something goes wrong?

Autonomous execution can be disabled independently while intake, recommendations, human review,
and the established manual workflow continue. Missing or contradictory evidence causes a safe stop,
not a guess. Authorization anomalies freeze the affected authority envelope. Execution errors or
unknown results preserve the disposition and case state, reconcile by operation identity, and route
to review without marking the case closed. Serious defects can move a slice back to reviewed or
shadow operation; re-entry requires evidence that the defect is repaired.

### What we monitor

| Category | Highest-level signals |
| --- | --- |
| Technical | Model/dependency failures; latency and cost; state/execution failures; retries and duplicates. |
| Workflow | Coverage; path mix; overrides; review, fallback, and clarification rates; unresolved and repeated cases. |
| Business/customer | Released support capacity; unnecessary compensation; cost per case; resolution and customer outcomes reported separately. |

## What production still needs

The lab prototype does **not** yet include:

- durable persistence, checkpointing, and restart recovery;
- real retailer, support, carrier, order, and execution integrations;
- enterprise service identity, secrets management, and PII controls;
- production observability and alerting; or
- formal operating ownership, incident response, and on-call processes.

These are described production requirements, not implemented capabilities.

## Appendix — Production readiness details

### Workflow and business discovery

Observe the actual DNR workflow rather than treating the lab's synthetic 11-step hypothesis as
fact. Establish eligible volume and variation; active handling and review time; compensation amounts
and outcomes; policies, exceptions, and risk tolerance; actors, decision owners, and escalation
paths; current support tooling and workarounds; order, shipment, carrier, and customer systems; each
source of truth; and actual refund/replacement authority limits. Define a fair customer outcome
alongside what the business can safely automate.

Replace the ROI model's synthetic inputs with approved, aggregated measurements. Released capacity
is not cash savings unless the business can show how it is used. Track CSAT, resolution time,
repeat contacts, retention, and consistency separately rather than forcing them into a monetary
claim.

### Integration and schema readiness

Map schemas and stable identifiers across customer, order, shipment, ticket, and carrier records.
Test linkage for split shipments, guest orders, corrected identifiers, and conflicting records.
Confirm API contracts, rate limits, dependency SLAs, sandbox/test environments, and behavior for
missing, stale, partial, or contradictory evidence. Consequential APIs must accept a stable
operation identity or equivalent deduplication control; otherwise they are not eligible for
autonomous retries or execution.

### Security and authorization requirements

Production requires a dedicated service identity, least-privilege credentials, managed secrets,
tenant/customer isolation where applicable, approved PII handling and retention, and an auditable
link from every action to the case, actor, policy version, and authority decision. Refund and
replacement envelopes must be explicit by action, amount, currency, and approving owner. This is a
deployment control, not a proposal for a generic IAM framework.

### Persistence and recovery semantics

The lab's explicit case fields and append-only traces are in-process. Production requires durable
case persistence and checkpointing so work survives restarts, retries resume from a known state,
prior evidence and decisions are retained, and operators can inspect and recover a case. Execution
attempts must durably retain `operation_id`, stable idempotency key, attempt result, and external
reference. A restart must never turn `not_started`, `in_progress`, or an unknown external result
into assumed success, nor repeat a known successful effect.

Discovery/readiness ends only with named workflow and policy owners; approved data/security
handling; validated sources of truth and contracts; a recoverable state design; safe, idempotent
consequential APIs; representative historical cases; and agreed success, stop, escalation, and
incident criteria. Otherwise, remain in discovery.

### Shadow-mode metrics and disagreement analysis

Run real eligible cases with autonomous consequential actions disabled. The system may ingest
messages, propose structured extraction, retrieve and link evidence, compute proposed policy and
disposition, propose an authorization result, and emit a trace. Humans continue to own the real
case and execute every action in existing tools.

Compare proposals with human decisions and later outcomes, not merely an initial label. Measure:

- extraction validity and semantic correctness;
- customer/order/shipment/evidence linkage;
- policy and disposition agreement, including false positives and false negatives;
- trajectory invariants, latency, cost, dependency failures, coverage, path mix, and reasons cases
  cannot proceed; and
- disagreements and safe stops by failure layer: input/task, retrieval/context, model
  interpretation, dependency, state/orchestration, policy/authorization, execution, or evaluator.

Sanitize reproducible failures and add the smallest useful regression case. Reviewed operation
requires representative coverage of the pilot slice, stable and explainable extraction/linkage,
no unresolved high-severity trajectory or authorization defect, acceptable dependency and safe-stop
behavior, reconstructable traces, and owner agreement. Aggregate accuracy or elapsed time alone is
insufficient.

### Reviewed-pilot adoption and change management

Put the recommendation into the actual support workflow while approval remains mandatory for
consequential actions. Preserve four paths:

| Path | Meaning during the pilot |
| --- | --- |
| Straight-through candidate | Complete evidence and a proposed permitted resolution, still confirmed by a human before execution. |
| Human review | Ambiguity, risk, policy exception, authorization block, or technical execution failure needs judgment. |
| Clarification/customer action | Required information is missing, or the customer must check, wait, or correct an identifier. |
| Operational fallback | Provider, dependency, validation, budget, or workflow failure returns the case safely to the established manual path. |

Measure reviewer agreement and override reasons, review time, clarification and fallback rates,
execution success, duplicate-action prevention, released capacity, unnecessary compensation,
incidents, and cost per eligible and adopted case. Report CSAT, resolution time, and repeat contacts
as separate non-monetized outcomes.

Train frontline staff and reviewers on what the system proposes, what it does not decide, and how
to stop or escalate it. Surface evidence and policy/authority rationale, capture structured override
reasons without discouraging overrides, and inspect workarounds, bypasses, and rework. Easy
escalation and visible uncertainty are adoption controls.

### Autonomy gates

A candidate slice needs:

- sustained reviewer evidence and high evaluation performance relevant to that exact slice;
- no unresolved high-severity trajectory failure and reliable evidence linkage;
- a satisfied authorization envelope;
- confirmed idempotent execution, duplicate suppression, and restart recovery;
- acceptable review, clarification, fallback, incident, customer, and operational error behavior;
- demonstrated value after residual human work and operating cost; and
- explicit approval from policy, support, risk, security, and operational owners.

Preserve the sequence **policy → disposition → authorization → execution**. Failed execution keeps
the disposition, routes to review, and cannot close the case.

### Controlled expansion

Expand one meaningful dimension where possible: case type, compensation amount, evidence quality,
customer segment, carrier, geography, or integration reliability. Do not enable the agent for
everyone at once. Every expansion must:

1. add or refresh representative evaluation cases;
2. pass the relevant regression suite;
3. confirm end-to-end observability and operator ownership;
4. define a specific rollback condition;
5. compare technical, workflow, customer, and business results with the prior slice; and
6. preserve human review and operational fallback.

Pause or reverse expansion when the new slice differs enough to invalidate the evidence that
justified the prior one.

### Production evaluation and regression gates

Use existing lab evidence as the seed, not the production acceptance bar. Component/offline
evaluations explain why a layer failed; shadow and pilot evaluation show whether the workflow works
in practice.

| Layer | Production evidence |
| --- | --- |
| Extraction | Schema validity, grounding, exact/contract-semantic field grading, representative historical cases, and meaning-preserving wording, fact-order, irrelevant-detail, and verbosity variations. |
| Workflow | Outcome and trajectory correctness measured separately; deterministic ordering of linkage, evidence, policy, disposition, authorization, and execution; failed execution never closes a case. |
| Safety controls | Authorization boundaries across currencies and amounts; execution identity and duplicate suppression; bounded calls, retries, latency, and cost; safe stops and recovery. |
| Failure behavior | Injected timeouts, rate limits, unavailable dependencies, malformed responses, and execution failures; attribution to the responsible layer, including brittle evaluators. |

A production regression blocks the affected release or expansion until repaired and represented by
a sanitized deterministic test or evaluation case. Outcome metrics cannot waive a trajectory or
authorization failure.

### Monitoring and observability

Production monitoring must support action, not just reporting. Each case needs a durable,
access-controlled reconstruction of:

`input → evidence → policy → disposition → authorization → execution`

Include versions, actor or service identity, state before/after, retries, costs, human override,
and external operation reference. Retention and trace content must follow approved PII rules; raw
customer data must not be copied into this repository. Operational drill-down should include
malformed responses, unknown execution outcomes, case aging by state, override reasons, realized
capacity, and cost per eligible and adopted case beneath the main document's monitoring categories.

### Rollback and incident behavior

| Signal | Immediate behavior |
| --- | --- |
| Model/extraction degradation | Disable autonomous progression; stop at validated structure or manual intake/review. |
| Carrier/evidence dependency degradation | Safe-stop or use operational fallback; do not infer missing evidence. |
| Authorization anomaly | Disable autonomous execution for the affected envelope; preserve recommendations for review. |
| Execution API errors or unknown result | Preserve disposition and state, reconcile by operation identity, route to human review, and do not mark closed. |
| Regression-gate failure | Block the release or expansion; keep the last proven scope. |
| Duplicate-action concern | Freeze the affected execution path while preserving case history and review capability. |

Incident handling must name an owner, affected slice, customer-remediation path,
evidence-preservation rule, and re-enable gate. Autonomous execution must remain independently
disableable without taking down intake, recommendation, or the human workflow.

### Production capability boundary

The repository currently proves a modular, deterministic DNR workflow around bounded extraction:
explicit case, disposition, execution, and follow-up state; append-only in-process traces; synthetic
adapters; refund-specific authority checks; idempotency behavior; bounded retries and budgets;
failure injection; layered evaluation; and a synthetic ROI assumption register.

Production additionally requires the capabilities summarized in the main document. A reliable
queue or workflow runtime may also be warranted if measured load demonstrates the need. Kubernetes,
a new orchestration framework, dashboards, generic IAM, or production integrations would not by
themselves make the lab evidence more truthful; implementation should follow measured need.

### Reusable deployment patterns

What judgment from this project has earned the right to become reusable infrastructure?

Reusable **patterns and playbooks now**:

- policy → disposition → authorization → execution;
- explicit state plus an append-only trace;
- outcome versus trajectory evaluation;
- deterministic invariants;
- failure attribution;
- safe-stop and idempotency patterns;
- shadow → reviewed → autonomy rollout gates; and
- the ROI evidence boundary and assumption register.

Reusable **code only after another project proves genuine cross-domain reuse** with compatible
semantics. Refund limits, DNR states, carrier evidence, and retailer policy remain domain-specific.
The sequence remains: **real problem → minimal implementation → inspect/break → extract an
abstraction only after evidence of reuse.**
