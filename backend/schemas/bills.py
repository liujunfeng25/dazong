from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class BillOut(BaseModel):
    id: int
    order_id: int
    role: str
    amount: Decimal
    order_snapshot_json: dict
    bill_type: str
    status: str
    created_at: datetime
