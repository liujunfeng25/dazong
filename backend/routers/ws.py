import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from config import settings
from database import SessionLocal
from dependencies import decode_access_token
from models import Alert, Delivery, IoTData, Order
from services.ws_manager import ws_manager

router = APIRouter(tags=["ws"])


async def _validate_ws_token(websocket: WebSocket, role: Optional[str] = None):
    token = websocket.query_params.get("token", "")
    if not token:
        await websocket.close(code=1008)
        return None
    payload = decode_access_token(token)
    if role and payload.get("role") != role:
        await websocket.close(code=1008)
        return None
    return payload


async def _monitor_snapshot():
    async with SessionLocal() as db:
        today = datetime.utcnow().date()
        orders = (await db.scalars(select(Order))).all()
        today_orders = [o for o in orders if o.created_at.date() == today]
        gmv = float(sum(float(o.total_amount) for o in today_orders))
        active_vehicles = len((await db.scalars(select(Delivery).where(Delivery.status == "运输中"))).all())
        pending_alerts = len((await db.scalars(select(Alert).where(Alert.status == "open"))).all())
        latest_alerts = (
            await db.scalars(select(Alert).order_by(Alert.id.desc()).limit(10))
        ).all()
        latest_sensor = await db.scalar(
            select(IoTData).where(IoTData.device_type == "sensor").order_by(IoTData.id.desc())
        )
        sensor_payload = (latest_sensor.payload_json if latest_sensor else {}) or {}
        return {
            "kpi": {
                "today_orders": len(today_orders),
                "today_gmv": gmv,
                "active_vehicles": active_vehicles,
                "pending_alerts": pending_alerts,
            },
            "alerts": latest_alerts,
            "sensor": {
                "temperature": sensor_payload.get("temperature", 0),
                "humidity": sensor_payload.get("humidity", 0),
                "warning": False,
            },
        }


async def _vehicle_positions():
    async with SessionLocal() as db:
        gps_rows = (
            await db.scalars(
                select(IoTData)
                .where(IoTData.device_type == "gps")
                .order_by(IoTData.id.desc())
                .limit(30)
            )
        ).all()
        dedup = {}
        for row in gps_rows:
            if row.device_id in dedup:
                continue
            payload = row.payload_json or {}
            dedup[row.device_id] = {
                "vehicle_no": row.device_id,
                "lat": payload.get("lat"),
                "lng": payload.get("lng"),
                "order_id": payload.get("order_id"),
                "driver": payload.get("driver", "未知"),
            }
        return list(dedup.values())


@router.websocket("/ws/monitor")
async def ws_monitor(websocket: WebSocket):
    auth = await _validate_ws_token(websocket, "monitor")
    if not auth:
        return
    await ws_manager.connect_monitor(websocket)
    try:
        snapshot = await _monitor_snapshot()
        await websocket.send_json({"type": "snapshot", "data": snapshot})
        sec = 0
        while True:
            if sec % settings.ws_monitor_kpi_interval_seconds == 0:
                snap = await _monitor_snapshot()
                await websocket.send_json({"type": "kpi_tick", "data": snap["kpi"]})
            if sec % settings.ws_monitor_vehicle_interval_seconds == 0:
                vehicles = await _vehicle_positions()
                await websocket.send_json({"type": "vehicle_move", "data": vehicles})
            await asyncio.sleep(1)
            sec += 1
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception:  # noqa: BLE001
        await ws_manager.disconnect(websocket)


@router.websocket("/ws/notifications/{role}")
async def ws_role_notifications(websocket: WebSocket, role: str):
    auth = await _validate_ws_token(websocket, role)
    if not auth:
        return
    user_id = int(auth.get("sub") or 0)
    if user_id <= 0:
        await websocket.close(code=1008)
        return
    await ws_manager.connect_role(role, user_id, websocket)
    try:
        await websocket.send_json({"type": "connected", "role": role})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception:  # noqa: BLE001
        await ws_manager.disconnect(websocket)
