# Santander Product Recommendation — Hệ Thống MLOps Pipeline & Cloud Training

[![Santander ML Pipeline CI/CD](https://github.com/TranDucThien-0509/Santander-Product-Recommendation/actions/workflows/ci.yml/badge.svg)](https://github.com/TranDucThien-0509/Santander-Product-Recommendation/actions/workflows/ci.yml)
[![Docker Image](https://img.shields.io/badge/GCP_Artifact_Registry-santander--pipeline-blue?logo=google-cloud)](https://console.cloud.google.com/artifacts)
[![Python](https://img.shields.io/badge/Python-3.11-brightgreen?logo=python)](https://python.org)

Dự án xây dựng hệ thống gợi ý sản phẩm tài chính ngân hàng Santander (**Santander Product Recommendation - Kaggle**) theo tiêu chuẩn **MLOps**: từ giai đoạn phân tích khám phá dữ liệu (EDA) trên Notebook, module hóa thành **Pipeline 6 công đoạn**, kiểm thử tự động (**Smoke Test**), đánh giá ngoại tuyến (**Offline MAP@7**), đóng gói **Docker** và triển khai huấn luyện quy mô lớn trên **Google Cloud Platform (Vertex AI Custom Jobs)**.

---

## 1. Bài toán & Mục tiêu đồ án

- **Bài toán**: Dựa trên 1.5 năm lịch sử giao dịch (từ tháng 01/2015 đến tháng 05/2016) của ngân hàng Santander (Tây Ban Nha), dự đoán các **sản phẩm tài chính mới** mà khách hàng sẽ mua thêm vào tháng kế tiếp (**tháng 06/2016**).
- **Dữ liệu**: Hơn **13.6 triệu dòng giao dịch** (~2.3 GB CSV) gồm 24 sản phẩm tài chính (tài khoản thanh toán, thẻ tín dụng, tiền gửi tiết kiệm, vay thế chấp, chứng khoán...) cùng thông tin nhân khẩu học và hành vi khách hàng.
- **Thách thức cốt lõi**:
  1. Dữ liệu lớn dễ gây tràn RAM (Out of Memory) trên máy tính cá nhân.
  2. Chỉ được đề xuất các sản phẩm khách hàng **chưa sở hữu** ở tháng liền trước (cơ chế Masking).
  3. Đánh giá bằng thang đo xếp hạng **MAP@7** (Mean Average Precision tại cut-off 7).

---

## 2. Cấu trúc mã nguồn dự án

```
├── notebooks/                     # Phân tích khám phá (EDA) & R&D tuần tự
│   ├── 01_eda_before_cleaning.ipynb     # Khám phá dữ liệu thô & phân phối ban đầu
│   ├── 02_cleaning.ipynb                # Xử lý Missing values, ngoại lai & làm sạch
│   ├── 03_eda_after_cleaning.ipynb      # Trực quan hóa tương quan sau làm sạch
│   └── 04_feature_engineering.ipynb     # Thử nghiệm trích xuất đặc trưng & lag
├── pipeline/                      # Hệ thống Pipeline Production (6 Stages)
│   ├── config.py                  # Cấu hình đường dẫn, hằng số & biến môi trường
│   ├── tracking.py                # Context manager ghi log JSONL tiến trình & metrics
│   ├── ingest.py                  # Stage 1: Giải nén & đọc CSV -> Parquet tối ưu bộ nhớ
│   ├── preprocess.py              # Stage 2: Làm sạch & Label Encoding
│   ├── feature_engineering.py     # Stage 3: Tạo đặc trưng 'days', lag hành vi, tách Valid & 5-month lag
│   ├── train.py                   # Stage 4: Huấn luyện XGBoost Classifier đa lớp (multi:softprob)
│   ├── predict.py                 # Stage 5: Dự đoán xác suất, mask sản phẩm đã có -> sub.csv
│   ├── evaluate.py                # Stage 6: Đánh giá MAP@7 offline (map7_all vs map7_buyers)
│   ├── smoke_test.py              # Bộ kiểm thử chất lượng không cần nhãn (3 bài test)
│   └── run_pipeline.py            # Điều phối chạy toàn bộ hoặc chọn lọc từng stage
├── .github/workflows/
│   └── ci.yml                     # Tự động hóa CI/CD qua GitHub Actions
├── Dockerfile                     # Đóng gói môi trường thực thi Pipeline
├── GCP_DEPLOYMENT.md              # Sổ tay hướng dẫn vận hành Vertex AI chi tiết
├── custom_job_full.yaml           # Cấu hình Vertex AI chạy full 13.6M dòng
├── custom_job_fe_train.yaml       # Cấu hình Vertex AI chạy từ Feature Engineering
├── custom_job_test.yaml           # Cấu hình Vertex AI chạy kiểm thử nhanh (10k dòng)
└── requirements.txt               # Thư viện phụ thuộc
```

---

## 3. Nội dung các Notebook nghiên cứu (`notebooks/`)

Các file Jupyter Notebook đóng vai trò là giai đoạn R&D (nghiên cứu thử nghiệm ban đầu) được sắp xếp mạch lạc theo 4 bước chuẩn:

1. **`01_eda_before_cleaning.ipynb` (Khám phá dữ liệu thô)**:
   - Thống kê tỷ lệ giá trị thiếu (missing values) ở từng cột: `renta` (thu nhập) thiếu ~20%, `age`, `antiguedad`, `indrel_1mes`...
   - Phân tích độ mất cân bằng của 24 sản phẩm tài chính: các sản phẩm phổ biến nhất (`ind_cco_fin_ult1` chiếm phần lớn) và các sản phẩm hầu như không có giao dịch (`ind_aval_fin_ult1`, `ind_ahor_fin_ult1`).
2. **`02_cleaning.ipynb` (Làm sạch & Điền khuyết)**:
   - Điền khuyết thu nhập (`renta`) theo trung vị của từng tỉnh thành (`cod_prov`).
   - Xử lý tuổi khách hàng bất thường (`age < 18` hoặc `age > 100`).
   - Chuẩn hóa các biến định danh phân loại (`sexo`, `segmento`, `canal_entrada`, `pais_residencia`).
3. **`03_eda_after_cleaning.ipynb` (Trực quan hóa sau làm sạch)**:
   - Phân tích tương quan giữa các nhóm nhân khẩu học và tỷ lệ sở hữu sản phẩm.
   - Trực quan hóa xu hướng mua sắm sản phẩm theo thời gian (tính thời vụ theo từng tháng).
4. **`04_feature_engineering.ipynb` (Thử nghiệm trích xuất đặc trưng)**:
   - Xây dựng đặc trưng số ngày khách gắn bó với ngân hàng (`days`).
   - Thử nghiệm tạo cờ thay đổi trạng thái khách hàng giữa 2 tháng liên tiếp.
   - Đánh giá khả năng tạo đặc trưng trễ (Lag features) 5 tháng liền trước.

---

## 4. Kiến trúc Pipeline Production (`pipeline/`)

Pipeline được module hóa thành các script Python độc lập, trao đổi dữ liệu trung gian qua định dạng **Parquet** và ma trận **NumPy (`.npy`)** trong thư mục `artifacts/`, giúp hệ thống vận hành bền bỉ và không phụ thuộc vào bộ nhớ RAM của một phiên làm việc:

```
[1. Ingest] -> [2. Preprocess] -> [3. Feature Engineering] -> [4. Train] -> [5. Predict] -> [6. Evaluate]
                                                                                                  |
                                                                                    [Smoke Test Verification]
```

### Chi tiết 6 Stage chính:
- **Stage 1 — Ingest (`ingest.py`)**: Đọc dữ liệu CSV từ local/GCS, nén và lưu sang Parquet (giảm 70% dung lượng, tăng tốc độ I/O lên gấp 5 lần).
- **Stage 2 — Preprocess (`preprocess.py`)**: Thực hiện các bước làm sạch chuẩn hóa và áp dụng `LabelEncoder` lên các cột phân loại, lưu bộ encoder thành `feature_label_encoders.pkl`.
- **Stage 3 — Feature Engineering (`feature_engineering.py`)**:
  - Tính đặc trưng `days = fecha_dato - fecha_alta`.
  - Tạo các cờ thay đổi hành vi (`segmento_changed`, `ind_actividad_cliente_changed`, `tiprel_1mes_changed`).
  - Xác định nhãn mục tiêu (khách hàng mua mới sản phẩm tại tháng 06/2015 so với tháng 05/2015).
  - **Tách tập Validation**: Tách 20% khách hàng duy nhất làm tập Validation offline và lưu nhãn thực tế vào `val_ground_truth.json`.
  - Sinh đặc trưng trễ 5 tháng (`5-month lag features`) cho 24 sản phẩm của cả tập Train, Valid và Test.
- **Stage 4 — Train (`train.py`)**:
  - Huấn luyện mô hình **XGBoost Multiclass** với hàm mục tiêu `multi:softprob` trên ma trận đặc trưng $X_{train}$.
  - Mã hóa nhãn với `target_encoder.pkl` và xuất file mô hình `xgb_model.pkl`.
- **Stage 5 — Predict (`predict.py`)**:
  - Dự đoán xác suất cho khách hàng tập Test ($X_{test}$).
  - **Masking**: Tra cứu snapshot tháng 05/2016, loại bỏ các sản phẩm khách đã có.
  - Lấy **top-7 sản phẩm** có xác suất cao nhất và xuất file `sub.csv` theo đúng định dạng nộp bài Kaggle.
- **Stage 6 — Evaluate (`evaluate.py`)**:
  - Đánh giá offline mô hình trên tập Validation tháng 06/2015.
  - Sử dụng PyArrow đọc snapshot tháng 05/2015 để mask các sản phẩm khách đã sở hữu trước đó.
  - Áp dụng thuật toán xếp hạng vector hóa (`np.argsort`) và tính chỉ số **MAP@7** chuẩn Kaggle:
    - `map7_all`: Tính trên toàn bộ tập validation (khách không mua có AP = 0) $\rightarrow$ dùng để đối chiếu với điểm Kaggle.
    - `map7_buyers`: Chỉ tính trên nhóm khách có mua mới sản phẩm.
  - Hỗ trợ CLI `--update-kaggle` để cập nhật điểm thật từ Leaderboard vào log truy vết.

### Bộ kiểm thử chất lượng không cần nhãn (`smoke_test.py`):
- **Test 1**: Kiểm tra đầy đủ Schema và dtypes của 22 cột nhân khẩu học và 24 cột sản phẩm.
- **Test 2**: Đảm bảo ma trận đặc trưng $X_{train}, X_{val}$ sạch $100\%$ (**0 NaN, 0 Inf**).
- **Test 3**: Kiểm tra định dạng file `sub.csv`: đủ số dòng tập test, header chuẩn, mỗi khách đúng 7 sản phẩm **không trùng lặp**.

---

## 5. Thực thi trên Google Cloud Platform (GCP)

Toàn bộ hệ thống được container hóa và thiết kế để chạy serverless trên nền tảng Google Cloud:

```
[Code Repository] ---> [GitHub Actions CI/CD] ---> [Artifact Registry (Docker Image)]
                                                                  |
                                                                  v
[Cloud Storage (gs://)] <===========================> [Vertex AI Custom Job (VM Compute)]
   - Raw Data (train_ver2.csv)                            - Ingest & Preprocess
   - Output Artifacts & sub.csv                           - Feature Engineering & Train XGBoost
                                                          - Predict & Offline Evaluation (MAP@7)
```

### 1. Lưu trữ dữ liệu trên Cloud Storage (GCS)
- Bucket: `gs://uit-thien-santander-ds/`
- Thư mục `raw/`: Lưu trữ dữ liệu gốc `train_ver2.csv` (2.3 GB) và `test_ver2.csv` (110 MB).
- Khi chạy trên Cloud, container tải dữ liệu trực tiếp từ GCS và upload lại toàn bộ artifacts cùng `sub.csv` sau khi hoàn thành.

### 2. Đóng gói Container với Docker & Artifact Registry
- `Dockerfile` đóng gói toàn bộ môi trường Python 3.11, thư viện máy học C++ (XGBoost, LightGBM, Scikit-learn, PyArrow).
- Docker Image được lưu trữ tại Google Artifact Registry:
  `us-central1-docker.pkg.dev/santander-ds/santander-repo/santander-pipeline:latest`

### 3. Huấn luyện bằng Vertex AI Custom Jobs
Pipeline được thực thi thông qua Custom Job trên máy ảo cấu hình cao (`e2-standard-4` hoặc `n1-standard-8`):
- **Serverless & Tự động tắt máy**: Máy ảo chỉ khởi chạy khi có lệnh, xử lý xong toàn bộ pipeline sẽ tự động hủy ngay lập tức ($0$ chi phí duy trì máy ngầm).
- Các cấu hình Job có sẵn:
  - `custom_job_full.yaml`: Huấn luyện trên toàn bộ dữ liệu 13.6 triệu dòng.
  - `custom_job_fe_train.yaml`: Huấn luyện từ bước Feature Engineering đến Predict/Evaluate.
  - `custom_job_test.yaml`: Kiểm thử nhanh trên dữ liệu mẫu 10k dòng.

### 4. Tự động hóa CI/CD qua GitHub Actions
File `.github/workflows/ci.yml` tự động kiểm soát chất lượng mã nguồn mỗi khi có thay đổi:
1. Tự động kích hoạt toàn bộ pipeline trên tập dữ liệu mẫu 10k dòng.
2. Thực thi bộ kiểm thử `smoke_test.py`.
3. Tự động build lại Docker image và đẩy lên GCP Artifact Registry khi code được merge vào nhánh `main`.

---

## 6. Hướng dẫn chạy dự án

### A. Chạy tại máy Local

```powershell
# 1. Kích hoạt môi trường ảo
.\.venv\Scripts\Activate.ps1

# 2. Chạy toàn bộ pipeline trên dữ liệu mẫu 10k dòng
$env:SANTANDER_SAMPLE_ROWS="10000"
python pipeline/run_pipeline.py

# 3. Chạy kiểm thử chất lượng dữ liệu
python pipeline/smoke_test.py

# 4. Chạy riêng bước đánh giá Offline MAP@7
python pipeline/evaluate.py
```

### B. Huấn luyện trên Google Cloud Vertex AI

```powershell
# 1. Đăng nhập Google Cloud SDK
gcloud auth login
gcloud config set project santander-ds

# 2. Khởi chạy Job huấn luyện toàn diện trên Vertex AI
gcloud ai custom-jobs create `
    --region=us-central1 `
    --project=santander-ds `
    --display-name="santander-full-training" `
    --config=custom_job_full.yaml

# 3. Theo dõi tiến trình qua log streaming
gcloud ai custom-jobs stream-logs <JOB_ID> --region=us-central1 --project=santander-ds

# 4. Tải file kết quả dự đoán từ GCS về máy
gcloud storage cp gs://uit-thien-santander-ds/artifacts/sub.csv ./sub.csv
```

*Xem thêm sổ tay vận hành chi tiết từ A-Z tại [GCP_DEPLOYMENT.md](file:///c:/Users/Admin/Documents/VSF/GCP_DEPLOYMENT.md).*
