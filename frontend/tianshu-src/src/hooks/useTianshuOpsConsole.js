/**
 * 天枢实时链路条：WebSocket（/api/insights/business/ws/live-gmv）+ 服务端 ping 心跳脉冲
 */
import { ref, computed, onMounted, onUnmounted } from "vue"
import { hasTianshuAuthToken, isTianshuNoAuthDemoMode } from "@/api/tianshuInsights.js"

const WS_PATH = "/api/insights/business/ws/live-gmv"
const BAR_N = 16
/** 与后端 live-gmv WebSocket JSON ping 周期一致（见驾驶舱 PanelOpsDataFreshness） */
const WS_PING_INTERVAL_MS = 60000

export function useTianshuOpsConsole() {
  const wsConnected = ref(false)
  const lastPingAt = ref(null)
  const lastPushAt = ref(null)
  const liveOrderCount = ref(null)
  const liveGmv = ref(null)
  /** 圆点短闪 */
  const pingPulse = ref(false)
  /** 与驾驶舱「实时通道」一致：ping 后约 1.38s 波形/光晕节拍 */
  const beatFlash = ref(false)
  const activityBars = ref(Array.from({ length: BAR_N }, (_, i) => 22 + ((i * 17) % 53)))

  let ws = null
  let reconnectAttempt = 0
  let reconnectTimer = null
  let pingPulseTimer = null
  let beatTimer = null
  /** 每秒递增，驱动「X 秒前 / 距下次 ping」类文案刷新 */
  const clockTick = ref(0)
  let clockTimer = null

  function bumpBars(intensity = 28) {
    const v = Math.min(100, 14 + intensity + Math.random() * 22)
    activityBars.value = [...activityBars.value.slice(1), v]
  }

  function flashPingPulse() {
    pingPulse.value = true
    if (pingPulseTimer) clearTimeout(pingPulseTimer)
    pingPulseTimer = setTimeout(() => {
      pingPulseTimer = null
      pingPulse.value = false
    }, 700)
  }

  function flashBeat() {
    beatFlash.value = true
    if (beatTimer) clearTimeout(beatTimer)
    beatTimer = setTimeout(() => {
      beatTimer = null
      beatFlash.value = false
    }, 1380)
  }

  function handleMsg(msg) {
    if (msg.type === "ping") {
      lastPingAt.value = Date.now()
      flashPingPulse()
      flashBeat()
      bumpBars(24)
      return
    }
    if (msg.type === "snapshot") {
      lastPushAt.value = Date.now()
      if (msg.order_count != null) liveOrderCount.value = msg.order_count
      if (msg.cumulative_gmv != null) liveGmv.value = msg.cumulative_gmv
      bumpBars(22)
      return
    }
    if (msg.type === "batch") {
      lastPushAt.value = Date.now()
      if (msg.order_count != null) liveOrderCount.value = msg.order_count
      if (msg.cumulative_gmv != null) liveGmv.value = msg.cumulative_gmv
      const rows = msg.rows || []
      bumpBars(26 + Math.min(28, rows.length * 3))
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer != null) return
    reconnectAttempt += 1
    const delay = Math.min(30000, 1000 * 2 ** Math.min(reconnectAttempt, 5))
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, delay)
  }

  function connect() {
    if (ws) return
    if (isTianshuNoAuthDemoMode()) {
      wsConnected.value = false
      return
    }
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    const token = window.localStorage?.getItem("dz_token") || ""
    if (!token && !hasTianshuAuthToken()) return
    const q = new URLSearchParams()
    if (token) q.set("token", token)
    const qs = q.toString()
    const u = `${proto}//${window.location.host}${WS_PATH}${qs ? `?${qs}` : ""}`
    try {
      ws = new WebSocket(u)
    } catch {
      scheduleReconnect()
      return
    }
    ws.onopen = () => {
      wsConnected.value = true
      reconnectAttempt = 0
    }
    ws.onclose = () => {
      wsConnected.value = false
      ws = null
      scheduleReconnect()
    }
    ws.onmessage = (ev) => {
      try {
        handleMsg(JSON.parse(ev.data))
      } catch {
        /* ignore */
      }
    }
    ws.onerror = () => {
      if (import.meta.env.DEV) {
        console.warn("[tianshu-ops] WebSocket error", u)
      }
    }
  }

  /**
   * 将顶部/底部展示与 HTTP（kpi-summary 实查）对齐。
   * 典型场景：多 Uvicorn worker 各有一份 LiveGmvHub 内存，WS 连到「陈旧」实例时 GMV 落后、单量却与库一致。
   */
  function applyClientKpiReconcile(gmv, orderCount) {
    if (gmv != null && Number.isFinite(Number(gmv))) {
      liveGmv.value = Number(gmv)
    }
    if (orderCount != null && Number.isFinite(Number(orderCount))) {
      liveOrderCount.value = Math.round(Number(orderCount))
    }
    lastPushAt.value = Date.now()
  }

  function disconnect() {
    if (reconnectTimer != null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (pingPulseTimer != null) {
      clearTimeout(pingPulseTimer)
      pingPulseTimer = null
    }
    if (beatTimer != null) {
      clearTimeout(beatTimer)
      beatTimer = null
    }
    reconnectAttempt = 0
    if (ws) {
      ws.close()
      ws = null
    }
    wsConnected.value = false
    pingPulse.value = false
    beatFlash.value = false
  }

  onMounted(() => {
    connect()
    clockTimer = setInterval(() => {
      clockTick.value += 1
    }, 1000)
  })
  onUnmounted(() => {
    if (clockTimer != null) {
      clearInterval(clockTimer)
      clockTimer = null
    }
    disconnect()
  })

  const liveGmvYuan = computed(() => {
    const g = Number(liveGmv.value)
    if (!Number.isFinite(g)) return "—"
    return Math.round(g).toLocaleString("zh-CN", { maximumFractionDigits: 0 })
  })

  const lastPingLabel = computed(() => {
    void clockTick.value
    const t = lastPingAt.value
    if (!t) return wsConnected.value ? "等待保活" : "—"
    const s = Math.floor((Date.now() - t) / 1000)
    if (s < 0) return "刚刚"
    if (s < 60) return `${s} 秒前`
    if (s < 3600) return `${Math.floor(s / 60)} 分钟前`
    return "较久"
  })

  /** 单行：上次 ping 距今 + 距下次 JSON 保活约几秒 */
  const heartbeatInline = computed(() => {
    void clockTick.value
    if (!wsConnected.value) return "—"
    const t = lastPingAt.value
    if (!t) return "已连接 · 等待首次 ping"
    const elapsed = Math.floor((Date.now() - t) / 1000)
    const nextMs = t + WS_PING_INTERVAL_MS - Date.now()
    const nextSec = Math.max(0, Math.ceil(nextMs / 1000))
    const ago =
      elapsed < 0
        ? "刚刚"
        : elapsed < 60
          ? `${elapsed} 秒前`
          : elapsed < 3600
            ? `${Math.floor(elapsed / 60)} 分钟前`
            : "较久"
    return `${ago} · 下次 ~${nextSec}s`
  })

  /**
   * 模拟器接口：把合成消息丢进真实消息处理管线，UI 完全分辨不出。
   * 用于「模拟数据」按钮在前端注入 batch/snapshot/ping，让 KPI/心跳条/活动条都跳起来。
   * 仅本地内存，不发送任何网络帧。
   */
  function pushSyntheticEvent(msg) {
    if (msg && typeof msg === "object") {
      handleMsg(msg)
    }
  }

  return {
    wsConnected,
    pingPulse,
    beatFlash,
    lastPingAt,
    lastPushAt,
    liveOrderCount,
    liveGmv,
    liveGmvYuan,
    activityBars,
    lastPingLabel,
    heartbeatInline,
    applyClientKpiReconcile,
    pushSyntheticEvent,
  }
}
