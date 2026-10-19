# GCP execution evidence

Đánh giá riêng RFM/lifecycle/CLV/persona/affinity trên cùng cohort full-data,
bao gồm AP/AUC/Lift10/Capture10 và độ ổn định theo tháng, nằm trong
[báo cáo thống nhất v2](UNIFIED_EVALUATION.md). Các bảng cloud-run bên dưới
giữ nguyên số đo của ranker đã chạy trên GCP.

Recorded on 18/10/2026 (Vietnam time).

Image source: `9879bc55c1149095e4842cad6dcacdf38b9015a0`.
Image digest: `sha256:c702d189741c197ab2fa4ae331339ae88956e59a894a3e9bb70a4c4648b203f7`.
Cloud Build: `d145840c-5ff0-4f37-ae16-a06dfd4a1b97` (success).

## Sample

Job: `5535594721440694272`, **JOB_STATE_SUCCEEDED**.
Created: 2026-10-17T19:46:40.316482Z; started: 2026-10-17T19:57:19Z; ended: 2026-10-17T19:58:53Z (UTC).
Worker: n1-standard-8, one replica, 200 GB boot SSD.
Output: `gs://uit-thien-santander-ds/event-v2/9879bc5/sample/runs/cloud_sample_10k_20261017T195709548634Z_829ea764`.
Observed input snapshots across 17 months: **143,126**.
Feature construction: 30.04 seconds; sampled peak process RSS 435.8 MiB.

| Variant | Val MAP all | Val MAP buyers | Test MAP all | Test MAP buyers | Recall buyers | Eligible val/test | Seconds | Peak RSS MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 0.023624 | 0.813876 | 0.025969 | 0.840532 | 0.984444 | 9,681/9,710 | 3.00 | 429.5 |
| baseline_plus_rfm | 0.023739 | 0.817839 | 0.026081 | 0.844155 | 0.989444 | 9,681/9,710 | 3.35 | 429.5 |
| baseline_plus_clv | 0.023790 | 0.819598 | 0.025956 | 0.840114 | 0.986111 | 9,681/9,710 | 3.20 | 419.8 |
| baseline_plus_persona | 0.023675 | 0.815656 | 0.026155 | 0.846541 | 0.984444 | 9,681/9,710 | 3.03 | 419.9 |
| baseline_plus_lifecycle | 0.023624 | 0.813876 | 0.025969 | 0.840532 | 0.984444 | 9,681/9,710 | 3.08 | 419.0 |
| baseline_plus_affinity | 0.023244 | 0.800791 | 0.025111 | 0.812765 | 0.991111 | 9,681/9,710 | 4.16 | 415.8 |
| all_enabled | 0.023257 | 0.801237 | 0.025529 | 0.826298 | 0.990556 | 9,681/9,710 | 4.22 | 415.3 |

Forecast: 9,758 predictions, 0 unverified fallbacks, **0 owned-product violations**.
Evaluation model labels end 2016-03; forecast refit labels end 2016-05. CLV label availability ≤ each origin was checked from every audit record.

Runtime versions:

```json
{
  "numpy": "2.4.6",
  "pandas": "2.3.3",
  "pyarrow": "26.0.0",
  "scikit-learn": "1.9.1",
  "psutil": "7.2.2",
  "python": "3.11.17",
  "xgboost": "3.2.0"
}
```

Eligible label-pair coverage relative to all origin snapshots: validation 9,681/9,699 (99.8144%); test 9,710/9,735 (99.7432%). This denominator includes origin rows later excluded for absence or incomplete product flags.
Forecast complete-snapshot coverage: 9,758/9,758 May snapshots (100.0000%).

## Full

Job: `8379336411148451840`, **JOB_STATE_SUCCEEDED**.
Created: 2026-10-17T20:00:44.698506Z; started: 2026-10-17T20:02:21Z; ended: 2026-10-17T20:20:36Z (UTC).
Worker: n1-standard-8, one replica, 200 GB boot SSD.
Output: `gs://uit-thien-santander-ds/event-v2/9879bc5/full/runs/full_validation_selected_20261017T200237620339Z_9e8e42ca`.
Observed input snapshots across 17 months: **13,647,309**.
Feature construction: 466.01 seconds; sampled peak process RSS 3247.2 MiB.

| Variant | Val MAP all | Val MAP buyers | Test MAP all | Test MAP buyers | Recall buyers | Eligible val/test | Seconds | Peak RSS MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| full_validation_selected | 0.023887 | 0.825024 | 0.025341 | 0.842417 | 0.987901 | 923,414/926,663 | 133.41 | 3355.3 |

Forecast: 931,453 predictions, 0 unverified fallbacks, **0 owned-product violations**.
Evaluation model labels end 2016-03; forecast refit labels end 2016-05. CLV label availability ≤ each origin was checked from every audit record.

Runtime versions:

```json
{
  "numpy": "2.4.6",
  "pandas": "2.3.3",
  "pyarrow": "26.0.0",
  "scikit-learn": "1.9.1",
  "psutil": "7.2.2",
  "python": "3.11.17",
  "xgboost": "3.2.0"
}
```

Eligible label-pair coverage relative to all origin snapshots: validation 923,414/925,076 (99.8203%); test 926,663/928,274 (99.8265%). This denominator includes origin rows later excluded for absence or incomplete product flags.
Forecast complete-snapshot coverage: 931,453/931,453 May snapshots (100.0000%).

Full flags were frozen as baseline+CLV from the local sample validation; full test metrics did not change the choice. Caps, seed, split and model parameters match the sample settings. Full uses worker-local SSD for cache/features, then publishes the completed run to GCS. Both published.json and Vertex success confirm publication finished. Raw cache is temporary and not published.

These are temporal development backtests on months already used during notebook research. Results are not an untouched holdout or a Kaggle leaderboard score. RSS is sampled process memory, not allocated VM memory or a billing estimate. Customer-level artifacts and models remain private in GCS; only aggregates are in Git.
