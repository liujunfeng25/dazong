/**
 * 电子围栏地图几何：圆 → Polygon 外环（与后端球面近似一致，供禁行/分检圆形落库）。
 */

export function circleRingCoordinates(centerLng, centerLat, radiusM, segments = 36) {
  const R = 6371000.0
  const lat1 = (centerLat * Math.PI) / 180
  const lng1 = (centerLng * Math.PI) / 180
  const d = radiusM / R
  const n = Math.max(8, Math.min(72, Math.floor(segments)))
  const ring = []
  for (let i = 0; i <= n; i += 1) {
    const brng = (2 * Math.PI * (i % n)) / n
    const lat2 = Math.asin(Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(brng))
    const dlng = Math.atan2(
      Math.sin(brng) * Math.sin(d) * Math.cos(lat1),
      Math.cos(d) - Math.sin(lat1) * Math.sin(lat2),
    )
    const lng2 = lng1 + dlng
    ring.push([Math.round((lng2 * 180) / Math.PI * 1e6) / 1e6, Math.round((lat2 * 180) / Math.PI * 1e6) / 1e6])
  }
  return ring
}

export function circleToPolygonGeoJson(centerLng, centerLat, radiusM, segments = 36) {
  const ring = circleRingCoordinates(centerLng, centerLat, radiusM, segments)
  return { type: 'Polygon', coordinates: [ring] }
}

/** AMap Bounds → 闭合矩形外环 [lng,lat][] */
export function rectangleRingFromBounds(sw, ne) {
  const swLng = sw.getLng()
  const swLat = sw.getLat()
  const neLng = ne.getLng()
  const neLat = ne.getLat()
  return [
    [swLng, swLat],
    [neLng, swLat],
    [neLng, neLat],
    [swLng, neLat],
    [swLng, swLat],
  ]
}
