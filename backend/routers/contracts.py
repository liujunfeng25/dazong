from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_role
from models import Category, Contract, Tender, TenderBid, User
from schemas.contracts import AwardIn, BidIn, TenderCreateIn
from services.audit_service import write_audit_log
from services.contract_state_machine import ensure_contract_transition
from services.notification_service import push_notification

router = APIRouter(prefix="/contracts", tags=["contracts"])


def _contract_lifecycle_status(row: Contract, today: date) -> str:
    if row.status == "已过期" or row.period_end < today:
        return "已过期"
    if row.status != "已中标":
        return row.status
    if row.period_start > today:
        return "待生效"
    if row.period_start <= today <= row.period_end:
        return "生效中"
    return "已过期"


def _serialize_contract_row(
    row: Contract,
    client: Optional[User],
    today: date,
    delivery: Optional[User] = None,
) -> dict:
    lifecycle = _contract_lifecycle_status(row, today)
    return {
        "id": row.id,
        "contract_no": row.contract_no,
        "client_id": row.client_id,
        "delivery_id": row.delivery_id,
        "category_ids_json": row.category_ids_json or [],
        "category_rates_json": row.category_rates_json or [],
        "period_start": row.period_start,
        "period_end": row.period_end,
        "status": row.status,
        "price_float_rate": float(row.price_float_rate or 0),
        "created_at": row.created_at,
        "client_name": (client.company_name or client.username or f"客户{row.client_id}") if client else "",
        "client_address": (client.address or "") if client else "",
        "delivery_name": (delivery.company_name or delivery.username or "") if delivery else "",
        "lifecycle_status": lifecycle,
    }


def _audit_meta(request: Request) -> dict:
    return {
        "trace_id": getattr(request.state, "trace_id", ""),
        "source_ip": request.client.host if request.client else "",
    }


async def _overlapping_awarded_contracts(
    db: AsyncSession,
    client_id: int,
    period_start: date,
    period_end: date,
    *,
    exclude_delivery_id: Optional[int] = None,
) -> list[tuple[Contract, User]]:
    """与时段相交的「已中标」合约（可选排除某配送商，用于定标校验）。"""
    stmt = (
        select(Contract, User)
        .join(User, User.id == Contract.delivery_id)
        .where(
            Contract.client_id == client_id,
            Contract.status == "已中标",
            Contract.period_start <= period_end,
            Contract.period_end >= period_start,
        )
        .order_by(Contract.id.desc())
    )
    if exclude_delivery_id is not None:
        stmt = stmt.where(Contract.delivery_id != int(exclude_delivery_id))
    return list((await db.execute(stmt)).all())


async def _has_overlapping_awarded_contract_other_delivery(
    db: AsyncSession,
    client_id: int,
    delivery_id: int,
    period_start: date,
    period_end: date,
) -> bool:
    """同一学校、时段与区间相交时，已中标合约不能与另一家配送商重叠。"""
    rows = await _overlapping_awarded_contracts(
        db,
        client_id,
        period_start,
        period_end,
        exclude_delivery_id=delivery_id,
    )
    return len(rows) > 0


def _serialize_overlap_contracts(rows: list[tuple[Contract, User]]) -> list[dict]:
    contracts: list[dict] = []
    for contract, delivery in rows:
        contracts.append(
            {
                "contract_id": int(contract.id),
                "contract_no": contract.contract_no,
                "delivery_id": int(contract.delivery_id),
                "delivery_name": (delivery.company_name or delivery.username or "").strip()
                or f"配送方#{contract.delivery_id}",
                "period_start": contract.period_start,
                "period_end": contract.period_end,
            }
        )
    return contracts


def _build_overlap_hint_message(
    contracts: list[dict],
    *,
    invited: Optional[set[int]] = None,
) -> str:
    if not contracts:
        return ""
    parts = [f"{c['delivery_name']}（{c['period_start']} ~ {c['period_end']}）" for c in contracts]
    message = f"招标周期与以下已中标合约时段重叠：{'；'.join(parts)}。"
    overlap_delivery_ids = {int(c["delivery_id"]) for c in contracts}
    if invited and overlap_delivery_ids <= invited:
        renew_names = "、".join(
            c["delivery_name"] for c in contracts if int(c["delivery_id"]) in invited
        )
        message += f"定标给 {renew_names} 可视为续约；定标给其他配送商将在定标时被拒绝。"
    else:
        message += "定标时若选择其他配送商将无法签约，请调整招标周期或仅对原配送商定标续约。"
    return message


@router.post("/tender")
async def create_tender(
    payload: TenderCreateIn,
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    delivery_ids = sorted({int(i) for i in (payload.delivery_ids or [])})
    requested_category_ids = sorted({int(i) for i in (payload.category_ids or [])})
    if not delivery_ids:
        raise HTTPException(400, "请至少选择一个配送单位")
    if payload.period_start > payload.period_end:
        raise HTTPException(400, "招标结束日期不能早于开始日期")

    delivery_rows = (
        await db.scalars(
            select(User).where(
                User.id.in_(delivery_ids), User.role == "delivery", User.status == "active"
            )
        )
    ).all()
    if len(delivery_rows) != len(delivery_ids):
        raise HTTPException(400, "配送单位存在无效或停用账号")

    if requested_category_ids:
        category_rows = (
            await db.scalars(
                select(Category).where(
                    Category.id.in_(requested_category_ids),
                    Category.level == 1,
                    Category.is_deleted.is_(False),
                )
            )
        ).all()
        if len(category_rows) != len(requested_category_ids):
            raise HTTPException(400, "仅允许选择有效的一级分类")
    else:
        category_rows = (
            await db.scalars(
                select(Category).where(
                    Category.level == 1,
                    Category.is_deleted.is_(False),
                )
            )
        ).all()
    if not category_rows:
        raise HTTPException(400, "当前没有可用的一级分类，请联系运营维护")
    category_ids = sorted({int(row.id) for row in category_rows})

    row = Tender(
        client_id=user.id,
        delivery_ids_json=delivery_ids,
        category_ids_json=category_ids,
        period_start=payload.period_start,
        period_end=payload.period_end,
        status="招标中",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await push_notification(
        db=db,
        role="delivery",
        event_type="tender_shortlisted",
        title="入围投标通知",
        content=f"您已入围招标 #{row.id}，请尽快填写浮动率报价。",
        route=f"/delivery/tenders/{row.id}",
        object_type="tender",
        object_id=row.id,
        target_user_ids=delivery_ids,
    )
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/meta")
async def tender_meta(
    _=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deliveries = (
        await db.scalars(
            select(User).where(User.role == "delivery", User.status == "active").order_by(User.id.asc())
        )
    ).all()
    categories = (
        await db.scalars(
            select(Category)
            .where(Category.level == 1, Category.is_deleted.is_(False))
            .order_by(Category.id.asc())
        )
    ).all()
    return {
        "deliveries": [
            {
                "id": row.id,
                "username": row.username,
                "company_name": row.company_name,
            }
            for row in deliveries
        ],
        "level1_categories": [
            {
                "id": row.id,
                "name": row.name,
                "max_float_rate": float(row.max_float_rate) if row.max_float_rate is not None else 1.0,
            }
            for row in categories
        ],
    }


@router.get("/tender/list")
async def list_open_tenders(
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.scalars(select(Tender).where(Tender.status == "招标中"))).all()
    visible_rows = [r for r in rows if user.id in (r.delivery_ids_json or [])]
    if not visible_rows:
        return []
    client_ids = sorted({int(r.client_id) for r in visible_rows})
    client_rows = (
        await db.scalars(select(User).where(User.id.in_(client_ids)))
    ).all()
    client_name_map = {u.id: (u.company_name or u.username) for u in client_rows}
    tender_ids = [row.id for row in visible_rows]
    my_bids = (
        await db.scalars(
            select(TenderBid).where(
                TenderBid.delivery_id == user.id,
                TenderBid.tender_id.in_(tender_ids),
            )
        )
    ).all()
    my_bid_map = {bid.tender_id: float(bid.price_float_rate) for bid in my_bids}
    return [
        {
            "id": row.id,
            "client_id": row.client_id,
            "client_name": client_name_map.get(row.client_id, f"客户#{row.client_id}"),
            "delivery_ids_json": row.delivery_ids_json,
            "category_ids_json": row.category_ids_json,
            "period_start": row.period_start,
            "period_end": row.period_end,
            "status": row.status,
            "created_at": row.created_at,
            "my_bid_float_rate": my_bid_map.get(row.id),
        }
        for row in visible_rows
    ]


@router.get("/tender/my")
async def list_my_tenders(
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.scalars(select(Tender).where(Tender.client_id == user.id).order_by(Tender.id.desc()))
    ).all()
    if not rows:
        return []
    tender_ids = [row.id for row in rows]
    bid_counts = (
        await db.execute(
            select(TenderBid.tender_id, func.count(TenderBid.id))
            .where(TenderBid.tender_id.in_(tender_ids))
            .group_by(TenderBid.tender_id)
        )
    ).all()
    bid_count_map = {tender_id: count for tender_id, count in bid_counts}
    return [
        {
            "id": row.id,
            "client_id": row.client_id,
            "delivery_ids_json": row.delivery_ids_json,
            "category_ids_json": row.category_ids_json,
            "period_start": row.period_start,
            "period_end": row.period_end,
            "status": row.status,
            "created_at": row.created_at,
            "bid_count": int(bid_count_map.get(row.id, 0)),
        }
        for row in rows
    ]


@router.get("/tender/period-overlap-hint")
async def tender_period_overlap_hint(
    period_start: date = Query(...),
    period_end: date = Query(...),
    delivery_ids: Optional[str] = Query(
        None,
        description="逗号分隔的入围配送商 ID，用于区分「可续约」与「定标将失败」",
    ),
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    """发起招标前软性提示：招标周期是否与另一家配送商的已中标合约重叠。"""
    if period_start > period_end:
        return {"has_overlap": False, "contracts": [], "message": ""}

    rows = await _overlapping_awarded_contracts(db, int(user.id), period_start, period_end)
    contracts = _serialize_overlap_contracts(rows)

    invited: set[int] = set()
    if delivery_ids:
        for chunk in str(delivery_ids).split(","):
            chunk = chunk.strip()
            if chunk.isdigit():
                invited.add(int(chunk))

    message = _build_overlap_hint_message(contracts, invited=invited or None)

    return {"has_overlap": bool(contracts), "contracts": contracts, "message": message}


@router.get("/tender/{tender_id}/award-context")
async def tender_award_context(
    tender_id: int,
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    """定标页：招标周期、重叠合约说明及各配送商是否允许定标。"""
    tender = await db.scalar(
        select(Tender).where(Tender.id == int(tender_id), Tender.client_id == int(user.id))
    )
    if not tender:
        raise HTTPException(404, "招标单不存在")

    overlap_rows = await _overlapping_awarded_contracts(
        db, int(user.id), tender.period_start, tender.period_end
    )
    contracts = _serialize_overlap_contracts(overlap_rows)
    invited = {int(i) for i in (tender.delivery_ids_json or [])}
    message = _build_overlap_hint_message(contracts, invited=invited or None)

    check_delivery_ids: set[int] = set(invited)
    bid_delivery_ids = (
        await db.scalars(
            select(TenderBid.delivery_id).where(TenderBid.tender_id == int(tender_id))
        )
    ).all()
    for did in bid_delivery_ids:
        check_delivery_ids.add(int(did))

    per_delivery: dict[str, dict] = {}
    for did in sorted(check_delivery_ids):
        blocked = await _has_overlapping_awarded_contract_other_delivery(
            db,
            int(user.id),
            did,
            tender.period_start,
            tender.period_end,
        )
        if blocked:
            others = [c for c in contracts if int(c["delivery_id"]) != did]
            names = "、".join(
                f"{c['delivery_name']}（{c['period_start']}~{c['period_end']}）" for c in others
            )
            per_delivery[str(did)] = {
                "can_award": False,
                "reason": f"与现有合约时段冲突：{names}。请对原配送商续约或调整招标周期。",
            }
        else:
            renew_note = ""
            if any(int(c["delivery_id"]) == did for c in contracts):
                renew_note = "与现有合约为同一配送商，定标视为续约。"
            per_delivery[str(did)] = {"can_award": True, "reason": renew_note}

    return {
        "tender_id": int(tender.id),
        "period_start": tender.period_start,
        "period_end": tender.period_end,
        "status": tender.status,
        "has_overlap": bool(contracts),
        "overlap_contracts": contracts,
        "message": message,
        "per_delivery": per_delivery,
    }


@router.get("/tender/{tender_id}")
async def tender_detail(
    tender_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tender = await db.scalar(select(Tender).where(Tender.id == tender_id))
    if not tender:
        raise HTTPException(404, "招标单不存在")
    if user.role == "client" and user.id != tender.client_id:
        raise HTTPException(403, "无权限查看")
    if user.role == "delivery" and user.id not in (tender.delivery_ids_json or []):
        raise HTTPException(403, "无权限查看")
    client_user = await db.scalar(select(User).where(User.id == tender.client_id))
    my_bid = None
    if user.role == "delivery":
        my_bid = await db.scalar(
            select(TenderBid).where(
                TenderBid.tender_id == tender.id,
                TenderBid.delivery_id == user.id,
            )
        )
    categories = (
        await db.scalars(
            select(Category).where(Category.id.in_(tender.category_ids_json or []))
        )
    ).all()
    category_name_map = {row.id: row.name for row in categories}
    cap_map = {
        int(row.id): float(row.max_float_rate) if row.max_float_rate is not None else 1.0
        for row in categories
    }
    return {
        "id": tender.id,
        "client_id": tender.client_id,
        "client_name": (client_user.company_name or client_user.username) if client_user else f"客户#{tender.client_id}",
        "delivery_ids_json": tender.delivery_ids_json,
        "period_start": tender.period_start,
        "period_end": tender.period_end,
        "status": tender.status,
        "created_at": tender.created_at,
        "my_bid_float_rate": float(my_bid.price_float_rate) if my_bid else None,
        "my_category_rates": (my_bid.category_rates_json or []) if my_bid else [],
        "categories": [
            {
                "category_id": int(cid),
                "category_name": category_name_map.get(int(cid), f"一级分类#{cid}"),
                "max_float_rate": cap_map.get(int(cid), 1.0),
            }
            for cid in (tender.category_ids_json or [])
        ],
    }


@router.post("/tender/{tender_id}/bid")
async def bid_tender(
    tender_id: int,
    payload: BidIn,
    user=Depends(require_role("delivery")),
    db: AsyncSession = Depends(get_db),
):
    tender = await db.scalar(select(Tender).where(Tender.id == tender_id))
    if not tender:
        raise HTTPException(404, "招标单不存在")
    if user.id not in (tender.delivery_ids_json or []):
        raise HTTPException(403, "不在可投标配送商范围")
    if tender.status != "招标中":
        raise HTTPException(400, "该招标已结束，无法继续报价")

    tender_category_ids = {int(i) for i in (tender.category_ids_json or [])}
    if not tender_category_ids:
        raise HTTPException(400, "招标分类为空，无法报价")
    rate_map = {int(i.category_id): Decimal(str(i.float_rate)) for i in payload.category_rates}
    if set(rate_map.keys()) != tender_category_ids:
        raise HTTPException(400, "请对招标内全部一级分类填写浮动率")

    cap_rows = (
        await db.scalars(select(Category).where(Category.id.in_(tender_category_ids)))
    ).all()
    cap_by_id = {
        int(r.id): (float(r.max_float_rate) if r.max_float_rate is not None else 1.0) for r in cap_rows
    }
    name_by_id = {int(r.id): r.name for r in cap_rows}
    for category_id in tender_category_ids:
        rate = rate_map[category_id]
        cap = cap_by_id.get(int(category_id), 1.0)
        if rate > Decimal(str(cap)):
            cname = name_by_id.get(int(category_id), str(category_id))
            raise HTTPException(
                400,
                f"分类「{cname}」的上浮率 {float(rate):.4f} 超过运营设定上限 {cap:.4f}，请调整后再提交",
            )

    avg_rate_total = Decimal("0")
    category_rates_json = []
    for category_id in tender_category_ids:
        rate = rate_map[category_id]
        avg_rate_total += rate
        category_rates_json.append(
            {"category_id": int(category_id), "float_rate": float(rate)}
        )

    exists = await db.scalar(
        select(TenderBid).where(
            TenderBid.tender_id == tender_id, TenderBid.delivery_id == user.id
        )
    )
    avg_rate = float(avg_rate_total / Decimal(len(tender_category_ids)))
    if exists:
        exists.price_float_rate = avg_rate
        exists.category_rates_json = category_rates_json
        exists.total_amount = Decimal("0")
        await db.commit()
        await db.refresh(exists)
        await push_notification(
            db=db,
            role="client",
            event_type="tender_bid_updated",
            title="配送商已更新报价",
            content=f"招标 #{tender_id} 有配送商更新了浮动率报价。",
            route=f"/client/contracts/{tender_id}/bids",
            object_type="tender",
            object_id=tender_id,
            target_user_ids=[tender.client_id],
            canteen_id=None,
        )
        await db.commit()
        return exists
    row = TenderBid(
        tender_id=tender_id,
        delivery_id=user.id,
        price_float_rate=avg_rate,
        category_rates_json=category_rates_json,
        total_amount=Decimal("0"),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await push_notification(
        db=db,
        role="client",
        event_type="tender_bid_created",
        title="收到新的配送报价",
        content=f"招标 #{tender_id} 收到新的浮动率报价。",
        route=f"/client/contracts/{tender_id}/bids",
        object_type="tender",
        object_id=tender_id,
        target_user_ids=[tender.client_id],
        canteen_id=None,
    )
    await db.commit()
    return row


@router.get("/tender/{tender_id}/bids")
async def list_tender_bids(
    tender_id: int,
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    tender = await db.scalar(select(Tender).where(Tender.id == tender_id, Tender.client_id == user.id))
    if not tender:
        raise HTTPException(404, "招标单不存在")
    bids = (await db.scalars(select(TenderBid).where(TenderBid.tender_id == tender_id))).all()
    if not bids:
        return []
    category_rows = (
        await db.scalars(
            select(Category).where(Category.id.in_(tender.category_ids_json or []))
        )
    ).all()
    category_name_map = {int(c.id): c.name for c in category_rows}
    delivery_ids = [b.delivery_id for b in bids]
    users = (
        await db.scalars(select(User).where(User.id.in_(delivery_ids)))
    ).all()
    name_map = {u.id: (u.company_name or u.username) for u in users}
    return [
        {
            "id": bid.id,
            "tender_id": bid.tender_id,
            "delivery_id": bid.delivery_id,
            "delivery_name": name_map.get(bid.delivery_id, f"配送方#{bid.delivery_id}"),
            "price_float_rate": float(bid.price_float_rate),
            "category_rates": [
                {
                    "category_id": int(i.get("category_id")),
                    "category_name": category_name_map.get(
                        int(i.get("category_id")), f"一级分类#{i.get('category_id')}"
                    ),
                    "float_rate": float(i.get("float_rate", 0)),
                }
                for i in (bid.category_rates_json or [])
                if i.get("category_id") is not None
            ],
            "created_at": bid.created_at,
        }
        for bid in bids
    ]


@router.post("/tender/{tender_id}/award")
async def award_tender(
    tender_id: int,
    payload: AwardIn,
    request: Request,
    user=Depends(require_role("client")),
    db: AsyncSession = Depends(get_db),
):
    tender = await db.scalar(
        select(Tender).where(Tender.id == tender_id, Tender.client_id == user.id)
    )
    if not tender:
        raise HTTPException(404, "招标单不存在")
    if tender.status != "招标中":
        raise HTTPException(400, "该招标已完成定标，请勿重复中标")
    bid = await db.scalar(
        select(TenderBid).where(
            TenderBid.tender_id == tender_id, TenderBid.delivery_id == payload.delivery_id
        )
    )
    if not bid:
        raise HTTPException(404, "报价不存在")

    if await _has_overlapping_awarded_contract_other_delivery(
        db,
        tender.client_id,
        payload.delivery_id,
        tender.period_start,
        tender.period_end,
    ):
        raise HTTPException(
            400,
            "该学校在招标对应的合约期内已与另一家配送商存在「已中标」合约（时段相交），无法再签约当前配送商；不与当前时段相交时可与其他配送商签约。",
        )

    contract = Contract(
        contract_no=f"CT{tender_id:06d}",
        client_id=tender.client_id,
        delivery_id=payload.delivery_id,
        category_ids_json=tender.category_ids_json,
        period_start=tender.period_start,
        period_end=tender.period_end,
        status="已中标",
        price_float_rate=bid.price_float_rate,
        category_rates_json=bid.category_rates_json or [],
    )
    ensure_contract_transition(tender.status, "已中标")
    tender.status = "已中标"
    db.add(contract)
    await write_audit_log(
        db=db,
        actor_user_id=user.id,
        action="tender_award",
        category="contract",
        object_type="tender",
        object_id=tender.id,
        detail=f"award delivery={payload.delivery_id}",
        **_audit_meta(request),
    )
    await db.commit()
    await db.refresh(contract)
    await push_notification(
        db=db,
        role="client",
        event_type="tender_awarded_done",
        title="中标已确认",
        content=f"招标 #{tender_id} 已完成定标，合约 {contract.contract_no} 已生成。",
        route="/client/contracts",
        object_type="contract",
        object_id=contract.id,
        target_user_ids=[tender.client_id],
        canteen_id=None,
    )
    await push_notification(
        db=db,
        role="delivery",
        event_type="tender_award_win",
        title="恭喜中标",
        content=f"您已中标招标 #{tender_id}，请进入我的合约查看执行信息。",
        route="/delivery/contracts",
        object_type="contract",
        object_id=contract.id,
        target_user_ids=[payload.delivery_id],
    )
    loser_ids = [int(i) for i in (tender.delivery_ids_json or []) if int(i) != int(payload.delivery_id)]
    await push_notification(
        db=db,
        role="delivery",
        event_type="tender_award_lose",
        title="招标结果通知",
        content=f"很遗憾，您未中标招标 #{tender_id}。",
        route="/delivery/tenders",
        object_type="tender",
        object_id=tender_id,
        target_user_ids=loser_ids,
    )
    await db.commit()
    await db.refresh(contract)
    return contract


@router.get("/list")
async def list_my_contracts(
    lifecycle: Optional[str] = Query(None, description="待生效|生效中|已过期|招标中|已中标，空为全部"),
    keyword: Optional[str] = Query(None, description="合约号/客户名称/地址模糊筛选"),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    stmt = select(Contract).order_by(Contract.id.desc())
    if user.role == "client":
        stmt = stmt.where(Contract.client_id == user.id)
    elif user.role == "delivery":
        stmt = stmt.where(Contract.delivery_id == user.id)
    rows = (await db.scalars(stmt)).all()
    for row in rows:
        if row.period_end < today and row.status != "已过期":
            row.status = "已过期"
    await db.commit()

    client_ids = sorted({int(r.client_id) for r in rows})
    delivery_ids = sorted({int(r.delivery_id) for r in rows})
    client_map: dict[int, User] = {}
    if client_ids:
        client_rows = (await db.scalars(select(User).where(User.id.in_(client_ids)))).all()
        client_map = {int(u.id): u for u in client_rows}
    delivery_map: dict[int, User] = {}
    if delivery_ids:
        delivery_rows = (await db.scalars(select(User).where(User.id.in_(delivery_ids)))).all()
        delivery_map = {int(u.id): u for u in delivery_rows}

    out: list[dict] = []
    for row in rows:
        client = client_map.get(int(row.client_id))
        delivery = delivery_map.get(int(row.delivery_id))
        item = _serialize_contract_row(row, client, today, delivery)
        out.append(item)

    if lifecycle and lifecycle.strip():
        want = lifecycle.strip()
        out = [i for i in out if i.get("lifecycle_status") == want or i.get("status") == want]

    if keyword and keyword.strip():
        k = keyword.strip().lower()
        out = [
            i
            for i in out
            if k in (i.get("contract_no") or "").lower()
            or k in (i.get("client_name") or "").lower()
            or k in (i.get("client_address") or "").lower()
        ]

    return out


@router.get("/{contract_id}")
async def contract_detail(
    contract_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(Contract).where(Contract.id == contract_id))
    if not row:
        raise HTTPException(404, "合约不存在")
    if user.role in {"client", "delivery"} and user.id not in {row.client_id, row.delivery_id}:
        raise HTTPException(403, "无权限查看")
    today = date.today()
    if row.period_end < today and row.status != "已过期":
        row.status = "已过期"
        await db.commit()
    client = await db.scalar(select(User).where(User.id == row.client_id))
    delivery = await db.scalar(select(User).where(User.id == row.delivery_id))
    return _serialize_contract_row(row, client, today, delivery)
