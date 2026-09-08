# Enterprise AI Deployment Lab

Hands-on projects for designing, implementing, evaluating, and preparing AI systems for deployment in real operational workflows.

This repository is a personal engineering lab, not a production product or vendor framework. Its purpose is to practice the full deployment problem: understand a workflow, define AI boundaries, implement the system, evaluate failures, reason about economics, and design a safe path to production.

## Flagship project: Delivered-Not-Received Support Agent

A synthetic ecommerce-retailer workflow for customers whose package is marked delivered but cannot be found. A bounded LLM extracts validated structure from the customer message; deterministic code retrieves customer, order, shipment, and carrier evidence, applies policy and disposition rules, checks authority, and either executes an idempotent refund or escalates for human review.

Each run has explicit workflow state and an inspectable append-only trace, backed by an offline evaluation suite and a staged rollout and business-case design. See the [project README](projects/support-agent/README.md).

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

Projects follow **Reality → Build → Break → Repair → Abstract**: investigate the operational workflow first; build the smallest credible system; probe its failure modes; repair with evidence; then capture reusable patterns. The [lab operating standard](docs/lab-operating-standard.md) defines the evidence expected across discovery, design, evaluation, economics, adoption, and reuse.

## Scope and limitations

This is a learning and engineering record, not evidence of a production deployment or realized business results. Project data, integrations, policies, and assumptions are explicitly labeled where synthetic; claims about behavior, cost, and performance apply only to the documented lab conditions.
