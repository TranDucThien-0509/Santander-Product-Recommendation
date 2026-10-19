"""
STAGE 3 — FEATURE ENGINEERING
Drop cột không dùng, tạo feature 'days', behavior lag/changed flags,
xây tập target (khách mua thêm sản phẩm tháng kế tiếp) và 5-month lag features.

NOTE: notebook gốc build X_train/y_train/X_test/test_cust_ids 2 lần
(1 lần ở cell riêng, 1 lần lặp lại y hệt ngay trước khi thêm lag) —
kết quả giống hệt nhau nên bản tách này chỉ build 1 lần, ngay trước khi
gắn lag, để tránh tính trùng.

Input: parquet đã preprocess. Output: X_train/y_train/X_test (npy),
target_cols, df kèm behavior-lag (cần cho predict.py để biết khách đã
sở hữu sản phẩm gì).

Chạy độc lập: python feature_engineering.py
"""
import json
import warnings

import numpy as np
import pandas as pd
from tqdm import tqdm

import config
from tracking import track_stage

DROP_COLS_BOTH = ["tipodom", "cod_prov", "ult_fec_cli_1t", "conyuemp"]
DROP_LOW_VOLUME_PRODUCTS = ["ind_ahor_fin_ult1", "ind_aval_fin_ult1", "ind_cder_fin_ult1", "ind_deme_fin_ult1"]

ALL_ORIGINAL_PRODUCTS = [
    "ind_ahor_fin_ult1", "ind_aval_fin_ult1", "ind_cco_fin_ult1", "ind_cder_fin_ult1",
    "ind_cno_fin_ult1", "ind_ctju_fin_ult1", "ind_ctma_fin_ult1", "ind_ctop_fin_ult1",
    "ind_ctpp_fin_ult1", "ind_deco_fin_ult1", "ind_deme_fin_ult1", "ind_dela_fin_ult1",
    "ind_ecue_fin_ult1", "ind_fond_fin_ult1", "ind_hip_fin_ult1", "ind_plan_fin_ult1",
    "ind_pres_fin_ult1", "ind_reca_fin_ult1", "ind_tjcr_fin_ult1", "ind_valo_fin_ult1",
    "ind_viv_fin_ult1", "ind_nomina_ult1", "ind_nom_pens_ult1", "ind_recibo_ult1",
]

# Cột non-product cần loại khỏi lag features (giữ nguyên danh sách gốc)
NON_LAG_COLS = [
    "ind_empleado", "pais_residencia", "sexo", "age", "days", "ind_nuevo", "antiguedad",
    "indrel", "indrel_1mes", "tiprel_1mes", "indresi", "indext", "canal_entrada",
    "indfall", "nomprov", "ind_actividad_cliente", "renta", "segmento",
]


def drop_unused_columns(df, df_test):
    df.drop(columns=DROP_COLS_BOTH, inplace=True)
    df_test.drop(columns=DROP_COLS_BOTH, inplace=True)
    # sản phẩm ít giao dịch — chỉ có ở train, test không chứa cột product
    df.drop(columns=DROP_LOW_VOLUME_PRODUCTS, inplace=True)
    return df, df_test


def add_days_feature(df, df_test):
    df["fecha_dato"] = pd.to_datetime(df["fecha_dato"])
    df["fecha_alta"] = pd.to_datetime(df["fecha_alta"])
    df_test["fecha_dato"] = pd.to_datetime(df_test["fecha_dato"])
    df_test["fecha_alta"] = pd.to_datetime(df_test["fecha_alta"])

    df_days_column = (df["fecha_dato"] - df["fecha_alta"]).dt.days
    df_test_days_column = (df_test["fecha_dato"] - df_test["fecha_alta"]).dt.days

    df.insert(loc=6, column="days", value=df_days_column)
    df_test.insert(loc=6, column="days", value=df_test_days_column)

    df.drop(columns=["fecha_alta"], inplace=True)
    df_test.drop(columns=["fecha_alta"], inplace=True)

    df["days"] = df["days"].fillna(df["days"].mean())
    df_test["days"] = df_test["days"].fillna(df["days"].mean())
    return df, df_test


def add_behavior_lag_flags(df):
    df = df.sort_values(["ncodpers", "fecha_dato"])
    behavior_cols = [c for c in ["segmento", "ind_actividad_cliente", "tiprel_1mes"] if c in df.columns]
    for col in behavior_cols:
        lag_col = f"{col}_lag_1"
        df[lag_col] = df.groupby("ncodpers")[col].shift(1)
        df[f"{col}_changed"] = (df[col] != df[lag_col]).astype(int)
        df.loc[df[lag_col].isnull(), f"{col}_changed"] = 0
    print(df[[f"{c}_changed" for c in behavior_cols]].mean())
    return df


def get_target_cols(df):
    dropped = [c for c in ALL_ORIGINAL_PRODUCTS if c not in df.columns]
    print("Các cột đã bị drop:", dropped)
    target_cols = np.array([c for c in ALL_ORIGINAL_PRODUCTS if c in df.columns])
    print(len(target_cols))
    print(target_cols)
    return target_cols


def build_train_total(df, df_test, target_cols):
    """Xác định khách hàng mua thêm sản phẩm mới giữa MONTH_PREV_LABEL và MONTH_TRAIN_LABEL,
    cộng với khách mới xuất hiện ở MONTH_TRAIN_LABEL — đây là tập 'positive/negative' cho target."""
    cust5_2015 = df[df["fecha_dato"] == config.MONTH_PREV_LABEL].set_index("ncodpers")[target_cols]
    id_cust5_2015 = cust5_2015.index.to_numpy()
    cust6_in52015 = df[
        (df["fecha_dato"] == config.MONTH_TRAIN_LABEL) & (df["ncodpers"].isin(cust5_2015.index))
    ].set_index("ncodpers")[target_cols]
    subtract_56 = cust5_2015 - cust6_in52015
    q = (subtract_56[target_cols] == -1).sum(1)
    id_cust5_buyin6 = q[q > 0].index

    cust5_buyin6 = df[(df["fecha_dato"] == config.MONTH_TRAIN_LABEL) & (df["ncodpers"].isin(id_cust5_buyin6))]
    cust6_newbuyin6 = df[
        (df["fecha_dato"] == config.MONTH_TRAIN_LABEL) & (~df["ncodpers"].isin(id_cust5_2015))
    ]

    warnings.filterwarnings("ignore")
    train_total = pd.DataFrame()
    t = 0
    for i in tqdm(target_cols):
        train = cust5_buyin6[cust5_buyin6["ncodpers"].isin(subtract_56[subtract_56[i] == -1].index)]
        train2 = cust6_newbuyin6[cust6_newbuyin6[i] == 1]
        train.drop(columns=target_cols, inplace=True)
        train2.drop(columns=target_cols, inplace=True)
        train["target"] = t
        train2["target"] = t

        train = pd.concat([train, train2], ignore_index=True, sort=False)
        train_total = pd.concat([train_total, train], ignore_index=True, sort=False)
        t += 1
    warnings.filterwarnings("default")

    df_total = pd.concat([train_total, df_test], ignore_index=True, sort=False)
    return train_total, df_total


def build_base_train_test(df_total):
    """Build X_train/y_train/X_test/*_cust_ids trước khi gắn lag features."""
    X_train = df_total[~df_total["target"].isnull()]
    y_train = X_train["target"].astype(int)
    X_train = X_train.drop(columns=["target"])

    train_cust_ids = X_train["ncodpers"]
    X_train = X_train.drop(columns=["fecha_dato", "ncodpers"])
    X_train = X_train.values.tolist()

    test_cust_ids = df_total[df_total["target"].isnull()]["ncodpers"].values
    X_test = df_total[df_total["target"].isnull()]
    X_test = X_test.drop(columns=["target"])
    X_test = X_test.drop(columns=["fecha_dato", "ncodpers"])
    X_test = X_test.values.tolist()

    return X_train, y_train, train_cust_ids, X_test, test_cust_ids


def _build_lag_dict(df_slice, non_lag_cols):
    """temp -> dict {ncodpers: [array sản phẩm mỗi tháng, theo thứ tự tăng dần]}"""
    temp = df_slice.drop(columns=non_lag_cols)
    lags = {}
    for row in tqdm(temp.itertuples()):
        cust_id = row[2]
        if cust_id not in lags:
            lags[cust_id] = []
        lags[cust_id].append(np.array(row[3:]).astype(int))
    n_lag_cols = temp.shape[1] - 2
    return lags, n_lag_cols


def _get_lag_k(lag_list, k, n_lag_cols):
    try:
        return list(lag_list[-k])
    except IndexError:
        return [0] * n_lag_cols


def _attach_lags(cust_ids, feature_rows, lags_dict, n_lag_cols):
    """Gắn 5-month lag features vào danh sách feature vector theo từng khách hàng."""
    result = []
    for k, cust_id in enumerate(tqdm(cust_ids)):
        l = lags_dict.get(cust_id, [[0] * n_lag_cols])
        lag_1 = _get_lag_k(l, 1, n_lag_cols)
        lag_2 = _get_lag_k(l, 2, n_lag_cols)
        lag_3 = _get_lag_k(l, 3, n_lag_cols)
        lag_4 = _get_lag_k(l, 4, n_lag_cols)
        lag_5 = _get_lag_k(l, 5, n_lag_cols)
        result.append(np.array(feature_rows[k] + lag_1 + lag_5 + lag_4 + lag_3 + lag_2))
    return np.array(result)


def run():
    with track_stage("feature_engineering") as t:
        df = pd.read_parquet(config.PROCESSED_TRAIN_PARQUET)
        df_test = pd.read_parquet(config.PROCESSED_TEST_PARQUET)

        df, df_test = drop_unused_columns(df, df_test)
        df, df_test = add_days_feature(df, df_test)
        df = add_behavior_lag_flags(df)

        # Lưu lại df ở trạng thái này — predict.py & evaluate.py cần để mask sản phẩm đã sở hữu
        df.to_parquet(config.DF_WITH_BEHAVIOR_PARQUET, index=False)

        target_cols = get_target_cols(df)
        with open(config.TARGET_COLS_JSON, "w") as f:
            json.dump(list(target_cols), f)

        train_total, df_total = build_train_total(df, df_test, target_cols)

        # ---- TÁCH TẬP VALIDATION THEO KHÁCH HÀNG (Tránh Data Leakage) ----
        unique_custs = train_total["ncodpers"].unique()
        np.random.seed(42)
        val_ratio = 0.2
        if len(unique_custs) > 1:
            n_val = min(len(unique_custs) - 1, max(1, int(len(unique_custs) * val_ratio)))
            val_custs_set = set(np.random.choice(unique_custs, size=n_val, replace=False))
            train_custs_set = set(unique_custs) - val_custs_set
        else:
            val_custs_set = set(unique_custs)
            train_custs_set = set(unique_custs)

        # 1. Tập Train (80% khách hàng)
        train_subset = train_total[train_total["ncodpers"].isin(train_custs_set)].copy()
        y_train = train_subset["target"].astype(int)
        train_cust_ids = train_subset["ncodpers"].values
        X_train_base = train_subset.drop(columns=["target", "fecha_dato", "ncodpers"]).values.tolist()

        # 2. Tập Validation (20% khách hàng đại diện để đo MAP@7)
        val_subset = train_total[train_total["ncodpers"].isin(val_custs_set)].drop_duplicates(subset=["ncodpers"]).copy()
        y_val = val_subset["target"].astype(int)
        val_cust_ids = val_subset["ncodpers"].values
        X_val_base = val_subset.drop(columns=["target", "fecha_dato", "ncodpers"]).values.tolist()

        # 3. Ground Truth: Lưu danh sách sản phẩm thực tế khách đã mua mới tại tháng target
        val_ground_truth = {}
        for cust_id in val_custs_set:
            targets = train_total[train_total["ncodpers"] == cust_id]["target"].tolist()
            val_ground_truth[str(cust_id)] = [str(target_cols[idx]) for idx in targets]

        with open(config.VAL_GROUND_TRUTH_JSON, "w") as f:
            json.dump(val_ground_truth, f)

        # 4. Tập Test (lấy từ df_total để đồng bộ đầy đủ các cột feature với train)
        test_part = df_total[df_total["target"].isnull()].copy()
        test_cust_ids = test_part["ncodpers"].values
        test_feature_df = test_part.drop(columns=["target", "fecha_dato", "ncodpers"]).fillna(0)
        X_test_base = test_feature_df.values.tolist()

        # ---- XÂY DỰNG LAG FEATURES CHO TRAIN, VALID VÀ TEST ----
        temp1 = df[(df["fecha_dato"] < config.LAG_TRAIN_CUTOFF) & (df["ncodpers"].isin(train_total["ncodpers"]))]
        train_lags, n_lag_cols = _build_lag_dict(temp1, NON_LAG_COLS)

        temp2 = df[
            (df["fecha_dato"] < config.LAG_TEST_CUTOFF)
            & (df["fecha_dato"] >= config.LAG_TEST_START)
            & (df["ncodpers"].isin(df_test["ncodpers"]))
        ]
        test_lags, n_lag_cols_test = _build_lag_dict(temp2, NON_LAG_COLS)
        assert n_lag_cols == n_lag_cols_test, "Số cột lag giữa train/test lệch nhau"

        print("Đang gắn lag cho X_train...")
        X_train = _attach_lags(train_cust_ids, X_train_base, train_lags, n_lag_cols)

        print("Đang gắn lag cho X_val...")
        X_val = _attach_lags(val_cust_ids, X_val_base, train_lags, n_lag_cols)

        print("Đang gắn lag cho X_test...")
        X_test = _attach_lags(test_cust_ids, X_test_base, test_lags, n_lag_cols_test)

        print(f"X_train shape: {X_train.shape} | y_train shape: {y_train.shape}")
        print(f"X_val shape:   {X_val.shape} | val_cust_ids: {len(val_cust_ids)}")
        print(f"X_test shape:  {X_test.shape}")

        np.save(config.X_TRAIN_NPY, X_train)
        np.save(config.Y_TRAIN_NPY, y_train.to_numpy())
        np.save(config.TRAIN_CUST_IDS_NPY, train_cust_ids)

        np.save(config.X_VAL_NPY, X_val)
        np.save(config.Y_VAL_NPY, y_val.to_numpy())
        np.save(config.VAL_CUST_IDS_NPY, val_cust_ids)

        np.save(config.X_TEST_NPY, X_test)
        np.save(config.TEST_CUST_IDS_NPY, test_cust_ids)

        print(f"Đã lưu toàn bộ artifact feature engineering vào {config.ARTIFACT_DIR}")

        t.log(
            n_target_cols=len(target_cols),
            n_train_rows=X_train.shape[0],
            n_val_rows=X_val.shape[0],
            n_test_rows=X_test.shape[0],
            X_train_shape=list(X_train.shape),
            target_class_balance=y_train.value_counts(normalize=True).round(3).to_dict(),
        )


if __name__ == "__main__":
    run()

