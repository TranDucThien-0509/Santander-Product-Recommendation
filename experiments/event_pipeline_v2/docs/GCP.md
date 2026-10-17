# Chạy container trên GCP

Đây là mẫu triển khai để bạn tự chạy sau khi điền project/bucket và cấp quyền. Trong lần bàn giao chỉ chạy test local trên dữ liệu mô phỏng; chưa build/push image, tạo job hoặc tiêu thụ tài nguyên GCP.

## Chuẩn bị

- GCP project đã bật Vertex AI, Artifact Registry, Cloud Storage; có repository Docker, bucket và service account chạy training.
- Service account đọc được raw/config và tạo/ghi/xóa được cache, feature, model trong prefix output của bucket. Quyền image pull và quyền tạo job tùy cấu hình tổ chức. Không nhúng service account key vào image hoặc repo.
- Upload `train_ver2.csv.zip` vào bucket. Config dùng đường dẫn filesystem `/gcs/BUCKET/...` trong custom training worker; không truyền `gs://...` vào `pd.read_csv` của pipeline này.

Tài liệu chính thức: [Cloud Storage mount trong custom training](https://cloud.google.com/blog/products/ai-machine-learning/cloud-storage-file-system-ai-training), [gcloud custom-jobs create](https://docs.cloud.google.com/sdk/gcloud/reference/ai/custom-jobs/create).

## Cấu hình và build

Sửa `configs/default.json`, rồi upload thành `gs://YOUR_BUCKET/configs/event-v2.json`. Đặc biệt điền `data.train_csv_or_zip`, `data.work_dir`, optional roster; giữ raw/config/output ở các prefix khác nhau. Work dir phải có đủ dung lượng; không cho hai job chạy đồng thời vào cùng cache hoặc bật rebuild cùng lúc.

Ví dụ build **sau khi thay toàn bộ placeholder**:

```bash
docker build -t us-central1-docker.pkg.dev/PROJECT_ID/REPOSITORY/santander-event:IMAGE_TAG .
gcloud auth configure-docker us-central1-docker.pkg.dev
docker push us-central1-docker.pkg.dev/PROJECT_ID/REPOSITORY/santander-event:IMAGE_TAG
gcloud storage cp configs/default.json gs://YOUR_BUCKET/configs/event-v2.json
```

Sửa image URI và config path trong `configs/vertex_job.yaml` cho khớp. Mẫu dùng 1 CPU worker, `n1-standard-8`, disk 200 GB. Đây là điểm bắt đầu để đo tài nguyên, không phải cấu hình đã benchmark trên full Santander. CSV đọc theo chunk nhưng mỗi tháng và training matrix vẫn vào RAM; giảm caps hoặc tăng RAM nếu profiling cho thấy cần.

## Gửi job

```bash
gcloud ai custom-jobs create \
  --project=PROJECT_ID \
  --region=us-central1 \
  --display-name=santander-event-v2 \
  --service-account=TRAINING_SA@PROJECT_ID.iam.gserviceaccount.com \
  --config=configs/vertex_job.yaml
```

Lệnh trên tạo job chạy thực tế. Theo dõi log để lấy dòng `COMPLETE`; output nằm dưới `work_dir/runs/...` tương ứng object trong bucket. Dùng `completed.json` để phân biệt run hoàn tất với run có thư mục nhưng đã lỗi.

Không trộn điểm validation/test với điểm của model refit. Muốn so sánh group: bật `run.ablation` trong JSON trước khi upload; số lần train tăng nên thời gian và tài nguyên tăng.

## Hiệu năng và giới hạn

GCS FUSE có thể tốn I/O khi đọc lại nhiều tháng. CLV fit lại từng origin và affinity dùng cửa sổ quá khứ nên bản v1 ưu tiên đúng thời gian, chưa tối ưu mọi lần đọc. Có thể chạy trên VM với ổ local, sau đó copy output lên bucket, nếu muốn kiểm soát cache/I/O.

Chưa có orchestration Vertex Pipelines/Kubeflow, model registry, endpoint online, MLflow, drift monitor hay tự động chọn model. Một CustomJob chạy một pipeline Python end-to-end. Không cần GPU để dùng backend mặc định này.
