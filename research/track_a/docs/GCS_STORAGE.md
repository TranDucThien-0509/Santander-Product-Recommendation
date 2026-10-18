# Storage Track A — GCS thay AWS S3

## Quyết định của chủ repo

Ngày 2026-10-18, chủ repo chọn **giữ Google Cloud Storage (GCS)** và ghi rõ khác yêu cầu AWS S3 trong brief Track A. Sau đó chủ repo xác nhận payload processed và bucket/prefix cụ thể để upload.

| Nội dung | Trạng thái |
|---|---|
| Yêu cầu gốc | Processed dataset và dictionary trên AWS S3 |
| Triển khai được chọn | **GCS thay AWS S3**; đây là sai khác đã được chủ repo chấp nhận |
| AWS S3 | Không triển khai/upload; không đánh dấu đã đáp ứng AWS S3 |
| GCS processed sample | Đã upload và kiểm tra lại size + SHA256 |
| Phạm vi dữ liệu | Sample 10.000 ID cố định từ Kaggle; không phải full export hay dữ liệu customer production |

## Vị trí và payload

```text
gs://uit-thien-santander-ds/track-a/sample-10k-20261018T042040Z-gcs/processed/
```

Region bucket: `US-CENTRAL1`, project đang dùng `santander-ds`.

- `customer_features_latest.parquet`: **9.758** khách complete hiện tại, snapshot 2016-05.
- `lifecycle_latest.parquet`: **10.000** khách đã biết, gồm cả khách đang vắng.
- `acquisition_events/2015-02.parquet` … `2016-05.parquet`: **16 partitions / 6.062** product-level acquisitions được xác minh.
- `feature_store_spec.json`: schema, định nghĩa, naming, versions, availability, TTL.
- `processed_manifest.json`: file list, size và SHA256; được publish cuối sau khi xác minh dữ liệu.

Tổng cộng **19 file data/spec + 1 completion manifest = 20 object**. Raw CSV và model pickle không thuộc payload. GitHub chỉ chứa receipt/metadata, không có customer-level rows.

[Mở prefix trong Cloud Console](https://console.cloud.google.com/storage/browser/uit-thien-santander-ds/track-a/sample-10k-20261018T042040Z-gcs/processed?project=santander-ds)

## Kiểm chứng

Receipt: [gcs_storage_receipt.json](../reports/sample_10k/gcs_storage_receipt.json).

1. Xác minh toàn bộ đường dẫn, size và SHA256 của local manifest trước khi gọi cloud.
2. Chỉ stage các file được liệt kê trong manifest, giữ cấu trúc partition.
3. Upload vào prefix mới bằng `--if-generation-match=0`, không ghi đè object cũ.
4. Tải lại mọi object data/spec, so sánh byte size và SHA256 với manifest local.
5. Publish completion manifest cuối; tải lại manifest để đối chiếu SHA256.
6. Ghi metadata của **20 object**, gồm generation, size và CRC32C do GCS trả về.

Đã kiểm tra trước upload: bucket dùng uniform bucket-level access và có **0 public IAM bindings**. Lần publish không đổi IAM/ACL và không cấp quyền đọc công khai.

## Chạy lại hoặc xác minh lại

Từ `experiments/event_pipeline_v2/`:

```bash
python ../../research/track_a/scripts/publish_gcs.py \
  --manifest /absolute/run/processed/processed_manifest.json \
  --destination gs://YOUR_BUCKET/track-a/NEW_RUN_ID \
  --apply --receipt /absolute/run/gcs_storage_receipt.json
```

Không có `--apply` thì chỉ dry-run, không gọi cloud. Để kiểm tra bản đã publish mà **không ghi thêm object**, dùng `--verify-only` thay `--apply`, với destination đã có. Receipt verified chỉ được ghi sau khi hoàn tất kiểm tra.

Exporter S3 vẫn là tùy chọn trong `track_a.storage`; không được dùng trong lần publish này. Không cần AWS bucket, region hoặc access key để hoàn tất phương án GCS đã chọn.

Tài liệu tham khảo: [gcloud storage cp](https://docs.cloud.google.com/sdk/gcloud/reference/storage/cp), [Cloud Storage checksum validation](https://docs.cloud.google.com/storage/docs/data-validation).

Lần publish này chỉ lưu output sample Track A đã hoàn tất; không train lại model và không chạy full data. Metrics, source hashes và thời điểm benchmark gốc được giữ riêng với receipt storage bổ sung.
