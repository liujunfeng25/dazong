/**
 * 主订单 orders.status 存库值与后端 Enum 一致。
 * 展示名与 OMS 习惯一致；其中存库「发货」表示 **配送商已取货、正送往终端客户途中**，
 * 不是供货商→配送商区段（该区段体现在配货/分包出库与「确认取货」之前）。
 */
export const MAIN_ORDER_STATUS_OPTIONS = [
  { value: '下单', label: '待履约' },
  { value: '配货', label: '配货中' },
  { value: '发货', label: '向客户送货中' },
  { value: '收货', label: '待确认收货' },
  { value: '收货确认', label: '已收货' },
  { value: '已结算', label: '已结算' },
  { value: '取消', label: '已取消' },
]

export function orderStatusLabel(status) {
  if (status == null || status === '') return '—'
  const hit = MAIN_ORDER_STATUS_OPTIONS.find((o) => o.value === status)
  return hit ? hit.label : String(status)
}

/** 列表/详情主单状态标签色（存库值判断） */
export function orderMainStatusTagType(status) {
  if (status === '取消') return 'danger'
  if (status === '已结算') return 'success'
  if (status === '发货') return 'warning'
  return 'info'
}
