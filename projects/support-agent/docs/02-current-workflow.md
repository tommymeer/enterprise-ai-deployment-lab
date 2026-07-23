# Current Workflow

**Status: In progress**

## Purpose

Document how the support workflow actually happens today, before any AI assistance, so that a
future system design can be evaluated against the real process it would change — not an
idealized version of it.

## Template

### Workflow steps (as-is)
_Walk through the current process end to end, step by step._

1. TBD

### Actors involved
_Who touches this workflow, in what role, at what step?_

| Step | Actor | Action | Tooling used |
|---|---|---|---|
| | | | |

### Volume and timing
_How many requests, how often, what's the current time-to-response?_
- TBD

### Known pain points
_Where does this workflow currently break down, slow down, or frustrate people?_
- TBD

### What "good" looks like today
_Absent any AI system, what does a well-handled request look like?_
- TBD

### Assumptions
- TBD

### Evidence log
_Track individual claims or observations with enough provenance to judge how much to trust them.
Add one row per claim rather than leaving this as a single TBD._

| Claim / observation | Source | Date | Collection method | Evidence type (observed / reported / inferred / synthetic) | Confidence | Unresolved questions |
|---|---|---|---|---|---|---|
| | | | | | | |

### Data safety
_Answer before recording any real request content, ticket data, or screenshots above._
- Data classification: what kind of data appears in this workflow (request content, customer
  records, internal notes), and how sensitive is it?
- Does this involve PII or other sensitive customer data?
- Is there explicit authorization to access or use this data for this project?
- What are the retention requirements, if any?
- Are there compliance constraints (regulatory, contractual, or internal policy)?
- May this information be sent to a model provider (e.g., in a prompt or API call)?
- May this information appear in fixtures, prompts, traces, logs, screenshots, or evaluation
  datasets?

**Default:** this project uses synthetic, placeholder workflow examples unless use of real data
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
