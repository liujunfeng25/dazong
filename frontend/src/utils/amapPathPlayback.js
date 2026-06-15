/**
 * 高德折线轨迹播放（与 RoutePlanPanel 思路一致：RAF + Marker.setPosition）。
 * 历史轨迹点含 monitorTime（Unix 秒）时，播放总时长按真实时间跨度压缩到合理区间。
 */

/** 沿折线顶点比例 t∈[0,1] 线性插值（与 RoutePlanPanel 一致） */
export function interpolatePath(coords, t) {
  if (!coords?.length) return null
  if (coords.length === 1) return coords[0]
  const n = coords.length - 1
  const f = Math.min(1, Math.max(0, t)) * n
  const i = Math.min(n - 1, Math.floor(f))
  const u = f - i
  const a = coords[i]
  const b = coords[i + 1]
  return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u]
}

/**
 * 按 monitorTime 升序，去掉连续重复坐标，得到折线路径与元数据（一一对应）。
 * @param {Array<{lng?: number, lat?: number, monitorTime?: number, speed?: number|string}>} points
 */
export function buildSortedHistoryPath(points) {
  const sorted = [...(points || [])].sort(
    (a, b) => Number(a?.monitorTime || 0) - Number(b?.monitorTime || 0),
  )
  const path = []
  const meta = []
  for (const p of sorted) {
    const lng = Number(p.lng)
    const lat = Number(p.lat)
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue
    const prev = path[path.length - 1]
    if (prev && Math.abs(prev[0] - lng) < 1e-8 && Math.abs(prev[1] - lat) < 1e-8) continue
    path.push([lng, lat])
    const mt = Number(p.monitorTime)
    let spd = null
    if (p.speed != null && p.speed !== '') {
      const x = Number(p.speed)
      spd = Number.isFinite(x) ? x : null
    }
    let crs = null
    if (p.course != null && p.course !== '') {
      const c = Number(p.course)
      crs = Number.isFinite(c) ? c : null
    }
    meta.push({
      monitorTime: Number.isFinite(mt) ? mt : 0,
      speed: spd,
      course: crs,
    })
  }
  return { path, meta }
}

/**
 * 播放时长：按轨迹起止 Unix 秒跨度映射到 [8s, 300s]，再除以倍速（不低于 sxw 观感上限）。
 * @param {{ monitorTime: number }[]} meta
 * @param {number} playSpeed 倍速，如 1、2、4
 */
export function historyPlaybackDurationMs(meta, playSpeed) {
  const sp = Math.max(0.25, Math.min(8, Number(playSpeed) || 1))
  if (!meta?.length) return Math.round(15000 / sp)
  const t0 = meta[0].monitorTime
  const t1 = meta[meta.length - 1].monitorTime
  const spanSec = Math.max(1, t1 - t0)
  const raw = Math.min(300000, Math.max(8000, spanSec * 1000))
  return Math.round(raw / sp)
}

export function escapeHtmlForMap(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function formatMonitorTimeUnix(sec) {
  const n = Number(sec)
  if (!Number.isFinite(n) || n <= 0) return '—'
  try {
    return new Date(n * 1000).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return '—'
  }
}

/** 方位角（度），北为 0°，顺时针；用于车头 / 与 sxw 航向一致 */
export function bearingDegrees(lng1, lat1, lng2, lat2) {
  const rad = Math.PI / 180
  const φ1 = lat1 * rad
  const φ2 = lat2 * rad
  const Δλ = (lng2 - lng1) * rad
  const y = Math.sin(Δλ) * Math.cos(φ2)
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ)
  const θ = Math.atan2(y, x)
  return ((θ * 180) / Math.PI + 360) % 360
}

/** 当前插值点在折线上的「已驶过」路径（含笔尖），用于渐进轨迹线 */
export function subpathWithTip(path, ratio) {
  const n = path.length
  if (n < 2) return path ? [...path] : []
  const t = Math.min(1, Math.max(0, ratio))
  const tip = interpolatePath(path, t)
  const seg = Math.min(n - 2, Math.max(0, Math.floor(t * (n - 1))))
  const out = path.slice(0, seg + 1)
  out.push(tip)
  return out
}
