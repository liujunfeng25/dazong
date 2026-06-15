/**
 * 配送商操作阶段（workflow stage）前端展示映射。
 * 阶段 code 与后端 services/delivery_workflow.py 的 STAGE_DEFS 一致，
 * 由后端列表/工作台接口下发 stage 对象；本文件补充前端展示用的颜色与动作按钮文案，
 * 并提供 deliveryStageFromDetail() 在订单详情页用现有字段直接派生阶段。
 */

export const DELIVERY_STAGE_META = {
  await_split: { label: '待分单', tagType: 'danger', actionLabel: '去智能分单' },
  await_ship: { label: '待供货商发货', tagType: 'warning', actionLabel: '去智能排线' },
  await_sort: { label: '待分拣', tagType: 'warning', actionLabel: '' },
  await_pickup: { label: '待取货', tagType: 'primary', actionLabel: '确认取货' },
  delivering: { label: '配送中', tagType: 'primary', actionLabel: '确认送达' },
  await_receive: { label: '待客户收货', tagType: 'info', actionLabel: '' },
  await_settle: { label: '待结算', tagType: 'info', actionLabel: '' },
  done: { label: '已完成', tagType: 'success', actionLabel: '' },
  cancelled: { label: '已取消', tagType: 'info', actionLabel: '' },
}

export const DELIVERY_STAGE_HINT = {
  await_split: '订单已接，去「智能分单」把订单行分配给供货商和工厂。',
  await_ship: '已分单，等待供货商出库；可先去「智能排线」按配送日期安排车辆。',
  await_sort: '供货商已出库，等待分检端（PDA）扫码分拣完成。',
  await_pickup: '分拣已完成，可确认取货并发车。',
  delivering: '已发车，送达后确认送达。',
  await_receive: '货已送达，等待客户确认收货。',
  await_settle: '客户已确认收货，等待结算。',
  done: '订单已结算完成。',
  cancelled: '订单已取消。',
}

/** 阶段筛选下拉选项（仅进行中阶段，供订单列表使用） */
export const DELIVERY_STAGE_FILTER_OPTIONS = [
  { value: 'await_split', label: '待分单' },
  { value: 'await_ship', label: '待供货商发货' },
  { value: 'await_sort', label: '待分拣' },
  { value: 'await_pickup', label: '待取货' },
  { value: 'delivering', label: '配送中' },
  { value: 'await_receive', label: '待客户收货' },
  { value: 'await_settle', label: '待结算' },
]

export function deliveryStageLabel(code) {
  return DELIVERY_STAGE_META[code]?.label || '—'
}

export function deliveryStageTagType(code) {
  return DELIVERY_STAGE_META[code]?.tagType || 'info'
}

/**
 * 用订单详情已有字段派生阶段 code（与后端 compute_delivery_stage 同口径）。
 * 详情已含 status / allocation_total / all_allocations_shipped / delivery_sort_all_done。
 */
export function deliveryStageFromDetail(detail) {
  const status = detail?.status || ''
  if (status === '取消') return 'cancelled'
  const allocTotal = Number(detail?.allocation_total || 0)
  const allShipped = Boolean(detail?.all_allocations_shipped)
  const sortAllDone = Boolean(detail?.delivery_sort_all_done)
  if (status === '下单' || status === '配货') {
    if (allocTotal <= 0) return 'await_split'
    if (!allShipped) return 'await_ship'
    if (!sortAllDone) return 'await_sort'
    return 'await_pickup'
  }
  if (status === '发货') return 'delivering'
  if (status === '收货') return 'await_receive'
  if (status === '收货确认') return 'await_settle'
  if (status === '已结算') return 'done'
  return 'await_split'
}
