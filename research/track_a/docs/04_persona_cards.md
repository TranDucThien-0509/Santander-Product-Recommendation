# Sáu persona card — evidence snapshot 2016-05

# P1 — Danh mục cơ bản, chưa quan sát event

Danh mục cơ bản, chưa quan sát event; tuổi trung vị thấp hơn baseline.

**Nguồn:** output notebook 10 và 14 đã chạy, snapshot 2016-05. Số liệu lấy từ bảng hiển thị được lưu; không tái tính từ raw.

- Rule: `F_event_months = 0; n_products <= 2`; chỉ áp dụng trên cohort persona đủ điều kiện upstream.
- Quy mô: 688,628 khách; 75.09% cohort persona; 71.98% known population.
- F trung vị: 0 tháng có event; số sản phẩm trung vị: 1.
- Acquisition t+1 trong development (source 2015-12–2016-04): **0.47% - 0.61%**.
  Đây là min–max tỷ lệ nhóm qua tháng, không phải khoảng xác suất cá nhân hay CI.

| Thuộc tính | Median | Q25 - Q75 | Coverage | Median baseline |
|---|---:|---:|---:|---:|
| age | 34.0 | 24.0 - 50.0 | 100.00% | 38.0 |
| renta | 98,472.3 | 66,738.4 - 151,151.7 | 76.00% | 101,493.4 |
| antiguedad | 53.0 | 25.0 - 125.0 | 100.00% | 54.0 |

Thu nhập chỉ mô tả khách có renta hợp lệ; chưa phải giá trị tiền tạo cho ngân hàng.

**Profile ổn định qua 6 tháng:**
- age: trung vị từng tháng trong khoảng 34 - 36; không chứng minh cùng khách giữ nguyên persona.
- antiguedad: trung vị từng tháng trong khoảng 50 - 53; không chứng minh cùng khách giữ nguyên persona.
- Top canal_entrada tại tháng cuối: KHE: 33.7%; KFC: 20.2%; KAT: 19.4%.
- Top nomprov tại tháng cuối: MADRID: 28.4%; BARCELONA: 10.2%; VALENCIA: 5.4%.

**Dự báo và trạng thái hiện tại (nguồn notebook 12):**
- Mean CLV-proxy 1 tháng ≈ **0.006955**; coverage 100.00%; method ML_RFM_stable.
  Output nguồn là points; mọi product weight=1 nên cùng đơn vị số acquisition. Mean gộp theo n từ các nhóm lifecycle; không gộp median bằng trung bình.
- Lifecycle: Active: 688,617; Win-back: 11.
  Forecast chưa có nhãn tương lai để xác minh; lifecycle chỉ là presence proxy.

**Ví dụ quan hệ sản phẩm lịch sử (nguồn 13, nhánh persona affinity):**
| Đang có A, chưa có B → mở B tháng sau | Exposure khách-tháng | Acquisitions | Confidence quan sát |
|---|---:|---:|---:|
| prod_payroll_account → prod_pension_payroll | 7,614 | 503 | 6.61% |
| prod_payroll_account → prod_payroll | 7,731 | 458 | 5.92% |

Các luật trên được hiển thị theo lift, là mô tả lịch sử có support; không phải top-7 cuối hoặc tác động nhân quả. Export chính vẫn dùng recent3_temporal đã khóa.

**Cách dùng kết quả:**
- Tiếp cận chi phí thấp theo nhu cầu; dùng CLV-proxy để ưu tiên trong nhóm, affinity để chọn sản phẩm.
- CLV-proxy ưu tiên khách, affinity chọn sản phẩm; chưa có top-7 customer-level để tổng hợp tần suất gợi ý thật.
- RFM là tag chi tiết; nhãn F4 cuối và nhãn nguồn CLV được phân biệt trong bảng tổng hợp.

**Giới hạn:** F=0 là chưa quan sát event trong lịch sử dataset; card là mô tả, không thêm mô hình dự đoán.

---

# P2 — Danh mục đa sản phẩm, chưa quan sát event

Danh mục đa sản phẩm, chưa quan sát event; khách lâu năm và lớn tuổi hơn mặt bằng.

**Nguồn:** output notebook 10 và 14 đã chạy, snapshot 2016-05. Số liệu lấy từ bảng hiển thị được lưu; không tái tính từ raw.

- Rule: `F_event_months = 0; n_products >= 3`; chỉ áp dụng trên cohort persona đủ điều kiện upstream.
- Quy mô: 33,448 khách; 3.65% cohort persona; 3.50% known population.
- F trung vị: 0 tháng có event; số sản phẩm trung vị: 3.
- Acquisition t+1 trong development (source 2015-12–2016-04): **2.35% - 3.71%**.
  Đây là min–max tỷ lệ nhóm qua tháng, không phải khoảng xác suất cá nhân hay CI.

| Thuộc tính | Median | Q25 - Q75 | Coverage | Median baseline |
|---|---:|---:|---:|---:|
| age | 49.0 | 43.0 - 57.0 | 100.00% | 38.0 |
| renta | 127,455.3 | 85,671.3 - 189,975.9 | 87.00% | 101,493.4 |
| antiguedad | 163.0 | 116.0 - 191.0 | 100.00% | 54.0 |

Thu nhập chỉ mô tả khách có renta hợp lệ; chưa phải giá trị tiền tạo cho ngân hàng.

**Profile ổn định qua 6 tháng:**
- age: trung vị từng tháng trong khoảng 48 - 49; không chứng minh cùng khách giữ nguyên persona.
- antiguedad: trung vị từng tháng trong khoảng 157 - 163; không chứng minh cùng khách giữ nguyên persona.
- Top canal_entrada tại tháng cuối: KAT: 49.6%; KFC: 30.5%; KFA: 5.3%.
- Top nomprov tại tháng cuối: MADRID: 56.0%; BARCELONA: 7.4%; VALENCIA: 3.6%.

**Dự báo và trạng thái hiện tại (nguồn notebook 12):**
- Mean CLV-proxy 1 tháng ≈ **0.030206**; coverage 100.00%; method ML_RFM_stable.
  Output nguồn là points; mọi product weight=1 nên cùng đơn vị số acquisition. Mean gộp theo n từ các nhóm lifecycle; không gộp median bằng trung bình.
- Lifecycle: Active: 33,448.
  Forecast chưa có nhãn tương lai để xác minh; lifecycle chỉ là presence proxy.

**Ví dụ quan hệ sản phẩm lịch sử (nguồn 13, nhánh persona affinity):**
| Đang có A, chưa có B → mở B tháng sau | Exposure khách-tháng | Acquisitions | Confidence quan sát |
|---|---:|---:|---:|
| prod_pension_payroll → prod_payroll_account | 1,336 | 144 | 10.78% |
| prod_payroll → prod_payroll_account | 1,274 | 137 | 10.75% |

Các luật trên được hiển thị theo lift, là mô tả lịch sử có support; không phải top-7 cuối hoặc tác động nhân quả. Export chính vẫn dùng recent3_temporal đã khóa.

**Cách dùng kết quả:**
- Xác minh nhu cầu bổ sung ở khách lâu năm; chưa quan sát acquisition không đồng nghĩa không sử dụng.
- CLV-proxy ưu tiên khách, affinity chọn sản phẩm; chưa có top-7 customer-level để tổng hợp tần suất gợi ý thật.
- RFM là tag chi tiết; nhãn F4 cuối và nhãn nguồn CLV được phân biệt trong bảng tổng hợp.

**Giới hạn:** F=0 là chưa quan sát event trong lịch sử dataset; card là mô tả, không thêm mô hình dự đoán.

---

# P3 — Một tháng acquisition được quan sát

Một tháng acquisition được quan sát; demographics khá đa dạng.

**Nguồn:** output notebook 10 và 14 đã chạy, snapshot 2016-05. Số liệu lấy từ bảng hiển thị được lưu; không tái tính từ raw.

- Rule: `F_event_months = 1`; chỉ áp dụng trên cohort persona đủ điều kiện upstream.
- Quy mô: 84,572 khách; 9.22% cohort persona; 8.84% known population.
- F trung vị: 1 tháng có event; số sản phẩm trung vị: 2.
- Acquisition t+1 trong development (source 2015-12–2016-04): **6.29% - 8.95%**.
  Đây là min–max tỷ lệ nhóm qua tháng, không phải khoảng xác suất cá nhân hay CI.

| Thuộc tính | Median | Q25 - Q75 | Coverage | Median baseline |
|---|---:|---:|---:|---:|
| age | 41.0 | 29.0 - 51.0 | 100.00% | 38.0 |
| renta | 106,509.2 | 71,997.0 - 161,018.7 | 72.10% | 101,493.4 |
| antiguedad | 42.0 | 12.0 - 135.0 | 100.00% | 54.0 |

Thu nhập chỉ mô tả khách có renta hợp lệ; chưa phải giá trị tiền tạo cho ngân hàng.

**Profile ổn định qua 6 tháng:**
- age: trung vị từng tháng trong khoảng 41 - 42; không chứng minh cùng khách giữ nguyên persona.
- antiguedad: trung vị từng tháng trong khoảng 42 - 49; không chứng minh cùng khách giữ nguyên persona.
- Top canal_entrada tại tháng cuối: KAT: 25.1%; KFC: 24.0%; KHE: 9.9%.
- Top nomprov tại tháng cuối: MADRID: 38.6%; BARCELONA: 7.5%; VALENCIA: 4.8%.

**Dự báo và trạng thái hiện tại (nguồn notebook 12):**
- Mean CLV-proxy 1 tháng ≈ **0.081194**; coverage 100.00%; method ML_RFM_stable.
  Output nguồn là points; mọi product weight=1 nên cùng đơn vị số acquisition. Mean gộp theo n từ các nhóm lifecycle; không gộp median bằng trung bình.
- Lifecycle: Active: 84,565; Win-back: 7.
  Forecast chưa có nhãn tương lai để xác minh; lifecycle chỉ là presence proxy.

**Ví dụ quan hệ sản phẩm lịch sử (nguồn 13, nhánh persona affinity):**
| Đang có A, chưa có B → mở B tháng sau | Exposure khách-tháng | Acquisitions | Confidence quan sát |
|---|---:|---:|---:|
| prod_short_term_deposit → prod_long_term_deposit | 878 | 67 | 7.63% |
| prod_payroll → prod_payroll_account | 3,824 | 1,360 | 35.56% |

Các luật trên được hiển thị theo lift, là mô tả lịch sử có support; không phải top-7 cuối hoặc tác động nhân quả. Export chính vẫn dùng recent3_temporal đã khóa.

**Cách dùng kết quả:**
- Theo dõi khả năng mở tiếp; dùng R và CLV-proxy để phân biệt trong nhóm.
- CLV-proxy ưu tiên khách, affinity chọn sản phẩm; chưa có top-7 customer-level để tổng hợp tần suất gợi ý thật.
- RFM là tag chi tiết; nhãn F4 cuối và nhãn nguồn CLV được phân biệt trong bảng tổng hợp.

**Giới hạn:** F=0 là chưa quan sát event trong lịch sử dataset; card là mô tả, không thêm mô hình dự đoán.

---

# P4 — Acquisition lặp lại, danh mục 0–1 sản phẩm

Acquisition lặp lại, danh mục hẹp; thâm niên tương đối ngắn.

**Nguồn:** output notebook 10 và 14 đã chạy, snapshot 2016-05. Số liệu lấy từ bảng hiển thị được lưu; không tái tính từ raw.

- Rule: `F_event_months >= 2; n_products <= 1`; chỉ áp dụng trên cohort persona đủ điều kiện upstream.
- Quy mô: 20,196 khách; 2.20% cohort persona; 2.11% known population.
- F trung vị: 2 tháng có event; số sản phẩm trung vị: 1.
- Acquisition t+1 trong development (source 2015-12–2016-04): **21.04% - 28.09%**.
  Đây là min–max tỷ lệ nhóm qua tháng, không phải khoảng xác suất cá nhân hay CI.

| Thuộc tính | Median | Q25 - Q75 | Coverage | Median baseline |
|---|---:|---:|---:|---:|
| age | 37.0 | 26.0 - 47.0 | 100.00% | 38.0 |
| renta | 95,709.1 | 65,402.3 - 143,121.0 | 77.00% | 101,493.4 |
| antiguedad | 31.0 | 16.0 - 56.0 | 100.00% | 54.0 |

Thu nhập chỉ mô tả khách có renta hợp lệ; chưa phải giá trị tiền tạo cho ngân hàng.

**Profile ổn định qua 6 tháng:**
- age: trung vị từng tháng trong khoảng 36 - 37; không chứng minh cùng khách giữ nguyên persona.
- antiguedad: trung vị từng tháng trong khoảng 27 - 31; không chứng minh cùng khách giữ nguyên persona.
- Top canal_entrada tại tháng cuối: KHE: 23.2%; KFC: 22.8%; KAT: 17.8%.
- Top nomprov tại tháng cuối: MADRID: 30.7%; BARCELONA: 8.3%; SEVILLA: 5.1%.

**Dự báo và trạng thái hiện tại (nguồn notebook 12):**
- Mean CLV-proxy 1 tháng ≈ **0.271309**; coverage 100.00%; method ML_RFM_stable.
  Output nguồn là points; mọi product weight=1 nên cùng đơn vị số acquisition. Mean gộp theo n từ các nhóm lifecycle; không gộp median bằng trung bình.
- Lifecycle: Active: 20,195; Win-back: 1.
  Forecast chưa có nhãn tương lai để xác minh; lifecycle chỉ là presence proxy.

**Ví dụ quan hệ sản phẩm lịch sử (nguồn 13, nhánh persona affinity):**
| Đang có A, chưa có B → mở B tháng sau | Exposure khách-tháng | Acquisitions | Confidence quan sát |
|---|---:|---:|---:|
| prod_mas_particular_account → prod_eaccount | 562 | 137 | 24.38% |
| prod_direct_debit → prod_payroll_account | 4,015 | 393 | 9.79% |

Các luật trên được hiển thị theo lift, là mô tả lịch sử có support; không phải top-7 cuối hoặc tác động nhân quả. Export chính vẫn dùng recent3_temporal đã khóa.

**Cách dùng kết quả:**
- Kiểm tra đóng/mở lại trước khi gọi là tăng trưởng; chưa suy ra churn hay lợi nhuận.
- CLV-proxy ưu tiên khách, affinity chọn sản phẩm; chưa có top-7 customer-level để tổng hợp tần suất gợi ý thật.
- RFM là tag chi tiết; nhãn F4 cuối và nhãn nguồn CLV được phân biệt trong bảng tổng hợp.

**Giới hạn:** F=0 là chưa quan sát event trong lịch sử dataset; card là mô tả, không thêm mô hình dự đoán.

---

# P5 — Acquisition lặp lại, danh mục 2–4 sản phẩm

Acquisition lặp lại, danh mục 2–4 sản phẩm; demographics gần mặt bằng hơn P2/P6.

**Nguồn:** output notebook 10 và 14 đã chạy, snapshot 2016-05. Số liệu lấy từ bảng hiển thị được lưu; không tái tính từ raw.

- Rule: `F_event_months >= 2; 2 <= n_products <= 4`; chỉ áp dụng trên cohort persona đủ điều kiện upstream.
- Quy mô: 62,588 khách; 6.83% cohort persona; 6.54% known population.
- F trung vị: 3 tháng có event; số sản phẩm trung vị: 3.
- Acquisition t+1 trong development (source 2015-12–2016-04): **13.58% - 22.53%**.
  Đây là min–max tỷ lệ nhóm qua tháng, không phải khoảng xác suất cá nhân hay CI.

| Thuộc tính | Median | Q25 - Q75 | Coverage | Median baseline |
|---|---:|---:|---:|---:|
| age | 42.0 | 33.0 - 51.0 | 100.00% | 38.0 |
| renta | 105,946.1 | 71,495.3 - 160,267.8 | 78.70% | 101,493.4 |
| antiguedad | 54.0 | 21.0 - 145.0 | 100.00% | 54.0 |

Thu nhập chỉ mô tả khách có renta hợp lệ; chưa phải giá trị tiền tạo cho ngân hàng.

**Profile ổn định qua 6 tháng:**
- age: trung vị từng tháng trong khoảng 42 - 42; không chứng minh cùng khách giữ nguyên persona.
- antiguedad: trung vị từng tháng trong khoảng 52 - 59; không chứng minh cùng khách giữ nguyên persona.
- Top canal_entrada tại tháng cuối: KFC: 29.2%; KAT: 28.5%; KHE: 9.3%.
- Top nomprov tại tháng cuối: MADRID: 41.3%; BARCELONA: 7.4%; VALENCIA: 4.7%.

**Dự báo và trạng thái hiện tại (nguồn notebook 12):**
- Mean CLV-proxy 1 tháng ≈ **0.183516**; coverage 100.00%; method ML_RFM_stable.
  Output nguồn là points; mọi product weight=1 nên cùng đơn vị số acquisition. Mean gộp theo n từ các nhóm lifecycle; không gộp median bằng trung bình.
- Lifecycle: Active: 62,588.
  Forecast chưa có nhãn tương lai để xác minh; lifecycle chỉ là presence proxy.

**Ví dụ quan hệ sản phẩm lịch sử (nguồn 13, nhánh persona affinity):**
| Đang có A, chưa có B → mở B tháng sau | Exposure khách-tháng | Acquisitions | Confidence quan sát |
|---|---:|---:|---:|
| prod_short_term_deposit → prod_eaccount | 260 | 68 | 26.15% |
| prod_payroll → prod_payroll_account | 3,656 | 1,651 | 45.16% |

Các luật trên được hiển thị theo lift, là mô tả lịch sử có support; không phải top-7 cuối hoặc tác động nhân quả. Export chính vẫn dùng recent3_temporal đã khóa.

**Cách dùng kết quả:**
- Ứng viên thử bán chéo sản phẩm chưa sở hữu, kiểm tra bằng thử nghiệm khi có dữ liệu triển khai.
- CLV-proxy ưu tiên khách, affinity chọn sản phẩm; chưa có top-7 customer-level để tổng hợp tần suất gợi ý thật.
- RFM là tag chi tiết; nhãn F4 cuối và nhãn nguồn CLV được phân biệt trong bảng tổng hợp.

**Giới hạn:** F=0 là chưa quan sát event trong lịch sử dataset; card là mô tả, không thêm mô hình dự đoán.

---

# P6 — Acquisition lặp lại, danh mục ≥5 sản phẩm

Acquisition lặp lại, danh mục rộng; khách lâu năm và lớn tuổi hơn mặt bằng.

**Nguồn:** output notebook 10 và 14 đã chạy, snapshot 2016-05. Số liệu lấy từ bảng hiển thị được lưu; không tái tính từ raw.

- Rule: `F_event_months >= 2; n_products >= 5`; chỉ áp dụng trên cohort persona đủ điều kiện upstream.
- Quy mô: 27,611 khách; 3.01% cohort persona; 2.89% known population.
- F trung vị: 3 tháng có event; số sản phẩm trung vị: 6.
- Acquisition t+1 trong development (source 2015-12–2016-04): **10.88% - 20.67%**.
  Đây là min–max tỷ lệ nhóm qua tháng, không phải khoảng xác suất cá nhân hay CI.

| Thuộc tính | Median | Q25 - Q75 | Coverage | Median baseline |
|---|---:|---:|---:|---:|
| age | 46.0 | 40.0 - 53.0 | 100.00% | 38.0 |
| renta | 123,808.4 | 83,144.5 - 185,427.3 | 87.00% | 101,493.4 |
| antiguedad | 154.0 | 84.0 - 193.0 | 100.00% | 54.0 |

Thu nhập chỉ mô tả khách có renta hợp lệ; chưa phải giá trị tiền tạo cho ngân hàng.

**Profile ổn định qua 6 tháng:**
- age: trung vị từng tháng trong khoảng 46 - 46; không chứng minh cùng khách giữ nguyên persona.
- antiguedad: trung vị từng tháng trong khoảng 151 - 157; không chứng minh cùng khách giữ nguyên persona.
- Top canal_entrada tại tháng cuối: KAT: 47.3%; KFC: 30.5%; KFA: 4.9%.
- Top nomprov tại tháng cuối: MADRID: 55.9%; BARCELONA: 7.3%; SEVILLA: 4.0%.

**Dự báo và trạng thái hiện tại (nguồn notebook 12):**
- Mean CLV-proxy 1 tháng ≈ **0.135894**; coverage 100.00%; method ML_RFM_stable.
  Output nguồn là points; mọi product weight=1 nên cùng đơn vị số acquisition. Mean gộp theo n từ các nhóm lifecycle; không gộp median bằng trung bình.
- Lifecycle: Active: 27,611.
  Forecast chưa có nhãn tương lai để xác minh; lifecycle chỉ là presence proxy.

**Ví dụ quan hệ sản phẩm lịch sử (nguồn 13, nhánh persona affinity):**
| Đang có A, chưa có B → mở B tháng sau | Exposure khách-tháng | Acquisitions | Confidence quan sát |
|---|---:|---:|---:|
| prod_mas_particular_account → prod_eaccount | 2,497 | 290 | 11.61% |
| prod_home_account → prod_current_account | 1,314 | 33 | 2.51% |

Các luật trên được hiển thị theo lift, là mô tả lịch sử có support; không phải top-7 cuối hoặc tác động nhân quả. Export chính vẫn dùng recent3_temporal đã khóa.

**Cách dùng kết quả:**
- Tìm khoảng trống danh mục; không mặc định nhóm này luôn có xác suất mua cao nhất.
- CLV-proxy ưu tiên khách, affinity chọn sản phẩm; chưa có top-7 customer-level để tổng hợp tần suất gợi ý thật.
- RFM là tag chi tiết; nhãn F4 cuối và nhãn nguồn CLV được phân biệt trong bảng tổng hợp.

**Giới hạn:** F=0 là chưa quan sát event trong lịch sử dataset; card là mô tả, không thêm mô hình dự đoán.
