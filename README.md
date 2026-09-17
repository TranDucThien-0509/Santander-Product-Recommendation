# Santander pipeline — tách từ notebook

Tách `ban-lam-lai (1).ipynb` (61 cell) thành 5 stage độc lập, mỗi stage
đọc/ghi artifact qua `artifacts/` để không phụ thuộc biến trong RAM của
notebook — chạy lại 1 stage không cần chạy lại toàn bộ.

## Cấu trúc

```
config.py               # đường dẫn + hằng số dùng chung
tracking.py              # ghi log tiến trình (shape, thời gian, metric) mỗi stage
ingest.py                # giải nén + đọc CSV -> parquet
preprocess.py             # reduce memory, xử lý null, label encode
feature_engineering.py    # drop cột, feature 'days', behavior lag, target set, 5-month lag
train.py                  # (tùy chọn) hyperparam search + train XGBoost cuối
predict.py                 # predict + mask sản phẩm đã sở hữu + xuất sub.csv
run_pipeline.py             # chạy tuần tự cả 5 stage
requirements.txt
```

## Theo dõi pipeline (tracking)

Mỗi stage tự động ghi 1 dòng JSON vào `artifacts/pipeline_run_log.jsonl`
khi chạy xong (hoặc khi lỗi giữa chừng) — không cần MLflow/W&B hay
server nào, chỉ là 1 file text append-only. Mỗi dòng gồm: tên stage,
timestamp, thời gian chạy, status (success/failed), và các số liệu
riêng của stage đó (số dòng, memory, params, metric...).

Xem log của lần chạy gần nhất:
```bash
tail -n 5 artifacts/pipeline_run_log.jsonl | python3 -m json.tool --json-lines
```

Ví dụ nội dung 1 dòng log (đã format lại cho dễ đọc):
```json
{
  "stage": "train",
  "timestamp": "2026-09-16T10:00:00+00:00",
  "duration_sec": 842.3,
  "status": "success",
  "params": {"max_depth": 3, "n_estimators": 50, "...": "..."},
  "n_train_rows": 123456,
  "train_set_log_loss": 0.42
}
```

Lưu ý: `train_set_log_loss` tính trên chính tập train, không phải tập
validation riêng — chỉ để biết model có học được gì qua các lần chạy,
không dùng để đánh giá khả năng tổng quát hóa.

Nếu sau này muốn có dashboard/so sánh trực quan giữa các lần chạy thay
vì đọc file JSON tay, đây chính là chỗ dễ nâng cấp lên MLflow nhất —
chỉ cần thay lệnh `t.log(...)` bằng `mlflow.log_metric(...)` /
`mlflow.log_param(...)`, cấu trúc stage giữ nguyên.

## Chạy

Từng bước riêng (khuyên dùng — tránh mất hết khi 1 bước lỗi/kernel restart):
```bash
python ingest.py
python preprocess.py
python feature_engineering.py
python train.py
python predict.py
```

Hoặc chạy hết 1 lần:
```bash
python run_pipeline.py
```

Trên Kaggle: mặc định `config.py` dùng `/kaggle/input/...` và
`/kaggle/working/`. Chạy nơi khác thì set biến môi trường:
```bash
export SANTANDER_INPUT_DIR=/path/to/input
export SANTANDER_WORK_DIR=/path/to/working
```

## Khác biệt so với notebook gốc (không đổi kết quả cuối, chỉ dọn code)

- Cell 49 và cell 51 (build X_train/y_train/X_test trước khi thêm lag)
  bị lặp lại y hệt ngay trong cell 53 — bản tách chỉ build 1 lần.
- Biến `le` trong notebook gốc bị dùng lại 2 lần cho 2 mục đích khác
  nhau (encoder cột categorical ở cell 29, rồi encoder cho target ở
  cell 58) — đổi tên thành `feature_label_encoders` (dict) và
  `target_encoder` (rõ ràng, tránh nhầm lẫn khi sửa code sau này).

## Cần xem lại (giữ nguyên hành vi gốc, chỉ ghi chú lại — chưa sửa)

- `preprocess.py::clean_antiguedad`: tính `antiguedad_calc` nhưng
  không gán ngược vào `df["antiguedad"]` — cột này vẫn còn NaN sau
  bước xử lý (giống hệt notebook gốc).
- `train.py`: hyperparameter search chỉ chạy trên LightGBM, nhưng
  model cuối lại là XGBoost với params hardcode tay — không lấy từ
  kết quả search (search hiện không ảnh hưởng model cuối).
- `predict.py::build_owned_products_mask`: dùng slice cột theo tên
  (`'ind_cco_fin_ult1':'ind_recibo_ult1'`) để lấy đúng 24 cột sản
  phẩm — cách này phụ thuộc thứ tự cột gốc, dễ vỡ nếu sau này chèn
  thêm cột mới vào giữa dải đó. An toàn hơn thì đổi sang
  `row[target_cols]`.
