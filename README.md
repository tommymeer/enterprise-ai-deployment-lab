# Enterprise AI Deployment Lab

Hands-on projects for designing, implementing, evaluating, and preparing AI systems for deployment in real operational workflows.

This repository is a personal engineering lab, not a production product or vendor framework. Its purpose is to practice the full deployment problem: understand a workflow, define AI boundaries, implement the system, evaluate failures, reason about economics, and design a safe path to production.

## Start here

[Support Agent walkthrough](./projects/support-agent/README.md) ·
[Architecture](./projects/support-agent/README.md#architecture) ·
[Evaluation](./projects/support-agent/README.md#evaluation) ·
[Business case & rollout](./projects/support-agent/README.md#business-case-and-rollout) ·
[Deep dive](./projects/support-agent/README.md#deep-dive)

## Flagship project: Delivered-Not-Received Support Agent

A synthetic ecommerce support workflow for customers whose package is marked delivered but cannot be found.

The system uses an LLM only to convert the customer message into validated structured data. Deterministic code then retrieves customer, order, shipment, and carrier evidence; applies policy and disposition rules; checks execution authority; and either issues an idempotent refund or escalates to a human.

Every run produces explicit workflow state and an append-only trace so the decision can be reconstructed and evaluated.

→ [Open the full project walkthrough](./projects/support-agent/README.md)

### What this project demonstrates

- Bounded LLM use for natural-language extraction
- Deterministic orchestration, policy, and workflow state
- Clear tool and external-API boundaries
- Safe consequential actions with authorization and idempotency
- Human escalation and failure handling
- Trace-based observability and reconstructable decisions
- Outcome, trajectory, safety, and recovery evaluation
- Evidence-gated rollout planning and synthetic deployment economics

## How the lab works

Projects follow:

**Reality → Build → Break → Repair → Abstract**

The sequence is deliberate:

1. Investigate the operational workflow and constraints.
2. Build the smallest credible system.
3. Probe how and where it fails.
4. Repair failures using evidence.
5. Capture reusable patterns without overgeneralizing from one case.

The [Lab Operating Standard](./docs/lab-operating-standard.md) defines the evidence expected across workflow discovery, system design, technical ownership, evaluation, economics, adoption, and reuse.

## Scope and limitations

This is a learning and engineering record, not evidence of a production deployment or realized business results.

Project data, integrations, policies, and assumptions are explicitly labeled where synthetic. Claims about behavior, cost, and performance apply only to the documented lab conditions.
