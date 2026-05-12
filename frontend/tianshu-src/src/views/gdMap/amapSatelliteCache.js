/**
 * 天枢卫星拼贴本地持久化（IndexedDB），避免每次进页重复拉瓦片。
 * 键随 Geo 包络与级别变化；换数据/改投影尺度会自然失效。
 */
const DB_NAME = "tianshu_map_satellite"
const STORE = "png"
const DB_VER = 1

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VER)
    req.onupgradeneeded = (e) => {
      const db = e.target.result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE)
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

/**
 * @param {{ minX: number, maxX: number, minY: number, maxY: number }} shapeBounds
 * @param {number} z
 * @param {{ minLng: number, maxLng: number, minLat: number, maxLat: number }} ll
 */
export function buildSatelliteCacheKey(shapeBounds, z, ll) {
  const r = (x) => Math.round(Number(x) * 10000) / 10000
  const b = shapeBounds
  return [
    "v2",
    z,
    r(b.minX),
    r(b.maxX),
    r(b.minY),
    r(b.maxY),
    r(ll.minLng),
    r(ll.maxLng),
    r(ll.minLat),
    r(ll.maxLat),
  ].join("|")
}

/** @param {string} key */
export async function getSatellitePngBlob(key) {
  try {
    const db = await openDb()
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly")
      const req = tx.objectStore(STORE).get(key)
      req.onsuccess = () => resolve(req.result ?? null)
      req.onerror = () => reject(req.error)
    })
  } catch {
    return null
  }
}

/** @param {string} key @param {Blob} blob */
export async function putSatellitePngBlob(key, blob) {
  try {
    const db = await openDb()
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite")
      tx.objectStore(STORE).put(blob, key)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } catch {
    /* 缓存失败不影响主流程 */
  }
}
