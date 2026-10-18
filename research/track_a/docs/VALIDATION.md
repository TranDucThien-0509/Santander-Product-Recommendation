# Kiểm tra bộ wrap v1

## Đã thực hiện tại môi trường tạo repo

- Cài editable package từ pyproject.toml thành công (Python 3.12).
- CLI help chạy được; module Python parse được.
- 8 unittest integration đã pass: full build, owned product, wrong month, duplicate IDs, CLV selection mismatch, persona rule mismatch, future history, duplicate recommendations.
- Full build dùng 10 khách mô phỏng: đủ P1–P6, history-short, incomplete, At-risk và Churned. Đọc raw CSV và Parquet nguồn, ghi master/long recommendations, coverage và cards. Kiểm tra missing không thành 0, tuổi trẻ em giữ nguyên, nhãn F3 nguồn khác tag F4 cuối.
- 16 notebook trong repo đã strip mọi output/execution_count. Notebook finalization 15 có code syntax hợp lệ.
- 6 evidence cards được tạo từ aggregate notebook outputs. N profile/CLV theo persona được kiểm tra khớp; mean CLV có weighting theo n, không gộp median.
- Markdown relative links được kiểm tra tồn tại. Không đính raw dataset, customer-level parquet, pickle, credential hoặc PDF sách.

## Chưa thực hiện

- Chưa chạy lại training hoặc tái tính metric từ dữ liệu Santander gốc.
- Chưa chạy build trên toàn ~956K khách vì thiếu Parquet nguồn trong phiên này.
- Chưa xác minh lại toàn bộ notebook 00–14 bằng Run All trong môi trường mới. Chúng là bản nghiên cứu nguồn, xem limitations.md.
- Chưa push GitHub, cấu hình cloud, hoặc đo conversion/lợi nhuận thực.

## Lệnh kiểm tra lại

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m santander_wrap.cli --help
```

Sau khi chạy trên Kaggle, đối chiếu build_manifest: May2016 bản nguồn hiện có kỳ vọng known=956645, observed=931453, persona_assigned=917043, CLV predicted=931453. Các số này là đối chiếu với output cũ, không phải giá trị hardcode để sửa dữ liệu. Nếu lệch phải kiểm tra phiên bản input.
