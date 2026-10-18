# Bước 1 — Chốt phương án bàn giao v1

Đây là quyết định đóng gói sau khi đã xem development/backtest, không phải tuyên bố có một holdout mới chưa từng dùng để chọn phương pháp. Không train, tune hoặc chọn lại phương pháp từ test trong pipeline wrap.

| Thành phần | Chốt v1 | Vai trò và lý do |
|---|---|---|
| Event | 0→1 trên hai snapshot liền tháng có cờ hợp lệ; gồm reopen | Tháng đầu/gap/NaN không tự trở thành acquisition |
| R | Tháng từ acquisition quan sát gần nhất | Không có event: R thiếu; không gán R=0 |
| F | F_event_months; giữ F_events để audit | Đếm tháng có event, tránh đồng nhất số sản phẩm mở với số lần hoạt động |
| M | M_group_points hiện có của notebook 01 | 100 × tỷ lệ acquisition lịch sử theo đúng danh mục hiện tại; không phải monetary hoặc tổng single-product weights |
| RFM | Hybrid_REDA_F4_M5, edges fit 2015-11 | R: 0 / 1–2 / 3–7 / ≥8; F: 1 / 2 / 3–4 / ≥5; M: quantile 5 học từ fit. Giữ ties. Tốt trong development và cùng biến thể notebook 13/persona RFM audit |
| Lifecycle | lifecycle-v3-presence-gap6 | Hiện diện/vắng panel; vắng 1–5 tháng At-risk, ≥6 Churned proxy; quay lại sau ≥6 tháng Win-back trong tháng quay lại. New: tuổi quan hệ ngân hàng <2 tháng theo fecha_alta; không đồng nhất first-seen với New |
| Persona | Cây P1–P6 tree6-nov2015-v1 | Giữ 6 lá và tiêu chí eligibility upstream. Tree học nhãn Nov→Dec; nhóm hành vi dễ bàn giao; demographics bổ sung mô tả |
| CLV chính | acquisitions / 1 tháng / ML_RFM_stable | Method khóa từ validation Nov→Dec. Mục tiêu ưu tiên theo capture@10%, không chọn model RMSE tốt nhất để thay ranking model |
| CLV phụ | 3 tháng ML_RFM_only; 6 tháng ML_full cố định | Giữ bảng nghiên cứu; 6m ít mốc độc lập và không có model selection đáng tin. Không mở rộng claims thành tiền hoặc CLV cả đời |
| Affinity chính | recent3_temporal / top7 | Method đã khóa ở source Dec2015; window=3. Dù temporal hoặc blend tốt hơn trên test, không đổi lựa chọn |
| Affinity persona | temporal trong nhánh so sánh persona | Đây là selection riêng của notebook 13, không thay export chính recent3_temporal. Các biến thể persona là ablation |
| Demographics | age/renta/antiguedad/canal_entrada/segmento + sexo/nomprov | Mô tả mỗi tháng, không refit persona và chưa có bằng chứng incremental predictive value |

## Tách rõ phiên bản và tránh diễn giải sai

- Notebook 05/06 và nguồn metadata dùng để train CLV 07 có thể gắn nhãn Hybrid_REDA_F3_M5. Notebook 13 và audit persona dùng F4. Bản wrap tính lại **tag mô tả F4** từ edges đã fit, không fit lại mô hình.
- `rfm_cluster` + `rfm_method` là tag cuối F4. `clv_source_rfm_cluster` giữ nhãn nguồn nếu có trong output 07. Không coi hai hệ F3/F4 có cùng ý nghĩa chỉ vì cùng tên R1_F3_M5.
- M của notebook 01 đã dùng history result_month ≤ feature_month. Nhưng lựa chọn biến thể/ngưỡng dựa trên các tháng backtest vẫn là development selection. Cần temporal holdout mới nếu muốn kết luận generalization mới.
- BGNBD benchmark có baseline fallback cho phần lớn khách; phải báo coverage cùng metric. Gamma-Gamma chỉ là thử nghiệm với proxy giá trị mỗi event-month.
- Mọi trọng số sản phẩm CLV hiện bằng 1 nên points=acquisitions; chỉ báo một target chính.
- Thẻ persona là cách tóm tắt, không tăng chất lượng dự đoán. Hành động là giả thuyết, chưa có uplift/conversion hoặc lợi nhuận do can thiệp được đo.

## Tiêu chí chấp nhận artifact cuối

Một dòng mỗi known customer-tháng, kể cả không đủ điều kiện persona/CLV; không điền thiếu thành score 0. Top7 không lặp, không chứa sản phẩm đang sở hữu đối với danh mục hiện tại đầy đủ. Danh mục cũ phải có cờ xác minh trước tiếp cận.
