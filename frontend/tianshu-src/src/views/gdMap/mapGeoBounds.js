/**
 * GeoJSON 在场景 Shape 空间中的包络（与 BaseMap / ExtrudeMap 一致：x = 投影 x，y = -投影 y）
 */
export function computeShapeSpaceBounds(mapJsonRaw, project) {
  const mapJsonData =
    typeof mapJsonRaw === "string" ? JSON.parse(mapJsonRaw) : mapJsonRaw
  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  const feats = mapJsonData?.features || []
  for (const f of feats) {
    const coords = f.geometry?.coordinates
    if (!coords) continue
    for (const multi of coords) {
      for (const ring of multi) {
        for (const pt of ring) {
          if (!pt || pt.length < 2) continue
          const [x, y] = project(pt)
          const sy = -y
          minX = Math.min(minX, x)
          maxX = Math.max(maxX, x)
          minY = Math.min(minY, sy)
          maxY = Math.max(maxY, sy)
        }
      }
    }
  }
  const eps = 1e-6
  if (!(maxX - minX > eps) || !(maxY - minY > eps)) {
    return { minX: -1, maxX: 1, minY: -1, maxY: 1 }
  }
  return { minX, maxX, minY, maxY }
}
