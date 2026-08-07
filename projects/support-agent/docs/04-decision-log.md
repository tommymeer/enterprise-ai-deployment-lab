# Decision Log

**Status: In progress**

**Execution status:** The first bounded live validation was executed; its three provider responses
were rejected during deterministic JSON parsing and require sanitized shape diagnostics.

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
