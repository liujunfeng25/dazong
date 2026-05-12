import asyncio
import math
import random
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
from uuid import uuid4
from typing import Any, Literal, Optional
from collections import defaultdict

import bcrypt
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from dependencies import require_role
from models import (
    Category,
    Contract,
    DeliveryDevice,
    DeliveryGeofence,
    DeliveryVehicle,
    DeliveryVehicleDeviceBinding,
    Order,
    OrderItemAllocation,
    OrderReview,
    OrderItemStatusLog,
    Product,
    SupplierProductQuote,
    Tender,
    Ticket,
    User,
)
from services.planning_display_notes import ESTIMATED_ON_TIME_RATE_NOTE_CN
from services.amap_direction_driving import DrivingLegResult, fetch_driving_leg, merge_leg_polylines
from services.no_go_avoidpolygons import (
    build_avoidpolygons_param,
    no_go_penalty_for_leg,
    rings_for_leg_avoid_strict,
    rings_from_no_go_geofences,
)
from services.amap_geocode import geocode_address, regeocode_lnglat, search_address_tips
from services.audit_service import write_audit_log
from services.beidou_client import BeidouClient
from services.beijing_vehicle_plate_limit import (
    build_vehicle_limit_today,
    classify_vehicle_limit,
    departure_may_overlap_beijing_tail_restriction,
    ROUTE_PLAN_BLOCKED_LIMIT_STATUSES,
)
from services.delivery_slot import parse_delivery_slot_hours
from services.driving_restriction import fetch_beijing_driving_restriction, fetch_beijing_weather_now
from services.geofence_geometry import circle_polygon_geojson, validate_polygon_geojson
from services.ys7_client import YS7Client
from services.notification_service import list_operation_user_ids, push_notification
from services.ticket_service import complaint_ticket_public_dict, submit_delivery_complaint_response

router = APIRouter(prefix="/delivery", tags=["delivery"])
SMART_SPLIT_ALLOWED_ORDER_STATUSES = {"下单"}


class ComplaintRespondIn(BaseModel):
    response: str = Field(..., min_length=1)


class SmartSplitIn(BaseModel):
    order_ids: list[int]
    mode: str = Field(default="normal", pattern="^(eco|normal|sport)$")
    quota_window: str = Field(default="week", pattern="^(week|month|quarter)$")
    allow_split: Optional[bool] = None


class SmartSplitAllocationIn(BaseModel):
    order_id: int
    line_no: int
    product_id: int
    quantity: float
    unit_price: float
    supplier_id: int


class SmartSplitCommitIn(BaseModel):
    allocations: list[SmartSplitAllocationIn]
    mode: str = Field(default="normal", pattern="^(eco|normal|sport)$")
    quota_window: str = Field(default="week", pattern="^(week|month|quarter)$")
    allow_split: Optional[bool] = None


class RoutePlanIn(BaseModel):
    driver_id: int
    order_ids: list[int]
    # 计划发车为北京时间（Asia/Shanghai）
    planning_date: Optional[date] = None
    departure_time: str = Field(default="06:00", max_length=8, description="HH:mm 如 06:00，未在按车映射中出现的车辆用此值")
    departure_time_by_vehicle_no: Optional[dict[str, str]] = Field(
        default=None,
        description="车牌号 -> HH:mm（北京时间），与 departure_time 同日；未列出的车辆沿用 departure_time",
    )
    service_minutes_default: int = Field(default=30, ge=5, le=240)
    service_minutes_by_order: Optional[dict[str, int]] = Field(
        default=None, description="订单 id -> 服务分钟，键为字符串数字"
    )
    user_disabled_vehicle_nos: Optional[list[str]] = Field(
        default=None,
        description="用户手动禁用的车牌号列表：须严格排除，不得参与本次智能排线计算",
    )
    geofence_policy: Literal["normal", "strict"] = Field(
        default="normal",
        description="禁行围栏：normal 与现网一致（避让失败可降级无避让）；strict 禁止无避让重试且按路段排除「终点在围栏内」的环，失败则整单报错",
    )


class SupplierAccountIn(BaseModel):
    username: str
    password: str = "demo123"
    company_name: str
    contact_phone: str = ""
    address: str = ""
    status: str = "active"


class VehicleIn(BaseModel):
    vehicle_no: str
    vehicle_model: str = ""
    driver_name: str = ""
    capacity_weight_kg: Optional[float] = None
    capacity_volume_m3: Optional[float] = None
    status: str = "active"


class DeviceIn(BaseModel):
    device_type: str = Field(pattern="^(beidou|camera)$")
    vendor: str = Field(pattern="^(beidou|ys7)$")
    device_code: str
    device_name: str = ""
    channel_no: int = 0
    status: str = "active"
    raw_payload_json: Optional[dict[str, Any]] = None


class VehicleBindingIn(BaseModel):
    device_id: int


@router.get("/home")
async def delivery_home(_=Depends(require_role("delivery"))):
    return {"message": "ok", "module": "delivery"}


def _audit_meta(request: Request) -> dict:
    return {
        "trace_id": getattr(request.state, "trace_id", ""),
        "source_ip": request.client.host if request.client else "",
    }


def _normalize_supplier_payload(payload: SupplierAccountIn):
    payload.username = (payload.username or "").strip()
    payload.company_name = (payload.company_name or "").strip()
    payload.contact_phone = (payload.contact_phone or "").strip()
    payload.address = (payload.address or "").strip()


async def _delivery_suppliers(db: AsyncSession, delivery_id: int) -> list[User]:
    return (
        await db.scalars(
            select(User).where(
                User.role == "supplier",
                User.supplier_delivery_id == delivery_id,
                User.status == "active",
            )
        )
    ).all()


def _mode_config(mode: str, allow_split: Optional[bool]) -> dict[str, Any]:
    mode_key = (mode or "normal").strip().lower()
    defaults = {
        "eco": {
            "label": "成本优先",
            "max_suppliers_per_order": 2,
            "split_quantity_threshold": 2.0,
            "weights": {"price": 0.55, "quota": 0.10, "distance": 0.20, "rating": 0.10, "stability": 0.05},
            "allow_split_default": False,
        },
        "normal": {
            "label": "均衡协同",
            "max_suppliers_per_order": 2,
            "split_quantity_threshold": 2.0,
            "weights": {"price": 0.35, "quota": 0.20, "distance": 0.20, "rating": 0.15, "stability": 0.10},
            "allow_split_default": False,
        },
        "sport": {
            "label": "多源保障",
            "max_suppliers_per_order": 3,
            "split_quantity_threshold": 2.0,
            "weights": {"price": 0.25, "quota": 0.35, "distance": 0.15, "rating": 0.15, "stability": 0.10},
            "allow_split_default": True,
        },
    }
    conf = defaults.get(mode_key, defaults["normal"]).copy()
    conf["mode"] = mode_key if mode_key in defaults else "normal"
    conf["allow_split"] = conf["allow_split_default"] if allow_split is None else bool(allow_split)
    return conf


def _item_quantity(item: dict[str, Any]) -> float:
    try:
        return float(item.get("quantity") or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _item_unit_price(item: dict[str, Any]) -> float:
    try:
        return float(item.get("unit_price") or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _supplier_quota_reason(
    supplier_id: int,
    quote_price: float,
    quota_usage: dict[int, float],
    score_detail: dict[str, float],
    distance_km: Optional[float],
    supplier_rating: Optional[float],
) -> str:
    usage_ratio = float(quota_usage.get(supplier_id, 0.0)) * 100
    max_factor = max(score_detail.items(), key=lambda x: x[1])[0] if score_detail else "price"
    distance_text = f"{distance_km:.1f}km" if isinstance(distance_km, (int, float)) else "未知"
    rating_text = f"{supplier_rating:.1f}分" if isinstance(supplier_rating, (int, float)) else "暂无"
    if max_factor == "quota":
        return f"配额均衡优先：当前份额约{usage_ratio:.1f}%，距离{distance_text}，评分{rating_text}"
    if max_factor == "distance":
        return f"距离优先：预计{distance_text}，报价¥{quote_price:.2f}，评分{rating_text}"
    if max_factor == "rating":
        return f"服务评分优先：评分{rating_text}，份额约{usage_ratio:.1f}%，距离{distance_text}"
    return f"成本优先：报价¥{quote_price:.2f}，份额约{usage_ratio:.1f}%，距离{distance_text}"


def _haversine_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


def _contract_rate_map_and_fallback(contract: Contract) -> tuple[dict[int, float], float]:
    rate_map: dict[int, float] = {}
    for item in contract.category_rates_json or []:
        if isinstance(item, dict) and item.get("category_id") is not None:
            rate_map[int(item["category_id"])] = float(item.get("float_rate", 0))
    return rate_map, float(contract.price_float_rate or 0)


def _floating_price(reference_price: float, category1_id: Optional[int], rate_map: dict[int, float], fallback_rate: float) -> Optional[float]:
    if category1_id is None:
        return None
    rate = rate_map.get(int(category1_id), fallback_rate)
    return float(round(Decimal(str(reference_price)) * (Decimal("1") + Decimal(str(rate))), 2))


def _serialize_vehicle(row: DeliveryVehicle) -> dict[str, Any]:
    return {
        "id": row.id,
        "vehicle_no": row.vehicle_no,
        "vehicle_model": row.vehicle_model or "",
        "driver_name": row.driver_name,
        "capacity_weight_kg": float(row.capacity_weight_kg) if row.capacity_weight_kg is not None else None,
        "capacity_volume_m3": float(row.capacity_volume_m3) if row.capacity_volume_m3 is not None else None,
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _serialize_device(row: DeliveryDevice) -> dict[str, Any]:
    raw = row.raw_payload_json or {}
    online_status = _device_online_status(raw, row.vendor)
    lng, lat = _device_location(raw, row.vendor)
    return {
        "id": row.id,
        "device_type": row.device_type,
        "vendor": row.vendor,
        "device_code": row.device_code,
        "device_name": row.device_name,
        "channel_no": row.channel_no,
        "status": row.status,
        "online_status": online_status,
        "lng": lng,
        "lat": lat,
        "raw_payload_json": row.raw_payload_json,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _to_float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:  # noqa: BLE001
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _device_location(raw_payload: dict[str, Any], vendor: str) -> tuple[Optional[float], Optional[float]]:
    raw = _as_dict(raw_payload)
    if vendor == "beidou":
        lng = _to_float_or_none(raw.get("jingdu")) or _to_float_or_none(raw.get("ljingdu"))
        lat = _to_float_or_none(raw.get("weidu")) or _to_float_or_none(raw.get("lweidu"))
        return lng, lat

    # 萤石：优先 camera/device 里可能存在的经纬度字段
    camera = _as_dict(raw.get("camera"))
    device = _as_dict(raw.get("device"))
    lng = (
        _to_float_or_none(camera.get("longitude"))
        or _to_float_or_none(device.get("longitude"))
        or _to_float_or_none(camera.get("lng"))
        or _to_float_or_none(device.get("lng"))
    )
    lat = (
        _to_float_or_none(camera.get("latitude"))
        or _to_float_or_none(device.get("latitude"))
        or _to_float_or_none(camera.get("lat"))
        or _to_float_or_none(device.get("lat"))
    )
    return lng, lat


def _device_online_status(raw_payload: dict[str, Any], vendor: str) -> str:
    raw = _as_dict(raw_payload)
    # 优先读取显式在线字段
    explicit_keys = ("online", "is_online", "isOnline", "onlineStatus", "status")
    if vendor == "ys7":
        c = _as_dict(raw.get("camera"))
        d = _as_dict(raw.get("device"))
        for src in (c, d, raw):
            for k in explicit_keys:
                val = src.get(k)
                if val is None:
                    continue
                text = str(val).strip().lower()
                if text in {"1", "true", "online", "on"}:
                    return "online"
                if text in {"0", "false", "offline", "off"}:
                    return "offline"
        return "offline"

    # 北斗：优先根据最近心跳判断在线（毫秒时间戳）
    now_ms = int(datetime.utcnow().timestamp() * 1000)
    for k in ("heart_time", "server_time", "datetime", "sys_time"):
        ts = _to_float_or_none(raw.get(k))
        if ts is None or ts <= 0:
            continue
        # 心跳 10 分钟内视为在线
        if now_ms - int(ts) <= 10 * 60 * 1000:
            return "online"
        return "offline"

    status_text = str(raw.get("status") or "").strip().lower()
    if status_text in {"1", "online", "true"}:
        return "online"
    return "offline"


async def _attach_device_list_addresses(items: list[dict[str, Any]]) -> None:
    """按坐标去重并发逆地理编码，写入 location_address（无 Key 或失败则为 None）。"""
    coord_to_items: dict[tuple[float, float], list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        lng = item.get("lng")
        lat = item.get("lat")
        if lng is None or lat is None:
            item["location_address"] = None
            continue
        try:
            key = (round(float(lng), 5), round(float(lat), 5))
        except (TypeError, ValueError):
            item["location_address"] = None
            continue
        coord_to_items[key].append(item)

    if not coord_to_items:
        return

    async def _one(key: tuple[float, float]) -> tuple[tuple[float, float], Optional[str]]:
        addr = await regeocode_lnglat(key[0], key[1])
        return key, addr

    pairs = await asyncio.gather(*[_one(k) for k in coord_to_items.keys()])
    for key, addr in pairs:
        for it in coord_to_items.get(key, []):
            it["location_address"] = addr


async def _load_vehicle_or_404(db: AsyncSession, delivery_id: int, vehicle_id: int) -> DeliveryVehicle:
    vehicle = await db.scalar(
        select(DeliveryVehicle).where(
            DeliveryVehicle.id == vehicle_id,
            DeliveryVehicle.delivery_id == delivery_id,
        )
    )
    if not vehicle:
        raise HTTPException(404, "车辆不存在")
    return vehicle


async def _load_device_or_404(db: AsyncSession, delivery_id: int, device_id: int) -> DeliveryDevice:
    device = await db.scalar(
        select(DeliveryDevice).where(
            DeliveryDevice.id == device_id,
            DeliveryDevice.delivery_id == delivery_id,
        )
    )
    if not device:
        raise HTTPException(404, "设备不存在")
    return device


async def _validate_binding_limits(db: AsyncSession, vehicle_id: int, device: DeliveryDevice) -> None:
    count_stmt = (
        select(func.count(DeliveryVehicleDeviceBinding.id))
        .join(DeliveryDevice, DeliveryDevice.id == DeliveryVehicleDeviceBinding.device_id)
        .where(DeliveryVehicleDeviceBinding.vehicle_id == vehicle_id)
    )
    if device.vendor == "beidou":
        count_stmt = count_stmt.where(DeliveryDevice.vendor == "beidou")
        bound_count = int(await db.scalar(count_stmt) or 0)
        if bound_count >= 1:
            raise HTTPException(400, "每辆车最多绑定1个北斗设备")
    elif device.vendor == "ys7":
        count_stmt = count_stmt.where(DeliveryDevice.vendor == "ys7", DeliveryDevice.device_type == "camera")
        bound_count = int(await db.scalar(count_stmt) or 0)
        if bound_count >= 3:
            raise HTTPException(400, "每辆车最多绑定3个萤石摄像头")


def _normalize_vehicle_payload(payload: VehicleIn) -> None:
    payload.vehicle_no = (payload.vehicle_no or "").strip()
    payload.vehicle_model = (payload.vehicle_model or "").strip()
    payload.driver_name = (payload.driver_name or "").strip()
    payload.status = (payload.status or "active").strip() or "active"
    if not payload.vehicle_no:
        raise HTTPException(400, "车牌号不能为空")


def _normalize_device_payload(payload: DeviceIn) -> None:
    payload.device_type = (payload.device_type or "").strip().lower()
    payload.vendor = (payload.vendor or "").strip().lower()
    payload.device_code = (payload.device_code or "").strip()
    payload.device_name = (payload.device_name or "").strip()
    payload.status = (payload.status or "active").strip() or "active"
    if not payload.device_code:
        raise HTTPException(400, "设备编码不能为空")
    if payload.vendor == "beidou" and payload.device_type != "beidou":
        raise HTTPException(400, "北斗设备类型必须是 beidou")
    if payload.vendor == "ys7" and payload.device_type != "camera":
        raise HTTPException(400, "萤石设备类型必须是 camera")
    if payload.channel_no < 0:
        raise HTTPException(400, "摄像头通道号非法")


@router.get("/vehicles")
async def list_delivery_vehicles(
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.scalars(
            select(DeliveryVehicle)
            .where(DeliveryVehicle.delivery_id == user.id)
            .order_by(DeliveryVehicle.id.desc())
        )
    ).all()
    return [_serialize_vehicle(r) for r in rows]


@router.get("/vehicles/restriction/beijing")
async def beijing_vehicle_restriction_today(
    user=Depends(require_role("delivery")),
    plan_date: Optional[date] = Query(
        None,
        description="限行规则参照的自然日（YYYY-MM-DD）；不传则按今日（北京时间）",
    ),
):
    _ = user
    try:
        return await fetch_beijing_driving_restriction(target_date=plan_date)
    except Exception as exc:  # noqa: BLE001
        sh = ZoneInfo("Asia/Shanghai")
        fallback = (plan_date or datetime.now(sh).date()).isoformat()
        return {
            "source": "seniverse",
            "available": False,
            "message": f"实时限号接口请求失败：{exc}",
            "city": "北京",
            "date": fallback,
            "digits": [],
            "raw_text": "",
        }


@router.get("/weather/beijing")
async def beijing_weather_today(user=Depends(require_role("delivery"))):
    _ = user
    try:
        return await fetch_beijing_weather_now()
    except Exception as exc:  # noqa: BLE001
        return {
            "source": "seniverse",
            "available": False,
            "message": f"实时天气接口请求失败：{exc}",
            "city": "北京",
            "text": "",
            "temperature": "",
            "last_update": "",
        }


@router.post("/vehicles")
async def create_delivery_vehicle(
    payload: VehicleIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    _normalize_vehicle_payload(payload)
    exists = await db.scalar(
        select(DeliveryVehicle).where(
            DeliveryVehicle.delivery_id == user.id,
            DeliveryVehicle.vehicle_no == payload.vehicle_no,
        )
    )
    if exists:
        raise HTTPException(400, "车辆已存在")
    row = DeliveryVehicle(
        delivery_id=user.id,
        vehicle_no=payload.vehicle_no,
        vehicle_model=payload.vehicle_model,
        driver_name=payload.driver_name,
        capacity_weight_kg=payload.capacity_weight_kg,
        capacity_volume_m3=payload.capacity_volume_m3,
        status=payload.status,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _serialize_vehicle(row)


@router.put("/vehicles/{vehicle_id}")
async def update_delivery_vehicle(
    vehicle_id: int,
    payload: VehicleIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    _normalize_vehicle_payload(payload)
    row = await _load_vehicle_or_404(db, user.id, vehicle_id)
    if row.vehicle_no != payload.vehicle_no:
        exists = await db.scalar(
            select(DeliveryVehicle).where(
                DeliveryVehicle.delivery_id == user.id,
                DeliveryVehicle.vehicle_no == payload.vehicle_no,
                DeliveryVehicle.id != vehicle_id,
            )
        )
        if exists:
            raise HTTPException(400, "车辆已存在")
    row.vehicle_no = payload.vehicle_no
    row.vehicle_model = payload.vehicle_model
    row.driver_name = payload.driver_name
    row.capacity_weight_kg = payload.capacity_weight_kg
    row.capacity_volume_m3 = payload.capacity_volume_m3
    row.status = payload.status
    await db.commit()
    await db.refresh(row)
    return _serialize_vehicle(row)


@router.delete("/vehicles/{vehicle_id}")
async def delete_delivery_vehicle(
    vehicle_id: int,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    row = await _load_vehicle_or_404(db, user.id, vehicle_id)
    row.status = "inactive"
    await db.commit()
    return {"message": "ok"}


@router.get("/devices")
async def list_delivery_devices(
    device_type: Optional[str] = None,
    bind_vehicle_id: Optional[int] = Query(
        default=None,
        description="当前要绑定设备的车辆 ID；传入时仅返回尚未绑定任何车辆的设备",
    ),
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(DeliveryDevice)
        .where(DeliveryDevice.delivery_id == user.id)
        .order_by(DeliveryDevice.id.desc())
    )
    if device_type:
        stmt = stmt.where(DeliveryDevice.device_type == device_type.strip().lower())
    rows = (await db.scalars(stmt)).all()
    ids = [r.id for r in rows]
    # device_id -> 绑定车辆信息（每设备只保留首条绑定）
    device_vehicle: dict[int, dict[str, Any]] = {}
    if ids:
        bind_rows = (
            await db.execute(
                select(
                    DeliveryVehicleDeviceBinding.device_id,
                    DeliveryVehicle.id,
                    DeliveryVehicle.vehicle_no,
                    DeliveryVehicle.driver_name,
                )
                .join(
                    DeliveryVehicle,
                    DeliveryVehicle.id == DeliveryVehicleDeviceBinding.vehicle_id,
                )
                .where(
                    DeliveryVehicle.delivery_id == user.id,
                    DeliveryVehicleDeviceBinding.device_id.in_(ids),
                )
            )
        ).all()
        for row in bind_rows:
            did = int(row[0])
            if did in device_vehicle:
                continue
            device_vehicle[did] = {
                "vehicle_id": int(row[1]),
                "vehicle_no": str(row[2] or "").strip(),
                "driver_name": str(row[3] or "").strip(),
            }

    out: list[dict[str, Any]] = []
    for r in rows:
        vinfo = device_vehicle.get(r.id)
        item = _serialize_device(r)
        item["bound_vehicle_id"] = vinfo["vehicle_id"] if vinfo else None
        item["bound_vehicle_no"] = vinfo["vehicle_no"] if vinfo else None
        item["bound_vehicle_driver"] = vinfo["driver_name"] if vinfo else None
        item["bound"] = bool(vinfo)
        item["location_address"] = None
        if bind_vehicle_id:
            # 绑定候选：只展示「未绑任何车」的设备（已绑本车或其它车的均不列出）
            if vinfo is not None:
                continue
            item["bound_other_vehicle_id"] = None
        else:
            item["bound_other_vehicle_id"] = vinfo["vehicle_id"] if vinfo else None
        out.append(item)

    await _attach_device_list_addresses(out)
    return out


@router.post("/devices")
async def create_delivery_device(
    payload: DeviceIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    _normalize_device_payload(payload)
    exists = await db.scalar(
        select(DeliveryDevice).where(
            DeliveryDevice.delivery_id == user.id,
            DeliveryDevice.vendor == payload.vendor,
            DeliveryDevice.device_code == payload.device_code,
            DeliveryDevice.channel_no == payload.channel_no,
        )
    )
    if exists:
        raise HTTPException(400, "设备已存在")
    row = DeliveryDevice(
        delivery_id=user.id,
        device_type=payload.device_type,
        vendor=payload.vendor,
        device_code=payload.device_code,
        device_name=payload.device_name or payload.device_code,
        channel_no=payload.channel_no,
        status=payload.status,
        raw_payload_json=payload.raw_payload_json,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _serialize_device(row)


@router.put("/devices/{device_id}")
async def update_delivery_device(
    device_id: int,
    payload: DeviceIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    _normalize_device_payload(payload)
    row = await _load_device_or_404(db, user.id, device_id)
    exists = await db.scalar(
        select(DeliveryDevice).where(
            DeliveryDevice.delivery_id == user.id,
            DeliveryDevice.vendor == payload.vendor,
            DeliveryDevice.device_code == payload.device_code,
            DeliveryDevice.channel_no == payload.channel_no,
            DeliveryDevice.id != device_id,
        )
    )
    if exists:
        raise HTTPException(400, "设备已存在")
    row.device_type = payload.device_type
    row.vendor = payload.vendor
    row.device_code = payload.device_code
    row.device_name = payload.device_name or payload.device_code
    row.channel_no = payload.channel_no
    row.status = payload.status
    row.raw_payload_json = payload.raw_payload_json
    await db.commit()
    await db.refresh(row)
    return _serialize_device(row)


@router.delete("/devices/{device_id}")
async def delete_delivery_device(
    device_id: int,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    row = await _load_device_or_404(db, user.id, device_id)
    row.status = "inactive"
    await db.execute(
        DeliveryVehicleDeviceBinding.__table__.delete().where(
            DeliveryVehicleDeviceBinding.device_id == device_id
        )
    )
    await db.commit()
    return {"message": "ok"}


@router.post("/devices/refresh/beidou")
async def refresh_beidou_devices(
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    client = BeidouClient()
    try:
        devices = await client.list_devices()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            502, "北斗设备同步失败：当前网络无法连接北斗开放平台，请稍后重试或检查服务器出网策略"
        ) from e
    upserted = 0
    for item in devices:
        row = await db.scalar(
            select(DeliveryDevice).where(
                DeliveryDevice.delivery_id == user.id,
                DeliveryDevice.vendor == "beidou",
                DeliveryDevice.device_code == item.device_code,
                DeliveryDevice.channel_no == 0,
            )
        )
        if not row:
            row = DeliveryDevice(
                delivery_id=user.id,
                device_type="beidou",
                vendor="beidou",
                device_code=item.device_code,
                device_name=item.device_name,
                channel_no=0,
                status="active",
                raw_payload_json=item.raw,
            )
            db.add(row)
        else:
            row.device_name = item.device_name
            row.status = "active"
            row.raw_payload_json = item.raw
        upserted += 1
    await db.commit()
    return {"message": "ok", "upserted": upserted}


@router.post("/devices/refresh/ys7")
async def refresh_ys7_devices(
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    client = YS7Client()
    try:
        channels = await client.list_channels()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            502, "萤石设备同步失败：当前网络无法连接萤石开放平台，请稍后重试或检查服务器出网策略"
        ) from e
    upserted = 0
    for item in channels:
        row = await db.scalar(
            select(DeliveryDevice).where(
                DeliveryDevice.delivery_id == user.id,
                DeliveryDevice.vendor == "ys7",
                DeliveryDevice.device_code == item.device_code,
                DeliveryDevice.channel_no == item.channel_no,
            )
        )
        if not row:
            row = DeliveryDevice(
                delivery_id=user.id,
                device_type="camera",
                vendor="ys7",
                device_code=item.device_code,
                device_name=item.device_name,
                channel_no=item.channel_no,
                status="active",
                raw_payload_json=item.raw,
            )
            db.add(row)
        else:
            row.device_name = item.device_name
            row.status = "active"
            row.raw_payload_json = item.raw
        upserted += 1
    await db.commit()
    return {"message": "ok", "upserted": upserted}


@router.get("/devices/{device_id}/camera-live-url")
async def get_camera_live_url(
    device_id: int,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    row = await _load_device_or_404(db, user.id, device_id)
    if row.vendor != "ys7" or row.device_type != "camera":
        raise HTTPException(400, "仅摄像头设备支持查看直播地址")

    raw = row.raw_payload_json or {}
    camera = raw.get("camera") if isinstance(raw, dict) and isinstance(raw.get("camera"), dict) else {}
    for key in ("liveAddress", "hlsHd", "hls", "rtmpHd", "rtmp", "flvHd", "flv", "url"):
        value = camera.get(key) or raw.get(key) if isinstance(raw, dict) else None
        if value:
            return {"live_url": str(value), "source": "cache"}

    client = YS7Client()
    try:
        live_url = await client.get_live_address(row.device_code, int(row.channel_no or 1))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            502, "萤石直播地址获取失败：当前网络无法连接萤石开放平台，请稍后重试或检查服务器出网策略"
        ) from e
    return {"live_url": live_url, "source": "remote"}


@router.get("/vehicles/{vehicle_id}/location")
async def get_vehicle_location(
    vehicle_id: int,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    """车辆位置：优先取绑定北斗设备的经纬度，否则取首个有坐标的绑定设备（如萤石）。"""
    vehicle = await _load_vehicle_or_404(db, user.id, vehicle_id)
    devices = (
        await db.scalars(
            select(DeliveryDevice)
            .join(
                DeliveryVehicleDeviceBinding,
                DeliveryVehicleDeviceBinding.device_id == DeliveryDevice.id,
            )
            .where(
                DeliveryVehicleDeviceBinding.vehicle_id == vehicle_id,
                DeliveryVehicleDeviceBinding.delivery_id == user.id,
            )
            .order_by(DeliveryDevice.id.asc())
        )
    ).all()
    if not devices:
        raise HTTPException(404, "未绑定设备：请先绑定北斗或摄像头后再查看位置")
    beidou_first = sorted(
        devices,
        key=lambda d: (0 if getattr(d, "vendor", "") == "beidou" else 1, d.id),
    )
    for device in beidou_first:
        raw = device.raw_payload_json or {}
        lng, lat = _device_location(raw, device.vendor)
        if lng is not None and lat is not None:
            return {
                "lng": float(lng),
                "lat": float(lat),
                "vehicle_no": vehicle.vehicle_no,
                "vehicle_model": vehicle.vehicle_model or "",
                "source": device.vendor,
                "device_label": device.device_name or device.device_code or "",
            }
    raise HTTPException(
        404,
        "暂无坐标：请先在设备管理中同步北斗/萤石数据，或确认设备已上报经纬度",
    )


@router.get("/vehicles/{vehicle_id}/bindings")
async def list_vehicle_bindings(
    vehicle_id: int,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    await _load_vehicle_or_404(db, user.id, vehicle_id)
    rows = (
        await db.execute(
            select(DeliveryVehicleDeviceBinding, DeliveryDevice)
            .join(DeliveryDevice, DeliveryDevice.id == DeliveryVehicleDeviceBinding.device_id)
            .where(
                DeliveryVehicleDeviceBinding.vehicle_id == vehicle_id,
                DeliveryVehicleDeviceBinding.delivery_id == user.id,
            )
            .order_by(DeliveryVehicleDeviceBinding.id.desc())
        )
    ).all()
    return [
        {
            "id": binding.id,
            "vehicle_id": binding.vehicle_id,
            "device": _serialize_device(device),
            "created_at": binding.created_at,
        }
        for binding, device in rows
    ]


@router.post("/vehicles/{vehicle_id}/bindings")
async def create_vehicle_binding(
    vehicle_id: int,
    payload: VehicleBindingIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    await _load_vehicle_or_404(db, user.id, vehicle_id)
    device = await _load_device_or_404(db, user.id, payload.device_id)
    exists = await db.scalar(
        select(DeliveryVehicleDeviceBinding).where(
            DeliveryVehicleDeviceBinding.vehicle_id == vehicle_id,
            DeliveryVehicleDeviceBinding.device_id == payload.device_id,
        )
    )
    if exists:
        raise HTTPException(400, "设备已绑定该车辆")
    bound_elsewhere = await db.scalar(
        select(func.count(DeliveryVehicleDeviceBinding.id))
        .join(DeliveryVehicle, DeliveryVehicle.id == DeliveryVehicleDeviceBinding.vehicle_id)
        .where(
            DeliveryVehicleDeviceBinding.device_id == payload.device_id,
            DeliveryVehicle.delivery_id == user.id,
            DeliveryVehicleDeviceBinding.vehicle_id != vehicle_id,
        )
    )
    if int(bound_elsewhere or 0) > 0:
        raise HTTPException(400, "设备已绑定其他车辆，请先解绑")
    await _validate_binding_limits(db, vehicle_id, device)
    row = DeliveryVehicleDeviceBinding(
        delivery_id=user.id,
        vehicle_id=vehicle_id,
        device_id=payload.device_id,
    )
    db.add(row)
    try:
        await db.commit()
        await db.refresh(row)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(400, "设备已被其他车辆占用，请先解绑后再绑定")
    return {"id": row.id, "vehicle_id": row.vehicle_id, "device_id": row.device_id, "created_at": row.created_at}


@router.delete("/vehicles/{vehicle_id}/bindings/{binding_id}")
async def delete_vehicle_binding(
    vehicle_id: int,
    binding_id: int,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    await _load_vehicle_or_404(db, user.id, vehicle_id)
    row = await db.scalar(
        select(DeliveryVehicleDeviceBinding).where(
            DeliveryVehicleDeviceBinding.id == binding_id,
            DeliveryVehicleDeviceBinding.vehicle_id == vehicle_id,
            DeliveryVehicleDeviceBinding.delivery_id == user.id,
        )
    )
    if not row:
        raise HTTPException(404, "绑定关系不存在")
    await db.delete(row)
    await db.commit()
    return {"message": "ok"}


@router.get("/suppliers")
async def delivery_suppliers(
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    return (
        await db.scalars(
            select(User)
            .where(User.role == "supplier", User.supplier_delivery_id == user.id)
            .order_by(User.id.desc())
        )
    ).all()


@router.get("/suppliers/address-tips")
async def supplier_address_tips(
    keywords: str,
    city: Optional[str] = "北京",
    _=Depends(require_role("delivery")),
):
    items = await search_address_tips(keywords=keywords, city=city, limit=10)
    return {
        "items": items,
        "amap_enabled": bool((settings.amap_web_key or "").strip()),
    }


@router.get("/suppliers/quote-filter-categories")
async def delivery_supplier_quote_filter_categories(
    _=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    """供货商报价弹窗筛选用：一级商品分类（只读）。"""
    rows = (
        await db.scalars(
            select(Category)
            .where(Category.level == 1, Category.is_deleted.is_(False))
            .order_by(Category.sort_order, Category.id)
        )
    ).all()
    return [{"id": int(c.id), "name": c.name} for c in rows]


@router.post("/suppliers")
async def create_delivery_supplier(
    payload: SupplierAccountIn,
    request: Request,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    _normalize_supplier_payload(payload)
    if not payload.username:
        raise HTTPException(400, "用户名不能为空")
    if not payload.company_name:
        raise HTTPException(400, "企业名称不能为空")
    if not payload.address:
        raise HTTPException(400, "用户地址不能为空")
    coord = await geocode_address(payload.address)
    if not coord:
        raise HTTPException(400, "地址无法解析，请填写更准确地址")
    exists = await db.scalar(select(User).where(User.username == payload.username))
    if exists:
        raise HTTPException(400, "用户名已存在")
    row = User(
        username=payload.username,
        password_hash=bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        role="supplier",
        supplier_delivery_id=user.id,
        company_name=payload.company_name,
        contact_phone=payload.contact_phone,
        address=payload.address,
        lng=coord[0],
        lat=coord[1],
        status=payload.status,
    )
    db.add(row)
    await db.flush()
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="supplier_create_by_delivery",
        category="account",
        object_type="account",
        object_id=row.id,
                detail=f"配送商新增供货商账号 {row.username}",
        **_audit_meta(request),
    )
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/suppliers/{supplier_id}")
async def update_delivery_supplier(
    supplier_id: int,
    payload: SupplierAccountIn,
    request: Request,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    _normalize_supplier_payload(payload)
    if not payload.company_name:
        raise HTTPException(400, "企业名称不能为空")
    if not payload.address:
        raise HTTPException(400, "用户地址不能为空")
    coord = await geocode_address(payload.address)
    if not coord:
        raise HTTPException(400, "地址无法解析，请填写更准确地址")
    row = await db.scalar(
        select(User).where(
            User.id == supplier_id, User.role == "supplier", User.supplier_delivery_id == user.id
        )
    )
    if not row:
        raise HTTPException(404, "供货商账号不存在")
    row.company_name = payload.company_name
    row.contact_phone = payload.contact_phone
    row.address = payload.address
    row.lng = coord[0]
    row.lat = coord[1]
    row.status = payload.status
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="supplier_update_by_delivery",
        category="account",
        object_type="account",
        object_id=row.id,
                detail=f"配送商更新供货商账号 {row.username}",
        **_audit_meta(request),
    )
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/suppliers/{supplier_id}")
async def delete_delivery_supplier(
    supplier_id: int,
    request: Request,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(
        select(User).where(
            User.id == supplier_id, User.role == "supplier", User.supplier_delivery_id == user.id
        )
    )
    if not row:
        raise HTTPException(404, "供货商账号不存在")
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="supplier_delete_by_delivery",
        category="account",
        object_type="account",
        object_id=row.id,
                detail=f"配送商删除供货商账号 {row.username}",
        **_audit_meta(request),
    )
    await db.delete(row)
    await db.commit()
    return {"message": "deleted"}


@router.get("/suppliers/{supplier_id}/product-quotes")
async def delivery_supplier_product_quotes(
    supplier_id: int,
    keyword: Optional[str] = None,
    category1_id: Optional[int] = Query(None, ge=1),
    page: int = 1,
    page_size: int = 20,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    supplier = await db.scalar(
        select(User).where(
            User.id == supplier_id,
            User.role == "supplier",
            User.supplier_delivery_id == user.id,
        )
    )
    if not supplier:
        raise HTTPException(404, "供货商账号不存在")

    safe_page = max(int(page or 1), 1)
    safe_size = min(max(int(page_size or 20), 1), 100)
    offset = (safe_page - 1) * safe_size

    where = [SupplierProductQuote.supplier_id == supplier_id]
    if keyword and keyword.strip():
        kw = keyword.strip()
        where.append(or_(Product.name.like(f"%{kw}%"), Product.goods_sn.like(f"%{kw}%")))
    if category1_id is not None:
        where.append(Product.category1_id == int(category1_id))

    count_stmt = (
        select(func.count(SupplierProductQuote.id))
        .select_from(SupplierProductQuote)
        .join(Product, Product.id == SupplierProductQuote.product_id)
        .where(*where)
    )
    total = int(await db.scalar(count_stmt) or 0)

    rows = (
        await db.execute(
            select(SupplierProductQuote, Product)
            .join(Product, Product.id == SupplierProductQuote.product_id)
            .where(*where)
            .order_by(SupplierProductQuote.id.desc())
            .offset(offset)
            .limit(safe_size)
        )
    ).all()

    category_ids = {
        int(product.category1_id)
        for _, product in rows
        if product and product.category1_id is not None
    }
    category_map: dict[int, str] = {}
    if category_ids:
        categories = (await db.scalars(select(Category).where(Category.id.in_(category_ids)))).all()
        category_map = {int(c.id): c.name for c in categories}

    all_contracts = (
        await db.scalars(
            select(Contract)
            .where(Contract.delivery_id == user.id, Contract.status == "已中标")
            .order_by(Contract.id.desc())
        )
    ).all()
    latest_contract_by_client: dict[int, Contract] = {}
    for contract in all_contracts:
        cid = int(contract.client_id)
        if cid not in latest_contract_by_client:
            latest_contract_by_client[cid] = contract
    client_name_map: dict[int, str] = {}
    if latest_contract_by_client:
        client_ids = list(latest_contract_by_client.keys())
        clients = (
            await db.scalars(
                select(User).where(User.id.in_(client_ids), User.role == "client")
            )
        ).all()
        client_name_map = {int(c.id): (c.company_name or c.username) for c in clients}
    today = date.today()

    items = []
    product_ids = [int(product.id) for _, product in rows if product and product.id is not None]
    peer_quote_map: dict[int, list[dict[str, Any]]] = {}
    if product_ids:
        peer_rows = (
            await db.execute(
                select(SupplierProductQuote, User)
                .join(User, User.id == SupplierProductQuote.supplier_id)
                .where(
                    SupplierProductQuote.product_id.in_(product_ids),
                    User.role == "supplier",
                    User.supplier_delivery_id == user.id,
                )
            )
        ).all()
        for peer_quote, peer_supplier in peer_rows:
            pid = int(peer_quote.product_id)
            peer_quote_map.setdefault(pid, []).append(
                {
                    "supplier_id": int(peer_quote.supplier_id),
                    "supplier_name": peer_supplier.company_name
                    or peer_supplier.username
                    or f"供货商#{int(peer_quote.supplier_id)}",
                    "quote_price": float(peer_quote.quote_price or 0),
                }
            )
        for pid in list(peer_quote_map.keys()):
            peer_quote_map[pid] = sorted(
                peer_quote_map[pid],
                key=lambda x: (float(x.get("quote_price") or 0), int(x.get("supplier_id") or 0)),
            )

    for quote, product in rows:
        c1 = int(product.category1_id) if product.category1_id is not None else None
        contract_quotes: list[dict[str, Any]] = []
        for client_id, contract in latest_contract_by_client.items():
            rate_map, fallback_rate = _contract_rate_map_and_fallback(contract)
            floating_price = _floating_price(float(product.reference_price or 0), c1, rate_map, fallback_rate)
            in_period = bool(contract.period_start <= today <= contract.period_end)
            contract_quotes.append(
                {
                    "client_id": client_id,
                    "client_name": client_name_map.get(client_id, f"客户端#{client_id}"),
                    "contract_id": contract.id,
                    "period_start": contract.period_start,
                    "period_end": contract.period_end,
                    "in_period": in_period,
                    "float_rate": rate_map.get(c1, fallback_rate) if c1 is not None else None,
                    "floating_price": floating_price,
                }
            )
        ranked_quotes = peer_quote_map.get(int(product.id), [])
        rank = None
        for idx, row in enumerate(ranked_quotes, 1):
            if int(row["supplier_id"]) == int(supplier_id):
                rank = idx
                break
        peer_only = [row for row in ranked_quotes if int(row["supplier_id"]) != int(supplier_id)]
        peer_prices = [float(row["quote_price"]) for row in peer_only]
        peer_min = round(min(peer_prices), 2) if peer_prices else None
        peer_avg = round(sum(peer_prices) / len(peer_prices), 2) if peer_prices else None
        items.append(
            {
                "quote_id": quote.id,
                "product_id": product.id,
                "goods_sn": product.goods_sn or "",
                "product_name": product.name,
                "unit": product.unit,
                "category1_id": product.category1_id,
                "category1_name": category_map.get(c1 or 0, ""),
                "reference_price": float(product.reference_price or 0),
                "quote_price": float(quote.quote_price or 0),
                "remark": quote.remark or "",
                "updated_at": getattr(quote, "updated_at", None) or quote.created_at,
                "client_float_quotes": contract_quotes,
                "peer_supplier_quotes": peer_only,
                "peer_quote_min": peer_min,
                "peer_quote_avg": peer_avg,
                "quote_rank": rank,
                "quote_rank_total": len(ranked_quotes),
            }
        )

    return {
        "supplier_id": supplier_id,
        "supplier_name": supplier.company_name or supplier.username,
        "items": items,
        "total": total,
        "page": safe_page,
        "page_size": safe_size,
    }


@router.get("/orders")
async def delivery_orders(
    status: Optional[str] = None,
    status_in: Optional[str] = None,
    order_no: Optional[str] = None,
    created_date_start: Optional[str] = None,
    created_date_end: Optional[str] = None,
    expected_delivery_date: Optional[str] = None,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Order).where(Order.delivery_id == user.id).order_by(Order.id.desc())
    # 多状态筛选（如智能排线：下单+配货）；与单个 status 互斥，优先 status_in
    if status_in and str(status_in).strip():
        parts = [s.strip() for s in str(status_in).split(",") if s.strip()]
        if parts:
            stmt = stmt.where(Order.status.in_(parts))
    elif status:
        stmt = stmt.where(Order.status == status)
    if order_no and order_no.strip():
        stmt = stmt.where(Order.order_no.like(f"%{order_no.strip()}%"))

    if expected_delivery_date and str(expected_delivery_date).strip():
        try:
            ed = date.fromisoformat(str(expected_delivery_date).strip())
        except ValueError:
            raise HTTPException(400, "expected_delivery_date 格式须为 YYYY-MM-DD")
        stmt = stmt.where(Order.expected_delivery_date == ed)
    else:
        today = datetime.utcnow().date()
        try:
            start_date = date.fromisoformat(created_date_start) if created_date_start else today
            end_date = date.fromisoformat(created_date_end) if created_date_end else today
        except ValueError:
            raise HTTPException(400, "时间筛选格式错误，需为 YYYY-MM-DD")
        if end_date < start_date:
            raise HTTPException(400, "结束日期不能早于开始日期")
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date + timedelta(days=1), time.min)
        stmt = stmt.where(Order.created_at >= start_dt, Order.created_at < end_dt)

    return (await db.scalars(stmt)).all()


@router.get("/complaints")
async def delivery_list_complaints(
    status: Optional[str] = None,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    """本配送商关联订单的售后投诉工单列表。"""
    stmt = (
        select(Ticket)
        .join(Order, Order.id == Ticket.order_id)
        .where(Order.delivery_id == user.id, Ticket.type == "售后投诉")
        .order_by(Ticket.id.desc())
    )
    if status:
        stmt = stmt.where(Ticket.status == status)
    rows = (await db.scalars(stmt)).all()
    if not rows:
        return []
    order_ids = sorted({int(r.order_id) for r in rows})
    order_map: dict[int, str] = {}
    if order_ids:
        orows = (await db.execute(select(Order.id, Order.order_no).where(Order.id.in_(order_ids)))).all()
        order_map = {int(o[0]): o[1] for o in orows}
    out = []
    for r in rows:
        d = complaint_ticket_public_dict(r)
        d["order_no"] = order_map.get(int(r.order_id), "")
        out.append(d)
    return out


@router.post("/complaints/{ticket_id}/respond")
async def delivery_respond_complaint(
    ticket_id: int,
    payload: ComplaintRespondIn,
    request: Request,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    ticket = await db.scalar(select(Ticket).where(Ticket.id == ticket_id, Ticket.type == "售后投诉"))
    if not ticket:
        raise HTTPException(404, "工单不存在")
    order = await db.scalar(select(Order).where(Order.id == ticket.order_id))
    if not order or int(order.delivery_id) != int(user.id):
        raise HTTPException(403, "无权限处理该工单")
    await submit_delivery_complaint_response(db, ticket, user, payload.response)
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="ticket_complaint_delivery_response",
        category="ticket",
        object_type="ticket",
        object_id=int(ticket.id),
        detail=f"配送商提交售后处理意见 ticket_id={ticket_id}",
        **_audit_meta(request),
    )
    op_ids = await list_operation_user_ids(db)
    if op_ids:
        await push_notification(
            db=db,
            role="operation",
            event_type="ticket_complaint",
            title=f"配送商已反馈售后工单 #{ticket_id}",
            content=(payload.response or "")[:300],
            route="/operation/tickets",
            object_type="ticket",
            object_id=int(ticket_id),
            target_user_ids=op_ids,
        )
    await db.commit()
    await db.refresh(ticket)
    return complaint_ticket_public_dict(ticket)


@router.get("/tenders")
async def delivery_tenders(
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.scalars(select(Tender).where(Tender.status == "招标中"))).all()
    return [r for r in rows if user.id in (r.delivery_ids_json or [])]


@router.get("/contracts")
async def delivery_contracts(
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    return (
        await db.scalars(select(Contract).where(Contract.delivery_id == user.id).order_by(Contract.id.desc()))
    ).all()


@router.post("/smart-split")
async def smart_split_orders(
    payload: SmartSplitIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    return await smart_split_preview(payload, user=user, db=db)


@router.post("/smart-split/preview")
async def smart_split_preview(
    payload: SmartSplitIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    conf = _mode_config(payload.mode, payload.allow_split)
    order_ids = sorted({int(i) for i in (payload.order_ids or []) if int(i) > 0})
    if not order_ids:
        raise HTTPException(400, "请至少选择一个订单")
    orders = (
        await db.scalars(
            select(Order)
            .where(Order.id.in_(order_ids), Order.delivery_id == user.id)
            .order_by(Order.id.asc())
        )
    ).all()
    if len(orders) != len(order_ids):
        raise HTTPException(400, "存在无效订单或无权限订单")
    invalid_status_orders = [o.order_no for o in orders if o.status not in SMART_SPLIT_ALLOWED_ORDER_STATUSES]
    if invalid_status_orders:
        raise HTTPException(400, f"以下订单状态不允许分单：{', '.join(invalid_status_orders)}")

    suppliers = await _delivery_suppliers(db, user.id)
    if not suppliers:
        raise HTTPException(400, "当前配送商下没有可用供货商")
    supplier_options = [
        {
            "id": s.id,
            "username": s.username,
            "company_name": s.company_name,
            "label": s.company_name or s.username,
        }
        for s in suppliers
    ]
    supplier_ids = [s.id for s in suppliers]
    # 仅将「本批订单里商品勾选了指定厂家」的厂家账号加入下拉，避免全库厂家混入智能分单（厂家非供货商、通常也无 SupplierProductQuote）
    preview_product_ids: set[int] = set()
    for _o in orders:
        for _it in _o.items_json or []:
            _pid = int(_it.get("product_id") or 0)
            if _pid > 0:
                preview_product_ids.add(_pid)
    factory_ids_needed: set[int] = set()
    if preview_product_ids:
        _prows = (
            await db.scalars(
                select(Product).where(Product.id.in_(preview_product_ids), Product.is_deleted.is_(False))
            )
        ).all()
        for _p in _prows:
            if _p and bool(_p.is_designated_factory) and int(_p.designated_factory_id or 0) > 0:
                factory_ids_needed.add(int(_p.designated_factory_id))
    factory_label_map: dict[int, str] = {}
    if factory_ids_needed:
        factory_users_needed = (
            await db.scalars(
                select(User).where(
                    User.id.in_(factory_ids_needed),
                    User.role == "factory",
                    User.status == "active",
                )
            )
        ).all()
        for f in factory_users_needed:
            factory_label_map[int(f.id)] = f.company_name or f.username or f"厂家{f.id}"
            if int(f.id) in {int(x["id"]) for x in supplier_options}:
                continue
            supplier_options.append(
                {
                    "id": f.id,
                    "username": f.username,
                    "company_name": f.company_name,
                    "label": f.company_name or f.username,
                }
            )

    now = datetime.utcnow()
    if payload.quota_window == "week":
        window_days = 7
    elif payload.quota_window == "month":
        window_days = 30
    else:
        window_days = 90
    window_start = now - timedelta(days=window_days)
    quota_rows = (
        await db.execute(
            select(
                OrderItemAllocation.supplier_id,
                func.sum(OrderItemAllocation.quantity),
            )
            .where(
                OrderItemAllocation.delivery_id == user.id,
                OrderItemAllocation.created_at >= window_start,
                OrderItemAllocation.supplier_id.in_(supplier_ids),
            )
            .group_by(OrderItemAllocation.supplier_id)
        )
    ).all()
    usage_raw = {int(sid): float(qty or 0) for sid, qty in quota_rows}
    total_usage = sum(usage_raw.values())
    quota_usage = {
        sid: (float(usage_raw.get(sid, 0.0)) / total_usage) if total_usage > 0 else 0.0
        for sid in supplier_ids
    }
    review_rows = (
        await db.execute(
            select(
                Order.supplier_id,
                func.avg(OrderReview.rating),
            )
            .join(OrderReview, OrderReview.order_id == Order.id)
            .where(
                Order.delivery_id == user.id,
                Order.supplier_id.in_(supplier_ids),
            )
            .group_by(Order.supplier_id)
        )
    ).all()
    rating_map = {int(sid): float(avg_rating or 0) for sid, avg_rating in review_rows if avg_rating is not None}
    rated_supplier_ids = {sid for sid, score in rating_map.items() if score > 0}

    results: list[dict[str, Any]] = []
    for order in orders:
        selected_suppliers: list[int] = []
        line_items = order.items_json or []
        for idx, item in enumerate(line_items, 1):
            product_id = int(item.get("product_id") or 0)
            if product_id <= 0:
                continue
            product = await db.scalar(select(Product).where(Product.id == product_id))
            is_designated_factory = bool(product.is_designated_factory) if product else False
            designated_factory_id = int(product.designated_factory_id or 0) if product else 0
            quote_rows = (
                await db.scalars(
                    select(SupplierProductQuote).where(
                        SupplierProductQuote.product_id == product_id,
                        SupplierProductQuote.supplier_id.in_(supplier_ids),
                    )
                )
            ).all()
            quote_map = {int(q.supplier_id): float(q.quote_price or 0) for q in quote_rows}
            has_quoted_suppliers = bool(quote_map)
            candidate_supplier_ids = sorted(quote_map.keys())
            designated_reason = ""
            if is_designated_factory and designated_factory_id > 0:
                designated_label = factory_label_map.get(
                    designated_factory_id, f"厂家#{designated_factory_id}"
                )
                designated_reason = f"指定厂家商品，仅允许分配给{designated_label}"
                has_quoted_suppliers = True
                candidate_supplier_ids = [designated_factory_id]
            state_supplier_ids = list(supplier_ids)
            if is_designated_factory and designated_factory_id > 0 and designated_factory_id not in state_supplier_ids:
                state_supplier_ids.append(designated_factory_id)
            supplier_option_states = [
                {
                    "supplier_id": int(sid),
                    "quoted": (int(sid) in quote_map) or (is_designated_factory and int(sid) == designated_factory_id),
                    "quote_price": quote_map.get(int(sid)),
                    "disabled": (
                        int(sid) != designated_factory_id if is_designated_factory else int(sid) not in quote_map
                    ),
                    "disabled_reason": (
                        designated_reason if (is_designated_factory and int(sid) != designated_factory_id)
                        else ("" if int(sid) in quote_map else "未报价")
                    ),
                }
                for sid in state_supplier_ids
            ]

            price_values = [quote_map[sid] for sid in candidate_supplier_ids if sid in quote_map]
            min_price = min(price_values) if price_values else None
            max_price = max(price_values) if price_values else None

            scored: list[tuple[float, int, str, dict[str, float]]] = []
            for sid in candidate_supplier_ids:
                quote_price = quote_map.get(sid)
                if quote_price is None:
                    price_score = 0.35
                elif min_price is None or max_price is None or max_price == min_price:
                    price_score = 1.0
                else:
                    price_score = (max_price - quote_price) / (max_price - min_price)

                quota_score = 1 - min(max(quota_usage.get(sid, 0.0), 0.0), 1.0)
                stability_score = 1.0 if sid in selected_suppliers else 0.7
                distance_km: Optional[float] = None
                supplier = next((s for s in suppliers if int(s.id) == int(sid)), None)
                if (
                    user.lng is not None
                    and user.lat is not None
                    and supplier
                    and supplier.lng is not None
                    and supplier.lat is not None
                ):
                    distance_km = _haversine_km(
                        float(user.lng),
                        float(user.lat),
                        float(supplier.lng),
                        float(supplier.lat),
                    )
                distance_score = 0.5 if distance_km is None else max(0.0, 1.0 - min(distance_km, 50.0) / 50.0)
                supplier_rating = rating_map.get(int(sid))
                rating_score = (
                    max(0.0, min(float(supplier_rating), 5.0) / 5.0)
                    if supplier_rating is not None and supplier_rating > 0
                    else 0.0
                )
                score_detail = {
                    "price": conf["weights"]["price"] * price_score,
                    "quota": conf["weights"]["quota"] * quota_score,
                    "distance": conf["weights"].get("distance", 0.0) * distance_score,
                    "rating": conf["weights"].get("rating", 0.0) * rating_score,
                    "stability": conf["weights"]["stability"] * stability_score,
                }
                total_score = sum(score_detail.values())
                reason = _supplier_quota_reason(
                    sid,
                    quote_price or 0.0,
                    quota_usage,
                    score_detail,
                    distance_km,
                    supplier_rating,
                )
                scored.append((total_score, sid, reason, score_detail))
            if scored:
                scored.sort(key=lambda x: x[0], reverse=True)

            max_suppliers = int(conf["max_suppliers_per_order"])
            preferred_supplier_id = int(scored[0][1]) if scored else 0
            reason_text = scored[0][2] if scored else "当前配送商下该商品暂无供货商报价，需先报价后分单"
            if designated_reason:
                reason_text = designated_reason
            score_detail_top = (
                scored[0][3]
                if scored
                else {"price": 0.0, "quota": 0.0, "distance": 0.0, "rating": 0.0, "stability": 0.0}
            )
            if scored and preferred_supplier_id not in selected_suppliers and len(selected_suppliers) >= max_suppliers:
                existed = [x for x in scored if x[1] in selected_suppliers]
                if existed:
                    preferred_supplier_id = existed[0][1]
                    reason_text = f"{existed[0][2]}；受订单供货商上限约束"
                    score_detail_top = existed[0][3]
            if scored and preferred_supplier_id not in selected_suppliers:
                selected_suppliers.append(preferred_supplier_id)

            quantity = _item_quantity(item)
            if quantity <= 0:
                continue
            split_allowed = bool(conf["allow_split"] and quantity > float(conf["split_quantity_threshold"]))
            score_total = sum(float(v or 0.0) for v in score_detail_top.values()) or 1.0
            results.append(
                {
                    "order_id": order.id,
                    "order_no": order.order_no,
                    "line_no": idx,
                    "product_id": product_id,
                    "product_name": product.name if product else f"商品#{product_id}",
                    "quantity": quantity,
                    "source_quantity": quantity,
                    "unit_price": _item_unit_price(item),
                    "supplier_id": int(designated_factory_id if designated_factory_id > 0 and is_designated_factory else preferred_supplier_id),
                    "supplier_options": supplier_options,
                    "supplier_option_states": supplier_option_states,
                    "has_quoted_suppliers": has_quoted_suppliers,
                    "is_designated_factory": is_designated_factory,
                    "designated_factory_id": designated_factory_id if designated_factory_id > 0 else None,
                    "suggest_reason": reason_text,
                    "allow_split": split_allowed,
                    "score_breakdown": {
                        "price": round(float(score_detail_top.get("price", 0.0)), 6),
                        "quota": round(float(score_detail_top.get("quota", 0.0)), 6),
                        "stability": round(float(score_detail_top.get("stability", 0.0)), 6),
                        "price_ratio": round(float(score_detail_top.get("price", 0.0)) / score_total, 4),
                        "quota_ratio": round(float(score_detail_top.get("quota", 0.0)) / score_total, 4),
                        "stability_ratio": round(float(score_detail_top.get("stability", 0.0)) / score_total, 4),
                    },
                }
            )
    return {
        "success": True,
        "results": results,
        "mode_meta": {
            "mode": conf["mode"],
            "mode_label": conf["label"],
            "allow_split": bool(conf["allow_split"]),
            "max_suppliers_per_order": int(conf["max_suppliers_per_order"]),
            "split_quantity_threshold": float(conf["split_quantity_threshold"]),
            "quota_window": payload.quota_window,
            "weights": conf["weights"],
            "rating_data": {
                "rated_supplier_count": len(rated_supplier_ids),
                "total_supplier_count": len(supplier_ids),
                "coverage": round(len(rated_supplier_ids) / len(supplier_ids), 4) if supplier_ids else 0.0,
                "enabled": len(rated_supplier_ids) > 0,
            },
            "quota_snapshot": [
                {
                    "supplier_id": sid,
                    "supplier_name": (
                        next((s.company_name or s.username) for s in suppliers if int(s.id) == int(sid))
                    ),
                    "usage_ratio": round(float(quota_usage.get(sid, 0.0)), 4),
                }
                for sid in supplier_ids
            ],
        },
    }


@router.post("/smart-split/commit")
async def smart_split_commit(
    payload: SmartSplitCommitIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    conf = _mode_config(payload.mode, payload.allow_split)
    if not payload.allocations:
        raise HTTPException(400, "请先生成并确认分单结果")

    order_ids = sorted({int(a.order_id) for a in payload.allocations})
    orders = (
        await db.scalars(
            select(Order).where(Order.id.in_(order_ids), Order.delivery_id == user.id)
        )
    ).all()
    order_map = {o.id: o for o in orders}
    if len(order_map) != len(order_ids):
        raise HTTPException(400, "存在无权限订单")
    invalid_status_orders = [o.order_no for o in orders if o.status not in SMART_SPLIT_ALLOWED_ORDER_STATUSES]
    if invalid_status_orders:
        raise HTTPException(400, f"以下订单状态不允许分单：{', '.join(invalid_status_orders)}")

    suppliers = await _delivery_suppliers(db, user.id)
    supplier_ids = {s.id for s in suppliers}
    supplier_label_map = {int(s.id): (s.company_name or s.username or f"供货商{s.id}") for s in suppliers}

    source_quantity_map: dict[tuple[int, int], float] = {}
    source_product_map: dict[tuple[int, int], int] = {}
    for order in orders:
        for idx, item in enumerate(order.items_json or [], 1):
            source_quantity_map[(order.id, idx)] = _item_quantity(item)
            source_product_map[(order.id, idx)] = int(item.get("product_id") or 0)

    alloc_product_ids = sorted({int(a.product_id) for a in payload.allocations})
    product_rows = (
        await db.execute(
            select(
                Product.id,
                Product.name,
                Product.is_designated_factory,
                Product.designated_factory_id,
            ).where(
                Product.id.in_(alloc_product_ids),
                Product.is_deleted.is_(False),
            )
        )
    ).all()
    product_name_map = {int(pid): (name or f"商品#{pid}") for pid, name, _, _ in product_rows}
    product_designated_map = {
        int(pid): {
            "is_designated_factory": bool(is_designated_factory),
            "designated_factory_id": int(designated_factory_id or 0),
        }
        for pid, _, is_designated_factory, designated_factory_id in product_rows
    }
    existed_product_ids = set(product_name_map.keys())
    missing_products = [pid for pid in alloc_product_ids if pid not in existed_product_ids]
    if missing_products:
        raise HTTPException(
            400,
            f"存在已删除商品，无法确认分单：{', '.join(str(i) for i in missing_products)}。请先刷新订单或联系运营修复商品主数据。",
        )

    sum_quantity_map: dict[tuple[int, int], float] = {}
    supplier_set_by_order: dict[int, set[int]] = {}
    for row in payload.allocations:
        meta0 = product_designated_map.get(int(row.product_id), {})
        is_df0 = bool(meta0.get("is_designated_factory"))
        dfid0 = int(meta0.get("designated_factory_id") or 0)
        sid0 = int(row.supplier_id)
        if is_df0 and dfid0 > 0 and sid0 == dfid0:
            pass
        elif sid0 not in supplier_ids:
            raise HTTPException(400, f"供货商 {row.supplier_id} 不属于当前配送商")
        key = (row.order_id, row.line_no)
        expected_product_id = source_product_map.get(key)
        if expected_product_id is None:
            raise HTTPException(400, f"订单 {row.order_id} 行号 {row.line_no} 不存在")
        if int(row.product_id) != int(expected_product_id):
            raise HTTPException(400, f"订单 {row.order_id} 行号 {row.line_no} 商品不匹配")
        if float(row.quantity) <= 0:
            raise HTTPException(400, "分配数量必须大于0")
        sum_quantity_map[key] = float(sum_quantity_map.get(key, 0)) + float(row.quantity)
        supplier_set_by_order.setdefault(row.order_id, set()).add(int(row.supplier_id))

    alloc_supplier_ids = sorted({int(a.supplier_id) for a in payload.allocations})
    quote_pairs = set(
        (
            await db.execute(
                select(SupplierProductQuote.supplier_id, SupplierProductQuote.product_id).where(
                    SupplierProductQuote.supplier_id.in_(alloc_supplier_ids),
                    SupplierProductQuote.product_id.in_(alloc_product_ids),
                )
            )
        ).all()
    )
    for row in payload.allocations:
        product_meta = product_designated_map.get(int(row.product_id), {})
        is_designated_factory = bool(product_meta.get("is_designated_factory"))
        designated_factory_id = int(product_meta.get("designated_factory_id") or 0)
        if is_designated_factory:
            if designated_factory_id <= 0:
                raise HTTPException(400, f"商品{row.product_id}缺少指定厂家，无法分单")
            if int(row.supplier_id) != designated_factory_id:
                product_name = product_name_map.get(int(row.product_id), f"商品#{row.product_id}")
                raise HTTPException(
                    400,
                    f"商品“{product_name}”为指定厂家商品，仅可分配给厂家#{designated_factory_id}",
                )
            continue
        pair = (int(row.supplier_id), int(row.product_id))
        if pair in quote_pairs:
            continue
        order = order_map.get(int(row.order_id))
        order_no = order.order_no if order else f"#{row.order_id}"
        product_name = product_name_map.get(int(row.product_id), f"商品#{row.product_id}")
        supplier_label = supplier_label_map.get(int(row.supplier_id), f"供货商#{row.supplier_id}")
        raise HTTPException(
            400,
            f"订单{order_no} 第{row.line_no}行（{product_name}）不能分配给{supplier_label}：该供货商未报价，请先完成报价后再分单。",
        )

    for key, src_qty in source_quantity_map.items():
        commit_qty = float(sum_quantity_map.get(key, 0))
        if round(commit_qty, 3) != round(float(src_qty), 3):
            raise HTTPException(
                400,
                f"订单 {key[0]} 行号 {key[1]} 分配数量不等于原始数量（原始 {src_qty}，提交 {commit_qty}）",
            )

        # 是否发生拆行
        alloc_count = sum(1 for a in payload.allocations if a.order_id == key[0] and a.line_no == key[1])
        if alloc_count > 1 and not bool(conf["allow_split"]):
            raise HTTPException(400, f"当前模式不允许拆行：订单 {key[0]} 行号 {key[1]}")
        if alloc_count > 1 and float(src_qty) <= float(conf["split_quantity_threshold"]):
            raise HTTPException(
                400,
                f"订单 {key[0]} 行号 {key[1]} 数量过小（{src_qty}），低于拆分阈值 {conf['split_quantity_threshold']}",
            )

    for order_id, supplier_set in supplier_set_by_order.items():
        if len(supplier_set) > int(conf["max_suppliers_per_order"]):
            raise HTTPException(
                400,
                f"订单 {order_id} 供货商数量超限（最多 {conf['max_suppliers_per_order']} 家）",
            )

    # 先删状态日志：order_item_status_logs 引用 allocations，MySQL 外键无 ON DELETE CASCADE 时直接删 allocations 会 500
    old_alloc_ids = (
        await db.scalars(
            select(OrderItemAllocation.id).where(
                OrderItemAllocation.order_id.in_(order_ids),
                OrderItemAllocation.delivery_id == user.id,
            )
        )
    ).all()
    if old_alloc_ids:
        await db.execute(
            delete(OrderItemStatusLog).where(OrderItemStatusLog.allocation_id.in_(old_alloc_ids))
        )
    await db.execute(
        delete(OrderItemAllocation).where(
            OrderItemAllocation.order_id.in_(order_ids),
            OrderItemAllocation.delivery_id == user.id,
        )
    )
    batch_no = f"split-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    created = 0
    for row in payload.allocations:
        allocation = OrderItemAllocation(
            order_id=row.order_id,
            delivery_id=user.id,
            supplier_id=row.supplier_id,
            line_no=row.line_no,
            product_id=row.product_id,
            quantity=round(float(row.quantity), 3),
            unit_price=round(float(row.unit_price), 2),
            allocation_batch_no=batch_no,
            status="已分配",
            created_by=user.id,
        )
        db.add(allocation)
        await db.flush()
        db.add(
            OrderItemStatusLog(
                allocation_id=allocation.id,
                old_status="待确认",
                new_status="已分配",
                operator_id=user.id,
                note="智能分单确认提交",
            )
        )
        created += 1

    # 已确认分单的订单进入「配货」阶段，避免继续出现在待分单池中
    for order in orders:
        order.status = "配货"

    # 通知本分单涉及的供货商 / 厂家（分包对象），与订单状态流转侧供货商通知语义一致
    for order in orders:
        sids = supplier_set_by_order.get(order.id) or set()
        if not sids:
            continue
        users = (await db.scalars(select(User).where(User.id.in_(list(sids))))).all()
        by_role: dict[str, list[int]] = defaultdict(list)
        for u in users:
            by_role[str(u.role or "")].append(int(u.id))
        base_content = (
            f"订单 {order.order_no} 已由配送商确认智能分单，请登录对应端查看分包明细并及时配货。"
        )
        if by_role.get("supplier"):
            await push_notification(
                db=db,
                role="supplier",
                event_type="order_split_confirmed",
                title="新的供货分单",
                content=base_content,
                route=f"/supplier/orders/{order.id}",
                object_type="order",
                object_id=order.id,
                target_user_ids=by_role["supplier"],
            )
        if by_role.get("factory"):
            await push_notification(
                db=db,
                role="factory",
                event_type="order_split_confirmed",
                title="新的供货分单",
                content=base_content,
                route=f"/factory/orders/{order.id}",
                object_type="order",
                object_id=order.id,
                target_user_ids=by_role["factory"],
            )

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(400, "确认分单失败：存在无效外键数据，请刷新建议后重试") from e
    return {
        "message": "分单已确认",
        "created": created,
        "batch_no": batch_no,
        "mode": conf["mode"],
    }


@router.get("/smart-split/{order_id}")
async def smart_split_detail(
    order_id: int,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.delivery_id == user.id)
    )
    if not order:
        raise HTTPException(404, "订单不存在")
    rows = (
        await db.scalars(
            select(OrderItemAllocation)
            .where(
                OrderItemAllocation.order_id == order_id,
                OrderItemAllocation.delivery_id == user.id,
            )
            .order_by(OrderItemAllocation.line_no.asc(), OrderItemAllocation.id.asc())
        )
    ).all()
    return {
        "order_id": order.id,
        "order_no": order.order_no,
        "results": [
            {
                "id": row.id,
                "order_id": row.order_id,
                "line_no": row.line_no,
                "product_id": row.product_id,
                "quantity": float(row.quantity),
                "unit_price": float(row.unit_price),
                "supplier_id": row.supplier_id,
                "status": row.status,
                "batch_no": row.allocation_batch_no,
            }
            for row in rows
        ],
    }


def _order_client_window_sh(order: Order, fallback_plan_date: date, sh_tz: ZoneInfo) -> tuple[datetime, datetime]:
    """客户约定配送窗口（北京时间）：日期取订单 expected_delivery_date，缺省为本次计划日期。时段缺省按 09:00-10:00（1 小时）。"""
    d = order.expected_delivery_date or fallback_plan_date
    parsed = parse_delivery_slot_hours(order.expected_delivery_slot)
    if not parsed:
        ha, hb = 9, 10
    else:
        ha, hb = parsed
    start = datetime.combine(d, time(ha, 0), tzinfo=sh_tz)
    if hb >= 24:
        end = datetime.combine(d, time(23, 59, 59), tzinfo=sh_tz)
    else:
        end = datetime.combine(d, time(hb, 0), tzinfo=sh_tz)
    return start, end


def _arrive_late_minutes_vs_window(arrive_utc: datetime, window_end_sh: datetime) -> float:
    arr = arrive_utc.astimezone(window_end_sh.tzinfo)
    return max(0.0, (arr - window_end_sh).total_seconds() / 60.0)


def _clamp_arrive_not_before_window_start(arrive_utc: datetime, window_start_sh: datetime) -> tuple[datetime, float]:
    """
    若车辆驶达时刻早于客户约定窗口起点，按「就地等待至窗内再开工」将到达时刻钳到窗口起点。
    返回 (钳制后的到达 UTC, 等待分钟数)。
    """
    ws_utc = window_start_sh.astimezone(timezone.utc)
    if arrive_utc >= ws_utc:
        return arrive_utc, 0.0
    wait_m = (ws_utc - arrive_utc).total_seconds() / 60.0
    return ws_utc, wait_m


@router.post("/route-plan")
async def route_plan(
    payload: RoutePlanIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    if int(payload.driver_id) != int(user.id):
        raise HTTPException(403, "仅能使用本人配送商账号发起路线规划")
    driver = await db.scalar(
        select(User).where(User.id == payload.driver_id, User.role == "delivery")
    )
    if not driver:
        raise HTTPException(404, "配送账号不存在")
    if not payload.order_ids:
        raise HTTPException(400, "请至少选择一个订单")
    sh_tz = ZoneInfo("Asia/Shanghai")
    plan_date = payload.planning_date or datetime.now(sh_tz).date()

    orders = (
        await db.scalars(
            select(Order).where(Order.id.in_(payload.order_ids)).order_by(Order.id.asc())
        )
    ).all()
    if not orders:
        raise HTTPException(404, "未找到可规划订单")
    for o in orders:
        if o.delivery_id is None or int(o.delivery_id) != int(payload.driver_id):
            raise HTTPException(400, f"订单 {o.order_no} 不属于当前配送商，无法纳入规划")
    for o in orders:
        if o.expected_delivery_date is None:
            raise HTTPException(
                400,
                f"订单 {o.order_no} 未设置客户配送日，无法与计划日期 {plan_date.isoformat()} 对齐",
            )
        if o.expected_delivery_date != plan_date:
            raise HTTPException(
                400,
                f"订单 {o.order_no} 的客户配送日为 {o.expected_delivery_date.isoformat()}，"
                f"与当前计划日期 {plan_date.isoformat()} 不一致，请调整计划日期或重新选单",
            )

    svc_map: dict[int, int] = {}
    if payload.service_minutes_by_order:
        for k, v in payload.service_minutes_by_order.items():
            try:
                svc_map[int(k)] = max(5, min(240, int(v)))
            except (TypeError, ValueError):
                continue

    def _service_minutes_for_order(order: Order) -> int:
        oid = int(order.id)
        if oid in svc_map:
            return svc_map[oid]
        od = int(order.service_duration_min or 0)
        if 5 <= od <= 240:
            return od
        return max(5, min(240, int(payload.service_minutes_default)))

    dep_raw_default = (payload.departure_time or "06:00").strip().replace("：", ":")
    dep_by_vn: dict[str, str] = {}
    if payload.departure_time_by_vehicle_no:
        for _k, _v in payload.departure_time_by_vehicle_no.items():
            _kn = str(_k or "").strip()
            if _kn:
                dep_by_vn[_kn] = str(_v or "").strip().replace("：", ":")

    def _departure_sh_from_hhmm(raw: str, *, label: str = "") -> datetime:
        s = (raw or "06:00").strip().replace("：", ":")
        try:
            hparts = s.split(":")
            hh = int(hparts[0])
            mm = int(hparts[1]) if len(hparts) > 1 else 0
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise ValueError
        except (ValueError, IndexError):
            suf = f"（车辆 {label}）" if label else ""
            raise HTTPException(400, f"发车时间格式须为 HH:mm（如 06:30）{suf}，收到：{s!r}")
        return datetime.combine(plan_date, time(hh, mm), tzinfo=sh_tz)

    departure_sh_default = _departure_sh_from_hhmm(dep_raw_default, label="默认")
    departure_utc_default = departure_sh_default.astimezone(timezone.utc)
    restriction_raw = await fetch_beijing_driving_restriction(target_date=plan_date)

    def _dep_raw_for_vehicle_no(vn: str) -> str:
        if vn in dep_by_vn:
            return dep_by_vn[vn]
        for k, val in dep_by_vn.items():
            if str(k).strip().upper() == str(vn).strip().upper():
                return val
        return dep_raw_default

    client_ids = sorted({int(o.client_id) for o in orders if o.client_id})
    client_rows = (
        await db.scalars(
            select(User).where(User.id.in_(client_ids), User.role == "client")
        )
    ).all()
    client_map = {int(c.id): c for c in client_rows}
    no_go_fence_rows = (
        await db.scalars(
            select(DeliveryGeofence).where(
                DeliveryGeofence.delivery_id == int(payload.driver_id),
                DeliveryGeofence.fence_type == "no_go",
                DeliveryGeofence.is_active.is_(True),
            )
        )
    ).all()
    no_go_rings = rings_from_no_go_geofences(no_go_fence_rows)
    avoidpolygons_full_str, avoid_polygon_build_alerts = build_avoidpolygons_param(no_go_rings)
    geofence_strict = str(payload.geofence_policy or "normal") == "strict"
    # 严格模式按路段构造 avoid，禁止全局串参与驾车（见下方 _drive_leg 调用）
    avoidpolygons_str = None if geofence_strict else avoidpolygons_full_str
    vehicles = (
        await db.scalars(
            select(DeliveryVehicle)
            .where(
                DeliveryVehicle.delivery_id == payload.driver_id,
                DeliveryVehicle.status == "active",
            )
            .order_by(DeliveryVehicle.id.asc())
        )
    ).all()

    any_overlap_tail_window = False
    if vehicles:
        for _vv in vehicles:
            _uvn = str(getattr(_vv, "vehicle_no", None) or "").strip()
            if not _uvn:
                continue
            _dsh0 = _departure_sh_from_hhmm(_dep_raw_for_vehicle_no(_uvn), label=_uvn)
            if departure_may_overlap_beijing_tail_restriction(_dsh0):
                any_overlap_tail_window = True
                break

    user_disabled_set: set[str] = set()
    if payload.user_disabled_vehicle_nos:
        for _vn in payload.user_disabled_vehicle_nos:
            s = str(_vn or "").strip()
            if s:
                user_disabled_set.add(s)

    vehicles_excluded_from_planning: list[dict[str, Any]] = []
    vehicles_eligible: list[DeliveryVehicle] = []
    if vehicles:
        for v in vehicles:
            vn = str(getattr(v, "vehicle_no", None) or "").strip()
            if vn and vn in user_disabled_set:
                vehicles_excluded_from_planning.append(
                    {
                        "vehicle_no": v.vehicle_no,
                        "limit_status": "用户禁用",
                        "reason": "您已在路线规划中手动禁用，该车不参与本次智能排线的计算。",
                    }
                )
                continue
            cls = classify_vehicle_limit(v.vehicle_no, restriction=restriction_raw)
            st = str(cls.get("status") or "")
            dep_sh_v = _departure_sh_from_hhmm(_dep_raw_for_vehicle_no(vn), label=vn)
            overlap_v = departure_may_overlap_beijing_tail_restriction(dep_sh_v)
            blocked = overlap_v and st in ROUTE_PLAN_BLOCKED_LIMIT_STATUSES
            if blocked:
                vehicles_excluded_from_planning.append(
                    {
                        "vehicle_no": v.vehicle_no,
                        "limit_status": st,
                        "reason": cls.get("reason") or "",
                    }
                )
            else:
                vehicles_eligible.append(v)
        if not vehicles_eligible:
            reasons = "；".join(f"{x['vehicle_no']}({x['limit_status']})" for x in vehicles_excluded_from_planning[:12])
            raise HTTPException(
                400,
                "当前发车时间位于可能与北京尾号限行时段（北京时间当日 7:00–20:00）重叠的区间，"
                "车队中可用于智能排线的车辆均被限行规则剔除（尾号限行或外地牌默认限行）。"
                f"请调整发车至当日 20:00 之后，或更换车辆/日期。涉及车辆：{reasons}",
            )

    def _haversine_km(a_lng: float, a_lat: float, b_lng: float, b_lat: float) -> float:
        rad = math.pi / 180
        lat1 = a_lat * rad
        lat2 = b_lat * rad
        dlat = lat2 - lat1
        dlng = (b_lng - a_lng) * rad
        x = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
        return 6371 * 2 * math.asin(math.sqrt(max(x, 0)))

    base_lng = float(driver.lng) if driver and driver.lng is not None else 116.397
    base_lat = float(driver.lat) if driver and driver.lat is not None else 39.908
    total_weight_kg = float(sum(float(o.total_weight_kg or 0) for o in orders))
    total_volume_m3 = float(sum(float(o.total_volume_m3 or 0) for o in orders))
    geo_hit_count = 0
    time_window_hit_count = 0
    total_distance_km = 0.0
    total_drive_minutes = 0
    total_service_minutes = 0
    stops: list[dict[str, Any]] = []
    route_path: list[list[float]] = []
    vehicle_routes: list[dict[str, Any]] = []
    vehicle_stop_counter: dict[int, int] = defaultdict(int)

    vehicle_inputs = list(vehicles_eligible) if vehicles_eligible else ([None] if not vehicles else [])
    vehicle_states: list[dict[str, Any]] = []
    departure_effective_by_vehicle: dict[str, str] = {}
    for idx, v in enumerate(vehicle_inputs, 1):
        weight_cap = float(v.capacity_weight_kg or 0) if v else 0.0
        volume_cap = float(v.capacity_volume_m3 or 0) if v else 0.0
        vn_run = str(v.vehicle_no).strip() if v else ""
        dep_raw_v = _dep_raw_for_vehicle_no(vn_run) if v else dep_raw_default
        dep_sh_run = _departure_sh_from_hhmm(dep_raw_v, label=vn_run or f"虚拟-{idx}")
        departure_utc_v = dep_sh_run.astimezone(timezone.utc)
        if vn_run:
            departure_effective_by_vehicle[vn_run] = dep_raw_v
        vehicle_states.append(
            {
                "id": int(v.id) if v else 0,
                "vehicle_no": v.vehicle_no if v else f"虚拟车辆-{idx}",
                "vehicle_model": v.vehicle_model if v else "",
                "driver_name": str(getattr(v, "driver_name", None) or "").strip() if v else "",
                "capacity_weight_kg": weight_cap if weight_cap > 0 else None,
                "capacity_volume_m3": volume_cap if volume_cap > 0 else None,
                "current_lng": base_lng,
                "current_lat": base_lat,
                "planned_time": departure_utc_v,
                "departure_utc_initial": departure_utc_v,
                "total_weight_kg": 0.0,
                "total_volume_m3": 0.0,
                "distance_km": 0.0,
                "drive_minutes": 0,
                "service_minutes": 0,
                "stops": [],
                "route_path": [[round(base_lng, 6), round(base_lat, 6)]],
            }
        )

    order_by_id: dict[int, Order] = {int(o.id): o for o in orders}

    def _planning_sort_key(o: Order) -> tuple:
        _ws, we = _order_client_window_sh(o, plan_date, sh_tz)
        return (
            we,
            str(o.expected_delivery_date or ""),
            str(o.expected_delivery_slot or ""),
            int(o.id),
        )

    ordered_orders = sorted(orders, key=_planning_sort_key)
    for global_idx, order in enumerate(ordered_orders, 1):
        client = client_map.get(int(order.client_id))
        fallback_lng = base_lng + global_idx * 0.009
        fallback_lat = base_lat + global_idx * 0.006
        order_has_geo = order.delivery_lng is not None and order.delivery_lat is not None
        target_lng = float(order.delivery_lng) if order_has_geo else (
            float(client.lng) if client and client.lng is not None else round(fallback_lng, 6)
        )
        target_lat = float(order.delivery_lat) if order_has_geo else (
            float(client.lat) if client and client.lat is not None else round(fallback_lat, 6)
        )
        if order_has_geo or (client and client.lng is not None and client.lat is not None):
            geo_hit_count += 1
        if order.expected_delivery_slot:
            time_window_hit_count += 1

        order_weight = float(order.total_weight_kg or 0)
        order_volume = float(order.total_volume_m3 or 0)
        _win_start, win_end_sh = _order_client_window_sh(order, plan_date, sh_tz)

        # 选择车辆：优先满足客户下单时的「配送日期 + 时段」截止时刻，再兼顾距离与载重
        scored: list[tuple[tuple[float, ...], dict[str, Any]]] = []
        for s in vehicle_states:
            d = _haversine_km(float(s["current_lng"]), float(s["current_lat"]), target_lng, target_lat)
            projected_weight = float(s["total_weight_kg"]) + order_weight
            projected_volume = float(s["total_volume_m3"]) + order_volume
            w_cap = float(s["capacity_weight_kg"] or 0)
            v_cap = float(s["capacity_volume_m3"] or 0)
            overload_penalty = 0.0
            if w_cap > 0 and projected_weight > w_cap:
                overload_penalty += (projected_weight - w_cap) * 4
            if v_cap > 0 and projected_volume > v_cap:
                overload_penalty += (projected_volume - v_cap) * 80
            dist_est = round(
                _haversine_km(
                    float(s["current_lng"]),
                    float(s["current_lat"]),
                    target_lng,
                    target_lat,
                ),
                2,
            )
            drive_est = max(8, int(round(dist_est * 3.2)))
            proj_arrive_raw = s["planned_time"] + timedelta(minutes=drive_est)
            proj_arrive, _ = _clamp_arrive_not_before_window_start(proj_arrive_raw, _win_start)
            late_m = _arrive_late_minutes_vs_window(proj_arrive, win_end_sh)
            ng_pen = no_go_penalty_for_leg(
                float(s["current_lng"]),
                float(s["current_lat"]),
                target_lng,
                target_lat,
                no_go_rings,
            )
            base_geo = d + overload_penalty + len(s["stops"]) * 0.4 + ng_pen
            # 先最小化超窗，再最小化超窗分钟，再停靠数，再地理成本（含禁行直线穿越惩罚）
            sort_key = (
                0.0 if late_m < 1e-6 else 1.0,
                late_m,
                float(len(s["stops"])),
                base_geo,
            )
            scored.append((sort_key, s))
        scored.sort(key=lambda x: x[0])
        selected = scored[0][1]

        distance_km = round(
            _haversine_km(
                float(selected["current_lng"]),
                float(selected["current_lat"]),
                target_lng,
                target_lat,
            ),
            2,
        )
        drive_minutes = max(8, int(round(distance_km * 3.2)))
        service_minutes = _service_minutes_for_order(order)
        arrive_raw = selected["planned_time"] + timedelta(minutes=drive_minutes)
        arrive_at, early_wait_m = _clamp_arrive_not_before_window_start(arrive_raw, _win_start)
        leave_at = arrive_at + timedelta(minutes=service_minutes)
        selected["planned_time"] = leave_at
        arrive_sh = arrive_at.astimezone(sh_tz)
        leave_sh = leave_at.astimezone(sh_tz)
        selected["distance_km"] = float(selected["distance_km"]) + distance_km
        selected["drive_minutes"] = int(selected["drive_minutes"]) + drive_minutes
        selected["service_minutes"] = int(selected["service_minutes"]) + service_minutes
        selected["total_weight_kg"] = float(selected["total_weight_kg"]) + order_weight
        selected["total_volume_m3"] = float(selected["total_volume_m3"]) + order_volume

        total_distance_km += distance_km
        total_drive_minutes += drive_minutes
        total_service_minutes += service_minutes

        vehicle_id = int(selected["id"])
        vehicle_stop_counter[vehicle_id] += 1
        sequence_no = vehicle_stop_counter[vehicle_id]
        slot_disp = (order.expected_delivery_slot or "").strip() or "09:00-10:00（默认1小时）"
        date_disp = str(order.expected_delivery_date or plan_date)
        client_window_label = f"{date_disp} {slot_disp}"
        late_pre = _arrive_late_minutes_vs_window(arrive_at, win_end_sh)

        hit_rules = ["顺路优先", "客户约定送达窗口", "载重约束校验"]
        if not order_has_geo and not (client and client.lng is not None and client.lat is not None):
            hit_rules.append("地址坐标缺失-按估算模式")
        if not order.expected_delivery_slot:
            hit_rules.append("配送时段缺失-已按默认 09:00-10:00（1小时）截止估算")
        if early_wait_m > 1e-3:
            hit_rules.append(f"驶达早于窗口起点约 {early_wait_m:.0f} 分钟，按就地等待至窗内再服务推算")
        if late_pre > 1e-3:
            hit_rules.append(f"首算预计晚于约定窗口约 {late_pre:.0f} 分钟（已尽量换车/分担）")
        if selected.get("capacity_weight_kg") and float(selected["total_weight_kg"]) > float(selected["capacity_weight_kg"]):
            hit_rules.append("载重超阈值-触发调度预警")
        if selected.get("capacity_volume_m3") and float(selected["total_volume_m3"]) > float(selected["capacity_volume_m3"]):
            hit_rules.append("容积超阈值-触发调度预警")

        stop = {
            "sequence": sequence_no,
            "sequence_global": int(global_idx),
            "order_id": int(order.id),
            "order_no": order.order_no,
            "client_name": client.company_name if client and client.company_name else f"客户{order.client_id}",
            "address": order.delivery_address or (client.address if client and client.address else f"示例配送点{global_idx}"),
            "lng": round(target_lng, 6),
            "lat": round(target_lat, 6),
            "planned_arrive_time": arrive_sh.strftime("%H:%M"),
            "planned_leave_time": leave_sh.strftime("%H:%M"),
            "planned_arrive_datetime": arrive_sh.strftime("%Y-%m-%d %H:%M"),
            "planned_leave_datetime": leave_sh.strftime("%Y-%m-%d %H:%M"),
            "distance_from_prev_km": distance_km,
            "travel_minutes": drive_minutes,
            "service_minutes": service_minutes,
            "load_weight_kg": round(order_weight, 3),
            "load_volume_m3": round(order_volume, 4),
            "remain_weight_kg": round(max(0.0, total_weight_kg - float(sum(float(x["load_weight_kg"]) for x in stops)) - order_weight), 3),
            "remain_volume_m3": round(max(0.0, total_volume_m3 - float(sum(float(x["load_volume_m3"]) for x in stops)) - order_volume), 4),
            "time_window": order.expected_delivery_slot or "09:00-10:00（估算·1小时）",
            "client_delivery_window": client_window_label,
            "window_deadline_sh": win_end_sh.strftime("%Y-%m-%d %H:%M"),
            "window_early_wait_minutes": round(early_wait_m, 1),
            "window_violation_minutes": round(late_pre, 1),
            "constraints_hit": hit_rules,
            "vehicle_id": selected["id"] or None,
            "vehicle_no": selected["vehicle_no"],
            "driver_name": str(selected.get("driver_name") or "").strip(),
        }
        stops.append(stop)
        selected["stops"].append(stop)
        selected["route_path"].append([round(target_lng, 6), round(target_lat, 6)])
        selected["current_lng"] = target_lng
        selected["current_lat"] = target_lat

    # 高德驾车路径：更新每段距离/时长、折线与到达时刻（失败则保留 Haversine 估算并标记 fallback）
    sem = asyncio.Semaphore(4)
    amap_leg_ok = 0
    amap_leg_total = 0
    amap_avoid_fallback_legs = 0

    async def _drive_leg(
        o_lng: float,
        o_lat: float,
        d_lng: float,
        d_lat: float,
        *,
        avoid_str: Optional[str],
        retry_no_avoid: bool,
    ):
        async with sem:
            return await fetch_driving_leg(
                o_lng,
                o_lat,
                d_lng,
                d_lat,
                avoidpolygons=avoid_str,
                retry_without_avoid=retry_no_avoid,
            )

    for s in vehicle_states:
        rp = s["route_path"]
        st_list = s["stops"]
        if len(rp) < 2 or not st_list or len(rp) - 1 != len(st_list):
            continue
        tasks = []
        for i in range(len(rp) - 1):
            a, b = rp[i], rp[i + 1]
            o_lng, o_lat = float(a[0]), float(a[1])
            d_lng, d_lat = float(b[0]), float(b[1])
            if geofence_strict:
                leg_rings = rings_for_leg_avoid_strict(no_go_rings, d_lng, d_lat)
                leg_avoid_str, _ = build_avoidpolygons_param(leg_rings)
                tasks.append(
                    _drive_leg(o_lng, o_lat, d_lng, d_lat, avoid_str=leg_avoid_str, retry_no_avoid=False)
                )
            else:
                tasks.append(
                    _drive_leg(
                        o_lng, o_lat, d_lng, d_lat, avoid_str=avoidpolygons_str, retry_no_avoid=True
                    )
                )
        raw_results = await asyncio.gather(*tasks)
        leg_objs: list[DrivingLegResult] = []
        for i, leg_pair in enumerate(raw_results):
            amap_leg_total += 1
            st = st_list[i]
            a, b = rp[i], rp[i + 1]
            res, used_avoid = leg_pair
            if geofence_strict and res is None:
                vn = str(s.get("vehicle_no") or "?")
                seq = int(st.get("sequence") or (i + 1))
                oid = st.get("order_no") or st.get("order_id")
                raise HTTPException(
                    400,
                    f"严格禁行模式：车辆 {vn} 第 {seq} 站（订单 {oid}）未能求得避让路径。"
                    "请检查禁行围栏数量/顶点、高德 Key 与配额，或改用「正常」模式。",
                )
            if avoidpolygons_str and res is not None and not used_avoid:
                amap_avoid_fallback_legs += 1
            if res is not None:
                amap_leg_ok += 1
                dist_km = round(res.distance_m / 1000.0, 2)
                trav_min = max(1, int(round(res.duration_s / 60.0)))
                st["distance_from_prev_km"] = dist_km
                st["travel_minutes"] = trav_min
                st["routing_source"] = "amap"
                if avoidpolygons_str and not used_avoid:
                    ch = list(st.get("constraints_hit") or [])
                    tag = "高德：禁行避让参数未生效或已降级为无避让路径"
                    if tag not in ch:
                        ch.append(tag)
                    st["constraints_hit"] = ch
                leg_objs.append(res)
            else:
                dm = float(st.get("distance_from_prev_km") or 0)
                tm = max(1, int(st.get("travel_minutes") or 1))
                st["routing_source"] = "fallback"
                leg_objs.append(
                    DrivingLegResult(
                        distance_m=max(dm, 0.001) * 1000.0,
                        duration_s=float(tm * 60),
                        points=[(float(a[0]), float(a[1])), (float(b[0]), float(b[1]))],
                    )
                )
        s["route_path"] = merge_leg_polylines(leg_objs)
        planned = s.get("departure_utc_initial") or departure_utc_default
        cum_drive = 0
        for st in st_list:
            planned = planned + timedelta(minutes=int(st["travel_minutes"]))
            arrive_raw = planned
            cum_drive += int(st["travel_minutes"])
            sv = int(st.get("service_minutes") or 0)
            oid = int(st.get("order_id") or 0)
            ord_i = order_by_id.get(oid)
            early_wait_m = 0.0
            arrive_at = arrive_raw
            if ord_i:
                ws_i, we_i = _order_client_window_sh(ord_i, plan_date, sh_tz)
                arrive_at, early_wait_m = _clamp_arrive_not_before_window_start(arrive_raw, ws_i)
            leave_at = arrive_at + timedelta(minutes=sv)
            planned = leave_at
            arrive_sh = arrive_at.astimezone(sh_tz)
            leave_sh = leave_at.astimezone(sh_tz)
            st["planned_arrive_time"] = arrive_sh.strftime("%H:%M")
            st["planned_arrive_datetime"] = arrive_sh.strftime("%Y-%m-%d %H:%M")
            st["planned_leave_time"] = leave_sh.strftime("%H:%M")
            st["planned_leave_datetime"] = leave_sh.strftime("%Y-%m-%d %H:%M")
            st["window_early_wait_minutes"] = round(early_wait_m, 1)
            st["cumulative_drive_minutes"] = cum_drive
            if ord_i:
                _w0, we_i = _order_client_window_sh(ord_i, plan_date, sh_tz)
                late_i = _arrive_late_minutes_vs_window(arrive_at, we_i)
                st["window_violation_minutes"] = round(late_i, 1)
                ch = [x for x in (st.get("constraints_hit") or []) if "驶达早于窗口起点" not in x]
                if early_wait_m > 1e-3:
                    tag = f"高德重算：早于窗口约 {early_wait_m:.0f} 分钟按就地等待至窗内再服务"
                    if not any("高德重算：早于窗口" in x for x in ch):
                        ch.append(tag)
                if late_i > 1e-3:
                    tag = f"高德重算后仍晚于约定窗口约 {late_i:.0f} 分钟"
                    if tag not in ch and not any("晚于约定窗口" in x for x in ch):
                        ch.append(tag)
                else:
                    ch = [x for x in ch if "首算预计晚于" not in x]
                st["constraints_hit"] = ch
        s["distance_km"] = round(sum(float(x.get("distance_from_prev_km") or 0) for x in st_list), 2)
        s["drive_minutes"] = int(sum(int(x.get("travel_minutes") or 0) for x in st_list))
        s["service_minutes"] = int(sum(int(x.get("service_minutes") or 0) for x in st_list))

    total_distance_km = round(sum(float(x.get("distance_from_prev_km") or 0) for x in stops), 2)
    total_drive_minutes = int(sum(int(x.get("travel_minutes") or 0) for x in stops))
    total_service_minutes = int(sum(int(x.get("service_minutes") or 0) for x in stops))
    optimized_distance_km = total_distance_km
    _baseline_dist_uplift = 0.12
    _baseline_dur_uplift = 0.14
    baseline_distance_km = round(optimized_distance_km * (1.0 + _baseline_dist_uplift), 2)
    optimized_duration = total_drive_minutes + total_service_minutes
    baseline_duration = int(round(optimized_duration * (1.0 + _baseline_dur_uplift)))
    distance_saved = round(max(0.0, baseline_distance_km - optimized_distance_km), 2)
    duration_saved = max(0, baseline_duration - optimized_duration)
    route_path = []
    vehicle_routes = []
    for s in vehicle_states:
        if len(s["route_path"]) > 1:
            route_path.extend(s["route_path"])
            vehicle_routes.append(
                {
                    "vehicle_id": s["id"] or None,
                    "vehicle_no": s["vehicle_no"],
                    "vehicle_model": s["vehicle_model"],
                    "driver_name": str(s.get("driver_name") or "").strip(),
                    "capacity_weight_kg": s["capacity_weight_kg"],
                    "capacity_volume_m3": s["capacity_volume_m3"],
                    "route_path": s["route_path"],
                    "stops": s["stops"],
                    "distance_km": round(float(s["distance_km"]), 2),
                    "duration_minutes": int(s["drive_minutes"]) + int(s["service_minutes"]),
                    "load_weight_kg": round(float(s["total_weight_kg"]), 3),
                    "load_volume_m3": round(float(s["total_volume_m3"]), 4),
                }
            )

    weight_cap = float(sum(float(s["capacity_weight_kg"] or 0) for s in vehicle_states))
    volume_cap = float(sum(float(s["capacity_volume_m3"] or 0) for s in vehicle_states))
    weight_usage = round((total_weight_kg / weight_cap), 4) if weight_cap > 0 else None
    volume_usage = round((total_volume_m3 / volume_cap), 4) if volume_cap > 0 else None
    risk_alerts = []
    if weight_usage is not None and weight_usage > 0.95:
        risk_alerts.append("车辆载重利用率超过95%，建议拆分波次")
    if volume_usage is not None and volume_usage > 0.95:
        risk_alerts.append("车辆容积利用率超过95%，存在装载风险")
    if geo_hit_count < len(orders):
        risk_alerts.append("部分订单缺少精确坐标，当前规划包含估算路径")
    if amap_leg_total > 0 and amap_leg_ok < amap_leg_total:
        risk_alerts.append(
            f"部分路段未返回高德驾车结果（{amap_leg_ok}/{amap_leg_total}），已用直线距离与经验车速降级，请检查 Key 或配额"
        )
    late_stops = [x for x in stops if float(x.get("window_violation_minutes") or 0) > 1.0]
    if late_stops:
        risk_alerts.append(
            f"{len(late_stops)} 个停靠点预计到达仍晚于客户下单约定的配送日期/时段截止，可尝试提前发车、加车或与客户端协调改期。"
        )
    for _msg in avoid_polygon_build_alerts:
        if _msg and _msg not in risk_alerts:
            risk_alerts.append(_msg)
    if amap_avoid_fallback_legs > 0:
        risk_alerts.append(
            f"{amap_avoid_fallback_legs} 段驾车路径在启用禁行避让时高德未返回有效路径，已降级为无避让请求。"
        )

    geo_coverage = round(geo_hit_count / len(orders), 4) if orders else 0.0
    routing_mode = (
        "amap_driving"
        if amap_leg_total > 0 and amap_leg_ok == amap_leg_total
        else ("mixed" if amap_leg_ok > 0 else "fallback")
    )

    all_plates_for_limit_ui = [str(v.vehicle_no) for v in vehicles if getattr(v, "vehicle_no", None)]
    vehicle_limit_today = build_vehicle_limit_today(all_plates_for_limit_ui, restriction_raw)
    if user_disabled_set:
        for row in vehicle_limit_today.get("vehicles") or []:
            if str(row.get("vehicle_no") or "").strip() in user_disabled_set:
                row["user_disabled"] = True
    if user_disabled_set:
        risk_alerts.append(
            "已按您的设置将下列车辆排除在本次智能排线之外："
            + "、".join(sorted(user_disabled_set)[:24])
            + ("…" if len(user_disabled_set) > 24 else "")
        )
    tail_excluded = [x for x in vehicles_excluded_from_planning if str(x.get("limit_status") or "") != "用户禁用"]
    if tail_excluded:
        risk_alerts.append(
            "下列车辆未纳入本次智能排线（发车在北京时间当日 20:00 及以前时，剔除尾号限行及外地牌默认限行车辆）："
            + "、".join(x["vehicle_no"] for x in tail_excluded)
        )

    return {
        "driver": driver.company_name or driver.username if driver else f"driver-{payload.driver_id}",
        "driver_id": payload.driver_id,
        "vehicle": {
            "id": int(vehicle_states[0]["id"]) if vehicle_states else None,
            "vehicle_no": vehicle_states[0]["vehicle_no"] if vehicle_states else "未配置车辆",
            "vehicle_model": vehicle_states[0]["vehicle_model"] if vehicle_states else "",
            "capacity_weight_kg": weight_cap if weight_cap > 0 else None,
            "capacity_volume_m3": volume_cap if volume_cap > 0 else None,
        },
        "vehicle_count": len(vehicle_states),
        "vehicles_used_in_plan": len(vehicle_routes),
        "vehicles_available_today": len(vehicle_states),
        "vehicles_active_total": len(vehicles),
        "vehicles_excluded_from_planning": vehicles_excluded_from_planning,
        "vehicle_routes": vehicle_routes,
        "planning_inputs_echo": {
            "planning_date": plan_date.isoformat(),
            "departure_time_local": dep_raw_default,
            "departure_time_by_vehicle_no_request": dict(sorted(dep_by_vn.items())) if dep_by_vn else {},
            "departure_time_by_vehicle_no_effective": dict(sorted(departure_effective_by_vehicle.items())),
            "departure_shanghai": departure_sh_default.isoformat(),
            "departure_utc": departure_utc_default.isoformat(),
            "timezone": "Asia/Shanghai",
            "service_minutes_default": payload.service_minutes_default,
            "service_minutes_by_order_applied": {str(k): v for k, v in sorted(svc_map.items())},
            "beijing_tail_exclusion_applied": any_overlap_tail_window,
            "beijing_tail_exclusion_note": (
                "发车晚于当日北京时间 20:00 时不剔除限行车辆；20:00 及以前发车时剔除「限行」「外地限行」车辆。"
            ),
            "beijing_restriction_rule_date": restriction_raw.get("date"),
            "beijing_restriction_available": restriction_raw.get("available"),
            "user_disabled_vehicle_nos": sorted(user_disabled_set),
            "no_go_fence_active_count": len(no_go_fence_rows),
            "no_go_polygon_rings_used": len(no_go_rings),
            "geofence_policy": payload.geofence_policy,
            "avoidpolygons_supplied": bool(avoidpolygons_full_str)
            if not geofence_strict
            else bool(no_go_rings),
            "avoidpolygons_mode": "per_leg" if geofence_strict else "global",
        },
        "vehicle_limit_today": vehicle_limit_today,
        "total_distance": f"{optimized_distance_km}km",
        "estimated_time": f"{optimized_duration}分钟",
        "total_distance_km": optimized_distance_km,
        "estimated_duration_minutes": optimized_duration,
        "total_weight_kg": round(total_weight_kg, 3),
        "total_volume_m3": round(total_volume_m3, 4),
        "capacity_usage": {
            "weight_ratio": weight_usage,
            "volume_ratio": volume_usage,
            "weight_ratio_text": f"{round(weight_usage * 100, 1)}%" if weight_usage is not None else "未配置",
            "volume_ratio_text": f"{round(volume_usage * 100, 1)}%" if volume_usage is not None else "未配置",
        },
        "optimization_compare": {
            "baseline_distance_km": baseline_distance_km,
            "optimized_distance_km": optimized_distance_km,
            "distance_saved_km": distance_saved,
            "baseline_duration_minutes": baseline_duration,
            "optimized_duration_minutes": optimized_duration,
            "duration_saved_minutes": duration_saved,
            "estimated_on_time_rate": round(max(0.78, min(0.99, 0.88 + geo_coverage * 0.08)), 4),
            "estimated_on_time_rate_note": ESTIMATED_ON_TIME_RATE_NOTE_CN,
            "baseline_model": "synthetic_uplift",
            "baseline_distance_uplift_ratio": round(_baseline_dist_uplift, 4),
            "baseline_duration_uplift_ratio": round(_baseline_dur_uplift, 4),
            "baseline_description": (
                "「对标里程/时长」并非第二套真实路径回放：在「本方案」高德/降级路段累计值之上，"
                f"按可配置行业粗放冗余系数估算（当前里程 +{int(_baseline_dist_uplift * 100)}%、"
                f"总时长 +{int(_baseline_dur_uplift * 100)}%），"
                "用于演示量级；节省量 = 对标值 − 本方案累计。"
            ),
        },
        "data_quality": {
            "mode": "real_geo" if geo_hit_count == len(orders) else "real_mixed_estimation",
            "geo_coverage": geo_coverage,
            "time_window_coverage": round(time_window_hit_count / len(orders), 4) if orders else 0.0,
            "missing_geo_order_count": max(0, len(orders) - geo_hit_count),
            "amap_legs_ok": amap_leg_ok,
            "amap_legs_total": amap_leg_total,
            "routing": routing_mode,
            "geofence_policy": payload.geofence_policy,
        },
        "risk_alerts": risk_alerts,
        "capability_badges": [
            "北斗定位接入",
            "高德驾车路径与ETA",
            "载重容积约束",
            "顺路策略",
            "时窗策略（演示）",
            "禁行区避让（高德+分配惩罚）",
        ],
        "route_path": route_path,
        "stops": stops,
    }


def _geofence_row_dict(g: DeliveryGeofence) -> dict[str, Any]:
    return {
        "id": g.id,
        "delivery_id": g.delivery_id,
        "fence_type": g.fence_type,
        "name": g.name or "",
        "geometry_json": g.geometry_json,
        "center_lng": float(g.center_lng) if g.center_lng is not None else None,
        "center_lat": float(g.center_lat) if g.center_lat is not None else None,
        "radius_m": g.radius_m,
        "client_id": g.client_id,
        "is_active": bool(g.is_active),
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
    }


class GeofenceCreateIn(BaseModel):
    fence_type: str = Field(pattern="^(no_go|staging|receiving)$")
    name: str = Field(default="", max_length=128)
    geometry_json: Optional[dict[str, Any]] = None
    center_lng: Optional[float] = None
    center_lat: Optional[float] = None
    radius_m: int = Field(default=200, ge=50, le=5000)
    client_id: Optional[int] = None


class GeofencePatchIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    geometry_json: Optional[dict[str, Any]] = None
    center_lng: Optional[float] = None
    center_lat: Optional[float] = None
    radius_m: Optional[int] = Field(default=None, ge=50, le=5000)
    is_active: Optional[bool] = None


class GeofenceSeedIn(BaseModel):
    radius_m: int = Field(default=200, ge=50, le=2000)


@router.get("/geofences")
async def list_delivery_geofences(
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.scalars(
            select(DeliveryGeofence)
            .where(DeliveryGeofence.delivery_id == user.id)
            .order_by(DeliveryGeofence.id.desc())
        )
    ).all()
    return [_geofence_row_dict(r) for r in rows]


@router.post("/geofences")
async def create_delivery_geofence(
    payload: GeofenceCreateIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    name = (payload.name or "").strip()
    if payload.fence_type in ("no_go", "staging"):
        ok, err = validate_polygon_geojson(payload.geometry_json)
        if not ok:
            raise HTTPException(400, err)
        row = DeliveryGeofence(
            delivery_id=int(user.id),
            fence_type=payload.fence_type,
            name=name,
            geometry_json=payload.geometry_json,
            center_lng=None,
            center_lat=None,
            radius_m=None,
            client_id=None,
            is_active=True,
        )
    else:
        lng = payload.center_lng
        lat = payload.center_lat
        if lng is None or lat is None:
            raise HTTPException(400, "收货区域须指定 center_lng、center_lat（米制半径默认 200）")
        rad = int(payload.radius_m or 200)
        geom = circle_polygon_geojson(float(lng), float(lat), float(rad))
        row = DeliveryGeofence(
            delivery_id=int(user.id),
            fence_type="receiving",
            name=name,
            geometry_json=geom,
            center_lng=float(lng),
            center_lat=float(lat),
            radius_m=rad,
            client_id=int(payload.client_id) if payload.client_id else None,
            is_active=True,
        )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _geofence_row_dict(row)


@router.put("/geofences/{fence_id}")
async def update_delivery_geofence(
    fence_id: int,
    payload: GeofencePatchIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(DeliveryGeofence, fence_id)
    if not row or int(row.delivery_id) != int(user.id):
        raise HTTPException(404, "围栏不存在或无权限")
    if payload.name is not None:
        row.name = str(payload.name).strip()
    if payload.is_active is not None:
        row.is_active = bool(payload.is_active)
    if row.fence_type in ("no_go", "staging"):
        if payload.geometry_json is not None:
            ok, err = validate_polygon_geojson(payload.geometry_json)
            if not ok:
                raise HTTPException(400, err)
            row.geometry_json = payload.geometry_json
    elif row.fence_type == "receiving":
        if payload.geometry_json is not None and payload.center_lng is None and payload.center_lat is None:
            ok, err = validate_polygon_geojson(payload.geometry_json)
            if not ok:
                raise HTTPException(400, err)
            row.geometry_json = payload.geometry_json
        else:
            lng = payload.center_lng if payload.center_lng is not None else row.center_lng
            lat = payload.center_lat if payload.center_lat is not None else row.center_lat
            rad = payload.radius_m if payload.radius_m is not None else row.radius_m
            if lng is None or lat is None or rad is None:
                raise HTTPException(400, "收货区域更新须提供完整 center 与 radius，或提交 Polygon geometry_json")
            row.center_lng = float(lng)
            row.center_lat = float(lat)
            row.radius_m = int(rad)
            row.geometry_json = circle_polygon_geojson(row.center_lng, row.center_lat, float(rad))
    await db.commit()
    await db.refresh(row)
    return _geofence_row_dict(row)


@router.delete("/geofences/{fence_id}")
async def delete_delivery_geofence(
    fence_id: int,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(DeliveryGeofence, fence_id)
    if not row or int(row.delivery_id) != int(user.id):
        raise HTTPException(404, "围栏不存在或无权限")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.post("/geofences/seed-receiving-from-contracts")
async def seed_receiving_geofences_from_contracts(
    payload: Optional[GeofenceSeedIn] = Body(default=None),
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    """已中标且在合约期内的客户：按客户坐标生成/更新默认收货圆（幂等）。"""
    p = payload or GeofenceSeedIn()
    sh = ZoneInfo("Asia/Shanghai")
    today = datetime.now(sh).date()
    contracts = (
        await db.scalars(
            select(Contract).where(
                Contract.delivery_id == int(user.id),
                Contract.status == "已中标",
                Contract.period_start <= today,
                Contract.period_end >= today,
            )
        )
    ).all()
    skipped: list[dict[str, Any]] = []
    upserted = 0
    rad = int(p.radius_m)
    for c in contracts:
        client = await db.get(User, int(c.client_id))
        if not client:
            skipped.append({"client_id": c.client_id, "reason": "客户不存在"})
            continue
        if client.lng is None or client.lat is None:
            skipped.append(
                {
                    "client_id": int(client.id),
                    "company_name": client.company_name or client.username,
                    "reason": "客户账号未维护经纬度",
                }
            )
            continue
        lng = float(client.lng)
        lat = float(client.lat)
        geom = circle_polygon_geojson(lng, lat, float(rad))
        nm = f"收货区·{client.company_name or client.username}"
        existing = await db.scalar(
            select(DeliveryGeofence).where(
                DeliveryGeofence.delivery_id == int(user.id),
                DeliveryGeofence.fence_type == "receiving",
                DeliveryGeofence.client_id == int(client.id),
            )
        )
        if existing:
            existing.geometry_json = geom
            existing.center_lng = lng
            existing.center_lat = lat
            existing.radius_m = rad
            existing.name = nm
            existing.is_active = True
        else:
            db.add(
                DeliveryGeofence(
                    delivery_id=int(user.id),
                    fence_type="receiving",
                    name=nm,
                    geometry_json=geom,
                    center_lng=lng,
                    center_lat=lat,
                    radius_m=rad,
                    client_id=int(client.id),
                    is_active=True,
                )
            )
        upserted += 1
    await db.commit()
    return {"upserted": upserted, "skipped": skipped, "radius_m": rad}
