# Notebook nghiên cứu và notebook finalization

00–14 là source nghiên cứu đã nhận, xóa toàn bộ output để đăng GitHub. Một số source chứa nhiều phiên bản phương pháp và ghi chú cũ; quyết định cuối nằm ở docs/01_decisions.md. Không mặc định mọi kết luận Markdown nguồn đều đã được kiểm chứng.

15 là entrypoint wrap mới, dùng các Parquet đã chạy trên Kaggle. Cài dependencies từ pyproject.toml và sửa đường dẫn trước khi chạy.

Để tái trích benchmark từ bản gốc có outputs:

```bash
python -m pip install -e '.[evidence]'
python scripts/extract_evidence.py --source-dir /path/to/original-executed-notebooks
python scripts/render_benchmarks.py
santander-wrap cards-evidence --repo .
```

Extractor giữ tên bản gốc theo source_manifest. Nó cập nhật các bản notebook nguồn đã strip và aggregate evidence; không chạy model. Nếu bạn có phiên bản notebook mới, kiểm tra lại cell/output indexes trước khi dùng.
