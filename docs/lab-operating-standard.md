# Lab Operating Standard

This document defines what "done" means for a project in this lab. It applies to every project
under `projects/`. If a project deviates from this standard, the deviation should be stated
explicitly in that project's docs, not left implicit.

## The seven required project dimensions

Every project must, at some point in its lifecycle, produce visible evidence for each of the
following. "Visible" means written down somewhere in the project's docs — not just reasoned about
privately.

1. **Reality discovery** — The real workflow, the real people involved, and the real constraints
   have been investigated and documented before system design begins. Assumptions that stand in
   for missing real-world access are named as assumptions.
2. **Concrete system design** — A specific design exists: components, data flow, boundaries,
   inputs/outputs, and failure modes. Not a vague description of "using AI to help with X."
3. **Technical ownership** — The person doing the build can, on demand: explain the execution
   path, inspect the relevant code, schemas, traces, and logs, form and test hypotheses about
   observed behavior, identify or narrow which layer a failure lives in, and explain the repair
   made and the evidence for it. Using agents, documentation, tools, or peer review to get there is
   allowed and expected — technical ownership is about being able to account for the system, not
   about refusing help. Blindly delegating diagnosis (accepting a fix without understanding why it
   worked) does not count as ownership.
4. **Empirical model evaluation** — Claims about how well the system performs are backed by
   actual test cases, not intuition. This includes both "does it work" and "how does it fail."
5. **Deployment arithmetic** — The cost of running the system has been estimated and weighed
   against the value it produces, concisely covering: workload volume assumptions; tokens or API
   calls per unit of work; unit costs; retry and failure assumptions; human-review volume and
   labor cost; latency assumptions; low / base / high scenarios where uncertainty is material; and
   a comparison against a baseline process or value estimate.
6. **Adoption and operations** — Who would use this system, what would make them trust or reject
   it, and how it would be monitored and operated day-to-day have been considered concretely.
7. **Field-to-product leverage** — What was learned or built is captured in a form that a future
   project (in this lab or elsewhere) can reuse, rather than being locked inside this one project.

## Definition of project completion

A project is complete when all seven dimensions above have documented evidence, and the project's
decision log records the key tradeoffs made along the way. Completion does not require a polished
product, a deployed service, or a large feature set. It requires that the reasoning and evidence
for each dimension exist and are legible to someone other than the author.

## AI-assisted code quality and human review

AI-generated code is provisional until human review confirms its purpose and necessity; domain and
data invariants; failure behavior; behavioral test coverage; security, privacy, cost, and dependency
impact; readability and maintainability; and whether a simpler design would be sufficient.

- Prefer bounded changes over broad rewrites, and inspect diffs before committing.
- Passing tests are necessary but not sufficient. Tests should verify intended behavior rather than
  merely mirror the implementation.
- Avoid unnecessary dependencies, frameworks, compatibility shims, and speculative abstractions.
  Every abstraction should be explainable in plain English.
- Prefer simplification or deletion when complexity is not justified.
- Do not accept code merely because an agent produced it and the test suite passed.

## Minimum evidence per stage

These are lightweight evidence standards meant to keep each stage honest, not a formal approval
process. Nothing here requires sign-off, review gates, or paperwork beyond what's written in the
project's own docs — it's a checklist for the practitioner, not for a reviewer.

**Reality**
- Record evidence sources and label each as observed, reported, inferred, or synthetic.
- Record unresolved assumptions and their confidence.
- Establish baseline measurements where evidence exists.
- End with an explicit design-readiness decision: what is known, what is unknown, and what is
  safe to assume.

**Build**
- Define executable scope.
- Document workflow and system design.
- Identify deterministic and probabilistic responsibilities.
- Include tests for implemented behavior.
- Record known limitations and omitted production concerns.

**Break**
- Record reproducible failure cases.
- For each case, include input, expected behavior, actual behavior, severity, and reproduction
  steps.
- Include failures beyond the happy path.

**Repair**
- Reproduce the failure.
- Identify or narrow the root cause.
- Record the change made.
- Add a regression test or evaluation case.
- Record before-and-after evidence.
- Do not claim improvement from a code change alone — show the evidence that it improved things.

**Abstract**
- Name the reusable pattern or artifact.
- Explain what evidence supports the abstraction.
- State where the abstraction may not apply.
- Test it against at least one case outside the original happy path or workflow.

## Downstream production and evaluation requirements

The following are additions to this project standard. They are requirements for downstream
implementation and evaluation, not claims about capabilities that already exist and not reasons to
skip the required project sequence. The default architecture remains a modular monolith with a
deterministic workflow; models perform bounded tasks inside that workflow. These requirements must
not trigger premature multi-agent systems, distributed services, observability platforms, model
routers, or other infrastructure.

- **Full workflow tracing** — When the workflow is implemented, each case must be reconstructable
  through a trace ID and records of the workflow step; state before and after; model and prompt
  version; retrieved context; tool name, arguments, and result; latency; retries; token usage and
  estimated cost; evaluation result; escalation or human override; and final outcome. Traces must
  follow the repository's data-safety rules.
- **Explicit execution budgets** — Bound model calls, tool calls, retries, loop iterations, total
  latency, and estimated cost per case. Exceeding a budget must cause safe termination or
  escalation, never unbounded execution.
- **Rate-limit and capacity failure testing** — Test provider and dependency throttling,
  saturation, timeouts, and unavailable capacity, including the workflow's safe response and
  recovery behavior.
- **Idempotent consequential actions** — Refunds, replacements, messages, claims, and other
  consequential external actions must use an operation identity or equivalent control so retries
  cannot knowingly duplicate the real-world effect.
- **Layered evaluations** — Evaluate classification, extraction, evidence sufficiency, policy
  selection, tool choice, tool parameters, state transitions, final outcome, abstention,
  escalation correctness, and repeated-run consistency separately where each layer applies. Do not
  let an acceptable final answer conceal an unsafe intermediate decision.
- **Production failures become regression tests** — Convert every reproducible production failure
  into the smallest relevant deterministic test or evaluation case before or alongside repair,
  using sanitized or synthetic data.
- **Deliberate context construction** — Select, order, label, limit, and version model context for
  the bounded task; do not treat all available data or an ever-growing transcript as the default
  prompt.
- **Provider-neutral model interface** — Keep workflow contracts and domain behavior independent
  of a provider SDK. Add only the smallest interface needed for the models actually evaluated; do
  not build a speculative model router.
- **Governance as executable controls** — Express approved permissions, data handling, policy
  constraints, review requirements, and budget limits as testable runtime controls wherever the
  system can enforce them, with human ownership for unresolved policy.
- **Simplicity before complexity** — Meet these requirements first with local records, explicit
  workflow code, focused evaluations, and deterministic controls. Add services, platforms,
  orchestration, or additional agents only when measured evidence shows the simpler architecture
  is insufficient.

## The demo rule

**A successful demo is not sufficient for completion.**

A demo shows that a system can work under favorable, hand-picked conditions. It does not show
that the system was understood, evaluated against failure, costed out, or built for adoption. Any
project that stops at "it worked when I tried it" has completed the Build stage of
Reality → Build → Break → Repair → Abstract at most, and should say so plainly rather than
implying more.
