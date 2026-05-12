from sqlalchemy.ext.asyncio import AsyncSession

from models import OutboxEvent
from services.ws_manager import ws_manager


async def add_outbox_event(db: AsyncSession, event_type: str, payload: dict, channel: str = "monitor"):
    db.add(
        OutboxEvent(
            event_type=event_type,
            channel=channel,
            payload_json=payload,
            processed=False,
        )
    )


async def dispatch_monitor_event(event_type: str, payload: dict):
    await ws_manager.broadcast_monitor({"type": event_type, "data": payload})
