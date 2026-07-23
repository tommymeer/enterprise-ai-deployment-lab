# System Boundaries

**Status: In progress**

## Purpose

Define explicitly what this system is and is not responsible for, before design work begins.
Boundaries prevent scope creep and make later tradeoffs (what to build first, what to defer)
easier to reason about.

This document deliberately separates three different kinds of statement, so they don't get
conflated:

- **Observed boundaries** — facts about the current environment and workflow, gathered during
  Reality. These describe what exists today, not what a future system will do.
- **Tentative hypotheses** — provisional guesses about what a future system might need to do,
  named as hypotheses precisely so they can be revised without friction later.
- **Proposed component contracts** — draft shapes for inputs, outputs, and interfaces. These are
  useful to sketch early to stress-test thinking, but they are drafts, not commitments. Final
  component contracts belong to the Build stage, once Reality discovery is complete — nothing in
  this section should be treated as a finalized architecture.

## Observed boundaries (current environment — Reality)
_What is actually true today about the systems, tools, and processes this project would touch._

### Current systems and tools in play
- TBD

### Current data flows and dependencies
_What existing systems, tools, or data sources are involved in the current workflow?_
- TBD

### Current constraints
_Real constraints already known today (access limits, compliance requirements, tooling
limitations, staffing, etc.), as opposed to constraints assumed about a future system._
- TBD

## Tentative hypotheses (future system — not yet decided)
_Provisional only. Expected to change as Reality discovery and Build proceed — do not treat these
as scoped or committed._

### In scope (hypothesis)
_What this system might be responsible for handling._
- TBD

### Out of scope (hypothesis)
_What this system would explicitly not handle, and why._
- TBD

### Non-goals
_Things that might sound related but are deliberately excluded from this project's ambition._
- TBD

## Proposed component contracts (draft only — not final until Build)
_Sketches useful for early thinking. Do not finalize or implement against these until the Build
stage, once Reality discovery is complete._

### Inputs (draft)
_What data or events might the system receive, and from where?_
- TBD

### Outputs (draft)
_What might the system produce, and who or what would consume it?_
- TBD

### Human-in-the-loop points (draft)
_Where might a human review, approve, or take over?_
- TBD

### Evidence log
_Track individual claims or observations with enough provenance to judge how much to trust them.
Add one row per claim rather than leaving this as a single TBD._

| Claim / observation | Source | Date | Collection method | Evidence type (observed / reported / inferred / synthetic) | Confidence | Unresolved questions |
|---|---|---|---|---|---|---|
| | | | | | | |

### Data safety
_Answer before recording any real system names, data samples, or screenshots above._
- Data classification: what kind of data would flow through this system, and how sensitive is it?
- Does this involve PII or other sensitive customer data?
- Is there explicit authorization to access or use this data for this project?
- What are the retention requirements, if any?
- Are there compliance constraints (regulatory, contractual, or internal policy)?
- May this information be sent to a model provider (e.g., in a prompt or API call)?
- May this information appear in fixtures, prompts, traces, logs, screenshots, or evaluation
  datasets?

**Default:** this project uses synthetic, placeholder data and fixtures unless use of real data
has been explicitly authorized above and a safe handling plan is recorded here.

**Authorization scope:** authorization to access or use real data in a controlled external
environment does not authorize storing or copying credentials, customer records, PII, or other
sensitive data into this Git repository. Real sensitive data must never appear in tracked
documentation, fixtures, prompts, traces, logs, screenshots, or evaluation datasets (see
`AGENTS.md`). When real-world evidence is used, repository artifacts must contain only sanitized,
aggregated, or synthetic representations that cannot identify customers or expose sensitive
information. Any controlled use of real data happens outside tracked repository artifacts, subject
to the applicable authorization and governance requirements.

### Open questions
- TBD
