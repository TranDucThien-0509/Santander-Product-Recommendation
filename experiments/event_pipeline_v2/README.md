# Santander — configurable acquisition-event pipeline

Pipeline thử nghiệm riêng trong `experiments/event_pipeline_v2/` để dự đoán **sản phẩm mở thêm ở tháng t+1**, dùng thông tin đã quan sát đến hết tháng t. Thêm config bật/tắt RFM, CLV-proxy, persona, lifecycle và affinity. Chạy mọi lệnh bên dưới từ thư mục v2 để chọn đúng package `pipeline`.

Tham chiếu cấu trúc project: https://github.com/TranDucThien-0509/Santander-Product-Recommendation, commit được đọc `5e791bda2958fa395f69d342aeaa83a28ad78bcb`.

## 1. Input

Bắt buộc: `train_ver2.csv` hoặc ZIP chứa đúng một file tên `train_ver2.csv`, gồm:

- `ncodpers`, `fecha_dato`, `fecha_alta`.
- `age`, `renta`, `antiguedad`, `canal_entrada`, `segmento`, `sexo`, `nomprov`.
- Đủ 24 cột sản phẩm Santander, xem `pipeline/common.py`.
- Đủ mọi tháng từ `history_start` đến `forecast_month`. Mỗi khách tối đa một dòng mỗi tháng.

Tùy chọn: `test_ver2.csv` hoặc ZIP chứa file này, dùng **cột ID** làm danh sách cần dự đoán. Pipeline không lấy thuộc tính của tháng tương lai từ file test.

Không bắt buộc có parquet RFM/CLV/persona cũ: bản này tự tính các nhóm theo thời điểm. Đây là định nghĩa proxy mới có ghi rõ trong [feature catalog](docs/FEATURE_CATALOG.md); không mặc định tái tạo kết quả các notebook cũ.

Xem [mapping notebook và phiên bản](docs/NOTEBOOK_FEATURE_MAPPING.md), [kiểm chứng](docs/VALIDATION.md) và [ablation trên mẫu 10.000 khách](docs/SAMPLE_BENCHMARK.md). RFM M dùng thang 0–100 và baseline fallback của notebook 01; persona dùng sáu rule đã xác nhận. CLV và affinity có phiên bản riêng.

## 2. Chạy local

Yêu cầu Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp configs/default.json configs/config.local.json
```

Sửa ba trường trong `configs/config.local.json`:

```json
{
  "train_csv_or_zip": "/absolute/path/train_ver2.csv.zip",
  "prediction_roster_csv_or_zip": null,
  "work_dir": "/absolute/path/santander-runs"
}
```

Ba trường trên nằm trong object `data`, không phải ở top-level. Các phần khác giữ cấu trúc của file mẫu.

```bash
OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 python -m pipeline.run_pipeline --config configs/config.local.json
```

Pipeline chạy ingest → feature theo tháng → train → validation/test → optional refit → forecast. In ra đường dẫn `COMPLETE` sau khi hoàn thành. Cache raw đã làm sạch dùng lại nếu file nguồn và phạm vi tháng không đổi. Nếu nguồn thay đổi, chọn `work_dir` mới hoặc bật `data.rebuild_cache`.

## 3. Công tắc feature

```json
"feature_groups": {
  "rfm": true,
  "clv": false,
  "persona": true,
  "lifecycle": true,
  "affinity": false
}
```

`false` nghĩa là toàn bộ cột của nhóm **không có trong input của model xếp hạng**. Không phải đưa cột vào rồi thay bằng số 0. Baseline gồm portfolio và các thuộc tính khách hàng vẫn có. Một số lịch sử trung gian vẫn được tính để tạo feature khác; CLV chỉ dùng baseline numeric, không dùng persona/RFM làm input nội bộ.

Artifact `feature_manifest.json` ghi cả cột gốc và cột sau encoding. Vì persona P1–P6 dựa vào F và số sản phẩm, bật persona vẫn cung cấp thông tin dẫn xuất từ F kể cả khi tắt các cột RFM trực tiếp. Các flag điều khiển **nhóm cột**, không bảo đảm các nhóm độc lập về thông tin.

## 4. Phạm vi train và đánh giá

Một event hợp lệ là cờ sản phẩm 0→1 của **cùng khách, ở hai tháng liên tiếp, cả hai snapshot đủ 24 cờ**. Không coi lần xuất hiện đầu tiên hoặc lần quay lại sau khoảng trống là một acquisition đã xác minh.

Tại origin t:

- Feature: chỉ dữ liệu đến t.
- Label: các sản phẩm 0→1 giữa t và t+1.
- Train: chỉ khách có ít nhất một label. Khách mở nhiều sản phẩm tạo một dòng cho mỗi sản phẩm mở thêm; không lấy sản phẩm đầu tiên rồi bỏ các label còn lại.
- Model: multiclass XGBoost. Điểm dùng để xếp hạng sản phẩm khi có acquisition; không coi điểm softmax là xác suất mua tuyệt đối của mỗi khách.
- Validation/test: chấm **tất cả cặp snapshot đủ điều kiện**, lưu cả `MAP@7_all` và `MAP@7_buyers`, tỷ lệ buyers và Recall@7_buyers. Hai MAP dùng denominator khác nhau.
- Forecast: dự đoán mọi khách có snapshot đủ ở origin, vì khi chạy thực tế chưa biết ai sẽ mở sản phẩm. Loại sản phẩm đang sở hữu trước khi chọn tối đa 7 sản phẩm.

Split mặc định:

| Tập | Tháng feature | Tháng label |
|---|---|---|
| Train | 2015-12, 2016-01, 2016-02 | 2016-01, 02, 03 |
| Validation | 2016-03 | 2016-04 |
| Test | 2016-04 | 2016-05 |
| Forecast | 2016-05 | 2016-06, chưa có nhãn |

Khách có thể xuất hiện trong nhiều tập vì đây là dự đoán theo tháng cho khách hiện hữu. Không random split các customer-month. Kết quả không đại diện riêng cho cold-start customers.

## 5. So sánh nhóm feature

Bật `run.ablation: true` để chạy baseline, baseline+từng nhóm đang bật, và all-enabled nếu có nhiều nhóm. Các lần chạy dùng cùng tháng, cùng cohort, cùng seed và cùng giới hạn sampling. Bảng kết quả ở `comparison.json`. Nếu phải sampling, quota event rows được chia đều theo số origin; `feature_manifest.json` ghi số event thực dùng và số sẵn có từng tháng.

So sánh **validation** để chọn cấu hình; khóa cấu hình rồi báo cáo test. Pipeline xuất forecast cho cấu hình cuối trong danh sách (all-enabled khi có nhiều nhóm), **không tự chọn cấu hình tốt nhất từ test**. Muốn dùng variant khác: sửa flag, đặt tên run và chạy lại.

Đây là so sánh tác dụng bổ sung của từng nhóm trên baseline; không phải phân rã đóng góp nhân quả. Bản v1 chưa có SHAP, confidence interval hay leave-one-group-out.

## 6. Output

Mỗi run có thư mục riêng với thời gian và hash config. Model, metric và CSV nằm trong thư mục variant (`all_features` mặc định, hoặc tên variant khi ablation); feature và audit chung nằm ở root của run:

- `config.resolved.json`, `input_manifest.json`, `environment.json`, `point_in_time_audit.json`.
- `features/YYYY-MM.parquet`: snapshot feature, gồm cả cột trung gian phục vụ kiểm tra.
- `lifecycle/YYYY-MM.parquet`: mọi khách đã biết đến tháng đó, kể cả At-risk/Churned đang vắng.
- `feature_build_resources.json`: thời gian và peak process RSS đo mỗi 0,1 giây; từng variant có resource metrics riêng.
- `evaluation_model/model.pkl` và `feature_manifest.json`: model fit trên train để chấm validation/test.
- `validation_metrics.json`, `test_metrics.json`: aggregate và chi tiết theo tháng, cohort coverage.
- `forecast_model/`: model refit trên train+validation+test nếu `refit_for_forecast=true`; chỉ dùng cho forecast. Điểm test vẫn của evaluation model.
- `submission.csv`: `ncodpers,added_products`.
- `predictions_with_status.csv`: thêm trạng thái chất lượng đầu vào.
- `comparison.json`, `completed.json`: bảng so sánh và dấu hoàn thành.

Model không quan sát được acquisition của một số sản phẩm trong train sẽ có điểm 0 cho các sản phẩm đó. Khi cần lấp top-7, tie-break theo thứ tự danh sách sản phẩm; chưa có model riêng cho rare product.

Nếu có prediction roster: khách thiếu snapshot đủ tháng t được gợi ý bằng độ phổ biến acquisition của tháng quan sát gần nhất và đánh dấu `fallback_ownership_unverified`. Không khẳng định những khách này chưa sở hữu sản phẩm được gợi ý. Nếu không cung cấp roster, chỉ xuất khách đủ snapshot ở tháng t.

Re-score bằng artifact đáng tin cậy:

```bash
python -m pipeline.score --config config.local.json \
  --model /absolute/run/all_features/forecast_model/model.pkl \
  --features /absolute/run/features --out /absolute/rescore
```

Phải dùng cùng config, cache, feature của run đã fit; nếu chưa refit thì dùng `evaluation_model/model.pkl`.

## 7. Chạy test và GCP

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m unittest discover -s tests -v
```

Test tự tạo dữ liệu giả; không tải hay commit dữ liệu Kaggle. Có test XGBoost, pipeline end-to-end, mốc thời gian, mask ownership, cohort missing và flags.

Xem [hướng dẫn GCP](docs/GCP.md), `Dockerfile`, `configs/vertex_job.yaml` và [trạng thái kiểm chứng](docs/VALIDATION.md). Raw ingest đọc theo chunk nhưng bước tổng hợp/feature vẫn nạp một tháng vào RAM; không phải pipeline hoàn toàn out-of-core. Giới hạn event rows và CLV rows có config; scoring encoding chia batch 20.000 dòng.

Workflow v2 nằm tại root `.github/workflows/event-pipeline-v2.yml`, cài requirements và chạy synthetic tests từ thư mục v2, sau đó build Docker và kiểm tra import trong container. Workflow CI/CD cũ được giữ riêng. Không commit raw data, cache, model pickle hoặc credentials.
