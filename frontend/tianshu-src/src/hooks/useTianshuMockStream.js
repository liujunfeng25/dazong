/**
 * 天枢大屏「模拟数据」composable。
 *
 * 用途：测试环境真实数据稀少，演示时启用此模拟器：
 *   - 注入 25~40 个模拟光柱点（client 蓝 / delivery 金 混合分布全国），shape 与
 *     /api/insights/business/cockpit-customer-map-points 返回的 points[] 完全一致；
 *   - 为每个模拟光柱预生成 5~15 条模拟订单（字段集照 backend/models/orders.py Order 抄全），
 *     给 hover tooltip 和 click 详情用，绕过 HTTP 直接出数据；
 *   - 周期性合成 WS batch/snapshot 事件丢进 useTianshuOpsConsole.pushSyntheticEvent，
 *     让 KPI 翻牌、心跳活动条、波形脉冲都跳起来。
 *
 * 强约束：0 后端写入。停止 / 卸载 / 页面隐藏时 stop() 一调即净，没有残留。
 */
import { reactive, ref, computed } from "vue"

// ───── 模块级单例状态：让 index.vue 的 click handler 和模拟器共享数据 ─────
const _running = ref(false)
const _mockPoints = ref([])
/** key = _mockId, value = mock orders array */
const _ordersByMock = reactive({})
/** 累计模拟 GMV / 单量（注入到 WS handler，实现翻牌效果） */
const _mockOrderCount = ref(0)
const _mockGmv = ref(0)

let _wsTimer = null
let _snapshotTimer = null
let _opsConsoleRef = null

// ───── 常量：北京各区 + 雄安（与监管大屏视角一致，让 mock 飞线/光柱可见） ─────
const _CITIES = [
  { name: "北京·朝阳", lng: 116.486, lat: 39.921 },
  { name: "北京·海淀", lng: 116.298, lat: 39.959 },
  { name: "北京·东城", lng: 116.418, lat: 39.917 },
  { name: "北京·西城", lng: 116.363, lat: 39.914 },
  { name: "北京·丰台", lng: 116.286, lat: 39.858 },
  { name: "北京·石景山", lng: 116.222, lat: 39.906 },
  { name: "北京·通州", lng: 116.656, lat: 39.910 },
  { name: "北京·昌平", lng: 116.231, lat: 40.220 },
  { name: "北京·大兴", lng: 116.341, lat: 39.726 },
  { name: "北京·房山", lng: 116.143, lat: 39.749 },
  { name: "北京·门头沟", lng: 116.105, lat: 39.937 },
  { name: "北京·顺义", lng: 116.654, lat: 40.130 },
  { name: "北京·怀柔", lng: 116.638, lat: 40.316 },
  { name: "北京·密云", lng: 116.843, lat: 40.376 },
  { name: "北京·延庆", lng: 115.974, lat: 40.456 },
  { name: "北京·平谷", lng: 117.121, lat: 40.140 },
  { name: "雄安·容城", lng: 115.873, lat: 39.052 },
  { name: "雄安·安新", lng: 115.936, lat: 38.935 },
]

const _CLIENT_NAMES = [
  "第一实验中学", "外国语学校", "工业大学附属中学", "师范大学附属中学",
  "市第二中学", "高级中学", "民族中学", "新区中学",
  "经济技术开发区中心食堂", "高新区学校食堂", "国际学校食堂", "示范小学食堂",
]
const _DELIVERY_NAMES = [
  "京福鲜配·区域中转仓", "顺丰冷链·华东仓配中心", "申通供应链·区域分拨",
  "韵达冷链·区域分拨", "圆通供应链·城市仓", "中通冷运·区域分拨",
  "极兔冷链·区域仓", "天天供应链·城市分拨", "京东物流·城市仓",
]

const _SUPPLIER_IDS = [201, 202, 203, 204, 205]

// ───── 工具：可重复的伪随机（同 session 内每次刷新分布一致，避免抖动） ─────
let _seed = 0
function _rand() {
  _seed = (_seed * 9301 + 49297) % 233280
  return _seed / 233280
}
function _pick(arr) {
  return arr[Math.floor(_rand() * arr.length)]
}
function _jitter(coord, range = 0.18) {
  return coord + (_rand() - 0.5) * range
}

// ───── 生成单条模拟订单（字段照 backend/models/orders.py Order 抄全） ─────
let _orderSeq = 0
function _mkOrder(point) {
  _orderSeq += 1
  const now = Date.now()
  const minutesAgo = Math.floor(_rand() * 60 * 8)
  const createdAt = new Date(now - minutesAgo * 60_000).toISOString()
  const total = Math.round((_rand() * 6500 + 380) * 100) / 100
  const statuses = ["下单", "已分单", "备货中", "已发货", "已收货", "已确认收货"]
  const status = _pick(statuses)
  return {
    id: 900_000 + _orderSeq,                       // 大数字段避开真实自增范围
    order_no: `ODMOCK-${String(_orderSeq).padStart(6, "0")}`,
    status,
    client_id: 100 + (point._mockIdx % 6),
    delivery_id: 110 + (point._mockIdx % 3),
    supplier_id: _pick(_SUPPLIER_IDS),
    canteen_id: 500 + (point._mockIdx % 12),
    total_amount: total,
    delivery_address: point.address,
    delivery_lng: point.lng,
    delivery_lat: point.lat,
    created_at: createdAt,
    updated_at: createdAt,
    // 与真实 schema 一致的扩展字段（前端如展开商品行会用到）
    items_snapshot_json: null,
    receive_signatures_json: null,
  }
}

// ───── 生成模拟点位（业务约束：配送商必须是真实数据，mock 只补量客户/蓝光柱） ─────
function _generatePoints(target = 32) {
  const out = []
  for (let i = 0; i < target; i += 1) {
    const city = _CITIES[i % _CITIES.length]
    const role = "client"
    const lng = _jitter(city.lng, 0.18)
    const lat = _jitter(city.lat, 0.18)
    const name = _pick(_CLIENT_NAMES)
    const orderCount = Math.floor(_rand() * 22) + 3
    const gmv = Math.round(orderCount * (320 + _rand() * 1180) * 100) / 100
    const p = {
      _mockId: `mock-${role}-${String(i).padStart(3, "0")}`,
      _mockIdx: i,
      role,
      member_key: `mock:${role}:${i}`,
      member_id: 800_000 + i,
      member_count: 1,
      customer_name: `${city.name}·${name}`,
      address: `${city.name.replace("·", "市")}${name}（演示）`,
      order_count: orderCount,
      gmv,
      lng,
      lat,
    }
    out.push(p)
  }
  return out
}

// ───── 主 composable ─────
export function useTianshuMockStream() {
  /** 注册 ops console（在 setup 阶段从父组件传入），让 stop 时也能干净停掉 timer */
  function bindOpsConsole(ref) {
    _opsConsoleRef = ref
  }

  function isRunning() {
    return _running.value
  }

  /** 启动模拟：注入 points + 启动 WS 合成事件 timer。幂等。 */
  function start() {
    if (_running.value) return
    _seed = Date.now() & 0xffff || 1   // 每次开启换种子
    _orderSeq = 0
    _mockOrderCount.value = 0
    _mockGmv.value = 0
    const points = _generatePoints(32)
    _mockPoints.value = points
    for (const p of points) {
      const n = 5 + Math.floor(_rand() * 11)         // 5~15 单/点
      const list = []
      for (let i = 0; i < n; i += 1) list.push(_mkOrder(p))
      _ordersByMock[p._mockId] = list
    }
    _running.value = true

    // WS 合成事件：每 2s 一个 batch，KPI 累加；每 30s 强制 snapshot 补偿
    _wsTimer = setInterval(() => {
      if (!_running.value) return
      const newOrders = 1 + Math.floor(_rand() * 4)   // 每 tick 1~4 单
      _mockOrderCount.value += newOrders
      const incGmv = newOrders * (400 + _rand() * 2200)
      _mockGmv.value = Math.round((_mockGmv.value + incGmv) * 100) / 100
      const console_ = _opsConsoleRef
      if (console_ && typeof console_.pushSyntheticEvent === "function") {
        console_.pushSyntheticEvent({
          type: "batch",
          order_count: _mockOrderCount.value,
          cumulative_gmv: _mockGmv.value,
          rows: Array.from({ length: newOrders }, (_, k) => ({
            id: Date.now() + k,
            order_no: `ODMOCK-W-${Date.now()}-${k}`,
          })),
        })
      }
    }, 2000)

    _snapshotTimer = setInterval(() => {
      if (!_running.value) return
      const console_ = _opsConsoleRef
      if (console_ && typeof console_.pushSyntheticEvent === "function") {
        console_.pushSyntheticEvent({
          type: "snapshot",
          order_count: _mockOrderCount.value,
          cumulative_gmv: _mockGmv.value,
        })
      }
    }, 30_000)
  }

  /** 停止 + 清理所有模拟状态。幂等。可在 onBeforeUnmount / visibilitychange / 用户点关闭按钮调。 */
  function stop() {
    _running.value = false
    if (_wsTimer != null) {
      clearInterval(_wsTimer)
      _wsTimer = null
    }
    if (_snapshotTimer != null) {
      clearInterval(_snapshotTimer)
      _snapshotTimer = null
    }
    _mockPoints.value = []
    for (const k of Object.keys(_ordersByMock)) {
      delete _ordersByMock[k]
    }
    _mockOrderCount.value = 0
    _mockGmv.value = 0
  }

  function getMockOrdersByMockId(mockId) {
    return _ordersByMock[mockId] || []
  }

  function getMockPointByMockId(mockId) {
    return _mockPoints.value.find((p) => p._mockId === mockId) || null
  }

  /**
   * 业务约束：金色光柱必须是真实配送商坐标。mock 自己不造 delivery。
   * 调用方传入真实配送商点位（来自 cockpit-customer-map-points role=delivery），
   * 每个真实 delivery 配 3~5 个最近的 mock client 生成飞线对。
   * 返回 schema 与后端 /cockpit-flylines 一致（from_lng/from_lat/to_lng/to_lat/gmv/order_count）。
   */
  function buildMockFlylines(realDeliveries) {
    const clients = _mockPoints.value
    if (!Array.isArray(realDeliveries) || !realDeliveries.length) return []
    if (!clients.length) return []
    // 业务约束：mock 模式下每个客户都对应一条飞线——选最近的真实配送商作为起点。
    // 这样所有客户柱（蓝光柱）都与至少一家配送商形成飞线，不漏单。
    const validDeliveries = realDeliveries
      .map((d) => ({
        lng: Number(d.lng),
        lat: Number(d.lat),
        name: d.customer_name || d.address || "",
      }))
      .filter((d) => Number.isFinite(d.lng) && Number.isFinite(d.lat))
    if (!validDeliveries.length) return []
    const out = []
    for (const c of clients) {
      let best = validDeliveries[0]
      let bestD2 = Infinity
      for (const d of validDeliveries) {
        const dx = c.lng - d.lng
        const dy = c.lat - d.lat
        const d2 = dx * dx + dy * dy
        if (d2 < bestD2) {
          bestD2 = d2
          best = d
        }
      }
      out.push({
        from_lng: best.lng,
        from_lat: best.lat,
        from_name: best.name,
        to_lng: c.lng,
        to_lat: c.lat,
        to_name: c.customer_name,
        gmv: Math.round((Number(c.gmv) || 0) * 0.7),
        order_count: Math.max(1, Math.floor((Number(c.order_count) || 1) * 0.5)),
      })
    }
    return out
  }

  return {
    running: computed(() => _running.value),
    mockPoints: computed(() => _mockPoints.value),
    buildMockFlylines,
    bindOpsConsole,
    isRunning,
    start,
    stop,
    getMockOrdersByMockId,
    getMockPointByMockId,
  }
}
