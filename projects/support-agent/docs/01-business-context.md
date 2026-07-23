# Business Context

**Status: In progress**

## Purpose

Establish who this system would serve, what business problem it addresses, and why that problem
matters — before any technical design happens. This doc should be grounded in real or plausibly
realistic detail, with anything unverified explicitly flagged as an assumption rather than stated
as fact.

## Template

### Organization / team profile
_Who is the (real or modeled) organization? What kind of support does it provide? Scale?_
- TBD

### Problem statement
_What is going wrong today, in concrete terms (not "support is slow" but specifics: volumes,
delays, error rates, complaints)?_
- TBD

### Stakeholders
_Who is affected by this problem, and who would be affected by a proposed AI solution?_

| Stakeholder | Role | Interest / concern |
|---|---|---|
| | | |

### Business motivation
_Why does this problem matter to the business — cost, customer retention, compliance, other?_
- TBD

### Assumptions
_Anything above that is not verified against a real source should be listed here explicitly._
- TBD

### Evidence log
_Track individual claims or observations with enough provenance to judge how much to trust them.
Add one row per claim rather than leaving this as a single TBD._

| Claim / observation | Source | Date | Collection method | Evidence type (observed / reported / inferred / synthetic) | Confidence | Unresolved questions |
|---|---|---|---|---|---|---|
| | | | | | | |

### Data safety
_Answer before recording any real organization or customer detail above._
- Data classification: what kind of data would this involve, and how sensitive is it?
- Does this involve PII or other sensitive customer data?
- Is there explicit authorization to access or use this data for this project?
- What are the retention requirements, if any?
- Are there compliance constraints (regulatory, contractual, or internal policy)?
- May this information be sent to a model provider (e.g., in a prompt or API call)?
- May this information appear in fixtures, prompts, traces, logs, screenshots, or evaluation
  datasets?

**Default:** this project uses synthetic, placeholder data unless use of real data has been
explicitly authorized above and a safe handling plan is recorded here.

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
