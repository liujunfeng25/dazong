from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    BillingStatement,
    ClientCanteen,
    Order,
    OrderItemAllocation,
    OrderReceivingLine,
    OrderReturn,
    OrderReturnLine,
    Product,
    User,
)
from services.order_detail_aggregator import _amount_text, _receiving_line_payload, _return_line_payload
from services.receiving_billing import build_receiving_billing_snapshot
from services.storage.minio_client import normalize_public_image_urls


def _num(value: Any, digits: int = 2) -> float:
    try:
        return round(float(value or 0), digits)
    except (TypeError, ValueError):
        return 0.0


def _reason_label(code: Any) -> str:
    return {"lack": "缺货", "quality": "质量问题", "other": "其他"}.get(
        str(code or "").strip(),
        str(code or "").strip() or "—",
    )


def _return_status_label(status: Any) -> str:
    return {"pending_delivery_review": "待配送商审核", "confirmed": "已确认", "rejected": "已驳回", "draft": "草稿", "cancelled": "已取消"}.get(
        str(status or "").strip(),
        str(status or "").strip() or "—",
    )


async def receiving_difference_summary_map(db: AsyncSession, orders: Iterable[Order]) -> dict[int, dict[str, Any]]:
    order_rows = list(orders)
    order_ids = [int(o.id) for o in order_rows]
    if not order_ids:
        return {}

    returns = (
        await db.scalars(select(OrderReturn).where(OrderReturn.order_id.in_(order_ids), OrderReturn.source == "receive_shortage"))
    ).all()
    return_by_order = {int(r.order_id): r for r in returns}
    return_ids = [int(r.id) for r in returns]
    return_lines_by_return: dict[int, list[OrderReturnLine]] = defaultdict(list)
    if return_ids:
        ret_lines = (
            await db.scalars(select(OrderReturnLine).where(OrderReturnLine.order_return_id.in_(return_ids)))
        ).all()
        for line in ret_lines:
            return_lines_by_return[int(line.order_return_id)].append(line)

    summaries: dict[int, dict[str, Any]] = {}
    for order in order_rows:
        ret = return_by_order.get(int(order.id))
        lines = return_lines_by_return.get(int(ret.id), []) if ret else []
        shortage_kg = sum(float(x.delta_kg or 0) for x in lines)
        deduction_amount = sum(float(x.deduction_amount or 0) for x in lines)
        if ret and lines:
            billing = await build_receiving_billing_snapshot(db, order)
            billing_lines = {int(x.get("line_index") or 0): x for x in (billing.get("lines") or [])}
            recalculated = sum(
                float((billing_lines.get(int(x.line_index)) or {}).get("deduction_amount") or 0)
                for x in lines
            )
            if recalculated > 0:
                deduction_amount = recalculated
            shortage_parts = [
                _amount_text(
                    float((billing_lines.get(int(x.line_index)) or {}).get("diff_qty_signed"))
                    if (billing_lines.get(int(x.line_index)) or {}).get("diff_qty_signed") is not None
                    else -abs(float(x.delta_kg or 0)),
                    str((billing_lines.get(int(x.line_index)) or {}).get("measure_unit") or "kg"),
                )
                for x in lines
            ]
            shortage_text = "、".join(shortage_parts[:2]) + ("等" if len(shortage_parts) > 2 else "")
        else:
            shortage_text = f"-{round(shortage_kg, 3)} kg" if shortage_kg else "0 kg"
        summaries[int(order.id)] = {
            "has_receiving_difference": bool(ret),
            "difference_type": "shortage" if ret else "none",
            "difference_label": "少收退货" if ret else "无差异",
            "return_no": ret.return_no if ret else None,
            "return_status": ret.status if ret else None,
            "return_status_label": _return_status_label(ret.status) if ret else None,
            "shortage_kg": round(shortage_kg, 3),
            "shortage_text": shortage_text,
            "overage_kg": 0,
            "overage_text": "0 kg",
            "deduction_amount": round(deduction_amount, 2),
        }

    recv_rows = (
        await db.scalars(select(OrderReceivingLine).where(OrderReceivingLine.order_id.in_(order_ids)))
    ).all()
    recv_by_order: dict[int, list[OrderReceivingLine]] = defaultdict(list)
    for row in recv_rows:
        recv_by_order[int(row.order_id)].append(row)
    for order in order_rows:
        if int(order.id) in return_by_order:
            continue
        billing = await build_receiving_billing_snapshot(db, order)
        billing_by_line = {int(x.get("line_index") or 0): x for x in (billing.get("lines") or [])}
        overage = 0.0
        overage_parts = []
        for row in recv_by_order.get(int(order.id), []):
            payload = _receiving_line_payload(row, billing_by_line)
            if payload.get("diff_type") == "overage":
                overage += float(payload.get("diff_kg_signed") or 0)
                overage_parts.append(payload.get("diff_label") or f"+{payload.get('diff_kg_signed')} kg")
        if overage > 0:
            summaries[int(order.id)] = {
                "has_receiving_difference": True,
                "difference_type": "overage",
                "difference_label": "多收留痕",
                "return_no": None,
                "return_status": None,
                "return_status_label": None,
                "shortage_kg": 0,
                "shortage_text": "0 kg",
                "overage_kg": round(overage, 3),
                "overage_text": "、".join(overage_parts[:2]) + ("等" if len(overage_parts) > 2 else ""),
                "deduction_amount": 0,
            }
    return summaries


async def list_receiving_shortage_returns(
    db: AsyncSession,
    *,
    role: str,
    user_id: int,
    order_no: Optional[str] = None,
    client_keyword: Optional[str] = None,
    supplier_keyword: Optional[str] = None,
    reason: Optional[str] = None,
    status: Optional[str] = None,
    created_date_start: Optional[Any] = None,
    created_date_end: Optional[Any] = None,
    expected_delivery_date_start: Optional[Any] = None,
    expected_delivery_date_end: Optional[Any] = None,
) -> list[dict[str, Any]]:
    stmt = (
        select(OrderReturn, Order)
        .join(Order, Order.id == OrderReturn.order_id)
        .where(OrderReturn.source == "receive_shortage")
        .order_by(OrderReturn.created_at.desc(), OrderReturn.id.desc())
    )
    if role == "delivery":
        stmt = stmt.where(Order.delivery_id == user_id)
    elif role == "client":
        stmt = stmt.where(Order.client_id == user_id)
    if order_no and order_no.strip():
        stmt = stmt.where(Order.order_no.like(f"%{order_no.strip()}%"))
    if status and status.strip():
        stmt = stmt.where(OrderReturn.status == status.strip())
    if created_date_start:
        stmt = stmt.where(OrderReturn.created_at >= created_date_start)
    if created_date_end:
        stmt = stmt.where(OrderReturn.created_at < created_date_end)
    if expected_delivery_date_start:
        stmt = stmt.where(Order.expected_delivery_date >= expected_delivery_date_start)
    if expected_delivery_date_end:
        stmt = stmt.where(Order.expected_delivery_date <= expected_delivery_date_end)

    pairs = (await db.execute(stmt.limit(500))).all()
    if not pairs:
        return []

    orders = [row[1] for row in pairs]
    order_ids = [int(o.id) for o in orders]
    return_ids = [int(row[0].id) for row in pairs]
    user_ids = sorted({int(o.client_id) for o in orders} | {int(o.delivery_id) for o in orders})
    canteen_ids = sorted({int(o.canteen_id) for o in orders if o.canteen_id is not None})

    users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
    user_map = {int(u.id): (u.company_name or u.username or f"账号#{u.id}") for u in users}
    canteens = (await db.scalars(select(ClientCanteen).where(ClientCanteen.id.in_(canteen_ids)))).all() if canteen_ids else []
    canteen_map = {int(c.id): c.name or "" for c in canteens}

    ret_lines = (
        await db.scalars(select(OrderReturnLine).where(OrderReturnLine.order_return_id.in_(return_ids)))
    ).all()
    lines_by_return: dict[int, list[OrderReturnLine]] = defaultdict(list)
    product_ids = sorted({int(x.product_id) for x in ret_lines if x.product_id is not None})
    products = (await db.scalars(select(Product).where(Product.id.in_(product_ids)))).all() if product_ids else []
    product_map = {int(p.id): p for p in products}
    for line in ret_lines:
        lines_by_return[int(line.order_return_id)].append(line)

    alloc_rows = (
        await db.scalars(select(OrderItemAllocation).where(OrderItemAllocation.order_id.in_(order_ids)))
    ).all()
    supplier_ids = sorted({int(a.supplier_id) for a in alloc_rows})
    supplier_users = (await db.scalars(select(User).where(User.id.in_(supplier_ids)))).all() if supplier_ids else []
    supplier_name_map = {int(u.id): (u.company_name or u.username or f"供货商#{u.id}") for u in supplier_users}
    supplier_by_order_line: dict[tuple[int, int], str] = defaultdict(str)
    for alloc in alloc_rows:
        key = (int(alloc.order_id), int(alloc.line_no or 0))
        name = supplier_name_map.get(int(alloc.supplier_id), f"供货商#{int(alloc.supplier_id)}")
        if supplier_by_order_line[key]:
            if name not in supplier_by_order_line[key]:
                supplier_by_order_line[key] += f"、{name}"
        else:
            supplier_by_order_line[key] = name

    statements = (await db.scalars(select(BillingStatement).order_by(BillingStatement.id.desc()).limit(2000))).all()

    out: list[dict[str, Any]] = []
    for ret, order in pairs:
        billing = await build_receiving_billing_snapshot(db, order)
        billing_lines = {int(x.get("line_index") or 0): x for x in (billing.get("lines") or [])}
        related_statements = []
        for st in statements:
            source = st.source_snapshot_json or {}
            ids = source.get("order_ids") or []
            if int(order.id) in {int(i) for i in ids}:
                related_statements.append(
                    {
                        "statement_id": int(st.id),
                        "statement_no": st.statement_no,
                        "direction": st.direction,
                        "role": st.role,
                        "status": st.status,
                        "amount": float(st.amount or 0),
                    }
                )
        for line in lines_by_return.get(int(ret.id), []):
            product = product_map.get(int(line.product_id or 0))
            if reason and reason.strip() and str(line.reason_code or "") != reason.strip():
                continue
            row_supplier = supplier_by_order_line.get((int(order.id), int(line.line_index)), "")
            if supplier_keyword and supplier_keyword.strip():
                if supplier_keyword.strip() not in row_supplier:
                    continue
            client_name = user_map.get(int(order.client_id), "")
            canteen_name = canteen_map.get(int(order.canteen_id), "") if order.canteen_id is not None else ""
            if client_keyword and client_keyword.strip():
                kw = client_keyword.strip()
                if kw not in client_name and kw not in canteen_name:
                    continue
            payload = _return_line_payload(line)
            line_billing = billing_lines.get(int(line.line_index)) or {}
            unit = str(line_billing.get("measure_unit") or product.unit if product else line_billing.get("measure_unit") or "kg")
            ordered_qty = line_billing.get("ordered_qty", payload.get("ordered_kg"))
            received_qty = line_billing.get("received_qty", payload.get("received_kg"))
            diff_qty = line_billing.get("diff_qty_signed")
            if diff_qty is None:
                diff_qty = -abs(float(payload.get("delta_kg") or 0))
            line_deduction = _num(line_billing.get("deduction_amount"))
            if not line_billing and line_deduction <= 0:
                line_deduction = _num(payload.get("deduction_amount"))
            out.append(
                {
                    "id": f"{int(ret.id)}-{int(line.id)}",
                    "return_id": int(ret.id),
                    "return_no": ret.return_no,
                    "return_status": ret.status,
                    "return_status_label": _return_status_label(ret.status),
                    "reviewed_at": ret.reviewed_at.isoformat() if getattr(ret, "reviewed_at", None) else None,
                    "review_note": getattr(ret, "review_note", None),
                    "order_id": int(order.id),
                    "order_no": order.order_no,
                    "client_name": client_name,
                    "canteen_name": canteen_name,
                    "delivery_name": user_map.get(int(order.delivery_id), ""),
                    "product_name": payload.get("product_name"),
                    "spec": product.spec if product else "",
                    "unit": product.unit if product else "",
                    "measure_unit": unit,
                    "is_standard": bool(line_billing.get("is_standard")),
                    "ordered_kg": ordered_qty,
                    "received_kg": received_qty,
                    "shortage_kg": abs(float(diff_qty or 0)),
                    "ordered_qty": ordered_qty,
                    "received_qty": received_qty,
                    "shortage_qty": abs(float(diff_qty or 0)),
                    "ordered_text": _amount_text(ordered_qty, unit),
                    "received_text": _amount_text(received_qty, unit),
                    "shortage_text": _amount_text(diff_qty, unit),
                    "diff_label": _amount_text(diff_qty, unit),
                    "deduction_amount": line_deduction,
                    "reason_code": payload.get("reason_code"),
                    "reason_label": _reason_label(payload.get("reason_code")),
                    "reason_detail": payload.get("reason_detail"),
                    "photo_urls": normalize_public_image_urls(payload.get("photo_urls") or []),
                    "confirmed_at": ret.created_at.isoformat() if ret.created_at else None,
                    "created_at": ret.created_at.isoformat() if ret.created_at else None,
                    "billing": {
                        "ordered_amount": _num(billing.get("ordered_amount")),
                        "received_amount": _num(billing.get("received_amount")),
                        "deduction_amount": _num(billing.get("deduction_amount")),
                    },
                    "related_statements": related_statements[:8],
                    "supplier_name": row_supplier,
                }
            )
    return out
