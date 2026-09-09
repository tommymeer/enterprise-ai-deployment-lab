# Deployment Economics

**Synthetic ROI model · Not a measured customer result**

This model asks a simple deployment question:

> If a delivered-not-received support workflow can safely handle more cases with less human effort and less unnecessary compensation, does the value exceed implementation and operating cost?

The inputs below are synthetic. They are placeholders for the customer-specific measurements that would be collected during discovery and a pilot.

## Base case

Assume a retailer has **10,000 eligible DNR cases per month** with a modeled baseline cost of about **$12.80 per case**:

- **$8.30** expected human labor
- **$4.50** unnecessary compensation

Under the synthetic base scenario:

- **70%** of eligible cases enter the workflow
- adopted cases cost about **$4.80** before fixed operating cost
- ongoing operating cost is **$10K/month**
- blended all-in cost falls to about **$8.20 per eligible case**
- illustrative net value is about **$46K/month**
- a **$100K** implementation would have a simple payback of about **2.2 months**
- about **1,170 hours/month** of support and review capacity are released

**This is a decision hypothesis, not a savings claim.** Released capacity only has economic value if the customer can redeploy it, avoid future hiring, improve service, or otherwise convert it into an operating benefit.

## Scenario range

| Result | Low | Base | High |
| --- | ---: | ---: | ---: |
| Workflow coverage | 40% | 70% | 85% |
| All-in cost / eligible case | ~$11.60 | ~$8.20 | ~$5.90 |
| Net value / eligible case | ~$1.30 | ~$4.60 | ~$7.00 |
| Illustrative monthly net value | ~$13K | ~$46K | ~$70K |
| Simple payback on $100K implementation | ~8 mo | ~2.2 mo | ~1.4 mo |
| Released support/review capacity | ~600 hrs | ~1,170 hrs | ~1,530 hrs |

Low, base, and high vary **coverage and workflow performance**, not retailer size.

## Where the value comes from

Adopted cases move through four controlled paths:

| Path | Base mix | Human-work assumption |
| --- | ---: | --- |
| Straight-through | 55% | 0 human minutes |
| Human review | 20% | 8 reviewer minutes |
| Clarification / customer action | 15% | 4 frontline minutes |
| Operational fallback | 10% | Baseline human effort preserved |

Straight-through rate is **not** treated as a labor-savings rate. The model values only the reduction in expected human effort across the full path mix.

Carrier recovery, CSAT, resolution time, consistency, auditability, fraud reduction, and retention are **not monetized**.

## What would determine whether this is real

A real pilot would replace the synthetic assumptions with measured customer data:

- eligible DNR volume and baseline handling time
- loaded frontline and reviewer cost
- review, clarification, fallback, and straight-through rates
- actual residual human effort by path
- compensation decisions and delayed adjudicated outcomes
- model, tool, retry, and integration cost
- workflow adoption and bypass reasons
- failure, recovery, and repeated-contact rates
- whether released capacity is actually redeployed or otherwise realized

The economic case weakens or fails if coverage is materially lower than expected, fallback or clarification work is much heavier, compensation outcomes do not improve, operating cost is higher, or released capacity has no realizable value.

## Rollout implication

The economics should be tested in stages rather than assumed from a working prototype:

**Discovery → shadow mode → human-reviewed pilot → limited autonomy → controlled expansion**

Expansion should depend on both **technical evidence** and **economic evidence**. A system can be technically correct and still fail to create customer value.

→ [Production rollout plan](06-production-rollout.md)

<details>
<summary><strong>Assumptions and formulas</strong></summary>

### Fixed synthetic assumptions

| Input | Value |
| --- | ---: |
| Eligible DNR cases / month | 10,000 |
| Baseline frontline handling | 12 min / case |
| Loaded frontline cost | $35 / hour |
| Baseline review rate | 20% |
| Review time | 8 min / review |
| Loaded reviewer cost | $50 / hour |
| Average compensation economic cost | $75 |
| Baseline unnecessary compensation rate | 6% |
| Model inference cost | $0.005 / adopted case |
| Implementation cost | $100,000 one time |
| Ongoing operating cost | $10,000 / month |

All values are synthetic assumptions.

### Baseline

```text
frontline labor
= 12 / 60 × $35
= $7.00 / case

expected review labor
= 20% × 8 / 60 × $50
= $1.33 / case

baseline human labor
= $8.33 / case

baseline unnecessary compensation
= 6% × $75
= $4.50 / case

baseline modeled economic cost
= $12.83 / eligible case
```

### Scenario calculation

For adopted cases:

```text
target human labor
= review path labor
+ clarification path labor
+ fallback path labor

target cost
= target human labor
+ target unnecessary compensation
+ inference cost
```

Across all eligible cases:

```text
blended monthly cost
= adopted cases × target cost
+ non-adopted cases × baseline cost
+ fixed operating cost

net value / eligible case
= baseline cost - blended all-in cost / eligible case

monthly net value
= eligible cases × net value / eligible case

simple payback months
= implementation cost / monthly net value
```

Implementation cost is used in payback and is not also charged as a monthly cost.

### Scenario assumptions

| Input | Low | Base | High |
| --- | ---: | ---: | ---: |
| Workflow coverage | 40% | 70% | 85% |
| Straight-through | 40% | 55% | 65% |
| Human review | 25% | 20% | 15% |
| Clarification | 20% | 15% | 12% |
| Operational fallback | 15% | 10% | 8% |
| Target unnecessary compensation rate | 5% | 3% | 2% |

</details>

<details>
<summary><strong>Evidence discipline</strong></summary>

**Known / implemented**

- The prototype uses a bounded model task for message extraction.
- Validation, routing, authorization, execution controls, state, and tracing are deterministic after extraction.
- Synthetic tests exercise the workflow paths and failure controls.

**Synthetic assumptions**

- Every business input and scenario value in this document.
- Target path mix, residual effort, compensation improvement, implementation cost, and operating cost.

**Not yet known**

- Actual customer workload and labor economics.
- Production adoption and path mix.
- Real integration and maintenance cost.
- Production failure, latency, and throughput characteristics.
- Whether released capacity becomes avoided hiring, cash savings, faster service, or no realizable financial benefit.

A positive modeled result is conditional on the assumptions above. Technical evaluation success does not establish production automation, customer benefit, or realized ROI.

</details>
