# Decision Log

**Status: In progress**

**Execution status:** The latest bounded live validation passed 2/3 cases end to end. Disabling
adaptive thinking resolved the prior truncation, and the remaining failure is a clarification-
consistency mismatch addressed offline below; its live effect has not yet been validated.

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
