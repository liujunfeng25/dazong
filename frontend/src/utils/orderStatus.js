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

/**
 * 主单状态自定义配色：el-tag 内置 type 仅 5 种、状态有 7 个，统一用自定义底色
 * （配合 effect="dark" 白字）让各状态清晰可分。
 */
export const ORDER_STATUS_COLORS = {
  下单: '#3b82f6', // 蓝 · 待履约
  配货: '#06b6d4', // 青 · 配货中
  发货: '#f59e0b', // 橙 · 向客户送货中
  收货: '#8b5cf6', // 紫 · 待确认收货
  收货确认: '#22c55e', // 绿 · 已收货
  已结算: '#475569', // 深灰蓝 · 终态
  取消: '#ef4444', // 红 · 已取消
}

/** 返回主单状态底色（hex）；未知状态返回 ''（调用方回退默认 tag 颜色） */
export function orderStatusTagColor(status) {
  return ORDER_STATUS_COLORS[status] || ''
}

/** 供货商视角状态（supplier_status：英文枚举）配色，与主单观感统一 */
export const SUPPLIER_STATUS_COLORS = {
  pending_ship: '#f59e0b', // 待发货 · 橙
  shipped: '#3b82f6', // 已发货 · 蓝
  completed: '#22c55e', // 已完成 · 绿
  cancelled: '#ef4444', // 已取消 · 红
}

export function supplierStatusTagColor(status) {
  return SUPPLIER_STATUS_COLORS[status] || ''
}
