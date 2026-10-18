# Chạy lại Track A

## Hai loại kết quả trong repo

1. `reports/evidence/` và `docs/02_benchmarks.md`: aggregate trích từ output nghiên cứu gốc. `reports/evidence_manifest.json` giữ provenance. Notebooks 00–15 giữ source, đã bỏ customer-level outputs; các đường dẫn Kaggle cần chỉnh trước khi chạy. Xem limitations.md cho vấn đề đã audit của notebook 00 và cohort của mỗi benchmark.
2. `reports/sample_10k/`: bổ sung được chạy lại từ sample 10.000 ID cố định, giữ 17 tháng. Đây là kết quả sample, không thay thế full-cloud recommendation benchmark hay benchmark gốc.

## Tạo source run v2

Từ `experiments/event_pipeline_v2/`, cài Python 3.11/3.12 và dependencies:

```bash
python -m pip install -r requirements-track-a.txt
python -m pipeline.run_pipeline --config configs/config.local.json
```

Config local cần raw Kaggle CSV/ZIP được phép sử dụng, work_dir local; bật tất cả feature groups để persona clustering có CLV và affinity. Cấu hình seed/splits theo configs/default.json. Muốn tạo mẫu cố định, xem README v2 và CLI `python -m pipeline.sample --help`. Không dùng sample lấy 10k **dòng đầu** để làm benchmark này.

## Chạy phần bổ sung

Từ thư mục v2, dùng **thư mục source run đã hoàn thành** và cache cùng manifest:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m track_a.run \
  --run-dir /absolute/work/runs/source-run \
  --cache-dir /absolute/work/cache \
  --out /absolute/work/track-a/new-run \
  --fit-month 2015-11 \
  --tracking-uri http://127.0.0.1:5000
```

PowerShell: đặt `$env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'` rồi chạy lệnh trên một dòng hoặc dùng backtick xuống dòng. SQLite local cũng được; `--artifact-location` chỉ đặt khi tạo experiment mới. Không dùng SQLite trên GCS FUSE. Pipeline không overwrite output directory.

Thứ tự: raw EDA → verified event export → 3 cách RFM tiering/stability → CLV 6m + SHAP → KMeans persona 5–8 cụm + stability/cards → affinity matrices/next-month benchmark → processed dataset/spec/manifest → MLflow. Experiment MLflow tên **santander-track-a**, khác experiment ranker `santander-event-v2`.

CLV 6m mặc định: source origin 2015-11, nhãn đến 2016-05; train origins 2015-03…05 với label end ≤2015-11. Không có model selection qua validation 6m. So sánh BG/NBD, BG/NBD+Gamma-Gamma, fixed gradient boosting và mean trên cùng cohort; tỷ trọng fallback ghi rõ. SHAP báo link scale và kiểm tra additive reconstruction, chỉ lưu mean absolute importance.

12m không có đủ lịch sử để supervised train/validation/test đáng tin. Không tạo metric giả hoặc tự đổi tên horizon 1m thành 6/12m.

## Storage đã chọn: GCS thay AWS S3

Chủ repo xác nhận giữ GCS. Đây là sai khác so với yêu cầu AWS S3 trong brief; xem [GCS_STORAGE.md](GCS_STORAGE.md) và receipt ở reports/sample_10k/gcs_storage_receipt.json.

Từ thư mục v2:

```bash
python ../../research/track_a/scripts/publish_gcs.py \
  --manifest /absolute/work/track-a/new-run/processed/processed_manifest.json \
  --destination gs://YOUR_BUCKET/track-a/NEW_RUN_ID \
  --apply --receipt /absolute/work/gcs_storage_receipt.json
```

Không có `--apply` thì chỉ kiểm tra local manifest/hash và in kế hoạch. Lệnh apply chỉ copy file trong manifest sang prefix mới, tải lại kiểm size/SHA256, rồi publish manifest cuối. `--if-generation-match=0` ngăn ghi đè object cũ; không đổi IAM/ACL. Google Cloud CLI dùng tài khoản đã đăng nhập, không ghi token/key vào code.

## Export S3 tùy chọn, chưa sử dụng trong dự án này

```bash
python -m track_a.storage \
  --manifest /absolute/work/track-a/new-run/processed/processed_manifest.json \
  --destination s3://YOUR_BUCKET/track-a/RUN_ID --region YOUR_REGION
```

Lệnh trên chỉ kiểm tra hash và in kế hoạch. Thêm `--apply` để thực sự upload sau khi chọn bucket/prefix. Boto3 dùng role/profile/default credential chain; không đưa access key vào repo. Chỉ các file generated được liệt kê trong manifest được upload, không tự quét raw/model/log.

Exporter S3 vẫn được giữ như tùy chọn có test client giả. Dự án hiện chọn GCS và không tuyên bố đã upload AWS. Trạng thái và bằng chứng nằm trong GCS_STORAGE.md/TRACK_A_AUDIT.md. Không tạo thêm cloud compute cho lần publish processed sample.

## Test

```bash
python -m unittest discover -s tests -v
```

Từ repo root, kiểm tra package wrap gốc:

```bash
python -m pip install -e research/track_a
python -m unittest discover -s research/track_a/tests -v
```

CI `track-a.yml` cài dependencies riêng và kiểm tra source wrap + data contracts. Pipeline/Docker/requirements cũ ở root giữ riêng. Các synthetic tests không chứng minh metric full Santander.
