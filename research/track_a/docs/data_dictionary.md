# Schema bảng customer analytics

Khóa: customer_id (int64), as_of_month (YYYY-MM). Một dòng/known customer. Refresh theo tháng. `NULL` nghĩa là không có giá trị/không đủ điều kiện, không phải 0.

| Cột/nhóm | Định nghĩa |
|---|---|
| is_observed | Có snapshot tháng chốt |
| lifecycle, lifecycle_version, missing_months | Proxy presence lấy từ 05; không phải tần suất giao dịch |
| R | Tháng từ event acquisition gần nhất; NULL nếu chưa quan sát event hoặc không có snapshot |
| F_event_months, F_events | Số tháng có acquisition / số product acquisitions, lũy kế đến cutoff |
| M_group_points | 100 × historical next-month acquisition rate của danh mục hiện tại; không phải currency |
| products_complete, n_products | Cờ đủ 24 sản phẩm / số đang sở hữu; thông tin current snapshot |
| rfm_cluster, rfm_method, rfm_fit_month, rfm_status | Tag F4 và provenance; NoEvent có cluster NULL |
| persona_id, persona_valid_pairs, persona_version, persona_status | Assignment P1–P6 upstream và điều kiện đủ history |
| age, renta, antiguedad | Tuổi / thu nhập hộ / thâm niên tháng; chỉ current raw |
| *_raw, *_missing_raw, *_invalid | Audit trước xử lý numeric; giữ nguyên missing, không impute |
| canal_entrada, segmento, sexo, nomprov | Mã kênh gia nhập, phân khúc sẵn có, mã giới tính, tỉnh; không suy đoán mã kênh |
| demographics_status | current_snapshot hoặc no_current_snapshot |
| expected_acquisitions | Số product acquisitions kỳ vọng trong 1 tháng, gồm reopen; không phải P(any acquisition) |
| clv_horizon_months, clv_target, clv_method, clv_status | Horizon/target/selection và coverage |
| clv_source_rfm_cluster | Nhãn nguồn 07 nếu có, có thể là F3; không đổi thành nhãn F4 |
| top7_products_json | JSON array thứ tự gợi ý; kiểm tra owned đối với current complete |
| recommendation_method | Method được khóa từ validation |
| recommendation_scoring_method | Method thực dùng cho từng khách; stale có popularity_fallback |
| catalog_status | current_complete / last_complete_snapshot / no_complete_snapshot |
| recommendation_eligibility | current_catalog_verified hoặc verify_current_portfolio_before_contact |

Bảng recommendation dài: customer_id + as_of_month + rank là khóa. `ranking_score` chỉ dùng xếp thứ tự trong từng khách, chưa calibration thành xác suất.
