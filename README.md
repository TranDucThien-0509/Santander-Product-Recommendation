# Santander Product Recommendation

## Track A — Customer Segmentation / DS

**Customer 360:** đã có [dashboard hồ sơ khách hàng theo tháng](experiments/event_pipeline_v2/docs/CUSTOMER_360.md)
chạy local: RFM, lifecycle, CLV-proxy 1m, affinity, thông tin khách, nhóm hành vi P và diễn giải mức
ưu tiên chăm sóc. Chọn mã khách, khoảng từ tháng → đến tháng hoặc 6/12/toàn bộ
lịch sử, xem thông tin cá nhân và giải thích nhóm hành vi P theo hai cột, tải JSON. Bản hiện
hỗ trợ toàn bộ khách từ completed full v2 run qua store trên ổ đĩa; vẫn có chế
độ sample 10k. Mức ưu tiên là heuristic thử nghiệm, chưa phải kết luận ROI.
Tab **Mở sản phẩm theo tháng** cho xem lượt mở và khách có sự kiện theo tháng;
bấm mã khách để chuyển thẳng sang hồ sơ tại tháng ghi nhận đó.

Bộ nghiên cứu Track A nằm tại [`research/track_a/`](research/track_a/README.md):
notebook RFM quantile/KMeans/rule, lifecycle, CLV BG/NBD + Gamma-Gamma/ML,
Apriori/item2vec, 6 persona card và package bàn giao. Xem
[đối chiếu từng yêu cầu](research/track_a/docs/TRACK_A_AUDIT.md),
[báo cáo chạy mới sample 10k](research/track_a/reports/sample_10k/TRACK_A_REPORT.md),
[notebook demo 15–20 phút](research/track_a/notebooks/16_track_a_review.ipynb)
và [feature store spec](research/track_a/docs/FEATURE_STORE_SPEC.md).
Các bổ sung chạy lại bằng CLI `track_a` ở thư mục v2, có CI riêng và MLflow
experiment `santander-track-a`. Kết quả sample, nghiên cứu gốc và full-cloud
recommendation được ghi rõ phạm vi. Chủ repo chọn **GCS thay AWS S3**;
xem [quyết định storage](research/track_a/docs/GCS_STORAGE.md) và receipt kiểm chứng.

## Configurable event pipeline v2

Pipeline thử nghiệm tại [`experiments/event_pipeline_v2/`](experiments/event_pipeline_v2/README.md)
cho phép bật/tắt RFM, CLV-proxy, persona, lifecycle và affinity. Chạy lệnh Python
từ thư mục v2 để chọn đúng package `pipeline`. Xem [mapping notebook và availability](experiments/event_pipeline_v2/docs/NOTEBOOK_FEATURE_MAPPING.md),
[kiểm chứng tích hợp](experiments/event_pipeline_v2/docs/VALIDATION.md) và
[benchmark mẫu theo khách hàng](experiments/event_pipeline_v2/docs/SAMPLE_BENCHMARK.md).
Docker, dependencies và CI của v2 tách riêng khỏi pipeline sáu stage trong `legacy/pipeline_v1/`.
Đã chạy mẫu 10.000 khách và full 13.647.309 snapshot trên Vertex với cấu hình
chọn từ validation; xem [bằng chứng cloud và metric](experiments/event_pipeline_v2/docs/CLOUD_RUNS.md).
Đây là temporal development backtest trên các tháng đã dùng trong nghiên cứu.

## Pipeline cũ — mục riêng

Pipeline sáu stage được giữ tại **[legacy/pipeline_v1/](legacy/pipeline_v1/README.md)**,
bao gồm mã nguồn, dependencies, Dockerfile, bốn cấu hình Vertex và hướng dẫn GCP.
Đây là phiên bản tham chiếu đã kiểm tra sample 10k dòng; kết quả full v2 được báo riêng.

- [Chạy lại pipeline v1](legacy/pipeline_v1/README.md)
- [Triển khai GCP của v1](legacy/pipeline_v1/GCP_DEPLOYMENT.md)
- [CI dành riêng cho v1](.github/workflows/legacy-pipeline.yml)

## Cấu trúc repo

```text
experiments/event_pipeline_v2/  Pipeline v2, Customer 360 và đánh giá thống nhất
research/track_a/              Notebook, package bàn giao và bằng chứng Track A
legacy/pipeline_v1/            Pipeline sáu stage cùng cấu hình triển khai cũ
notebooks/                    EDA và feature engineering ban đầu
src/                          Helper ingest cho notebook EDA
data/raw/                     Hai file sample phục vụ kiểm thử v1
```

[Báo cáo đánh giá thống nhất Track A trên full data](research/track_a/reports/unified_v2_full_20261019/README.md)
đặt cạnh các benchmark nghiên cứu và sample, có ghi rõ phạm vi từng nguồn.

`requirements.txt` ở root là entrypoint tương thích cho môi trường notebook/v1.
V2 dùng bộ dependencies riêng trong thư mục của nó.
