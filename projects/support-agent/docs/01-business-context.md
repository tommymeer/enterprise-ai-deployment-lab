# Business Context

**Status: In progress — Reality stage, increment 1**

## Purpose

Establish who this system would serve, what business problem it addresses, and why that problem
matters — before any technical design happens. This doc should be grounded in real or plausibly
realistic detail, with anything unverified explicitly flagged as an assumption rather than stated
as fact.

This increment establishes enough business context to design a credible workflow. It is
deliberately lean, not a comprehensive industry report, and does not yet reconstruct the human
workflow or design the AI system.

## Template

### Synthetic organization profile

**Synthetic, not observed.** No real company is modeled here.

A US direct-to-consumer (DTC) ecommerce retailer that sells ordinary physical consumer goods
through its own website and ships via UPS, FedEx, and USPS. It handles customer reports of the
form "tracking says delivered, but I don't have the package."

Initial exclusions (out of scope for this increment): marketplace sellers, grocery / same-day
delivery, controlled or regulated goods, international customs cases, digital products, and
extremely high-value merchandise.

### Problem statement

Customers may report that carrier tracking shows a package as "delivered" while the
package cannot be located at the delivery address. This is the reference problem for this project.

*Inferred:* This is fundamentally an evidence-reconciliation and controlled-resolution problem.
Resolving a single case may require reconciling the customer's report, the retailer's order
information, carrier evidence including tracking events and picture proof when available, hypothetical merchant
policy, and the risk of two opposite errors: denying a legitimate claim, or compensating a false or
fraudulent one.

No volumes, delay figures, or error rates are established at this stage. Unknown — evidence not
yet established.

### Relevant actors

*Inferred / synthetic — roles are plausible for a DTC retailer of this shape, not observed at any
real company.*

| Actor | Role | Interest / concern |
|---|---|---|
| Customer | Reports non-receipt of a "delivered" package | Wants a fast, fair resolution (refund, replacement, or help locating the package) |
| Frontline support agent | Handles the inbound case | Needs a consistent, defensible way to decide or escalate |
| Carrier (UPS / FedEx / USPS) | Provided the delivery scan/evidence | Source of tracking and delivery evidence; may require a separate claim process |
| Retailer risk/fraud reviewer or designated escalation owner | Reviews cases for abuse patterns | Wants to limit compensation for false or repeated claims |
| Retailer finance / ops | Owns cost of refunds, replacements, and carrier claims | Wants predictable, bounded cost exposure |

Whether these roles exist as described, and who actually owns each decision, is not established —
see Important unknowns.

### Desired business and customer outcomes

*Inferred, not sourced from any specific company's stated goals.*

- Customer: a resolution that feels fast and fair, without having to prove a negative (that they
  didn't receive the package).
- Business: resolve legitimate cases at reasonable cost while limiting exposure to incorrect
  compensation, without so much friction that legitimate customers are wrongly denied and churn.

No specific target thresholds (e.g., resolution time, cost per case) are established. Unknown —
evidence not yet established.

### Principal risks

*Inferred from the structure of the problem, not from any observed incident data.*

- **Incorrect denial** — a legitimate non-receipt is denied or under-resolved, damaging trust and
  customer retention.
- **Incorrect compensation** — a case is refunded or replaced when the package was in fact
  delivered/received, or the claim is fraudulent or abusive.
- **Inconsistent handling** — similar cases resolved differently depending on which agent (or
  system) handles them, undermining fairness and auditability.
- **Carrier-dependency risk** — in cases requiring a carrier claim, resolution may depend on a
  carrier claims process the retailer does not fully control, creating delay or disputes outside
  the retailer's authority.

### Evidence log

| Claim / observation | Source | Date | Collection method | Evidence type | Confidence | Unresolved questions |
|---|---|---|---|---|---|---|
| Amazon directs customers to verify information such as the shipping address, delivery notices, and the area around the delivery location. | Amazon — "Find a Missing Package That Shows As Delivered" (https://www.amazon.com/gp/help/customer/display.html?nodeId=GCU8BWGTQNJKQEBS) | 2026-07-27 | Public help-page text, as summarized in the task brief; not independently browsed in this session | Reported | Medium — official published guidance, but consumer-facing only | Does this reflect the actual agent-side decision process, or only customer-facing self-help messaging? |
| Walmart directs customers to inspect the delivery location and confirmation, ask household members or neighbors, verify the saved address, and sometimes wait two business days because a carrier may mark a package delivered before it arrives. | Walmart — "Order Not Received" (https://www.walmart.com/help/article/order-not-received/af24f9d61b5143d9973f95c9d5bc3140) | 2026-07-27 | Public help-page text, as summarized in the task brief; not independently browsed in this session | Reported | Medium — official published guidance, but consumer-facing only | What triggers the two-day wait internally, and what happens if the package still isn't found after? |
| FedEx points customers toward picture proof of delivery and provides a flow for reporting a missing package. | FedEx — "FedEx says delivered but no package" (https://www.fedex.com/en-us/customer-support/faqs/receiving/tracking-questions/fedex-says-delivered-but-no-package.html) | 2026-07-27 | Public help-page text, as summarized in the task brief; not independently browsed in this session | Reported | Medium — official published guidance, but consumer-facing only | How reliable/available is photo proof of delivery in practice, and who evaluates it? |
| UPS directs customers to file a claim when tracking says delivered but the package cannot be found. | UPS — "Tracking Support" (https://www.ups.com/us/en/support/tracking-support) | 2026-07-27 | Public help-page text, as summarized in the task brief; not independently browsed in this session | Reported | Medium — official published guidance, but consumer-facing only | Who initiates and owns this claim on the retailer side — the retailer or the customer directly? |

### Assumptions

_Anything above that is not verified against a real source is listed here explicitly, with
confidence._

- The synthetic company profile (DTC retailer, ordinary goods, UPS/FedEx/USPS shipping) is an
  assumed scenario for this lab, not an observed company. **Confidence: N/A (stipulated, not a
  factual claim).**
- The listed actors (support agent, trust/fraud function, finance/ops) are a plausible
  organizational structure for a retailer of this shape, not observed. **Confidence: Low.**
- That "delivered-not-received" is handled as a distinct case type (rather than folded into
  general order-issue handling) is assumed for scoping purposes. **Confidence: Low.**
- That carrier evidence (tracking scans, photo proof) is available to the retailer at the time of
  the case is assumed. **Confidence: Medium** — plausible given the carrier sources, but not
  confirmed for this specific synthetic retailer.
- The four evidence-log sources describe customer-facing guidance only; whether they reflect any
  retailer's actual internal resolution logic is unknown and not claimed here.

### Important unknowns

The following are not established by this increment. None should be treated as decided when
designing a workflow:

- How cases enter support (e.g., channel, intake form). Unknown — evidence not yet established.
- What information the customer initially supplies. Unknown — evidence not yet established.
- Which order, tracking, delivery-proof, and account information an agent can access. Unknown —
  evidence not yet established.
- The sequence of verification and investigation steps an agent takes. Unknown — evidence not yet
  established.
- Possible resolution and closure states for a case. Unknown — evidence not yet established.
- Customer communication and follow-up responsibilities. Unknown — evidence not yet established.
- Relevant handoffs, tools, and exception paths. Unknown — evidence not yet established.
- Refund and replacement thresholds. Unknown — evidence not yet established.
- Order-value or item-category rules affecting how a case is handled. Unknown — evidence not yet
  established.
- Whether prior-claim history or account history is checked before resolving a case. Unknown —
  evidence not yet established.
- What frontline agents are permitted to decide versus escalate. Unknown — evidence not yet
  established.
- What fraud or abuse signals (if any) are used. Unknown — evidence not yet established.
- What triggers escalation beyond the frontline agent. Unknown — evidence not yet established.
- Case volume and typical handling time. Unknown — evidence not yet established.
- Error rates (incorrect denials/compensations) and their cost. Unknown — evidence not yet
  established.
- Who owns filing and following up on carrier claims — the retailer or the customer. Unknown —
  evidence not yet established.

### Data safety

_Answer before recording any real organization or customer detail above._
- Data classification: none — this increment uses only a synthetic company profile and publicly
  published carrier/retailer help-page content (no customer-level data of any kind).
- Does this involve PII or other sensitive customer data? No.
- Is there explicit authorization to access or use this data for this project? Not applicable —
  no real customer or proprietary data is used.
- What are the retention requirements, if any? Not applicable.
- Are there compliance constraints (regulatory, contractual, or internal policy)? Not applicable
  at this stage.
- May this information be sent to a model provider (e.g., in a prompt or API call)? Yes — all
  content here is synthetic or drawn from public help pages, safe to use in prompts.
- May this information appear in fixtures, prompts, traces, logs, screenshots, or evaluation
  datasets? Yes, under the same condition.

**Default:** this project uses synthetic, placeholder data unless use of real data has been
explicitly authorized above and a safe handling plan is recorded here. That default holds for this
increment.

**Authorization scope:** authorization to access or use real data in a controlled external
environment does not authorize storing or copying credentials, customer records, PII, or other
sensitive data into this Git repository. Real sensitive data must never appear in tracked
documentation, fixtures, prompts, traces, logs, screenshots, or evaluation datasets (see
`AGENTS.md`). When real-world evidence is used, repository artifacts must contain only sanitized,
aggregated, or synthetic representations that cannot identify customers or expose sensitive
information. Any controlled use of real data happens outside tracked repository artifacts, subject
to the applicable authorization and governance requirements.

## Sufficient to proceed?

**What this increment establishes:** a synthetic but scoped reference scenario (DTC retailer,
delivered-not-received cases), a problem statement framed as evidence reconciliation under
uncertainty, plausible actors, directionally reasonable business/customer outcomes and risks, and
a small evidence log of public carrier/retailer guidance labeled by evidence type.

**What it does not establish:** any real or observed internal workflow, decision thresholds,
volumes, error rates, costs, or agent permissions. Nothing here should be read as describing how
any actual retailer resolves these cases internally.

**Yes, with constraints.** The unknowns above (how cases enter support, what an agent can access,
verification steps, resolution states, communication responsibilities, handoffs/tools/exceptions,
permissions, escalation triggers, fraud signals, thresholds) are workflow questions, not business-
context questions, and this document deliberately leaves them undone.

The next task is not to claim discovery of a real retailer's observed current workflow — no such
observation exists. It is to construct a clearly labeled synthetic reference workflow hypothesis,
grounded in the public evidence already recorded in the evidence log above, with every step not
directly supported by that evidence explicitly labeled inferred or synthetic.
