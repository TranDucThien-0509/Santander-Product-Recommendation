"""
STAGE 6 — EVALUATE
Đánh giá mô hình offline bằng MAP@7 trên tập validation (tháng 06/2015).

Quy trình:
1. Load X_val, val_cust_ids, val_ground_truth.json đã được tách ở stage feature_engineering.
2. Tra cứu sản phẩm khách đã sở hữu tại tháng liền trước (MONTH_PREV_LABEL: 2015-05-28).
   Chỉ đề xuất sản phẩm khách CHƯA sở hữu ở tháng trước (giống hệt quy tắc Kaggle).
3. Dự đoán xác suất bằng mô hình (XGBoost/LightGBM), xếp hạng lấy top 7.
4. Tính Mean Average Precision @ 7 (MAP@7) đối chiếu với val_ground_truth.
5. Ghi kết quả vào pipeline_run_log.jsonl (kèm run_id, image_tag, map7_valid, kaggle_public).
6. Cho phép cập nhật điểm Kaggle Public sau khi nộp qua CLI:
   python evaluate.py --update-kaggle 0.0295 --run-id 2026-09-21_full_v1

Chạy độc lập: python evaluate.py
"""
import argparse
import json
import os
import pickle
import subprocess
import sys
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
from tqdm import tqdm

import config
from tracking import track_stage


# ----------------------------------------------------------------------
# 1. Metric MAP@7 (Kaggle Official Formula)
# ----------------------------------------------------------------------
def apk(actual, predicted, k=7):
    """
    Tính Average Precision tại cut-off k cho một khách hàng.
    - actual: danh sách tên các sản phẩm thực tế khách mua mới (vd: ['ind_cco_fin_ult1'])
    - predicted: danh sách top k tên sản phẩm được mô hình đề xuất
    """
    if not actual:
        return 0.0

    if len(predicted) > k:
        predicted = predicted[:k]

    score = 0.0
    num_hits = 0.0

    for i, p in enumerate(predicted):
        if p in actual and p not in predicted[:i]:
            num_hits += 1.0
            score += num_hits / (i + 1.0)

    return score / min(len(actual), k)


def mapk(actual, predicted, k=7):
    """
    Tính Mean Average Precision tại cut-off k trên toàn bộ danh sách khách hàng.
    """
    if not actual or not predicted:
        return 0.0
    return float(np.mean([apk(a, p, k) for a, p in zip(actual, predicted)]))


# ----------------------------------------------------------------------
# 2. Tiện ích Git & Metadata
# ----------------------------------------------------------------------
def get_git_commit_sha():
    """Lấy git SHA ngắn (short hash) hiện tại để gắn tag truy vết artifact/run."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        return out.decode("utf-8").strip()
    except Exception:
        return "local-no-git"


# ----------------------------------------------------------------------
# 3. Mask sản phẩm đã sở hữu ở tháng trước (2015-05-28)
# ----------------------------------------------------------------------
def build_val_owned_mask(df, val_cust_ids, target_cols):
    """
    Với mỗi khách hàng trong tập validation, xác định danh sách index các sản phẩm
    mà khách CHƯA sở hữu tại tháng liền trước (config.MONTH_PREV_LABEL = 2015-05-28).
    Chỉ các sản phẩm này mới hợp lệ để đưa vào top-7 đề xuất.
    """
    valid_cols_in_df = [c for c in target_cols if c in df.columns]
    reference_rows = df[
        (df["fecha_dato"] == config.MONTH_PREV_LABEL)
        & (df["ncodpers"].isin(val_cust_ids))
    ]

    val_users_eligible = {}
    if not reference_rows.empty:
        prev_owned_matrix = reference_rows.set_index("ncodpers")[valid_cols_in_df]
        for cust_id in val_cust_ids:
            if cust_id in prev_owned_matrix.index:
                row_vals = prev_owned_matrix.loc[cust_id]
                if isinstance(row_vals, pd.DataFrame):
                    row_vals = row_vals.iloc[0]
                unowned_cols = [c for c in valid_cols_in_df if row_vals[c] == 0]
                # Index tương ứng trong target_cols
                val_users_eligible[cust_id] = [
                    np.where(target_cols == c)[0][0] for c in unowned_cols
                ]
            else:
                # Khách mới xuất hiện tại tháng 6/2015 -> chưa sở hữu sp nào ở tháng 5
                val_users_eligible[cust_id] = list(range(len(target_cols)))
    else:
        for cust_id in val_cust_ids:
            val_users_eligible[cust_id] = list(range(len(target_cols)))

    return val_users_eligible


# ----------------------------------------------------------------------
# 4. Đánh giá mô hình trên tập Validation
# ----------------------------------------------------------------------
def evaluate_validation_set(model, target_encoder, target_cols, X_val, val_cust_ids, val_ground_truth, val_users_mask):
    """
    Dự đoán xác suất trên X_val, mask sản phẩm đã sở hữu, trích xuất top-7 và tính MAP@7.
    """
    y_pred_proba = model.predict_proba(X_val)

    # Map giữa class index của mô hình và vị trí cột trong target_cols
    label_to_col = {label: idx for idx, label in enumerate(target_encoder.classes_)}

    actual_list = []
    pred_list = []
    per_cust_apk = []

    for k, cust_id in enumerate(val_cust_ids):
        actual_products = val_ground_truth.get(str(cust_id), [])
        if not actual_products:
            continue

        eligible_indices = val_users_mask.get(cust_id, list(range(len(target_cols))))
        valid_indices = [idx for idx in eligible_indices if idx in label_to_col]

        if not valid_indices:
            top_seven = []
        else:
            model_cols = [label_to_col[idx] for idx in valid_indices]
            scores = y_pred_proba[k][model_cols]
            sorted_order = np.argsort(scores)[::-1][:7]
            top_seven = [target_cols[valid_indices[i]] for i in sorted_order]

        actual_list.append(actual_products)
        pred_list.append(top_seven)
        per_cust_apk.append(apk(actual_products, top_seven, k=7))

    map7_score = float(np.mean(per_cust_apk)) if per_cust_apk else 0.0
    return map7_score, actual_list, pred_list


# ----------------------------------------------------------------------
# 5. Hàm cập nhật Kaggle Public Score vào Log
# ----------------------------------------------------------------------
def update_kaggle_public_score(run_id, kaggle_score, log_path=None):
    """
    Cập nhật điểm Kaggle Public vào pipeline_run_log.jsonl cho một run_id cụ thể.
    """
    path = log_path or config.PIPELINE_LOG_JSONL
    if not os.path.exists(path):
        print(f"Không tìm thấy file log: {path}")
        return False

    updated = False
    lines = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                record = json.loads(line_str)
                # Tìm bản ghi evaluate khớp run_id, hoặc bản ghi evaluate cuối cùng nếu run_id='latest'
                if (record.get("stage") == "evaluate" or "map7_valid" in record) and (
                    record.get("run_id") == run_id or run_id == "latest"
                ):
                    record["kaggle_public"] = float(kaggle_score)
                    record["kaggle_updated_at"] = datetime.now(timezone.utc).isoformat()
                    updated = True
                    lines.append(json.dumps(record, ensure_ascii=False) + "\n")
                    continue
            except Exception:
                pass
            lines.append(line)

    if updated:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f">> Đã cập nhật Kaggle Public Score = {kaggle_score} cho run '{run_id}' trong {path}")
        return True
    else:
        print(f"!! Không tìm thấy bản ghi evaluate khớp với run_id='{run_id}'")
        return False


# ----------------------------------------------------------------------
# 6. Hàm chạy chính (Run)
# ----------------------------------------------------------------------
def run():
    with track_stage("evaluate") as t:
        # 1. Kiểm tra artifact bắt buộc
        required_files = [
            config.MODEL_PKL,
            config.TARGET_ENCODER_PKL,
            config.TARGET_COLS_JSON,
            config.X_VAL_NPY,
            config.VAL_CUST_IDS_NPY,
            config.VAL_GROUND_TRUTH_JSON,
            config.DF_WITH_BEHAVIOR_PARQUET,
        ]
        for p in required_files:
            if not os.path.exists(p):
                raise FileNotFoundError(f"Thiếu artifact cần cho evaluate: {p}")

        # 2. Load artifacts
        with open(config.MODEL_PKL, "rb") as f:
            model = pickle.load(f)
        with open(config.TARGET_ENCODER_PKL, "rb") as f:
            target_encoder = pickle.load(f)
        with open(config.TARGET_COLS_JSON) as f:
            target_cols = np.array(json.load(f))

        X_val = np.load(config.X_VAL_NPY, allow_pickle=True)
        val_cust_ids = np.load(config.VAL_CUST_IDS_NPY, allow_pickle=True)
        with open(config.VAL_GROUND_TRUTH_JSON, "r", encoding="utf-8") as f:
            val_ground_truth = json.load(f)

        df = pd.read_parquet(config.DF_WITH_BEHAVIOR_PARQUET)

        # 3. Tạo mask sản phẩm đã sở hữu
        print(f"Đang tạo mask sản phẩm đã sở hữu cho {len(val_cust_ids)} khách hàng validation...")
        val_users_mask = build_val_owned_mask(df, val_cust_ids, target_cols)

        # 4. Dự đoán và tính MAP@7
        print("Đang chạy dự đoán và tính MAP@7...")
        map7_score, actual_list, pred_list = evaluate_validation_set(
            model, target_encoder, target_cols, X_val, val_cust_ids, val_ground_truth, val_users_mask
        )

        # 5. Chuẩn bị metadata run_id & image_tag
        default_run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        run_id = os.environ.get("SANTANDER_RUN_ID", default_run_id)
        image_tag = os.environ.get("SANTANDER_IMAGE_TAG", get_git_commit_sha())

        kaggle_public_env = os.environ.get("SANTANDER_KAGGLE_PUBLIC", "")
        kaggle_public = float(kaggle_public_env) if kaggle_public_env else None

        cost_usd_env = os.environ.get("SANTANDER_RUN_COST_USD", "0")
        cost_usd = float(cost_usd_env) if cost_usd_env else 0.0

        # In kết quả đánh giá rõ ràng ra terminal
        print("\n" + "=" * 50)
        print("           KẾT QUẢ ĐÁNH GIÁ OFFLINE")
        print("=" * 50)
        print(f"  Run ID            : {run_id}")
        print(f"  Image Tag / SHA   : {image_tag}")
        print(f"  Validation MAP@7  : {map7_score:.5f}")
        print(f"  Số khách validation: {len(actual_list):,}")
        if kaggle_public is not None:
            print(f"  Kaggle Public     : {kaggle_public:.5f}")
            print(f"  Chênh lệch (Local - Kaggle): {map7_score - kaggle_public:+.5f}")
        print("=" * 50 + "\n")

        # Lưu file tóm tắt metrics độc lập eval_metrics.json
        eval_metrics = {
            "run_id": run_id,
            "image_tag": image_tag,
            "map7_valid": round(map7_score, 5),
            "kaggle_public": kaggle_public,
            "n_val_customers": len(actual_list),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(config.EVAL_METRICS_JSON, "w", encoding="utf-8") as f:
            json.dump(eval_metrics, f, indent=2, ensure_ascii=False)

        # Log vào pipeline_run_log.jsonl đúng chuẩn yêu cầu mục 2.1
        t.log(
            run_id=run_id,
            image_tag=image_tag,
            map7_valid=round(map7_score, 5),
            kaggle_public=kaggle_public,
            cost_usd=cost_usd,
            n_val_customers=len(actual_list),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage Evaluate & Metric Logging")
    parser.add_argument(
        "--update-kaggle",
        type=float,
        help="Cập nhật điểm Kaggle Public vào log cho run_id (vd: --update-kaggle 0.0295)",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default="latest",
        help="Run ID cần cập nhật (mặc định: 'latest' = bản ghi evaluate cuối cùng)",
    )
    args = parser.parse_args()

    if args.update_kaggle is not None:
        update_kaggle_public_score(args.run_id, args.update_kaggle)
    else:
        run()
