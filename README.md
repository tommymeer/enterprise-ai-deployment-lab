# Enterprise AI Deployment Lab

Hands-on projects for understanding how AI systems are designed, built, evaluated, broken, repaired, and prepared for deployment in real enterprise workflows.

This is a personal engineering lab. The goal is not to build demos that look intelligent. It is to understand the full system around the model: workflow, orchestration, tools, state, controls, failures, evaluation, and rollout.

## 🚀 Start here

[Support Agent walkthrough](./projects/support-agent/README.md) ·
[Architecture](./projects/support-agent/README.md#architecture) ·
[Evaluation](./projects/support-agent/README.md#evaluation) ·
[Business case & rollout](./projects/support-agent/README.md#business-case-and-rollout) ·
[Deep dive](./projects/support-agent/README.md#deep-dive)

## 🤖 Flagship: Delivered-Not-Received Support Agent

A synthetic ecommerce support workflow for customers whose package is marked delivered but cannot be found.

The LLM has a bounded job: convert the customer message into validated structured data.

Deterministic code then:

- retrieves customer, order, shipment, and carrier evidence
- applies policy and disposition rules
- checks whether the system is authorized to act
- issues an idempotent refund or escalates to a human
- records workflow state and an append-only trace

**What it demonstrates**

`bounded LLM use` · `orchestration` · `APIs` · `workflow state` · `authorization` · `idempotency` · `human escalation` · `traces` · `evals` · `rollout economics`

→ [Open the full project walkthrough](./projects/support-agent/README.md)

## 🧪 Lab method

**Reality → Build → Break → Repair → Abstract**

Start from the real workflow. Build the smallest credible system. Probe its failures. Repair them using evidence. Generalize only when the evidence supports it.

→ [Lab Operating Standard](./docs/lab-operating-standard.md)

## ⚠️ Scope

This is a learning and engineering record, not evidence of a production deployment or realized business results.

Synthetic data, integrations, policies, assumptions, and economics are labeled as such.
