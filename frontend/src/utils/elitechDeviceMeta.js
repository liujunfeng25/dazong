const WARNING_LABELS = {
  1: '高温告警',
  2: '低温告警',
  3: '高湿告警',
  4: '低湿告警',
  5: '低湿告警',
  6: 'TVOC超标',
  7: 'PM2.5超标',
  8: 'PM1.0超标',
  9: 'PM10超标',
  10: '二氧化碳过高',
  11: '二氧化碳过低',
  12: '掉电告警',
  13: '通讯中断',
  14: '电量不足',
  15: '氨气过高',
  16: '高光照强度告警',
  17: '低光照强度告警',
  18: '高气压告警',
  19: '低气压告警',
  20: '高PH值告警',
  21: '低PH值告警',
  22: 'DI1高触发',
  23: 'DI1低触发',
  24: 'DI2高触发',
  25: 'DI2低触发',
  26: '测检不到探头',
  101: '高温告警解除',
  102: '低温告警解除',
  103: '高湿告警解除',
  104: '低湿告警解除',
  105: '甲醛超标解除',
  106: 'TVOC超标解除',
  107: 'PM2.5超标解除',
  108: 'PM1.0超标解除',
  109: 'PM10超标解除',
  110: '二氧化碳过高告警解除',
  111: '二氧化碳过低告警解除',
  112: '掉电告警解除',
  113: '通讯恢复',
  114: '电量恢复',
  115: '氨气过高告警解除',
  116: '高光照强度告警解除',
  117: '低光照强度告警解除',
  118: '高气压告警解除',
  119: '低气压告警解除',
  120: '高PH值告警解除',
  121: '低PH值告警解除',
  126: '探头恢复',
}

export function elitechWarningLabel(wrId) {
  const id = Number(wrId)
  if (!Number.isFinite(id)) return String(wrId || '—')
  return WARNING_LABELS[id] || `告警#${id}`
}

export function elitechWarningText(warningField) {
  const raw = String(warningField || '').trim()
  if (!raw) return '无'
  return raw
    .split(',')
    .map((p) => elitechWarningLabel(p.trim()))
    .filter(Boolean)
    .join('、')
}

export function elitechHasSensor(deviceTypes, bitIndex) {
  const s = String(deviceTypes || '')
  if (s.length < bitIndex) return false
  return s[bitIndex - 1] === '1'
}

export function elitechSensorSummary(deviceTypes) {
  const parts = []
  if (elitechHasSensor(deviceTypes, 1)) parts.push('温度')
  if (elitechHasSensor(deviceTypes, 2)) parts.push('湿度')
  if (elitechHasSensor(deviceTypes, 14)) parts.push('定位')
  return parts.length ? parts.join(' / ') : '—'
}

export function elitechFormatValue(value, unit = '') {
  const s = String(value ?? '').trim()
  if (!s || s === '-999.0' || s === '-999') return '—'
  return unit ? `${s}${unit}` : s
}

export function elitechOnlineLabel(status) {
  const n = Number(status)
  if (n === 0) return { text: '在线', type: 'success' }
  if (n === 1) return { text: '离线', type: 'info' }
  return { text: '未知', type: 'info' }
}

export function elitechElectricityLabel(level) {
  const n = Number(level)
  if (!Number.isFinite(n)) return '—'
  const map = ['空', '低', '中低', '中高', '满']
  return map[n] ?? String(n)
}

export function defaultHistoryRange() {
  const end = new Date()
  // 默认查最近 1 小时，减轻精创接口压力、加快历史明细加载
  const start = new Date(end.getTime() - 3600 * 1000)
  const fmt = (d) => {
    const p = (n) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  }
  return { start_time: fmt(start), end_time: fmt(end) }
}

function _parseNum(v) {
  const s = String(v ?? '').trim()
  if (!s || s === '-999' || s === '-999.0') return null
  const m = s.match(/-?\d+(?:\.\d+)?/)
  return m ? Number(m[0]) : null
}

/** 由历史明细行计算 min/avg/max（仅当前页，不再单独请求精创） */
export function elitechHistoryStatsFromRows(rows) {
  const list = Array.isArray(rows) ? rows : []
  if (!list.length) return null
  const temps = []
  const hums = []
  for (const r of list) {
    const t = _parseNum(r.temperature)
    const h = _parseNum(r.humidity)
    if (t != null) temps.push(t)
    if (h != null) hums.push(h)
  }
  const printStsList = []
  if (temps.length) {
    printStsList.push({
      text: '温度℃',
      minValue: String(Math.min(...temps)),
      maxValue: String(Math.max(...temps)),
      averageValue: String(Math.round((temps.reduce((a, b) => a + b, 0) / temps.length) * 10) / 10),
    })
  }
  if (hums.length) {
    printStsList.push({
      text: '湿度%RH',
      minValue: String(Math.min(...hums)),
      maxValue: String(Math.max(...hums)),
      averageValue: String(Math.round((hums.reduce((a, b) => a + b, 0) / hums.length) * 10) / 10),
    })
  }
  return printStsList.length ? { count: list.length, printStsList } : null
}
