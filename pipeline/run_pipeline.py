"""
Chạy toàn bộ pipeline theo thứ tự. Có thể chạy từng stage riêng
(python ingest.py, python preprocess.py, ...) khi chỉ cần lặp lại 1 bước.

Chạy toàn bộ: python run_pipeline.py
"""
import time

import ingest
import preprocess
import feature_engineering
import train
import predict

STAGES = [
    ("ingest", ingest.run),
    ("preprocess", preprocess.run),
    ("feature_engineering", feature_engineering.run),
    ("train", train.run),
    ("predict", predict.run),
]


def run():
    for name, stage_fn in STAGES:
        print(f"\n{'=' * 20} STAGE: {name} {'=' * 20}")
        start = time.time()
        stage_fn()
        print(f"--- {name} xong sau {time.time() - start:.1f}s ---")


if __name__ == "__main__":
    run()
