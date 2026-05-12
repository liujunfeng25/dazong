/**
 * 高德影像瓦片（经同源 /api/map/tiles/amap 代理）拼贴为 CanvasTexture，供 mapTop / 挤出顶采样。
 * 拼贴结果写入 IndexedDB，同包络再次进入页面可直接读本地，无需实时拉瓦片。
 */
import { CanvasTexture, SRGBColorSpace, LinearFilter, ClampToEdgeWrapping } from "three"
import { computeShapeSpaceBounds } from "./mapGeoBounds.js"
import {
  buildSatelliteCacheKey,
  getSatellitePngBlob,
  putSatellitePngBlob,
} from "./amapSatelliteCache.js"

const TILE = 256
const DEFAULT_Z = 11
const MAX_TILES = 110
const MAX_CANVAS_EDGE = 4096

function lonToTileX(lon, z) {
  const n = 2 ** z
  return Math.floor(((lon + 180) / 360) * n)
}

function latToTileY(lat, z) {
  const n = 2 ** z
  const latRad = (lat * Math.PI) / 180
  const y =
    ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n
  return Math.floor(y)
}

/**
 * @param {import("d3-geo").GeoProjection} mercator d3 geoMercator 实例（含 invert）
 * @param {{ minX: number, maxX: number, minY: number, maxY: number }} shapeBounds
 * @returns {{ minLng: number, maxLng: number, minLat: number, maxLat: number }}
 */
function shapeBoundsToLngLatBBox(mercator, shapeBounds) {
  const { minX, maxX, minY, maxY } = shapeBounds
  const pts = [
    mercator.invert([minX, -minY]),
    mercator.invert([maxX, -minY]),
    mercator.invert([maxX, -maxY]),
    mercator.invert([minX, -maxY]),
  ]
  let minLng = Infinity
  let maxLng = -Infinity
  let minLat = Infinity
  let maxLat = -Infinity
  for (const p of pts) {
    if (!p || p.length < 2) continue
    const [lng, lat] = p
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue
    minLng = Math.min(minLng, lng)
    maxLng = Math.max(maxLng, lng)
    minLat = Math.min(minLat, lat)
    maxLat = Math.max(maxLat, lat)
  }
  if (!Number.isFinite(minLng)) {
    return { minLng: 116.0, maxLng: 117.0, minLat: 39.7, maxLat: 40.3 }
  }
  const padLng = (maxLng - minLng) * 0.06 + 0.01
  const padLat = (maxLat - minLat) * 0.06 + 0.01
  return {
    minLng: minLng - padLng,
    maxLng: maxLng + padLng,
    minLat: minLat - padLat,
    maxLat: maxLat + padLat,
  }
}

/**
 * @param {Blob} blob
 * @returns {Promise<import("three").CanvasTexture | null>}
 */
async function textureFromPngBlob(blob) {
  const bmp = await createImageBitmap(blob)
  const canvas = document.createElement("canvas")
  canvas.width = bmp.width
  canvas.height = bmp.height
  const ctx = canvas.getContext("2d")
  if (!ctx) {
    bmp.close?.()
    return null
  }
  ctx.drawImage(bmp, 0, 0)
  bmp.close?.()
  const tex = new CanvasTexture(canvas)
  tex.colorSpace = SRGBColorSpace
  tex.wrapS = ClampToEdgeWrapping
  tex.wrapT = ClampToEdgeWrapping
  tex.minFilter = LinearFilter
  tex.magFilter = LinearFilter
  tex.generateMipmaps = false
  tex.needsUpdate = true
  return tex
}

/**
 * @param {string|object} mapJsonRaw
 * @param {(lngLat: number[]) => number[]} projectFn d3 forward（与 World.geoProjection 一致入参）
 * @param {import("d3-geo").GeoProjection} mercator 与 projectFn 同一套 center/scale/translate 的实例
 * @param {{ zoom?: number, signal?: AbortSignal }} opts
 * @returns {Promise<import("three").CanvasTexture | null>}
 */
export async function loadAmapSatelliteTexture(mapJsonRaw, projectFn, mercator, opts = {}) {
  const zoom = Number.isFinite(opts.zoom) ? opts.zoom : DEFAULT_Z
  const signal = opts.signal

  const shapeBounds = computeShapeSpaceBounds(mapJsonRaw, projectFn)
  const ll = shapeBoundsToLngLatBBox(mercator, shapeBounds)

  let z = Math.max(3, Math.min(18, Math.round(zoom)))
  let x0 = 0
  let x1 = 0
  let y0 = 0
  let y1 = 0
  let n = 2 ** z
  let tw = 0
  let th = 0
  for (; z >= 3; z--) {
    n = 2 ** z
    x0 = lonToTileX(ll.minLng, z)
    x1 = lonToTileX(ll.maxLng, z)
    y0 = latToTileY(ll.maxLat, z)
    y1 = latToTileY(ll.minLat, z)
    if (x0 > x1) [x0, x1] = [x1, x0]
    if (y0 > y1) [y0, y1] = [y1, y0]
    x0 -= 1
    x1 += 1
    y0 -= 1
    y1 += 1
    x0 = Math.max(0, x0)
    x1 = Math.min(n - 1, x1)
    y0 = Math.max(0, y0)
    y1 = Math.min(n - 1, y1)
    tw = x1 - x0 + 1
    th = y1 - y0 + 1
    if (tw * th <= MAX_TILES) break
  }

  const cacheKey = buildSatelliteCacheKey(shapeBounds, z, ll)
  const cachedBlob = await getSatellitePngBlob(cacheKey)
  if (cachedBlob && cachedBlob.size > 32) {
    try {
      const tex = await textureFromPngBlob(cachedBlob)
      if (tex) return tex
    } catch {
      /* 损坏缓存则继续拉瓦片 */
    }
  }

  let cw = tw * TILE
  let ch = th * TILE
  const scale = Math.min(1, MAX_CANVAS_EDGE / Math.max(cw, ch))
  if (scale < 1) {
    cw = Math.floor(cw * scale)
    ch = Math.floor(ch * scale)
  }

  const canvas = document.createElement("canvas")
  canvas.width = cw
  canvas.height = ch
  const ctx = canvas.getContext("2d")
  if (!ctx) return null

  const fetchTile = async (tx, ty) => {
    const u = `/api/map/tiles/amap?z=${z}&x=${tx}&y=${ty}`
    const res = await fetch(u, { signal })
    if (!res.ok) throw new Error(`tile ${tx},${ty}: ${res.status}`)
    const blob = await res.blob()
    return createImageBitmap(blob)
  }

  try {
    const results = new Map()
    for (let ty = y0; ty <= y1; ty++) {
      for (let tx = x0; tx <= x1; tx++) {
        const bmp = await fetchTile(tx, ty)
        results.set(`${tx},${ty}`, bmp)
      }
    }

    const tileDraw = scale < 1 ? Math.floor(TILE * scale) : TILE
    for (let ty = y0; ty <= y1; ty++) {
      for (let tx = x0; tx <= x1; tx++) {
        const bmp = results.get(`${tx},${ty}`)
        if (!bmp) continue
        const dx = (tx - x0) * tileDraw
        const dy = (ty - y0) * tileDraw
        ctx.drawImage(bmp, dx, dy, tileDraw, tileDraw)
        bmp.close?.()
      }
    }
  } catch (e) {
    if (signal?.aborted) return null
    console.warn("[amapSatellite] 拼贴失败", e)
    return null
  }

  await new Promise((resolve) => {
    canvas.toBlob(
      async (b) => {
        if (b && b.size > 32) {
          await putSatellitePngBlob(cacheKey, b)
        }
        resolve()
      },
      "image/png",
      0.92,
    )
  })

  const tex = new CanvasTexture(canvas)
  tex.colorSpace = SRGBColorSpace
  tex.wrapS = ClampToEdgeWrapping
  tex.wrapT = ClampToEdgeWrapping
  tex.minFilter = LinearFilter
  tex.magFilter = LinearFilter
  tex.generateMipmaps = false
  tex.needsUpdate = true
  return tex
}
