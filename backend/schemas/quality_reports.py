from datetime import datetime

from pydantic import BaseModel


class QualityReportOut(BaseModel):
    id: int
    supplier_id: int
    product_id: int
    order_id: int
    allocation_id: int | None = None
    file_url: str
    report_no: str
    status: str
    created_at: datetime
