"""
STAGE 5 — PREDICT
Load model đã train, predict_proba cho X_test, loại các sản phẩm khách
đã sở hữu (tra theo tháng PREDICT_REFERENCE_MONTH), giữ lại top-7,
xuất ra sub.csv.

Có thể chạy lại riêng stage này khi đã có model — không cần chạy lại
toàn bộ EDA/feature engineering mỗi lần muốn ra submission mới.

Chạy độc lập: python predict.py
"""
import json
import pickle

import numpy as np
import pandas as pd
from tqdm import tqdm

import config
from tracking import track_stage


def load_artifacts():
    with open(config.MODEL_PKL, "rb") as f:
        model = pickle.load(f)
    with open(config.TARGET_ENCODER_PKL, "rb") as f:
        target_encoder = pickle.load(f)
    with open(config.TARGET_COLS_JSON) as f:
        target_cols = np.array(json.load(f))

    X_test = np.load(config.X_TEST_NPY, allow_pickle=True)
    test_cust_ids = np.load(config.TEST_CUST_IDS_NPY, allow_pickle=True)

    df = pd.read_parquet(config.DF_WITH_BEHAVIOR_PARQUET)
    df_test = pd.read_parquet(config.PROCESSED_TEST_PARQUET)

    return model, target_encoder, target_cols, X_test, test_cust_ids, df, df_test


def build_owned_products_mask(df, df_test):
    """Với mỗi khách trong test set, trả về index các sản phẩm mà khách CHƯA sở hữu
    tính tại PREDICT_REFERENCE_MONTH (chỉ những sản phẩm này mới được đề xuất)."""
    test_users = {}
    reference_rows = df[
        (df["fecha_dato"] == config.PREDICT_REFERENCE_MONTH)
        & (df["ncodpers"].isin(df_test["ncodpers"].to_numpy()))
    ]
    for row in tqdm(reference_rows.iloc):
        # NOTE: slice theo tên cột 'ind_cco_fin_ult1':'ind_recibo_ult1' phụ thuộc thứ tự
        # cột trong df — hợp lệ miễn cột product vẫn nằm liền nhau đúng thứ tự gốc.
        test_users[row["ncodpers"]] = np.where(row["ind_cco_fin_ult1":"ind_recibo_ult1"] == 0)[0]
    return test_users


def build_top7_predictions(model, target_encoder, target_cols, X_test, test_cust_ids, test_users):
    y_pred = model.predict_proba(X_test)

    label_to_col = {label: idx for idx, label in enumerate(target_encoder.classes_)}

    test_user_ratings = {}
    test_users_valid = {}
    for k, cust_id in enumerate(tqdm(test_cust_ids)):
        original_zero_idx = test_users.get(cust_id, np.arange(len(target_cols)))
        valid_idx = [idx for idx in original_zero_idx if idx in label_to_col]
        cols_in_pred = [label_to_col[idx] for idx in valid_idx]
        test_user_ratings[cust_id] = y_pred[k][cols_in_pred]
        test_users_valid[cust_id] = valid_idx

    final_preds = []
    test_ids = []
    for cust_id in tqdm(test_user_ratings.keys()):
        sorted_idx = np.argsort(test_user_ratings[cust_id])[::-1][:7]
        top_seven = [test_users_valid[cust_id][j] for j in sorted_idx]
        final_preds.append(" ".join(target_cols[np.array(top_seven)]))
        test_ids.append(cust_id)

    return test_ids, final_preds


def run():
    with track_stage("predict") as t:
        model, target_encoder, target_cols, X_test, test_cust_ids, df, df_test = load_artifacts()

        test_users = build_owned_products_mask(df, df_test)
        test_ids, final_preds = build_top7_predictions(
            model, target_encoder, target_cols, X_test, test_cust_ids, test_users
        )

        submission = pd.DataFrame({"ncodpers": test_ids, "added_products": final_preds})
        submission = submission.sort_values("ncodpers")
        submission.to_csv(config.SUBMISSION_CSV, index=False)

        print(f"Submission đã lưu -> {config.SUBMISSION_CSV}")

        # sanity check nhanh: sản phẩm nào được đề xuất đứng đầu (top-1) nhiều nhất
        top1_products = submission["added_products"].str.split().str[0]
        top1_distribution = top1_products.value_counts(normalize=True).round(3).head(5).to_dict()

        t.log(
            n_predictions=submission.shape[0],
            top1_product_distribution=top1_distribution,
        )


if __name__ == "__main__":
    run()
