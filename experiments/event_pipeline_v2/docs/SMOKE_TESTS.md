# Kết quả kiểm tra bản bàn giao gốc (trước tích hợp)

**Lịch sử:** phần dưới ghi kết quả 5 test của bản ZIP ban đầu. Kết quả tích hợp mới
và 13 test nằm tại [VALIDATION.md](VALIDATION.md); không dùng số cột hoặc trạng
thái Docker/GCP trong bản ghi lịch sử này làm trạng thái hiện tại.

Ngày kiểm tra: 2026-10-17. Dữ liệu **mô phỏng**, tối đa 160 khách và 9 tháng (2020-01 đến 2020-09). Không dùng kết quả này làm benchmark Santander.

Lệnh:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m unittest discover -s tests -v
```

Kết quả: **5 tests passed**, lần chạy cuối trước format khoảng 5 giây.

| Test | Điều đã kiểm tra |
|---|---|
| End-to-end + future invariance | Ingest chunked CSV → feature → train → evaluation → refit → forecast; sửa tháng tương lai không đổi feature quá khứ, kể cả CLV/affinity; giữ tuổi 15; age 164 thành missing; không tạo event ở first-seen/gap; cache nguồn thay đổi bị chặn |
| XGBoost + ablation | Ingest ZIP có file ở thư mục con; chạy 7 variant baseline/+RFM/+CLV/+persona/+lifecycle/+affinity/all; cohort chấm giống nhau; manifest cột khớp từng config; load model đã lưu rồi dự đoán roster có khách cold-start và cờ fallback |
| Metric/mask | MAP_all = buyer_prevalence × MAP_buyers; AP nhiều label; mask sản phẩm đang sở hữu |
| Persona | P1/P6, thiếu lịch sử thành UNKNOWN, rule chưa khả dụng thành UNKNOWN |
| Config guard | Flag dạng chuỗi `"false"` bị từ chối; train/val/test sai thứ tự bị từ chối |

Cấu hình all-enabled có đúng 64 numeric + 6 categorical trước encoding. Đã kiểm tra CLI `run_pipeline --help`, `score --help`, và compile Python.

Runtime đã chạy: Python 3.12, numpy 2.3.5, pandas 2.2.3, scikit-learn 1.8.0, pyarrow 26.0.0, xgboost 3.4.1. Docker/CI cấu hình Python 3.11; chưa build Docker hoặc chạy GitHub Actions thực tế.

Chưa kiểm tra: chất lượng trên raw Santander, RAM/thời gian full data, job Vertex thực tế, cold-start ownership thật, calibration xác suất và persona stability. Có tài liệu input/định nghĩa/giới hạn để tiếp tục kiểm tra các phần này khi có dữ liệu và tài nguyên.
