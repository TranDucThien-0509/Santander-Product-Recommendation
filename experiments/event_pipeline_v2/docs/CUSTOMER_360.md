# Customer 360 — Track A

Dashboard local, chỉ đọc: chọn mã khách, từ tháng / đến tháng (tháng as-of) tùy ý,
hoặc chọn nhanh 6 / 12 / toàn bộ lịch sử (tối đa 24 tháng). Không cần cài thêm
web framework hoặc gọi dịch vụ AI.
Giao diện tiếng Việt, biểu đồ SVG; không tải tài nguyên từ CDN.

## Khám phá lượt mở theo tháng

Trong cùng trang, chọn tab **Mở sản phẩm theo tháng**:

1. Bấm tháng trong bảng tổng hợp để xem số khách có mở thêm SP, tổng lượt mở
   và số khách đủ cặp snapshot để so sánh.
2. Bảng chi tiết có một dòng cho mỗi khách mở SP trong tháng, số SP mở thêm và
   tên từng SP. Sắp số SP giảm dần, rồi mã khách tăng dần; có lọc theo tiền tố
   mã khách và phân trang 25 khách/trang.
3. Bấm mã khách để mở hồ sơ Customer 360, tự chọn **tháng ghi nhận sự kiện** làm
   tháng chấm điểm. Nút **Trở lại lượt mở tháng…** quay về danh sách đó.

Lượt mở = cờ sở hữu **0→1** ở cặp tháng liên tiếp, cả hai snapshot đủ 24 cột
sở hữu. Một khách mở 2 SP được tính là 1 khách, 2 lượt. Có thể gồm mở lại SP.
Khách chỉ xuất hiện lần đầu, vắng tháng trước, hoặc thiếu ownership không được
gán lượt mở từ 0 giả định. Tháng đầu dataset (hoặc tháng không có cặp hợp lệ)
hiển thị chưa xác định, không biến thành một tháng 0 lượt. Bảng là quan sát
snapshot trên tập khách đang phục vụ; không phải xác nhận giao dịch hay danh sách đủ điều kiện
marketing. Các cờ activity/indfall vẫn được kiểm tra riêng khi mở hồ sơ.

API local `GET /api/acquisitions/summary` trả tổng hợp từng tháng;
`GET /api/acquisitions?month=YYYY-MM&q=...&page=1&page_size=25` trả khách có sự
kiện. Summary là toàn tháng; số khách kết quả/phân trang theo mã lọc. Chế độ xem
và tháng sự kiện lưu trong URL để phục hồi khi tải lại; không truyền dữ liệu ra
dịch vụ ngoài.

## Chạy trên toàn bộ dữ liệu

Store trên ổ đĩa hỗ trợ toàn bộ khách trong completed v2 run, không nạp toàn bộ
feature/lifecycle vào RAM. Cài `requirements.txt`, lấy các partition `features/`,
`lifecycle/`, config/manifest/audit/completed của cùng run và raw CSV đúng nguồn.
Không sửa đường dẫn trong config gốc. Build ghi SHA-256 của nguồn và kiểm tra
CRC32C raw với receipt của object nguồn khi truyền `--raw-crc32c`.

```powershell
python -m track_a.customer360_index `
  --source-run /path/to/completed-full-run `
  --raw-csv /path/to/train_ver2.csv `
  --raw-crc32c CHECKSUM_FROM_SOURCE_OBJECT `
  --out artifacts/customer360-full/customers.duckdb

python -m track_a.serve_customer360 `
  --index artifacts/customer360-full/customers.duckdb --port 8501
```

Build một lần với DuckDB memory limit 512 MB, một thread và spill ra ổ đĩa;
server chỉ đọc index với memory limit 256 MB. Đây là giới hạn memory manager
của DuckDB, không phải trần RSS của toàn bộ Python. Index mới cần đường dẫn
chưa tồn tại. Index lỗi/chưa có metadata success không được phục vụ.

RFM, lifecycle, nhãn P và CLV 1m lấy từ source full đúng thời điểm. Phân vị CLV
được tính lại trên cohort full cùng tháng. Affinity phục vụ được tính lại bằng
cùng công thức temporal-ownership-smoothed-24-v1, cửa sổ/prior trong config;
chỉ dùng cặp nhãn đến tháng chấm điểm, mask SP đang sở hữu. Kiểm thử đối chiếu
với `pipeline.features.affinity`, không trộn điểm hay model sample vào full.

Đây là mở rộng **phục vụ Customer 360** từ completed v2 full run, không đồng
nghĩa đã chạy lại các benchmark Track A 6m, clustering, SHAP hay notebook
nghiên cứu trên full. Các kết quả nghiên cứu sample vẫn giữ nguyên phạm vi.
Raw, index và customer artifacts nằm local/private, không đi kèm mã nguồn.

### Kiểm chứng full tại máy ngày 18/10/2026

Nguồn: `full_validation_selected_20261017T200237620339Z_9e8e42ca`, cùng
completed v2 run được ghi trong [CLOUD_RUNS.md](CLOUD_RUNS.md).

| Nội dung | Kết quả |
|---|---:|
| Khách duy nhất đã xuất hiện đến tháng cuối | 956.645 |
| Snapshot được quan sát | 13.647.309 |
| Khoảng tháng | 2015-01…2016-05 (17 tháng) |
| Lượt mở SP xác định từ cặp đầy đủ | 561.648 |
| Tháng 2015-07: khách mở / lượt mở | 26.097 / 33.362 |
| Dung lượng index | 972.566.528 byte |

CRC32C raw local khớp receipt object nguồn. Đã mở hồ sơ một khách ngoài
sample 10k cũ, xác minh 17 tháng, mask sở hữu, trang 1/2 không trùng khách và
đối chiếu tổng snapshot với full run. Dashboard tại cổng 8501 đã dùng index này.
Lần rà soát bổ sung đối chiếu ID quan sát với feature của cả 17 partition,
không có mismatch. Builder kiểm tra membership theo khóa, cờ quan sát và
tháng partition, không chỉ so số dòng hai tập.

Một lượt API smoke test sau build: hồ sơ 17 tháng 143 ms, bảng tháng 43,4 ms,
tìm khách 16,1 ms; hồ sơ lặp lại 2,5 ms. Đây là một lần đo local với cache hệ
điều hành đã được làm nóng bởi build, không phải kiểm thử tải đồng thời trên
full hoặc cam kết latency. Không đo lại độ chính xác dự báo trong bước phục vụ.

## Chạy trên sample đã có

Từ `experiments/event_pipeline_v2`, với environment đã cài `requirements-track-a.txt`:

```powershell
python -m track_a.serve_customer360 `
  --source-run artifacts/sample-10k-seed42/runs/mlflow_sample_10k_20261018T034306294124Z_96c55699 `
  --cache-dir artifacts/sample-10k-seed42/cache `
  --track-a-run artifacts/track-a/sample_10k_final `
  --port 8501
```

Mở <http://127.0.0.1:8501>. Có thể dùng interpreter `.venv/Scripts/python.exe`
trên Windows. Lệnh chạy foreground; Ctrl+C để dừng. Port khác: `--port 8502`.
Dashboard đọc snapshot và provenance; không nạp model clustering.

Các path trên là bộ **sample 10.000 khách** đã chạy tại máy phát triển, không
được commit vào Git. Clone mới cần lấy raw/private artifacts đúng provenance
hoặc chạy v2 all-features + `track_a.run` trước. Không có dữ liệu khách đi kèm
UI; không tự tải GCS. `Panel` kiểm tra completed source run, fingerprint raw,
manifest cache và cutoff label; loader còn đối chiếu SHA-256 raw/config/cache
manifest/audit với `run_provenance.json` của completed Track A run.

## Đọc hồ sơ

| Thành phần | Diễn giải |
|---|---|
| R | Số tháng từ lần mở thêm SP gần nhất; null nếu chưa có sự kiện hợp lệ |
| F | Số tháng có ít nhất 1 sự kiện mở thêm SP trong toàn lịch sử hợp lệ đến as-of, không chỉ cửa sổ hiển thị |
| M | `M_group_points`: portfolio propensity points của pipeline, không phải tiền; có cờ baseline |
| Danh mục | 24 ownership flags tại tháng as-of; sự kiện mở/rời chỉ khi 2 tháng liên tiếp đều đủ dữ liệu |
| Lifecycle | Presence lifecycle, bổ sung activity/indfall **đúng tháng**, không carry-forward trạng thái tương lai |
| CLV | Dự báo số SP mở thêm kỳ vọng tháng kế tiếp; không phải xác suất mua hay CLV bằng tiền |
| Phân vị CLV | Midrank trong khách cùng tháng: đang quan sát, đủ ownership, activity=1, indfall=N, CLV hợp lệ, ≥3 cặp tháng đầy đủ |
| Persona P | Rule label có sẵn trong feature tại tháng đó; giữ mốc availability của pipeline |
| Thông tin khách | Tuổi, thu nhập renta, thâm niên, kênh và phân khúc của chính khách tại tháng chấm điểm |
| Affinity | Tối đa 5 SP chưa sở hữu có điểm dương hữu hạn, xếp điểm giảm dần; không phải xác suất đã hiệu chỉnh |

Khách vắng vẫn có trong lifecycle/search nếu đã xuất hiện đến tháng đó, nhưng
R/F/M/ownership/CLV không được điền từ lần quan sát cũ. Trước lần xuất hiện đầu
tiên hiển thị “Chưa xuất hiện”.

Phần “Hồ sơ khách hàng” hiển thị ngang: thông tin cá nhân bên trái và nhóm hành
vi P bên phải (màn hình nhỏ xếp dọc). Bảng chỉ hiển thị tuổi, thu nhập `renta`,
thâm niên, kênh và phân khúc của chính khách tại tháng chấm điểm. Thiếu dữ liệu
giữ null / “Chưa có dữ liệu”, không điền trung vị từ khách khác. Thu nhập giữ
đơn vị nguồn, không diễn giải thành lợi nhuận. P hiện quy tắc F/số SP cùng số
liệu cụ thể của khách, ví dụ P5 = F≥2 và 2–4 SP.

Dashboard và JSON hồ sơ không còn cụm C, so sánh demographics với cụm hoặc
metadata mô hình clustering. Phần nghiên cứu Track A có artifact riêng; giao
diện Customer 360 tập trung vào hồ sơ từng khách.

Đổi **Lịch sử từ tháng** chỉ đổi cửa sổ quan sát, không tính lại F hoặc nhãn persona.
Đổi **Tháng chấm điểm** (tháng kết thúc) đổi thời điểm đánh giá toàn bộ hồ sơ. Ví dụ chọn
2015-03 → 2016-05 để xem 15 tháng. Chọn nhanh tự điều chỉnh tháng bắt đầu;
khoảng tùy chọn giữ tháng bắt đầu khi đổi tháng kết thúc nếu vẫn hợp lệ. Nếu
tháng kết thúc lùi trước tháng bắt đầu, UI thu khoảng về 1 tháng để tránh đảo
ngược thời gian. URL lưu số tháng thực tế và preset để phục hồi bộ lọc khi tải lại.

Ngay trên thẻ có tiêu đề **Điểm tại tháng YYYY-MM · Khách #ID**. Bấm mã tháng
trong bảng lịch sử để chọn tháng chấm điểm; dashboard tải lại đúng snapshot,
CLV, lifecycle và persona tại tháng ấy rồi cuộn lên khu vực điểm. Không refit
mô hình theo cửa sổ xem. Đổi tháng vẫn có thể giữ cùng R/F/lifecycle nếu hành
vi khách không đổi; điều đó không có nghĩa dữ liệu bị cache từ tháng khác.

Biểu đồ không nối qua tháng thiếu/vắng; bảng có R/F/M, số SP, CLV, lifecycle,
nhóm hành vi P và số SP mở/rời. Hover ô mở/rời để xem tên SP. Nút JSON tải hồ sơ
về máy; file đó chứa dữ liệu khách, cần giữ ngoài Git/public report.

Bấm số trong cột **Sản phẩm** hoặc điểm trên biểu đồ số SP để mở danh sách
sản phẩm đang sở hữu tại đúng snapshot tháng đó. Dialog ghi rõ mã khách/tháng,
đánh dấu SP mới ghi nhận khi có cặp tháng đầy đủ; có thể đóng bằng nút Đóng
hoặc Escape. Snapshot đủ dữ liệu và không sở hữu SP nào hiển thị danh sách 0;
tháng vắng/thiếu ownership hiển thị “—”, không mở danh sách giả định.

## Chính sách ưu tiên `customer-care-v1`

Đây là heuristic hỗ trợ phân bổ chăm sóc / thử nghiệm cross-sell. Không phải
quyết định cho vay, định giá, tín dụng hay đánh giá lợi nhuận khách.
Không dùng tuổi, giới tính, thu nhập hoặc địa lý để đặt mức ưu tiên.

Nếu nguồn từng ghi indfall=S đến tháng as-of, dashboard chặn tiếp cận tự động
và yêu cầu kiểm tra thủ công, kể cả khi snapshot hiện tại vắng hoặc cờ đổi.
Đây là cờ cảnh báo từ lịch sử; không giả định trạng thái hiện tại đã biết và
không nhìn cờ của tháng tương lai. Presence lifecycle vẫn giữ đúng tháng.

Theo thứ tự:

1. Từng có indfall=S đến as-of → dừng cross-sell tự động, kiểm tra nghiệp vụ.
2. Vắng snapshot → xác minh / tái kết nối.
3. Thiếu ownership hoặc activity/indfall chưa biết → bổ sung dữ liệu.
4. Không active → xác minh nhu cầu / giữ chân, không xuất affinity đề xuất.
5. Thiếu CLV hợp lệ hoặc <3 cặp tháng → theo dõi / thử nghiệm nhỏ.
6. Đủ điều kiện và CLV percentile ≥80 → ưu tiên thử nghiệm cross-sell.
7. Còn lại → duy trì chăm sóc chi phí thấp.

Ngưỡng 80 và 3 cặp là lựa chọn minh bạch ban đầu, chưa được tối ưu bằng uplift
hay ROI. Ties dùng midrank: mọi forecast bằng nhau có percentile 50, không đẩy
tất cả khách vào nhóm ưu tiên. “Đủ điều kiện so sánh” chỉ phản ánh dữ liệu,
không phải độ tin cậy thống kê hay xác suất dự báo đúng.

Để kết luận có nên tăng ngân sách thực tế cần thêm chi phí liên hệ, biên lợi
nhuận từng SP, conversion/uplift từ thử nghiệm có nhóm đối chứng và giới hạn
nghiệp vụ. Chưa có dự báo churn xác suất, CLV tiền, hay phục vụ mô hình CLV 6m
cho từng khách ở dashboard; không nhân CLV 1m với 6 để thay thế.

## Phạm vi và vận hành

- Chế độ `--index` truy vấn trên ổ đĩa; chế độ sample cũ giữ dữ liệu trong RAM.
  Cả hai giữ cùng hợp đồng point-in-time, xử lý thiếu dữ liệu và gates.
  Số khách trong header là số ID đã xuất hiện tính đến tháng cuối nguồn;
  không phải số snapshot hay số khách quan sát trong một tháng riêng lẻ.
- Chỉ bind 127.0.0.1, không có đăng nhập; không expose qua tunnel/reverse proxy
  hoặc sửa thành 0.0.0.0. Endpoint chỉ GET, không ghi model/raw/GCS, API/asset
  `no-store`, không CORS, kiểm tra Host/Origin; không log query chứa mã khách.
- Đây là local development server. Nếu triển khai dùng chung cần authentication,
  authorization theo khách, audit truy cập và review triển khai riêng.
- Peer percentile dùng cohort dữ liệu nguồn, không phải toàn dân số ngân hàng;
  CLV là mô hình sẵn có, không được refit khi người dùng đổi bộ lọc.
- URL `/?id=...&month=...&window=6` phục hồi bộ lọc trong cùng máy. Không chia sẻ
  URL/profile/screenshot khách lên repo công khai.

## Kiểm tra

```powershell
python -m unittest discover -s tests -p 'test_customer360*.py' -v
```

18 synthetic contract tests: không dùng tháng tương lai, hồ sơ không xuất cụm C,
absence/null và cặp sự kiện bị đứt, ownership mask, activity/death/unknown gates,
midrank ties, invalid CLV, policy thresholds, cờ deceased trong lịch sử và
HTTP no-store/Host/Origin/validation.
Hai test bổ sung kiểm tra thông tin khách đúng tháng và dữ liệu thiếu không
thành 0, không điền thông tin từ khách khác hoặc tháng tương lai.
4 test lượt mở kiểm tra nhiều SP trên một khách, đối chiếu với profile cùng
tháng, loại bỏ gap/first-seen/incomplete, chưa xác định khi thiếu toàn bộ cặp,
lọc/phân trang và bất biến khi dữ liệu tháng tương lai đổi. HTTP test kiểm tra
thêm hai endpoint cùng validation tháng/trang/mã lọc.
Không cần raw thật cho CI.

6 contract tests cho index: snapshot/profile/search/monthly pagination tương
đương store cũ; affinity khớp công thức pipeline; không dùng cờ deceased tương
lai; kiểm tra lỗi checksum và audit có nhãn tương lai; HTTP đồng thời trên
store chỉ đọc và chặn lệch ID/cờ quan sát/tháng partition dù số dòng bằng nhau.
Thêm 3 test affinity tháng trước: đúng origin dù window=1,
mask theo sở hữu trước sự kiện, giữ gates lịch sử và không gán outcome thiếu
bằng false. Tổng 24 tests.

### Diễn biến trước lượt mở

Khi mở khách từ danh sách lượt mở tháng, hồ sơ tự chọn toàn bộ lịch sử có sẵn
đến tháng sự kiện (tối đa 24 tháng), kể cả khi khoảng xem trước đó chỉ có một
tháng. Khối “Trước và tại tháng” ở đầu hồ sơ đối chiếu snapshot liền trước và
tháng đang chọn: lifecycle, số sản phẩm, R/F/M và CLV tại từng tháng; đồng thời
liệt kê tên sản phẩm mở thêm/rời. Mở thêm SP không bắt buộc đổi lifecycle.

Nút “Xem toàn bộ diễn biến đến tháng này” dẫn tới biểu đồ và bảng lịch sử.
Không đưa tháng sau sự kiện vào nhận định này. Nếu người dùng thu hẹp khoảng
xem còn một tháng, khối đối chiếu báo chưa có tháng trước trong khoảng xem;
không dùng snapshot gần nhất để lấp tháng vắng hoặc tự suy diễn giao dịch ngày.

Khối **Affinity tháng trước** lấy top 5 sản phẩm chưa sở hữu tại đúng tháng
liền trước, cùng điểm affinity được tính đến tháng đó. Ví dụ, xem 2016-05
thì hiển thị affinity tại 2016-04 và đối chiếu với các lượt mở ghi nhận trong
2016-05. Không lấy affinity tháng 5 để diễn giải ngược về tháng 4. Phần này
vẫn lấy được tháng trước khi cửa sổ biểu đồ chỉ còn một tháng.

Điều kiện hiển thị đề xuất được kiểm tra ở tháng trước (activity/indfall,
ownership, CLV hợp lệ và tối thiểu 3 cặp tháng), giống đề xuất hiện tại.
Nếu chưa đủ điều kiện, hiển thị lý do. Outcome là có/không ghi nhận mở trong
cặp snapshot đầy đủ; thiếu cặp thì “Chưa đối chiếu được”. Đây không phải xác
suất mua hoặc metric đánh giá toàn mô hình. API và JSON export chứa trường
`previous_affinity` với origin, target month, điểm và outcome riêng từng SP.
