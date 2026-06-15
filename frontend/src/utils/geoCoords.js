/** 是否为可用于地图/路线的有效坐标（排除空值与 0,0 占位） */
export function isUsableGeoCoord(lng, lat) {
  const x = Number(lng)
  const y = Number(lat)
  if (!Number.isFinite(x) || !Number.isFinite(y)) return false
  if (x < -180 || x > 180 || y < -90 || y > 90) return false
  if (Math.abs(x) < 1e-5 && Math.abs(y) < 1e-5) return false
  return true
}

export function formatGeoCoord(lng, lat, digits = 6) {
  if (!isUsableGeoCoord(lng, lat)) return ''
  return `${Number(lng).toFixed(digits)}, ${Number(lat).toFixed(digits)}`
}
