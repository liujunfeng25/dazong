import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_role
from models import Product

router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceParseIn(BaseModel):
    text: str


def _cn_to_int(token: str) -> int:
    if token.isdigit():
        return int(token)
    if token == "十":
        return 10
    if token.endswith("十"):
        lead = token[:-1]
        lead_val = int(lead) if lead.isdigit() else _map_digit(lead)
        return max(lead_val, 1) * 10
    if "十" in token:
        left, right = token.split("十", 1)
        left_val = _map_digit(left) if left else 1
        right_val = _map_digit(right) if right else 0
        return left_val * 10 + right_val
    if token.endswith("百"):
        lead = token[:-1]
        lead_val = int(lead) if lead.isdigit() else _map_digit(lead)
        return max(lead_val, 1) * 100
    if "百" in token:
        left, right = token.split("百", 1)
        left_val = _map_digit(left) if left else 1
        right_val = _cn_to_int(right) if right else 0
        return left_val * 100 + right_val
    return _map_digit(token)


def _map_digit(s: str) -> int:
    mapping = {
        "零": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    return mapping.get(s, 0)


def _match_product_name(raw_name: str, products: list[Product]) -> str:
    for p in products:
        if raw_name in p.name or p.name in raw_name:
            return p.name
    return raw_name


@router.post("/parse-order")
async def parse_order_by_voice(
    payload: VoiceParseIn,
    _=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    text = payload.text or ""
    products = (await db.scalars(select(Product).where(Product.status == "active"))).all()
    pattern = re.compile(
        r"([0-9一二两三四五六七八九十百]+)\s*(斤|公斤|箱|袋|个)?\s*([\u4e00-\u9fa5A-Za-z0-9]+?)(?=和|,|，|。|$)"
    )
    recognized_items = []
    for qty_token, unit_token, name_token in pattern.findall(text):
        quantity = _cn_to_int(qty_token)
        if quantity <= 0:
            continue
        matched_name = _match_product_name(name_token.strip(), products)
        recognized_items.append(
            {
                "product_name": matched_name,
                "quantity": quantity,
                "unit": unit_token or "斤",
            }
        )
    return {
        "success": bool(recognized_items),
        "recognized_items": recognized_items,
        "confidence": 0.9 if recognized_items else 0.2,
    }
