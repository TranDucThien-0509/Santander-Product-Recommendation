# Integration validation

Date: 18/10/2026, Vietnam time. Base main:
`5e791bda2958fa395f69d342aeaa83a28ad78bcb`. Branch: `feature/event-pipeline-v2`.

| Check | Evidence / current status |
|---|---|
| Existing implementation preserved | Root pipeline/, Dockerfile, requirements.txt and ci.yml unchanged against integration base |
| Local tests | 13 tests passed on Python 3.12, including synthetic end-to-end XGBoost and seven variants |
| Notebook contracts | 450-point persona rule grid; completeness/F/R/history/availability boundaries; M points/support/fallback/NaN; all-known lifecycle states and return precedence |
| Temporal/target contracts | Future mutation invariance including CLV/affinity; zero outcomes retained for CLV; first-seen/gap excluded; multiple-product event labels; ownership mask and both MAP denominators |
| Config/manifest | Invalid flags, split/date/numeric settings rejected; disabled columns absent from actual fitted models; versions, dependencies and persona availability recorded |
| Reproducible customer sample | 10,000 fixed IDs, 143,126 snapshots, all 17 months retained; sampling order/chunk-size invariance tested |
| Local real ablation | B0–B6 completed on identical eligible cohorts; metrics/resources and sanitized config in SAMPLE_BENCHMARK.md |
| Validation selection | baseline_plus_clv chosen from validation only; separate selected run reproduced metrics and produced 9,758 forecasts, 0 ownership violations, 0 fallbacks |
| Linux v2 tests | Passed in runs 39063692400 (source 9879bc5) and 39064016082 (PR merge check for ca49683) |
| Docker / Cloud Build | Image built and pushed successfully: build d145840c-5ff0-4f37-ae16-a06dfd4a1b97, source commit 9879bc5, immutable digest listed below |
| Legacy CI | Smoke test and Docker build passed, including run 39064016104 for the PR; main-only publish correctly skipped |
| Container runtime | Docker CLI import smoke passed in run 39064016082, in addition to image build |
| Vertex sample | Job 5535594721440694272 SUCCEEDED; 17-month sample, all seven variants, 9,758 forecasts, 0 fallbacks/ownership violations. Feature build 30.04s, sampled peak RSS 435.85 MiB |
| Vertex full | Job 8379336411148451840 SUCCEEDED on all 13,647,309 input snapshots; completed.json and published.json verified, 931,453 forecasts and 0 ownership violations. Baseline+CLV frozen from sample validation; one n1-standard-8 / 200GB SSD / 7200s timeout |

## Run tests

From `experiments/event_pipeline_v2/`:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m unittest discover -s tests -v
```

Raw data, feature Parquet, models and per-customer predictions stay in ignored
local directories or private GCS. Config templates contain placeholders only;
root `*.json` ignore has one explicit exception for v2 configs/default.json.
The build upload allowlist contains only Python source, requirements, Dockerfile
and default config (15 files / 53 KiB for the first cloud build).

Cloud image: `us-central1-docker.pkg.dev/santander-ds/santander-repo/santander-event:9879bc5`.
Digest: `sha256:c702d189741c197ab2fa4ae331339ae88956e59a894a3e9bb70a4c4648b203f7`.
Sample output prefix: `gs://uit-thien-santander-ds/event-v2/9879bc5/sample/`.
Sample run: `cloud_sample_10k_20261017T195709548634Z_829ea764`.
Sample execution start/end: 2026-10-17 19:57:19Z → 19:58:53Z (UTC), after cold framework provisioning.
Full output prefix: `gs://uit-thien-santander-ds/event-v2/9879bc5/full/`.
Full run: `full_validation_selected_20261017T200237620339Z_9e8e42ca`.
Full execution start/end: 2026-10-17 20:02:21Z → 20:20:36Z (UTC).
See [CLOUD_RUNS.md](CLOUD_RUNS.md) for actual aggregate cloud metrics, runtime
versions, eligible-pair coverage and immutable run locations.
Job launch alone is not evidence of successful training; final status is recorded
after checking both the Vertex state and completed.json.

Notebook parity here means independent formula/rule checks with source hashes,
not a full rerun of historical notebooks or proof that experimental CLV/affinity
matches their selected notebook models. Panel absence is not confirmed bank
churn. Forecast fallbacks for an optional roster cannot verify ownership.

### Local selected run

- Val MAP@7_all: 0.02375131783250779; MAP@7_buyers: 0.8182793876744054.
- Test MAP@7_all: 0.025884213623657497; MAP@7_buyers: 0.8377857142857142.
- Test eligible: 9,710; buyers: 300; recall@7_buyers: 0.9861111111111113.
- Forecast: 9,758 complete current snapshots, no owned-product violation.
- These research months form a temporal development backtest. The sample
  result does not establish superiority on full data or an untouched holdout.

### Cloud sample replication

The same fixed-ID sample completed on Vertex. Baseline+CLV also has the highest
validation MAP@7_all among the cloud variants (0.02378960); its test MAP@7_all is
0.02595614. The locked full flags remain baseline+CLV; test did not choose them.
Cloud image uses Python 3.11.17 / numpy 2.4.6 / XGBoost 3.2.0, while local uses
Python 3.12 / numpy 2.5.4 / XGBoost 3.4.1. Small metric differences across these
environments are recorded rather than asserted as exact numerical parity.
The immutable cloud image digest fixes the runtime used by both cloud jobs.

### Full run

- All 13,647,309 snapshots across 17 months processed, confirmed from observed
  lifecycle state counts. All origin audits satisfy CLV max label month ≤ origin.
- Validation: 923,414 eligible pairs / 26,736 buyers; MAP@7_all 0.023887266372912032.
- Test: 926,663 eligible pairs / 27,875 buyers; MAP@7_all 0.025340798796240526;
  MAP@7_buyers 0.8424172425083636; recall@7_buyers 0.9879013452914798.
- Forecast: 931,453 current complete snapshots, no fallbacks, no owned-product
  violations. No future June labels are required or claimed.
- Feature build: 466.01 seconds / 3247.18 MiB sampled process RSS peak. Ranker
  fit plus validation/test scoring: 133.41 seconds / 3355.35 MiB peak. These stage
  measurements exclude ingest, final forecast refit and publication; job times
  include the whole container execution/teardown.
- Evaluation model labels end March; separate forecast refit labels end May.
  Full flags stayed baseline+CLV; full test metrics did not select or tune them.
- Artifact publication finished before published.json was written and before
  Vertex reported success. Models, features and customer predictions stay in GCS.

## Plan completion

- [x] Isolated branch/scaffold from the fetched main SHA; existing root pipeline preserved.
- [x] Default config tracked; local configs/data/artifacts ignored and excluded from image.
- [x] M scale/fallback and persona eligibility/provenance audited; lifecycle states exported.
- [x] CLV/affinity separately versioned, fitted per origin with availability audits.
- [x] Flags/manifests, event-only ranker, all-eligible metrics and ownership contracts tested.
- [x] Synthetic/parity tests, original/new CI and Docker/runtime checks pass.
- [x] Same-customer sample B0–B6 measured; validation selection frozen and forecast rerun.
- [x] Dedicated immutable image published; Vertex sample and full succeeded with audits.
- [x] Runbooks, aggregate evidence and PR prepared for main review.
