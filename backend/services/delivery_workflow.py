"""配送商操作阶段（workflow stage）派生与批量聚合。

阶段由 order.status + 分单聚合（OrderItemAllocation）+ 分拣聚合
（DeliverySortScanRecord）共同推导，是工作台、订单列表、订单详情三处
"下一步该做什么"引导的唯一真源。智能排线为纯计算建议、不落库，故不参与
阶段判定，仅在 await_ship 阶段作为建议动作提示。
"""

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import DeliverySortScanRecord, OrderItemAllocation

# 阶段定义：code -> 标签 / 一句话引导 / 前端跳转路由（None 表示等待型，无跳转）
STAGE_DEFS: dict[str, dict] = {
    "await_split": {
        "label": "待分单",
        "hint": "订单已接，去「智能分单」把订单行分配给供货商和工厂。",
        "action_route": "/delivery/smart-split",
    },
    "await_ship": {
        "label": "待供货商发货",
        "hint": "已分单，等待供货商出库；可先去「智能排线」按配送日期安排车辆。",
        "action_route": "/delivery/smart-routing",
    },
    "await_sort": {
        "label": "待分拣",
        "hint": "供货商已出库，等待分检端（PDA）扫码分拣完成。",
        "action_route": None,
    },
    "await_pickup": {
        "label": "待取货",
        "hint": "分拣已完成，可在订单详情确认取货并发车。",
        "action_route": None,
    },
    "delivering": {
        "label": "配送中",
        "hint": "已发车，送达后在订单详情确认送达。",
        "action_route": None,
    },
    "await_receive": {
        "label": "待客户收货",
        "hint": "货已送达，等待客户确认收货。",
        "action_route": None,
    },
    "await_settle": {
        "label": "待结算",
        "hint": "客户已确认收货，等待结算。",
        "action_route": None,
    },
    "done": {"label": "已完成", "hint": "订单已结算完成。", "action_route": None},
    "cancelled": {"label": "已取消", "hint": "订单已取消。", "action_route": None},
}


def compute_delivery_stage(
    status: str,
    alloc_total: int,
    alloc_shipped: int,
    all_shipped: bool,
    sort_all_done: bool,
) -> dict:
    """根据订单状态与聚合派生配送阶段，返回 {code, label, hint, action_route}。"""
    s = str(status or "")
    if s == "取消":
        code = "cancelled"
    elif s in {"下单", "配货"}:
        if int(alloc_total) <= 0:
            code = "await_split"
        elif not bool(all_shipped):
            code = "await_ship"
        elif not bool(sort_all_done):
            code = "await_sort"
        else:
            code = "await_pickup"
    elif s == "发货":
        code = "delivering"
    elif s == "收货":
        code = "await_receive"
    elif s == "收货确认":
        code = "await_settle"
    elif s == "已结算":
        code = "done"
    else:
        code = "await_split"
    return {"code": code, **STAGE_DEFS[code]}


async def delivery_stage_aggregates(
    db: AsyncSession, order_ids: list[int]
) -> dict[int, dict]:
    """批量聚合多个订单的分单与分拣进度，避免逐单 N+1 查询。

    返回 {order_id: {alloc_total, alloc_shipped, all_shipped,
                     sort_total, sort_done, sort_all_done}}。
    """
    ids = [int(i) for i in order_ids]
    if not ids:
        return {}

    alloc_rows = (
        await db.execute(
            select(
                OrderItemAllocation.order_id,
                func.count(OrderItemAllocation.id),
                func.coalesce(
                    func.sum(case((OrderItemAllocation.status == "已出库", 1), else_=0)),
                    0,
                ),
            )
            .where(OrderItemAllocation.order_id.in_(ids))
            .group_by(OrderItemAllocation.order_id)
        )
    ).all()
    alloc_map = {int(oid): (int(total or 0), int(shipped or 0)) for oid, total, shipped in alloc_rows}

    sort_rows = (
        await db.execute(
            select(
                DeliverySortScanRecord.order_id,
                func.count(DeliverySortScanRecord.id),
            )
            .where(DeliverySortScanRecord.order_id.in_(ids))
            .group_by(DeliverySortScanRecord.order_id)
        )
    ).all()
    sort_map = {int(oid): int(done or 0) for oid, done in sort_rows}

    out: dict[int, dict] = {}
    for oid in ids:
        total, shipped = alloc_map.get(oid, (0, 0))
        sort_done = sort_map.get(oid, 0)
        all_shipped = total > 0 and shipped == total
        # 与 delivery_sort_summary_for_order 口径一致：无分单时视为已分拣完成
        sort_all_done = sort_done >= total if total > 0 else True
        out[oid] = {
            "alloc_total": total,
            "alloc_shipped": shipped,
            "all_shipped": all_shipped,
            "sort_total": total,
            "sort_done": sort_done,
            "sort_all_done": sort_all_done,
        }
    return out
