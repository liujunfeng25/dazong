"""订单详情聚合（运营 / 客户端 / 配送商同口径字段）。

供 operation_order_detail 与 GET /orders/{id}（client/delivery）共用。"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    Category,
    Contract,
    Delivery,
    Order,
    OrderItemAllocation,
    OrderReceivingLine,
    OrderReturn,
    OrderReturnLine,
    OrderStatusLog,
    Product,
    QualityReport,
    Ticket,
    User,
)
from services.order_quality_missing import missing_quality_allocations
from services.ticket_service import complaint_ticket_public_dict

ORDER_STATUS_FLOW = ["下单", "配货", "发货", "收货", "收货确认", "已结算"]


def user_brief(user: Optional[User]) -> dict:
    if not user:
        return {}
    return {
        "id": int(user.id),
        "username": user.username,
        "company_name": user.company_name,
        "contact_phone": user.contact_phone,
        "address": user.address,
        "lng": float(user.lng) if user.lng is not None else None,
        "lat": float(user.lat) if user.lat is not None else None,
        "role": user.role,
    }


def calc_order_float_rate(
    order: Order,
    *,
    product_ref_by_id: Optional[dict[int, float]] = None,
) -> Optional[float]:
    """实付相对指导价：实际成交额/指导价基准额−1（用于 order_realized_float_rate；指导价优先快照，否则商品表，再否则由成交价与快照品类上浮反推）。"""
    items = order.items_json or []
    snaps = order.items_snapshot_json or []
    if not items:
        return None
    ref_map = product_ref_by_id or {}
    reference_total = 0.0
    actual_total = 0.0
    for idx, item in enumerate(items):
        snap = snaps[idx] if idx < len(snaps) and isinstance(snaps[idx], dict) else {}
        pid = int((item or {}).get("product_id") or snap.get("product_id") or 0)
        qty = float((item or {}).get("quantity") or snap.get("order_quantity") or 0)
        actual_unit_price = float((item or {}).get("unit_price") or snap.get("order_unit_price") or 0)
        reference_unit = float((snap or {}).get("reference_price") or 0)
        if reference_unit <= 0 and pid in ref_map:
            reference_unit = float(ref_map[pid])
        if reference_unit <= 0 and actual_unit_price > 0:
            r = float((snap or {}).get("category_float_rate") or 0)
            if r > -0.999999:
                reference_unit = actual_unit_price / (1.0 + r)
        if qty <= 0:
            continue
        actual_total += qty * actual_unit_price
        reference_total += qty * reference_unit
    if reference_total <= 0:
        return None
    return round(actual_total / reference_total - 1, 6)


def _contract_category_rate_map(contract: Contract) -> tuple[dict[int, float], float]:
    """与下单侧一致：品类 id -> 上浮率；fallback 为合约整单上浮率。"""
    rate_map: dict[int, float] = {}
    for i in contract.category_rates_json or []:
        if i.get("category_id") is not None:
            try:
                rate_map[int(i["category_id"])] = float(i.get("float_rate", 0))
            except (TypeError, ValueError):
                continue
    return rate_map, float(contract.price_float_rate or 0)


def amount_weighted_contract_float_rate(
    order: Order,
    rate_map: dict[int, float],
    fallback_rate: float,
    product_meta_map: Optional[dict[int, dict]] = None,
) -> Optional[float]:
    """合约口径该单上浮：Σ(行金额×该行一级品类在合约中的上浮率)/Σ行金额；行金额=qty×单价（单价优先 items_json）。"""
    items = order.items_json or []
    snaps = order.items_snapshot_json or []
    if not items:
        return None
    meta = product_meta_map or {}
    total_amt = 0.0
    weighted = 0.0
    for idx, item in enumerate(items):
        snap = snaps[idx] if idx < len(snaps) and isinstance(snaps[idx], dict) else {}
        pid = int((item or {}).get("product_id") or snap.get("product_id") or 0)
        qty = float((item or {}).get("quantity") or snap.get("order_quantity") or 0)
        raw_up = (item or {}).get("unit_price")
        if raw_up is None or raw_up == "":
            raw_up = snap.get("order_unit_price", 0)
        try:
            up = float(raw_up or 0)
        except (TypeError, ValueError):
            up = 0.0
        amt = qty * up
        if amt <= 0 and qty > 0:
            amt = qty * float((snap or {}).get("reference_price") or 0)
        c1 = snap.get("category1_id")
        if c1 is None and pid in meta:
            c1 = (meta.get(pid) or {}).get("category1_id")
        try:
            cid = int(c1) if c1 is not None else None
        except (TypeError, ValueError):
            cid = None
        r = float(rate_map.get(int(cid), fallback_rate)) if cid is not None else float(fallback_rate)
        weighted += amt * r
        total_amt += amt
    if total_amt <= 0:
        return None
    return round(weighted / total_amt, 6)


async def _signed_contract_for_order_on_date(
    db: AsyncSession, client_id: int, delivery_id: int, on_date: date
) -> Optional[Contract]:
    return await db.scalar(
        select(Contract)
        .where(
            Contract.client_id == client_id,
            Contract.delivery_id == delivery_id,
            Contract.status == "已中标",
            Contract.period_start <= on_date,
            Contract.period_end >= on_date,
        )
        .order_by(Contract.id.desc())
    )


async def build_order_detail_extensions(
    db: AsyncSession,
    order: Order,
    *,
    viewer_role: Optional[str] = None,
    viewer_user_id: Optional[int] = None,
) -> dict[str, Any]:
    """返回需合并进订单详情 payload 的扩展字段（不含 Order ORM 本体 json）。"""
    user_ids: set[int] = {int(order.client_id), int(order.delivery_id)}
    if order.supplier_id is not None:
        user_ids.add(int(order.supplier_id))
    users = (await db.scalars(select(User).where(User.id.in_(list(user_ids))))).all()
    user_map = {int(u.id): u for u in users}

    out: dict[str, Any] = {}
    out["client"] = user_brief(user_map.get(int(order.client_id)))
    out["delivery"] = user_brief(user_map.get(int(order.delivery_id)))
    # 不再使用「主单供货商」语义；详情仅展示 allocation_suppliers（分单去重）
    out["supplier"] = None

    item_snapshot_map: dict[int, dict] = {}
    for idx, snap in enumerate(order.items_snapshot_json or [], 1):
        if isinstance(snap, dict):
            item_snapshot_map[idx] = snap
    product_ids_from_order = {
        int(i.get("product_id") or 0)
        for i in (order.items_json or [])
        if int(i.get("product_id") or 0) > 0
    }
    product_meta_map: dict[int, dict] = {}
    if product_ids_from_order:
        product_rows = (
            await db.scalars(
                select(Product).where(Product.id.in_(list(product_ids_from_order)))
            )
        ).all()
        product_meta_map = {
            int(p.id): {
                "unit": p.unit or "",
                "spec": p.spec or "",
                "name": p.name or f"商品#{int(p.id)}",
                "reference_price": float(p.reference_price or 0),
                "category1_id": int(p.category1_id) if p.category1_id is not None else None,
                "is_designated_factory": bool(p.is_designated_factory),
                "designated_factory_id": int(p.designated_factory_id) if p.designated_factory_id else None,
            }
            for p in product_rows
        }

    on_date = order.expected_delivery_date or order.created_at.date()
    contract = await _signed_contract_for_order_on_date(
        db, int(order.client_id), int(order.delivery_id), on_date
    )
    contract_payload: Optional[dict] = None
    if contract:
        cat_ids = [int(x) for x in (contract.category_ids_json or [])]
        cat_rows = (
            (await db.scalars(select(Category).where(Category.id.in_(cat_ids)))).all()
            if cat_ids
            else []
        )
        cat_name_map = {int(c.id): c.name for c in cat_rows}
        category_rates = []
        for entry in contract.category_rates_json or []:
            try:
                cid = int(entry.get("category_id")) if entry.get("category_id") is not None else None
            except (TypeError, ValueError):
                cid = None
            category_rates.append(
                {
                    "category_id": cid,
                    "category_name": cat_name_map.get(cid, "") if cid is not None else "",
                    "float_rate": float(entry.get("float_rate") or 0),
                }
            )
        ref_by_pid = {
            int(pid): float(m.get("reference_price") or 0) for pid, m in product_meta_map.items()
        }
        rate_map, fallback_rt = _contract_category_rate_map(contract)
        contract_payload = {
            "id": int(contract.id),
            "contract_no": contract.contract_no,
            "period_start": contract.period_start.isoformat(),
            "period_end": contract.period_end.isoformat(),
            "status": contract.status,
            "price_float_rate": float(contract.price_float_rate or 0),
            # 该单上浮率：合约品类按订单行金额加权（与「实付÷指导价−1」可不同，见 order_realized_float_rate）
            "order_float_rate": amount_weighted_contract_float_rate(
                order, rate_map, fallback_rt, product_meta_map
            ),
            "order_realized_float_rate": calc_order_float_rate(order, product_ref_by_id=ref_by_pid),
            "category_rates": category_rates,
            "category_ids": cat_ids,
            "category_names": [cat_name_map.get(cid, str(cid)) for cid in cat_ids],
        }
    out["contract"] = contract_payload

    order_items: list[dict] = []
    for idx, item in enumerate(order.items_json or [], 1):
        snap = item_snapshot_map.get(idx, {})
        pid = int(item.get("product_id") or snap.get("product_id") or 0)
        pmeta = product_meta_map.get(pid, {})
        qty = float(item.get("quantity") or 0)
        unit_price = float(item.get("unit_price") or 0)
        order_items.append(
            {
                "line_no": idx,
                "product_id": pid,
                "product_name": snap.get("product_name") or pmeta.get("name") or f"商品#{pid}",
                "spec": snap.get("spec") or pmeta.get("spec") or "",
                "unit": snap.get("unit") or pmeta.get("unit") or "",
                "quantity": qty,
                "unit_price": unit_price,
                "amount": round(qty * unit_price, 2),
                "category1_id": snap.get("category1_id"),
                "category1_name": snap.get("category1_name") or "",
                "category2_id": snap.get("category2_id"),
                "category2_name": snap.get("category2_name") or "",
                "is_designated_factory": pmeta.get("is_designated_factory", False),
                "designated_factory_id": pmeta.get("designated_factory_id"),
            }
        )
    out["order_items"] = order_items

    alloc_rows = (
        await db.scalars(
            select(OrderItemAllocation)
            .where(OrderItemAllocation.order_id == order.id)
            .order_by(OrderItemAllocation.line_no.asc(), OrderItemAllocation.id.asc())
        )
    ).all()
    alloc_supplier_ids = sorted({int(a.supplier_id) for a in alloc_rows})
    supplier_name_map: dict[int, str] = {}
    supplier_user_map: dict[int, User] = {}
    if alloc_supplier_ids:
        supplier_rows = (
            await db.scalars(select(User).where(User.id.in_(alloc_supplier_ids)))
        ).all()
        supplier_user_map = {int(u.id): u for u in supplier_rows}
        supplier_name_map = {
            int(u.id): (u.company_name or u.username or f"供货商#{u.id}") for u in supplier_rows
        }
    # 交易主体「供货商」按分单去重展示；无分单时前端仍回退 order.supplier（主单字段）
    out["allocation_suppliers"] = [
        user_brief(supplier_user_map[sid]) for sid in alloc_supplier_ids if sid in supplier_user_map
    ]

    qr_rows = (
        await db.scalars(
            select(QualityReport).where(QualityReport.order_id == order.id)
        )
    ).all()
    qr_by_alloc: dict[int, dict] = {}
    qr_legacy: dict[tuple[int, int], dict] = {}
    for q in qr_rows:
        qpayload = {
            "id": int(q.id),
            "report_no": q.report_no,
            "file_url": q.file_url,
            "status": q.status,
            "supplier_id": int(q.supplier_id),
            "product_id": int(q.product_id),
            "allocation_id": int(q.allocation_id) if q.allocation_id is not None else None,
            "created_at": q.created_at.isoformat() if getattr(q, "created_at", None) else None,
        }
        if q.allocation_id is not None:
            qr_by_alloc[int(q.allocation_id)] = qpayload
        else:
            qr_legacy.setdefault((int(q.product_id), int(q.supplier_id)), qpayload)

    allocations: list[dict] = []
    line_split_count: dict[int, int] = {}
    for row in alloc_rows:
        ln = int(row.line_no)
        line_split_count[ln] = line_split_count.get(ln, 0) + 1
    for row in alloc_rows:
        ln = int(row.line_no)
        snap = item_snapshot_map.get(ln, {})
        pmeta = product_meta_map.get(int(row.product_id), {})
        report = qr_by_alloc.get(int(row.id))
        if not report:
            report = qr_legacy.get((int(row.product_id), int(row.supplier_id)))
        allocations.append(
            {
                "id": int(row.id),
                "line_no": ln,
                "product_id": int(row.product_id),
                "product_name": snap.get("product_name") or pmeta.get("name") or f"商品#{int(row.product_id)}",
                "spec": snap.get("spec") or pmeta.get("spec") or "",
                "unit": snap.get("unit") or pmeta.get("unit") or "",
                "quantity": float(row.quantity),
                "unit_price": float(row.unit_price),
                "amount": round(float(row.quantity) * float(row.unit_price), 2),
                "supplier_id": int(row.supplier_id),
                "supplier_name": supplier_name_map.get(int(row.supplier_id), f"供货商#{int(row.supplier_id)}"),
                "status": row.status,
                "allocation_batch_no": row.allocation_batch_no,
                "is_split_line": bool(line_split_count.get(ln, 0) > 1),
                "split_line_count": int(line_split_count.get(ln, 0)),
                "quality_report": report,
                "missing_quality": report is None,
                "missing_quality_shipped": report is None and str(row.status) == "已出库",
            }
        )
    out["allocations"] = allocations

    line_alloc_groups: list[dict] = []
    for it in order_items:
        ln = int(it["line_no"])
        line_allocs = [a for a in allocations if int(a["line_no"]) == ln]
        line_alloc_groups.append(
            {
                "line_no": ln,
                "product_name": it["product_name"],
                "spec": it["spec"],
                "unit": it["unit"],
                "ordered_quantity": float(it["quantity"]),
                "ordered_amount": float(it["amount"]),
                "is_split": bool(len(line_allocs) > 1),
                "is_designated_factory": bool(it.get("is_designated_factory")),
                "allocations": line_allocs,
            }
        )
    out["line_alloc_groups"] = line_alloc_groups

    recv_rows = (
        await db.scalars(
            select(OrderReceivingLine)
            .where(OrderReceivingLine.order_id == order.id)
            .order_by(OrderReceivingLine.line_index.asc())
        )
    ).all()
    out["receiving_lines"] = [
        {
            "line_index": int(r.line_index),
            "status": str(r.status),
            "draft_kg": float(r.draft_kg) if r.draft_kg is not None else None,
            "confirmed_kg": float(r.confirmed_kg) if r.confirmed_kg is not None else None,
            "confirmed_at": r.confirmed_at.isoformat() if r.confirmed_at else None,
            "shortage_reason_code": r.shortage_reason_code,
            "shortage_reason_detail": r.shortage_reason_detail,
            "shortage_ordered_kg": float(r.shortage_ordered_kg) if r.shortage_ordered_kg is not None else None,
            "shortage_delta_kg": float(r.shortage_delta_kg) if r.shortage_delta_kg is not None else None,
        }
        for r in recv_rows
    ]
    out["receiving_total_lines"] = len(order_items)
    out["receiving_confirmed_count"] = len([r for r in recv_rows if str(r.status) == "confirmed"])
    out["receiving_total_kg"] = round(float(sum(float(r.confirmed_kg or 0) for r in recv_rows)), 3)
    shortage_ct = len(
        [r for r in recv_rows if r.shortage_delta_kg is not None and float(r.shortage_delta_kg) < 0]
    )
    out["shortage_line_count"] = shortage_ct

    ret_hdr = await db.scalar(
        select(OrderReturn).where(OrderReturn.order_id == order.id, OrderReturn.source == "receive_shortage")
    )
    if ret_hdr:
        ret_lns = (
            await db.scalars(
                select(OrderReturnLine).where(OrderReturnLine.order_return_id == int(ret_hdr.id))
            )
        ).all()
        out["order_return"] = {
            "id": int(ret_hdr.id),
            "return_no": ret_hdr.return_no,
            "status": str(ret_hdr.status),
            "lines": [
                {
                    "line_index": int(x.line_index),
                    "product_id": int(x.product_id) if x.product_id is not None else None,
                    "product_name": x.product_name,
                    "ordered_kg": float(x.ordered_kg),
                    "received_kg": float(x.received_kg),
                    "delta_kg": float(x.delta_kg),
                    "reason_code": x.reason_code,
                    "reason_detail": x.reason_detail,
                }
                for x in ret_lns
            ],
        }
    else:
        out["order_return"] = None

    delivery_record = await db.scalar(
        select(Delivery).where(Delivery.order_id == order.id).order_by(Delivery.id.desc())
    )
    out["delivery_record"] = (
        {
            "id": int(delivery_record.id),
            "driver_name": delivery_record.driver_name,
            "vehicle_no": delivery_record.vehicle_no,
            "status": str(delivery_record.status),
            "departed_at": delivery_record.departed_at.isoformat() if delivery_record.departed_at else None,
            "arrived_at": delivery_record.arrived_at.isoformat() if delivery_record.arrived_at else None,
            "current_lng": float(delivery_record.current_lng) if delivery_record.current_lng is not None else None,
            "current_lat": float(delivery_record.current_lat) if delivery_record.current_lat is not None else None,
        }
        if delivery_record
        else None
    )

    log_rows = (
        await db.scalars(
            select(OrderStatusLog)
            .where(OrderStatusLog.order_id == order.id)
            .order_by(OrderStatusLog.id.asc())
        )
    ).all()
    timeline = [
        {
            "from_status": str(l.old_status),
            "to_status": str(l.new_status),
            "actor_user_id": int(l.actor_user_id),
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in log_rows
    ]
    timeline.insert(
        0,
        {
            "from_status": "",
            "to_status": "下单",
            "actor_user_id": int(order.client_id),
            "created_at": order.created_at.isoformat() if order.created_at else None,
        },
    )
    out["status_timeline"] = timeline
    out["status_flow"] = list(ORDER_STATUS_FLOW)

    complaint_ticket_rows = (
        await db.scalars(
            select(Ticket)
            .where(Ticket.order_id == order.id, Ticket.type == "售后投诉")
            .order_by(Ticket.id.desc())
        )
    ).all()

    def _delivery_can_see_ticket(ct: Ticket) -> bool:
        if viewer_role != "delivery" or viewer_user_id is None:
            return True
        aid = getattr(ct, "assigned_delivery_id", None)
        effective_delivery = int(aid) if aid is not None else int(order.delivery_id)
        if str(ct.status) == "已关闭":
            return effective_delivery == int(viewer_user_id)
        return effective_delivery == int(viewer_user_id)

    complaint_attachments: list[dict] = []
    complaint_tickets: list[dict] = []
    my_complaint_ticket: Optional[dict] = None

    for ct in complaint_ticket_rows:
        if viewer_role == "delivery" and viewer_user_id is not None and not _delivery_can_see_ticket(ct):
            continue
        imgs = list(ct.attachments_json or []) if isinstance(ct.attachments_json, list) else []
        imgs = [str(u).strip() for u in imgs if str(u).strip()][:5]
        desc = (ct.description or "").strip()
        if imgs or desc or viewer_role != "delivery":
            complaint_attachments.append(
                {
                    "ticket_id": int(ct.id),
                    "status": str(ct.status),
                    "description": ct.description,
                    "created_at": ct.created_at.isoformat() if ct.created_at else None,
                    "images": imgs,
                }
            )
        full = complaint_ticket_public_dict(ct)
        complaint_tickets.append(full)
        if (
            viewer_role == "delivery"
            and viewer_user_id is not None
            and str(ct.status) != "已关闭"
            and _delivery_can_see_ticket(ct)
        ):
            if my_complaint_ticket is None or int(ct.id) > int(my_complaint_ticket.get("ticket_id") or 0):
                my_complaint_ticket = full

    out["complaint_attachments"] = complaint_attachments
    out["complaint_tickets"] = complaint_tickets
    out["my_complaint_ticket"] = my_complaint_ticket if viewer_role == "delivery" else None

    missing_shipped = await missing_quality_allocations(db, int(order.id), shipped_only=True)
    missing_all = sum(1 for a in allocations if a.get("missing_quality"))
    out["abnormal_flags"] = {
        "missing_quality_count": int(missing_all),
        "missing_quality_shipped_count": len(missing_shipped),
        "missing_quality_shipped": bool(missing_shipped),
        "missing_quality_after_ship": bool(missing_shipped),
        "shortage_line_count": int(shortage_ct),
        "has_order_return": bool(ret_hdr is not None),
        "has_abnormal": bool(order.has_abnormal),
    }

    return out
