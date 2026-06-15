"""把某次训练任务涉及的所有 Sample 图从 MinIO 下载到本地 ImageFolder 目录。

目录布局（与 train.py 的 ImageFolder 约定一致）：
    /app/data/smart_scale_recognition/datasets/{task_id}/cat_{category_id}/{sample_id}.{ext}

下载走 HTTP（sample.image_url 是公开/匿名可读的 MinIO URL），出错样本跳过、不阻塞整批。
返回每个类目实际落盘的样本数，调用方据此决定是否丢弃样本不足的类目。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import SmartScaleRecognitionSample

from .paths import task_dataset_dir
from .roi import download_image_bytes


def _ext_from_url(url: str) -> str:
    base = url.split("?", 1)[0]
    suffix = Path(base).suffix.lower()
    if suffix in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        return suffix
    return ".jpg"


async def materialize_task(db: AsyncSession, task_id: int, category_ids: Iterable[int]) -> dict[int, int]:
    """把指定类目下所有未删除的 Sample 下载到 datasets/{task_id}/cat_{cid}/。"""
    root = task_dataset_dir(task_id)
    root.mkdir(parents=True, exist_ok=True)

    counts: dict[int, int] = {}
    sem = asyncio.Semaphore(8)

    for cid in category_ids:
        cat_dir = root / f"cat_{int(cid)}"
        cat_dir.mkdir(parents=True, exist_ok=True)
        samples = (
            await db.scalars(
                select(SmartScaleRecognitionSample).where(
                    SmartScaleRecognitionSample.category_id == int(cid),
                    SmartScaleRecognitionSample.is_deleted.is_(False),
                    SmartScaleRecognitionSample.review_status == "approved",
                    SmartScaleRecognitionSample.quality_status == "passed",
                    SmartScaleRecognitionSample.cropped_image_url.is_not(None),
                )
            )
        ).all()

        async def _one(sample: SmartScaleRecognitionSample) -> bool:
            async with sem:
                source_url = sample.cropped_image_url or sample.image_url
                try:
                    content = await download_image_bytes(source_url)
                    if not content:
                        return False
                    out = cat_dir / f"{sample.id}{_ext_from_url(source_url)}"
                    out.write_bytes(content)
                    return True
                except Exception:  # noqa: BLE001
                    return False

        results = await asyncio.gather(*[_one(s) for s in samples])
        counts[int(cid)] = sum(1 for r in results if r)
    return counts
