# Current Workflow

**Status: In progress — Reality stage, increment 2**

## Purpose

Document how the support workflow would plausibly happen for the "tracking says delivered, package
not received" case type, so a future system design can be evaluated against a concrete process
rather than a vague description of "using AI to help with support."

**No real retailer's internal workflow was observed for this increment.** This document is a
**synthetic reference workflow hypothesis**, constructed from the synthetic organization profile in
`01-business-context.md` and the public customer-facing carrier/retailer guidance listed in that
document's evidence log, plus a small set of new public sources listed below. Every step not
directly supported by that public evidence is explicitly labeled **Inferred** or **Synthetic** — see
the "Evidence classification" column in the workflow table. Nothing here should be read as
describing how any actual retailer resolves these cases internally.

## Reference workflow (synthetic hypothesis)

11 steps, covering intake through disposition and follow-up. Ordering, actor assignments, and the
existence of specific internal systems are Inferred or Synthetic unless marked Reported.

All values in the "Output / case state" column below — including states such as "refund issued,"
"denied," "pending customer action," and "escalated," and any similar internal case state named
elsewhere in this document — are **synthetic candidate states** proposed for this reference
workflow, not observed retailer production states. They exist to make the workflow executable
enough to reason about; no source describes an actual retailer's case-state model.

| # | Step | Primary actor | Input / trigger | Action | Information / system consulted | Output / case state | Evidence classification | Key uncertainty or exception |
|---|---|---|---|---|---|---|---|---|
| 1 | Case intake and customer/order identification | Frontline support agent | Customer contacts support reporting non-receipt of a "delivered" package | Open a case; identify the customer's account and the order in question | Support ticket/conversation system; customer-account history; order-management record | Case opened, linked to customer and order (or "order not identified") | Synthetic — intake channel and mechanics are not addressed by any listed source | Customer cannot identify the order (guest checkout, multiple accounts, gifted order) |
| 2 | Confirm issue is delivered-but-not-received | Frontline support agent | Case opened | Classify the reported issue as this case type rather than a different issue (wrong item, damage, never shipped) | Case intake notes; order/fulfillment record; carrier tracking status | Case classified as delivered-not-received (or redirected) | Synthetic — the case-type taxonomy is a project modeling choice | Order contains multiple shipments, only one of which is affected |
| 3 | Collect information initially supplied by the customer | Customer, via agent or intake form | Case opened | Capture order/tracking identifier, delivery address, when/how customer checked, who else could have received it | Support ticket/conversation system | Case notes recorded | Inferred — some structured intake is a logical prerequisite for every downstream verification step described by the public sources | Customer does not respond, or provides incomplete/contradictory information |
| 4 | Retrieve retailer order and fulfillment records | Frontline agent (system-assisted) | Order linked to case | Pull order items, ship-to address on file, shipment(s), fulfillment timestamps | Order-management record; fulfillment/shipment record | Order and shipment record attached to case | Inferred — necessary precursor to the address/timestamp checks the public sources describe | Order contains multiple shipments; fulfillment record incomplete or delayed |
| 5 | Verify address, delivery timestamp, and carrier status | Frontline agent (system-assisted) | Order/shipment record retrieved | Compare ship-to address on file against customer-confirmed address; check carrier delivery timestamp and status code | Order-management record; carrier tracking / proof-of-delivery source | Address match/mismatch noted; delivery status confirmed | Inferred (agent-side action) / Reported (narrow) — that a retailer agent internally compares address, timestamp, and status data against order records is Inferred, not itself described by any source. Only the underlying public evidence is Reported: FedEx's delivered-but-missing guidance evidences that carrier tracking includes a delivery timestamp and status code; Walmart's guidance evidences that customers are directed to verify their saved address (customer-facing self-help, not evidence of an internal agent comparison step) | Address information is disputed; tracking data unavailable or stale |
| 6 | Retrieve carrier evidence (tracking events, picture proof) | Frontline agent (system-assisted) | Delivered status confirmed | Retrieve detailed tracking event history and picture proof of delivery, if available | Carrier tracking / proof-of-delivery source | Evidence attached to case, or noted unavailable | Inferred (agent-side action) / Reported (narrow) — that a retailer agent internally retrieves and attaches this evidence to a case is Inferred, not described by any source. Only the underlying evidence is Reported: FedEx's delivered-but-missing guidance evidences that tracking event history and picture proof of delivery may be available | Picture proof unavailable; carrier evidence conflicts with customer report; external carrier system unavailable |
| 7 | Customer self-check / waiting guidance | Frontline agent → customer | Evidence retrieved, no immediate resolution (e.g., address correct, delivery very recent) | Advise customer to check the delivery location and ask household members/neighbors; if delivery is very recent, advise waiting because a carrier may scan "delivered" before physical arrival | Support ticket/conversation system; merchant policy source (for any wait guidance) | Case set to "pending customer action" / "waiting," or closed if customer finds the package | Reported (guidance content only) / Inferred (delivery mechanism) — Walmart's guidance evidences the content of this advice (check delivery location/confirmation, ask household members/neighbors, verify saved address, sometimes wait). That a frontline agent relays this guidance within a mediated support case, rather than the customer reaching it directly as self-service, is Inferred and not established by this source | Customer does not respond; how long to wait is not established by any source |
| 8 | Internal policy and case-context review | Frontline agent, possibly with risk/fraud reviewer | Step 7 complete without resolution, or skipped as unnecessary | Review case against internal policy and context: order value, item category, customer's prior-case/account history | Merchant policy source; customer-account/prior-case history; order-management record | Case has a policy-context assessment attached | Synthetic — that *some* policy/context review occurs is Inferred from the existence of risk actors named in `01-business-context.md`; its specific content is explicitly unresolved there | Duplicate cases or duplicate-compensation risk; case falls outside frontline permissions |
| 9 | Outcome selection or human escalation | Frontline agent, or escalation/risk-fraud reviewer | Policy-context review complete | Select an outcome from the branch set below, or escalate | All prior case data; merchant policy source | Disposition selected (see "Workflow outcomes") | Synthetic — the branch structure is a project modeling choice needed to make the workflow executable; the decision logic between branches is not established | Case falls outside frontline permissions; required carrier documentation missing |
| 10 | Execute selected outcome | Frontline agent / escalation owner / claims owner, depending on outcome | Outcome selected at step 9 | Carry out the outcome: issue refund, issue replacement, open/recommend a carrier claim, deny with explanation, or route to escalation | Order-management record (refund/replacement); carrier-claim record (retailer-side, Synthetic — see "Systems and records"); merchant policy source | Case state updated (e.g., "refund issued," "claim opened," "escalated," "denied") — synthetic candidate states, not observed | Synthetic for execution mechanics and for the retailer-side carrier-claim record (its fields, lifecycle, ownership, and system representation). Reported only for the existence of a public carrier claim path: UPS's supporting-documents guidance ties a delivered-but-missing report to a claim requiring documentation (e.g., invoice, merchandise description); USPS's file-a-claim guidance describes general missing-mail search and eligibility-dependent claims processes tied to shipment circumstances and purchased services — this does not itself establish a delivered-but-not-received claim path | Required carrier documentation missing; case falls outside frontline permissions; duplicate compensation risk |
| 11 | Customer communication, documentation, and follow-up | Frontline agent / system | Outcome executed | Communicate outcome and next steps to customer; record final disposition and rationale; schedule follow-up if pending on an external process (e.g., carrier claim) | Support ticket/conversation system; audit or case-disposition record | Case closed, or open pending external follow-up | Synthetic — documentation/follow-up structure is a project modeling choice, not described by any listed source | Customer does not respond to communication; carrier claim outcome pending indefinitely |

### Workflow outcomes (branches)

Possible dispositions selected at step 9 and carried out at step 10. Listed as a set of plausible
branches only — **the conditions that route a case to any one of these remain unknown** and are not
invented here:

- Request more information from the customer
- Advise customer to complete basic checks (inspect location, ask household/neighbors, verify
  address) and/or wait
- Wait and follow up
- Open or recommend a carrier inquiry or claim
- Escalate for human review
- Approve a replacement
- Approve a refund
- Deny or close with explanation
- Record the disposition and next action (applies regardless of which branch above is taken)

The specific conditions for refund, replacement, denial, or escalation are **not established** by
this increment. They will later need to be represented as explicit synthetic policy assumptions
during Build — this document does not silently supply them.

## Systems and records (categories, not vendor products)

Named as plausible categories consulted across the workflow above. All are Inferred or Synthetic
unless marked Reported — none are observed.

| Category | Evidence classification | Basis |
|---|---|---|
| Support ticket or conversation system | Inferred | Necessary for any case handling; existence not itself described by a public source |
| Order-management record | Inferred | Necessary precursor to address/order verification described in carrier guidance |
| Fulfillment or shipment record | Inferred | Necessary to know what was shipped and when |
| Carrier tracking / proof-of-delivery source | Reported (narrow) | Tracking events and picture proof of delivery are substantively evidenced by FedEx's delivered-but-missing guidance. UPS and USPS each have only a title-only source on general tracking/missing-mail support (Low confidence, no extracted claim), not used here to substantiate this claim; their substantive sources instead evidence a claims process — see Carrier-claim record below |
| Customer-account or prior-case history | Synthetic | Existence and use for this case type is an unresolved question per `01-business-context.md` |
| Merchant policy source | Synthetic | Content and even existence entirely unknown; assumed only because *some* consistent decision basis is implied by having a risk/fraud reviewer role |
| Carrier-claim record (retailer-side representation of a claim) | Synthetic | The public carrier claim path is Reported, but asymmetrically between carriers: UPS's supporting-documents guidance substantively ties a delivered-but-missing report to a claim requiring supporting documentation (e.g., invoice, merchandise description). USPS's file-a-claim guidance substantively describes general missing-mail search and eligibility-dependent claims processes tied to shipment circumstances and purchased services — this does not itself establish a delivered-but-not-received claim path. A distinct retailer-side record of that claim — its fields, lifecycle, ownership, or system representation — is not described by any source and remains Synthetic, a modeling choice for this reference workflow |
| Audit or case-disposition record | Synthetic | Not sourced from public evidence; included to satisfy the lab's auditability expectation, not because any source describes it |

## Failure and exception inventory

Complications the workflow above must eventually account for. **Not solved here** — this is an
inventory, not a resolution:

- Customer cannot identify the order (guest checkout, multiple accounts, gifted order)
- Tracking data is unavailable or stale
- Carrier evidence conflicts with the customer's report
- Picture proof of delivery is unavailable
- Order contains multiple shipments, only one of which is affected
- Address information is disputed between customer and order record
- Required carrier claim documentation is missing (e.g., invoice, merchandise description)
- The case falls outside frontline agent permissions
- Customer does not respond to a request for information or self-check guidance
- An external carrier tracking/claims system is unavailable
- Duplicate cases or duplicate-compensation risk for the same underlying order
- Incorrect order/customer linkage (Synthetic — a plausible failure mode of the Synthetic intake
  mechanics at step 1, not sourced)
- Order or fulfillment system unavailable (Inferred — a plausible failure mode of the Inferred
  order/fulfillment records used at step 4)
- Refund or replacement execution failure after approval (Synthetic — a plausible failure mode of
  the Synthetic execution mechanics at step 10)
- Carrier claim rejected or expired (Inferred — a plausible outcome of the Reported public carrier
  claim path, not itself described by any source)
- Tracking events conflicting with picture proof (Inferred — both are Reported carrier-evidence
  elements per FedEx guidance; a conflict between them is a plausible complication, not itself
  described by any source)
- Follow-up deadline passing without an external result (Synthetic — a plausible failure mode of
  the Synthetic follow-up structure at step 11)

## Assumptions and design choices made constructing this workflow

- Assumed a single case is owned end-to-end by one frontline agent (with optional escalation),
  rather than split across specialized queues. **Confidence: Low** — a plausible simplification,
  not observed.
- Assumed self-check/wait guidance (step 7) is offered before policy/escalation review (step 8),
  mirroring the order in which Walmart's public guidance presents these actions to customers.
  **Confidence: Low** — customer-facing ordering may not reflect internal agent-side sequencing.
- Assumed a distinct "policy and case-context review" step exists at all, separate from outcome
  selection. **Confidence: Low** — inferred only from the existence of a risk/fraud actor named in
  `01-business-context.md`, not from any source describing an internal review step.
- Assumed carrier claim initiation (part of step 10) is something the retailer can open or
  recommend, rather than something only the customer can do directly with the carrier. **Confidence:
  Low** — this exact question is flagged as unresolved in `01-business-context.md` and is not
  answered by the UPS/USPS sources, which describe the claims process without saying who initiates
  it in a retailer-mediated scenario.
- Treated "delivered-not-received" as a distinct case type with its own workflow (rather than a
  branch of general order-issue handling), consistent with the same assumption already flagged in
  `01-business-context.md`.
- Did not invent any refund/replacement thresholds, fraud rules, wait-period lengths, or permission
  boundaries. Where the public sources imply an action exists (e.g., "sometimes wait," "may require
  documentation") without specifying a rule, the table cites the action as Reported and leaves the
  triggering condition unresolved.

## Evidence log

| Claim / observation | Source | Date | Collection method | Evidence type | Confidence | Unresolved questions |
|---|---|---|---|---|---|---|
| Customers are directed to inspect the delivery location and confirmation, ask household members or neighbors, verify the saved address, and sometimes wait because a carrier may mark a package delivered before physical arrival. | Walmart — "Order Not Received" (https://www.walmart.com/help/article/order-not-received/af24f9d61b5143d9973f95c9d5bc3140) | 2026-07-27 | Public help-page text as summarized in the task brief; not independently browsed this session | Reported | Medium — official published guidance, consumer-facing only | Does this reflect internal agent-side sequencing, or only customer self-help messaging? |
| Not applicable — source identified by URL/title only; no substantive claim was extracted, and it is not used to substantiate any workflow claim in this document. | FedEx — "Tracking and Managing Deliveries" (https://www.fedex.com/en-us/tracking/guide-for-tracking-managing-deliveries.html) | 2026-07-27 | Source listed by URL/title only in the task brief; no content extracted; not independently browsed | Source inventory only — not substantive evidence | Not applicable — no claim extracted | Not applicable — source not used as evidence |
| Tracking events and picture proof of delivery may be available; FedEx provides a flow for reporting a delivered package as missing. | FedEx — "Delivered notification but package cannot be found" (https://www.fedex.com/en-us/customer-support/faqs/receiving/tracking-questions/fedex-says-delivered-but-no-package.html) | 2026-07-27 | Public help-page text as summarized in the task brief; not independently browsed | Reported | Medium — official published guidance, consumer-facing only | How reliable/available is picture proof in practice, and who evaluates it internally? |
| Not applicable — source identified by URL/title only; no substantive claim was extracted, and it is not used to substantiate any workflow claim in this document. | UPS — "Tracking Support" (https://www.ups.com/us/en/support/tracking-support) | 2026-07-27 | Source listed by URL/title only in the task brief; no content extracted; not independently browsed | Source inventory only — not substantive evidence | Not applicable — no claim extracted | Not applicable — source not used as evidence |
| A delivered-but-missing package may lead to a claim; claims may require supporting documentation such as an invoice and a detailed merchandise description. | UPS — "Supporting Documents for Claims" (https://www.ups.com/us/en/support/file-a-claim/supporting-documents) | 2026-07-27 | Public help-page text as summarized in the task brief; not independently browsed | Reported | Medium — official published guidance, consumer-facing only | Who initiates and owns this claim on the retailer side — retailer or customer directly? |
| Not applicable — source identified by URL/title only; no substantive claim was extracted, and it is not used to substantiate any workflow claim in this document. | USPS — "Missing Mail and Lost Packages" (https://www.usps.com/help/missing-mail.htm) | 2026-07-27 | Source listed by URL/title only in the task brief; no content extracted; not independently browsed | Source inventory only — not substantive evidence | Not applicable — no claim extracted | Not applicable — source not used as evidence |
| USPS provides inquiry, Missing Mail Search, and claims paths; claim eligibility depends on shipment circumstances and purchased services. | USPS — "File a Claim" (https://www.usps.com/help/claims.htm) | 2026-07-27 | Public help-page text as summarized in the task brief; not independently browsed | Reported | Medium — official published guidance, consumer-facing only | What shipment circumstances/purchased services actually gate eligibility? Not stated. |

All seven sources are consumer-facing published guidance, not internal retailer process
documentation. None describe agent-side decision logic, permissions, or thresholds — see
"Important unknowns" in `01-business-context.md`, which still apply unchanged.

## Data safety

_Answer before recording any real request content, ticket data, or screenshots above._
- Data classification: none — this document contains only a synthetic workflow hypothesis and
  publicly published carrier/retailer help-page content. No customer-level data of any kind.
- Does this involve PII or other sensitive customer data? No.
- Is there explicit authorization to access or use this data for this project? Not applicable — no
  real customer or proprietary data is used.
- What are the retention requirements, if any? Not applicable.
- Are there compliance constraints (regulatory, contractual, or internal policy)? Not applicable at
  this stage.
- May this information be sent to a model provider (e.g., in a prompt or API call)? Yes — all
  content here is synthetic or drawn from public help pages, safe to use in prompts.
- May this information appear in fixtures, prompts, traces, logs, screenshots, or evaluation
  datasets? Yes, under the same condition.

**Default:** this project uses synthetic, placeholder workflow examples unless use of real data has
been explicitly authorized above and a safe handling plan is recorded here. That default holds for
this increment.

**Authorization scope:** authorization to access or use real data in a controlled external
environment does not authorize storing or copying credentials, customer records, PII, or other
sensitive data into this Git repository. Real sensitive data must never appear in tracked
documentation, fixtures, prompts, traces, logs, screenshots, or evaluation datasets (see
`AGENTS.md`). When real-world evidence is used, repository artifacts must contain only sanitized,
aggregated, or synthetic representations that cannot identify customers or expose sensitive
information. Any controlled use of real data happens outside tracked repository artifacts, subject
to the applicable authorization and governance requirements.

## Open questions

Carried forward unresolved, matching `01-business-context.md`'s "Important unknowns," now scoped to
specific workflow steps:

- What triggers escalation beyond the frontline agent (step 9)? Unknown.
- What frontline agents are permitted to decide versus escalate (steps 9–10)? Unknown.
- What fraud or abuse signals, if any, are used in the policy/context review (step 8)? Unknown.
- Refund/replacement thresholds and order-value or item-category rules (steps 8–10)? Unknown.
- Whether prior-claim or account history is actually checked (step 8), and by whom? Unknown.
- Who owns filing and following up on a carrier claim — retailer or customer (step 10)? Unknown.
- How long a "wait" period (step 7) is, and what happens if the package still isn't found after?
  Unknown.
- Case volume and typical handling time across this workflow? Unknown.
- Error rates (incorrect denials/compensations) and their cost? Unknown.

## Sufficient to proceed?

**Yes, with constraints.**

- This is a synthetic reference workflow hypothesis, not an observed production process.
- It is detailed enough to begin drafting technical data structures and state transitions (e.g., a
  case object moving through the states implied by the "Output / case state" column above).
- Policy thresholds, permissions, system contracts, and risk signals remain unresolved and must not
  be silently invented during Build. Anywhere this document needed one to stay executable (case
  taxonomy, step ordering, branch structure), it is labeled Synthetic in the table above rather than
  presented as a discovered fact.
