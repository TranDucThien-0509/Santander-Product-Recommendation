FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pipeline ./pipeline
COPY configs ./configs
CMD ["python", "-m", "pipeline.run_pipeline", "--config", "configs/default.json"]
