/** 全站统一使用中国（上海）时间展示 */

export const CN_TZ = 'Asia/Shanghai'

/**
 * 解析后端时间：带 Z / 时区偏移的按标准解析；无时区后缀的视为 UTC（与库内 UTC 存储一致）。
 */
export function parseBackendDate(input) {
  if (input == null) return new Date(NaN)
  if (input instanceof Date) return input
  const raw = String(input).trim()
  if (!raw) return new Date(NaN)
  const hasOffset = /[+-]\d{2}:\d{2}$/.test(raw) || /[+-]\d{4}$/.test(raw)
  if (/Z$/i.test(raw) || hasOffset) {
    return new Date(raw)
  }
  const normalized = raw.includes('T') ? raw : raw.replace(' ', 'T')
  return new Date(`${normalized}Z`)
}

/** 格式：2026/04/28 15:59:48（中国时区，24 小时制） */
export function formatChinaDateTime(input) {
  const d = parseBackendDate(input)
  if (Number.isNaN(d.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: CN_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(d)
}

/** 当前时刻在中国时区下的显示（用于顶栏时钟等） */
export function formatChinaClock(date = new Date()) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: CN_TZ,
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

/** 用于按月聚合：YYYY-MM（中国时区） */
export function formatChinaYearMonth(input) {
  const d = parseBackendDate(input)
  if (Number.isNaN(d.getTime())) return ''
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: CN_TZ,
    year: 'numeric',
    month: '2-digit',
  }).format(d)
}
