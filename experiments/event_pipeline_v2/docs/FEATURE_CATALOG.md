# Feature catalog v1 — dùng tại origin t

Đơn vị một dòng input là `(customer_id, origin_month)`. ID chỉ để join; không đưa ID vào model. Nhãn là sản phẩm mở thêm ở t+1, lưu tách khỏi feature. Dữ liệu lịch sử đều là phần **đã quan sát**, không đại diện đầy đủ vòng đời trước 2015-01.

## Danh sách cột đưa vào model

| Nhóm | Cột | Cách tính/ý nghĩa | Vì sao thêm |
|---|---|---|---|
| Baseline | 24 cờ sản phẩm gốc | 0/1 sở hữu ở t | Model biết portfolio hiện tại; dùng mask ở output |
| Baseline | `age`, `renta`, `antiguedad` | Thuộc tính ở t; giá trị sai thành missing | Bối cảnh tuổi, thu nhập, thâm niên |
| Baseline | `canal_entrada`, `segmento`, `sexo`, `nomprov` | Categorical, one-hot fit trên train | Phân biệt bối cảnh khách/kênh/địa bàn |
| Baseline | `relationship_age_months` | Số tháng từ `fecha_alta` đến t; ngày tương lai thành missing | Nhận diện khách mới theo tuổi quan hệ |
| Baseline | `n_products` | Tổng 24 cờ ở t; missing nếu portfolio thiếu | Mức độ rộng portfolio |
| Baseline | `observed_pairs` | Số cặp snapshot liên tiếp, đủ cờ đã quan sát đến t | Độ dài lịch sử đủ tin cậy; tránh đồng nhất mới quan sát với không có event |
| Baseline | `calendar_month` | Tháng 1–12 | Mùa vụ; chưa encode sin/cos trong v1 |
| RFM | `R` | Số tháng từ acquisition được xác minh gần nhất đến t | Độ gần của event mở sản phẩm; không phải lần giao dịch ngân hàng gần nhất |
| RFM | `F_event_months` | Số tháng có ít nhất một acquisition hợp lệ từ history_start đến t | Nhịp mở sản phẩm; một tháng mở ba sản phẩm vẫn cộng 1 |
| RFM | `M_group_points` | Tỷ lệ customer-month có acquisition ở tháng kế tiếp, theo **đúng tổ hợp portfolio**, chỉ từ cặp lịch sử có label ≤t | Portfolio response propensity; là proxy hành vi, **không phải tiền/giá trị sinh lời** |
| RFM | `rfm_no_event` | Chưa quan sát được acquisition hợp lệ trong lịch sử | Phân biệt R thiếu với R=0 |
| RFM | `rfm_m_missing` | Chưa có tổ hợp portfolio trùng trong lịch sử đủ điều kiện | Báo M proxy thiếu độ phủ |
| CLV | `clv_expected_acquisitions_1m` | Poisson gradient boosting dự báo số sản phẩm sẽ mở thêm ở t+1 | Tín hiệu cường độ acquisition tương lai, không phải tiền CLV |
| CLV | `clv_unavailable` | 1 khi chưa đủ dữ liệu fit model, dùng mean fallback hoặc không có giá trị | Phân biệt dự báo model với fallback |
| Persona | `persona_id` | `P1`…`P6`/`UNKNOWN`, categorical | Gói hành vi thành nhóm dễ diễn giải; có thể trùng thông tin RFM/portfolio |
| Persona | `persona_unavailable` | Lịch sử <3 cặp quan sát hoặc trước mốc rule khả dụng | Không ép khách thiếu lịch sử vào persona chắc chắn |
| Lifecycle | `lifecycle` | `New`, `Active`, `Win-back` trên snapshot hiện tại | Bối cảnh tuổi quan hệ và việc quay lại dữ liệu |
| Lifecycle | `missing_months` | Số tháng vắng liên tiếp trước lần xuất hiện ở t | Thêm tín hiệu khoảng trống quan sát |
| Affinity | `affinity_<product>` ×24 | Điểm liên kết temporal cho từng sản phẩm chưa sở hữu | Tín hiệu “portfolio này thường đi trước acquisition sản phẩm nào” |

Khi tất cả nhóm bật: **64 cột numeric + 6 cột categorical = 70 cột input gốc**. Sau one-hot/imputation số cột tăng theo dữ liệu train. Baseline có 31 numeric + 4 categorical. File `feature_manifest.json` là nguồn kiểm tra chính xác của mỗi run.

## Chính xác cách tính các nhóm

### RFM-proxy

Để tính M, mỗi cặp `(portfolio ở s, có acquisition ở s+1)` chỉ được đưa vào thống kê tại origin t nếu `s+1≤t`. Tỷ lệ dùng tất cả cặp lịch sử hợp lệ, không lấy nhãn tương lai của chính origin t. Tổ hợp chưa từng quan sát có M missing và cờ missing=1. Portfolio mới ở t không bị mặc định response bằng 0.

M này là lựa chọn thực nghiệm trong pipeline mới, không thay thế định nghĩa monetary của retail. V1 không fit quantile/k-means tiering và không thêm R/F/M tier ordinal. Khi cần giữ công thức RFM của notebook cũ, thay module feature và version tài liệu; không trộn hai định nghĩa cùng tên trong một experiment.

### CLV-proxy

Tại mỗi t, fit một model từ các origin lịch sử `s<t`, label đếm acquisition có tháng kết quả `s+1≤t`. Dùng cả khách không có acquisition, vì label đếm cần cả giá trị 0. Điều kiện event-only **chỉ áp dụng cho model multiclass cuối**, không áp dụng cho model đếm CLV.

Input nội bộ CLV là `BASE_NUM` trong `pipeline/common.py`: baseline numeric, không dùng persona, RFM hoặc affinity. Giới hạn row qua `clv_max_train_rows`, sampling đều quota theo tháng, seed cố định. Nếu ít hơn `clv_min_train_rows` hoặc mọi label=0: trả trung bình lịch sử và cờ unavailable=1; chưa có label lịch sử: trả NaN và cờ=1.

Không có BG/NBD, Gamma-Gamma, doanh thu hay chiết khấu tiền trong bản này. Horizon là **1 tháng**, phù hợp label ranker. Nếu muốn dự báo 6/12 tháng thì phải tạo nhãn cửa sổ tương ứng, dời mốc availability và cần lịch sử đủ dài.

### Persona

Bản này sử dụng **rule-based persona v1**, không fit decision tree mới và không khẳng định đang tải lại tree đã train trong notebook cũ. Ngưỡng được khai báo trước, chỉ áp dụng từ `persona_rules_available_from`. Mốc mặc định là 2015-12; chỉ đổi về sớm hơn nếu bộ quy tắc đã thực sự được chốt trước thời điểm backtest đó.

| Persona | Điều kiện sau khi đủ ≥3 cặp quan sát |
|---|---|
| P1 | F=0 và n_products≤2 |
| P2 | F=0 và n_products≥3 |
| P3 | F=1 |
| P4 | F≥2 và n_products≤1 |
| P5 | F≥2 và 2≤n_products≤4 |
| P6 | F≥2 và n_products≥5 |

Tên P1–P6 là ID nhóm, không phải nhãn “tốt/xấu” hoặc thứ tự giá trị khách hàng. Không đưa ID như số 1…6 vào regression; model nhận one-hot. “Persona hữu ích” phải được kiểm tra bằng độ phủ, cỡ nhóm, ổn định theo tháng và tăng chất lượng validation khi bật nhóm này. V1 xuất feature để kiểm tra, chưa tự viết báo cáo stability persona.

Nếu đưa tree được học từ dữ liệu vào pipeline sau này, cần artifact version + thời điểm fit; dự đoán persona quá khứ chỉ được dùng tree đã khả dụng tại quá khứ đó. Không fit tree trên toàn lịch sử rồi backfill persona cho các origin trước khi fit.

### Lifecycle

Khách đang xuất hiện tại t:

1. Vắng ≥6 tháng trước đó rồi quay lại: `Win-back`.
2. Nếu không, tuổi quan hệ <2 tháng: `New`.
3. Còn lại: `Active` theo quy ước quan sát.

Không có record hiện tại cho khách đang vắng, nên `At-risk` và `Churned` **không xuất hiện trong cohort recommendation v1**. `Active` ở đây không xác nhận có giao dịch; v1 chưa dùng `ind_actividad_cliente`, `indfall` và không kết luận vắng dữ liệu là đã đóng tài khoản. Nếu đã có lifecycle upstream với định nghĩa khác, phải bổ sung adapter + kiểm tra provenance thay vì gán cùng tên rồi coi tương đương.

### Temporal affinity

Dùng tối đa `affinity_window_months` cặp gần nhất, chỉ có label đã quan sát đến t. Với sản phẩm hiện hữu i và sản phẩm chưa sở hữu j:

- `count[i,j]`: số cặp sở hữu i rồi mở j ở tháng sau.
- `exposure[i,j]`: số cặp sở hữu i và chưa sở hữu j ở origin.
- `pop[j]`: acquisition j / số cơ hội chưa sở hữu j.
- `conditional[i,j]=(count[i,j]+prior×pop[j])/(exposure[i,j]+prior)`; đường chéo=0.
- `affinity_j = 0.5×mean(conditional[i,j] theo các i đang sở hữu)+0.5×pop[j]`.
- Khách chưa sở hữu sản phẩm nào có thành phần mean=0; cờ sản phẩm đang sở hữu được đặt điểm feature=0 và bị mask ở output.

Đây là điểm heuristic dùng như feature, chưa calibration xác suất. Không phải co-occurrence tĩnh, Apriori hay item2vec; v1 ưu tiên sự kiện mở tiếp theo đúng bài toán label.

## Missing, cleaning và hợp đồng thời gian

- Không xóa trẻ dưới 18 tuổi: sản phẩm junior có thể hợp lệ. `age<0` hoặc `age>110` chuyển missing; ngưỡng 110 là kiểm tra chất lượng có thể sửa theo data dictionary.
- `renta`/`antiguedad` âm hoặc không finite chuyển missing, không tự coi bằng 0. Tuổi/thu nhập dạng không parse được cũng chuyển missing.
- Categorical missing dùng `__MISSING__`; category chưa thấy lúc fit được one-hot ignore. Numeric median và indicator được fit trên train, không fit lại trên validation/test.
- Product missing được giữ missing, không tự biến thành 0. Khách có snapshot thiếu cờ không đủ điều kiện tính label hoặc mask sở hữu.
- R chưa quan sát event có thể bị left-censoring. F là đếm trên lịch sử nhìn thấy, không phải toàn bộ lịch sử thật của khách.
- `month`, `customer_id`, `fecha_alta`, `product_complete` là metadata/trung gian, không đưa trực tiếp vào ranker. Không dùng actual future acquisitions, actual future CLV, actual future persona làm input.
- Availability: feature t dùng snapshot t và outcome của các cặp kết thúc tối đa ở t; label t+1 chỉ dùng ở bước train/evaluate.
- Refresh dự kiến: batch hàng tháng sau khi có snapshot. V1 là offline artifact; chưa triển khai online Feature Store hoặc TTL tự động. Nếu triển khai, kiểm tra age của snapshot và mốc dữ liệu đến, không forward-fill qua khoảng trống rồi gán acquisition.
