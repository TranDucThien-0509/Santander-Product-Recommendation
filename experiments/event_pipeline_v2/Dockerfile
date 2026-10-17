FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pipeline ./pipeline
COPY configs/default.json ./configs/default.json
CMD ["python", "-m", "pipeline.run_pipeline", "--config", "configs/default.json"]
