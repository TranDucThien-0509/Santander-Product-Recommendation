# Notebook mapping and point-in-time availability

Integration base: `Santander-Product-Recommendation/main` at
`5e791bda2958fa395f69d342aeaa83a28ad78bcb`, fetched on 18/10/2026 (Vietnam time).
The original root `pipeline/`, Dockerfile, dependencies and CI are preserved.
Notebook references below are the source-only files in
[`Santander-Recommendation` at `d6ab82d`](https://github.com/TranDucThien-0509/Santander-Recommendation/tree/d6ab82d9f0362c0e2c8cae72d054848a4c8217a0/notebooks).
Hashes identify the exact local files inspected, including their metadata.

| Notebook | SHA256 |
|---|---|
| `01_rfm_features.ipynb` | `b1c1866e354104412c487bb15139bc26ac2e85ce5f20fb272620c24e3623b4b7` |
| `05_lifecycle.ipynb` | `f5129095b6ad2d087d83e6158651417dc18b522f7a421ef781db2665df72beaf` |
| `07_clv_proxy.ipynb` | `66e0b3313b3f701c88208782eca12ae58fb84d97f23e68f870f20034ffbb8068` |
| `10_persona_tree.ipynb` | `030a0c3cfd66f9b8e2dde38fcc8ebe5e2e08dbf03f84a8270c4cb3464bb0d1f9` |
| `06_affinity.ipynb` | `0ace073cb40783dad607b9a7adb4ded54ed0f0fb37599521e121fe34dc0bab60` |

## Implemented definitions

| Group / version | Source and columns | Formula, units and fallback | Availability |
|---|---|---|---|
| RFM / `notebook01-group-points-baseline-v2` | Notebook 01 `build_rfm` and `iter_all_month_features`; `R`, `F_event_months`, `M_group_points` | R counts months since last verified acquisition; F counts months with one or more acquisitions. Missing R means no observed event. M = 100 × historical response rate of the exact 24-bit portfolio; unseen portfolios use the pooled historical rate. No historical pairs or incomplete current ownership → M missing. Values are rounded to 10 decimals, as in the export. | A pair s→s+1 enters history only when s+1≤t. Current t is never labeled with t+1 while computing its features. |
| RFM diagnostics | `M_group_history_n`, `M_group_uses_baseline`, `rfm_m_missing`, `score_history_available`, `historical_baseline` | Support counts eligible customer-month pairs. Fallback is distinct from missing; a supported portfolio with zero response has score 0, not NaN. First five RFM fields plus support/fallback/missing indicators enter ranker when enabled. | Same history as M. Diagnostics retain no customer-level future outcome. |
| Persona / `notebook10-tree6-nov2015-fixed-rules-v1` | Notebook 10 `expected_persona`, `load`; `persona_id`, `persona_unavailable` | P1: F=0,n≤2; P2: F=0,n≥3; P3: F=1; P4: F≥2,n≤1; P5: F≥2,2≤n≤4; P6: F≥2,n≥5. Requires current complete ownership, ≥3 valid pairs, finite integer F≥0, n in 0…24, valid R≥0 when F>0. Otherwise UNKNOWN. | Source tree uses origin 2015-11 with 2015-12 labels; rules are available at end 2015-12, never November. Config records fit origin, label month and availability month and rejects inconsistent dates. |
| Lifecycle / `lifecycle-v3-presence-gap6` | Notebook 05 presence/gap loop; `lifecycle`, `missing_months`, `absence_before_return` | Observed → Active; bank age 0…<2 → New; return after ≥6 absent months overrides with Win-back. Known absent → At-risk; absence ≥6 → Churned. Current missing_months=0; prior gap is a separate feature. | States use only customers known through t and their presence/date at t. All-known table in `lifecycle/YYYY-MM.parquet`; ranker reads only complete observed snapshots. |
| CLV / `baseline-numeric-poisson-1m-v1` | Separate experimental model; `predicted_acquisitions_1m`, `clv_unavailable` | HistGradientBoostingRegressor with Poisson loss, baseline numeric inputs, counts of additional products over one month, seed/config-controlled per-origin sampling. Uses all eligible pairs including label 0. Insufficient rows or all-zero outcomes → historical mean; no outcomes → NaN. | Refitted independently for each t using labels ending ≤t. Audit lists actual origins used, max label month, row count and method. Never backfilled from a May model. |
| Affinity / `temporal-ownership-smoothed-24-v1` | Separate temporal heuristic, not the full notebook 06 model; 24 `affinity_<product>` columns | For the configured window, conditional(i,j)=(acquisitions j after owning i + prior×population opportunity rate j)/(eligible ownership exposures i→j + prior). Score j = 0.5×mean conditional over owned i + 0.5×population rate j. Owned j gets score 0. Empty portfolio has mean term 0. | Only pairs with labels ending ≤t. Fixed order is `PRODUCTS` in `pipeline/common.py` and recorded in feature manifest. |

CLV is **not** notebook 07's `ML_RFM_stable`, and affinity is **not** asserted
to reproduce notebook 06. Their distinct versions are intentional. No monetary
CLV, BG/NBD or imported future prediction artifact is used.

Persona P1–P6 implements the six frozen notebook rules, rather than loading or
refitting a decision tree. Tests compare all 450 F=0…17 × n=0…24 combinations
and eligibility boundaries. M tests cover scale, exact support, unseen-portfolio
fallback, no-history and incomplete portfolios. Lifecycle tests cover six-month
absence and return precedence. These are independent formula/contract parity
tests on synthetic inputs; the original full-data notebooks have not been rerun.

## Feature flags and indirect information

`feature_manifest.json` records selected raw/encoded columns, product order,
feature versions, dependencies and model-fit label availability. Disabled groups
contribute no columns to the ranker. Baseline still contains current ownership,
product count and observed-pair count. Persona indirectly carries F and uses R
for eligibility. Experimental CLV uses baseline numeric columns, including
product count and observed pairs, but no direct R/F/M columns. Toggling direct
RFM therefore does not remove every piece of correlated or derived information.

## Evaluation contract

Features t; acquisition labels t+1 from consecutive complete snapshots only.
First-seen and gap returns are not verified acquisitions. Ranker training is
event-only with one label per acquired product. CLV training includes nonbuyers.
Evaluation includes all eligible buyers and nonbuyers and reports both MAP
denominators, buyer prevalence, buyer recall and recommendation coverage.
Forecast covers complete snapshots at t and masks current ownership before
top-7. Optional roster fallbacks are explicitly ownership-unverified.

Train origins 2015-12…2016-02, validation 2016-03, test 2016-04, forecast
2016-05. These months already informed notebook research: results are a
**temporal development backtest**, not an untouched holdout. Select using
validation. Test metrics come from `evaluation_model`; `forecast_model` may
refit using all labels ending by forecast month and cannot supply test scores.
