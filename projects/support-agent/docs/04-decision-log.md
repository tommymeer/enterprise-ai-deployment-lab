# Decision Log

**Active project record**

This log captures the decisions that materially changed the system: architecture, trust boundaries, evaluation design, execution safety, deployment evidence, and demo structure.

It is not a changelog. Small implementation choices are omitted unless they changed what the system could safely claim or do.

## Key decisions at a glance

| Date | Decision | Why it mattered |
| --- | --- | --- |
| 2026-08-31 | Use a fixed keyed retailer dataset for the live demo | Preserved the boundary between model interpretation and deterministic retailer retrieval; unknown IDs can fail truthfully instead of being fabricated into success. |
| 2026-08-31 | Organize the demo around one execution trace | Reduced UI repetition and made the customer outcome, system decisions, and evidence path legible in one view. |
| 2026-08-21 | Add bounded semantic-robustness evaluation | Tested whether extraction follows meaning rather than wording; exposed evaluator brittleness without requiring prompt or model changes. |
| 2026-08-21 | Calibrate synthetic economics without false precision | Kept public benchmarks as plausibility checks rather than turning them into fake customer evidence. |
| 2026-08-17 | Separate refund authorization from policy and execution | Made “correct decision” distinct from “system is allowed to act.” |
| 2026-08-17 | Start deployment arithmetic with transparent assumptions | Made ROI uncertainty inspectable and replaceable with real customer evidence later. |
| 2026-08-15 | Separate final-outcome checks from trace checks | Established that a correct final state is insufficient if the workflow took an unsafe path. |
| 2026-08-15 | Request customer correction when order lookup fails | Turned safe stopping into a recoverable workflow without pretending extraction failed. |
| 2026-08-10 | Keep extraction intake routing outside the support-case lifecycle | Prevented invalid or incomplete model output from entering the trusted workflow state machine. |
| 2026-08-06 | Stabilize the bounded extraction contract | Tightened the prompt, parser, model settings, and validation loop without loosening the trust boundary. |

## 2026-08-31 — Use a fixed keyed retailer dataset for the live demo

**Decision**

Add four explicit synthetic ecommerce orders keyed by customer-facing order ID. The validated extracted identifier is passed to a deterministic order adapter. Matched records retrieve their own shipment and carrier evidence; unknown IDs return `not_found`.

**Why**

The live extraction path accepted arbitrary wording, but downstream data still represented one successful order. Dynamically fabricating a matching record would blur the line between model interpretation and retailer retrieval.

**Alternatives**

- Add a database
- Generate retailer records from the input
- Expand the scenario framework
- Add new policy branches solely to create demo variety

**Reasoning**

A small immutable in-memory dataset demonstrates real identifier-driven retrieval without adding another dependency. It also makes unsupported order IDs fail truthfully.

**Status:** Accepted

## 2026-08-31 — Organize the interview demo around one execution trace

**Decision**

Replace the inspector-style collection of pipeline, timeline, case-detail, implementation-map, score-tile, and raw-trace surfaces with:

1. customer message
2. deterministic customer-facing outcome
3. one readable execution trace

Tool call/return events are paired by tool name and retain the recorded evidence behind each row. Live Claude extraction remains behind an explicit server flag with no fallback.

**Why**

The earlier demo exposed the same workflow evidence repeatedly and made the customer journey harder to explain.

**Reasoning**

A deterministic view-model projection exposes the real trace without changing system behavior or inventing reasoning. The resulting UI is easier to demonstrate and still grounded in the underlying execution record.

**Status:** Accepted

## 2026-08-21 — Add bounded semantic-robustness extraction evaluation

**Decision**

For five frozen canonical extraction cases, derive four meaning-preserving variants each:

- paraphrased wording
- reordered facts
- irrelevant detail
- materially different verbosity

Grade each result against the same structured facts.

For failures, record the likely responsible layer and supporting evidence, then confirm or revise that attribution through inspection.

**Observed result**

The authorized live run produced:

- **20/20 structurally valid outputs**
- **17/20 initial semantic matches**
- all eight non-reason fields matched in every case

The three apparent failures were caused by an overly narrow evaluator vocabulary for `clarification_reason`, not by extraction semantics. After a narrow grader repair, retained outputs rescored **20/20**.

No production-model or workflow change was required.

**Why it mattered**

The experiment tested whether extraction follows meaning rather than superficial wording and showed why evaluator failures must be distinguished from model failures.

**Status:** Accepted; live validation and retained-output rescoring complete

## 2026-08-21 — Calibrate synthetic economics without creating false precision

**Decision**

Use public benchmarks only to test whether synthetic assumptions are directionally plausible. Do not use them as substitutes for customer discovery or pilot measurements.

Keep unsupported DNR-specific inputs explicitly synthetic, round hiring-manager-facing outputs, and retain exact arithmetic only for auditability.

**Why**

No public source maps cleanly to this workflow. Wage data does not prove loaded support cost; response time does not prove active handling time; returns fraud does not prove DNR unnecessary-compensation rates.

**Status:** Accepted

## 2026-08-19 — Bound frontier-review follow-up to evidenced needs

**Decision**

Prioritize one small semantic-robustness evaluation and lightweight failure attribution before adding more infrastructure.

Do **not** build a deterministic fast lane, generic failure-classification framework, evaluation platform, or additional orchestration abstraction without evidence that the current system needs them.

**Why**

The existing design already keeps routing, policy, authorization, and execution deterministic and includes retries, idempotency, failure injection, and safe stops. The next useful question was whether the bounded extraction layer remained stable under meaning-preserving variation.

**Status:** Accepted

## 2026-08-17 — Separate refund authorization from policy and execution

**Decision**

After policy selects `approve_refund`, compare the refund amount and currency with the configured autonomous authority before creating an execution operation.

Example:

```text
refund amount = $150
autonomous limit = $100
```

results in:

```text
disposition = approve_refund
case_status = human_review
execution_status = not_started
```

**Why**

The prior workflow treated an executable disposition as sufficient authority to act. That collapsed three separate questions:

1. What is the correct outcome?
2. Is the system authorized to act?
3. Did execution succeed?

Authority denial happens before execution and therefore should not be represented as execution failure.

**Implementation choice**

Money is compared in integer minor units with explicit currency to avoid floating-point and cross-currency mistakes.

**Alternatives**

- Treat authority denial as execution failure
- Parse free-form order value
- Introduce a generic role/grant/permission framework

**Status:** Accepted

## 2026-08-17 — Start deployment arithmetic with transparent assumptions

**Decision**

Build the first ROI model from explicit low/base/high assumptions rather than external averages.

Separate:

- retailer baseline
- workflow coverage
- path mix
- residual human effort
- compensation outcomes
- implementation cost
- operating cost

**Why**

The project had bounded technical evidence but no observed customer workload, labor economics, compensation loss, adoption, or realized capacity value.

A transparent assumptions register makes uncertainty visible and lets each input later be replaced with authorized customer evidence.

**Status:** Accepted

## 2026-08-15 — Establish the untouched hard-extraction baseline

**Decision**

Run the six frozen hard extraction cases once through the existing live Claude extraction path with no retries or tuning.

**Observed result**

- **6/6 valid outputs**
- **6/6 semantic matches**
- **6/6 matches across all nine fields**
- no provider or validation failures

The raw result was retained locally rather than committed.

**Boundary**

Six synthetic hard cases plus the earlier ten-case baseline do not establish production robustness.

**Status:** Accepted

## 2026-08-15 — Add representable extraction failure-discovery cases

**Decision**

Add six offline hard cases covering:

- stale quoted order IDs
- order/tracking role confusion
- explicitly corrected order IDs
- dense unrelated numbers
- identifier words without actual identifiers
- unsupported address-correctness inference

Each case includes one correct scripted output and one schema-valid semantic mistake.

**Reasoning**

The cases expose representable blind spots without changing the nine-field contract or expanding into conversational conflict semantics the contract cannot honestly represent.

**Status:** Accepted

## 2026-08-15 — Grade clarification reasons by contract semantics

**Decision**

Keep exact equality for eight fields, but evaluate `clarification_reason` against the narrow meaning required by the contract instead of exact sentence wording.

A valid clarification reason must state that the order identifier is missing, required, absent, needed, or not provided.

**Why**

The first live baseline produced **10/10 valid outputs** and **9/10 exact semantic matches**. The sole mismatch was:

```text
Expected: Order identifier was not provided.
Actual:   The order identifier is required to locate the order but was not provided in the message.
```

That exposed evaluator brittleness rather than a meaningful extraction failure.

**Alternatives**

- Tune the prompt
- Keep exact wording
- Use fuzzy matching
- Use embeddings
- Add an LLM judge

**Status:** Accepted

## 2026-08-15 — Evaluate extraction separately with exact field comparisons

**Decision**

Evaluate extraction independently from workflow behavior using ten hand-curated synthetic messages, manually expected nine-field outputs, scripted model responses, and per-field grading.

**Why**

A model output can be structurally valid while assigning the wrong identifier, label, or customer claim. Workflow tests downstream cannot diagnose that boundary cleanly.

**Status:** Accepted

## 2026-08-15 — Separate final-outcome checks from concrete trace checks

**Decision**

Evaluate the final outcome and the execution trajectory separately.

Initial trace invariants included:

1. successful linkage precedes downstream work
2. evidence gathering precedes policy
3. policy routing precedes disposition
4. disposition precedes execution
5. failed execution does not close a case

**Experiment**

Moving `execution_started` before `disposition_selected` preserved the same final refunded state.

The outcome check still passed.

The trajectory check failed.

**Why it mattered**

A correct final state does not prove the system reached it safely.

**Status:** Accepted

## 2026-08-17 — Evaluate refund authorization as a trajectory invariant

**Decision**

Extend trajectory evaluation so that once the workflow records `execution_authority_blocked`, later refund-execution evidence is invalid.

**Why**

A closed and successfully refunded case can look correct at the outcome layer even if the system exceeded its configured authority.

**Status:** Accepted

## 2026-08-15 — Request customer correction when a supplied order identifier is not found

**Decision**

When deterministic order retrieval returns `not_found`, route the case to `awaiting_customer_action` and ask the customer to verify or correct the identifier.

Do not:

- pretend extraction omitted the identifier
- attach an untrusted order
- continue to evidence gathering or policy
- make the failure terminal when recovery is possible

A corrected identifier reruns order lookup and can resume the workflow.

**Why**

The observed failure was in deterministic linkage, not model extraction. Recovery should preserve that distinction.

**Status:** Accepted

## 2026-08-10 — Keep extraction intake routing outside the support-case lifecycle

**Decision**

Add a deterministic intake router with four outcomes:

```text
manual_intake_review_required
clarification_required
delivered_not_received_workflow
general_triage_required
```

Only a validated and complete extraction classified as delivered-not-received can enter the trusted support workflow.

**Why**

Invalid, incomplete, or unsupported model output is not the same thing as a support case that has already entered the workflow and later needs human review.

Keeping safe-stop intake outcomes outside `SupportCase` protects the semantics of the workflow state machine.

**Status:** Accepted

## 2026-08-06 — Stabilize the bounded extraction contract

The first live extraction work produced a useful sequence of failures. Rather than loosening validation, each repair targeted the smallest evidenced boundary.

### Step 1 — Bound live validation

Use one manual Anthropic runner with:

- three fixed synthetic cases
- sequential execution
- no retries
- explicit authorization
- a $0.10 spend ceiling

**Reason:** collect initial live evidence without making routine tests paid or network-dependent.

### Step 2 — Instrument rejected responses safely

Add provider-neutral finish metadata and response-shape diagnostics without logging raw customer content.

**Observed failure:** 3/3 provider calls were rejected at JSON parsing; two reached the 256-token cap.

**Reason:** diagnose before modifying the parser or prompt.

### Step 3 — Normalize one complete JSON fence

Accept either raw JSON or exactly one complete whole-response Markdown fence. Keep all schema, grounding, and clarification validation unchanged.

Raise only the manual runner output cap from 256 to 512 tokens.

**Reason:** address observed fenced responses without accepting arbitrary prose or repairing malformed JSON.

### Step 4 — Enumerate the nine-field contract in the prompt

The next run produced 3/3 normal JSON responses but all failed exact schema-key validation.

The prompt referenced a private schema without enumerating the actual required keys.

Prompt v3 therefore explicitly listed:

- all nine required fields
- allowed types
- identifier-grounding rules
- clarification consistency rules

**Reason:** fix missing information at the model boundary rather than weakening validation.

### Step 5 — Disable adaptive thinking for bounded extraction

One later run ended at `max_tokens` because adaptive thinking consumed part of the bounded output budget.

Thinking was disabled only for this isolated extraction adapter.

**Reason:** this task requires short structured extraction, not extended reasoning.

### Step 6 — Clarify `unknown` issue semantics

The remaining live failure combined:

```text
issue_type = unknown
needs_clarification = true
missing_required_fields = []
```

The schema intentionally defined clarification only around a missing order identifier.

The prompt was tightened so that `issue_type = unknown` alone does not require clarification.

### Final bounded result

The final three-case validation produced:

- **3/3 intended outcomes**
- valid raw JSON
- strict schema validation
- normal `end_turn`
- thinking disabled
- no validation failures

This evidence applies only to the three synthetic cases.

**Status:** Accepted; bounded extraction-validation repair loop closed

## Decision principles that emerged

Across the project, several recurring rules became explicit:

- **Do not loosen a trust boundary before diagnosing the failure.**
- **Fix the smallest layer supported by the evidence.**
- **Do not confuse evaluator failure with model failure.**
- **Do not confuse a correct outcome with a safe trajectory.**
- **Do not confuse policy approval with execution authority.**
- **Do not fabricate downstream evidence to make a demo succeed.**
- **Keep paid/live evaluation bounded and intentional.**
- **Do not build reusable infrastructure before repeated evidence justifies it.**
- **Treat synthetic economics as a decision hypothesis, not realized ROI.**
