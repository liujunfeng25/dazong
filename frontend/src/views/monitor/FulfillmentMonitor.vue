<script setup>
import { computed, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { monitorDispatchTripApi, monitorNeuralLogisticsApi } from '../../api/monitor'
import TripRouteMapCard from '../../components/TripRouteMapCard.vue'

const loading = ref(false)
const data = ref({})
const detailVisible = ref(false)
const detailState = ref({ title: '', subtitle: '', conclusion: '', summaryCards: [], sections: [], defaultOpen: [] })
const tripMapVisible = ref(false)
const tripMapLoading = ref(false)
const tripMapDetail = ref(null)
const tripMapFocusedStopId = ref(null)
const tripMapHeader = ref({ title: '', subtitle: '', summaryCards: [] })
const tripMapFallback = ref({ sections: [], defaultOpen: [] })
const tripMapError = ref('')

const summary = computed(() => data.value.summary || {})
const funnel = computed(() => Array.isArray(data.value.funnel) ? data.value.funnel : [])
const supplierBlocks = computed(() => Array.isArray(data.value.supplier_blocks) ? data.value.supplier_blocks : [])
const scopeDate = computed(() => summary.value.date || data.value.date || '')

const matchesScopeDate = (value) => !scopeDate.value || String(value || '') === String(scopeDate.value)

const ordersDetail = computed(() =>
  (Array.isArray(data.value.orders_detail) ? data.value.orders_detail : []).filter((row) =>
    matchesScopeDate(row.expected_delivery_date),
  ),
)
const allocationsDetail = computed(() => {
  const allowedOrderIds = new Set(ordersDetail.value.map((row) => Number(row.order_id)))
  return (Array.isArray(data.value.allocations_detail) ? data.value.allocations_detail : []).filter((row) =>
    allowedOrderIds.has(Number(row.order_id)),
  )
})
const trips = computed(() =>
  (Array.isArray(data.value.trips) ? data.value.trips : []).map((trip) => ({
    ...trip,
    stops: (trip.stops || []).filter((stop) => matchesScopeDate(stop.expected_delivery_date)),
  })).filter((trip) => (trip.stops || []).length > 0 || matchesScopeDate(trip.planning_date)),
)
const inTransit = computed(() =>
  (Array.isArray(data.value.in_transit) ? data.value.in_transit : []).filter((row) =>
    matchesScopeDate(row.expected_delivery_date),
  ),
)
const riskEvents = computed(() => Array.isArray(data.value.risk_events) ? data.value.risk_events : [])

const kpiCards = computed(() => [
  {
    key: 'today_orders',
    label: '今日配送订单',
    value: summary.value.today_orders,
    hint: `配送日（北京时间）：${summary.value.date || data.value.date || '今日'}`,
    tone: '',
  },
  {
    key: 'pending_trips',
    label: '待发车车次',
    value: summary.value.pending_trips,
    hint: '含有阻塞待处理车次',
    tone: 'warn',
  },
  {
    key: 'in_transit_trips',
    label: '配送中车次',
    value: summary.value.in_transit_trips,
    hint: `在途订单 ${fmt(summary.value.in_transit_orders)} 单`,
    tone: 'good',
  },
  {
    key: 'arrived_orders',
    label: '已送达订单',
    value: summary.value.arrived_orders,
    hint: `到达率 ${fmtPercent(summary.value.arrival_rate)}`,
    tone: 'good',
  },
  {
    key: 'blocked_allocations',
    label: '阻塞分单',
    value: summary.value.blocked_allocations,
    hint: `未出库 ${fmt(summary.value.not_shipped)} · 未分检 ${fmt(summary.value.not_sorted)}`,
    tone: 'danger',
  },
  {
    key: 'not_loaded',
    label: '未随车',
    value: summary.value.not_loaded,
    hint: '异常发车或现场留置',
    tone: 'danger',
  },
  {
    key: 'risk_count',
    label: '超时/风险',
    value: summary.value.risk_count,
    hint: '来自预警、工单和车次状态',
    tone: 'warn',
  },
])

const hubMetrics = computed(() => [
  { label: '今日配送', value: `${fmt(summary.value.today_orders)} 单` },
  { label: '在途车次', value: `${fmt(summary.value.in_transit_trips)} 辆` },
  { label: '阻塞分单', value: `${fmt(summary.value.blocked_allocations)} 条` },
])

const hubHealthScore = computed(() => {
  const sortRate = Number(summary.value.sort_rate || 0)
  const arrivalRate = Number(summary.value.arrival_rate || 0)
  const shipRate = Number(summary.value.ship_rate || 0)
  const blockedPenalty = Math.min(Number(summary.value.blocked_allocations || 0) * 3, 18)
  const riskPenalty = Math.min(Number(summary.value.risk_count || 0), 18)
  const score = sortRate * 0.45 + arrivalRate * 0.35 + shipRate * 0.2 - blockedPenalty - riskPenalty
  return Math.max(0, Math.min(Math.round(score), 100))
})

const hubMood = computed(() => {
  if (hubHealthScore.value >= 85) return 'happy'
  if (hubHealthScore.value >= 60) return 'neutral'
  return 'sad'
})

const hubMoodLabel = computed(() => {
  if (hubMood.value === 'happy') return '顺畅'
  if (hubMood.value === 'neutral') return '平稳'
  return '受阻'
})

const fmt = (value, digits = 0) => Number(value || 0).toLocaleString('zh-CN', {
  minimumFractionDigits: digits,
  maximumFractionDigits: digits,
})

const fmtPercent = (value) => `${fmt(value, 1)}%`

const fmtDateTime = (value) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const toneByLevel = (level) => {
  if (level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  return 'info'
}

const statusTone = (status) => {
  if (status === '运输中') return 'success'
  if (status === '有阻塞') return 'danger'
  if (status === '待发车') return 'warning'
  if (status === '已完成') return 'info'
  return 'info'
}

const detailLabelMap = {
  today_orders: '今日配送订单',
  pending_trips: '待发车车次',
  in_transit_trips: '配送中车次',
  arrived_orders: '已送达订单',
  blocked_allocations: '阻塞分单',
  not_loaded: '未随车',
  risk_count: '超时/风险',
}

const fmtMoney = (value) => `¥${fmt(value, 2)}`

const section = (title, rows, empty = '暂无相关明细') => ({
  title,
  rows: Array.isArray(rows) ? rows : [],
  empty,
})

const orderRows = (rows) => (rows || []).map((row) => ({
  订单号: row.order_no || '—',
  客户名称: row.client_name || '—',
  食堂名称: row.canteen_name || '—',
  配送日期: row.expected_delivery_date || '—',
  配送窗口: row.expected_delivery_slot || '—',
  当前状态: row.status || '—',
  订单金额: fmtMoney(row.amount),
  配送商: row.delivery_name || '—',
  分检进度: row.sort_progress || '—',
  关联车次: row.route_no || '暂未绑定车次',
}))

const allocationRows = (rows) => (rows || []).map((row) => ({
  订单号: row.order_no || '—',
  分单号: row.allocation_no || '—',
  商品名称: row.product_name || '—',
  规格单位: row.spec_unit || row.unit || '—',
  数量: `${fmt(row.quantity, 3)}${row.unit || ''}`,
  供应商: row.supplier_name || '—',
  出库状态: row.shipment_status || '—',
  分检状态: row.sort_status || '—',
  扫码时间: fmtDateTime(row.scan_time),
  装车状态: row.load_status || '—',
  当前问题: row.reason || row.not_loaded_reason || '无',
}))

const tripRows = (rows) => (rows || []).map((row) => ({
  车次号: row.route_no || '—',
  配送商: row.delivery_name || '—',
  司机: row.driver_name || '未填司机',
  车牌号: row.vehicle_no || '未定车',
  当前状态: row.status || '—',
  可发分单: fmt(row.ready_count),
  阻塞分单: fmt(row.blocked_count),
  未随车: fmt(row.not_loaded_count),
  站点数: `${fmt(row.stop_count)} 站`,
  发车时间: row.departed_at ? fmtDateTime(row.departed_at) : row.departure_time || '待定',
  设备情况: `北斗 ${fmt(row.beidou_count)} · 视频 ${fmt(row.camera_count)}`,
}))

const transitRows = (rows) => (rows || []).map((row) => ({
  订单号: row.order_no || '—',
  客户名称: row.client_name || '—',
  食堂名称: row.canteen_name || '—',
  车次号: row.route_no || '—',
  配送商: row.delivery_name || '—',
  车牌号: row.vehicle_no || '未定车',
  司机: row.driver_name || '未填司机',
  配送日期: row.expected_delivery_date || '—',
  配送窗口: row.expected_delivery_slot || '—',
  北斗状态: row.risk || row.beidou_reported_at || '暂无风险',
}))

const stopRows = (rows) => (rows || []).map((row) => ({
  顺序: `第 ${fmt(row.sequence)} 站`,
  订单号: row.order_no || '—',
  客户名称: row.client_name || '—',
  食堂名称: row.canteen_name || '—',
  配送窗口: row.expected_delivery_slot || '—',
  预计到达: row.planned_arrive_time || '—',
  当前状态: row.status || '—',
  地址: row.address || '—',
}))

const dispatchItemRows = (rows) => (rows || []).map((row) => ({
  订单号: row.order_no || '—',
  商品名称: row.product_name || '—',
  规格单位: row.spec_unit || row.unit || '—',
  数量: `${fmt(row.quantity, 3)}${row.unit || ''}`,
  供应商: row.supplier_name || '—',
  装车状态: row.status || '—',
  原因说明: row.reason || '无',
}))

const riskRows = (rows) => (rows || []).map((row) => ({
  风险类型: row.business_type || row.type || '履约风险',
  风险等级: row.level_label || '需关注',
  关联对象: row.title || '—',
  发生时间: fmtDateTime(row.created_at),
  风险说明: row.description || '—',
  建议动作: row.suggestion || '请进入对应订单、车次或工单继续核查。',
}))

const statusRows = (rows) => (rows || []).map((row) => ({
  流转节点: row.title || '状态变化',
  关联订单: row.description || '—',
  发生时间: fmtDateTime(row.created_at),
}))

const setDetail = (payload) => {
  detailState.value = {
    title: payload.title || '履约详情',
    subtitle: payload.subtitle || '今日履约监控',
    conclusion: payload.conclusion || '',
    summaryCards: payload.summaryCards || [],
    sections: payload.sections || [],
    defaultOpen: payload.defaultOpen || (payload.sections || []).slice(0, 2).map((item) => item.title),
  }
  detailVisible.value = true
}

const buildTripDetailFallback = (row) => ({
  title: row.route_no || '车次详情',
  subtitle: `${row.delivery_name || '配送商待识别'} · ${row.status || '状态待识别'}`,
  conclusion: `车次 ${row.route_no || ''} 当前状态为${row.status || '待识别'}，共 ${fmt(row.stop_count)} 个站点，未随车 ${fmt(row.not_loaded_count)} 条。`,
  summaryCards: [
    { label: '可发', value: fmt(row.ready_count), tone: 'good' },
    { label: '阻塞', value: fmt(row.blocked_count), tone: row.blocked_count ? 'danger' : '' },
    { label: '未随车', value: fmt(row.not_loaded_count), tone: row.not_loaded_count ? 'danger' : '' },
    { label: '站点', value: `${fmt(row.stop_count)} 站` },
  ],
  sections: [
    section('车次与司机车辆', tripRows([row])),
    section('站点顺序', stopRows(row.stops || [])),
    section('分单/商品明细', dispatchItemRows(row.item_details || [])),
    section('风险原因与处理建议', (row.risk_alerts || []).map((text) => ({ 风险说明: text || '—', 建议动作: '请调度员核实路线、时窗或车辆安排。' }))),
  ],
})

const buildTransitDetailFallback = (row) => ({
  title: row.order_no || '在途订单',
  subtitle: `${row.client_name || '客户待识别'} / ${row.canteen_name || '食堂待识别'}`,
  conclusion: `该订单当前在途，车辆 ${row.vehicle_no || '未定车'}，配送窗口 ${row.expected_delivery_slot || '待定'}。`,
  summaryCards: [
    { label: '车牌', value: row.vehicle_no || '未定车' },
    { label: '司机', value: row.driver_name || '未填司机' },
    { label: '配送窗口', value: row.expected_delivery_slot || '窗口待定' },
  ],
  sections: [
    section('关联订单', transitRows([row])),
    section('车次与司机车辆', [{ 车次号: row.route_no || '—', 配送商: row.delivery_name || '—', 车牌号: row.vehicle_no || '未定车', 司机: row.driver_name || '未填司机', 北斗状态: row.risk || row.beidou_reported_at || '暂无风险' }]),
  ],
})

const resolveTripIdFromRisk = (event) => {
  if (event?.trip_id) return Number(event.trip_id)
  const match = String(event?.id || '').match(/^trip-(?:late|no-beidou)-(\d+)$/)
  return match ? Number(match[1]) : null
}

const openTripMapDrawer = async ({ tripId, focusedOrderId = null, header, fallback }) => {
  if (!tripId) {
    if (fallback) setDetail(fallback)
    return
  }
  tripMapLoading.value = true
  tripMapVisible.value = true
  tripMapDetail.value = null
  tripMapFocusedStopId.value = null
  tripMapHeader.value = header || {}
  tripMapFallback.value = fallback || { sections: [], defaultOpen: [] }
  tripMapError.value = ''
  try {
    const detail = await monitorDispatchTripApi(tripId)
    tripMapDetail.value = detail
    if (focusedOrderId != null) {
      const stop = (detail.stops || []).find((item) => Number(item.order_id) === Number(focusedOrderId))
      tripMapFocusedStopId.value = stop ? Number(stop.id) : null
    }
    tripMapHeader.value = {
      title: header?.title || detail.route_no || '车次详情',
      subtitle: header?.subtitle || `${detail.vehicle_no || '未定车'} · ${detail.driver_name || '未填司机'} · ${detail.status || '—'}`,
      summaryCards: header?.summaryCards || [
        { label: '车牌', value: detail.vehicle_no || '未定车' },
        { label: '司机', value: detail.driver_name || '未填司机' },
        { label: '状态', value: detail.status || '—' },
        { label: '站点', value: `${(detail.stops || []).length} 站` },
      ],
    }
  } catch (err) {
    tripMapError.value = err?.response?.data?.detail || '车次地图加载失败'
    tripMapVisible.value = false
    if (fallback) setDetail(fallback)
  } finally {
    tripMapLoading.value = false
  }
}

const onTripMapUpdated = (detail) => {
  tripMapDetail.value = detail
}

const openKpiDetail = (card) => {
  const blockedRows = allocationsDetail.value.filter((row) => ['未出库', '未分检', '未随车'].includes(row.business_status))
  const notLoadedRows = allocationsDetail.value.filter((row) => row.business_status === '未随车')
  const arrivedRows = ordersDetail.value.filter((row) => ['收货', '收货确认', '已结算'].includes(row.status))
  const dataByKey = {
    today_orders: {
      conclusion: `今日共有 ${fmt(summary.value.today_orders)} 单配送任务，涉及 ${fmt(allocationsDetail.value.length)} 条分单。`,
      sections: [section('关联订单', orderRows(ordersDetail.value)), section('分单/商品明细', allocationRows(allocationsDetail.value.slice(0, 30)))],
    },
    pending_trips: {
      conclusion: `当前有 ${fmt(summary.value.pending_trips)} 个待发车或有阻塞车次。`,
      sections: [section('车次与司机车辆', tripRows(trips.value.filter((row) => ['待发车', '有阻塞'].includes(row.status))))],
    },
    in_transit_trips: {
      conclusion: `当前有 ${fmt(summary.value.in_transit_trips)} 个车次正在配送，关联 ${fmt(inTransit.value.length)} 个在途订单站点。`,
      sections: [section('在途订单', transitRows(inTransit.value)), section('车次与司机车辆', tripRows(trips.value.filter((row) => row.status === '运输中')))],
    },
    arrived_orders: {
      conclusion: `今日已有 ${fmt(summary.value.arrived_orders)} 单送达，送达率 ${fmtPercent(summary.value.arrival_rate)}。`,
      sections: [section('已送达订单', orderRows(arrivedRows))],
    },
    blocked_allocations: {
      conclusion: `当前还有 ${fmt(summary.value.blocked_allocations)} 条阻塞分单，主要集中在未出库、未分检或未随车。`,
      sections: [section('分单/商品明细', allocationRows(blockedRows)), section('供应商/厂家影响', supplierBlocks.value.map((row) => ({ 供应商: row.supplier_name, 未出库: row.not_shipped, 未分检: row.not_sorted, 未随车: row.not_loaded, 影响订单: `${row.affected_orders} 单`, 影响客户: row.affected_clients?.join('、') || '—' })))],
    },
    not_loaded: {
      conclusion: `当前有 ${fmt(summary.value.not_loaded)} 条分单未随车，需关注是否补送、退货或按实收处理。`,
      sections: [section('未随车商品明细', allocationRows(notLoadedRows))],
    },
    risk_count: {
      conclusion: `当前有 ${fmt(summary.value.risk_count)} 条履约风险，建议优先处理高风险和影响订单较多的事项。`,
      sections: [section('风险原因与处理建议', riskRows(riskEvents.value)), section('关联订单', orderRows(riskEvents.value.flatMap((row) => row.related_orders || [])))],
    },
  }
  const detail = dataByKey[card.key] || dataByKey.today_orders
  setDetail({
    title: detailLabelMap[card.key] || card.label,
    subtitle: card.hint,
    conclusion: detail.conclusion,
    summaryCards: [
      { label: card.label, value: fmt(card.value), tone: card.tone },
      { label: '分检完成率', value: fmtPercent(summary.value.sort_rate), tone: 'good' },
      { label: '送达率', value: fmtPercent(summary.value.arrival_rate), tone: 'good' },
    ],
    sections: detail.sections,
  })
}

const openHubDetail = () => {
  setDetail({
    title: '今日履约总览',
    subtitle: '履约中枢 · 真实闭环聚合',
    conclusion: `今日 ${fmt(summary.value.today_orders)} 单配送任务，分检完成率 ${fmtPercent(summary.value.sort_rate)}，送达率 ${fmtPercent(summary.value.arrival_rate)}，仍有 ${fmt(summary.value.blocked_allocations)} 条阻塞分单。`,
    summaryCards: [
      { label: '今日配送订单', value: `${fmt(summary.value.today_orders)} 单` },
      { label: '分检完成率', value: fmtPercent(summary.value.sort_rate), tone: 'good' },
      { label: '送达率', value: fmtPercent(summary.value.arrival_rate), tone: 'good' },
      { label: '阻塞分单', value: `${fmt(summary.value.blocked_allocations)} 条`, tone: 'danger' },
    ],
    sections: [
      section('关联订单', orderRows(ordersDetail.value)),
      section('分单/商品明细', allocationRows(allocationsDetail.value.slice(0, 30))),
      section('车次与司机车辆', tripRows(trips.value)),
      section('风险原因与处理建议', riskRows(riskEvents.value.slice(0, 12))),
    ],
  })
}

const openFunnelDetail = (item) => {
  const key = item.key
  const completed = {
    shipped: allocationsDetail.value.filter((row) => row.shipment_status === '已出库'),
    sorted: allocationsDetail.value.filter((row) => row.sort_status === '已分检'),
    loaded: allocationsDetail.value.filter((row) => row.load_status === '已装车'),
  }
  const unfinished = {
    shipped: allocationsDetail.value.filter((row) => row.shipment_status !== '已出库'),
    sorted: allocationsDetail.value.filter((row) => row.sort_status !== '已分检'),
    loaded: allocationsDetail.value.filter((row) => row.load_status !== '已装车'),
  }
  const stageSections = key === 'orders' || key === 'allocated'
    ? [section('关联订单', orderRows(ordersDetail.value)), section('分单/商品明细', allocationRows(allocationsDetail.value.slice(0, 30)))]
    : key === 'departed'
      ? [section('已发车车次', tripRows(trips.value.filter((row) => row.status === '运输中' || row.departed_at)))]
      : key === 'arrived'
        ? [section('已送达订单', orderRows(ordersDetail.value.filter((row) => ['收货', '收货确认', '已结算'].includes(row.status))))]
        : [
            section(`${item.label}明细`, allocationRows(completed[key] || [])),
            section(`尚未完成${item.label.replace('已', '')}`, allocationRows(unfinished[key] || [])),
          ]
  setDetail({
    title: item.label,
    subtitle: '履约漏斗阶段',
    conclusion: `当前阶段完成 ${fmt(item.count)} / ${fmt(item.total)}，完成率 ${fmtPercent(item.percent)}。`,
    summaryCards: [
      { label: '阶段完成数', value: fmt(item.count) },
      { label: '阶段总数', value: fmt(item.total) },
      { label: '完成率', value: fmtPercent(item.percent), tone: Number(item.percent || 0) >= 80 ? 'good' : 'warn' },
    ],
    sections: stageSections,
  })
}

const openSupplierDetail = (row) => {
  setDetail({
    title: row.supplier_name || '供应商阻塞',
    subtitle: `影响 ${fmt(row.affected_orders)} 单 · ${Array.isArray(row.affected_clients) ? row.affected_clients.join('、') : '客户待识别'}`,
    conclusion: `该供应商当前有 ${fmt(row.blocked_count)} 条阻塞分单，影响 ${fmt(row.affected_orders)} 个订单。`,
    summaryCards: [
      { label: '未出库', value: fmt(row.not_shipped), tone: row.not_shipped ? 'danger' : '' },
      { label: '未分检', value: fmt(row.not_sorted), tone: row.not_sorted ? 'warn' : '' },
      { label: '未随车', value: fmt(row.not_loaded), tone: row.not_loaded ? 'danger' : '' },
    ],
    sections: [
      section('关联订单', orderRows(row.orders || [])),
      section('分单/商品明细', allocationRows(row.allocations || [])),
      section('供应商/厂家影响', [{ 供应商: row.supplier_name || '—', 影响订单: `${fmt(row.affected_orders)} 单`, 影响客户: row.affected_clients?.join('、') || '—', 关联车次: `${fmt(row.affected_trips)} 个` }]),
    ],
  })
}

const openTripDetail = (row) => {
  const fallback = buildTripDetailFallback(row)
  openTripMapDrawer({
    tripId: row.id,
    header: {
      title: fallback.title,
      subtitle: fallback.subtitle,
      summaryCards: fallback.summaryCards,
    },
    fallback,
  })
}

const openTransitDetail = (row) => {
  const fallback = buildTransitDetailFallback(row)
  openTripMapDrawer({
    tripId: row.trip_id,
    focusedOrderId: row.order_id,
    header: {
      title: row.order_no || fallback.title,
      subtitle: `${row.vehicle_no || '未定车'} · ${row.route_no || '车次待定'}`,
      summaryCards: fallback.summaryCards,
    },
    fallback,
  })
}

const openRiskDetail = (event) => {
  const tripId = resolveTripIdFromRisk(event)
  const fallback = {
    title: event.title || '风险事件',
    subtitle: `${event.business_type || event.type || '履约风险'} · ${event.level_label || '需关注'}`,
    conclusion: event.description || '暂无风险说明',
    summaryCards: [
      { label: '风险类型', value: event.business_type || event.type || '履约风险', tone: toneByLevel(event.level) },
      { label: '风险等级', value: event.level_label || '需关注', tone: toneByLevel(event.level) },
      { label: '发生时间', value: fmtDateTime(event.created_at) },
    ],
    sections: [
      section('风险原因与处理建议', riskRows([event])),
      section('关联订单', orderRows(event.related_orders || [])),
      section('分单/商品明细', allocationRows(event.related_items || [])),
    ],
  }
  if (tripId) {
    openTripMapDrawer({
      tripId,
      header: {
        title: event.title || fallback.title,
        subtitle: `${event.type || '履约风险'} · ${event.vehicle_no || event.description || ''}`,
        summaryCards: fallback.summaryCards,
      },
      fallback,
    })
    return
  }
  setDetail(fallback)
}

const load = async () => {
  loading.value = true
  try {
    data.value = await monitorNeuralLogisticsApi() || {}
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section v-loading="loading" class="fulfillment-monitor">
    <div class="logistics-ambient" aria-hidden="true">
      <i class="logistics-ambient__beam"></i>
      <i class="logistics-ambient__grid"></i>
    </div>

    <header class="fm-hero">
      <div class="fm-heading">
        <p class="eyebrow"><i></i> LOGISTICS INTELLIGENCE / ONLINE</p>
        <h1>今日履约监控</h1>
        <span>按北京时间「今日配送日」订单、分单、车次与风险汇总</span>
      </div>
      <div class="hero-actions">
        <div>
          <small>BEIJING DELIVERY DAY</small>
          <strong>{{ summary.date || data.date || '今日' }}</strong>
        </div>
        <div>
          <small>LAST SYNCHRONIZED</small>
          <strong>{{ fmtDateTime(data.generated_at) }}</strong>
        </div>
        <el-button :icon="Refresh" type="primary" plain round @click="load">刷新数据</el-button>
      </div>
    </header>

    <div class="kpi-grid" aria-label="履约实时遥测">
      <article
        v-for="card in kpiCards"
        :key="card.key"
        class="kpi-card clickable"
        :class="card.tone"
        @click="openKpiDetail(card)"
      >
        <i class="kpi-signal"></i>
        <span>{{ card.label }}</span>
        <strong>{{ fmt(card.value) }}</strong>
        <small>{{ card.hint }}</small>
      </article>
    </div>

    <main class="fm-layout">
      <section class="panel funnel-panel track-panel">
        <div class="panel-title track-title">
          <div>
            <small>FULFILLMENT ORBIT</small>
            <h2>履约调度轨道</h2>
          </div>
          <span>订单从分单到送达的实时推进链路</span>
        </div>
        <div v-if="funnel.length" class="funnel-list" :style="{ '--track-count': funnel.length }">
          <button v-for="item in funnel" :key="item.key" type="button" class="funnel-row clickable-row" @click="openFunnelDetail(item)">
            <i class="track-node"></i>
            <div class="funnel-label">
              <strong>{{ item.label }}</strong>
              <span>{{ fmt(item.count) }} / {{ fmt(item.total) }}</span>
            </div>
            <div class="bar">
              <i :style="{ width: `${Math.max(3, Math.min(Number(item.percent || 0), 100))}%` }" />
            </div>
            <em>{{ fmtPercent(item.percent) }}</em>
          </button>
        </div>
        <el-empty v-else description="今日暂无履约漏斗数据" :image-size="64" />
      </section>

      <section class="panel supplier-panel signal-panel">
        <div class="panel-title">
          <div>
            <small>BLOCKING SIGNALS</small>
            <h2>供应商阻塞</h2>
          </div>
          <span>只统计影响今日履约的阻塞</span>
        </div>
        <div v-if="supplierBlocks.length" class="supplier-list">
          <button v-for="row in supplierBlocks.slice(0, 8)" :key="row.supplier_id" type="button" class="supplier-row clickable-row" @click="openSupplierDetail(row)">
            <i class="row-signal"></i>
            <div class="supplier-main">
              <strong>{{ row.supplier_name }}</strong>
              <span>影响 {{ row.affected_orders }} 单 · {{ row.affected_clients.join('、') || '客户待识别' }}</span>
            </div>
            <div class="block-tags">
              <el-tag type="danger" size="small">未出库 {{ row.not_shipped }}</el-tag>
              <el-tag type="warning" size="small">未分检 {{ row.not_sorted }}</el-tag>
              <el-tag type="info" size="small">未随车 {{ row.not_loaded }}</el-tag>
            </div>
          </button>
        </div>
        <el-empty v-else description="今日暂无供应商阻塞" :image-size="64" />
      </section>

      <section class="hub-panel clickable dispatch-core" role="button" tabindex="0" @click="openHubDetail" @keyup.enter="openHubDetail">
        <div class="hub-bg" />
        <div class="hub-top">
          <div>
            <small>AI DISPATCH CORE</small>
            <span>履约调度核心</span>
          </div>
          <strong><i></i>实时运行</strong>
        </div>
        <div class="hub-core">
          <div class="dispatch-orbit" :class="hubMood" aria-hidden="true">
            <i class="dispatch-orbit__ring dispatch-orbit__ring--outer"></i>
            <i class="dispatch-orbit__ring dispatch-orbit__ring--inner"></i>
            <div class="dispatch-score">
              <strong>{{ hubHealthScore }}</strong>
              <span>HEALTH</span>
            </div>
          </div>
          <b>{{ hubMoodLabel }}</b>
          <span>分检完成率 {{ fmtPercent(summary.sort_rate) }}</span>
        </div>
        <div class="hub-edge hub-edge-left">
          <span>在途车次</span>
          <strong>{{ fmt(summary.in_transit_trips) }}</strong>
        </div>
        <div class="hub-edge hub-edge-right">
          <span>今日配送</span>
          <strong>{{ fmt(summary.today_orders) }} 单</strong>
        </div>
        <div class="hub-edge hub-edge-bottom">
          <span>送达率</span>
          <strong>{{ fmtPercent(summary.arrival_rate) }}</strong>
        </div>
        <div class="hub-metrics">
          <div v-for="item in hubMetrics" :key="item.label">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
      </section>

      <section class="panel wide trips-panel">
        <div class="panel-title">
          <div>
            <small>DISPATCH LEDGER</small>
            <h2>今日车次调度台</h2>
          </div>
          <span>排线日 {{ summary.date || data.date || '今日' }} · 点击车次查看路线与站点</span>
        </div>
        <el-table :data="trips" height="320" class="dark-table clickable-table" @row-click="openTripDetail">
          <el-table-column prop="route_no" label="车次" min-width="130" />
          <el-table-column prop="delivery_name" label="配送商" min-width="160" show-overflow-tooltip />
          <el-table-column label="司机/车辆" min-width="150">
            <template #default="{ row }">
              <strong>{{ row.driver_name || '—' }}</strong>
              <span class="muted"> / {{ row.vehicle_no || '未定车' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="statusTone(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="可发/阻塞/未随车" width="150">
            <template #default="{ row }">{{ row.ready_count }} / {{ row.blocked_count }} / {{ row.not_loaded_count }}</template>
          </el-table-column>
          <el-table-column label="站点" width="90">
            <template #default="{ row }">{{ row.stop_count }} 站</template>
          </el-table-column>
          <el-table-column label="发车时间" min-width="130">
            <template #default="{ row }">{{ row.departed_at ? fmtDateTime(row.departed_at) : row.departure_time || '待定' }}</template>
          </el-table-column>
          <el-table-column label="设备" width="120">
            <template #default="{ row }">北斗 {{ row.beidou_count }} · 视频 {{ row.camera_count }}</template>
          </el-table-column>
        </el-table>
      </section>

      <section class="panel transit-panel signal-panel">
        <div class="panel-title">
          <div>
            <small>IN-TRANSIT STREAM</small>
            <h2>在途订单</h2>
          </div>
          <span>今日配送日在途订单 · 以车次发车与订单状态为准</span>
        </div>
        <div v-if="inTransit.length" class="transit-list">
          <button v-for="row in inTransit.slice(0, 10)" :key="`${row.trip_id}-${row.order_id}`" type="button" class="transit-row clickable-row" @click="openTransitDetail(row)">
            <i class="row-signal"></i>
            <div>
              <strong>{{ row.order_no }}</strong>
              <span>{{ row.client_name }} / {{ row.canteen_name || '食堂待识别' }}</span>
            </div>
            <div>
              <b>{{ row.vehicle_no || '未定车' }}</b>
              <span>{{ row.driver_name || '未填司机' }} · {{ row.expected_delivery_slot || '窗口待定' }}</span>
            </div>
            <el-tag v-if="row.risk" type="warning" size="small">{{ row.risk }}</el-tag>
          </button>
        </div>
        <el-empty v-else description="当前没有配送中订单" :image-size="64" />
      </section>

      <section class="panel risk-panel signal-panel">
        <div class="panel-title">
          <div>
            <small>RISK PULSE</small>
            <h2>风险事件流</h2>
          </div>
          <span>今日配送相关阻塞、未随车、超时和定位缺失</span>
        </div>
        <div v-if="riskEvents.length" class="risk-list">
          <button v-for="event in riskEvents.slice(0, 12)" :key="event.id" type="button" class="risk-row clickable-row" :class="event.level" @click="openRiskDetail(event)">
            <i class="row-signal"></i>
            <el-tag :type="toneByLevel(event.level)" size="small">{{ event.type }}</el-tag>
            <div>
              <strong>{{ event.title }}</strong>
              <span>{{ event.description }}</span>
            </div>
            <time>{{ fmtDateTime(event.created_at) }}</time>
          </button>
        </div>
        <el-empty v-else description="今日暂无履约风险" :image-size="64" />
      </section>
    </main>

    <el-drawer v-model="detailVisible" direction="rtl" size="720px" :title="detailState.title">
      <div class="fm-drawer">
        <p class="drawer-subtitle">{{ detailState.subtitle }}</p>
        <p v-if="detailState.conclusion" class="drawer-desc">{{ detailState.conclusion }}</p>
        <div v-if="detailState.summaryCards.length" class="drawer-metrics">
          <div v-for="item in detailState.summaryCards" :key="`${item.label}-${item.value}`" :class="item.tone">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
        <el-collapse :model-value="detailState.defaultOpen" class="leader-collapse">
          <el-collapse-item v-for="section in detailState.sections" :key="section.title" :name="section.title" :title="section.title">
            <div v-if="section.rows.length" class="leader-list">
              <article v-for="(row, idx) in section.rows" :key="`${section.title}-${idx}`" class="leader-row">
                <div v-for="(value, label) in row" :key="label" class="leader-field">
                  <span>{{ label }}</span>
                  <strong>{{ value || '—' }}</strong>
                </div>
              </article>
            </div>
            <el-empty v-else :description="section.empty || '暂无相关明细'" :image-size="72" />
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-drawer>

    <el-drawer
      v-model="tripMapVisible"
      direction="rtl"
      size="86%"
      destroy-on-close
      :title="tripMapHeader.title || '车次地图'"
      class="fm-trip-map-drawer"
    >
      <div v-loading="tripMapLoading" class="fm-trip-map-drawer-body">
        <p v-if="tripMapHeader.subtitle" class="drawer-subtitle">{{ tripMapHeader.subtitle }}</p>
        <p v-if="tripMapError" class="drawer-desc trip-map-error">{{ tripMapError }}</p>
        <div v-if="tripMapHeader.summaryCards?.length" class="drawer-metrics">
          <div v-for="item in tripMapHeader.summaryCards" :key="`${item.label}-${item.value}`" :class="item.tone">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
        <TripRouteMapCard
          v-if="tripMapDetail"
          v-model:focused-stop-id="tripMapFocusedStopId"
          :trip-detail="tripMapDetail"
          theme="dark"
          @trip-updated="onTripMapUpdated"
        />
        <el-collapse
          v-if="tripMapFallback.sections?.length"
          :model-value="tripMapFallback.defaultOpen?.length ? tripMapFallback.defaultOpen : tripMapFallback.sections.slice(0, 1).map((item) => item.title)"
          class="leader-collapse trip-map-fallback"
        >
          <el-collapse-item v-for="section in tripMapFallback.sections" :key="section.title" :name="section.title" :title="section.title">
            <div v-if="section.rows.length" class="leader-list">
              <article v-for="(row, idx) in section.rows" :key="`${section.title}-${idx}`" class="leader-row">
                <div v-for="(value, label) in row" :key="label" class="leader-field">
                  <span>{{ label }}</span>
                  <strong>{{ value || '—' }}</strong>
                </div>
              </article>
            </div>
            <el-empty v-else :description="section.empty || '暂无相关明细'" :image-size="72" />
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-drawer>
  </section>
</template>

<style scoped>
.fulfillment-monitor {
  min-height: 100vh;
  padding: 72px 28px 32px 126px;
  color: #dfe7ff;
  background:
    radial-gradient(circle at 30% 5%, rgba(0, 218, 243, 0.15), transparent 32%),
    radial-gradient(circle at 80% 18%, rgba(124, 58, 237, 0.18), transparent 30%),
    #0f131f;
  box-sizing: border-box;
}

.fm-hero,
.panel,
.kpi-card,
.hub-panel {
  border: 1px solid rgba(0, 218, 243, 0.16);
  background: linear-gradient(145deg, rgba(15, 23, 42, 0.86), rgba(8, 13, 24, 0.78));
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(12px);
}

.fm-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  padding: 22px 24px;
  border-radius: 8px;
}

.eyebrow {
  margin: 0 0 8px;
  color: #67e8f9;
  font: 700 12px/1 "JetBrains Mono", monospace;
  letter-spacing: 0;
}

.fm-hero h1 {
  margin: 0 0 8px;
  font-size: 30px;
  letter-spacing: 0;
}

.fm-hero span,
.hero-actions,
.panel-title span,
.muted {
  color: #94a3b8;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  white-space: nowrap;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 12px;
  margin: 16px 0;
}

.kpi-card {
  min-height: 112px;
  padding: 16px;
  border-radius: 8px;
  text-align: left;
}

.kpi-card span,
.kpi-card small {
  display: block;
  color: #94a3b8;
}

.kpi-card strong {
  display: block;
  margin: 10px 0 8px;
  color: #f8fafc;
  font-size: 30px;
}

.kpi-card.good strong { color: #5eead4; }
.kpi-card.warn strong { color: #fbbf24; }
.kpi-card.danger strong { color: #fb7185; }

.clickable {
  cursor: pointer;
  transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease;
}

.clickable:hover,
.clickable-row:hover {
  border-color: rgba(103, 232, 249, .46);
  box-shadow: 0 0 0 1px rgba(103, 232, 249, .08), 0 18px 36px rgba(14, 165, 233, .08);
  transform: translateY(-1px);
}

.clickable-row {
  width: 100%;
  color: inherit;
  font: inherit;
  text-align: left;
  border: 0;
  cursor: pointer;
  transition: border-color .18s ease, background .18s ease, transform .18s ease;
}

.fm-layout {
  display: grid;
  grid-template-columns: 1.05fr 1fr 1.12fr;
  gap: 16px;
}

.panel {
  min-height: 360px;
  padding: 18px;
  border-radius: 8px;
  overflow: hidden;
}

.panel.wide {
  grid-column: span 2;
}

.panel-title {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
  margin-bottom: 16px;
}

.panel-title h2 {
  margin: 0;
  color: #f8fafc;
  font-size: 18px;
}

.funnel-list,
.supplier-list,
.transit-list,
.risk-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.funnel-row {
  display: grid;
  grid-template-columns: 150px 1fr 58px;
  gap: 12px;
  align-items: center;
  padding: 6px;
  border-radius: 8px;
  background: transparent;
}

.funnel-label strong,
.funnel-label span {
  display: block;
}

.funnel-label span {
  color: #94a3b8;
  font-size: 12px;
}

.bar {
  height: 10px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.14);
  overflow: hidden;
}

.bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #22d3ee, #8b5cf6);
}

.funnel-row em {
  color: #67e8f9;
  font-style: normal;
  text-align: right;
}

.supplier-row,
.transit-row,
.risk-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  min-height: 78px;
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.54);
}

.supplier-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
  line-height: 1.35;
}

.supplier-row strong,
.supplier-row span,
.transit-row strong,
.transit-row span,
.risk-row strong,
.risk-row span {
  display: block;
}

.supplier-row span,
.transit-row span,
.risk-row span,
.risk-row time {
  color: #94a3b8;
  font-size: 12px;
}

.block-tags {
  width: 176px;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  align-content: center;
  gap: 6px;
}

.hub-panel {
  position: relative;
  min-height: 360px;
  padding: 20px;
  border-radius: 8px;
  overflow: hidden;
  background:
    radial-gradient(circle at center, rgba(34, 211, 238, .22), transparent 28%),
    linear-gradient(145deg, rgba(22, 16, 52, .86), rgba(8, 13, 24, .82));
}

.hub-bg {
  position: absolute;
  inset: 0;
  opacity: .72;
  background:
    radial-gradient(circle at 50% 54%, rgba(103, 232, 249, .34) 0 2px, transparent 3px),
    radial-gradient(circle at 36% 46%, rgba(103, 232, 249, .22) 0 2px, transparent 3px),
    radial-gradient(circle at 64% 44%, rgba(139, 92, 246, .28) 0 2px, transparent 3px),
    linear-gradient(120deg, transparent 22%, rgba(103, 232, 249, .14) 22.3%, transparent 22.8%, transparent 56%, rgba(103, 232, 249, .11) 56.3%, transparent 56.9%),
    linear-gradient(60deg, transparent 25%, rgba(139, 92, 246, .14) 25.3%, transparent 25.8%, transparent 68%, rgba(103, 232, 249, .13) 68.2%, transparent 68.8%);
  filter: blur(.1px);
}

.hub-bg::after {
  content: '';
  position: absolute;
  left: 8%;
  right: 8%;
  bottom: 8%;
  height: 48%;
  border-radius: 50% 50% 0 0;
  border-top: 1px solid rgba(103, 232, 249, .28);
  background: radial-gradient(ellipse at center bottom, rgba(103, 232, 249, .18), transparent 68%);
  transform: perspective(420px) rotateX(58deg);
}

.hub-top,
.hub-core,
.hub-edge,
.hub-metrics {
  position: relative;
  z-index: 1;
}

.hub-top {
  display: flex;
  justify-content: space-between;
  color: #93c5fd;
  font-size: 13px;
}

.hub-top strong {
  color: #5eead4;
}

.hub-core {
  position: absolute;
  inset: 90px 24px auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
}

.hub-face {
  position: relative;
  width: 58px;
  height: 46px;
  border-radius: 14px 14px 10px 10px;
  background: linear-gradient(180deg, #dffbff, #7dd3fc);
  box-shadow: 0 0 36px rgba(103, 232, 249, .46);
  transition: background .18s ease, box-shadow .18s ease;
}

.hub-face.happy {
  background: linear-gradient(180deg, #e9fff7, #5eead4);
  box-shadow: 0 0 38px rgba(94, 234, 212, .48);
}

.hub-face.sad {
  background: linear-gradient(180deg, #ffe4ea, #fb7185);
  box-shadow: 0 0 38px rgba(251, 113, 133, .42);
}

.hub-face .eye {
  position: absolute;
  top: 17px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #0f172a;
}

.hub-face .eye.left {
  left: 15px;
}

.hub-face .eye.right {
  right: 15px;
}

.hub-face .mouth {
  position: absolute;
  left: 16px;
  top: 28px;
  width: 26px;
  height: 10px;
  border-bottom: 5px solid #0f172a;
  border-radius: 4px;
}

.hub-face.happy .mouth {
  top: 23px;
  height: 14px;
  border-bottom: 5px solid #0f172a;
  border-radius: 0 0 18px 18px;
}

.hub-face.neutral .mouth {
  top: 31px;
  height: 5px;
  border-bottom: 5px solid #0f172a;
  border-radius: 4px;
}

.hub-face.sad .mouth {
  top: 30px;
  height: 14px;
  border-bottom: 0;
  border-top: 5px solid #0f172a;
  border-radius: 18px 18px 0 0;
}

.hub-core b {
  color: #f8fafc;
  font-size: 28px;
  letter-spacing: 0;
}

.hub-core span,
.hub-edge span,
.hub-metrics span {
  color: #94a3b8;
}

.hub-edge {
  position: absolute;
  padding-left: 12px;
  border-left: 3px solid rgba(103, 232, 249, .86);
}

.hub-edge strong {
  display: block;
  margin-top: 6px;
  color: #dffbff;
  font-size: 26px;
}

.hub-edge-left {
  left: 20px;
  top: 64px;
}

.hub-edge-right {
  right: 20px;
  bottom: 76px;
  border-color: rgba(216, 180, 254, .86);
}

.hub-edge-bottom {
  left: 20px;
  bottom: 70px;
  border-color: rgba(94, 234, 212, .86);
}

.hub-metrics {
  position: absolute;
  left: 18px;
  right: 18px;
  bottom: 16px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.hub-metrics div {
  padding: 10px;
  border: 1px solid rgba(148, 163, 184, .16);
  border-radius: 8px;
  background: rgba(15, 23, 42, .62);
}

.hub-metrics span,
.hub-metrics strong {
  display: block;
}

.hub-metrics strong {
  margin-top: 4px;
  color: #67e8f9;
}

.risk-row {
  justify-content: flex-start;
}

.risk-row > div {
  flex: 1;
  min-width: 0;
}

.risk-row.high {
  border-color: rgba(248, 113, 113, 0.34);
}

.risk-row.medium {
  border-color: rgba(251, 191, 36, 0.28);
}

.dark-table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(15, 23, 42, 0.85);
  --el-table-row-hover-bg-color: rgba(14, 165, 233, 0.12);
  --el-table-border-color: rgba(148, 163, 184, 0.16);
  --el-table-text-color: #dbeafe;
  --el-table-header-text-color: #93c5fd;
}

:deep(.clickable-table .el-table__row) {
  cursor: pointer;
}

:deep(.clickable-table .el-table__row:hover td) {
  background: rgba(14, 165, 233, .12) !important;
}

:deep(.el-empty__description p) {
  color: #94a3b8;
}

:deep(.el-drawer) {
  background: #08111f;
  color: #e6f1ff;
}

:deep(.el-drawer__header) {
  margin-bottom: 0;
  border-bottom: 1px solid rgba(103, 232, 249, .14);
}

:deep(.el-drawer__title) {
  color: #e6f1ff;
  font-weight: 800;
}

:deep(.el-drawer__close-btn) {
  color: #9cf0ff;
}

.fm-drawer {
  min-height: 100%;
  padding: 20px;
  color: #dfe7ff;
  background:
    radial-gradient(circle at 20% 0, rgba(34, 211, 238, .12), transparent 28%),
    #08111f;
}

.fm-trip-map-drawer-body {
  min-height: 100%;
  padding: 20px;
  color: #dfe7ff;
  background:
    radial-gradient(circle at 20% 0, rgba(34, 211, 238, .12), transparent 28%),
    #08111f;
}

.trip-map-fallback {
  margin-top: 18px;
}

.trip-map-error {
  color: #fb7185;
}

.drawer-subtitle {
  margin: 0 0 10px;
  color: #67e8f9;
  font: 700 12px/1.4 "JetBrains Mono", monospace;
}

.drawer-desc {
  margin: 0 0 16px;
  color: #a6b4ca;
  line-height: 1.7;
}

.drawer-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.drawer-metrics div {
  padding: 14px;
  border: 1px solid rgba(103, 232, 249, .18);
  border-radius: 8px;
  background: rgba(15, 23, 42, .72);
}

.drawer-metrics span,
.drawer-metrics strong {
  display: block;
}

.drawer-metrics span {
  color: #94a3b8;
  font-size: 12px;
}

.drawer-metrics strong {
  margin-top: 8px;
  color: #dffbff;
  font-size: 24px;
}

.drawer-metrics .good strong { color: #5eead4; }
.drawer-metrics .warn strong { color: #fbbf24; }
.drawer-metrics .danger strong { color: #fb7185; }

.drawer-table {
  display: grid;
  gap: 10px;
}

.drawer-row {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 12px;
  align-items: center;
  padding: 12px;
  border: 1px solid rgba(148, 163, 184, .14);
  border-radius: 8px;
  background: rgba(15, 23, 42, .56);
}

.drawer-row span {
  color: #94a3b8;
  font-size: 12px;
}

.drawer-row strong {
  min-width: 0;
  color: #f8fafc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.leader-collapse {
  --el-collapse-border-color: rgba(103, 232, 249, .16);
  --el-collapse-header-bg-color: rgba(15, 23, 42, .72);
  --el-collapse-content-bg-color: rgba(8, 17, 31, .86);
  --el-collapse-header-text-color: #dffbff;
  --el-collapse-content-text-color: #dfe7ff;
  border-top: 1px solid rgba(103, 232, 249, .16);
  border-bottom: 1px solid rgba(103, 232, 249, .16);
}

:deep(.leader-collapse .el-collapse-item__header) {
  padding: 0 14px;
  color: #dffbff;
  font-weight: 800;
  letter-spacing: 0;
}

:deep(.leader-collapse .el-collapse-item__content) {
  padding: 14px;
}

.leader-list {
  display: grid;
  gap: 12px;
}

.leader-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 14px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, .14);
  border-radius: 8px;
  background: rgba(15, 23, 42, .58);
}

.leader-field {
  min-width: 0;
}

.leader-field span,
.leader-field strong {
  display: block;
}

.leader-field span {
  margin-bottom: 5px;
  color: #94a3b8;
  font-size: 12px;
}

.leader-field strong {
  color: #eef6ff;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

@media (max-width: 1440px) {
  .kpi-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .fm-layout {
    grid-template-columns: 1fr 1fr;
  }

  .hub-panel,
  .panel.wide {
    grid-column: span 2;
  }
}
</style>

<style scoped>
.fulfillment-monitor {
  --fm-bg: #08111f;
  --fm-panel: rgba(8, 17, 31, 0.78);
  --fm-line: rgba(0, 229, 255, 0.14);
  --fm-cyan: #00e5ff;
  --fm-mint: #68fadd;
  --fm-amber: #fbbf24;
  --fm-danger: #fb7185;
  position: relative;
  isolation: isolate;
  min-height: 100vh;
  padding: 22px 28px 42px 42px;
  overflow: hidden;
  color: #dfe7ff;
  background:
    radial-gradient(circle at 26% -10%, rgba(0, 229, 255, 0.11), transparent 34%),
    linear-gradient(118deg, #060c16, #08111f 48%, #07131f);
}

.fulfillment-monitor::before {
  content: "";
  position: fixed;
  inset: 0;
  z-index: -3;
  pointer-events: none;
  opacity: 0.22;
  background-image:
    linear-gradient(rgba(0, 229, 255, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 229, 255, 0.045) 1px, transparent 1px);
  background-size: 64px 64px;
  mask-image: linear-gradient(to bottom, black, transparent 84%);
}

.logistics-ambient,
.logistics-ambient i {
  position: fixed;
  pointer-events: none;
}

.logistics-ambient {
  inset: 0;
  z-index: -2;
  overflow: hidden;
}

.logistics-ambient__beam {
  top: 3%;
  right: 6%;
  width: 42vw;
  height: 42vw;
  border-radius: 50%;
  background: rgba(14, 165, 233, 0.09);
  filter: blur(110px);
  animation: fm-ambient 14s ease-in-out infinite alternate;
}

.logistics-ambient__grid {
  inset: 0;
  background:
    radial-gradient(circle at 74% 26%, rgba(104, 250, 221, 0.07), transparent 23%),
    linear-gradient(105deg, transparent 45%, rgba(0, 229, 255, 0.025) 45.2%, transparent 45.4%);
}

.fm-hero {
  position: relative;
  z-index: 2;
  display: grid;
  grid-template-columns: minmax(360px, 1fr) auto;
  align-items: end;
  gap: 32px;
  min-height: 112px;
  padding: 4px 8px 20px;
  border: 0;
  border-bottom: 1px solid rgba(0, 229, 255, 0.13);
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
}

.eyebrow {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 0 0 9px;
  color: rgba(128, 232, 255, 0.66);
  font: 700 10px/1.2 "JetBrains Mono", monospace;
  letter-spacing: 0.18em;
}

.eyebrow i,
.hero-actions::before {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--fm-mint);
  box-shadow: 0 0 13px rgba(104, 250, 221, 0.84);
  animation: fm-pulse 1.8s ease-in-out infinite;
}

.fm-hero h1 {
  margin: 0;
  color: #f4f8ff;
  font-size: clamp(31px, 2.7vw, 44px);
  font-weight: 650;
  letter-spacing: -0.055em;
}

.fm-heading > span {
  display: block;
  margin-top: 7px;
  color: rgba(190, 205, 228, 0.48);
  font-size: 13px;
}

.hero-actions {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0;
  color: inherit;
}

.hero-actions::before {
  content: "";
  margin-right: 16px;
}

.hero-actions > div {
  min-width: 164px;
  padding: 5px 18px;
  border-left: 1px solid rgba(0, 229, 255, 0.12);
}

.hero-actions small,
.hero-actions strong {
  display: block;
}

.hero-actions small {
  margin-bottom: 6px;
  color: rgba(109, 216, 240, 0.38);
  font: 700 9px/1 "JetBrains Mono", monospace;
  letter-spacing: 0.12em;
}

.hero-actions strong {
  color: rgba(226, 240, 250, 0.76);
  font: 500 12px/1.2 "JetBrains Mono", monospace;
}

.hero-actions :deep(.el-button) {
  height: 38px;
  margin-left: 14px;
  border-color: rgba(0, 229, 255, 0.28);
  color: #bffcff;
  background: rgba(0, 229, 255, 0.055);
}

.hero-actions :deep(.el-button:hover) {
  border-color: rgba(0, 229, 255, 0.56);
  color: #07151d;
  background: var(--fm-cyan);
}

.kpi-grid {
  position: relative;
  z-index: 2;
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 0;
  margin: 0 0 18px;
  border-bottom: 1px solid rgba(0, 229, 255, 0.11);
}

.kpi-card {
  position: relative;
  min-height: 104px;
  padding: 17px 18px 14px;
  overflow: hidden;
  border: 0;
  border-left: 1px solid rgba(0, 229, 255, 0.1);
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
}

.kpi-card:first-child {
  border-left: 0;
}

.kpi-signal {
  position: absolute;
  top: 18px;
  right: 16px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--fm-cyan);
  box-shadow: 0 0 11px rgba(0, 229, 255, 0.72);
}

.kpi-card.good .kpi-signal {
  background: var(--fm-mint);
}

.kpi-card.warn .kpi-signal {
  background: var(--fm-amber);
  box-shadow: 0 0 11px rgba(251, 191, 36, 0.64);
}

.kpi-card.danger .kpi-signal {
  background: var(--fm-danger);
  box-shadow: 0 0 11px rgba(251, 113, 133, 0.64);
}

.kpi-card span,
.kpi-card small {
  color: rgba(179, 197, 220, 0.48);
}

.kpi-card span {
  font-size: 11px;
}

.kpi-card strong {
  margin: 9px 0 5px;
  color: #eef7ff;
  font: 500 30px/1 "JetBrains Mono", monospace;
  letter-spacing: -0.06em;
}

.kpi-card small {
  overflow: hidden;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kpi-card.good strong { color: var(--fm-mint); }
.kpi-card.warn strong { color: var(--fm-amber); }
.kpi-card.danger strong { color: var(--fm-danger); }

.clickable:hover,
.clickable-row:hover {
  border-color: rgba(0, 229, 255, 0.34);
  background-color: rgba(0, 229, 255, 0.035);
  box-shadow: none;
  transform: none;
}

.fm-layout {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 18px;
}

.panel,
.hub-panel {
  min-height: 0;
  border: 1px solid rgba(0, 229, 255, 0.12);
  border-radius: 9px 24px 9px 24px;
  background: linear-gradient(130deg, rgba(10, 22, 38, 0.76), rgba(7, 15, 27, 0.62));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.035),
    0 24px 70px rgba(0, 0, 0, 0.18);
  backdrop-filter: blur(18px);
}

.panel {
  padding: 20px;
}

.panel-title {
  align-items: flex-end;
  margin-bottom: 18px;
}

.panel-title > div > small,
.hub-top small {
  display: block;
  margin-bottom: 5px;
  color: rgba(111, 222, 245, 0.42);
  font: 700 9px/1 "JetBrains Mono", monospace;
  letter-spacing: 0.18em;
}

.panel-title h2 {
  color: #edf6ff;
  font-size: 19px;
  letter-spacing: -0.02em;
}

.panel-title > span {
  color: rgba(178, 195, 218, 0.42);
  font-size: 10px;
}

.track-panel {
  grid-column: 1 / 9;
  grid-row: 1;
  min-height: 350px;
  overflow: hidden;
  padding: 22px 24px;
}

.funnel-list {
  position: relative;
  display: grid;
  grid-template-columns: repeat(var(--track-count), minmax(86px, 1fr));
  gap: 0;
  min-height: 235px;
  padding: 24px 2px 0;
}

.funnel-list::before {
  content: "";
  position: absolute;
  left: 5%;
  right: 5%;
  top: 68px;
  height: 2px;
  background:
    linear-gradient(90deg, rgba(0, 229, 255, 0.16), rgba(0, 229, 255, 0.88), rgba(104, 250, 221, 0.7));
  box-shadow: 0 0 16px rgba(0, 229, 255, 0.32);
}

.funnel-list::after {
  content: "";
  position: absolute;
  left: 5%;
  top: 64px;
  width: 54px;
  height: 10px;
  border-radius: 999px;
  background: linear-gradient(90deg, transparent, rgba(229, 253, 255, 0.95), transparent);
  filter: blur(2px);
  animation: fm-track-travel 4.8s linear infinite;
}

.funnel-row {
  position: relative;
  z-index: 1;
  display: flex;
  min-width: 0;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  gap: 9px;
  padding: 0 8px 12px;
  border-radius: 9px;
  text-align: center;
}

.track-node {
  width: 16px;
  height: 16px;
  margin-top: 22px;
  border: 4px solid #0a1727;
  border-radius: 50%;
  background: var(--fm-cyan);
  box-shadow:
    0 0 0 1px rgba(0, 229, 255, 0.54),
    0 0 18px rgba(0, 229, 255, 0.72);
}

.funnel-row:last-child .track-node {
  background: var(--fm-mint);
  box-shadow:
    0 0 0 1px rgba(104, 250, 221, 0.54),
    0 0 18px rgba(104, 250, 221, 0.72);
}

.funnel-label strong {
  overflow: hidden;
  color: #eaf5ff;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.funnel-label span {
  margin-top: 4px;
  color: rgba(178, 197, 220, 0.45);
  font: 500 10px/1.2 "JetBrains Mono", monospace;
}

.funnel-row .bar {
  width: 100%;
  height: 3px;
  background: rgba(132, 164, 185, 0.12);
}

.funnel-row .bar i {
  background: linear-gradient(90deg, var(--fm-cyan), var(--fm-mint));
  box-shadow: 0 0 8px rgba(0, 229, 255, 0.24);
}

.funnel-row em {
  color: rgba(128, 235, 250, 0.76);
  font: 600 12px/1 "JetBrains Mono", monospace;
}

.dispatch-core {
  grid-column: 9 / 13;
  grid-row: 1;
  min-height: 350px;
  padding: 20px;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 46%, rgba(0, 229, 255, 0.13), transparent 32%),
    linear-gradient(145deg, rgba(8, 24, 39, 0.88), rgba(6, 14, 26, 0.88));
}

.hub-bg {
  opacity: 0.48;
  background:
    radial-gradient(circle at 50% 48%, rgba(104, 250, 221, 0.24) 0 2px, transparent 3px),
    radial-gradient(circle at 24% 34%, rgba(0, 229, 255, 0.2) 0 2px, transparent 3px),
    radial-gradient(circle at 78% 64%, rgba(0, 229, 255, 0.18) 0 2px, transparent 3px),
    linear-gradient(120deg, transparent 24%, rgba(0, 229, 255, 0.1) 24.2%, transparent 24.6%, transparent 68%, rgba(104, 250, 221, 0.09) 68.2%, transparent 68.6%);
}

.hub-bg::after {
  border-color: rgba(0, 229, 255, 0.2);
  background: radial-gradient(ellipse at center bottom, rgba(0, 229, 255, 0.12), transparent 68%);
}

.hub-top {
  align-items: flex-start;
}

.hub-top span {
  color: #eaf6ff;
  font-size: 17px;
  font-weight: 650;
}

.hub-top strong {
  display: flex;
  align-items: center;
  gap: 7px;
  color: rgba(104, 250, 221, 0.72);
  font: 700 10px/1 "JetBrains Mono", monospace;
}

.hub-top strong i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--fm-mint);
  box-shadow: 0 0 12px rgba(104, 250, 221, 0.8);
}

.hub-core {
  inset: 62px 24px auto;
  gap: 6px;
}

.dispatch-orbit {
  position: relative;
  width: 152px;
  height: 152px;
  display: grid;
  place-items: center;
  margin-bottom: 3px;
}

.dispatch-orbit::before {
  content: "";
  position: absolute;
  inset: 21%;
  border-radius: 50%;
  background: rgba(0, 229, 255, 0.12);
  filter: blur(20px);
  animation: fm-core-breathe 3.8s ease-in-out infinite;
}

.dispatch-orbit__ring {
  position: absolute;
  border-radius: 50%;
}

.dispatch-orbit__ring--outer {
  inset: 0;
  border: 1px solid rgba(0, 229, 255, 0.25);
  border-left-color: rgba(104, 250, 221, 0.9);
  border-right-color: transparent;
  animation: fm-spin 10s linear infinite;
}

.dispatch-orbit__ring--outer::after {
  content: "";
  position: absolute;
  left: 10px;
  top: 30px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--fm-mint);
  box-shadow: 0 0 14px rgba(104, 250, 221, 0.88);
}

.dispatch-orbit__ring--inner {
  inset: 15%;
  border: 1px dashed rgba(0, 229, 255, 0.25);
  animation: fm-spin-reverse 15s linear infinite;
}

.dispatch-score {
  position: relative;
  z-index: 1;
  width: 82px;
  height: 82px;
  display: grid;
  place-content: center;
  border: 1px solid rgba(0, 229, 255, 0.32);
  border-radius: 50%;
  background: radial-gradient(circle at 40% 32%, rgba(227, 254, 255, 0.16), rgba(0, 229, 255, 0.08) 45%, rgba(4, 18, 30, 0.9));
  box-shadow:
    inset 0 0 20px rgba(0, 229, 255, 0.12),
    0 0 28px rgba(0, 229, 255, 0.12);
}

.dispatch-score strong,
.dispatch-score span {
  display: block;
  text-align: center;
}

.dispatch-score strong {
  color: #dffcff;
  font: 500 28px/1 "JetBrains Mono", monospace;
}

.dispatch-score span {
  margin-top: 4px;
  color: rgba(104, 250, 221, 0.48);
  font: 700 8px/1 "JetBrains Mono", monospace;
  letter-spacing: 0.15em;
}

.dispatch-orbit.sad .dispatch-score {
  border-color: rgba(251, 113, 133, 0.48);
  box-shadow: inset 0 0 20px rgba(251, 113, 133, 0.1), 0 0 28px rgba(251, 113, 133, 0.12);
}

.dispatch-orbit.neutral .dispatch-score {
  border-color: rgba(251, 191, 36, 0.42);
}

.hub-core b {
  color: #eff9ff;
  font-size: 18px;
}

.hub-core > span {
  color: rgba(178, 198, 220, 0.48);
  font-size: 10px;
}

.hub-edge {
  padding-left: 9px;
  border-left-width: 2px;
  border-color: rgba(0, 229, 255, 0.56);
}

.hub-edge span {
  color: rgba(175, 197, 219, 0.42);
  font-size: 10px;
}

.hub-edge strong {
  margin-top: 3px;
  color: #dffbff;
  font: 500 20px/1.2 "JetBrains Mono", monospace;
}

.hub-edge-left {
  left: 18px;
  top: 86px;
}

.hub-edge-right {
  right: 18px;
  bottom: 100px;
  border-color: rgba(104, 250, 221, 0.6);
}

.hub-edge-bottom {
  left: 18px;
  bottom: 100px;
  border-color: rgba(104, 250, 221, 0.6);
}

.hub-metrics {
  left: 16px;
  right: 16px;
  bottom: 14px;
  gap: 6px;
}

.hub-metrics div {
  padding: 8px 9px;
  border-color: rgba(0, 229, 255, 0.1);
  border-radius: 6px;
  background: rgba(5, 18, 30, 0.64);
}

.hub-metrics span {
  color: rgba(173, 195, 216, 0.38);
  font-size: 9px;
}

.hub-metrics strong {
  color: var(--fm-mint);
  font: 600 11px/1.2 "JetBrains Mono", monospace;
}

.supplier-panel {
  grid-column: 1 / 5;
  grid-row: 2;
  min-height: 382px;
}

.panel.wide.trips-panel {
  grid-column: 5 / 13;
  grid-row: 2;
  min-height: 382px;
}

.transit-panel {
  grid-column: 1 / 7;
  grid-row: 3;
  min-height: 350px;
}

.risk-panel {
  grid-column: 7 / 13;
  grid-row: 3;
  min-height: 350px;
}

.signal-panel {
  overflow: hidden;
}

.supplier-list,
.transit-list,
.risk-list {
  gap: 0;
  max-height: 292px;
  overflow: auto;
}

.supplier-row,
.transit-row,
.risk-row {
  position: relative;
  min-height: 62px;
  padding: 11px 4px 11px 17px;
  border: 0;
  border-bottom: 1px solid rgba(0, 229, 255, 0.075);
  border-radius: 0;
  background: transparent;
}

.row-signal {
  position: absolute;
  left: 1px;
  top: 50%;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--fm-cyan);
  box-shadow: 0 0 9px rgba(0, 229, 255, 0.68);
  transform: translateY(-50%);
}

.supplier-row .row-signal,
.risk-row.high .row-signal {
  background: var(--fm-danger);
  box-shadow: 0 0 9px rgba(251, 113, 133, 0.68);
}

.risk-row.medium .row-signal {
  background: var(--fm-amber);
  box-shadow: 0 0 9px rgba(251, 191, 36, 0.68);
}

.supplier-main {
  gap: 5px;
}

.supplier-row strong,
.transit-row strong,
.risk-row strong {
  color: rgba(235, 243, 255, 0.86);
  font-size: 12px;
}

.supplier-row span,
.transit-row span,
.risk-row span,
.risk-row time {
  color: rgba(171, 192, 214, 0.43);
  font-size: 10px;
}

.block-tags {
  width: 156px;
  gap: 4px;
}

.signal-panel :deep(.el-tag) {
  border-color: rgba(148, 163, 184, 0.14);
  background: rgba(15, 23, 42, 0.42);
  font-size: 9px;
}

.trips-panel :deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(6, 21, 35, 0.78);
  --el-table-row-hover-bg-color: rgba(0, 229, 255, 0.055);
  --el-table-border-color: rgba(0, 229, 255, 0.075);
  --el-table-text-color: rgba(225, 236, 249, 0.72);
  --el-table-header-text-color: rgba(126, 218, 239, 0.6);
  font-size: 11px;
}

.trips-panel :deep(.el-table th.el-table__cell) {
  font: 600 10px/1 "JetBrains Mono", monospace;
  letter-spacing: 0.05em;
}

.trips-panel :deep(.el-table td.el-table__cell) {
  border-bottom-color: rgba(0, 229, 255, 0.07);
}

.trips-panel :deep(.el-table__inner-wrapper::before) {
  display: none;
}

.fulfillment-monitor :deep(.el-empty__image) {
  opacity: 0.28;
}

.fulfillment-monitor :deep(.el-empty__description p) {
  color: rgba(167, 190, 214, 0.36);
  font-size: 11px;
}

@keyframes fm-track-travel {
  from { left: 5%; opacity: 0; }
  8% { opacity: 1; }
  92% { opacity: 1; }
  to { left: calc(95% - 54px); opacity: 0; }
}

@keyframes fm-spin { to { transform: rotate(360deg); } }
@keyframes fm-spin-reverse { to { transform: rotate(-360deg); } }
@keyframes fm-core-breathe { 50% { transform: scale(1.28); opacity: 0.62; } }
@keyframes fm-pulse { 50% { opacity: 0.35; transform: scale(0.72); } }
@keyframes fm-ambient { to { transform: translate(-5vw, 4vh) scale(1.1); } }

@media (prefers-reduced-motion: reduce) {
  .fulfillment-monitor *,
  .fulfillment-monitor *::before,
  .fulfillment-monitor *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}

@media (max-width: 1500px) {
  .fulfillment-monitor {
    padding-left: 30px;
  }

  .kpi-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .kpi-card:nth-child(5) {
    border-left: 0;
  }

  .track-panel {
    grid-column: 1 / 13;
    grid-row: 1;
  }

  .dispatch-core {
    grid-column: 1 / 5;
    grid-row: 2;
  }

  .supplier-panel {
    grid-column: 5 / 9;
    grid-row: 2;
  }

  .transit-panel {
    grid-column: 9 / 13;
    grid-row: 2;
  }

  .panel.wide.trips-panel {
    grid-column: 1 / 9;
    grid-row: 3;
  }

  .risk-panel {
    grid-column: 9 / 13;
    grid-row: 3;
  }
}

@media (max-width: 1050px) {
  .fm-hero {
    grid-template-columns: 1fr;
  }

  .hero-actions {
    flex-wrap: wrap;
  }

  .fm-layout {
    grid-template-columns: 1fr 1fr;
  }

  .track-panel,
  .dispatch-core,
  .supplier-panel,
  .transit-panel,
  .risk-panel {
    grid-column: auto;
    grid-row: auto;
  }

  .track-panel,
  .panel.wide.trips-panel {
    grid-column: 1 / -1;
    grid-row: auto;
  }

  .funnel-list {
    overflow-x: auto;
    grid-template-columns: repeat(var(--track-count), minmax(110px, 1fr));
  }
}

@media (max-width: 720px) {
  .fulfillment-monitor {
    padding: 18px 14px 110px;
  }

  .kpi-grid,
  .fm-layout {
    grid-template-columns: 1fr;
  }

  .kpi-card,
  .kpi-card:nth-child(5) {
    border-left: 0;
    border-bottom: 1px solid rgba(0, 229, 255, 0.08);
  }

  .track-panel,
  .panel.wide.trips-panel {
    grid-column: auto;
  }

  .hero-actions > div {
    min-width: 140px;
    padding-left: 12px;
  }
}
</style>
