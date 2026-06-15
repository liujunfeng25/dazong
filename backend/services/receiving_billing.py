from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Order, OrderItemAllocation, OrderReceivingLine, OrderReturn


def _money(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _ordered_qty_kg(order: Order, line_index: int) -> Decimal:
    items = order.items_json or []
    snaps = order.items_snapshot_json or []
    if line_index < 1 or line_index > len(items):
        return Decimal("0")
    item = items[line_index - 1] or {}
    snap = snaps[line_index - 1] if line_index - 1 < len(snaps) else {}
    qty = Decimal(str(item.get("quantity") or 0))
    unit = str((snap or {}).get("unit") or item.get("unit") or "kg").strip().lower()
    if "斤" in unit:
        return qty * Decimal("0.5")
    return qty


def _is_standard_line(order: Order, line_index: int) -> bool:
    snaps = order.items_snapshot_json or []
    if line_index < 1 or line_index > len(snaps):
        return False
    snap = snaps[line_index - 1] or {}
    return str(snap.get("standard_type") or "") == "standard"


def _line_unit(order: Order, line_index: int) -> str:
    items = order.items_json or []
    snaps = order.items_snapshot_json or []
    item = items[line_index - 1] if 0 < line_index <= len(items) else {}
    snap = snaps[line_index - 1] if 0 < line_index <= len(snaps) else {}
    return str((snap or {}).get("unit") or (item or {}).get("unit") or "kg").strip() or "kg"


def _unit_weight_kg(order: Order, line_index: int) -> Decimal:
    snaps = order.items_snapshot_json or []
    snap = snaps[line_index - 1] if 0 < line_index <= len(snaps) else {}
    try:
        return Decimal(str((snap or {}).get("unit_weight_kg") or 0))
    except Exception:
        return Decimal("0")


async def build_receiving_billing_snapshot(
    db: AsyncSession,
    order: Order,
    *,
    enforce_return_status: bool = True,
) -> dict[str, Any]:
    """统一实收计费快照。

    收货称重行存在时按实收比例折减；超收不增加应收应付。
    若少收退货单处于配送商待审/驳回状态，明细仍展示实际差异，但计费不提前扣减。
    没有称重行时兼容旧流程，仍按原订单金额。
    """
    items = order.items_json or []
    raw_recv_rows = (
        await db.scalars(
            select(OrderReceivingLine)
            .where(OrderReceivingLine.order_id == int(order.id))
            .order_by(OrderReceivingLine.line_index.asc())
        )
    ).all()
    recv_rows = [r for r in raw_recv_rows if hasattr(r, "line_index")]
    recv_by_line = {int(r.line_index): r for r in recv_rows}
    has_receiving = bool(recv_rows)
    ret = None
    if enforce_return_status and has_receiving:
        ret = await db.scalar(
            select(OrderReturn).where(OrderReturn.order_id == int(order.id), OrderReturn.source == "receive_shortage")
        )
    return_blocks_deduction = bool(ret is not None and str(ret.status) != "confirmed")

    line_ratios: dict[int, Decimal] = {}
    lines: list[dict[str, Any]] = []
    ordered_amount_total = Decimal("0.00")
    received_amount_total = Decimal("0.00")
    deduction_total = Decimal("0.00")
    received_kg_total = Decimal("0")

    snaps = order.items_snapshot_json or []
    for idx, item in enumerate(items, 1):
        qty = Decimal(str((item or {}).get("quantity") or 0))
        unit_price = Decimal(str((item or {}).get("unit_price") or 0))
        ordered_amount = _money(qty * unit_price)
        ordered_amount_total += ordered_amount

        snap = snaps[idx - 1] if 0 < idx <= len(snaps) else {}
        product_name = str((snap or {}).get("product_name") or (item or {}).get("product_name") or (item or {}).get("name") or f"商品#{idx}")
        product_spec = str((snap or {}).get("spec") or (item or {}).get("spec") or "")

        is_standard = _is_standard_line(order, idx)
        unit = _line_unit(order, idx)
        unit_weight_kg = _unit_weight_kg(order, idx)
        ordered_kg = _ordered_qty_kg(order, idx)
        rr = recv_by_line.get(idx)
        if is_standard:
            ordered_measure = qty
            if rr and rr.confirmed_quantity is not None:
                received_measure = Decimal(str(rr.confirmed_quantity))
            elif rr and rr.confirmed_kg is not None and unit_weight_kg > 0:
                received_measure = Decimal(str(rr.confirmed_kg)) / unit_weight_kg
            elif rr and rr.sample_kg is not None and unit_weight_kg > 0:
                received_measure = Decimal(str(rr.sample_kg)) / unit_weight_kg
            else:
                received_measure = ordered_measure
            received_kg_for_total = (
                Decimal(str(rr.sample_kg))
                if rr and rr.sample_kg is not None
                else Decimal(str(rr.confirmed_kg))
                if rr and rr.confirmed_kg is not None
                else received_measure * unit_weight_kg
                if unit_weight_kg > 0
                else Decimal("0")
            )
        else:
            ordered_measure = ordered_kg
            received_measure = Decimal(str(rr.confirmed_kg)) if rr and rr.confirmed_kg is not None else ordered_measure
            received_kg_for_total = received_measure
        if not has_receiving:
            received_measure = ordered_measure
            received_kg_for_total = ordered_kg
        billing_measure = received_measure
        if return_blocks_deduction and rr and rr.shortage_reason_code:
            billing_measure = ordered_measure
        if ordered_measure > 0:
            ratio = max(Decimal("0"), min(Decimal("1"), billing_measure / ordered_measure))
        else:
            ratio = Decimal("1")
        line_ratios[idx] = ratio
        received_amount = _money(ordered_amount * ratio)
        deduction = _money(ordered_amount - received_amount)
        received_amount_total += received_amount
        deduction_total += deduction
        received_kg_total += max(Decimal("0"), received_kg_for_total)
        diff_measure = received_measure - ordered_measure
        display_unit = unit if is_standard else "kg"
        lines.append(
            {
                "line_index": idx,
                "product_name": product_name,
                "spec": product_spec,
                "unit_price": float(unit_price),
                "is_standard": bool(is_standard),
                "measure_unit": display_unit,
                "ordered_kg": float(ordered_measure),
                "received_kg": float(received_measure),
                "ordered_qty": float(ordered_measure),
                "received_qty": float(received_measure),
                "diff_qty_signed": float(diff_measure),
                "bill_ratio": float(ratio),
                "ordered_amount": float(ordered_amount),
                "received_amount": float(received_amount),
                "deduction_amount": float(deduction),
                "return_billing_blocked": bool(return_blocks_deduction and rr and rr.shortage_reason_code),
            }
        )

    allocation_rows = (
        await db.execute(
            select(
                OrderItemAllocation.id,
                OrderItemAllocation.supplier_id,
                OrderItemAllocation.line_no,
                OrderItemAllocation.product_id,
                OrderItemAllocation.quantity,
                OrderItemAllocation.unit_price,
            ).where(
                OrderItemAllocation.order_id == int(order.id),
                OrderItemAllocation.delivery_id == int(order.delivery_id),
            )
        )
    ).all()
    allocation_amounts: dict[int, Decimal] = {}
    allocation_ratios: dict[int, Decimal] = {}
    for row in allocation_rows:
        amount = _money(Decimal(str(row.quantity or 0)) * Decimal(str(row.unit_price or 0)))
        ratio = line_ratios.get(int(row.line_no or 0), Decimal("1"))
        allocation_amounts[int(row.id)] = _money(amount * ratio)
        allocation_ratios[int(row.id)] = ratio

    return {
        "has_receiving": has_receiving,
        "ordered_amount": float(ordered_amount_total),
        "received_amount": float(_money(received_amount_total)),
        "deduction_amount": float(_money(deduction_total)),
        "received_kg": float(received_kg_total),
        "lines": lines,
        "allocation_amounts": {str(k): float(v) for k, v in allocation_amounts.items()},
        "allocation_ratios": {str(k): float(v) for k, v in allocation_ratios.items()},
        "return_billing_blocked": bool(return_blocks_deduction),
    }
