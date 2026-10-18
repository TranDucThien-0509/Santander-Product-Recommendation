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

## Kết quả kiểm chứng tích hợp — 2026-10-18

- MLflow 3.17.1 trên Windows, Python 3.12: 16 synthetic tests pass. Test SQLite dùng NullPool để đóng file trước khi dọn thư mục tạm trên Windows.
- Chạy trực tiếp sample cố định 10.000 khách / 143.126 snapshots / 17 tháng, các nhóm feature bật, refit forecast bật. Run hoàn thành với MLflow enabled; validation MAP@7_all 0.023296491409289674, test 0.025515484772693834; 9.758 forecast, 0 fallback và 0 ownership violations. Đây là smoke test tích hợp, không dùng để chọn lại variant.
- Feature build 76,30 giây / peak RSS 370,60 MiB; ranker fit + validation/test 12,68 giây / 185,65 MiB. Đây là số đo local của lần này; thời gian không so trực tiếp với môi trường cloud.
- Import cloud sample cũ thành 1 parent + 7 children; cloud full cũ thành 1 parent + 1 child. Toàn bộ aggregate validation/test metrics khớp JSON gốc; import lặp trả lại cùng parent ID. Revision của hai nguồn cloud là `9879bc55c1149095e4842cad6dcacdf38b9015a0`.
- Kiểm tra HTTP tracking API và `/health`: HTTP 200; experiment `santander-event-v2` có 3 parent + 9 child runs, tất cả FINISHED. Database/artifacts nằm local, không commit vào Git.

| Nguồn | Parent run ID | Loại |
|---|---|---|
| Sample cloud B0–B6 | `b29138baf12248e0b61c6e738f2c8758` | historical_import |
| Full cloud baseline + CLV | `a9fe171333174d3ab676345dbdc811d5` | historical_import |
| Sample 10k chạy mới | `7de3d16e5ae6432c881605ab659d5eab` | live |

Code của live run: `22645b4326a7d705beadd59143b4b6bbabb2a318`. Full data chưa chạy lại với MLflow enabled; full metrics trên UI được nhập từ cloud run hoàn thành trước đây.
