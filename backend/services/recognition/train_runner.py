"""训练子进程管理（移植自 ai-agent/app/services/train_runner.py，路径常量改用本模块的 paths）。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .paths import ensure_dirs, task_model_file, task_status_file


# task_id -> subprocess.Popen
_running: dict[int, subprocess.Popen] = {}


def start_train(task_id: int, dataset_path: Path | str, epochs: int = 10, batch_size: int = 16) -> bool:
    ensure_dirs()
    status_file = task_status_file(task_id)
    status_file.parent.mkdir(parents=True, exist_ok=True)
    output_path = task_model_file(task_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "services.recognition.train",
        "--data_dir", str(dataset_path),
        "--output", str(output_path),
        "--epochs", str(epochs),
        "--batch_size", str(batch_size),
        "--status_file", str(status_file),
    ]
    try:
        # cwd 设为 /app 以让 `python -m services.recognition.train` 解析到 backend 包
        proc = subprocess.Popen(cmd, cwd="/app", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _running[task_id] = proc
        return True
    except Exception as e:  # noqa: BLE001
        status_file.write_text(
            json.dumps({"status": "error", "message": f"启动失败: {e}"}, ensure_ascii=False),
            encoding="utf-8",
        )
        return False


def get_status(task_id: int) -> dict:
    status_file = task_status_file(task_id)
    if not status_file.exists():
        proc = _running.get(task_id)
        if proc and proc.poll() is None:
            return {"status": "starting", "message": "训练启动中…"}
        if proc and proc.poll() is not None:
            _running.pop(task_id, None)
        return {"status": "idle", "message": "未开始"}
    try:
        return json.loads(status_file.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"status": "idle", "message": "未知"}


def cancel_task(task_id: int) -> bool:
    proc = _running.get(task_id)
    if proc and proc.poll() is None:
        proc.terminate()
        _running.pop(task_id, None)
        return True
    return False


def is_running(task_id: Optional[int] = None) -> bool:
    if task_id is None:
        return any(p.poll() is None for p in _running.values())
    proc = _running.get(task_id)
    return proc is not None and proc.poll() is None
