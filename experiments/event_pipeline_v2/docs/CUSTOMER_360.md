# Customer 360 — Track A

Dashboard local, chỉ đọc: chọn mã khách, từ tháng / đến tháng (tháng as-of) tùy ý,
hoặc chọn nhanh 6 / 12 / toàn bộ lịch sử (tối đa 24 tháng). Không cần cài thêm
web framework hoặc gọi dịch vụ AI.
Giao diện tiếng Việt, biểu đồ SVG; không tải tài nguyên từ CDN.

## Chạy

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
Chỉ mở pickle do chính pipeline của mình tạo và tin cậy.

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
| Persona C | Frozen KMeans từ Track A; chỉ gán từ fit month, chỉ khách đủ ownership; peer summary tính lại đúng tháng |
| Affinity | Tối đa 5 SP chưa sở hữu có điểm dương hữu hạn, xếp điểm giảm dần; không phải xác suất đã hiệu chỉnh |

Khách vắng vẫn có trong lifecycle/search nếu đã xuất hiện đến tháng đó, nhưng
R/F/M/ownership/CLV không được điền từ lần quan sát cũ. Trước lần xuất hiện đầu
tiên hiển thị “Chưa xuất hiện”. Cụm C1…Ck không có thứ tự giá trị.

Phần “Khách thuộc nhóm nào?” hiển thị ngang toàn chiều rộng: C bên trái và P
bên phải (màn hình nhỏ tự xếp dọc). C giải thích cách KMeans gán hồ sơ vào tâm
cụm gần nhất sau preprocessing và hiển thị đặc điểm cohort cùng tháng. P hiện
quy tắc F/số SP cùng số liệu cụ thể của khách, ví dụ P5 = F≥2 và 2–4 SP.
Hai mã C/P mô tả hai góc nhìn song song, không phải điểm đánh giá khách.

**C là chân dung đa chiều, có demographics:** phần C có bảng tuổi, thu nhập
`renta`, thâm niên, kênh và phân khúc của khách so với cụm tại đúng tháng chấm
điểm. Số cụm dùng trung vị cho số, mode/tỷ trọng cho danh mục và hiển thị coverage
của dữ liệu số. Thiếu demographics giữ null, không thay bằng 0. Bảng mô tả đặc
điểm điển hình, không đặt điều kiện rằng mọi khách phải giống trung vị hoặc
kênh phổ biến của cụm. Thu nhập giữ đơn vị nguồn, không diễn giải thành lợi nhuận.

Mô hình đang phục vụ là **persona multiblock KMeans**, dùng cả demographics,
RFM, CLV-proxy, portfolio và affinity. C2 của mô hình này không phải C2 của
KMeans RFM notebook 03 hoặc một mô hình chỉ gom demographics. UI ghi rõ số
cụm và tháng fit; không đổi tên hay fit lại để ép các nhãn trùng nhau. Trạng
thái Active từ nguồn cũng không có nghĩa khách đã mở thêm sản phẩm (F>0).

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
persona C/P và số SP mở/rời. Hover ô mở/rời để xem tên SP. Nút JSON tải hồ sơ
về máy; file đó chứa dữ liệu khách, cần giữ ngoài Git/public report.

## Chính sách ưu tiên `customer-care-v1`

Đây là heuristic hỗ trợ phân bổ chăm sóc / thử nghiệm cross-sell. Không phải
quyết định cho vay, định giá, tín dụng hay đánh giá lợi nhuận khách.
Không dùng tuổi, giới tính, thu nhập hoặc địa lý để đặt mức ưu tiên; mô hình
persona nghiên cứu hiện có vẫn sử dụng demographic features để mô tả cụm.

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

- Bản hiện kiểm tra trên sample 10k, 17 tháng 2015-01…2016-05. Không phải kiểm
  chứng tải trên full dữ liệu. Loader giữ các feature/lifecycle/status trong RAM;
  muốn full scale cần truy vấn partition theo tháng/ID hoặc kho dữ liệu có index.
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
python -m unittest discover -s tests -p test_customer360.py -v
```

11 synthetic contract tests: không dùng tháng tương lai, không gán cụm trước fit,
absence/null và cặp sự kiện bị đứt, ownership mask, activity/death/unknown gates,
midrank ties, invalid CLV, policy thresholds, cờ deceased trong lịch sử và
HTTP no-store/Host/Origin/validation.
Hai test bổ sung kiểm tra demographics khách/cụm đúng tháng và coverage/null
không thành 0 hoặc dùng demographics của tháng tương lai.
Không cần raw thật cho CI.
