"""全国农产品价格预测训练 — 供 AI 问答自动触发（全国 single_current 口径）。"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from services.ai_chat.national_price import _load_snapshot


def get_forecast_train_status() -> dict[str, Any]:
    from routers.zgncpjgw import _FORECAST_STATUS

    return dict(_FORECAST_STATUS)


async def snapshot_exists(db: AsyncSession, sku_key: str) -> bool:
    snap = await _load_snapshot(db, sku_key, 7)
    return bool(snap and snap.get("ensemble"))


def start_national_forecast_train(sku_key: str) -> dict[str, Any]:
    """启动后台训练（全国口径）。"""
    from routers.zgncpjgw import _FORECAST_STATUS, _train_forecast_batch

    key = (sku_key or "").strip()
    if not key:
        return {"started": False, "message": "缺少 SKU"}
    if _FORECAST_STATUS.get("running"):
        return {"started": False, "message": "已有预测训练任务在运行", **get_forecast_train_status()}
    asyncio.create_task(
        _train_forecast_batch(
            [key],
            limit=1,
            include_popular=False,
            district_limit=1,
            scope_mode="single_current",
            single_district_id=None,
        )
    )
    return {"started": True, "message": "已开始训练全国农产品价格预测", **get_forecast_train_status()}


async def iter_forecast_train_progress(
    db: AsyncSession,
    sku_key: str,
    *,
    poll_seconds: float = 1.0,
    timeout_seconds: float = 180.0,
) -> AsyncIterator[dict[str, Any]]:
    """若缺快照则启动训练并产出进度事件。"""
    key = (sku_key or "").strip()
    if not key:
        yield {"phase": "failed", "message": "缺少 SKU", "progress_pct": 0}
        return
    if await snapshot_exists(db, key):
        yield {"phase": "ready", "message": "预测快照已就绪", "progress_pct": 100}
        return

    started = start_national_forecast_train(key)
    if not started.get("started"):
        yield {
            "phase": "busy",
            "message": str(started.get("message") or "训练未启动"),
            "progress_pct": int(get_forecast_train_status().get("display_progress_pct") or 0),
        }
        if await snapshot_exists(db, key):
            yield {"phase": "ready", "message": "预测快照已就绪", "progress_pct": 100}
        return

    elapsed = 0.0
    while elapsed < timeout_seconds:
        st = get_forecast_train_status()
        pct = int(st.get("display_progress_pct") or st.get("progress_pct") or 0)
        yield {
            "phase": str(st.get("phase") or "running"),
            "phase_label": str(st.get("phase_label") or "训练中"),
            "message": str(st.get("message") or st.get("phase_label") or "训练中…"),
            "progress_pct": pct,
            "eta_text": str(st.get("eta_text") or ""),
            "running": bool(st.get("running")),
        }
        if st.get("finished") or (not st.get("running") and st.get("status") in ("done", "idle", "failed")):
            break
        if await snapshot_exists(db, key):
            yield {"phase": "ready", "message": "预测快照已就绪", "progress_pct": 100}
            return
        await asyncio.sleep(poll_seconds)
        elapsed += poll_seconds

    if await snapshot_exists(db, key):
        yield {"phase": "ready", "message": "预测快照已就绪", "progress_pct": 100}
    else:
        st = get_forecast_train_status()
        yield {
            "phase": "timeout",
            "message": str(st.get("message") or "训练超时，请稍后在数据挖掘中心查看"),
            "progress_pct": int(st.get("display_progress_pct") or 0),
        }


async def ensure_forecast_snapshot(db: AsyncSession, sku_key: str) -> bool:
    """阻塞等待全国预测快照就绪。"""
    async for ev in iter_forecast_train_progress(db, sku_key):
        if ev.get("phase") in ("ready",):
            return True
    return await snapshot_exists(db, sku_key)
