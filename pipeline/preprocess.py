"""
STAGE 2 — PREPROCESS
Giảm memory footprint, xử lý null cho từng cột, label-encode cột categorical.
Input: parquet từ ingest.py. Output: parquet đã xử lý + label encoders (pickle).

Chạy độc lập: python preprocess.py
"""
import pickle

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

import config
from tracking import track_stage

CATEGORICAL_COLS = [
    "ind_empleado", "pais_residencia", "sexo", "ind_nuevo", "indrel_1mes",
    "tiprel_1mes", "indresi", "indext", "conyuemp", "canal_entrada",
    "indfall", "nomprov", "segmento", "indrel", "ind_actividad_cliente",
]

INDREL_1MES_MAP = {
    1.0: "1", "1.0": "1", "1": "1",
    "3.0": "3", "P": "P", 3.0: "3",
    2.0: "2", "3": "3", "2.0": "2",
    "4.0": "4", "4": "4", "2": "2",
}


def reduce_memory_usage(df, verbose=True):
    numerics = ["int8", "int16", "int32", "int64", "float16", "float32", "float64"]
    start_mem = df.memory_usage().sum() / 1024 ** 2
    for col in df.columns:
        col_type = df[col].dtypes
        if col_type in numerics:
            c_min = df[col].min()
            c_max = df[col].max()
            if str(col_type)[:3] == "int":
                if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                    df[col] = df[col].astype(np.int8)
                elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                    df[col] = df[col].astype(np.int16)
                elif c_min > np.iinfo(np.int32).min and c_max < np.iinfo(np.int32).max:
                    df[col] = df[col].astype(np.int32)
                elif c_min > np.iinfo(np.int64).min and c_max < np.iinfo(np.int64).max:
                    df[col] = df[col].astype(np.int64)
            else:
                if c_min > np.finfo(np.float32).min and c_max < np.finfo(np.float32).max:
                    df[col] = df[col].astype(np.float32)
                else:
                    df[col] = df[col].astype(np.float64)
    end_mem = df.memory_usage().sum() / 1024 ** 2
    if verbose:
        print("Mem. usage decreased to {:.2f} Mb ({:.1f}% reduction)".format(
            end_mem, 100 * (start_mem - end_mem) / start_mem))
    return df


def clean_age(df):
    df["age"] = pd.to_numeric(df["age"], errors="coerce").astype(float)
    n_young = int((df["age"] < 18).sum())
    n_old = int((df["age"] > 100).sum())
    print(f"Outliers: {n_young} tuổi < 18, {n_old} tuổi > 100")

    mean_young = df.loc[(df.age >= 18) & (df.age <= 30), "age"].mean()
    mean_mid = df.loc[(df.age >= 30) & (df.age <= 100), "age"].mean()

    df.loc[df.age < 18, "age"] = mean_young
    df.loc[df.age > 100, "age"] = mean_mid
    df["age"] = df["age"].fillna(df["age"].mean())
    df["age"] = df["age"].replace([np.inf, -np.inf], np.nan).fillna(40).round().astype(int)
    return df


def clean_antiguedad(df):
    df["fecha_dato"] = pd.to_datetime(df["fecha_dato"], errors="coerce")
    df["fecha_alta"] = pd.to_datetime(df["fecha_alta"], errors="coerce")
    df["antiguedad"] = pd.to_numeric(df["antiguedad"], errors="coerce")
    # NOTE: notebook gốc tính antiguedad_calc nhưng không gán ngược lại vào
    # df["antiguedad"] — giữ nguyên hành vi này, antiguedad vẫn còn NaN sau bước này
    # nếu muốn dùng antiguedad_calc để fill thì cần bổ sung dòng gán.
    _antiguedad_calc = (
        (df["fecha_dato"].dt.year - df["fecha_alta"].dt.year) * 12
        + (df["fecha_dato"].dt.month - df["fecha_alta"].dt.month)
    )
    print(f"fecha_dato null sau convert: {df['fecha_dato'].isnull().sum()}")
    print(f"fecha_alta null sau convert: {df['fecha_alta'].isnull().sum()}")
    return df


def clean_renta(df, df_test):
    df["renta"] = pd.to_numeric(df["renta"], errors="coerce")
    df_test["renta"] = pd.to_numeric(df_test["renta"], errors="coerce")

    mean_gross_classified_df = df.groupby(["nomprov", "segmento"])["renta"].mean().reset_index()
    mean_gross_classified_df.rename(columns={"renta": "mean_gross_classified"}, inplace=True)

    overall_renta = df["renta"].mean()
    mean_gross_classified_df["mean_gross_classified"] = (
        mean_gross_classified_df["mean_gross_classified"].fillna(overall_renta)
    )

    def fill_renta_vectorized(data):
        data = data.merge(mean_gross_classified_df, on=["nomprov", "segmento"], how="left")
        data["renta"] = data["renta"].fillna(data["mean_gross_classified"])
        data["renta"] = data["renta"].fillna(overall_renta)
        data.drop(columns=["mean_gross_classified"], inplace=True)
        return data

    df = fill_renta_vectorized(df)
    df_test = fill_renta_vectorized(df_test)
    return df, df_test


def clean_nomina_flags(df):
    df = df.sort_values(["ncodpers", "fecha_dato"])
    for col in ["ind_nomina_ult1", "ind_nom_pens_ult1"]:
        df[col] = df.groupby("ncodpers")[col].ffill()
        df[col] = df[col].fillna(0)
    return df


def clean_indrel_1mes(df, df_test):
    for frame in (df, df_test):
        frame["indrel_1mes"] = frame["indrel_1mes"].fillna("P")
        frame["indrel_1mes"] = frame["indrel_1mes"].apply(lambda x: INDREL_1MES_MAP.get(x, x))
        frame["indrel_1mes"] = frame["indrel_1mes"].astype("category")
    return df, df_test


def clean_ind_nuevo(df):
    df["ind_nuevo"] = pd.to_numeric(df["ind_nuevo"], errors="coerce")
    n_missing = df["ind_nuevo"].isnull().sum()
    print(f"Missing: {n_missing}")
    if n_missing > 0:
        months_active = df.loc[df["ind_nuevo"].isnull(), :].groupby("ncodpers").size()
        print(f"Max số tháng active trong nhóm thiếu dữ liệu: {months_active.max()}")
        df.loc[df["ind_nuevo"].isnull(), "ind_nuevo"] = 1
    return df


def clean_indrel(df, df_test):
    for frame in (df, df_test):
        frame["indrel"] = frame["indrel"].astype(float)
        frame["indrel"] = frame["indrel"].fillna(1.0)
    return df, df_test


def clean_ind_actividad_cliente(df, df_test):
    df["ind_actividad_cliente"] = df["ind_actividad_cliente"].astype(float)
    df_test["ind_actividad_cliente"] = df_test["ind_actividad_cliente"].astype(float)
    return df, df_test


def clean_indfall(df, df_test):
    df["indfall"] = df["indfall"].fillna("N")
    df_test["indfall"] = df_test["indfall"].fillna("N")
    return df, df_test


def label_encode_categoricals(df, df_test):
    label_encoders = {}
    for col in CATEGORICAL_COLS:
        le = LabelEncoder()
        df[col] = df[col].astype(str)
        df_test[col] = df_test[col].astype(str)

        le.fit(df[col])
        df[col] = le.transform(df[col])

        mapping = dict(zip(le.classes_, le.transform(le.classes_)))
        df_test[col] = df_test[col].map(mapping).fillna(-1).astype(int)

        label_encoders[col] = le
    return df, df_test, label_encoders


def run():
    with track_stage("preprocess") as t:
        df = pd.read_parquet(config.RAW_TRAIN_PARQUET)
        df_test = pd.read_parquet(config.RAW_TEST_PARQUET)
        mem_before = round(df.memory_usage().sum() / 1024 ** 2, 1)

        df = reduce_memory_usage(df)
        df_test = reduce_memory_usage(df_test)
        mem_after_reduce = round(df.memory_usage().sum() / 1024 ** 2, 1)

        df = clean_age(df)
        df = clean_antiguedad(df)
        df, df_test = clean_renta(df, df_test)
        df = clean_nomina_flags(df)
        df, df_test = clean_indrel_1mes(df, df_test)
        df = clean_ind_nuevo(df)
        df, df_test = clean_indrel(df, df_test)
        df, df_test = clean_ind_actividad_cliente(df, df_test)
        df, df_test = clean_indfall(df, df_test)

        df, df_test, label_encoders = label_encode_categoricals(df, df_test)

        df.to_parquet(config.PROCESSED_TRAIN_PARQUET, index=False)
        df_test.to_parquet(config.PROCESSED_TEST_PARQUET, index=False)
        with open(config.FEATURE_LABEL_ENCODERS_PKL, "wb") as f:
            pickle.dump(label_encoders, f)

        print(f"train processed shape: {df.shape} -> {config.PROCESSED_TRAIN_PARQUET}")
        print(f"test processed shape:  {df_test.shape} -> {config.PROCESSED_TEST_PARQUET}")

        t.log(
            rows=df.shape[0], cols=df.shape[1],
            test_rows=df_test.shape[0],
            mem_before_mb=mem_before, mem_after_reduce_mb=mem_after_reduce,
            null_total_after=int(df.isnull().sum().sum()),
        )


if __name__ == "__main__":
    run()
