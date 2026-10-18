# MLflow tracking

## Local

Cài `requirements.txt`, thêm vào config local (giữ nguyên các trường khác):

```json
"tracking": {
  "enabled": true,
  "tracking_uri": null,
  "experiment_name": "santander-event-v2",
  "artifact_location": null,
  "log_models": false
}
```

Chạy pipeline như cũ. Khi URI null và không có `MLFLOW_TRACKING_URI`, database nằm ở `<work_dir>/mlflow/tracking.db`; artifacts nằm ở `<work_dir>/mlflow/artifacts`. Mở UI bằng đường dẫn tuyệt đối tương ứng:

```powershell
python -m mlflow ui --backend-store-uri "sqlite:///C:/absolute/work/mlflow/tracking.db" --host 127.0.0.1 --port 5000
```

Mở http://127.0.0.1:5000. Mỗi pipeline có một parent run và một child run cho từng ablation variant. `mlflow_tracking.json` trong thư mục run lưu IDs và trạng thái. Run lỗi được đánh dấu FAILED; lỗi tracking cũng làm pipeline thất bại để không báo thành công khi chưa ghi được kết quả. Mặc định tracking tắt, config cũ không có trường tracking vẫn chạy được.

Metrics gồm validation/test aggregate và theo origin, forecast audit, thời gian và peak RSS của feature build/ranker. Đây là temporal development backtest, chưa phải holdout độc lập hay điểm Kaggle. JSON config, phiên bản thư viện, input/feature manifest và audit được lưu theo allowlist; không gửi raw CSV, features parquet hoặc prediction theo khách hàng lên MLflow. Khóa secret và credential trong URL bị che trước khi ghi JSON/params.

`log_models=true` thêm pickle của evaluation model và forecast model nếu có. Đây là file artifact; chưa có MLflow pyfunc, Model Registry hoặc serving endpoint. Chỉ load pickle từ nguồn tin cậy. Model evaluation và model refit để forecast được lưu riêng.

## Server / Vertex

Đặt `tracking.tracking_uri` hoặc environment `MLFLOW_TRACKING_URI` tới HTTP(S) tracking server. Server quản lý SQL backend và artifact store; chỉ cấu hình `artifact_location` khi bạn thực sự muốn override vị trí experiment mới. Nếu experiment đã tồn tại, vị trí artifacts giữ nguyên theo experiment đó. Dùng biến môi trường/secret chuẩn MLflow cho authentication, không đưa credential vào config Git.

Worker cần truy cập được cả tracking server và artifact store mà server cấu hình. Không dùng SQLite trên GCS FUSE `/gcs/`; dùng local disk cho SQLite hoặc tracking server cho Vertex. Chưa triển khai tracking server trên GCP trong thay đổi này.

## Import kết quả cũ, không train lại

Chuẩn bị bản sao local giữ nguyên cấu trúc run: `config.resolved.json`, `completed.json`, `comparison.json`, các JSON ở root và `<variant>/validation_metrics.json`, `test_metrics.json`, `forecast_audit.json`, `evaluation_model/feature_manifest.json`, `forecast_model/feature_manifest.json` nếu có. Không cần tải features hoặc CSV. CLI nhận thư mục local, không tự tải GCS:

```powershell
python -m pipeline.import_mlflow --run-dir "C:/absolute/copied-run" --tracking-uri "sqlite:///C:/absolute/mlflow/tracking.db" --artifact-location "file:///C:/absolute/mlflow/artifacts" --source-uri "gs://bucket/path/runs/original-run" --source-code-sha ORIGINAL_SHA
```

Các run được gắn `tracking.mode=historical_import`, URI gốc và revision gốc. Thời gian MLflow là thời điểm import; tên run gốc giữ mốc thời gian chạy, thời gian xử lý lấy từ resource metrics gốc. Import lặp lại cùng source URI trong cùng experiment trả về parent FINISHED đã có. Import thất bại có thể thử lại; không tự hợp nhất các run đang import đồng thời. Chỉ import source có completion manifest thành công, đủ metrics và variant khớp comparison. Dùng `--log-models` khi đã tải model và muốn lưu thêm pickle.

Các cloud run sample/full trong [CLOUD_RUNS.md](CLOUD_RUNS.md) diễn ra trước tích hợp MLflow; import không có nghĩa đã chạy lại full data với code tracking mới.
