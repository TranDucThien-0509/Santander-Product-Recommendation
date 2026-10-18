# Santander Customer Analytics

RFM-proxy, lifecycle, acquisition-proxy, affinity và sáu persona từ Santander Product Recommendation. Bộ repo này hoàn thiện **bước 1–4**: chốt lựa chọn, tổng hợp benchmark, chuẩn bị bảng khách hàng cuối và sáu persona card.

## Xem kết quả

- [Chốt phương pháp](docs/01_decisions.md)
- [Benchmark và cách đọc](docs/02_benchmarks.md)
- [Sáu persona card từ output thực tế](docs/04_persona_cards.md)
- [Nguồn input, lệnh chạy và output bảng cuối](docs/03_integration.md)
- [Schema](docs/data_dictionary.md) · [Giới hạn](docs/limitations.md)

**Đã có:** benchmark CSV trích từ output đã chạy và cards dùng số thực tế từ notebook 10/14. **Cần chạy trên Kaggle:** bảng khách hàng đầy đủ, phân bố CLV và top sản phẩm theo persona. Chúng cần Parquet nguồn, chưa có trong các file ipynb đính kèm.

## Cài và chạy phần wrap

Python 3.10+ (đã kiểm tra package trong Python 3.12).

```bash
python -m pip install -e .
cp configs/finalization.example.json config.local.json
# Sửa các đường dẫn nguồn theo docs/03_integration.md
santander-wrap build --config config.local.json
```

Nếu dùng Kaggle, mở [notebook 15](notebooks/15_finalize.ipynb). Đây là bước ghép output đã fit; không cần retrain để xuất artifact cuối.

```bash
python -m unittest discover -s tests -v
santander-wrap cards-evidence --repo .
```

Các kiểm tra dùng dữ liệu mô phỏng, không phải xác minh lại metric toàn Santander. Cài `python -m pip install -e '.[notebooks]'` để mở notebook nghiên cứu; đường dẫn Kaggle trong các notebook nguồn cần chỉnh theo môi trường.

## Thứ tự notebook nguồn

01 → 03 → 05; 06 dùng 01/03/05 để tạo cache; 07 dùng output 06. Nhánh persona: 08 → 09 → 10; 11/12 nối lifecycle và CLV. 13 dùng raw + 01/03/05 và thêm 08/10 ở phần persona affinity. 14 dùng raw +10. Cuối cùng 15 gọi package wrap với output đã chạy. 02 và 10b là phương án nghiên cứu đối chiếu.

Các notebook trong repo đã xóa output, giữ source để nhẹ và không phát tán preview customer-level. Benchmark aggregate được giữ trong `reports/evidence`; cell/output gốc và SHA256 bản upload nằm trong các manifest. Chưa chuyển toàn bộ training notebooks thành một CLI production.

## Cấu trúc

```text
configs/       Cấu hình ví dụ, không chứa credential
src/           Pipeline wrap và renderer persona cards
notebooks/     Notebook nghiên cứu + finalization
reports/       Benchmark aggregate và provenance
scripts/       Tạo báo cáo benchmark từ evidence
docs/          Định nghĩa, quyết định và persona cards
tests/         Kiểm tra ghép, coverage và lỗi nguồn
```

## Đưa lên GitHub

Giải nén repo rồi chạy trong thư mục này:

```bash
git init
git add .
git commit -m "Finalize Santander customer analytics handoff"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

Tạo repo trống trên GitHub trước và thay URL bằng repo của bạn. Kiểm tra danh sách staged bằng `git diff --cached --stat` trước commit. `.gitignore` loại data, artifact Parquet/model, config.local.json và .env. Không đưa raw Kaggle, snapshot customer-level hoặc model pickle lên repo công khai; truy cập và sử dụng dữ liệu theo điều khoản cuộc thi.

Repo không chứa khóa truy cập, dữ liệu khách hàng thật hoặc bản PDF sách. Chưa thêm giấy phép phần mềm vì cần chủ repo quyết định quyền cấp phép; điều khoản dữ liệu Kaggle là riêng biệt.
