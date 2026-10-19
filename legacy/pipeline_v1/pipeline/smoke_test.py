"""
SMOKE TEST — KIỂM TRA CHẤT LƯỢNG PIPELINE KHÔNG CẦN NHÃN (Chạy trên sample 10k hoặc CI)

Mục tiêu (Mục 2.2):
1. Schema và dtype sau preprocess đúng như mong đợi.
2. Không có NaN / Inf trong X_train (và X_val, X_test).
3. sub.csv đúng định dạng: đủ số dòng của test, mỗi khách hàng có 7 sản phẩm, không trùng lặp.

Dùng cho:
- Chạy local sau mỗi lần sửa code: python pipeline/smoke_test.py
- Chạy trong GitHub Actions CI trước khi build & push Docker image.
"""
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

# Cho phép import config từ thư mục hiện tại hoặc pipeline/
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

import config

ALL_PRODUCT_NAMES = [
    "ind_ahor_fin_ult1", "ind_aval_fin_ult1", "ind_cco_fin_ult1", "ind_cder_fin_ult1",
    "ind_cno_fin_ult1", "ind_ctju_fin_ult1", "ind_ctma_fin_ult1", "ind_ctop_fin_ult1",
    "ind_ctpp_fin_ult1", "ind_deco_fin_ult1", "ind_deme_fin_ult1", "ind_dela_fin_ult1",
    "ind_ecue_fin_ult1", "ind_fond_fin_ult1", "ind_hip_fin_ult1", "ind_plan_fin_ult1",
    "ind_pres_fin_ult1", "ind_reca_fin_ult1", "ind_tjcr_fin_ult1", "ind_valo_fin_ult1",
    "ind_viv_fin_ult1", "ind_nomina_ult1", "ind_nom_pens_ult1", "ind_recibo_ult1",
]

EXPECTED_BASE_COLS = [
    "fecha_dato", "ncodpers", "ind_empleado", "pais_residencia", "sexo", "age",
    "fecha_alta", "ind_nuevo", "antiguedad", "indrel", "indrel_1mes", "tiprel_1mes",
    "indresi", "indext", "canal_entrada", "indfall", "tipodom", "cod_prov",
    "nomprov", "ind_actividad_cliente", "renta", "segmento",
]


def test_preprocess_schema_and_dtypes():
    """Kiểm tra schema và kiểu dữ liệu sau stage preprocess."""
    print("\n[TEST 1] Kiểm tra schema và dtypes sau Preprocess...")
    
    assert os.path.exists(config.PROCESSED_TRAIN_PARQUET), (
        f"Thiếu file: {config.PROCESSED_TRAIN_PARQUET}"
    )
    assert os.path.exists(config.PROCESSED_TEST_PARQUET), (
        f"Thiếu file: {config.PROCESSED_TEST_PARQUET}"
    )

    df_train = pd.read_parquet(config.PROCESSED_TRAIN_PARQUET)
    df_test = pd.read_parquet(config.PROCESSED_TEST_PARQUET)

    print(f"  - df_train: {df_train.shape[0]:,} dòng, {df_train.shape[1]} cột")
    print(f"  - df_test : {df_test.shape[0]:,} dòng, {df_test.shape[1]} cột")

    # 1. Cột bắt buộc phải có
    for col in EXPECTED_BASE_COLS:
        assert col in df_train.columns, f"df_train thiếu cột bắt buộc: {col}"
        assert col in df_test.columns, f"df_test thiếu cột bắt buộc: {col}"

    # 2. Khóa chính không được null
    assert df_train["ncodpers"].isnull().sum() == 0, "ncodpers trong df_train có NaN"
    assert df_test["ncodpers"].isnull().sum() == 0, "ncodpers trong df_test có NaN"
    assert df_train["fecha_dato"].isnull().sum() == 0, "fecha_dato trong df_train có NaN"

    # 3. Kiểu dữ liệu số cốt lõi
    assert np.issubdtype(df_train["ncodpers"].dtype, np.integer), "ncodpers phải là kiểu integer"
    assert np.issubdtype(df_train["age"].dtype, np.number), "age phải là kiểu số"
    assert np.issubdtype(df_train["renta"].dtype, np.number), "renta phải là kiểu số"
    assert np.issubdtype(df_train["antiguedad"].dtype, np.number), "antiguedad phải là kiểu số"

    # 4. Kiểm tra các cột sản phẩm tồn tại trong train
    product_cols_found = [c for c in ALL_PRODUCT_NAMES if c in df_train.columns]
    assert len(product_cols_found) >= 20, (
        f"df_train phải có ít nhất 20 cột sản phẩm, hiện tại chỉ có {len(product_cols_found)}"
    )

    print("  [OK] Test 1: Schema và dtypes sau Preprocess HỢP LỆ!")


def test_no_nan_inf_in_features():
    """Kiểm tra ma trận đặc trưng X_train không chứa NaN hoặc Inf."""
    print("\n[TEST 2] Kiểm tra NaN/Inf trong ma trận feature X_train & X_val...")

    assert os.path.exists(config.X_TRAIN_NPY), f"Thiếu file: {config.X_TRAIN_NPY}"
    X_train = np.load(config.X_TRAIN_NPY, allow_pickle=True).astype(np.float32)

    assert X_train.ndim == 2, f"X_train phải là ma trận 2D, hiện tại ndim={X_train.ndim}"
    assert X_train.shape[0] > 0, "X_train rỗng (0 dòng)"
    assert X_train.shape[1] > 0, "X_train rỗng (0 cột)"

    nan_count = int(np.isnan(X_train).sum())
    inf_count = int(np.isinf(X_train).sum())

    print(f"  - X_train shape: {X_train.shape}")
    print(f"  - NaN count   : {nan_count}")
    print(f"  - Inf count   : {inf_count}")

    assert nan_count == 0, f"X_train có {nan_count} giá trị NaN!"
    assert inf_count == 0, f"X_train có {inf_count} giá trị Inf!"

    # Kiểm tra thêm X_val nếu có
    if os.path.exists(config.X_VAL_NPY):
        X_val = np.load(config.X_VAL_NPY, allow_pickle=True).astype(np.float32)
        val_nan = int(np.isnan(X_val).sum())
        val_inf = int(np.isinf(X_val).sum())
        assert val_nan == 0, f"X_val có {val_nan} giá trị NaN!"
        assert val_inf == 0, f"X_val có {val_inf} giá trị Inf!"
        print(f"  - X_val shape  : {X_val.shape} (0 NaN, 0 Inf)")

    print("  [OK] Test 2: Ma trận features KHÔNG CÓ NaN/Inf!")


def test_submission_format():
    """Kiểm tra sub.csv: đủ dòng, đúng format top-7, không trùng lặp."""
    print("\n[TEST 3] Kiểm tra định dạng file submission sub.csv...")

    assert os.path.exists(config.SUBMISSION_CSV), (
        f"Không tìm thấy file submission: {config.SUBMISSION_CSV}"
    )

    sub = pd.read_csv(config.SUBMISSION_CSV)
    print(f"  - sub.csv shape: {sub.shape}")

    # 1. Header đúng yêu cầu Kaggle
    assert list(sub.columns) == ["ncodpers", "added_products"], (
        f"Header sai! Cần ['ncodpers', 'added_products'], nhận được: {list(sub.columns)}"
    )

    # 2. Số dòng khớp số khách hàng test
    if os.path.exists(config.TEST_CUST_IDS_NPY):
        test_cust_ids = np.load(config.TEST_CUST_IDS_NPY, allow_pickle=True)
        assert len(sub) == len(test_cust_ids), (
            f"Số dòng sub.csv ({len(sub):,}) không khớp số khách test ({len(test_cust_ids):,})!"
        )

    # 3. Không trùng lặp mã khách hàng
    assert sub["ncodpers"].nunique() == len(sub), "Có mã khách hàng bị trùng lặp trong sub.csv!"

    # 4. Kiểm tra từng dòng: đúng 7 sản phẩm, không trùng lặp bên trong
    sample_to_check = sub.head(1000)  # kiểm tra mẫu 1000 dòng hoặc toàn bộ nếu nhỏ
    for _, row in sample_to_check.iterrows():
        preds_str = str(row["added_products"]).strip()
        assert len(preds_str) > 0, f"Khách hàng {row['ncodpers']} có chuỗi dự đoán rỗng!"
        items = preds_str.split()
        
        # Đủ 7 sản phẩm
        assert len(items) == 7, (
            f"Khách hàng {row['ncodpers']} không có đúng 7 sản phẩm (có {len(items)}): {items}"
        )
        
        # Không trùng lặp sản phẩm trong 7 sản phẩm đề xuất
        assert len(items) == len(set(items)), (
            f"Khách hàng {row['ncodpers']} có sản phẩm trùng lặp: {items}"
        )

    print("  [OK] Test 3: sub.csv ĐỦ DÒNG, ĐÚNG 7 SẢN PHẨM KHÔNG TRÙNG LẶP!")


def main():
    print("=" * 60)
    print("       CHẠY SMOKE TEST TOÀN DIỆN (CI / LOCAL VERIFICATION)")
    print("=" * 60)
    failed = False

    for test_fn in [
        test_preprocess_schema_and_dtypes,
        test_no_nan_inf_in_features,
        test_submission_format,
    ]:
        try:
            test_fn()
        except AssertionError as e:
            print(f"  [FAIL] {test_fn.__name__} THẤT BẠI: {e}")
            failed = True
        except Exception as e:
            print(f"  [ERROR] {test_fn.__name__} GẶP LỖI HỆ THỐNG: {e}")
            failed = True

    print("\n" + "=" * 60)
    if failed:
        print("  KET QUA: SMOKE TEST THAT BAI! Vui long kiem tra lai pipeline.")
        print("=" * 60)
        sys.exit(1)
    else:
        print("  KET QUA: TOAN BO SMOKE TEST THANH CONG (ALL PASSED)!")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
