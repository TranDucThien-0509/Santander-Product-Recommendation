# Santander Product Recommendation — MLOps Pipeline & Cloud Training

[![Santander ML Pipeline CI/CD](https://github.com/TranDucThien-0509/Santander-Product-Recommendation/actions/workflows/ci.yml/badge.svg)](https://github.com/TranDucThien-0509/Santander-Product-Recommendation/actions/workflows/ci.yml)
[![Docker Image](https://img.shields.io/badge/GCP_Artifact_Registry-santander--pipeline-blue?logo=google-cloud)](https://console.cloud.google.com/artifacts)
[![Python](https://img.shields.io/badge/Python-3.11-brightgreen?logo=python)](https://python.org)

Hệ thống Machine Learning Pipeline dự đoán sản phẩm ngân hàng Santander, chuẩn hóa từ mã nguồn Jupyter Notebook ban đầu thành kiến trúc **Modular Pipeline, Offline Temporal Validation, Container hóa Docker, và Huấn luyện trên Google Cloud Platform (Vertex AI Custom Jobs)** với **CI/CD tự động qua GitHub Actions**.

---

## 1. Bảng so sánh: Trước và Sau khi nâng cấp (What Changed?)

Dưới đây là bảng tổng hợp chi tiết để người chấm, giảng viên hoặc thành viên nhóm thấy rõ sự khác biệt giữa phiên bản ban đầu và hệ thống hiện tại:

| Hạng mục | Trước khi nâng cấp (Baseline Notebook) | Hiện tại (Production-Ready MLOps V2) |
| :--- | :--- | :--- |
| **Cấu trúc mã nguồn** | 1 file `.ipynb` dài 61 cell, dùng biến toàn cục chung trong RAM, lỗi 1 cell phải chạy lại từ đầu. | **6 Stage module hóa** (`pipeline/`), mỗi stage độc lập, đọc/ghi trung gian qua Parquet/NPY, chạy lại stage tùy ý. |
| **Đánh giá mô hình (Validation)** | **Không có validation offline** — chỉ biết điểm khi submit lên Kaggle (mù thông tin trong quá trình thử nghiệm). | **Stage `evaluate.py`**: Temporal Validation tháng 06/2015, mask sản phẩm đã sở hữu tháng 05/2015, tính **MAP@7 chuẩn Kaggle**. |
| **Kiểm thử chất lượng (QA)** | Kiểm tra thủ công bằng mắt hoặc print trong notebook. | **Bộ Smoke Test tự động (`smoke_test.py`)**: Kiểm tra Schema/Dtypes, đảm bảo ma trận features **0 NaN / 0 Inf**, và `sub.csv` đúng format top-7. |
| **Theo dõi thử nghiệm (Tracking)** | Không có log, mất thông tin khi đóng terminal hoặc kernel restart. | File **`pipeline_run_log.jsonl`** tự động lưu `run_id`, tag Git SHA, `map7_valid`, thời gian chạy, cấu hình params và hỗ trợ cập nhật điểm Kaggle sau nộp. |
| **Môi trường (Containerization)** | Cài đặt thủ công trên máy cá nhân, dễ lỗi xung đột thư viện giữa các máy. | **Docker Container hóa chuẩn hóa** (`Dockerfile`), độc lập môi trường, tích hợp sẵn trên Artifact Registry. |
| **Huấn luyện quy mô lớn (Cloud)** | Huấn luyện trên máy cá nhân dễ tràn RAM (13.6M dòng ~ 2.3GB raw). | **Vertex AI Custom Jobs (GCP)**: Chạy phân tán trên máy ảo compute serverless, train xong tự tắt máy ($0 chi phí ngầm). |
| **Tự động hóa CI/CD** | Không có CI/CD. | **GitHub Actions (`.github/workflows/ci.yml`)**: Tự động kích hoạt smoke test trên sample 10k, build container và đẩy image lên GCP khi merge vào `main`. |

---

## 2. Cách xem chi tiết các thay đổi (How to view changes)

Mọi người có thể xem toàn bộ lịch sử và từng dòng code thay đổi qua các cách sau:

### Cách 1: Xem trực quan trên GitHub Web
1. **Xem Commit Diff chi tiết**: Truy cập tab [Commits](https://github.com/TranDucThien-0509/Santander-Product-Recommendation/commits/main) trên repository. Click vào commit mới nhất để xem side-by-side diff (dòng xanh là thêm mới, dòng đỏ là code cũ đã thay thế).
2. **Xem tiến trình CI/CD**: Truy cập tab [GitHub Actions](https://github.com/TranDucThien-0509/Santander-Product-Recommendation/actions) để xem log chạy thực tế của các bài test tự động.

### Cách 2: Xem bằng Git CLI tại máy local
```powershell
# 1. Xem danh sách commit và các file thay đổi
git log -n 3 --stat

# 2. So sánh chi tiết từng dòng code giữa commit hiện tại và commit ban đầu
git diff 92ea02e HEAD

# 3. Xem danh sách các file đã được thêm mới trong phiên bản V2
git diff 92ea02e HEAD --name-status
```

---

## 3. Cấu trúc thư mục dự án

```
├── .github/workflows/
│   └── ci.yml                     # Pipeline GitHub Actions CI/CD (Smoke test + Docker build)
├── data/
│   └── raw/
│       ├── train_sample_10k.csv   # Dữ liệu mẫu 10k dòng để test nhanh & chạy CI
│       └── test_sample_5k.csv     # Dữ liệu mẫu 5k dòng khách test
├── pipeline/
│   ├── config.py                  # Cấu hình đường dẫn, hằng số & biến môi trường
│   ├── tracking.py                # Context manager ghi log JSONL tiến trình & metrics
│   ├── ingest.py                  # Stage 1: Giải nén + đọc CSV -> Parquet
│   ├── preprocess.py              # Stage 2: Xử lý Missing values, ngoại lai & Label Encode
│   ├── feature_engineering.py     # Stage 3: Tạo đặc trưng 'days', lag hành vi, tách Valid 20% & 5-month lag
│   ├── train.py                   # Stage 4: Huấn luyện XGBoost đa lớp (multi:softprob)
│   ├── predict.py                 # Stage 5: Dự đoán xác suất, mask sản phẩm đã có -> sub.csv
│   ├── evaluate.py                # Stage 6: Đánh giá MAP@7 offline, phân biệt map7_all và map7_buyers
│   ├── smoke_test.py              # Bộ kiểm thử chất lượng không cần nhãn (3 tests)
│   └── run_pipeline.py            # Script chạy tuần tự pipeline (hỗ trợ lọc stage)
├── notebooks/                     # Các notebook phân tích EDA & dọn dẹp dữ liệu
├── Dockerfile                     # Docker image đóng gói môi trường pipeline
├── GCP_DEPLOYMENT.md              # Sổ tay hướng dẫn vận hành GCP Vertex AI từ A-Z
├── custom_job_full.yaml           # Cấu hình Vertex AI chạy full dữ liệu
├── custom_job_fe_train.yaml       # Cấu hình Vertex AI chạy từ Feature Engineering
├── custom_job_test.yaml           # Cấu hình Vertex AI chạy thử nghiệm trên sample 10k
└── requirements.txt               # Danh sách dependencies
```

---

## 4. Hướng dẫn chạy nhanh Local

### A. Chạy toàn bộ Pipeline (Sample mode 10k)
```powershell
$env:SANTANDER_SAMPLE_ROWS="10000"
python pipeline/run_pipeline.py
```

### B. Chỉ chạy các stage mong muốn
Ví dụ chỉ muốn chạy từ feature engineering đến evaluate:
```powershell
$env:SANTANDER_STAGES="feature_engineering,train,predict,evaluate"
python pipeline/run_pipeline.py
```

### C. Chạy bộ kiểm thử Smoke Test
```powershell
python pipeline/smoke_test.py
```

### D. Cập nhật điểm Kaggle sau khi submit
```powershell
python pipeline/evaluate.py --update-kaggle 0.0295 --run-id latest
```

---

## 5. Hướng dẫn chạy trên Google Cloud Platform (GCP)
Xem tài liệu hướng dẫn chi tiết tại [GCP_DEPLOYMENT.md](file:///c:/Users/Admin/Documents/VSF/GCP_DEPLOYMENT.md).
