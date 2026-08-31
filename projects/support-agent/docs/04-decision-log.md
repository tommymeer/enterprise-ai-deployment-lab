# Decision Log

**Status: In progress**

**Execution status:** The bounded extraction-validation increment is complete. The latest
three-case live validation passed all cases end to end with thinking disabled, valid raw JSON, and
successful strict validation; this evidence is limited to the three synthetic cases.

## Purpose

Record significant decisions made during this project, along with the reasoning and alternatives
considered, so the "why" behind the system is legible later — to the author or to anyone else
reading it. Not every small choice needs an entry; scope, architecture, and tradeoff decisions do.

## Template

Add one entry per decision, most recent first.

### YYYY-MM-DD — Decision title
- **Decision:** What was decided.
- **Context:** Why this decision was needed now.
- **Alternatives considered:** What else was on the table.
- **Reasoning:** Why this option was chosen over the alternatives.
- **Status:** Proposed / Accepted / Superseded (by which later entry, if applicable).

---

### 2026-08-31 — Use a fixed keyed retailer dataset for the live demo

- **Decision:** Add four explicit synthetic ecommerce orders keyed by customer-facing order ID.
  The validated extracted ID is passed to a deterministic order adapter; matched records lead to
  their own shipment and carrier evidence, while unknown IDs return a real `not_found` result.
  Reuse the existing missing-evidence and refund-authority behavior for variation.
- **Context:** The live extraction path accepted arbitrary wording, but downstream data still
  represented one successful order. Dynamically fabricating a matching record would obscure the
  boundary between model interpretation and retailer retrieval.
- **Alternatives considered:** Add a database, generate records from input, expand the scenario
  framework, or introduce new policy branches solely for demo variety.
- **Reasoning:** A small immutable in-memory map is enough to demonstrate real identifier-driven
  retrieval and truthful unknown-ID handling. Enriching the existing tool return payloads exposes
  order-specific evidence without adding another trace layer or external dependency.
- **Status:** Accepted.

### 2026-08-31 — Organize the interview demo around one execution trace

- **Decision:** Replace the inspector-style pipeline, timeline, case-detail, implementation-map,
  score-tile, and raw-trace surfaces with a customer-message input, deterministic customer-facing
  outcome, and one readable execution-trace view model. Pair the existing tool call/return events
  by their recorded tool name, retain their raw evidence per row, keep scripted input locked, and
  allow live Claude extraction only behind an explicit server flag with no fallback.
- **Context:** The technically complete demo repeated the same workflow evidence across several
  dashboard sections and made the customer journey harder to explain. The workflow already records
  the inputs, normalized results, state, retries, latency, authority, and operation identity needed
  by a single trace. The synthetic lookup fixture also has a bounded supported order and must not
  imply arbitrary retailer coverage.
- **Alternatives considered:** Keep the existing surfaces and restyle them; add a frontend
  framework; generate customer copy with another model call; or make arbitrary synthetic orders
  succeed dynamically.
- **Reasoning:** A deterministic view-model projection is the smallest change that exposes real
  evidence without changing downstream behavior or inventing reasoning. Customer copy is derived
  from disposition, execution status, and final state. Unsupported extracted IDs become a recorded
  synthetic `not_found` result. The live path reuses the existing 512-token, 30-second Anthropic
  adapter configuration and stops on provider errors before routing.
- **Status:** Accepted.

### 2026-08-21 — Add a bounded semantic-robustness extraction evaluation

- **Decision:** Derive exactly four meaning-preserving variants from each of five frozen canonical
  extraction cases: paraphrased wording, reordered facts, an irrelevant detail, and materially
  different verbosity. Grade every variant with the existing nine-field comparator, changing only
  the expected `original_message`. For a failed result, emit a preliminary primary layer,
  supporting evidence, and likely remedy alongside the retained raw output; confirm or revise that
  attribution during human inspection. The authorized live run produced 20/20 structurally valid
  outputs and 17/20 initial semantic matches. All eight other fields matched in every case; the
  three apparent failures differed only because valid reasons using “needed” fell outside the
  comparator's accepted “missing,” “required,” or “not provided” vocabulary. Extend only that
  predicate to accept non-negated “needed” (and the contract-equivalent “absent”), leaving the
  other eight fields exact.
- **Context:** The canonical and hard extraction sets test selected meanings, but not whether
  equivalent meanings remain stable under controlled surface-form changes.
- **Alternatives considered:** A larger dataset, fuzzy scoring, an LLM judge, a generic taxonomy
  framework, persistent analytics, or changing the extraction prompt before observing failures.
- **Reasoning:** The 20 derived cases isolate four surface-form transformations while preserving
  the frozen structured facts. Exact structured-field grading keeps regressions visible. The small
  attribution record is enough to distinguish a likely model-interpretation failure from an
  ambiguous input or brittle grader during review without adding infrastructure. Inspection and
  retained-output rescoring confirmed 20/20 semantic matches after the narrow evaluator repair;
  the three preliminary automated “model interpretation” attributions are therefore finally
  attributed to `evaluation/grader`. No production-model or workflow change was required. The live
  run used 16,783 input tokens, 2,814 output tokens, 45,980.37 ms total provider latency, and an
  estimated $0.092559, with no provider or validation failures.
- **Status:** Accepted; live validation and retained-output rescoring complete.

### 2026-08-21 — Calibrate synthetic economics without creating false precision

- **Decision:** Use relevant public benchmarks only to calibrate the direction and order of
  magnitude of synthetic business assumptions, not as substitutes for customer discovery or pilot
  data. Keep unsupported DNR-specific inputs explicitly synthetic, round hiring-manager-facing ROI
  outputs, and retain exact arithmetic in the methodology for auditability.
- **Context:** The synthetic deployment model now has illustrative inputs and outputs that benefit
  from external plausibility checks, while no public source maps cleanly to the modeled DNR workflow.
- **Alternatives considered:** Present exact modeled outputs as forecasts, adopt generic benchmarks
  as DNR evidence, or omit all external calibration.
- **Reasoning:** Calibration can expose implausible orders of magnitude, but it cannot turn wages
  into loaded costs, response time into active handling time, or returns fraud into DNR unnecessary
  compensation. Rounded headline results communicate input uncertainty while exact underlying math
  remains reproducible.
- **Status:** Accepted.

### 2026-08-19 — Bound frontier-review follow-up to evidenced needs

- **Decision:** Before final portfolio packaging, add a bounded metamorphic extraction evaluation
  using five existing canonical cases and four meaning-preserving variants of each: paraphrasing,
  reordering, irrelevant detail, and changed verbosity. Expected structured facts must remain
  unchanged. For each genuine observed evaluation failure, record its primary layer, supporting
  evidence, and likely remedy, using: input/task specification, retrieval/context, model
  interpretation, tool selection/parameters, external dependency, state/orchestration,
  policy/authorization, execution, or evaluation/grader. Make no deterministic-fast-lane or
  infrastructure change now.
- **Context:** An Enterprise AI Frontier review raised semantic robustness, failure attribution,
  deterministic routing, and infrastructure robustness as portfolio-readiness concerns.
- **Alternatives considered:** Build a large new evaluation dataset, failure-classification
  framework or analytics layer, deterministic replacement path, or additional infrastructure
  abstraction; or make no bounded follow-up at all.
- **Reasoning:** The small metamorphic set tests whether extraction follows case meaning rather than
  superficial wording. Lightweight attribution improves diagnosis without new enums or machinery.
  The current design already confines bounded language interpretation to the LLM while routing,
  policy, authorization, and execution remain deterministic; a deterministic-vs-model
  microbenchmark is warranted later only for a concrete deployment question. Existing failure
  injection, retries, idempotency, safe stops, and adapter error handling cover most infrastructure
  concerns. Treat a partial dependency response as malformed when it violates the structured
  contract, and add infrastructure work only for a specifically observed uncovered failure mode.
- **Status:** Accepted.

### 2026-08-17 — Start deployment arithmetic with transparent assumptions

- **Decision:** Begin the ROI model with explicit low/base/high placeholders, separate target-state
  paths, and formulas tied to this project's evidence boundary. Do not populate business inputs from
  external benchmarks unless their relevance and provenance are later established.
- **Context:** The project has bounded technical cost and evaluation evidence but no observed
  retailer workflow, workload, labor, compensation-loss, carrier-recovery, or adoption data.
- **Alternatives considered:** Search for retailer or industry benchmarks now, present a single
  point estimate, or defer deployment arithmetic until production data exists.
- **Reasoning:** External averages could create false precision and hide the variables a real
  discovery or pilot must measure. A transparent assumptions register makes uncertainty inspectable,
  supports low/base/high sensitivity analysis, and can be replaced incrementally with authorized
  business evidence without presenting synthetic values as facts.
- **Status:** Accepted.

### 2026-08-17 — Separate refund authorization from policy and execution

- **Decision:** After policy selects `approve_refund`, compare the proposed refund amount with the
  configured autonomous refund limit before creating an execution operation. A refund of 15,000
  USD minor units against a 10,000 USD-minor-unit limit routes to `human_review` with disposition
  unchanged and execution still `not_started`; equal or lower amounts may follow the existing
  execution path. Currency mismatch also routes to review.
- **Context:** The workflow previously treated an executable disposition as sufficient authority
  to invoke execution, so policy approval, authorization, and execution were not distinct controls.
- **Alternatives considered:** Treat authority denial as execution failure, parse `order_value`, or
  introduce a generic permission framework with roles and grants.
- **Reasoning:** Authority denial occurs before an execution attempt and therefore is not execution
  failure. Integer minor units avoid floating-point money comparisons, and explicit currencies
  prevent unlike currencies from being compared. Refund-specific configuration and one narrow
  domain transition answer the observed $150/$100 failure without speculative permission concepts.
- **Status:** Accepted.

### 2026-08-15 — Establish the untouched live hard-extraction baseline

- **Decision:** Run each of the six frozen hard extraction cases once through the existing Claude
  production extraction path and current field grader, with no retries or tuning, and retain the
  raw JSONL locally for later inspection rather than commit it.
- **Context:** The earlier ten-case live baseline covered the initial extraction set but had not
  measured the model on the newer cases for stale and corrected identifiers, identifier roles
  among dense numbers, missing identifiers, and unsupported address inference. The hard-case run
  produced 6/6 valid outputs, 6/6 semantic matches, and 6/6 matches on all nine fields. All six
  calls ended with `end_turn`; there were no provider or validation failures. Total usage was
  5,138 input and 953 output tokens, total provider latency was 11,741.985 ms, and estimated cost
  was $0.029709.
- **Alternatives considered:** Rely only on scripted hard-case checks, broaden or tune the cases,
  rerun failures, or defer raw-result retention.
- **Reasoning:** This extends the earlier ten-case live baseline with untouched evidence on the
  frozen hard cases. No genuine model semantic failure has yet been observed in the current
  bounded extraction task, but sixteen small synthetic cases do not establish production quality
  or broad robustness. The complete raw result remains locally at
  `var/live-evals/claude-sonnet-5-hard-extraction-baseline.jsonl`, which is ignored and is not
  intended to be committed.
- **Status:** Accepted.

### 2026-08-15 — Add representable extraction failure-discovery cases

- **Decision:** Add six offline, manually specified hard cases covering stale quoted order IDs,
  order/tracking role confusion and punctuation, an explicitly corrected order ID, dense unrelated
  numbers, identifier words without supplied identifiers, and unsupported address-correctness
  inference. Exercise each with one exact scripted output and one schema-valid semantic mistake.
- **Context:** The initial ten cases covered basic classification, missing fields, simple numeric
  distractors, and address-claim restraint, but not dense role resolution, quotation staleness, or
  correction within one message. Proposed messages containing unresolved conflicting
  package-missing claims or unresolved conflicting address-correctness claims were rejected: each
  contract field is one nullable Boolean and cannot honestly preserve both claims or their order.
- **Alternatives considered:** Force conflicts to `null`, add conflict fields or conversational
  semantics, tune the extraction prompt, or make a live provider call.
- **Reasoning:** Six cases are enough to expose the identified representable blind spots without
  changing the nine-field contract. The unchanged validator accepts all scripted semantic mistakes,
  and the existing field grader rejects each on the intended fields. No validator or grader
  limitation was newly exposed; no prompt tuning, network access, or live model call occurred.
- **Status:** Accepted.

### 2026-08-15 — Grade clarification reasons by the contract's narrow semantics

- **Decision:** Preserve the first ten-case live baseline unchanged, then replace exact sentence
  equality only for `clarification_reason` with a deterministic contract-level check. When
  clarification is not needed, the reason must be null. When it is needed because the order
  identifier is absent, the reason must be a non-empty string that names the order identifier and
  says it is missing, required, or not provided. Keep exact equality for the other eight fields.
- **Context:** The untouched first live baseline produced 10/10 valid outputs and 9/10 exact
  semantic matches under the original exact-field grader. Every structured field was 10/10. The
  only mismatch was the expected `Order identifier was not provided.` versus the actual `The order
  identifier is required to locate the order but was not provided in the message.` Total estimated
  cost was $0.044655, with no provider or validation failures.
- **Alternatives considered:** Change the extraction prompt or contract; retain exact wording;
  introduce fuzzy matching, embeddings, an LLM judge, generic semantic similarity, or weighted
  scoring.
- **Reasoning:** Both reason strings express the same narrow fact required by the current contract.
  The mismatch therefore exposed evaluator brittleness rather than an obvious
  extraction-understanding failure. A tiny explicit rule admits only the evidenced wording
  variance while keeping the rest of the evaluation exact and inspectable. The first live run
  exposed a result-retention limitation: stdout was not persisted, so the complete run could not
  later be re-graded after the rubric changed. The recorded actual reason is covered as a
  deterministic regression fixture; no additional live call was made. Persisting results is
  deferred to a later increment.
- **Status:** Accepted.

### 2026-08-15 — Evaluate extraction separately with exact field comparisons

- **Decision:** Start extraction evaluation with ten hand-curated synthetic messages, manually
  expected nine-field outputs, scripted model responses, and exact per-field comparison.
- **Context:** Workflow trajectory evaluation checks deterministic state and event ordering after
  intake. Extraction is a separate probabilistic boundary: it must first produce a valid proposal,
  and a valid proposal can still assign the wrong supported label, identifier, or customer claim.
  Keeping those layers separate makes schema/validation failures distinct from schema-valid
  semantic failures.
- **Alternatives considered:** Reuse trajectory evaluation, introduce an evaluation platform or
  registry, use fuzzy or weighted scores, or ask another model to judge outputs.
- **Reasoning:** A small inspectable set and exact equality expose the mechanics and concrete
  failures without obscuring them behind abstractions. No platform, semantic similarity, or LLM
  judge is justified by this first increment, and this is not a production-quality model
  evaluation claim.
- **Status:** Accepted.

### 2026-08-15 — Separate final-outcome checks from concrete trace checks

- **Context:** The first evaluation increment inspected four existing offline runs: successful
  refund, carrier-evidence retrieval failure, refund execution failure, and unmatched order ID
  followed by customer correction and successful resume. A correct final state alone could not
  show whether the workflow reached it safely.
- **Decision:** Keep scenario-specific outcome checks separate from five trace invariants observed
  in those runs: successful linkage precedes downstream work; evidence gathering precedes policy;
  policy routing precedes disposition; disposition precedes execution; and failed execution does
  not close a case. The correction path's `order_identifier_correction_recorded` event counts as
  successful linkage because that is how the existing workflow records relinking.
- **Experiment:** Moving only `execution_started` before `disposition_selected` in a copy of the
  successful refund event sequence preserved the closed, approved, successfully executed refund
  outcome. The outcome check passed while the trajectory check failed with the intended invariant.
- **Why no platform yet:** Two plain deterministic functions and one small offline script expose
  the mechanics without an eval framework, registry, dashboard, external dependency, or model
  judge. This is an initial learning increment, not a production-quality evaluation system.

### 2026-08-17 — Evaluate refund authorization as a trajectory invariant

- **Decision:** Keep policy selection, amount/currency authorization, consequential execution,
  and evaluation as separate concerns. Treat an authorization block that leaves an approved refund
  in `human_review` with execution `not_started` as a correct safe outcome. Extend the trajectory
  evaluator only to reject traces that contain refund execution evidence despite the workflow having
  recorded `execution_authority_blocked`.
- **Reasoning:** A closed, successfully refunded final state can look correct even when execution
  exceeded the configured autonomous authority. Outcome-only evaluation therefore cannot establish
  that the path was acceptable. The existing concrete authority event supplies deterministic trace
  evidence, so no roles, grants, scopes, generic policy model, or permission framework was added.
- **Status:** Accepted.

### 2026-08-15 — Request customer correction when a supplied order identifier is not found

- **Decision:** When deterministic order retrieval succeeds with `match_status = not_found`, move
  the case directly from `intake` to the existing `awaiting_customer_action` state and record that
  the customer must verify or provide a corrected order identifier. Preserve the customer report
  and supplied identifier, attach no order, and stop the workflow as incomplete.
- **Context:** A controlled offline linkage-failure experiment using `Order 99999` showed that
  extraction succeeded, delivered-not-received routing was correct, and order lookup validly
  returned no match, but the case entered terminal `intake_failed` without requesting a correction.
  This exposed a gap between safe stopping and operational recovery.
- **Alternatives considered:** Keep `intake_failed`; treat the result as missing extraction data;
  send the case to `human_review`; or introduce a generic recovery framework or new state.
- **Reasoning:** Extraction success means the customer supplied a syntactically valid, grounded
  identifier; linkage failure means the deterministic order source could not match that supplied
  value. They are distinct facts, so the repair must not pretend extraction omitted the identifier.
  `awaiting_customer_action` already coherently represents a case blocked on information from the
  customer. Until corrected linkage succeeds, there is no trusted order or shipment context, so
  evidence gathering, policy evaluation, disposition selection, and execution remain blocked.
  The initial repair exposed a missing resume path: the case paused correctly but could not legally
  relink after a correction. The completed repair preserves the matched customer reference, records
  each corrected identifier without replacing the original report, reruns only order lookup, and
  supports `not_found → customer correction → relink → resume`. A second not-found result remains
  blocked on customer action, while retrieval failure does not link or progress. Focused offline
  tests cover the repaired experiment and unchanged matched and failed-retrieval paths; no live
  validation is claimed.
- **Status:** Accepted.

### 2026-08-10 — Keep extraction intake routing outside the support-case lifecycle

- **Decision:** Add one deterministic intake router with four outcomes:
  `manual_intake_review_required`, `clarification_required`,
  `delivered_not_received_workflow`, and `general_triage_required`. Only a validated `complete`
  extraction classified as `delivered_not_received` may enter the existing support workflow. The
  router constructs its workflow input from validated message and order data plus a separate,
  trusted non-model context.
- **Context:** The validated extraction component was separate from a deterministic workflow whose
  input already assumed a supported issue and complete identifiers. A narrow boundary was needed to
  prevent invalid, incomplete, or unsupported extraction outcomes from reaching evidence, policy,
  disposition, or execution logic.
- **Alternatives considered:** Extend `SupportCase` with intake-classification states; reuse
  `CaseStatus.HUMAN_REVIEW` or `INTAKE_FAILED`; route clarification through the existing
  `REQUEST_MORE_INFO` disposition; or add a generalized routing framework.
- **Reasoning:** Pre-workflow manual review, clarification, and general triage are intake outcomes,
  not states reached after evidence or policy work. Reusing the existing case states would falsely
  imply that a trusted support case entered that lifecycle. In particular, invalid model output is
  not `INTAKE_FAILED`, which currently represents deterministic lookup or linkage failure. Keeping
  the three safe-stop outcomes outside `SupportCase` preserves its state and human-review
  invariants, while delegation on the one supported route preserves the existing evidence, policy,
  decision, execution, and follow-up behavior unchanged. Validation for this increment is entirely
  offline with scripted `ExtractionResult` values; no live integration-validation claim is made.
- **Status:** Accepted.

### 2026-08-06 — Close the bounded extraction-validation repair loop

- **Decision:** Accept the explicit unknown-issue prompt clarification as live-validated for the
  three bounded synthetic cases and close this extraction-validation increment without another
  live rerun.
- **Context:** The separately authorized three-case live validation completed all three calls with
  their intended controlled outcomes. The complete delivered-not-received case returned
  `complete`; the missing-order-identifier case returned `needs_clarification` with
  `order_identifier` as its only missing required field; and the ambiguous unknown-issue case
  returned `complete` with `issue_type: unknown`. All responses ended with `end_turn`, produced raw
  JSON, and passed strict validation with no validation reason. Thinking-disabled operation avoided
  the prior truncation. Aggregate usage was 2,533 input tokens and 456 output tokens, estimated
  cost was $0.014439, and per-call latency was approximately 2.54–3.42 seconds.
- **Alternatives considered:** Run another live validation now; broaden the case set; or leave the
  repair loop open despite the bounded cases passing.
- **Reasoning:** The evidence confirms the intended extraction distinction: missing required data
  triggers `needs_clarification`, while a present identifier paired with an unsupported or vague
  issue completes as `issue_type: unknown`. It also confirms that thinking-disabled operation,
  raw-JSON output, and strict validation worked together for these cases. This result validates
  only the three synthetic cases and does not establish broad production accuracy, robustness, or
  generalization. No further live rerun is justified at this checkpoint.
- **Status:** Accepted.

### 2026-08-06 — Clarify unknown-issue semantics within the existing extraction contract

- **Decision:** Keep prompt v3, the nine-field schema, and deterministic validation unchanged.
  Explicitly define `issue_type: unknown`, state that unknown alone does not require clarification,
  and state that this extraction contract uses clarification only when `order_identifier` is
  missing. Add focused prompt assertions and direct offline assertions for all three bounded cases,
  including complete extraction of the vague issue with its present order identifier.
- **Context:** Disabling adaptive thinking resolved the prior `max_tokens` truncation. The next
  bounded run attempted and completed three calls: one `complete`, one `needs_clarification`, and
  one `invalid_model_output`. The third response ended with `end_turn`, but combined
  `issue_type: unknown` and `needs_clarification: true` with empty `missing_required_fields`, which
  correctly failed clarification consistency. The run used 1,960 input tokens and 485 output
  tokens, cost an estimated $0.013155, and had per-call latency of approximately 2.25–5.80 seconds.
- **Alternatives considered:** Broaden clarification semantics, add a clarification category,
  change the synthetic case, or change its intended outcome.
- **Reasoning:** Diagnosis showed that the prompt left unknown-issue clarification ambiguous while
  the existing schema and validator intentionally limit clarification to a missing required order
  identifier. Prompt clarification plus stronger offline semantic assertions is the smallest repair
  that makes the model-facing instructions match the existing contract. No claim is made that the
  live case will pass until another separately authorized bounded run occurs.
- **Status:** Accepted.

### 2026-08-06 — Disable adaptive thinking for bounded Sonnet 5 extraction

- **Decision:** Configure only the isolated Anthropic adapter to support an immutable, validated
  `disable_thinking` option, defaulting to false, and enable it in the three-case extraction
  runner. Correct the runner-local Sonnet 5 pricing assumptions from $2/$10 to $3/$15 per million
  input/output tokens.
- **Context:** The latest three-call run passed 2/3 cases end to end. The complete and clarification
  routes succeeded with `end_turn`; the ambiguous route ended at `max_tokens` after 512 output
  tokens with truncated visible JSON. Sonnet 5 adaptive thinking was still enabled because the
  request supplied no thinking field. Aggregate usage was 1,960 input tokens and 923 output tokens,
  with latency approximately 3.43–5.98 seconds. The previously emitted $0.01315 estimate used the
  outdated local $2/$10 assumptions; at $3/$15, the corrected run cost is $0.019725.
- **Alternatives considered:** Increase the token cap; add retries or calls; change the prompt,
  parser, schema, or validator; or introduce a generic reasoning configuration.
- **Reasoning:** Explicitly disabling thinking preserves the 512-token visible-output budget for
  this bounded structured extraction workload while keeping provider settings out of neutral
  application contracts. Offline evidence does not yet show that disabling thinking resolves the
  third case, so no improvement claim is made.
- **Status:** Accepted.

### 2026-08-06 — Enumerate the nine-field extraction contract in prompt v3

- **Decision:** Change the versioned model-facing contract to
  `customer-report-extraction-v3` and explicitly enumerate all nine required field names, allowed
  types, identifier-grounding rules, and clarification consistency rules, with one placeholder-only
  JSON template. Keep deterministic validation unchanged.
- **Context:** The third bounded live run completed 3/3 Anthropic calls. All three responses were
  valid raw JSON, ended normally with `end_turn`, and stayed below the 512-token output limit, but
  3/3 failed exact schema-key validation because required keys were missing and unsupported keys
  were present. Aggregate usage was 793 input tokens and 456 output tokens, estimated cost was
  $0.006146, and per-call latency was approximately 1.98–5.10 seconds. The diagnosed cause was that
  the model-facing prompt named a private schema without enumerating its contract.
- **Alternatives considered:** Loosen exact schema validation; accept aliases; map unsupported
  fields; repair JSON; or add retries.
- **Reasoning:** The approved repair addresses the missing information at the model boundary while
  preserving exact schema, type, clarification, and literal-grounding enforcement. Offline tests
  establish only that the v3 contract is present and existing validation behavior is preserved;
  semantic extraction correctness requires another separately authorized live run.
- **Status:** Accepted.

### 2026-08-06 — Normalize one complete JSON fence and raise the bounded output cap

- **Decision:** At the provider-neutral extraction parsing boundary, accept raw JSON or exactly one
  complete whole-response Markdown fence labeled `json` or unlabeled, then apply every existing
  schema, grounding, clarification, and trust-boundary check unchanged. Raise only the manual live
  runner's output cap from 256 to 512 tokens; keep three calls, no retries, sequential execution,
  the 30-second timeout, and the $0.10 spend ceiling.
- **Context:** The second diagnostic live run completed all three Anthropic calls. All three
  responses began with a Markdown fence and all were rejected at JSON parsing. The first two ended
  normally and had closing fences; the third stopped at `max_tokens` after 256 output tokens and
  lacked a closing fence. The run used 673 input and 558 output tokens (1,231 total), at an
  estimated total cost of $0.006926.
- **Alternatives considered:** Accept arbitrary JSON substrings or surrounding prose; repair
  malformed or truncated JSON; add provider-specific finish-reason behavior; retry automatically;
  or leave the 256-token cap unchanged.
- **Reasoning:** Strict whole-response normalization addresses the two completed fenced responses
  without broadening trust boundaries, while 512 tokens gives the bounded live cases more room to
  finish. An incomplete fence remains invalid, including a `max_tokens` response, and no retry or
  extra call is introduced. The evidence does not yet establish that JSON enclosed by the first
  two fences will pass schema or grounding validation.
- **Status:** Accepted.

### 2026-08-06 — Instrument rejected live responses without exposing their content

- **Decision:** Add provider-neutral finish metadata and sanitized response-shape diagnostics,
  then require separate authorization for one bounded rerun. Do not loosen JSON parsing or repair
  model output.
- **Context:** The first live run completed 3/3 provider calls, and all 3/3 responses were
  deterministically rejected at JSON parsing. The run used 673 input tokens and 673 output tokens,
  cost an estimated $0.008076, and had approximate per-call latency of 3.75–4.57 seconds. Two
  responses reached the 256 output-token cap.
- **Alternatives considered:** Infer the failure from token counts; print response excerpts; strip
  fences or accept surrounding prose; or immediately rerun with different prompt or token limits.
- **Reasoning:** Existing evidence does not establish whether responses were fenced, prefaced with
  prose, or truncated. Shape-only instrumentation can distinguish those possibilities on a
  separately authorized rerun without recording raw output, customer content, or identifiers.
- **Status:** Accepted.

### 2026-08-06 — Bound live extraction validation behind a fixed manual runner

- **Decision:** Validate the existing extraction path with one manually confirmed Anthropic runner
  fixed to three synthetic cases, sequential execution, no retries, and a $0.10 pre-call spend
  ceiling. Keep the pricing assumptions local to the runner rather than adding a shared pricing
  catalog to the provider adapter.
- **Context:** Deterministic extraction validation and the Anthropic adapter exist, but the project
  needs a tightly bounded way to collect initial live-model evidence without making routine tests
  paid or network-dependent.
- **Alternatives considered:** Put pricing and budget behavior in the provider adapter; add a
  general evaluation framework; or invoke the adapter directly from an ad hoc command.
- **Reasoning:** A fixed script is the smallest auditable increment. It preserves the existing
  adapter and extraction boundaries, makes authorization and maximum spend visible before use,
  and keeps all ordinary testing offline.
- **Status:** Accepted.
