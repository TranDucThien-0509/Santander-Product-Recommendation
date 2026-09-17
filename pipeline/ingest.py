"""
STAGE 1 — INGEST
Giải nén file zip từ Kaggle input, đọc train_ver2.csv / test_ver2.csv,
lưu ra parquet để các stage sau đọc nhanh và giữ nguyên dtype.

Chạy độc lập: python ingest.py
"""
import os
import zipfile
import pandas as pd

import config
from tracking import track_stage


def unzip_raw_files():
    # Kiểm tra nếu file CSV đã có sẵn ở WORK_DIR hoặc INPUT_DIR thì không cần unzip
    train_work = os.path.join(config.WORK_DIR, "train_ver2.csv")
    train_input = os.path.join(config.INPUT_DIR, "train_ver2.csv")
    if os.path.exists(train_work) or os.path.exists(train_input):
        print("File CSV đã có sẵn, bỏ qua bước giải nén.")
        return

    for zip_file in config.ZIP_FILES:
        zip_path = os.path.join(config.INPUT_DIR, zip_file)
        if os.path.exists(zip_path):
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(config.WORK_DIR)
            print(f"Đã giải nén: {zip_file}")
        else:
            print(f"Không tìm thấy file zip '{zip_path}', bỏ qua.")


def load_raw_csv():
    train_sample = os.path.join(config.INPUT_DIR, "train_sample_10k.csv")
    test_sample = os.path.join(config.INPUT_DIR, "test_sample_5k.csv")

    if config.SAMPLE_ROWS and os.path.exists(train_sample):
        train_csv = train_sample
        test_csv = test_sample if os.path.exists(test_sample) else os.path.join(config.INPUT_DIR, "test_ver2.csv")
    else:
        train_csv = os.path.join(config.WORK_DIR, "train_ver2.csv")
        if not os.path.exists(train_csv):
            train_csv = os.path.join(config.INPUT_DIR, "train_ver2.csv")

        test_csv = os.path.join(config.WORK_DIR, "test_ver2.csv")
        if not os.path.exists(test_csv):
            test_csv = os.path.join(config.INPUT_DIR, "test_ver2.csv")

    print(f"Đang đọc train: {train_csv} (sample={config.SAMPLE_ROWS})...")
    df = pd.read_csv(train_csv, nrows=config.SAMPLE_ROWS, low_memory=False)

    test_nrows = min(config.SAMPLE_ROWS, 5000) if config.SAMPLE_ROWS else None
    print(f"Đang đọc test: {test_csv} (sample={test_nrows})...")
    df_test = pd.read_csv(test_csv, nrows=test_nrows, low_memory=False)
    return df, df_test


def run():
    with track_stage("ingest") as t:
        unzip_raw_files()
        df, df_test = load_raw_csv()

        df.to_parquet(config.RAW_TRAIN_PARQUET, index=False)
        df_test.to_parquet(config.RAW_TEST_PARQUET, index=False)

        print(f"train shape: {df.shape} -> {config.RAW_TRAIN_PARQUET}")
        print(f"test shape:  {df_test.shape} -> {config.RAW_TEST_PARQUET}")

        t.log(
            train_rows=df.shape[0], train_cols=df.shape[1],
            test_rows=df_test.shape[0], test_cols=df_test.shape[1],
            train_mem_mb=round(df.memory_usage().sum() / 1024 ** 2, 1),
        )


if __name__ == "__main__":
    run()
