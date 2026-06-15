from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import DeliveryWarehouse, DeliveryWarehouseElitechBinding
from services.elitech_client import ElitechApiError, ElitechClient
from services.elitech_meta import normalize_realtime_payload


async def load_warehouse_or_404(
    db: AsyncSession,
    warehouse_id: int,
    *,
    delivery_id: Optional[int] = None,
) -> DeliveryWarehouse:
    stmt = select(DeliveryWarehouse).where(DeliveryWarehouse.id == int(warehouse_id))
    if delivery_id is not None:
        stmt = stmt.where(DeliveryWarehouse.delivery_id == int(delivery_id))
    row = await db.scalar(stmt)
    if not row:
        raise HTTPException(404, "仓库不存在")
    return row


def elitech_client_or_503() -> ElitechClient:
    client = ElitechClient()
    if not client.configured():
        raise HTTPException(
            503,
            "精创冷云未配置完整，请在环境变量中设置 ELITECH_CLIENT_ID、ELITECH_KEY_SECRET、"
            "ELITECH_USERNAME、ELITECH_PASSWORD（精创开放平台 API 账号，非网页登录手机号）",
        )
    return client


async def elitech_api_call(coro_factory):
    try:
        return await coro_factory()
    except ElitechApiError as e:
        msg = str(e) or "精创接口调用失败"
        if str(e.code) == "5110":
            msg = "精创接口调用过于频繁，请 10 秒后再试"
        raise HTTPException(502, msg) from e
    except ValueError as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"精创接口请求失败: {e}") from e


def binding_dict(
    row: DeliveryWarehouseElitechBinding,
    *,
    warehouse_name: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "warehouse_id": int(row.warehouse_id),
        "elitech_sn": row.elitech_sn,
        "device_name": row.device_name or "",
        "warehouse_name": warehouse_name or "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


async def load_binding_for_warehouse(
    db: AsyncSession,
    *,
    delivery_id: int,
    warehouse_id: int,
) -> Optional[DeliveryWarehouseElitechBinding]:
    return await db.scalar(
        select(DeliveryWarehouseElitechBinding).where(
            DeliveryWarehouseElitechBinding.delivery_id == delivery_id,
            DeliveryWarehouseElitechBinding.warehouse_id == warehouse_id,
        )
    )


async def load_binding_by_sn(
    db: AsyncSession,
    *,
    delivery_id: int,
    sn: str,
) -> Optional[DeliveryWarehouseElitechBinding]:
    return await db.scalar(
        select(DeliveryWarehouseElitechBinding).where(
            DeliveryWarehouseElitechBinding.delivery_id == delivery_id,
            DeliveryWarehouseElitechBinding.elitech_sn == sn.strip(),
        )
    )


async def occupancy_map_for_delivery(
    db: AsyncSession,
    delivery_id: int,
) -> dict[str, dict[str, Any]]:
    rows = (
        await db.execute(
            select(DeliveryWarehouseElitechBinding, DeliveryWarehouse.name)
            .join(
                DeliveryWarehouse,
                DeliveryWarehouse.id == DeliveryWarehouseElitechBinding.warehouse_id,
            )
            .where(DeliveryWarehouseElitechBinding.delivery_id == delivery_id)
        )
    ).all()
    out: dict[str, dict[str, Any]] = {}
    for binding, wh_name in rows:
        out[str(binding.elitech_sn)] = {
            "bound_warehouse_id": int(binding.warehouse_id),
            "bound_warehouse_name": wh_name or "",
        }
    return out


def elitech_realtime_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "elitech_temperature": str(item.get("temperature") or ""),
        "elitech_humidity": str(item.get("humidity") or ""),
        "elitech_online": int(item.get("status", 1)) == 0,
    }


def elitech_realtime_fields_empty() -> dict[str, Any]:
    return {
        "elitech_temperature": "",
        "elitech_humidity": "",
        "elitech_online": None,
    }


def elitech_warehouse_public_fields(
    binding: Optional[DeliveryWarehouseElitechBinding],
    rt: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """仓库列表/车队监控等只读展示用字段。"""
    if not binding or not str(binding.elitech_sn or "").strip():
        empty = elitech_realtime_fields_empty()
        return {
            "elitech_bound": False,
            "elitech_sn": "",
            "elitech_device_name": "",
            **empty,
        }
    rt = rt or elitech_realtime_fields_empty()
    return {
        "elitech_bound": True,
        "elitech_sn": str(binding.elitech_sn),
        "elitech_device_name": str(binding.device_name or ""),
        "elitech_temperature": str(rt.get("elitech_temperature") or ""),
        "elitech_humidity": str(rt.get("elitech_humidity") or ""),
        "elitech_online": rt.get("elitech_online"),
    }


async def elitech_realtime_map_for_sns(sns: list[str]) -> dict[str, dict[str, Any]]:
    """按设备 SN 拉取实时温湿度（走 client 缓存，适合列表展示）。"""
    ordered = list(dict.fromkeys(s.strip() for s in sns if (s or "").strip()))
    if not ordered:
        return {}
    client = ElitechClient()
    if not client.configured():
        return {sn: elitech_realtime_fields_empty() for sn in ordered}
    out: dict[str, dict[str, Any]] = {}
    for sn in ordered:
        try:
            payload = await elitech_api_call(lambda s=sn: client.get_realtime(s))
            item = normalize_realtime_payload(payload, device_guid=sn)
            out[sn] = elitech_realtime_fields(item)
        except HTTPException:
            out[sn] = elitech_realtime_fields_empty()
    return out


async def require_bound_sn(
    db: AsyncSession,
    *,
    delivery_id: int,
    warehouse_id: int,
) -> DeliveryWarehouseElitechBinding:
    await load_warehouse_or_404(db, warehouse_id, delivery_id=delivery_id)
    binding = await load_binding_for_warehouse(db, delivery_id=delivery_id, warehouse_id=warehouse_id)
    if not binding:
        raise HTTPException(400, "该仓库未绑定温湿度仪")
    return binding

