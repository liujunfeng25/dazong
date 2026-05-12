from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class BillingCycleOut(BaseModel):
    id: int
    cycle_code: str
    role: str
    owner_user_id: int
    scope_type: str
    scope_ref_id: int
    cycle_type: str
    start_date: date
    end_date: date
    close_day: int
    confirm_due_days: int
    payment_due_days: int
    is_active: bool
    is_confirmed: bool
    created_at: datetime
    relation_type: Optional[str] = None
    display_title: Optional[str] = None
    relation_description: Optional[str] = None
    scope_label: Optional[str] = None


class BillingStatementOut(BaseModel):
    id: int
    statement_no: str
    cycle_id: int
    role: str
    owner_user_id: int
    counterparty_user_id: int
    direction: str
    status: str
    amount: Decimal
    confirmed_amount: Decimal
    settled_amount: Decimal
    item_count: int
    source_snapshot_json: dict
    cycle_snapshot_json: dict
    remark: str
    confirmed_at: Optional[datetime]
    due_at: Optional[datetime]
    created_at: datetime
    counterparty_name: Optional[str] = None
    counterparty_role: Optional[str] = None
    display_title: Optional[str] = None
    action_hint: Optional[str] = None
    order_numbers: list[str] = []


class BillingCycleCreateIn(BaseModel):
    relation_type: str = Field(default="client_delivery", pattern="^(client_delivery|delivery_supplier)$")
    role: Optional[str] = Field(default=None, pattern="^(client|delivery|supplier|factory)$")
    scope_type: str = Field(default="canteen")
    scope_ref_id: int = 0
    cycle_type: str = Field(default="monthly", pattern="^(daily|weekly|monthly)$")
    close_day: int = Field(default=1, ge=1, le=31)
    confirm_due_days: int = Field(default=3, ge=1, le=90)
    payment_due_days: int = Field(default=7, ge=1, le=180)


class BillingCycleUpdateIn(BaseModel):
    cycle_type: Optional[str] = Field(default=None, pattern="^(daily|weekly|monthly)$")
    close_day: Optional[int] = Field(default=None, ge=1, le=31)
    confirm_due_days: Optional[int] = Field(default=None, ge=1, le=90)
    payment_due_days: Optional[int] = Field(default=None, ge=1, le=180)
    is_active: Optional[bool] = None


class BillingStatementConfirmIn(BaseModel):
    remark: str = ""


class BillingStatementSettleIn(BaseModel):
    amount: Decimal = Field(..., gt=0)
    remark: str = ""
