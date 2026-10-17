# Feature catalog v2

One row is `(customer_id, origin_month)`; customer ID is join metadata.
See [notebook mapping](NOTEBOOK_FEATURE_MAPPING.md) for source hashes,
formulas, fallbacks, versions and availability of every feature group.

| Group | Numeric input columns | Categorical input columns |
|---|---|---|
| Baseline | age, renta, antiguedad, relationship_age_months, n_products, observed_pairs, calendar_month, 24 product flags | canal_entrada, segmento, sexo, nomprov |
| RFM | R, F_event_months, M_group_points, M_group_history_n, M_group_uses_baseline, rfm_no_event, rfm_m_missing | — |
| CLV | predicted_acquisitions_1m, clv_unavailable | — |
| Persona | persona_unavailable | persona_id |
| Lifecycle | missing_months, absence_before_return | lifecycle |
| Affinity | 24 affinity_<product> columns in PRODUCTS order | — |

Baseline has 31 numeric + 4 categorical columns. All-enabled has **67 numeric +
6 categorical columns** before encoding. Actual manifests record raw/encoded
columns and indirect dependencies. Disabled groups contribute no ranker columns;
correlated baseline or derived information may remain.

- M_group_points = **100 × historical exact-portfolio response rate**. Unseen
  portfolios use the pooled historical baseline when eligible history exists.
  Missing product flags or no history → missing M. Support/fallback/missing
  indicators are separate. This is a propensity proxy, not money.
- Persona P1–P6 follows frozen notebook 10 rules. Complete current ownership,
  ≥3 valid pairs, valid F/n/R and rule availability are required.
- Lifecycle uses presence, bank relationship age and panel gaps. All-known
  tables include At-risk/Churned; ranker uses complete current snapshots.
  Current missing_months=0; absence_before_return records the prior gap.
- CLV is a separately versioned baseline-numeric Poisson count model, one-month
  horizon, including zero-count outcomes. It is not ML_RFM_stable from notebook 07.
- Affinity is a separately versioned smoothed temporal ownership heuristic,
  with an explicit window, prior and product order, not notebook 06 parity.

## Cleaning and temporal boundaries

- Consecutive complete snapshots define 0→1 acquisitions. First-seen and gap
  returns are not verified acquisitions. Every acquired product creates a ranker
  label; nonbuyers remain in evaluation and CLV training.
- Product missing stays missing; incomplete snapshots cannot verify ownership.
- Age outside 0…110, negative/nonfinite renta/antiguedad and future-month fecha_alta
  become missing. Junior customers are retained.
- Numeric median/indicators and categorical one-hot fit only on training rows.
  Unknown categories are ignored at scoring.
- R without an observed event is missing. History is left-censored. Current
  ownership and RFM are not forward-filled across absence.
- Features t use only snapshots/outcomes available by t; labels are t+1.
  evaluation_model supplies backtest metrics; forecast_model may refit on later
  already-known outcomes and is used only for forecast.
- Metadata/all-known lifecycle rows are not automatically ranker inputs.
  Only use trusted internally generated pickle artifacts with the score CLI.
