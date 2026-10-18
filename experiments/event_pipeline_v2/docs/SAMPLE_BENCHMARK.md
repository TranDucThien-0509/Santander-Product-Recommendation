# Santander sample ablation

Cloud replication and the validation-selected full run are recorded separately
in [CLOUD_RUNS.md](CLOUD_RUNS.md), with their actual runtime versions and metrics.

Measured on 18/10/2026 (Vietnam time); temporal development backtest.

Fixed-ID sample: **10,000 customers, 143,126 snapshots**, all 17 months retained, SplitMix64 smallest hashes, seed 42. The sample is drawn across the full ID population, including late entrants.

Source: `gs://uit-thien-santander-ds/raw/train_ver2.csv`, generation `1789365289268389`.
Raw SHA256: `51f919f6cc7145b214010895b303c0e76070cc947112cb3d31d060c23cc29c98`.
Sample SHA256: `d617a26fa870bea4800fac3b48af882581a7494e095aaae42a773cf50a63d105`.
Selected ID set SHA256: `01dea50fd41ee58d385184bc6998554881eda1e198e42ae01689e886b9312910`.

## B0–B6 results

| Variant | Val MAP all | Val MAP buyers | Test MAP all | Test MAP buyers | Test Recall buyers | Eligible val/test | Seconds | Peak RSS MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 baseline | 0.023606 | 0.813283 | 0.026173 | 0.847143 | 0.984444 | 9,681/9,710 | 3.69 | 238.6 |
| B1 baseline_plus_rfm | 0.023537 | 0.810894 | 0.026087 | 0.844345 | 0.989444 | 9,681/9,710 | 4.04 | 241.8 |
| B2 baseline_plus_clv | 0.023751 | 0.818279 | 0.025884 | 0.837786 | 0.986111 | 9,681/9,710 | 4.68 | 242.8 |
| B3 baseline_plus_persona | 0.023715 | 0.817020 | 0.026150 | 0.846374 | 0.984444 | 9,681/9,710 | 5.06 | 251.2 |
| B4 baseline_plus_lifecycle | 0.023606 | 0.813283 | 0.026173 | 0.847143 | 0.984444 | 9,681/9,710 | 5.55 | 251.6 |
| B5 baseline_plus_affinity | 0.023114 | 0.796323 | 0.025076 | 0.811622 | 0.988889 | 9,681/9,710 | 7.18 | 251.2 |
| B6 all_enabled | 0.023296 | 0.802610 | 0.025515 | 0.825851 | 0.989444 | 9,681/9,710 | 6.80 | 251.9 |

All variants share sample, eligible cohort, origins, seed, caps and model parameters.
Validation buyers: 281/9,681 (2.9026%); test buyers: 300/9,710 (3.0896%).
Recommendation coverage (test): 100.0000%.
Forecast: 9,758 predictions, 0 ownership-unverified fallbacks, 0 owned-product violations.

Shared feature construction: 31.69 seconds, 304.5 MiB peak sampled process RSS.
Variant seconds include evaluation-model fit and validation/test scoring. Shared feature construction and final forecast refit are separate. RSS is process-wide sampled every 0.1s, includes native allocations and shared data, and is not incremental per-group memory. These are local Windows measurements, not cloud billing estimates.

## Validation selection

Selected **baseline_plus_clv** using highest validation MAP@7_all; ties favor fewer groups. Test metrics were not used for selection. No hyperparameter tuning was performed.
The ablation run's forecast belongs to all_enabled. A separate run using `configs/selected.local.json` creates the validation-selected forecast and retains a separate evaluation_model and forecast_model.

## Reproduce

From `experiments/event_pipeline_v2/`:

```bash
python -m pipeline.sample --source data/train_ver2.csv --out data/customer_sample/train_ver2.csv --customers 10000 --seed 42
# Save the sanitized config below as configs/config.local.json; adjust local paths.
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m pipeline.run_pipeline --config configs/config.local.json
python -m pipeline.report --run artifacts/sample-10k-seed42/runs/RUN_ID --sample-manifest data/customer_sample/train_ver2.manifest.json --out docs/SAMPLE_BENCHMARK.md --selected-config configs/selected.local.json
python -m pipeline.run_pipeline --config configs/selected.local.json
```

```json
{
  "data": {
    "train_csv_or_zip": "data/customer_sample/train_ver2.csv",
    "prediction_roster_csv_or_zip": null,
    "work_dir": "artifacts/sample-10k-seed42",
    "history_start": "2015-01",
    "forecast_month": "2016-05",
    "chunk_size": 400000,
    "rebuild_cache": false
  },
  "split": {
    "train_origins": [
      "2015-12",
      "2016-01",
      "2016-02"
    ],
    "validation_origins": [
      "2016-03"
    ],
    "test_origins": [
      "2016-04"
    ]
  },
  "feature_groups": {
    "rfm": true,
    "clv": true,
    "persona": true,
    "lifecycle": true,
    "affinity": true
  },
  "meta_models": {
    "clv_max_train_rows": 150000,
    "clv_max_iter": 80,
    "clv_min_train_rows": 1000,
    "clv_min_history_origin": "2015-03",
    "persona_rules_available_from": "2015-12",
    "persona_rules_fit_origin": "2015-11",
    "persona_rules_label_month": "2015-12",
    "affinity_window_months": 3,
    "affinity_prior": 1000.0
  },
  "model": {
    "backend": "xgboost",
    "max_train_event_rows": 500000,
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.05,
    "n_jobs": 4,
    "seed": 42
  },
  "run": {
    "name": "sample_10k_seed42",
    "refit_for_forecast": true,
    "ablation": true
  }
}
```

Runtime versions:

```json
{
  "numpy": "2.5.4",
  "pandas": "2.3.3",
  "pyarrow": "26.0.0",
  "scikit-learn": "1.9.1",
  "psutil": "7.2.2",
  "python": "3.12.14",
  "xgboost": "3.4.1"
}
```

Raw data, customer IDs, per-customer features/predictions and models are not versioned. Only aggregate results and sanitized settings are published here. Full-data notebook parity, cloud sample and full training status are tracked in VALIDATION.md.
