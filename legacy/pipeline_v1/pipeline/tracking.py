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


def _get_memory_info():
    """Thu thập thông số RAM theo 3 tầng:
    1. Process chính: VmHWM (Peak Resident Set Size) & VmRSS từ /proc/self/status.
    2. Các tiến trình con (nếu có multiprocessing): Quét /proc/[pid]/task/[pid]/children.
    3. Bộ nhớ toàn hệ thống: MemTotal và MemAvailable từ /proc/meminfo.
    """
    import os
    mem = {}

    # 1. Process chính (Linux container)
    self_status = "/proc/self/status"
    if os.path.exists(self_status):
        try:
            with open(self_status, "r") as f:
                for line in f:
                    if line.startswith("VmHWM:"):
                        mem["peak_ram_mb"] = round(int(line.split()[1]) / 1024, 1)
                    elif line.startswith("VmRSS:"):
                        mem["curr_ram_mb"] = round(int(line.split()[1]) / 1024, 1)
        except Exception:
            pass

    # 2. Quét process con nếu có
    try:
        children_file = f"/proc/{os.getpid()}/task/{os.getpid()}/children"
        if os.path.exists(children_file):
            with open(children_file, "r") as f:
                children_pids = f.read().strip().split()
            child_rss_kb = 0
            for cpid in children_pids:
                c_status = f"/proc/{cpid}/status"
                if os.path.exists(c_status):
                    with open(c_status, "r") as cf:
                        for cline in cf:
                            if cline.startswith("VmRSS:"):
                                child_rss_kb += int(cline.split()[1])
            if child_rss_kb > 0:
                mem["children_ram_mb"] = round(child_rss_kb / 1024, 1)
                mem["total_process_tree_ram_mb"] = round(mem.get("curr_ram_mb", 0) + mem["children_ram_mb"], 1)
    except Exception:
        pass

    # 3. Bộ nhớ hệ thống toàn cục từ /proc/meminfo
    meminfo_file = "/proc/meminfo"
    if os.path.exists(meminfo_file):
        try:
            sys_mem = {}
            with open(meminfo_file, "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        k = parts[0].strip()
                        v = parts[1].strip().split()[0]
                        if v.isdigit():
                            sys_mem[k] = int(v)
            if "MemTotal" in sys_mem and "MemAvailable" in sys_mem:
                total_mb = sys_mem["MemTotal"] / 1024
                avail_mb = sys_mem["MemAvailable"] / 1024
                used_mb = total_mb - avail_mb
                mem["sys_used_gb"] = round(used_mb / 1024, 2)
                mem["sys_total_gb"] = round(total_mb / 1024, 2)
                mem["sys_util_pct"] = round((used_mb / total_mb) * 100, 1)
        except Exception:
            pass

    return mem


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
    Khi thoát khối `with`, tự động ghi thời gian chạy + RAM đỉnh + toàn bộ metric đã log
    (kể cả khi có exception — kèm status "failed" và thông tin lỗi).
    """
    metrics = {}

    class _Logger:
        @staticmethod
        def log(**kwargs):
            metrics.update(kwargs)

    start = time.time()
    print(f"[{_now_iso()}] >> BẮT ĐẦU stage '{stage_name}' | Image: {config.IMAGE_TAG}")
    try:
        yield _Logger()
    except Exception as e:
        duration = time.time() - start
        mem_after = _get_memory_info()
        record = {
            "stage": stage_name,
            "image_tag": config.IMAGE_TAG,
            "timestamp": _now_iso(),
            "duration_sec": round(duration, 2),
            "status": "failed",
            "error": str(e),
            "memory": mem_after,
            **metrics,
        }
        _append_log(record)
        print(f"[{_now_iso()}] !! LỖI stage '{stage_name}' sau {duration:.1f}s: {e}")
        raise
    else:
        duration = time.time() - start
        mem_after = _get_memory_info()
        record = {
            "stage": stage_name,
            "image_tag": config.IMAGE_TAG,
            "timestamp": _now_iso(),
            "duration_sec": round(duration, 2),
            "status": "success",
            "memory": mem_after,
            **metrics,
        }
        _append_log(record)
        mem_str = ""
        if "peak_ram_mb" in mem_after:
            mem_str += f" | RAM đỉnh: {mem_after['peak_ram_mb']} MB"
        if "sys_used_gb" in mem_after:
            mem_str += f" | Hệ thống: {mem_after['sys_used_gb']}/{mem_after['sys_total_gb']} GB ({mem_after['sys_util_pct']}%)"
        print(f"[{_now_iso()}] << XONG stage '{stage_name}' sau {duration:.1f}s{mem_str} | {metrics}")
