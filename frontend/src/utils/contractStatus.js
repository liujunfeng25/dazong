/**
 * 合约「生命周期」与库内 Contract.status 的标签色（与后端 _contract_lifecycle_status / Enum 一致）
 */

/** 计算态生命周期：待生效 | 生效中 | 已过期 | 以及招标流程中的招标中/已中标 */
export function contractLifecycleTagType(lifecycle) {
  const s = lifecycle == null ? '' : String(lifecycle).trim()
  if (s === '生效中') return 'success'
  if (s === '待生效') return 'warning'
  if (s === '已过期') return 'info'
  if (s === '招标中') return 'primary'
  if (s === '已中标') return 'primary'
  return 'info'
}

/** 定标状态（原数据表 Contract.status）：招标中 | 已中标 | 已过期（与「生命周期」列配色区分） */
export function contractDbStatusTagType(status) {
  const s = status == null ? '' : String(status).trim()
  if (s === '已中标') return 'primary'
  if (s === '招标中') return 'warning'
  if (s === '已过期') return 'danger'
  return 'info'
}
