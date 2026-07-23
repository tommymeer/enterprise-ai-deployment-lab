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

## The demo rule

**A successful demo is not sufficient for completion.**

A demo shows that a system can work under favorable, hand-picked conditions. It does not show
that the system was understood, evaluated against failure, costed out, or built for adoption. Any
project that stops at "it worked when I tried it" has completed the Build stage of
Reality → Build → Break → Repair → Abstract at most, and should say so plainly rather than
implying more.
