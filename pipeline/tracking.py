"""
Tracking nhẹ cho pipeline — không cần MLflow/W&B, không cần server.
Mỗi stage ghi 1 dòng JSON vào artifacts/pipeline_run_log.jsonl kèm
timestamp, thời gian chạy, và các số liệu (shape, memory, metric...)
mà chính stage đó truyền vào.

Dùng: xem README phần "Theo dõi pipeline" để biết cách đọc log.
"""
import json
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import numpy as np

import config


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _sanitize(obj):
    """Chuyển numpy scalar/dict-key thành kiểu Python thuần trước khi json.dumps —
    numpy.int64 làm dict key sẽ làm json.dumps lỗi ngay cả khi có default=str,
    vì hook default chỉ áp dụng cho value, không áp dụng cho key."""
    if isinstance(obj, dict):
        return {_sanitize(k) if not isinstance(k, str) else k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    return obj


def _append_log(record: dict):
    with open(config.PIPELINE_LOG_JSONL, "a") as f:
        f.write(json.dumps(_sanitize(record), default=str) + "\n")


@contextmanager
def track_stage(stage_name: str):
    """
    Bọc quanh phần chạy chính của 1 stage. Ví dụ:

        with track_stage("preprocess") as t:
            ... code xử lý ...
            t.log(rows_before=100, rows_after=95)

    `t.log(...)` có thể gọi nhiều lần trong stage, các key sẽ được gộp lại.
    Khi thoát khối `with`, tự động ghi thời gian chạy + toàn bộ metric đã log
    (kể cả khi có exception — kèm status "failed" và thông tin lỗi).
    """
    metrics = {}

    class _Logger:
        @staticmethod
        def log(**kwargs):
            metrics.update(kwargs)

    start = time.time()
    print(f"[{_now_iso()}] >> BẮT ĐẦU stage '{stage_name}'")
    try:
        yield _Logger()
    except Exception as e:
        duration = time.time() - start
        record = {
            "stage": stage_name,
            "timestamp": _now_iso(),
            "duration_sec": round(duration, 2),
            "status": "failed",
            "error": str(e),
            **metrics,
        }
        _append_log(record)
        print(f"[{_now_iso()}] !! LỖI stage '{stage_name}' sau {duration:.1f}s: {e}")
        raise
    else:
        duration = time.time() - start
        record = {
            "stage": stage_name,
            "timestamp": _now_iso(),
            "duration_sec": round(duration, 2),
            "status": "success",
            **metrics,
        }
        _append_log(record)
        print(f"[{_now_iso()}] << XONG stage '{stage_name}' sau {duration:.1f}s | {metrics}")
