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
    canteen_id: Optional[int] = None
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
    period_label: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    close_at: Optional[str] = None
    confirm_due_date: Optional[str] = None
    payment_due_date: Optional[str] = None
    cycle_type: Optional[str] = None
    cycle_type_label: Optional[str] = None
    close_day: Optional[int] = None
    unsettled_amount: Optional[float] = None
    overdue_confirm: bool = False
    overdue_payment: bool = False


class BillingCycleCreateIn(BaseModel):
    relation_type: str = Field(default="client_delivery", pattern="^(client_delivery|delivery_supplier)$")
    role: Optional[str] = Field(default=None, pattern="^(client|delivery|supplier|factory)$")
    scope_type: str = Field(default="canteen")
    scope_ref_id: int = 0
    cycle_type: str = Field(default="monthly", pattern="^(daily|weekly|monthly)$")
    close_day: int = Field(default=1, ge=1, le=28)
    confirm_due_days: int = Field(default=3, ge=1, le=90)
    payment_due_days: int = Field(default=7, ge=1, le=180)


class BillingCycleUpdateIn(BaseModel):
    cycle_type: Optional[str] = Field(default=None, pattern="^(daily|weekly|monthly)$")
    close_day: Optional[int] = Field(default=None, ge=1, le=28)
    confirm_due_days: Optional[int] = Field(default=None, ge=1, le=90)
    payment_due_days: Optional[int] = Field(default=None, ge=1, le=180)
    is_active: Optional[bool] = None


class TargetedCycleCreateIn(BaseModel):
    """运营端预配置定向账期规则：client_delivery 按 学校×食堂×配送商，delivery_supplier 按 配送商×供货商/厂家。"""

    relation_type: str = Field(pattern="^(client_delivery|delivery_supplier)$")
    owner_user_id: int = Field(gt=0)
    counterparty_user_id: int = Field(gt=0)
    canteen_id: Optional[int] = Field(default=None, gt=0)
    cycle_type: str = Field(default="monthly", pattern="^(daily|weekly|monthly)$")
    close_day: int = Field(default=1, ge=1, le=28)
    confirm_due_days: int = Field(default=3, ge=1, le=90)
    payment_due_days: int = Field(default=7, ge=1, le=180)


class TargetedCycleUpdateIn(BaseModel):
    cycle_type: Optional[str] = Field(default=None, pattern="^(daily|weekly|monthly)$")
    close_day: Optional[int] = Field(default=None, ge=1, le=28)
    confirm_due_days: Optional[int] = Field(default=None, ge=1, le=90)
    payment_due_days: Optional[int] = Field(default=None, ge=1, le=180)


class BillingStatementConfirmIn(BaseModel):
    remark: str = ""


class BillingStatementSettleIn(BaseModel):
    amount: Decimal = Field(..., gt=0)
    remark: str = ""
