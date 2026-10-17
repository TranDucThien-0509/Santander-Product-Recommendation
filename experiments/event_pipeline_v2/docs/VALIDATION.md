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
| Linux v2 tests | Passed in GitHub Actions run 39063692400 on source commit 9879bc5 |
| Docker / Cloud Build | Image built and pushed successfully: build d145840c-5ff0-4f37-ae16-a06dfd4a1b97, source commit 9879bc5, immutable digest listed below |
| Legacy CI | Existing smoke test passed; Docker build in progress at this checkpoint |
| Vertex sample | Submitted as job 5535594721440694272, one n1-standard-8 worker / 200GB disk / 1800s timeout; outcome pending |
| Vertex full | Not submitted yet; depends on successful cloud sample and resource audit |

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
