from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models import AuditLog


async def write_audit_log(
    db: AsyncSession,
    actor_user_id: int,
    action: str,
    object_type: str,
    object_id: int,
    detail: str,
    category: str = "system",
    source_ip: str = "",
    before_json: Optional[dict] = None,
    after_json: Optional[dict] = None,
    trace_id: str = "",
):
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            category=category,
            object_type=object_type,
            object_id=object_id,
            detail=detail,
            source_ip=source_ip,
            before_json=before_json or {},
            after_json=after_json or {},
            trace_id=trace_id,
        )
    )
