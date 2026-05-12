import asyncio
import random
from datetime import datetime

from config import settings
from database import SessionLocal
from models import Alert, IoTData, Order
from services.event_bus import publish_monitor_event
from sqlalchemy import select


class IoTSimulator:
    def __init__(self):
        self._running = True
        self._vehicle_state = {
            "京A12345": {"lat": 39.90, "lng": 116.35, "direction": 90, "speed": 35},
            "京B67890": {"lat": 39.94, "lng": 116.42, "direction": 120, "speed": 42},
        }
        self._last_alert_ts = 0

    async def stop(self):
        self._running = False

    async def run_gps(self):
        while self._running:
            async with SessionLocal() as db:
                active_order = await db.scalar(
                    select(Order).where(Order.status.in_(["发货", "收货"])).order_by(Order.id.desc())
                )
                for plate, pos in self._vehicle_state.items():
                    pos["lat"] += random.uniform(-0.003, 0.003)
                    pos["lng"] += random.uniform(-0.003, 0.003)
                    pos["direction"] = (pos["direction"] + random.uniform(-10, 10)) % 360
                    pos["lat"] = max(39.7, min(40.2, pos["lat"]))
                    pos["lng"] = max(116.0, min(116.8, pos["lng"]))
                    pos["speed"] = max(10, min(65, pos["speed"] + random.uniform(-3, 3)))
                    payload = {
                        "lat": round(pos["lat"], 6),
                        "lng": round(pos["lng"], 6),
                        "speed": round(pos["speed"], 2),
                        "direction": pos["direction"],
                        "order_id": active_order.id if active_order else None,
                        "driver": "张师傅",
                    }
                    db.add(
                        IoTData(
                            device_type="gps",
                            device_id=plate,
                            payload_json=payload,
                            recorded_at=datetime.utcnow(),
                        )
                    )
                await db.commit()
            await asyncio.sleep(settings.simulator_gps_interval_seconds)

    async def run_sensor(self):
        while self._running:
            now = datetime.utcnow().timestamp()
            async with SessionLocal() as db:
                temp = round(random.uniform(2, 8), 2)
                hum = round(random.uniform(40, 70), 2)
                if (
                    now - self._last_alert_ts >= settings.simulator_sensor_alert_cycle_seconds
                    and random.random() > 0.6
                ):
                    temp = round(random.uniform(10.2, 13.5), 2)
                    hum = round(random.uniform(76, 84), 2)
                    self._last_alert_ts = now
                    alert = Alert(
                        level="high",
                        type="sensor",
                        description=f"仓库温湿度异常: T={temp}, H={hum}",
                        status="open",
                        payload_json={"device_id": "WH-001", "temperature": temp, "humidity": hum},
                        created_at=datetime.utcnow(),
                    )
                    db.add(alert)
                    await db.flush()
                    await publish_monitor_event(
                        "new_alert",
                        {
                            "id": alert.id,
                            "level": alert.level,
                            "type": alert.type,
                            "description": alert.description,
                            "created_at": alert.created_at.isoformat(),
                        },
                    )
                    await publish_monitor_event(
                        "sensor_warning",
                        {"device_id": "WH-001", "temperature": temp, "humidity": hum},
                    )

                db.add(
                    IoTData(
                        device_type="sensor",
                        device_id="WH-001",
                        payload_json={"temperature": temp, "humidity": hum},
                        recorded_at=datetime.utcnow(),
                    )
                )
                await db.commit()
            await asyncio.sleep(settings.simulator_sensor_interval_seconds)

    async def run(self):
        await asyncio.gather(self.run_gps(), self.run_sensor())
