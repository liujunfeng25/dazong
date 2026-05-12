/**
 * 天枢大屏：与主站同源业务洞察 API（iframe 同域 /api/insights/business）
 */
const API_BASE = "/api/insights/business"

/** provide/inject：当前下钻选中的区县名（null = 全市），与地图 UI 同步、即时更新 */
export const TIANSHU_SELECTED_DISTRICT_KEY = Symbol("tianshuSelectedDistrict")

/** provide/inject：侧栏图表请求用区县（相机动画结束后再更新，减轻与 Three 抢主线程） */
export const TIANSHU_CHART_QUERY_DISTRICT_KEY = Symbol("tianshuChartQueryDistrict")

/** 切换区县后图表刷新防抖（毫秒）；实际拉数在 idle 回调中触发 */
export const DISTRICT_CHART_DEBOUNCE_MS = 420

const FETCH_CACHE_TTL_MS = 55_000
const FETCH_CACHE_MAX = 64
const fetchResponseCache = new Map()
const fetchInflight = new Map()

function authHeaders() {
  const token = window.localStorage?.getItem("dz_token")
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** 缓存命中时返回副本，避免多图表共享同一对象被就地改写 */
function cloneCachedJson(body) {
  if (body == null) return body
  if (typeof body !== "object") return body
  try {
    return JSON.parse(JSON.stringify(body))
  } catch {
    return body
  }
}

/** 在已有 query string 上追加可选 `district_name`（供各区县联动图表） */
export function appendDistrictToQueryString(qs, districtName) {
  const q = new URLSearchParams(qs || "")
  const t = districtName != null && String(districtName).trim()
  if (t) q.set("district_name", String(districtName).trim())
  return q.toString()
}

/**
 * GET JSON；对 `/api/insights/business/` 做 in-flight 合并 + 短期响应缓存（减轻区县切换并发）。
 * 需要绕过缓存时：`fetchJson(url, { bypassCache: true })`
 */
export async function fetchJson(url, opts = {}) {
  const bypass = opts.bypassCache === true
  const cacheable =
    !bypass && typeof url === "string" && url.includes("/api/insights/business/")
  const now = Date.now()

  if (cacheable) {
    const hit = fetchResponseCache.get(url)
    if (hit && now - hit.t < FETCH_CACHE_TTL_MS) {
      return cloneCachedJson(hit.body)
    }
    const pending = fetchInflight.get(url)
    if (pending) return pending
  }

  const promise = (async () => {
    const res = await fetch(url, { headers: authHeaders() })
    const text = await res.text()
    let body = null
    try {
      body = JSON.parse(text)
    } catch {
      body = null
    }
    if (!res.ok) {
      const detail = body?.detail
      const msg =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((x) => x.msg || x).join("; ")
            : text || res.statusText
      throw new Error(msg || `HTTP ${res.status}`)
    }
    if (cacheable) {
      fetchResponseCache.set(url, { body, t: Date.now() })
      while (fetchResponseCache.size > FETCH_CACHE_MAX) {
        const firstKey = fetchResponseCache.keys().next().value
        fetchResponseCache.delete(firstKey)
      }
    }
    return body
  })()

  if (cacheable) {
    fetchInflight.set(url, promise)
    promise.finally(() => {
      if (fetchInflight.get(url) === promise) {
        fetchInflight.delete(url)
      }
    })
  }

  return promise
}

let kpiRangeInflight = null
let kpiRangeCached = { qs: "", at: 0 }
const KPI_QS_TTL_MS = 4000

let kpiTodayInflight = null
let kpiTodayCached = { qs: "", at: 0 }

/** 与智能驾驶舱一致：先取 scope=range 的 start/end（in-flight + 短 TTL 去重） */
export async function resolveRangeQueryString() {
  const now = Date.now()
  if (kpiRangeCached.qs && now - kpiRangeCached.at < KPI_QS_TTL_MS) {
    return kpiRangeCached.qs
  }
  if (kpiRangeInflight) return kpiRangeInflight

  kpiRangeInflight = (async () => {
    try {
      const kr = await fetchJson(`${API_BASE}/kpi-summary?scope=range`)
      const sd = kr?.start_date
      const ed = kr?.end_date
      const q = new URLSearchParams()
      if (sd) q.set("start_date", sd)
      if (ed) q.set("end_date", ed)
      const qs = q.toString()
      kpiRangeCached = { qs, at: Date.now() }
      return qs
    } finally {
      kpiRangeInflight = null
    }
  })()
  return kpiRangeInflight
}

/** 天枢大屏：与后端「今日」对齐（上海时区），供各图表 start_date/end_date */
export async function todayRangeQueryString() {
  const now = Date.now()
  if (kpiTodayCached.qs && now - kpiTodayCached.at < KPI_QS_TTL_MS) {
    return kpiTodayCached.qs
  }
  if (kpiTodayInflight) return kpiTodayInflight

  kpiTodayInflight = (async () => {
    try {
      const kr = await fetchJson(`${API_BASE}/kpi-summary?scope=today`)
      const sd = kr?.start_date
      const ed = kr?.end_date
      const q = new URLSearchParams()
      if (sd) q.set("start_date", sd)
      if (ed) q.set("end_date", ed)
      const qs = q.toString()
      kpiTodayCached = { qs, at: Date.now() }
      return qs
    } finally {
      kpiTodayInflight = null
    }
  })()
  return kpiTodayInflight
}

/** Loading 阶段预热：kpi 日期窗口 + 全市 cockpit-smart-side-insights（区域分布） */
export function prefetchTianshuInsightCaches() {
  void (async () => {
    try {
      const [todayQs] = await Promise.all([
        todayRangeQueryString(),
        resolveRangeQueryString(),
      ])
      await fetchJson(`${API_BASE}/cockpit-smart-side-insights?${todayQs}`)
    } catch (e) {
      console.warn("[tianshu] prefetch insights", e)
    }
  })()
}

/**
 * 供 watch(chartQueryDistrict)：防抖后在 requestIdleCallback 中执行 load，
 * 避免与地图相机动画同一帧挤爆主线程；不支持 ric 时退化为 rAF。
 */
export function debouncedDistrictReload(loadFn, ms = DISTRICT_CHART_DEBOUNCE_MS) {
  let timer = null
  return () => {
    if (timer != null) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      const run = () => {
        void Promise.resolve(loadFn()).catch((err) => {
          console.warn("[tianshu] chart load", err)
        })
      }
      if (typeof requestIdleCallback !== "undefined") {
        requestIdleCallback(() => run(), { timeout: 320 })
      } else {
        requestAnimationFrame(run)
      }
    }, ms)
  }
}

/** 分钟桶按当日 6 小时一段聚成 4 段（minute_start / day_start_ts 均为 UNIX 秒） */
export function aggregateIntradayTo6hBins(dayStartTs, buckets) {
  const step = 6 * 3600
  const gmv = [0, 0, 0, 0]
  const orders = [0, 0, 0, 0]
  if (!Array.isArray(buckets)) return { gmv, orders }
  for (const b of buckets) {
    const ms = Number(b.minute_start)
    if (!Number.isFinite(ms) || ms < dayStartTs) continue
    const rel = ms - dayStartTs
    const idx = Math.min(3, Math.max(0, Math.floor(rel / step)))
    gmv[idx] += Number(b.bucket_gmv) || 0
    orders[idx] += Number(b.order_count) || 0
  }
  return { gmv, orders }
}

export const SIX_HOUR_LABELS = ["0–6时", "6–12时", "12–18时", "18–24时"]

/** 东八区今日、昨日 YYYY-MM-DD */
export function todayYesterdayIso() {
  const fmt = (d) => {
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, "0")
    const day = String(d.getDate()).padStart(2, "0")
    return `${y}-${m}-${day}`
  }
  const now = new Date()
  const t = fmt(now)
  const y = new Date(now)
  y.setDate(y.getDate() - 1)
  return { todayIso: t, yesterdayIso: fmt(y) }
}

/**
 * 分钟桶聚合为 8 个 3 小时区间（0-3 … 21-24），与 day_start_ts 对齐
 */
export function aggregateIntradayTo3hBins(dayStartTs, buckets) {
  const step = 3 * 3600
  const out = [0, 0, 0, 0, 0, 0, 0, 0]
  if (!Array.isArray(buckets)) return out
  for (const b of buckets) {
    const ms = Number(b.minute_start)
    const gmv = Number(b.bucket_gmv) || 0
    if (!Number.isFinite(ms) || ms < dayStartTs) continue
    const rel = ms - dayStartTs
    const idx = Math.min(7, Math.max(0, Math.floor(rel / step)))
    out[idx] += gmv
  }
  return out
}

export const HOUR3_LABELS = ["0-3", "3-6", "6-9", "9-12", "12-15", "15-18", "18-21", "21-24"]

export function truncateLabel(s, maxLen = 4) {
  const t = (s || "").trim()
  if (!t) return "—"
  return t.length > maxLen ? `${t.slice(0, maxLen)}…` : t
}
