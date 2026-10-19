FROM python:3.11-slim

WORKDIR /app/legacy/pipeline_v1

# Cài đặt build tools cần thiết cho một số thư viện C/C++ (XGBoost/LightGBM)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt dependencies Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code của pipeline v1 (build context: legacy/pipeline_v1)
COPY pipeline/ ./pipeline/

ENV PYTHONPATH=/app/legacy/pipeline_v1

CMD ["python", "pipeline/run_pipeline.py"]
