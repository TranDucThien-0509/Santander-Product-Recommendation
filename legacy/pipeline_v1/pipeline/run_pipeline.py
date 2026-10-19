"""
Chạy toàn bộ pipeline theo thứ tự. Có thể chạy từng stage riêng
(python ingest.py, python preprocess.py, ...) khi chỉ cần lặp lại 1 bước.

Chạy toàn bộ: python run_pipeline.py
"""
import os
import time

import ingest
import preprocess
import feature_engineering
import train
import predict
import evaluate

ALL_STAGES = [
    ("ingest", ingest.run),
    ("preprocess", preprocess.run),
    ("feature_engineering", feature_engineering.run),
    ("train", train.run),
    ("predict", predict.run),
    ("evaluate", evaluate.run),
]


def run():
    # Cho phép chọn các stage cần chạy qua biến môi trường SANTANDER_STAGES
    # vd: export SANTANDER_STAGES="feature_engineering,train,predict,evaluate"
    stages_env = os.environ.get("SANTANDER_STAGES", "").strip()
    if stages_env:
        selected_names = [s.strip().lower() for s in stages_env.split(",") if s.strip()]
        stages_to_run = [(name, fn) for name, fn in ALL_STAGES if name.lower() in selected_names]
        if not stages_to_run:
            print(f"!! Cảnh báo: SANTANDER_STAGES='{stages_env}' không khớp stage nào. Các stage hợp lệ: {[n for n, _ in ALL_STAGES]}")
            return
    else:
        stages_to_run = ALL_STAGES

    for name, stage_fn in stages_to_run:
        print(f"\n{'=' * 20} STAGE: {name} {'=' * 20}")
        start = time.time()
        stage_fn()
        print(f"--- {name} xong sau {time.time() - start:.1f}s ---")


if __name__ == "__main__":
    run()
