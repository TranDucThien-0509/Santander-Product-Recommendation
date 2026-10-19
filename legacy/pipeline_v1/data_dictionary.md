# Data Dictionary — Santander Product Recommendation (Checkpoint 1)

Mô tả toàn bộ 81 cột trong `cleaned_long_format.parquet` — dataset ở dạng **long format**
(1 dòng = 1 khách hàng × 1 tháng × 1 trong 24 sản phẩm).

## 1. Định danh & thời gian

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `ncodpers` | int64 | Mã khách hàng |
| `fecha_dato` | datetime | Ngày snapshot dữ liệu (cuối mỗi tháng) |
| `fecha_alta` | datetime | Ngày khách trở thành khách hàng đầu tiên của ngân hàng |
| `month` | int32 | Tháng (1–12), trích từ `fecha_dato` |
| `month_id` | int64 | ID tháng tăng dần (1, 2, 3...) thay cho `fecha_dato`, tiện sort/join |
| `product` | str | Tên 1 trong 24 sản phẩm — cột định danh sinh ra khi melt sang long format, **không phải feature** |
| `status` | str | Nhãn trạng thái sản phẩm này trong tháng: `Added` (mới mua), `Dropped` (vừa hủy), `Maintained_Owned` (đã có, vẫn giữ), `Maintained_NotOwned` (chưa có, vẫn chưa có — nhãn 0 cho task "dự đoán sản phẩm mới") |

## 2. Thuộc tính khách hàng gốc (tháng hiện tại)

| Cột | Kiểu | Ý nghĩa | Xử lý |
|---|---|---|---|
| `age` | int64 | Tuổi | Ép numeric, impute missing |
| `ind_nuevo` | float64 | Cờ khách mới (đăng ký <6 tháng) | Giữ nguyên |
| `antiguedad` | float64 | Thâm niên khách hàng (tháng) | Impute missing |
| `indrel` | float64 | 1 = khách chính; 99 = khách chính trong tháng nhưng không phải lúc cuối tháng | Giữ nguyên |
| `indresi` | int8 | Cờ cư trú cùng nước với ngân hàng | Map S/N → 1/0 |
| `indext` | int8 | Cờ khách nước ngoài | Map S/N → 1/0 |
| `ind_actividad_cliente` | float64 | Cờ hoạt động (1 active / 0 inactive) | Giữ nguyên |
| `renta` | float64 | Thu nhập hộ gia đình | Impute missing |
| `has_ult_fec_cli_1t` | int8 | Có giá trị `ult_fec_cli_1t` (ngày cuối làm khách chính) hay không | Cột gốc bị drop (quá nhiều missing), giữ lại dạng cờ 0/1 |

## 3. Cờ hành vi / thay đổi (so với tháng trước)

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `segmento_changed` | int64 | 1 nếu `segmento` đổi so với tháng trước |
| `tiprel_1mes_changed` | int64 | 1 nếu `tiprel_1mes` (loại quan hệ) đổi so với tháng trước |
| `ind_actividad_cliente_changed` | int64 | 1 nếu activity index đổi so với tháng trước |
| `ind_actividad_cliente_lag_1` | float64 | Giá trị activity index tháng trước (giữ dạng numeric, không one-hot vì đã nhị phân) |

## 4. One-hot — biến categorical bậc thấp (tháng hiện tại)

| Nhóm cột | Categories |
|---|---|
| `segmento_01 - TOP`, `segmento_02 - PARTICULARES`, `segmento_03 - UNIVERSITARIO`, `segmento_UNKNOWN` | Phân khúc khách hàng; `UNKNOWN` = bucket cho missing |
| `sexo_H`, `sexo_UNKNOWN`, `sexo_V` | Giới tính |
| `tiprel_1mes_A`, `_I`, `_P`, `_R` | Loại quan hệ đầu tháng: Active/Inactive/Former/Potential |
| `indrel_1mes_1`, `_2`, `_3`, `_4`, `_P` | Loại khách đầu tháng: chính/đồng sở hữu/cựu chính/cựu đồng sở hữu/tiềm năng |
| `ind_empleado_A`, `_B`, `_F`, `_N`, `_UNKNOWN` | Loại nhân viên: Active/Ex-employed/Filial/Not employee |

Mỗi nhóm one-hot: tổng theo dòng luôn = 1 (đã verify).

## 5. One-hot — bản THÁNG TRƯỚC của segmento/tiprel_1mes (fix đã thêm)

| Nhóm cột | Ghi chú |
|---|---|
| `segmento_lag_1_01 - TOP`, `_02 - PARTICULARES`, `_03 - UNIVERSITARIO`, `_UNKNOWN` | Bản lag 1 tháng của `segmento`. `UNKNOWN` bao gồm cả trường hợp khách chưa có tháng trước (NaN cấu trúc, không phải missing thật) |
| `tiprel_1mes_lag_1_A`, `_I`, `_P`, `_R`, `_UNKNOWN` | Tương tự cho `tiprel_1mes` |

*(Ban đầu 2 cột này bị sót, chưa encode — đã fix ở bản cập nhật.)*

## 6. Frequency encoding — biến categorical cardinality cao

| Cột | Ý nghĩa | Ghi chú |
|---|---|---|
| `canal_entrada_freq` | Tần suất (%) của kênh đăng ký (`canal_entrada`) trong toàn bộ dữ liệu | Cột string gốc đã bị drop sau khi encode |
| `pais_residencia_freq` | Tần suất (%) của nước cư trú | Cột string gốc đã bị drop |
| `nomprov_freq` | Tần suất (%) của tỉnh/thành | Cột string gốc đã bị drop |

## 7. Lag sản phẩm — TOÀN BỘ 24 sản phẩm, tháng trước (`_lag_1`)

24 cột `ind_<mã sản phẩm>_ult1_lag_1` (vd `ind_cco_fin_ult1_lag_1`, `ind_tjcr_fin_ult1_lag_1`...):
trạng thái sở hữu (0/1) của **từng sản phẩm trong số 24** ở tháng trước — dùng làm tín hiệu
"portfolio hiện có" của khách trước khi xét tháng hiện tại. Đây là 24 cột lặp lại giống nhau
trên cả 24 dòng melt của cùng 1 khách-tháng (vì đặc tả portfolio, không phụ thuộc `product`
của dòng đó).

## 8. Self-lag — lag của CHÍNH sản phẩm đang xét (`self_lag_2`–`self_lag_5`)

| Cột | Ý nghĩa |
|---|---|
| `self_lag_2`, `self_lag_3`, `self_lag_4`, `self_lag_5` | Trạng thái sở hữu (0/1) của **đúng sản phẩm ở cột `product`** của dòng đó, cách đây 2–5 tháng |

Khác với mục 7 (lag của tất cả 24 sản phẩm, chỉ tính lag 1 tháng), đây là lag sâu hơn
(2–5 tháng) nhưng chỉ giữ cho riêng sản phẩm đang xét — tránh nhân 24×4 cột dư thừa nếu giữ
lag 2–5 cho toàn bộ 24 sản phẩm.

## Lưu ý khi dùng cho modeling

- **`product` và `status`** không phải numeric feature — cần xử lý riêng: `product` dùng để
  group/filter (train riêng từng sản phẩm hoặc thêm vào model như 1 categorical), `status`
  dùng để tạo nhãn (`label = 1 nếu Added, 0 nếu Maintained_NotOwned`) rồi bỏ.
- 4 sản phẩm gần như không ai sở hữu (`ind_ahor_fin_ult1`, `ind_aval_fin_ult1`,
  `ind_deco_fin_ult1`, `ind_deme_fin_ult1` — ownership <0.25%) **chưa bị loại** khỏi dataset
  này. Các solution top của competition gốc loại 4 sản phẩm này trước khi train — cân nhắc
  làm tương tự ở checkpoint 2.
- Dataset chỉ chứa **sample ~10,000 khách hàng** (`LIMIT_PEOPLE`) từ 10 triệu dòng đầu file
  gốc (`LIMIT_ROWS`), phủ 01/2015–02/2016 (14 tháng, thiếu 3 tháng cuối so với bản gốc
  17 tháng). Không đại diện đầy đủ cho toàn bộ ~950k khách hàng thật.
