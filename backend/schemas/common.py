from datetime import datetime
from typing import Generic, TypeVar
from typing import Optional

from pydantic import BaseModel

T = TypeVar("T")


class MessageResponse(BaseModel):
    message: str = "ok"


class PaginationParams(BaseModel):
    page: int = 1
    page_size: int = 20


class PageResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class BusinessError(BaseModel):
    code: str
    message: str
    detail: Optional[str] = None
    timestamp: datetime
