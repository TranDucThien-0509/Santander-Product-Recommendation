# Track A — feature store handoff v1

Đây là hợp đồng bàn giao offline, không deploy Feature Store hoặc nối dữ liệu sang track MLE GeoLife.
Schema máy đọc được được sinh từ đúng bảng processed: `reports/sample_10k/feature_store_spec.json`.

## Entity, thời gian và chất lượng

- Entity: `customer_id` (nguồn `ncodpers`), không dùng làm feature dự báo.
- Grain: một dòng `(customer_id, as_of_month)`; duy nhất theo cặp này.
- Tên vật lý dùng `snake_case`; R/F/M cũ được map sang `rfm_recency_months`, `rfm_frequency_event_months`, `portfolio_propensity_points`.
- Event time là tháng snapshot; available time phải là thời điểm snapshot thực sự được công bố. File Kaggle chỉ có tháng nên hợp đồng ghi rõ cần timestamp publication thật khi chuyển sang production.
- Point-in-time join: chỉ lấy bản có `available_at <= scoring_time`, không hết hạn và không carry-forward ownership/RFM qua tháng khách vắng. Label và outcome tương lai là offline-only, không thuộc bảng feature.
- Refresh hàng tháng hoặc khi upstream sửa dữ liệu. TTL tối đa 45 ngày, mất hiệu lực ngay khi có snapshot mới. TTL không cho phép bỏ qua missing snapshot.
- Phiên bản view `santander_track_a_customer_month_v1`; lưu version RFM/CLV/affinity/lifecycle, fit month của clustering và config/source manifest cùng run. Thay định nghĩa cần tăng version, không ghi đè artifact cũ.

## Feature groups

| Nhóm | Định nghĩa / null | Availability | TTL / refresh |
|---|---|---|---|
| Ownership | 24 flag 0/1, current complete snapshot; bảng export loại portfolio incomplete | Snapshot hiện tại công bố | 45d, invalidate on next snapshot |
| R | Số tháng từ acquisition gần nhất được xác minh; null nếu chưa quan sát event | Chỉ event đã hoàn tất trước/đúng tháng hiện tại | Như snapshot |
| F | Số **tháng** có ít nhất một event; không phải tổng số sản phẩm mở | Tích lũy cặp tháng liền kề đã quan sát | Như snapshot |
| Monetary tiering | `n_products` hiện tại dùng cho quantile/rule/KMeans; không phải tiền | Current snapshot | Như snapshot |
| Portfolio points | `100 × historical next-month event rate` theo đúng portfolio; có pooled fallback/support/missing | Chỉ nhãn đã có trước/đúng origin | Như snapshot, version độc lập |
| CLV 1m | Poisson boosting dự báo số acquisition 1 tháng; null/flag khi unavailable | `max_train_label_month <= origin` | Như snapshot |
| CLV 6m | Benchmark nghiên cứu với nhãn đủ 6 cặp; **không giả thành feature tại cutoff hoặc tiền** | Future labels chỉ phục vụ offline report | Không đưa label vào Feature Store |
| Affinity | 24 score ownership→future acquisition từ lịch sử; khóa product order | Chỉ cặp lịch sử có outcome đã công bố | Như snapshot |
| Persona rule | P1–P6 frozen rules; UNKNOWN nếu history/cohort/rule chưa đủ | Rule availability + eligible current history | Như snapshot |
| Persona cluster | C1–Ck từ RFM + CLV + portfolio + affinity + demographics; scaler/encoder/centers cố định tại fit month | Chỉ từ fit month trở đi | Như snapshot; đổi centers → version mới |
| Presence lifecycle | New/Active/At-risk/Churned/Win-back dựa trên observed presence, gap và relationship age | Lịch sử đến current month | Không chứng minh đóng tài khoản |
| Activity lifecycle | Giữ `presence_lifecycle`; `indfall=S` → Churned; observed inactive → At-risk trừ New/Win-back | Activity/death current snapshot; missing giữ unknown | Như snapshot |
| Cross-sell eligibility | Complete observed customer, biết `indfall=N` và `ind_actividad_cliente=1`; missing → false | Chỉ khi đủ status hiện tại | Mất hiệu lực khi status đổi |

## State transitions và event contract

Acquisition là từng flag sản phẩm `0→1` giữa hai tháng liên tiếp, cùng customer, hai snapshot đều đủ 24 flag. Một tháng có thể có nhiều acquisition nhưng chỉ một event-month. Reopen được tính; first-seen hoặc quay lại sau gap không tự tạo acquisition. Event export có source_month, event_month, available_month và product.

Lifecycle presence: mới có relationship trong một tháng → New; quay lại sau gap → Win-back; đang quan sát → Active; vắng dưới 6 tháng → At-risk; vắng từ 6 tháng → Churned. Presence không khẳng định khách còn hoạt động hoặc rời ngân hàng. Activity/death là lớp enrichment riêng ở research export, không âm thầm đổi feature ranker v2. New/Win-back vẫn phải qua eligibility; deceased luôn bị loại.

## Validation và lưu trữ

- Kiểm tra unique keys, binary ownership, nonnegative F, R null khi chưa event, đầy đủ product order, training-label cutoff và raw/cache/run manifest.
- CLV horizon H chỉ có nhãn khi quan sát đủ mọi cặp tương lai; thiếu một cặp → censored, không điền 0.
- Processed Parquet và product-level event nằm trong artifact private. GitHub chỉ giữ schema, báo cáo và aggregate.
- Storage dự án: **GCS thay AWS S3 theo xác nhận chủ repo**; đây là sai khác với brief. Xem [GCS_STORAGE.md](GCS_STORAGE.md).
- `processed_manifest.json` liệt kê chính xác các file được xuất, size và SHA256. Exporter xác minh toàn bộ trước upload; manifest được publish cuối. AWS dùng default credential chain, server-side encryption và checksum; không có public ACL hoặc key trong config.
- Source raw actual trong dự án khoảng 2,3 GB / 13.647.309 dòng; số ~13 GB trong brief là ước lượng, không phải kích thước đã đo của file đang dùng.

## Tài liệu API

- [Lifetimes: BG/NBD và Gamma-Gamma](https://lifetimes.readthedocs.io/en/latest/Quickstart.html): phân biệt repeat frequency, recency last–first và T; monetary proxy không có nghĩa monetary thật.
- [Boto3 upload](https://docs.aws.amazon.com/boto3/latest/guide/s3-uploading-files.html): upload file và các extra arguments của S3 client.
