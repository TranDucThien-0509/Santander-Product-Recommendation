# Bước 2 — Benchmark tổng hợp từ output đã lưu

Số liệu trích từ HTML tables trong notebook upload, ở độ chính xác hiển thị, không tính lại metric từ customer-level predictions. Provenance từng bảng: [evidence manifest](../reports/evidence_manifest.json). Tất cả tháng đều là **tháng nguồn**; nhãn acquisition t+1 nằm ở tháng sau.

## RFM — HasEvent, cặp source Dec2015–Apr2016

Trung bình đều metric từng tháng. Cohort này có baseline acquisition khoảng 12.12%, khác cohort tất cả khách của CLV/persona. Không so Lift10 trực tiếp giữa hai cohort.

| method | AP | Lift10 | Brier | rank_stability_min |
|---|---|---|---|---|
| Quantile_555 | 0.264300 | 2.612000 | 0.098800 | 0.914800 |
| Hybrid_REDA_F3_M5 | 0.267500 | 2.641600 | 0.098100 | 0.953400 |
| Hybrid_REDA_F4_M5 | 0.275300 | 2.681900 | 0.097900 | 0.955400 |
| KMeans_6 | 0.219500 | 2.410700 | 0.100800 | 0.942900 |
| M_only | 0.278600 | 2.647100 | 0.100200 | NA |

Chọn F4 cho tag mô tả cuối và bàn giao. M_only có AP cao hơn nhưng ranking đơn biến không thay vai trò phân khúc R/F/M; không tuyên bố F4 thắng mọi baseline. Rank stability đo thứ tự rate nhóm, không đo membership.

## Persona + RFM — cohort persona đủ history, cùng labels

| method | AP_mean | Lift10_mean | Brier_mean |
|---|---|---|---|
| PersonaOnly | 0.144600 | 5.630300 | 0.025600 |
| Persona_F4 | 0.169700 | 5.670400 | 0.025400 |
| Persona_M | 0.204200 | 6.543900 | 0.024800 |
| Persona_R | 0.166100 | 5.707500 | 0.025400 |
| Persona_RFM | 0.223200 | 6.732600 | 0.024500 |

Đây là refinement score, không tạo thêm persona mới. P1–P6 vẫn là sáu nhóm gốc. Các kết quả đã được khảo sát trong development, chưa phải holdout mới.

## Lifecycle ablation — HasEvent đủ RFM và nhãn

| method | AP | AUC | Lift10 | Brier |
|---|---|---|---|---|
| Lifecycle | 0.122100 | 0.502500 | 1.045000 | 0.106900 |
| RFM | 0.267500 | 0.736400 | 2.641600 | 0.098100 |
| RFM+Lifecycle | 0.269100 | 0.736800 | 2.653000 | 0.098200 |

Increment nhỏ; dùng lifecycle chủ yếu cho presence, eligibility và theo dõi quay lại. New/Win-back không đủ support để suy ra mọi tổ hợp đều hữu ích. Chưa có bằng chứng retention intervention hiệu quả.

## Acquisition-proxy — toàn current complete có nhãn, horizon 1m

Validation source Nov2015; method ranking khóa **ML_RFM_stable**. Test source Dec2015–Apr2016, rolling refit bằng nhãn đã hoàn tất. Số dưới đây là trung bình đều từng tháng, không pooled metric.

| method | RMSE | capture10 | lift10 | calibration_ratio |
|---|---|---|---|---|
| ML_RFM | 0.225700 | 0.670500 | 6.704500 | 1.117500 |
| ML_RFM_stable | 0.224200 | 0.663400 | 6.634000 | 1.097000 |
| ML_RFM_only | 0.227700 | 0.610100 | 6.101100 | 1.262000 |
| BGNBD | 0.234700 | 0.510500 | 5.105400 | 1.347000 |
| has_event_mean | 0.236800 | 0.383000 | 3.830400 | 1.392100 |

`capture10` là tỷ trọng tổng product acquisitions ở top10% khách; `lift10` chia cho tỷ trọng được chọn. Không phải số khách mua / toàn bộ khách mua. Calibration ratio = tổng forecast / tổng actual mỗi tháng; mean của ratio không phải pooled ratio.

BG/NBD gồm fallback cho phần lớn khách. Dù ML_RFM tốt hơn trên một số metric test, giữ method đã chọn ở validation.

### Method đã khóa theo tháng

| month | method | capture10 | RMSE | calibration_ratio |
|---|---|---|---|---|
| 2015-12 | ML_RFM_stable | 0.623200 | 0.204600 | 1.246800 |
| 2016-01 | ML_RFM_stable | 0.731100 | 0.259300 | 0.750300 |
| 2016-02 | ML_RFM_stable | 0.624000 | 0.226000 | 1.259300 |
| 2016-03 | ML_RFM_stable | 0.662300 | 0.210800 | 1.210400 |
| 2016-04 | ML_RFM_stable | 0.676400 | 0.220300 | 1.018100 |

## Affinity — toàn cặp snapshot đầy đủ, test Jan–Apr2016

Validation source Dec2015 chọn **recent3_temporal**, window3. Main MAP@7 có cả khách không mở sản phẩm (AP=0). Recall dưới đây chỉ trên acquirers; không nhầm mẫu số.

| method | MAP7_all | recall7_acquirers |
|---|---|---|
| blend80 | 0.024765 | 0.972192 |
| temporal | 0.024527 | 0.958988 |
| recent3_temporal | 0.023750 | 0.964237 |
| apriori | 0.021016 | 0.951518 |
| popularity | 0.020843 | 0.956451 |
| item2vec | 0.003122 | 0.139700 |

Test cho thấy recent3_temporal thấp hơn temporal dù thắng validation. Báo trung thực kết quả này; không chọn blend80 sau khi xem test. Thử nghiệm item2vec có kết quả thấp trong cấu hình hiện tại, không chứng minh mọi embedding đều kém.

## Phân biệt evidence và forecast

- Snapshot 2016-05 chưa có labels sản phẩm 2016-06 trong bộ train. Current score không phải kết quả test đã xác minh.
- Horizon 3/6m giữ trong notebook 07 để phân tích phụ; không gộp vào bảng 1m.
- Card dùng demographics May2016 và acquisition rate range của nguồn Dec2015–Apr2016; không gọi range lịch sử là forecast May.
- Các bộ phương pháp khác cohort/target/horizon không tạo một bảng xếp hạng chung.
