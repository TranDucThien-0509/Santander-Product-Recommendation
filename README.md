# Santander Product Recommendation — Pipeline MLOps trên GCP

[![Santander ML Pipeline CI/CD](https://github.com/TranDucThien-0509/Santander-Product-Recommendation/actions/workflows/ci.yml/badge.svg)](https://github.com/TranDucThien-0509/Santander-Product-Recommendation/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11-brightgreen?logo=python)](https://python.org)

Hệ thống gợi ý sản phẩm tài chính cho bài toán **Santander Product Recommendation (Kaggle)**: từ EDA trên notebook, module hóa thành **pipeline 6 stage**, kiểm thử tự động (smoke test), đánh giá offline bằng **MAP@7**, đóng gói **Docker**, CI/CD bằng **GitHub Actions** và chạy job trên **Vertex AI Custom Jobs** (GCP).

> **Trạng thái:** pipeline đã được xác thực trên dữ liệu mẫu 10k dòng (local, Docker, Vertex AI). **Chạy full 13.6M dòng trên cloud chưa thực hiện** — xem [mục 7](#7-hạn-chế--hướng-phát-triển).

---

## 1. Bài toán

- **Mục tiêu**: dựa trên lịch sử giao dịch từ 01/2015 đến 05/2016 của ngân hàng Santander (Tây Ban Nha), dự đoán các **sản phẩm mới** mỗi khách hàng sẽ mua thêm vào tháng **06/2016**.
- **Dữ liệu**: hơn 13.6 triệu dòng (~2.3 GB CSV), 24 sản phẩm tài chính cùng thông tin nhân khẩu học và hành vi khách hàng.
- **Thách thức**:
  1. Dữ liệu lớn, dễ tràn RAM trên máy cá nhân.
  2. Chỉ được đề xuất sản phẩm khách **chưa sở hữu** ở tháng liền trước (masking).
  3. Đánh giá bằng **MAP@7** (Mean Average Precision tại cut-off 7).

---

## 2. Cấu trúc mã nguồn

```
├── notebooks/                          # EDA & R&D
│   ├── 01_eda_before_cleaning.ipynb
│   ├── 02_cleaning.ipynb
│   ├── 03_eda_after_cleaning.ipynb
│   └── 04_feature_engineering.ipynb
├── pipeline/                           # Pipeline production (6 stage)
│   ├── config.py                       # Đường dẫn, hằng số, biến môi trường
│   ├── tracking.py                     # Ghi log JSONL cho từng stage
│   ├── ingest.py                       # Stage 1
│   ├── preprocess.py                   # Stage 2
│   ├── feature_engineering.py          # Stage 3
│   ├── train.py                        # Stage 4
│   ├── predict.py                      # Stage 5
│   ├── evaluate.py                     # Stage 6
│   ├── smoke_test.py                   # Kiểm thử chất lượng không cần nhãn
│   └── run_pipeline.py                 # Điều phối chạy toàn bộ / chọn lọc stage
├── .github/workflows/ci.yml            # CI/CD (GitHub Actions)
├── Dockerfile
├── custom_job_test.yaml                # Vertex AI: sample 10k dòng
├── custom_job_fe_train.yaml            # Vertex AI: từ feature engineering trở đi
├── custom_job_full.yaml                # Vertex AI: full 13.6M dòng
├── GCP_DEPLOYMENT.md                   # Sổ tay vận hành GCP chi tiết
└── requirements.txt
```

---

## 3. Notebook nghiên cứu (`notebooks/`)

| Notebook | Nội dung |
|---|---|
| `01_eda_before_cleaning` | Thống kê missing values theo cột (`renta`, `age`, `antiguedad`, `indrel_1mes`...), độ mất cân bằng giữa 24 sản phẩm. |
| `02_cleaning` | Điền khuyết `renta` theo trung vị từng tỉnh (`cod_prov`), xử lý tuổi bất thường, chuẩn hóa biến phân loại. |
| `03_eda_after_cleaning` | Tương quan nhân khẩu học – sở hữu sản phẩm, xu hướng mua theo tháng (tính thời vụ). |
| `04_feature_engineering` | Thử nghiệm đặc trưng `days`, cờ thay đổi trạng thái, lag features 5 tháng. |

---

## 4. Pipeline production (`pipeline/`)

Các stage là script Python độc lập, trao đổi dữ liệu qua **Parquet** và **NumPy (`.npy`)** trong `artifacts/`, nên có thể chạy trọn gói hoặc chọn lọc từng stage (biến `SANTANDER_STAGES`).

```
[1 Ingest] → [2 Preprocess] → [3 Feature Eng.] → [4 Train] → [5 Predict] → [6 Evaluate]
                                                                                 ↑
                                                                        [Smoke Test]
```

| Stage | Vai trò |
|---|---|
| **1. Ingest** | Đọc CSV (local hoặc GCS), lưu sang Parquet để giảm dung lượng và tăng tốc I/O. |
| **2. Preprocess** | Làm sạch, `LabelEncoder` cho biến phân loại (lưu `feature_label_encoders.pkl`). Trên sample 10k giảm 44.5% RAM. |
| **3. Feature Engineering** | Đặc trưng `days = fecha_dato - fecha_alta`, cờ thay đổi hành vi (`segmento_changed`, `ind_actividad_cliente_changed`, `tiprel_1mes_changed`), nhãn "mua mới" tháng 06/2015 so với 05/2015, **tách 20% khách hàng làm tập validation** (`val_ground_truth.json`), lag features 5 tháng cho 24 sản phẩm. |
| **4. Train** | XGBoost đa lớp (`multi:softprob`), lưu `xgb_model.pkl` và `target_encoder.pkl`. |
| **5. Predict** | Dự đoán xác suất trên tập test, mask sản phẩm đã sở hữu ở snapshot 05/2016, lấy top-7, xuất `sub.csv` đúng định dạng Kaggle. |
| **6. Evaluate** | MAP@7 offline trên tập validation (mask theo snapshot 05/2015, xếp hạng vector hóa, chỉ đọc các cột cần thiết từ Parquet). Ghi kết quả vào `pipeline_run_log.jsonl`. |

### Metric đánh giá

| Tên trong log | Ý nghĩa |
|---|---|
| `map7_valid` | MAP@7 chia cho **toàn bộ** khách validation (khách không mua mới có AP = 0) — cách tính để so sánh với điểm Kaggle. |
| `map7_valid_buyers` | Chỉ tính trên khách có mua mới; số thường cao hơn nhiều, **không** so sánh với Kaggle. |
| `kaggle_public` | Điểm Public Leaderboard, cập nhật sau khi nộp bài. |

Mỗi run ghi kèm `run_id`, `image_tag`, `n_val_customers`, `n_val_buyers`, `n_empty_pred` và `cost_usd` (nếu có). Cập nhật điểm Kaggle mà không chạy lại pipeline:

```powershell
python pipeline/evaluate.py --update-kaggle 0.0295 --run-id latest
```

### Smoke test (`smoke_test.py`)

1. **Schema & dtype**: đủ 22 cột nhân khẩu học, 24 cột sản phẩm, khóa (`ncodpers`, `fecha_dato`) không null.
2. **Feature sạch**: `X_train`, `X_val` là ma trận 2D, 0 NaN, 0 Inf.
3. **Định dạng `sub.csv`**: header chuẩn, đủ số khách test, không trùng `ncodpers`, mỗi khách đúng 7 sản phẩm không lặp.

---

## 5. Chạy trên Google Cloud Platform

```
[GitHub] → [GitHub Actions CI/CD] → [Artifact Registry: santander-pipeline]
                                                   │
                                                   ▼
[Cloud Storage (gs://)] ◄── mount /gcs (FUSE) ──► [Vertex AI Custom Job — e2-standard-8]
  raw/  train_ver2.csv, test_ver2.csv                 chạy container, xong tự hủy máy
  <work_dir>/  artifacts, sub.csv, log
```

- **Storage**: bucket `gs://uit-thien-santander-ds/`, dữ liệu gốc ở `raw/`. Container đọc/ghi qua **Cloud Storage FUSE** (`/gcs/...`), kết quả tự đồng bộ về bucket.
- **Image**: `us-central1-docker.pkg.dev/santander-ds/santander-repo/santander-pipeline` (base `python:3.11-slim`; `pip install` đặt trước `COPY` để tận dụng layer cache).
- **Compute**: Vertex AI Custom Job trên `e2-standard-8` (8 vCPU, 32 GB RAM), chỉ tính tiền khi job chạy.
- **CI/CD** (`ci.yml`): chạy pipeline trên sample 10k, chạy `smoke_test.py`, và khi merge vào `main` thì build + push image lên Artifact Registry.

Chi tiết cấu hình IAM, lệnh vận hành và quy trình cập nhật image: xem [GCP_DEPLOYMENT.md](./GCP_DEPLOYMENT.md).

---

## 6. Hướng dẫn chạy

### A. Local (sample 10k dòng)

```powershell
.\.venv\Scripts\Activate.ps1

$env:SANTANDER_SAMPLE_ROWS="10000"
python pipeline/run_pipeline.py      # toàn bộ 6 stage
python pipeline/smoke_test.py        # kiểm thử chất lượng
python pipeline/evaluate.py          # chạy riêng stage evaluate
```

### B. Vertex AI

```powershell
gcloud auth login
gcloud config set project santander-ds

# Kiểm thử nhanh trên sample 10k
gcloud ai custom-jobs create --region=us-central1 --project=santander-ds `
    --display-name="santander-test-run" --config=custom_job_test.yaml

# Theo dõi log
gcloud ai custom-jobs stream-logs <JOB_ID> --region=us-central1 --project=santander-ds

# Tải kết quả về máy (đường dẫn theo SANTANDER_WORK_DIR trong YAML)
gcloud storage cp gs://uit-thien-santander-ds/test_run/sub.csv ./sub.csv
```

Job full (`custom_job_full.yaml`) ghi kết quả vào `full_run/`.

---

## 7. Kết quả & trạng thái

### Đã xác thực (sample 10k dòng)

| Môi trường | Kết quả |
|---|---|
| Local | Hoàn tất 6 stage, tổng ~5 giây (stage 1–5 đo được 5.1 giây). |
| Docker local | Chạy đủ các stage, không lỗi dependency hoặc đường dẫn. |
| Vertex AI Custom Job | `JOB_STATE_SUCCEEDED`, ~30 giây compute, máy tự hủy sau khi xong. |
| Chạy chọn lọc stage trên Vertex | Feature engineering 3.4 giây + train 1.6 giây, không cần chạy lại toàn bộ. |

### Kết quả mô hình

| Chỉ số | Giá trị |
|---|---|
| Điểm Kaggle Public | ≈ 0.029 (điểm cao nhất cuộc thi: 0.031) |
| `map7_valid` (full run) | _chưa có — chờ full run_ |
| So sánh với baseline (sản phẩm phổ biến theo segment) | _chưa có_ |
| Thời gian / RAM / chi phí full run trên Vertex | _chưa có_ |

> Số MAP@7 của sample 10k chỉ tính trên vài chục khách hàng nên không đại diện; không dùng để đánh giá mô hình.

---

## 8. Hạn chế & hướng phát triển

**Hạn chế hiện tại**
- **Chưa chạy full 13.6M dòng trên Vertex AI**; chưa có số đo thời gian, RAM, chi phí thật.
- Mô hình huấn luyện trên nhãn tháng 06/2015 (cùng mùa với tháng test 06/2016), chưa dùng toàn bộ 2015–2016.
- Tập validation là tách 20% khách hàng trong cùng tháng, không phải validation theo thời gian.
- Image đang dùng tag `:latest`; kết quả lưu vào thư mục thử nghiệm/`full_run` chứ chưa version hóa theo `runs/<run_id>/`.
- Tracking mới ở mức file JSONL; chưa có experiment tracking, model registry, serving hay monitoring.

**Lộ trình**
1. Chạy thử 1M dòng để đo scaling, rồi chạy full trên Vertex và ghi số liệu thật.
2. Tag image theo git SHA, version hóa output theo `runs/<run_id>/`, đưa config ra file YAML.
3. Experiment tracking (MLflow hoặc Vertex AI Experiments) và model registry.
4. Serving bằng FastAPI trên Cloud Run, đo latency.
5. Vertex AI Pipelines / Cloud Scheduler để retrain định kỳ; monitoring data drift (PSI).
6. Service account riêng với quyền tối thiểu thay cho Compute default service account.
