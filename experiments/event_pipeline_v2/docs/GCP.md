# Chạy container trên GCP

Runbook cho image v2 riêng. Xem [VALIDATION.md](VALIDATION.md) để biết build/job nào đã thực sự hoàn tất; cấu hình trong Git dùng placeholder, cấu hình chạy thật nằm ngoài Git.

## Chuẩn bị

- GCP project đã bật Vertex AI, Artifact Registry, Cloud Storage; có repository Docker, bucket và service account chạy training.
- Service account đọc được raw/config và tạo/ghi/xóa được cache, feature, model trong prefix output của bucket. Quyền image pull và quyền tạo job tùy cấu hình tổ chức. Không nhúng service account key vào image hoặc repo.
- Upload `train_ver2.csv.zip` vào bucket. Config dùng đường dẫn filesystem `/gcs/BUCKET/...` trong custom training worker; không truyền `gs://...` vào `pd.read_csv` của pipeline này.

Tài liệu chính thức: [Cloud Storage mount trong custom training](https://cloud.google.com/blog/products/ai-machine-learning/cloud-storage-file-system-ai-training), [gcloud custom-jobs create](https://docs.cloud.google.com/sdk/gcloud/reference/ai/custom-jobs/create).

## Cấu hình và build

Copy `configs/default.json` thành `configs/config.local.json`, sửa bản local rồi upload vào prefix mới, ví dụ `gs://YOUR_BUCKET/event-v2/IMAGE_TAG/configs/sample.json`. Điền `data.train_csv_or_zip`, `data.work_dir`, optional roster; giữ raw/config/output riêng. Work dir phải có đủ dung lượng; mỗi sample/full/attempt dùng prefix mới, không cho hai job dùng chung cache hoặc bật rebuild cùng lúc.

Ví dụ build **sau khi thay toàn bộ placeholder**:

```bash
docker build -t us-central1-docker.pkg.dev/PROJECT_ID/REPOSITORY/santander-event:IMAGE_TAG .
gcloud auth configure-docker us-central1-docker.pkg.dev
docker push us-central1-docker.pkg.dev/PROJECT_ID/REPOSITORY/santander-event:IMAGE_TAG
gcloud storage cp configs/config.local.json gs://YOUR_BUCKET/event-v2/IMAGE_TAG/configs/sample.json
```

Sửa image URI và config path trong bản local của `configs/vertex_job.yaml`. Mẫu dùng 1 CPU worker, `n1-standard-8`, disk 200 GB và timeout 7.200 giây; sample dùng timeout 1.800 giây. Ghim digest `.../santander-event@sha256:...` sau khi publish để job không chạy image bị đổi tag. CSV đọc theo chunk nhưng mỗi tháng và training matrix vẫn vào RAM; đo `feature_build_resources.json` và `comparison.json` trên sample trước khi chạy full.

Nếu Docker Desktop chưa chạy, có thể build/publish bằng Cloud Build:

```bash
gcloud meta list-files-for-upload
gcloud builds submit . --project=PROJECT_ID \
  --tag=us-central1-docker.pkg.dev/PROJECT_ID/REPOSITORY/santander-event:IMAGE_TAG \
  --timeout=1200s --async
```

`.gcloudignore` chỉ cho phép source Python, requirements, Dockerfile và default config. Kiểm tra danh sách upload trước mỗi build. Docker chỉ COPY default config; không copy config local hoặc credential vào image.

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

## Trình tự sample → full

1. Chạy `pipeline.sample` trên raw để lấy 10.000 customer ID cố định, giữ mọi tháng; upload sample và manifest vào prefix raw riêng. Không dùng sample 10k dòng cũ của pipeline root vì thiếu các tháng test.
2. Chạy sample với cả bảy ablation variants; kiểm tra state `JOB_STATE_SUCCEEDED`, `completed.json`, cohort, forecast audit và measured RSS.
3. Khóa flags theo validation, không dùng test để chọn. Thử nghiệm local chọn baseline+CLV; mọi điểm test vẫn từ evaluation_model trước refit.
4. Tạo config full từ cấu hình đã khóa, đổi raw path về full CSV, work_dir thành prefix full mới, `ablation=false`. Giữ seed, split, sampling caps và model parameters; không cần chạy lại bảy ablations trên full ngay lần đầu.
5. Tạo job full với cùng image digest, timeout hữu hạn. Chỉ ghi full verified sau khi job thành công và có completed.json cùng ownership/coverage audit. Các artifact customer-level/model tiếp tục ở GCS.

Với full, có thể đặt `data.work_dir=/tmp/event-v2-full-IMAGE_TAG` trên SSD của
worker để tránh đọc lặp cache/feature qua FUSE. Khi đó container command dùng
Python launcher tương đương đoạn dưới để publish thư mục run hoàn chỉnh sau
train. Cache thô ở SSD là tạm; artifact run được copy vào prefix full bền vững.
Không coi file completed.json đang copy dở là bằng chứng job đã thành công:
kiểm tra thêm `published.json` và trạng thái Vertex.
GCS FUSE không giữ đầy đủ quyền và timestamp như POSIX; không dùng metadata đó
để xác nhận tính toàn vẹn artifact. Xem [filesystem semantics chính thức](https://github.com/GoogleCloudPlatform/gcsfuse/blob/master/docs/semantics.md).

```python
from pathlib import Path
import shutil
from pipeline.common import load_config, write_json
from pipeline.run_pipeline import run

result = run(load_config('/gcs/YOUR_BUCKET/event-v2/IMAGE_TAG/configs/full.json'))
destination = Path('/gcs/YOUR_BUCKET/event-v2/IMAGE_TAG/full/runs') / result.name
shutil.copytree(result, destination)
write_json(destination / 'published.json', {'status': 'success', 'source_run': result.name})
```

```bash
gcloud ai custom-jobs describe JOB_ID --project=PROJECT_ID --region=us-central1 --format=json
gcloud ai custom-jobs stream-logs JOB_ID --project=PROJECT_ID --region=us-central1
gcloud storage ls 'gs://YOUR_BUCKET/event-v2/IMAGE_TAG/full/runs/*/completed.json'
```

Nếu cần dừng job đang chạy, dùng `gcloud ai custom-jobs cancel JOB_ID --project=PROJECT_ID --region=us-central1`. Không xóa raw hoặc prefix của job khác để sửa một lần chạy lỗi.

Không trộn điểm validation/test với điểm của model refit. Muốn so sánh group: bật `run.ablation` trong JSON trước khi upload; số lần train tăng nên thời gian và tài nguyên tăng.

## Hiệu năng và giới hạn

GCS FUSE có thể tốn I/O khi đọc lại nhiều tháng. CLV fit lại từng origin và affinity dùng cửa sổ quá khứ nên bản v1 ưu tiên đúng thời gian, chưa tối ưu mọi lần đọc. Có thể chạy trên VM với ổ local, sau đó copy output lên bucket, nếu muốn kiểm soát cache/I/O.

Chưa có orchestration Vertex Pipelines/Kubeflow, model registry, endpoint online, drift monitor hay tự động chọn model. Một CustomJob chạy một pipeline Python end-to-end. Không cần GPU để dùng backend mặc định này.


## MLflow trên Vertex

Xem [MLFLOW.md](MLFLOW.md). Bật `tracking.enabled=true` và truyền `MLFLOW_TRACKING_URI` trỏ tới tracking server mà worker truy cập được; cấu hình authentication bằng environment/secret của job. Không đặt SQLite trên `/gcs/`. Tracking mặc định tắt; các cloud run trong CLOUD_RUNS.md trước tích hợp này không ghi MLflow trực tiếp và có thể import lịch sử bằng CLI.
