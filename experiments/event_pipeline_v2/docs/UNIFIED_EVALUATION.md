# Track A — đánh giá thống nhất v2

Báo cáo dùng cùng nguồn feature v2 và cùng cohort/nhãn cho RFM, lifecycle,
CLV, persona và affinity. Không nhập các trị số benchmark notebook gốc vào bảng mới.

- [Báo cáo full có biểu đồ và bảng](../../../research/track_a/reports/unified_v2_full_20261019/README.md)
- [HTML độc lập, tải về rồi mở](../../../research/track_a/reports/unified_v2_full_20261019/report.html)
- [Metric từng phương pháp/tháng](../../../research/track_a/reports/unified_v2_full_20261019/customer_metrics_by_month.csv)
- [Acquisition rate từng nhóm/tháng](../../../research/track_a/reports/unified_v2_full_20261019/group_rates_by_month.csv)
- [Độ ổn định nhóm](../../../research/track_a/reports/unified_v2_full_20261019/group_stability_by_month.csv)
- [MAP/Recall sản phẩm](../../../research/track_a/reports/unified_v2_full_20261019/product_metrics_by_month.csv)

## Giao thức chung

1. Một quan sát là một khách tại tháng nguồn t. Cần đủ 24 cờ sản phẩm ở cả t và
   t+1, xuất hiện ở hai tháng liên tiếp. First-seen ở t+1 hoặc quay lại sau gap
   không tự sinh acquisition.
2. Mọi phương pháp nhận đúng cùng cohort tại mỗi origin; không loại riêng
   khách chưa từng mở thêm, ít lịch sử, inactive hoặc thiếu một loại score.
   Score thiếu dùng fallback từ quá khứ và báo số lượng riêng.
3. Nhãn sự kiện: có ít nhất một sản phẩm chuyển 0→1 ở t+1. Nhãn count: số sản
   phẩm chuyển 0→1. Khách không mở thêm vẫn nằm trong mẫu số.
4. Mọi score và tỷ lệ hiệu chỉnh nhóm chỉ dùng nhãn kết thúc không muộn hơn t.
   Không dùng nhãn t+1 để chọn nhóm tốt nhất hoặc gán điểm cho chính tháng t.
5. Ngưỡng phân vị, imputer/scaler và K-means 6 tâm fit trên toàn bộ snapshot
   đầy đủ tháng 11/2015, không dùng nhãn, rồi giữ cố định.
6. Các origin 12/2015–04/2016 là rolling development backtest. Tháng test được
   đánh dấu trong config nguồn là 04/2016, nhãn 05/2016. Không tuyên bố đây là
   holdout chưa từng được dùng trong nghiên cứu. Tháng 05/2016 không có nhãn
   06/2016 nên không được báo điểm test.

## Hai câu hỏi, cùng tập khách

### Ưu tiên khách hàng

| Adapter | Score dùng để xếp khách |
|---|---|
| Historical population | Tỷ lệ mở thêm của tất cả cặp lịch sử đã hoàn tất |
| RFM portfolio propensity | `M_group_points / 100` của feature v2 |
| RFM rule / quantile / K-means | Tỷ lệ mở thêm lịch sử trong nhóm, làm trơn về baseline |
| Lifecycle presence | Tỷ lệ mở thêm lịch sử theo trạng thái presence của catalog v2 |
| Lifecycle activity | Dòng enrichment activity/death của dashboard, báo riêng |
| Persona rules | Tỷ lệ mở thêm lịch sử theo P1–P6/UNKNOWN |
| CLV | `predicted_acquisitions_1m` từ Poisson boosting baseline-numeric đã lưu |
| Affinity max | Điểm affinity cao nhất trong các sản phẩm chưa sở hữu |

Score nhóm dùng `(events + 100 × baseline)/(n + 100)`. Baseline và các counts
đều tính từ cặp lịch sử đã kết thúc tại thời điểm chấm điểm. Với RFM group,
chỉ tích lũy từ tháng fit định nghĩa nhóm trở đi; không dùng định nghĩa tháng
11 để tạo một backtest giả cho các tháng trước 11.

Các adapter nhóm và affinity-max là phần bổ sung mới để đo ưu tiên khách,
không được gọi là các model notebook gốc. M của benchmark phân nhóm là
`n_products`; M của dòng portfolio propensity là `M_group_points`.

Độ đo chung:

- AP, ROC AUC cho nhãn có acquisition.
- Lift10 khách = precision ở top 10% / tỷ lệ buyers trong cùng cohort.
- Capture10 buyers = tỷ trọng người mua nằm trong top 10%.
- Capture10 products = tỷ trọng tổng acquisitions nằm trong top 10%.
- Lift10 products = Capture10 products / 0,1.
- Brier chỉ cho adapter có xác suất sự kiện; affinity-max để trống. Xác suất
  sự kiện của CLV dùng `1-exp(-lambda)`, là phép liên kết theo giả định Poisson,
  không phải một bộ hiệu chỉnh xác suất được fit độc lập.
- MAE, RMSE và calibration ratio của count chỉ cho CLV.

Top 10% dùng đúng khối lượng 0,1×N. Nếu ngưỡng cắt đi qua một nhóm đồng điểm,
mọi người trong nhóm đó nhận cùng trọng số phân số. Đây là kỳ vọng của chọn
ngẫu nhiên công bằng trong nhóm hòa, không phải một danh sách khách được chọn
theo ID. Do đó baseline score bằng nhau có lift đúng 1.

### Gợi ý sản phẩm

Affinity temporal v2 và popularity cơ hội mở thêm được chấm lại trên cùng cohort:

- Cố định thứ tự `PRODUCTS`, mask sản phẩm đang sở hữu, lấy tối đa 7 gợi ý.
- MAP@7 all, MAP@7 buyers, Recall@7 buyers, recommendation coverage.
- MAP@7 all tối đa bằng buyer prevalence theo định nghĩa code hiện tại.
- Recall@7 có trần dưới 1 nếu có khách thực sự mở hơn 7 sản phẩm.

Dòng ranker v2 đã lưu chỉ nhập từ `test_metrics.json` của evaluation model sau
khi kiểm tra số khách và buyers khớp. Không dùng forecast model để báo test,
không nói đã chạy lại ranker trong lần benchmark này. Product popularity dùng
cùng cửa sổ lịch sử với affinity; không dùng độ phổ biến từ tháng nhãn tương lai.

## Độ ổn định

`group_rates_by_month.csv` có n, events, Wilson 95% CI, rate/lift theo nhóm,
và rate ước tính từ quá khứ. Không đồng nhất chênh lệch tháng hiện tại với
khả năng dự báo bền vững.

`group_stability_by_month.csv` tách:

- Membership ARI/stay rate trên cùng khách có mặt ở hai cohort.
- Spearman của thứ hạng rate nhóm, chỉ dùng nhóm có ≥100 khách ở cả hai tháng.

Trung bình các metric là trung bình đều từng tháng, không phải pooled score.
Không cộng N của các tháng rồi gọi là số khách duy nhất. KTC rate là Wilson
nhị thức riêng mỗi nhóm/tháng, không phải một kiểm định tất cả cặp hoặc causal uplift.

Lifecycle presence ở cohort complete hiện tại chủ yếu gồm Active/New/Win-back.
Những khách đang vắng được loại khỏi acquisition cohort do không có cặp đầy đủ;
báo cáo không kiểm định khả năng dự báo churn hoặc phản ứng retention ở nhóm này.

## Tái chạy

Từ thư mục `experiments/event_pipeline_v2`, dùng environment đã cài
`requirements-track-a.txt` và `requirements.txt`:

```powershell
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
python -m track_a.unified_evaluation `
  --index artifacts/customer360-full/customers-v3.duckdb `
  --source-run artifacts/full-cloud/full_validation_selected_20261017T200237620339Z_9e8e42ca `
  --out artifacts/unified-evaluation/new-full-run `
  --publish-dir ../../research/track_a/reports/new-unified-full
```

Output phải là thư mục mới. DB mở read-only. Mỗi tháng chỉ nạp các cột cần thiết;
affinity/product ranking xử lý batch 32.768 khách. Artifact private lưu checksum
DB, source/config/audit hashes, tham số nhóm đã fit và version định nghĩa.
`--publish-dir` chỉ sao chép CSV aggregate, PNG, Markdown và HTML; không sao chép
customer rows, model hoặc config nguồn. Báo cáo không tự upload/push/cloud-run.

```powershell
python -m unittest discover -s tests -p test_unified_evaluation.py -v
```

Test kiểm tra ties, mẫu số, parity với MAP/Recall hiện tại, mask sở hữu, source
audit và việc thay nhãn tương lai không làm đổi điểm nhóm đã tính cho tháng trước.
