# Bước 3 — Bảng khách hàng cuối và đề xuất sản phẩm

## Input bắt buộc

| Config path | Nguồn | Các file cần |
|---|---|---|
| raw_csv_or_zip | Kaggle Santander | train_ver2.csv hoặc ZIP chứa file đó |
| rfm_features_dir | 01 | rfm_2016-05.parquet |
| rfm_model_dir | 03 | config.json, bucket_specs.json |
| lifecycle_dir | 05 | lifecycle_2016-05.parquet |
| persona_dir | 10 | config.json, personas_tree_2016-05.parquet, persona_validation_monthly.csv |
| clv_dir | 07 | config.json, selection.json, clv_predictions_2016-05_1m.parquet |
| affinity_dir | **13** | selection.json; product_recommendation/2016-05/recent3_temporal/part_*.parquet và status_*.parquet |
| snapshot_cache_dir | 13 | 2016-05.parquet, current complete portfolio dùng kiểm tra owned products |

Nhập folder đúng, không đưa ipynb thay cho output Parquet. Phải dùng notebook 13 cho affinity handoff F4; output 06 vẫn giữ ở phần nghiên cứu và là nguồn upstream của CLV.

## Cách chạy

Tại root repo, sau `python -m pip install -e .`:

```bash
cp configs/finalization.example.json config.local.json
# Sửa 9 đường dẫn trong config.local.json
santander-wrap build --config config.local.json
```

Hoặc mở `notebooks/15_finalize.ipynb` trên Kaggle. Repo có thể đưa lên Kaggle thành dataset code; notebook 15 có ô chọn REPO_DIR chứa pyproject.toml. Không cần cài lại mô hình training để ghép các output.

## Output

- `customer_analytics_2016-05.parquet`: một dòng/known customer; gắn persona, demographics, RFM, lifecycle, expected acquisitions, top7 JSON và status.
- `recommendations_2016-05/part_*.parquet`: Parquet dataset dạng dài, một dòng/customer/rank, tối đa 7 sản phẩm. Ghi theo batch để tránh tạo toàn bộ 6–7 triệu dict trong RAM. Đọc bằng `pd.read_parquet(path_to_directory)` nếu cần.
- `coverage.csv`: quy mô và CLV coverage theo persona/lifecycle, gồm NoCurrentPersona.
- `persona_summary.csv`, `persona_recommendation_top1.csv`, `persona_cards.md`: card được cập nhật bằng dự báo/gợi ý thực tế, không giả số từ notebook screenshots.
- `build_manifest.json`: config, nguồn/size, hash config, số khách và phạm vi validation. Không ghi public file này vì có local paths và bản build thuộc data artifacts.

## Chính sách xử lý

- Lifecycle là bảng nền toàn known population, không inner-join làm mất khách vắng.
- RFM, demographics, portfolio hiện tại chỉ ghép với snapshot cùng tháng. Khách vắng không lấy tuổi/thu nhập/portfolio cũ để giả là giá trị hiện tại.
- Không suy ra persona cho khách thiếu history/incomplete; eligibility giữ từ notebook 10.
- Tuổi 0–17 giữ nguyên. Giá trị tuổi >110/âm, thâm niên âm hoặc numeric không hữu hạn được đánh dấu rồi loại khỏi thống kê, không xóa cả khách. Thu nhập không impute/cap.
- CLV phải khớp method/horizon đã chọn, cover current complete snapshots. Thiếu dự báo được giữ thiếu và có status.
- CLV source group và final F4 tags được giữ riêng khi khác phiên bản.
- Recommendation stale dùng popularity_fallback, chỉ là danh sách ứng viên cần xác minh; score không phải xác suất, không nhân với CLV thành tiền.
- Pipeline kiểm tra unique IDs, month, rules P1–P6, số sản phẩm, cờ lifecycle, selected method và rank/product validity. Thất bại thì dừng; không tự sửa nhãn để chạy qua.
- Dùng folder output mới khi chạy lại. Nếu lỗi giữa chừng, folder recommendation có thể chứa vài partition; không xem đó là build hoàn tất khi chưa có build_manifest.json thành công.

## Trạng thái hiện tại

Code đã được kiểm tra trên fixture mô phỏng đủ 6 persona, absent, incomplete và history-short; chưa chạy tạo bảng 956.645 khách tại môi trường này vì thiếu các Parquet nguồn. Evidence cards và benchmark trong docs được tạo từ output notebook đã chạy. Chưa có product cụ thể/mean CLV theo persona nếu chưa chạy build với nguồn đầy đủ.
