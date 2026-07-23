# Project: Enterprise Customer Support Agent

**Status: In progress — Phase 1 (understanding the real workflow).** No system design or code
exists yet, by design. See `docs/lab-operating-standard.md` for why reality discovery comes
first.

## The scenario

A generic (not yet company-specific) enterprise customer support scenario: customers submit
requests through some channel, requests sometimes go unanswered or are delayed past an acceptable
window, and someone has proposed that an AI system could help reduce missed or delayed responses.
This is a **placeholder scenario** for the lab, not a description of a real company or a real
support team. It will be sharpened with concrete, sourced detail (or explicit, labeled
assumptions) as Phase 1 work proceeds — see `docs/01-business-context.md`.

## Project objective

Learn and apply the engineering disciplines required for an enterprise AI support system: by
understanding the workflow it would sit inside, designing around its failure modes, proving its
value and cost, and considering how humans would actually adopt and operate it — not by jumping
straight to a model integration.

## Current phase: understanding the real workflow

The project is currently in the **Reality** stage of the lab sequence
(Reality → Build → Break → Repair → Abstract). Work right now is limited to:

- Documenting business context and stakeholders (`docs/01-business-context.md`)
- Documenting the current, human workflow as it actually happens (`docs/02-current-workflow.md`)
- Establishing what is and isn't in scope for this project (`docs/03-system-boundaries.md`)
- Logging decisions and their reasoning as they're made (`docs/04-decision-log.md`)

No implementation, model selection, or architecture decisions should be treated as final until
this phase produces enough grounding to design against.

## Initial boundaries and open questions

These are starting points, expected to change as Phase 1 progresses:

- **Boundary (tentative):** the project is about *support request handling*, not broader CRM,
  billing, or account management systems.
- **Boundary (tentative):** "AI agent" here means a system that assists or drafts responses, not
  one assumed from the outset to fully replace a human in the loop.
- **Open question:** what channel(s) do requests actually arrive through, and does that change
  what "missed or delayed" means?
- **Open question:** who currently owns triage and response, and what does their existing tooling
  look like?
- **Open question:** what would make this workflow's owners trust or reject AI assistance?
- **Open question:** what is an acceptable response-time window, and who defines it?

## Planned lifecycle

This project is expected to move through the same five stages as every project in this lab:
**Reality → Build → Break → Repair → Abstract** (see the root `README.md`). Later stages are not
started and should not be treated as scoped or committed — they are a map, not a plan. See
`docs/lab-operating-standard.md` for the minimum evidence expected at each stage.

1. **Reality** — Understand the workflow and constraints before any design.
   - Workflow discovery: interview-style or document-based investigation of the real (or
     realistically modeled) support workflow, stakeholders, and pain points.
   - Business context and boundaries: define what problem is actually being solved, for whom, and
     what is explicitly out of scope.
2. **Build** — Design and implement the smallest system that could plausibly work.
   - System design: concrete architecture — inputs, outputs, components, human escalation points,
     and failure modes.
   - Implementation: build the smallest system that could plausibly work.
   - Evaluation: test against real and adversarial cases; measure quality, not just plausibility.
3. **Break** — Deliberately find where the system fails and why.
   - Failure analysis across bad inputs, edge cases, adversarial use, cost blowups, and silent
     errors — not just the happy path.
4. **Repair** — Fix identified failures and record what changed and why.
   - Includes deployment arithmetic (estimate real running cost and weigh it against value
     produced) and adoption/operations analysis (who would use this, what would make them trust or
     reject it, how it would be monitored day-to-day) once the system is stable enough to cost and
     operate.
5. **Abstract** — Extract at least one named, reusable artifact from this project — for example an
   evaluation harness, a failure taxonomy, a workflow discovery checklist, a policy-engine
   pattern, a human-review component, or a state-machine template. The artifact should be
   exercised or applied against at least one case beyond this project's original happy-path
   scenario before it is claimed as reusable; an artifact that has only ever been used once, in
   its original context, is not yet reusable. Close with an honest production-readiness
   assessment against `docs/lab-operating-standard.md`, explicitly distinguishing what was
   demonstrated from what would still be required for real production use.

See `portfolio/artifact-index.md` for artifacts this project may eventually produce.
