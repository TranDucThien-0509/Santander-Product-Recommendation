FROM python:3.11-slim

WORKDIR /app

# Cài đặt build tools cần thiết cho một số thư viện C/C++ (XGBoost/LightGBM)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt dependencies Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code của pipeline và src
COPY pipeline/ ./pipeline/
COPY src/ ./src/

ENV PYTHONPATH=/app

CMD ["python", "pipeline/run_pipeline.py"]
