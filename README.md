# Enterprise AI Deployment Lab

This repository is a hands-on, personal engineering lab for learning how enterprise AI systems
are actually understood, designed, built, evaluated, broken, repaired, and deployed. It is not a
product, a framework, or a portfolio of finished tools. It is a record of deliberate practice.

## Why this exists

Most AI tutorials teach model calls. They rarely teach the parts of the job that determine
whether an AI system survives contact with a real organization: understanding the actual
workflow being changed, designing around failure, proving the system is worth the cost of
running it, and getting humans to trust and adopt it. This lab exists to practice those parts
directly, project by project.

## Learning sequence: Reality → Build → Break → Repair → Abstract

Every project in this lab is expected to move through the same sequence:

1. **Reality** — Understand the real workflow, the real stakeholders, and the real constraints
   before writing any system design. Assumptions get named explicitly, not silently baked in.
2. **Build** — Design and implement the smallest system that could plausibly work, with clear
   boundaries and ownership.
3. **Break** — Deliberately probe the system for failure: bad inputs, edge cases, adversarial
   use, cost blowups, silent errors.
4. **Repair** — Fix what breaks, and record why it broke and what the fix actually changed.
5. **Abstract** — Extract what is reusable (patterns, checklists, evaluation harnesses, decision
   frameworks) so the next project starts from a higher floor, not from scratch.

Skipping a stage is a choice that should be named, not a default.

## First project: Enterprise Customer Support Agent

The first project (`projects/support-agent/`) works through a realistic enterprise scenario: a
customer support workflow where AI assistance is proposed as a way to reduce missed or delayed
responses. The project starts with understanding the current, human workflow before any system
design happens. See `projects/support-agent/README.md` for the current phase and planned
lifecycle.

## Core system concerns

Across every project in this lab, the following are treated as first-class engineering concerns,
not optional polish added at the end:

- **Evaluation** — how do we know the system works, and works well enough?
- **Observability** — can we see what the system is doing and why, in production and in testing?
- **Failure recovery** — what happens when the system is wrong, slow, or unavailable?
- **Security** — what can go wrong if the system is misused, and what is exposed if it fails?
- **Human escalation** — when and how does a human take over?
- **Adoption** — will the people who are supposed to use or benefit from this system actually
  use it, and what would stop them?
- **Economics** — what does running this system cost, and is that cost justified?

A project is not considered complete until it has addressed these concerns, not just produced a
working demo. See `docs/lab-operating-standard.md` for the full standard.

## What this repository is — and isn't

This repository is a **learning and engineering record**. It documents reasoning, decisions,
failures, and iteration. It is **not** evidence of a production deployment, a certified
enterprise system, or a vendor-ready product. Any claims about system behavior, cost, or
performance in this repo reflect lab conditions and stated assumptions, not live enterprise
usage, unless explicitly noted otherwise.
