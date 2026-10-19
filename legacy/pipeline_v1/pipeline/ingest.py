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


TOTAL_RAW_TRAIN_ROWS = 13_647_309


def _find_file(filename):
    """Tìm file theo thứ tự: SAMPLES_DIR -> INPUT_DIR -> WORK_DIR."""
    candidates = [
        os.path.join(config.SAMPLES_DIR, filename),
        os.path.join(config.INPUT_DIR, filename),
        os.path.join(config.WORK_DIR, filename),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def load_raw_csv():
    # 1. Chế độ Full Run
    if not config.SAMPLE_ROWS:
        train_csv = _find_file("train_ver2.csv")
        test_csv = _find_file("test_ver2.csv")
        if not train_csv or not test_csv:
            raise FileNotFoundError(f"Không tìm thấy train_ver2.csv hoặc test_ver2.csv trong {config.INPUT_DIR}")
        print(f"Chạy Full Dataset: đọc {train_csv} và {test_csv}...")
        df = pd.read_csv(train_csv, low_memory=False)
        df_test = pd.read_csv(test_csv, low_memory=False)
        return df, df_test

    sample_target = config.SAMPLE_ROWS
    print(f"Chế độ lấy mẫu: mục tiêu ~{sample_target:,} dòng...")

    # 2. Kiểm tra nếu có file sample nạp sẵn khớp với quy mô
    if sample_target <= 10000:
        sample_train = _find_file("train_sample_10k.csv")
        sample_test = _find_file("test_sample_5k.csv")
        if sample_train:
            print(f"Sử dụng file sample 10k có sẵn: {sample_train}")
            df = pd.read_csv(sample_train, nrows=sample_target, low_memory=False)
            test_path = sample_test if sample_test else _find_file("test_ver2.csv")
            df_test = pd.read_csv(test_path, nrows=min(sample_target, 5000), low_memory=False)
            return df, df_test

    if sample_target == 1000000:
        sample_train = _find_file("train_sample_1m.csv")
        sample_test = _find_file("test_sample_1m.csv")
        if sample_train:
            print(f"Sử dụng file sample 1M có sẵn: {sample_train}")
            df = pd.read_csv(sample_train, low_memory=False)
            test_path = sample_test if sample_test else _find_file("test_ver2.csv")
            df_test = pd.read_csv(test_path, low_memory=False)
            return df, df_test

    # 3. Lấy mẫu động (Dynamic Customer Modulo) bảo toàn chuỗi thời gian 17 tháng
    train_csv = _find_file("train_ver2.csv")
    test_csv = _find_file("test_ver2.csv")
    if not train_csv or not test_csv:
        raise FileNotFoundError(f"Không tìm thấy train_ver2.csv hoặc test_ver2.csv trong {config.INPUT_DIR}")

    divisor = max(1, round(TOTAL_RAW_TRAIN_ROWS / sample_target))
    print(f"Lấy mẫu động theo mã khách hàng: ncodpers % {divisor} == 0 (tỷ lệ 1/{divisor})...")

    chunks = []
    for chunk in pd.read_csv(train_csv, chunksize=500000, low_memory=False):
        filtered = chunk[chunk["ncodpers"] % divisor == 0]
        chunks.append(filtered)
    df = pd.concat(chunks, ignore_index=True)

    # Lấy mẫu test tương ứng theo cùng tỷ lệ khách hàng
    df_test_full = pd.read_csv(test_csv, low_memory=False)
    df_test = df_test_full[df_test_full["ncodpers"] % divisor == 0].reset_index(drop=True)
    if len(df_test) == 0:
        df_test = df_test_full.iloc[: min(len(df_test_full), max(1000, sample_target // 10))]

    # Tự động lưu cache tập mẫu vào SAMPLES_DIR để các lần chạy sau tải tức thì
    try:
        os.makedirs(config.SAMPLES_DIR, exist_ok=True)
        cache_name = "train_sample_1m.csv" if sample_target == 1000000 else f"train_sample_{sample_target}.csv"
        cache_test_name = "test_sample_1m.csv" if sample_target == 1000000 else f"test_sample_{sample_target}.csv"
        cache_train_path = os.path.join(config.SAMPLES_DIR, cache_name)
        cache_test_path = os.path.join(config.SAMPLES_DIR, cache_test_name)
        if not os.path.exists(cache_train_path):
            df.to_csv(cache_train_path, index=False)
            df_test.to_csv(cache_test_path, index=False)
            print(f"Đã lưu cache tập mẫu -> {cache_train_path} ({len(df):,} dòng)")
    except Exception as e:
        print(f"Bỏ qua lưu cache tập mẫu ({e})")

    print(f"Lấy mẫu hoàn tất: train={len(df):,} dòng ({df['ncodpers'].nunique():,} khách), test={len(df_test):,} dòng")
    return df, df_test


def run():
    with track_stage("ingest") as t:
        unzip_raw_files()
        df, df_test = load_raw_csv()

        # Chuẩn hóa các cột object sang string để pyarrow không bị lỗi mixed-type (như cột age)
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = df[col].astype(str)
        for col in df_test.select_dtypes(include=["object"]).columns:
            df_test[col] = df_test[col].astype(str)

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
