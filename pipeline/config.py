"""
Cấu hình đường dẫn dùng chung cho toàn bộ pipeline.
Chỉnh 1 chỗ ở đây thay vì rải rác trong từng script.
"""
import os

_PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_PIPELINE_DIR, ".."))
_LOCAL_RAW = os.path.join(_PROJECT_ROOT, "data", "raw")

_DEFAULT_INPUT = _LOCAL_RAW if os.path.exists(_LOCAL_RAW) else "/kaggle/input/santander-product-recommendation/"
_DEFAULT_WORK = _PIPELINE_DIR if os.path.exists(_LOCAL_RAW) else "/kaggle/working/"

# Có thể override bằng biến môi trường khi chạy ngoài Kaggle
# vd: export SANTANDER_INPUT_DIR=/home/user/data
INPUT_DIR = os.environ.get("SANTANDER_INPUT_DIR", _DEFAULT_INPUT)
WORK_DIR = os.environ.get("SANTANDER_WORK_DIR", _DEFAULT_WORK)

# Thư mục chứa tập mẫu (samples) — tách biệt hoàn toàn khỏi raw/ (bảo toàn tầng dữ liệu bất biến)
_LOCAL_SAMPLES = os.path.join(_PROJECT_ROOT, "data", "samples")
_DEFAULT_SAMPLES = _LOCAL_SAMPLES if os.path.exists(_LOCAL_SAMPLES) else os.path.join(INPUT_DIR, "..", "samples")
SAMPLES_DIR = os.environ.get("SANTANDER_SAMPLES_DIR", _DEFAULT_SAMPLES)

# Git commit SHA hoặc tag Docker image để truy vết mã nguồn trong log
IMAGE_TAG = os.environ.get("SANTANDER_IMAGE_TAG", "local-dev")

# Số dòng sample để test nhanh (vd: 10000, 1000000), mặc định None = chạy full
_sample_env = os.environ.get("SANTANDER_SAMPLE_ROWS", "").strip()
SAMPLE_ROWS = int(_sample_env) if _sample_env.isdigit() and int(_sample_env) > 0 else None

# Thư mục lưu artifact trung gian giữa các stage (parquet, pickle, npy)
ARTIFACT_DIR = os.path.join(WORK_DIR, "artifacts")
os.makedirs(ARTIFACT_DIR, exist_ok=True)

# Log tracking dùng chung cho mọi stage — mỗi lần chạy append thêm dòng, không ghi đè
PIPELINE_LOG_JSONL = os.path.join(ARTIFACT_DIR, "pipeline_run_log.jsonl")

# ---- Stage 1: ingest ----
ZIP_FILES = ["train_ver2.csv.zip", "test_ver2.csv.zip", "sample_submission.csv.zip"]
RAW_TRAIN_PARQUET = os.path.join(ARTIFACT_DIR, "df_train_raw.parquet")
RAW_TEST_PARQUET = os.path.join(ARTIFACT_DIR, "df_test_raw.parquet")

# ---- Stage 2: preprocess ----
PROCESSED_TRAIN_PARQUET = os.path.join(ARTIFACT_DIR, "df_train_processed.parquet")
PROCESSED_TEST_PARQUET = os.path.join(ARTIFACT_DIR, "df_test_processed.parquet")
FEATURE_LABEL_ENCODERS_PKL = os.path.join(ARTIFACT_DIR, "feature_label_encoders.pkl")

# ---- Stage 3: feature engineering ----
DF_WITH_BEHAVIOR_PARQUET = os.path.join(ARTIFACT_DIR, "df_with_behavior_lags.parquet")  # cần cho predict.py (mask sản phẩm đã sở hữu)
TARGET_COLS_JSON = os.path.join(ARTIFACT_DIR, "target_cols.json")
X_TRAIN_NPY = os.path.join(ARTIFACT_DIR, "X_train.npy")
Y_TRAIN_NPY = os.path.join(ARTIFACT_DIR, "y_train.npy")
X_TEST_NPY = os.path.join(ARTIFACT_DIR, "X_test.npy")
TRAIN_CUST_IDS_NPY = os.path.join(ARTIFACT_DIR, "train_cust_ids.npy")
TEST_CUST_IDS_NPY = os.path.join(ARTIFACT_DIR, "test_cust_ids.npy")

# ---- Stage 4: train ----
MODEL_PKL = os.path.join(ARTIFACT_DIR, "xgb_model.pkl")
TARGET_ENCODER_PKL = os.path.join(ARTIFACT_DIR, "target_encoder.pkl")
BEST_PARAMS_JSON = os.path.join(ARTIFACT_DIR, "best_params.json")

# ---- Stage 5: predict ----
SUBMISSION_CSV = os.path.join(WORK_DIR, "sub.csv")

# ---- Stage 6: evaluate ----
X_VAL_NPY = os.path.join(ARTIFACT_DIR, "X_val.npy")
Y_VAL_NPY = os.path.join(ARTIFACT_DIR, "y_val.npy")
VAL_CUST_IDS_NPY = os.path.join(ARTIFACT_DIR, "val_cust_ids.npy")
VAL_GROUND_TRUTH_JSON = os.path.join(ARTIFACT_DIR, "val_ground_truth.json")
EVAL_METRICS_JSON = os.path.join(ARTIFACT_DIR, "eval_metrics.json")

# Chiến lược validation: "customer_split" (80% train / 20% valid khách hàng tháng 6) hoặc "temporal" (train tháng 5, valid tháng 6)
VAL_STRATEGY = os.environ.get("SANTANDER_VAL_STRATEGY", "customer_split").lower()

# Ngày tham chiếu dùng trong feature engineering / predict — tách ra đây để không hardcode rải rác
MONTH_TRAIN_LABEL = "2015-06-28"     # tháng dùng để xác định khách mua thêm sản phẩm (target)
MONTH_PREV_LABEL = "2015-05-28"      # tháng liền trước, dùng để so sánh
LAG_TRAIN_CUTOFF = "2015-06-28"      # cutoff xây lag feature cho train
LAG_TEST_START = "2016-01-28"        # cửa sổ lag feature cho test
LAG_TEST_CUTOFF = "2016-06-28"
PREDICT_REFERENCE_MONTH = "2016-05-28"  # tháng dùng để biết khách test đã sở hữu sản phẩm gì

