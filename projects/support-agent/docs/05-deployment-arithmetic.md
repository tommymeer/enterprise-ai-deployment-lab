# Deployment Arithmetic / Synthetic ROI Model

**Status: synthetic business case for customer discovery; not a measured ROI result**

> This is a synthetic deployment scenario showing how I would evaluate the economics with a
> customer. It is not evidence that the implemented prototype actually produces these savings.

## 1. Economic hypothesis

For an eligible delivered-not-received (DNR) case, a bounded workflow may release support capacity
and reduce unnecessary compensation by routing cases among four controlled paths. The economic
question is whether those benefits exceed model/tool costs and fixed implementation and operating
costs at the customer's actual workload and performance levels.

The model does **not** treat released support capacity as automatic headcount savings. Its value is
realized only if the customer can redeploy that capacity, avoid future hiring, improve service, or
otherwise convert it into an operational benefit. Carrier recovery is $0 in every scenario and is
only unmodeled upside. CSAT, resolution time, consistency, auditability, fraud, and retention are
also non-monetized.

## 2. Synthetic low / base / high business case

The retailer baseline is fixed across scenarios: 10,000 eligible DNR cases per month, about $8.30
of expected human labor and $4.50 of unnecessary compensation per case, or **about $12.80 per
eligible case**. Low/base/high vary deployment coverage and target performance, not retailer size.
Exact calculations are retained in Appendix A for auditability; the hiring-manager-facing outputs
below are rounded to reflect the uncertainty of synthetic inputs. Mathematically precise outputs do
not imply precise economic forecasts.

| Result | Low | Base | High |
|---|---:|---:|---:|
| Workflow coverage | 40% | 70% | 85% |
| Target human labor / adopted case | ~$3.40 | ~$2.50 | ~$1.90 |
| Target unnecessary compensation / adopted case | ~$3.80 | ~$2.30 | ~$1.50 |
| Target cost / adopted case before fixed operating cost | ~$7.10 | ~$4.80 | ~$3.50 |
| Blended monthly cost, adopted + non-adopted | ~$106K | ~$72K | ~$49K |
| Monthly operating cost | $10K | $10K | $10K |
| Blended target all-in cost / eligible case | ~$11.60 | ~$8.20 | ~$5.90 |
| Net value / eligible case | ~$1.30 | ~$4.60 | ~$7.00 |
| Monthly illustrative net value | ~$13K | ~$46K | ~$70K |
| Illustrative payback on $100K implementation | ~8 months | ~2 months | ~1–2 months |
| Released support/review capacity / month | ~600 hours | ~1,200 hours | ~1,500 hours |

The base scenario therefore suggests roughly $46K of monthly net value and a roughly two-month
simple payback **if** its synthetic assumptions hold and released capacity is economically useful.
This is a decision hypothesis to test in discovery and a pilot, not a forecast or claim of customer
savings.

## 3. Four target workflow paths

Path rates are conditional on adopted cases and sum to 100% in each scenario.

| Path | Low | Base | High | Synthetic human-work assumption |
|---|---:|---:|---:|---|
| Straight-through | 40% | 55% | 65% | 0 human minutes |
| Human review | 25% | 20% | 15% | 8 reviewer minutes at $50/hour |
| Clarification / customer action | 20% | 15% | 12% | 4 frontline minutes at $35/hour |
| Operational fallback | 15% | 10% | 8% | Preserve baseline expected human labor cost |

Straight-through rate is not itself a labor-savings rate. The model values only the difference
between baseline expected labor and the path-weighted target labor. Operational fallback includes
safe manual takeover after provider, dependency, validation, budget, or execution failure.

## 4. What we would measure in a real pilot

- Confirm eligible DNR volume, baseline handling minutes, review incidence and minutes, loaded
  labor rates, compensation economics, and unnecessary-compensation outcomes using an approved
  representative period.
- Measure actual workflow adoption and bypass reasons; report straight-through, review,
  clarification, and fallback rates separately.
- Measure residual frontline and reviewer minutes for every path, including repeated contacts,
  rework, exception sampling, manual takeover, and operational recovery.
- Measure model and integration/tool calls, retries, failures, tokens, latency, and cost per adopted
  case. Reconcile these with the fixed cost of monitoring, evaluation, policy, and integration upkeep.
- Compare compensation decisions with delayed, adjudicated outcomes. Do not infer compensation
  improvement from technical correctness or automation rate alone.
- Track whether released capacity is redeployed or otherwise realized; do not relabel it as cash or
  headcount savings without evidence.
- Monitor CSAT, resolution time, consistency, auditability, fraud, and retention separately without
  assigning financial value until a causal, customer-approved value model exists.

Only sanitized, aggregated measurements may enter repository artifacts. Real customer records,
PII, credentials, raw conversations, and sensitive traces remain prohibited.

---

## Appendix A — Formulas and arithmetic

All currency is illustrative. Exact calculations below use unrounded intermediate values; the main
table rounds only the final outputs because input uncertainty dominates arithmetic precision.

### Fixed baseline

```text
frontline labor = 12 / 60 × $35 = $7.00 per case
expected review labor = 20% × 8 / 60 × $50 = $1.333333 per case
baseline human labor = $7.00 + $1.333333 = $8.333333 per case
baseline unnecessary compensation = 6% × $75 = $4.50 per case
baseline modeled economic cost = $8.333333 + $4.50 = $12.833333 per case
```

### Scenario calculation

For scenario path rates `R` (review), `C` (clarification), and `F` (fallback):

```text
target human labor / adopted case
  = R × (8 / 60 × $50)
    + C × (4 / 60 × $35)
    + F × $8.333333

target unnecessary compensation / adopted case
  = target unnecessary compensation rate × $75

target cost / adopted case before fixed operating cost
  = target human labor + target unnecessary compensation + $0.005 inference

blended monthly cost before fixed operating cost
  = adopted cases × target cost
    + non-adopted cases × $12.833333

blended target all-in cost / eligible case
  = (blended monthly cost + $10,000) / 10,000

net value / eligible case
  = $12.833333 - blended target all-in cost / eligible case

monthly net value = 10,000 × net value / eligible case
payback months = $100,000 / positive monthly net value
```

### Calculation-detail scenario results

These figures reproduce the main table with results displayed to six decimal places and formulas
evaluated without rounded intermediate values. They make the arithmetic auditable; they are not
precise forecasts of real customer economics.

| Result | Low | Base | High |
|---|---:|---:|---:|
| Target human labor / adopted case | $3.383333 | $2.516667 | $1.946667 |
| Target unnecessary compensation / adopted case | $3.750000 | $2.250000 | $1.500000 |
| Target cost / adopted case before fixed operating cost | $7.138333 | $4.771667 | $3.451667 |
| Blended monthly cost before fixed operating cost | $105,553.333333 | $71,901.666667 | $48,589.166667 |
| Monthly operating cost | $10,000.000000 | $10,000.000000 | $10,000.000000 |
| Blended target all-in cost / eligible case | $11.555333 | $8.190167 | $5.858917 |
| Net value / eligible case | $1.278000 | $4.643167 | $6.974417 |
| Monthly illustrative net value | $12,780.000000 | $46,431.666667 | $69,744.166667 |
| Illustrative payback on $100,000 implementation | 7.824726 months | 2.153703 months | 1.433812 months |
| Released support/review capacity / month | 584.000000 hours | 1,171.333333 hours | 1,534.533333 hours |

Adopted cases equal eligible cases times workflow coverage. Non-adopted cases retain baseline
economics. Implementation cost is a one-time investment and is used in payback, not also charged as
a monthly cost.

For released hours, baseline expected human time is `12 + 20% × 8 = 13.6 minutes` per eligible
case. Target expected time is `R × 8 + C × 4 + F × 13.6` minutes per adopted case. Because the
fallback input specifies baseline expected *labor cost* rather than its staffing mix, the hours
calculation additionally assumes fallback preserves baseline expected human time. This assumption
must be replaced with measured fallback minutes in a pilot.

## Appendix B — Assumption register

### Fixed synthetic retailer assumptions

| Input | Value | Evidence classification |
|---|---:|---|
| Eligible DNR cases/month | 10,000 | SYNTHETIC ASSUMPTION |
| Baseline frontline handling | 12 minutes/case | SYNTHETIC ASSUMPTION |
| Loaded frontline cost | $35/hour | SYNTHETIC ASSUMPTION |
| Baseline human review rate | 20% | SYNTHETIC ASSUMPTION |
| Baseline review time | 8 minutes/review | SYNTHETIC ASSUMPTION |
| Loaded reviewer cost | $50/hour | SYNTHETIC ASSUMPTION |
| Average compensation economic cost | $75 | SYNTHETIC ASSUMPTION |
| Baseline unnecessary compensation rate | 6% | SYNTHETIC ASSUMPTION |
| Model inference cost | $0.005/adopted case | SYNTHETIC ASSUMPTION |
| Integration/tool variable cost | $0/adopted case | SYNTHETIC ASSUMPTION; placeholder, not evidence of free integrations |
| Implementation cost | $100,000 one time | SYNTHETIC ASSUMPTION |
| Ongoing operating cost | $10,000/month | SYNTHETIC ASSUMPTION |
| Baseline and target carrier recovery | $0 | SYNTHETIC ASSUMPTION; unmodeled upside only |

### Scenario performance assumptions

| Input | Low | Base | High | Evidence classification |
|---|---:|---:|---:|---|
| Workflow coverage | 40% | 70% | 85% | SYNTHETIC ASSUMPTION |
| Straight-through | 40% | 55% | 65% | SYNTHETIC ASSUMPTION |
| Human review | 25% | 20% | 15% | SYNTHETIC ASSUMPTION |
| Clarification/customer action | 20% | 15% | 12% | SYNTHETIC ASSUMPTION |
| Operational fallback | 15% | 10% | 8% | SYNTHETIC ASSUMPTION |
| Target unnecessary compensation rate | 5% | 3% | 2% | SYNTHETIC ASSUMPTION |

## Appendix C — Evidence classifications

### KNOWN / MEASURED

- The prototype uses a bounded model task for message extraction and deterministic validation,
  routing, authorization, execution controls, and tracing after extraction.
- Small synthetic live-extraction runs provide token, inference-cost, and some latency observations
  recorded in `04-decision-log.md`. They are not production workload or ROI measurements.
- Deterministic tests and synthetic adapters exercise all four paths, but only extraction has used a
  live provider. No live customer, order, shipment, carrier, refund, replacement, or claims
  integration has been demonstrated.

### SYNTHETIC ASSUMPTIONS

- Every business input and scenario value in this document, including the reference retailer and
  baseline workflow, is constructed for illustration rather than observed at a customer.
- Target path mix, residual effort, compensation improvement, adoption, implementation cost, and
  operating cost are scenario inputs—not conclusions from prototype evaluations.

### NOT YET KNOWN

- Actual customer workload, labor, review, compensation, adoption, path mix, integration cost,
  implementation effort, maintenance burden, failures, throughput, latency, and capacity value.
- Whether released capacity would become useful operational capacity, avoided hiring, cash savings,
  faster service, or no realizable financial benefit.

### Benchmark calibration

Public benchmarks are used only to test whether a synthetic input is directionally plausible or to
identify variables worth measuring. None maps cleanly to this DNR workflow, and none converts a
synthetic assumption into known or measured project evidence. Customer-specific discovery and pilot
measurements would replace these inputs before an investment decision.

- The U.S. Bureau of Labor Statistics, [Retail Trade: NAICS 44–45, 2025 occupational wage
  data](https://www.bls.gov/iag/tgs/iag44-45.htm), reports customer service representative hourly
  wages of $17.96 median and $19.05 mean, and first-line retail sales supervisor/manager wages of
  $23.18 median and $25.40 mean. These are wages, not fully loaded employer costs. They make the
  synthetic $35 frontline and $50 reviewer rates directionally plausible after benefits, payroll,
  and overhead, but do not prove either rate or support a precise burden multiplier.
- Gorgias, [Customer Service Benchmarks: Real Data from 1,000+ Ecommerce
  Brands](https://www.gorgias.com/blog/customer-service-benchmarks), reports material variation in
  response performance across ecommerce verticals and materially faster response times among
  brands with 30%+ automation than brands with near-zero automation. This is directional evidence
  that automation can change support operations and that generic benchmarks are not universal. It
  does not validate the synthetic 12-minute DNR active-handling assumption: response time and active
  handling time are different measures.
- The National Retail Federation, [2025 Retail Returns
  Landscape](https://nrf.com/research/2025-retail-returns-landscape), reports that 9% of all returns
  were fraudulent. This supports returns and compensation leakage as a real retail concern, but
  returns are not DNR cases and fraud is not the same as unnecessary compensation. It does not
  validate the synthetic 6% baseline or any target unnecessary-compensation rate.

## Appendix D — Sensitivity and interpretation

At base-case performance, an adopted case creates `$12.833333 - $4.771667 = $8.061667` before
fixed operating cost. With 70% coverage, ongoing operating cost breaks even at approximately
**1,772 eligible cases/month** (`$10,000 / (70% × $8.061667)`). Approximately **3,249 eligible
cases/month** would cover ongoing operating cost plus enough monthly value for a simple 12-month
payback on implementation (`($10,000 + $100,000 / 12) / (70% × $8.061667)`). These thresholds
assume fixed performance, coverage, and costs as volume changes; they are orientation points, not a
volume forecast or a full sensitivity model.

The result is most sensitive to whether coverage and the four path rates hold in production,
whether fallback and clarification truly require only the assumed work, whether compensation
outcomes improve, and whether released capacity is realizable. Carrier recovery, CSAT, resolution
time, consistency, auditability, fraud, and retention remain outside the monetary result.

## Appendix E — Claims discipline

- This is not a factual ROI estimate and does not claim that the prototype creates savings.
- A positive modeled result is conditional on synthetic assumptions. It is not causal evidence.
- Exact arithmetic supports auditability; it does not reduce uncertainty in the synthetic inputs or
  make the rounded portfolio outputs precise forecasts.
- Technical evaluation success does not establish production automation, labor value,
  compensation improvement, customer benefit, or business value.
- Automation must not be equated with labor savings; residual work, oversight, review,
  clarification, fallback, and recovery must be measured.
- Released support capacity must not be called headcount savings without evidence of how the
  customer realizes it.
- Carrier recovery must remain $0 until defensible customer evidence supports a separately costed
  recovery value.
- Model/tool costs and fixed implementation and maintenance costs must remain in the economics,
  including retries and failed attempts when measured.
- Average inputs can conceal important variation. A real analysis should retain distributions or
  relevant segments and compare pilot outcomes with an appropriate baseline.
