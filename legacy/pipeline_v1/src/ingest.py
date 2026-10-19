"""
Ingest module — Santander Product Recommendation (Track DS, Checkpoint 1)

Tách từ notebook EDA để tái sử dụng được (import thay vì copy-paste code
giữa các notebook / dùng lại cho checkpoint 2, 3).

Phạm vi của ingest (KHÔNG bao gồm xử lý missing/outlier/feature engineering
— những việc đó thuộc preprocess, ở bước sau):
    1. Tải file thô từ GCS bucket về máy
    2. Đọc CSV với dtype/encoding đúng, sample khách hàng để tránh crash kernel
    3. Parse ngày tháng & vài feature cơ bản (month, age numeric)

Cách dùng:
    from src.ingest import ingest

    df = ingest(
        bucket_name="TEN-BUCKET-CUA-BAN",
        blob_name="raw/train_ver2.csv",
        project="santander-ds",
    )
"""

from pathlib import Path

import pandas as pd


def _resolve_local_path(path_or_blob: str | Path | None) -> Path | None:
    """Tìm đường dẫn file local tồn tại (hỗ trợ cả khi chạy ở root hoặc trong notebooks/)."""
    if not path_or_blob:
        return None
    p = Path(path_or_blob)
    candidates = [
        p,
        Path("..") / p,
        Path("data") / p,
        Path("..") / "data" / p,
    ]
    for c in candidates:
        if c.exists() and c.is_file() and c.stat().st_size > 0:
            return c
    return None


def download_from_gcs(bucket_name: str | None, blob_name: str, dest_path: str | Path,
                       project: str | None = None) -> Path:
    """Tải 1 file từ GCS bucket về local. Dùng Application Default Credentials
    (chạy `gcloud auth application-default login` trước nếu chưa login).
    Nếu file đã tồn tại và có dữ liệu thì tái sử dụng, không tải lại."""
    dest_path = Path(dest_path)

    local_file = _resolve_local_path(dest_path)
    if local_file is not None:
        print(f"[Ingest] File da co san tai '{local_file}' ({local_file.stat().st_size / (1024**2):.1f} MB), bo qua tai lai.")
        return local_file

    if not bucket_name or bucket_name == "TEN-BUCKET-CUA-BAN":
        raise ValueError(
            f"Khong tim thay file local tai '{dest_path}' va BUCKET_NAME chua duoc cau hinh hop le ('{bucket_name}'). "
            "Vui long dat file vao thu muc data/ hoac cap nhat BUCKET_NAME that."
        )

    from google.cloud import storage

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    client = storage.Client(project=project)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.download_to_filename(str(dest_path))
    return dest_path


def peek_schema(bucket_name: str | None, blob_name: str, project: str | None = None,
                 nrows: int = 10, local_path: str | Path | None = None) -> pd.DataFrame:
    """Đọc thử vài dòng đầu trực tiếp để kiểm tra schema.
    Ưu tiên đọc file local nếu đã có sẵn trong data/ hoặc local_path.
    Nếu chưa có ở local, mới kết nối tới GCS."""
    target_path = local_path or blob_name
    local_file = _resolve_local_path(target_path)
    if local_file is not None:
        print(f"[Ingest] Doc {nrows} dong thu nghiem tu file local: {local_file}")
        return pd.read_csv(local_file, nrows=nrows, low_memory=False)

    if not bucket_name or bucket_name == "TEN-BUCKET-CUA-BAN":
        raise ValueError(
            f"Khong tim thay file local cho '{blob_name}' va BUCKET_NAME chua duoc cau hinh hop le ('{bucket_name}'). "
            "Vui long dat file vao data/ hoac cau hinh bucket GCS that."
        )

    from google.cloud import storage

    client = storage.Client(project=project)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    with blob.open("rb") as f:
        return pd.read_csv(f, nrows=nrows, low_memory=False)


def load_raw(csv_path: str | Path, limit_rows: int | None = None,
             limit_people: int | None = None, random_state: int = 42) -> pd.DataFrame:
    """Đọc CSV với dtype cố định cho các cột hay bị suy sai kiểu (mixed type
    warning), sample bớt khách hàng nếu limit_people được set để tránh crash
    kernel trên máy yếu."""
    local_file = _resolve_local_path(csv_path) or Path(csv_path)

    df = pd.read_csv(
        local_file,
        dtype={"sexo": str, "ind_nuevo": str, "ult_fec_cli_1t": str, "indext": str},
        nrows=limit_rows,
        low_memory=False,
    )

    if limit_people is not None:
        unique_ids = pd.Series(df["ncodpers"].unique())
        n_sample = min(limit_people, len(unique_ids))
        sampled_ids = unique_ids.sample(n=n_sample, random_state=random_state)
        df = df[df["ncodpers"].isin(sampled_ids)].copy()

    return df


def parse_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    """Parse ngày tháng (fecha_dato, fecha_alta), thêm cột month, ép age về
    numeric. Đây là bước chuẩn hoá kiểu dữ liệu cơ bản, KHÔNG phải impute/
    xử lý outlier (thuộc preprocess, không phải ingest)."""
    df = df.copy()
    df["fecha_dato"] = pd.to_datetime(df["fecha_dato"], format="%Y-%m-%d")
    df["fecha_alta"] = pd.to_datetime(df["fecha_alta"], format="%Y-%m-%d")
    df["month"] = df["fecha_dato"].dt.month
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    return df


def ingest(bucket_name: str, blob_name: str, project: str | None = None,
           local_raw_path: str | Path = "data/raw/train_ver2.csv",
           limit_rows: int | None = 10_000_000, limit_people: int | None = 10_000,
           random_state: int = 42) -> pd.DataFrame:
    """Chạy trọn pipeline ingest: download GCS -> đọc CSV (sample) -> parse
    basic features. Dùng khi chỉ cần gọi 1 hàm (script/CLI); trong notebook
    có thể gọi 3 hàm con riêng lẻ để giữ từng bước tường minh."""
    csv_path = download_from_gcs(bucket_name, blob_name, local_raw_path, project=project)
    df = load_raw(csv_path, limit_rows=limit_rows, limit_people=limit_people,
                   random_state=random_state)
    df = parse_basic_features(df)
    return df


if __name__ == "__main__":
    BUCKET_NAME = "uit-thien-santander-ds"
    PROJECT = "santander-ds"
    TRAIN_BLOB = "raw/train_ver2.csv"

    df = ingest(BUCKET_NAME, TRAIN_BLOB, project=PROJECT)
    print(f"Ingested shape: {df.shape}")
    print(f"Số khách hàng: {df['ncodpers'].nunique()}")
    print(f"Khoảng thời gian: {df['fecha_dato'].min()} -> {df['fecha_dato'].max()}")
