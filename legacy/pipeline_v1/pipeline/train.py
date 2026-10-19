"""
STAGE 4 — TRAIN
(Tùy chọn) hyperparameter search cho LightGBM, sau đó train XGBoost cuối
với params cố định, lưu model + target encoder.

NOTE quan trọng: ở notebook gốc, RandomizedSearchCV chỉ chạy trên LGBM
(params_xgb/params_rf/params_cat được định nghĩa nhưng KHÔNG dùng để search),
còn model cuối cùng lại là XGBoost với params HARDCODE tay — không lấy từ
clf.best_params_ (mà best_params_ đó là của LGBM, không match tên tham số
XGBoost). Nghĩa là bước search hiện tại không thực sự quyết định params
của model cuối. Giữ nguyên hành vi này (RUN_HYPERPARAM_SEARCH mặc định
False vì tốn thời gian và không ảnh hưởng tới model cuối); bật lên nếu
em muốn dùng để tham khảo, hoặc sửa lại để áp dụng đúng best_params_ cho
đúng thuật toán đang search.

Chạy độc lập: python train.py
"""
import json
import pickle

import numpy as np
from sklearn.metrics import log_loss
from sklearn.model_selection import RandomizedSearchCV
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

import config
from tracking import track_stage

RUN_HYPERPARAM_SEARCH = False  # bật True nếu muốn chạy lại search (tốn thời gian)

PARAMS_XGB = {
    "learning_rate": [0.01, 0.03, 0.1, 0.2],
    "max_depth": [3, 5, 8],
    "n_estimators": [10, 50],
    "colsample_bytree": [0.5, 0.6, 0.7, 0.8, 0.9, 1],
    "subsample": [0.5, 0.6, 0.7, 0.8, 0.9, 1],
    "min_child_weight": [1, 3, 5, 7, 10, 14],
}
PARAMS_RF = {
    "n_estimators": [50, 100, 200],
    "max_depth": [None, 10, 20, 30],
    "min_samples_split": [2, 5, 10],
    "min_samples_leaf": [1, 2, 4],
    "bootstrap": [True, False],
}
PARAMS_CAT = {
    "depth": [4, 6, 8, 10],
    "learning_rate": [0.01, 0.05, 0.1],
    "iterations": [100, 200],
    "l2_leaf_reg": [1, 3, 5, 7, 9],
}
PARAMS_LGBM = {
    "num_leaves": [31, 50, 70],
    "learning_rate": [0.01, 0.05, 0.1],
    "n_estimators": [50, 100, 200],
    "min_child_samples": [10, 20, 30],
}

# Params cố định cho XGBoost cuối cùng (copy nguyên từ notebook gốc)
FINAL_XGB_PARAMS = dict(
    objective="multi:softprob",
    eval_metric="mlogloss",
    max_depth=3,
    n_estimators=50,
    learning_rate=0.03,
    colsample_bytree=0.8,
    subsample=0.9,
    min_child_weight=1,
)


def run_lgbm_search(X_train, y_train):
    from lightgbm import LGBMClassifier

    clf = RandomizedSearchCV(
        LGBMClassifier(objective="multiclass", n_jobs=1),
        PARAMS_LGBM,
        n_iter=10,
        scoring="neg_log_loss",
        cv=3,
        n_jobs=-1,
        verbose=10,
        error_score="raise",
    )
    clf.fit(X_train, y_train)
    print(f"Best params (LGBM): {clf.best_params_}")
    with open(config.BEST_PARAMS_JSON, "w") as f:
        json.dump(clf.best_params_, f)
    return clf.best_params_


def train_final_xgb(X_train, y_train):
    target_encoder = LabelEncoder()
    y_train_encoded = target_encoder.fit_transform(y_train)

    xgb = XGBClassifier(**FINAL_XGB_PARAMS)
    xgb.fit(X_train, y_train_encoded)
    return xgb, target_encoder


def run():
    with track_stage("train") as t:
        X_train = np.load(config.X_TRAIN_NPY, allow_pickle=True)
        y_train = np.load(config.Y_TRAIN_NPY, allow_pickle=True)

        best_lgbm_params = None
        if RUN_HYPERPARAM_SEARCH:
            best_lgbm_params = run_lgbm_search(X_train, y_train)

        xgb, target_encoder = train_final_xgb(X_train, y_train)

        with open(config.MODEL_PKL, "wb") as f:
            pickle.dump(xgb, f)
        with open(config.TARGET_ENCODER_PKL, "wb") as f:
            pickle.dump(target_encoder, f)

        print(f"Model đã lưu -> {config.MODEL_PKL}")
        print(f"Target encoder đã lưu -> {config.TARGET_ENCODER_PKL}")

        # NOTE: đây là log loss trên chính X_train/y_train (không phải validation set
        # riêng) — chỉ để theo dõi model có học được gì không qua từng lần chạy,
        # không dùng số này để đánh giá khả năng tổng quát hóa của model.
        y_train_encoded = target_encoder.transform(y_train)
        train_log_loss = log_loss(y_train_encoded, xgb.predict_proba(X_train))

        t.log(
            params=FINAL_XGB_PARAMS,
            hyperparam_search_ran=RUN_HYPERPARAM_SEARCH,
            best_lgbm_params=best_lgbm_params,
            n_train_rows=X_train.shape[0],
            train_set_log_loss=round(train_log_loss, 4),
        )


if __name__ == "__main__":
    run()
