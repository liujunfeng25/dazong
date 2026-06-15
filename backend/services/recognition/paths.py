"""所有路径常量集中在一处，便于 train_runner / materialize / inference / 路由共享。"""
from __future__ import annotations

from pathlib import Path

# /app 是后端容器工作目录；./backend:/app 卷挂载使此目录持久化到宿主
DATA_ROOT = Path("/app/data/smart_scale_recognition")
DATASETS_DIR = DATA_ROOT / "datasets"   # datasets/{task_id}/cat_{cid}/{sample_id}.jpg
MODELS_DIR = DATA_ROOT / "models"       # models/{task_id}/model.pt + class_mapping.json
TASKS_DIR = DATA_ROOT / "tasks"         # tasks/{task_id}/status.json


def task_dataset_dir(task_id: int) -> Path:
    return DATASETS_DIR / str(task_id)


def task_model_dir(task_id: int) -> Path:
    return MODELS_DIR / str(task_id)


def task_status_file(task_id: int) -> Path:
    return TASKS_DIR / str(task_id) / "status.json"


def task_model_file(task_id: int) -> Path:
    return task_model_dir(task_id) / "model.pt"


def task_class_mapping_file(task_id: int) -> Path:
    return task_model_dir(task_id) / "class_mapping.json"


def ensure_dirs() -> None:
    for d in (DATASETS_DIR, MODELS_DIR, TASKS_DIR):
        d.mkdir(parents=True, exist_ok=True)
