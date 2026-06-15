<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { monitorAuditChainApi, monitorOrderAuditApi, monitorOrdersApi } from '../../api/monitor'
import { formatChinaDateTime } from '../../utils/datetime'
import { MAIN_ORDER_STATUS_OPTIONS, orderStatusLabel, orderStatusTagColor } from '../../utils/orderStatus'
import EventDetailView from '../../components/monitor/EventDetailView.vue'

const loading = ref(true)
const loadError = ref('')

// —— 全部订单溯源（驾驶舱内深色抽屉，替代旧版浅色 /monitor/orders 页）——
const ordersDrawerVisible = ref(false)
const ordersList = ref([])
const ordersLoading = ref(false)
const ordersLoaded = ref(false)
const ofStatus = ref('')
const ofOrderNo = ref('')
const ofStart = ref('')
const ofEnd = ref('')

const loadOrders = async () => {
  ordersLoading.value = true
  try {
    ordersList.value = await monitorOrdersApi({
      status: ofStatus.value || undefined,
      order_no: ofOrderNo.value?.trim() || undefined,
      created_date_start: ofStart.value || undefined,
      created_date_end: ofEnd.value || undefined,
    })
    ordersLoaded.value = true
  } finally {
    ordersLoading.value = false
  }
}

const resetOrderFilter = () => {
  ofStatus.value = ''
  ofOrderNo.value = ''
  ofStart.value = ''
  ofEnd.value = ''
  loadOrders()
}

const goAllOrders = () => {
  ordersDrawerVisible.value = true
  if (!ordersLoaded.value) loadOrders()
}
const payload = ref({})
const stageDrawerVisible = ref(false)
const orderDrawerVisible = ref(false)
const activeStage = ref(null)
const activeOrder = ref(null)
const activeOrderLoading = ref(false)
const activeOrderError = ref('')
const activeOrderEvidence = ref([])
const chartRef = ref(null)
const gaugeRef = ref(null)
let trendChart = null
let gaugeChart = null
let resizeObserver = null

const stageIconMap = {
  order_create: 'ORD',
  allocation: 'SPL',
  supplier_ship: 'OUT',
  delivery: 'LOG',
  receiving: 'KG',
  quality: 'QC',
  billing: 'BIL',
  closure: 'GOV',
}

const philosophy = [
  { title: '快照固化', text: '订单创建即固化商品、价格、食堂、配送地址与时窗。', tone: 'primary' },
  { title: '状态留痕', text: '每一次业务流转自动写入审计日志和状态日志。', tone: 'teal' },
  { title: '称重锁定', text: '收货称重保留行级重量、签字与现场锁定照片。', tone: 'primary' },
  { title: '账务追溯', text: '账单基于收货快照生成，不受后续数据修改影响。', tone: 'violet' },
  { title: '监管闭环', text: '预警、工单、指令回执构成可追踪闭环。', tone: 'risk' },
]

const stageMetricMeta = [
  { key: 'count', field: 'count', label: '节点单量' },
  { key: 'evidence_count', field: 'evidence_count', label: '证据数量' },
  { key: 'risk_count', field: 'risk_count', label: '风险数量' },
]

/** 给领导看的"一句话指标解释"：避免审计日志 / 工单 / status 等技术词，重点说"这个数字为什么重要"。 */
const KPI_DESCRIPTIONS = {
  period_chain_orders:
    '最近 7 天内由学校或食堂下达、并已经走完订单创建审计的采购单总数。这个数字反映平台的业务体量。',
  audit_coverage_rate:
    '近 7 日订单中，有完整状态流转或操作留痕的占比。99% 表示几乎每一笔订单从下单到送达都有迹可循；低于 95% 说明部分订单走了系统外流程，需要排查。',
  closure:
    '左边是已经关闭的预警与工单数，右边是合计总数。比值越高说明监管闭环越快；未闭环项越多说明问题在堆积。',
  pending_attention:
    '当前需要监管关注的四类待办合计：未处理预警 + 未关闭工单 + 已出库缺质检报告 + 未结算账单。这个数字应保持低位，是每天进入页面第一眼要关注的指标。',
}

/** 8 个业务节点的"领导话术"：和后端 stage_defs 一一对应。 */
const STAGE_DESCRIPTIONS_HUMAN = {
  order_create:
    '学校或食堂发起一笔采购需求。系统会在创建瞬间把商品、单价、收货地址、送达时窗全部"拍照固化"，后续即使被修改也能追溯到原始版本。',
  allocation:
    '配送商把订单按行拆分给具体的供货档口，每一行的进度都独立留痕（待确认 / 备货中 / 已出库）。',
  supplier_ship:
    '供货档口按订单行打包出库，每出一行就在系统里登记一次。"已出库但还没传质检报告"会被自动标红。',
  delivery:
    '司机带着货物上车、出发、到达学校的整个过程。系统记录车辆、司机、发车与到达时间，超时未送达自动开工单。',
  receiving:
    '送达后食堂用智能秤逐行确认重量，秤值和签字、现场照片一起锁定。短斤少两会被自动识别为风险。',
  quality:
    '供货端上传的质检报告（图片 + 数据），与订单、商品、供货档口绑定。批次报告为存证留痕，上传即有效、无需逐单审核；待办指的是"已出库但还没补传报告"的分单。',
  billing:
    '账单根据食堂"实际收货重量"自动生成，不会被后续订单变更影响；待结算的账单在这里累计。',
  closure:
    '所有预警和工单从开出到关闭的进度。已关闭代表问题已处置完，未关闭代表问题还在堆积，监管要持续盯。',
}

/** 每个节点的"节点单量 / 证据数量 / 风险数量"分别含义；用一句话解释 + 一行口径。 */
const STAGE_METRIC_DESCRIPTIONS = {
  order_create: {
    count: { headline: '近 7 日总共创建了多少笔采购订单。', formula: '取自 orders 表 7 日内创建时间命中的记录数。' },
    evidence_count: { headline: '这些订单一共产生了多少条可追溯的操作留痕。', formula: '订单类审计日志条数 + 订单状态流转日志条数。' },
    risk_count: { headline: '其中有多少笔订单被系统标记了异常或者有未关闭工单。', formula: '"标记为异常"或"挂着未关闭工单"的订单数。' },
  },
  allocation: {
    count: { headline: '近 7 日由配送商生成的分单行数。一笔订单可以被拆成多行。', formula: '订单分单表（order_item_allocations）7 日内的行数。' },
    evidence_count: { headline: '这些分单行的状态变化总共留下多少条记录。', formula: '订单行状态流转日志条数。' },
    risk_count: { headline: '其中还卡在"待确认"未推进的分单行数。', formula: '分单行状态 = "待确认" 的行数。' },
  },
  supplier_ship: {
    count: { headline: '近 7 日供货端已经出库的分单行数。', formula: '分单行状态 = "已出库" 的行数。' },
    evidence_count: { headline: '这些出库分单行有多少条出库状态留痕。', formula: '状态变更日志里出现"已出库"的条数。' },
    risk_count: { headline: '其中"出库了但还没传质检报告"的行数。', formula: '已出库分单中未被批次报告或有效周期报告覆盖的行数。' },
  },
  delivery: {
    count: { headline: '近 7 日有车辆参与配送的订单数。', formula: '配送表中发车 / 到达时间命中 7 日窗口、或尚未发车的近期配送记录。' },
    evidence_count: { headline: '这些配送过程留下的"发货 / 收货"状态流转日志条数。', formula: '订单状态日志中 new_status 为发货或收货的条数。' },
    risk_count: { headline: '其中关联了"配送异常"工单且至今未关闭的配送订单数。一般是超时未送达、车辆故障、收货方拒收等。', formula: '近 7 日活跃配送订单 ∩ 配送异常类未关闭工单。' },
  },
  receiving: {
    count: { headline: '近 7 日已经由食堂确认收货的智能秤行数。', formula: '收货行状态 = "confirmed" 的行数。' },
    evidence_count: { headline: '这些收货行的全部确认 + 称重操作留痕。', formula: '已确认收货行数 + 收货相关审计日志。' },
    risk_count: { headline: '其中"实际收货重量 < 订单重量"的短斤少两行数。', formula: '已确认收货行中 shortage_delta_kg > 0 的行数。' },
  },
  quality: {
    count: { headline: '近 7 日供货端上传的质检报告总数（存证留痕量）。', formula: '质检报告表 7 日内创建的记录数。' },
    evidence_count: { headline: '这些报告 + 质检相关操作的全部留痕。', formula: '质检报告数 + 质检类审计日志条数。' },
    risk_count: { headline: '已出库但还没补传质检报告的分单行数，需督促供货商补传。', formula: '已出库分单中未被批次报告或有效周期报告覆盖的行数。' },
  },
  billing: {
    count: { headline: '近 7 日系统自动生成的账单数（含供货账单 / 配送账单）。', formula: '账单表 7 日内创建的记录数。' },
    evidence_count: { headline: '账单 + 结算操作的全部留痕。', formula: '账单数 + 账单类审计日志条数。' },
    risk_count: { headline: '其中"还没结算完成"的账单数。', formula: '账单 status ≠ "已结算" 的条数。' },
  },
  closure: {
    count: { headline: '近 7 日已经被处置关闭的预警 + 工单总数。', formula: '7 日内 status=closed 的预警 + status=已关闭 的工单。' },
    evidence_count: { headline: '系统类操作 + 已闭环预警工单的留痕条数。', formula: '系统类审计日志 + 已闭环预警与工单的合计。' },
    risk_count: { headline: '还没有被关闭的预警 + 工单数。这个数越高代表问题在堆积。', formula: '近 7 日内 status=open 的预警 + status ≠ 已关闭 的工单。' },
  },
}

const PANEL_DESCRIPTIONS = {
  evidence: {
    title: '实时审计证据流',
    headline:
      '监管系统自动捕获的最近业务事件，按时间倒序展示。点击右侧"档案"可调起该订单的完整审计文档。',
    formula: '颜色含义：红 = 风险（异常订单 / 超时 / 取消），黄 = 关注（缺质检报告等），灰 = 稳定。',
  },
  trend: {
    title: '7 日审计趋势',
    headline:
      '最近 7 天每日新增订单、新增审计存证、新增风险事件三条曲线，配合下方"审计覆盖率"与"监管闭环进度"两个仪表盘，反映平台运行健康度。',
  },
  philosophy: {
    title: '审计设计理念',
    headline:
      '平台审计遵循五条核心原则：快照固化、状态留痕、称重锁定、账务追溯、监管闭环。任何一笔订单出问题都能反查到最初快照、所有操作人和操作时间。',
  },
}

const summary = computed(() => payload.value.summary || {})
const stages = computed(() => payload.value.stages || [])
const evidenceFlow = computed(() => payload.value.evidence_flow || [])
const representativeOrders = computed(() => payload.value.representative_orders || [])
const trendRows = computed(() => payload.value.trend_7d || [])

const fmtNumber = (value, digits = 0) => {
  const n = Number(value || 0)
  return n.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

const fmtPct = (value) => `${fmtNumber(value, 1)}%`

const fmtMoney = (value) => {
  const n = Number(value || 0)
  if (Math.abs(n) >= 10000) return `¥${fmtNumber(n / 10000, 1)}万`
  return `¥${fmtNumber(n, 0)}`
}

const displayValue = (value, key = '') => {
  if (value === null || value === undefined || value === '') return '-'
  if (key === 'diff_type') return ({ shortage: '少收', overage: '多收', normal: '无差异' })[value] || value
  if (key === 'role') return ({ warehouse: '食堂签收人', carrier: '送货方' })[value] || value
  if (key.endsWith('_at') || key === 'time' || key === 'updated_at' || key === 'created_at') return formatChinaDateTime(value)
  if (key === 'amount') return fmtMoney(value)
  if (key.includes('kg')) return `${fmtNumber(value, 3)} kg`
  if (typeof value === 'boolean') return value ? '是' : '否'
  return value
}

/** 链路节点抽屉明细：后端 snake_case 字段 → 领导可读中文（与 monitor.py audit-chain items 对齐） */
const AUDIT_DETAIL_FIELD_LABELS = {
  order_id: '订单编号',
  order_no: '订单号',
  line_no: '订单行号',
  line_index: '收货行号',
  product_name: '商品名称',
  spec: '规格',
  unit: '单位',
  status: '状态',
  client_name: '客户 / 食堂',
  amount: '金额',
  updated_at: '更新时间',
  supplier: '供货商',
  driver_name: '司机',
  vehicle_no: '车牌号',
  departed_at: '发车时间',
  arrived_at: '到达时间',
  confirmed_kg: '确认重量',
  ordered_kg: '下单重量',
  received_kg: '实收重量',
  draft_kg: '锁定重量',
  diff_kg_signed: '收货差异',
  diff_label: '差异',
  diff_type: '差异类型',
  reason_label: '少收原因',
  shortage_delta_kg: '短收差额',
  confirmed_at: '确认时间',
  has_photo: '含锁定照片',
  report_no: '质检报告编号',
  created_at: '创建时间',
  role: '角色',
  bill_type: '账单类型',
  type: '类型',
  level: '等级',
  description: '说明',
}

const fieldLabelZh = (key) => AUDIT_DETAIL_FIELD_LABELS[key] || key

const stageTone = (status) => {
  if (status === 'risk') return 'risk'
  if (status === 'watch') return 'watch'
  return 'stable'
}

const evidenceTone = (level) => {
  if (level === 'risk' || level === 'high') return 'risk'
  if (level === 'watch' || level === 'medium') return 'watch'
  return 'stable'
}

const periodDays = computed(() => Number(payload.value?.period?.days || 7))

const kpiCards = computed(() => [
  {
    key: 'period_chain_orders',
    label: `近 ${periodDays.value} 日链路单量`,
    value: fmtNumber(summary.value.period_chain_orders),
    unit: '单',
    note: `今日新增 ${fmtNumber(summary.value.today_chain_orders)} 单 · 累计存证 ${fmtNumber(summary.value.period_evidence_count)} 条`,
    tone: 'primary',
  },
  {
    key: 'audit_coverage_rate',
    label: '审计覆盖率',
    value: fmtPct(summary.value.audit_coverage_rate),
    unit: '%',
    note: '订单状态与审计日志双轨覆盖',
    tone: 'teal',
  },
  {
    key: 'closure',
    label: '监管闭环进度',
    value: `${fmtNumber(summary.value.closure_done)} / ${fmtNumber(Number(summary.value.closure_done || 0) + Number(summary.value.closure_pending || 0))}`,
    unit: summary.value.closure_rate == null ? '—' : fmtPct(summary.value.closure_rate),
    note: `待闭环 ${fmtNumber(summary.value.closure_pending)} 项（预警 + 工单）`,
    tone: Number(summary.value.closure_pending || 0) > 0 ? 'violet' : 'teal',
  },
  {
    key: 'pending_attention',
    label: '待办分布',
    value: fmtNumber(summary.value.pending_attention),
    unit: '项',
    note: `预警 ${fmtNumber(summary.value.pending_alerts)} · 工单 ${fmtNumber(summary.value.pending_tickets)} · 质检 ${fmtNumber(summary.value.pending_quality)} · 账单 ${fmtNumber(summary.value.pending_bills)}`,
    tone: Number(summary.value.pending_attention || 0) > 0 ? 'risk' : 'teal',
  },
])

const selectedOrderEvidence = computed(() => activeOrderEvidence.value)

// —— 订单档案富卡片映射 ——
const orderHeader = computed(() => {
  const o = activeOrder.value || {}
  const risk = o.risk_count || 0
  return {
    title: o.order_no || '订单审计档案',
    badge: o.status || '—',
    badgeTone: risk > 0 ? 'danger' : 'default',
    status: o.risk_count == null ? '' : (risk > 0 ? `风险 ${risk} 项` : '无风险'),
  }
})
const orderSubjects = computed(() => {
  const o = activeOrder.value || {}
  return [
    { label: '客户 / 食堂', value: o.client_name },
    { label: '供应商', value: o.supplier_name },
    { label: '配送商', value: o.delivery_name },
  ].filter((s) => s.value)
})
const orderMetrics = computed(() => {
  const o = activeOrder.value || {}
  const tiles = []
  const push = (label, value) => { if (value !== null && value !== undefined && value !== '') tiles.push({ label, value }) }
  push('金额', o.amount != null ? fmtMoney(o.amount) : null)
  push('链路完成', o.completed_stage_count == null ? null : `${o.completed_stage_count}/8`)
  push('分单数', o.allocations_count)
  push('已出库', o.shipped_count)
  push('收货记录', o.receiving_count)
  push('质检报告', o.quality_count)
  push('关联账单', o.bills_count)
  push('待处理工单', o.pending_tickets_count)
  push('创建时间', o.created_at ? formatChinaDateTime(o.created_at) : null)
  push('更新时间', o.updated_at ? formatChinaDateTime(o.updated_at) : null)
  return tiles
})
const orderTimeline = computed(() =>
  selectedOrderEvidence.value.map((item) => ({
    title: item.title,
    meta: [item.kind ? `[${item.kind}]` : '', item.actor].filter(Boolean).join(' '),
    note: item.description && item.description !== item.title ? item.description : '',
    at: item.time,
  })),
)

const openStage = (stage) => {
  activeStage.value = stage
  stageDrawerVisible.value = true
}

/**
 * 打开订单档案：
 * - representative_orders 里已有的订单先用其快照渲染（即时反应）
 * - 同时按 order_id 调 /neural/order-audit/{id} 拉完整真档案（含证据流），覆盖到 activeOrder
 * - 拉失败时显示真实错误，不再造伪数据壳
 */
const openOrder = async (orderRefOrId) => {
  const isObject = orderRefOrId && typeof orderRefOrId === 'object'
  const orderId = Number(isObject ? orderRefOrId.order_id : orderRefOrId)
  if (!Number.isFinite(orderId) || orderId <= 0) return
  // 即时占位仅来自真实 representative_orders；找不到就置为最小集合，避免任何伪造字段
  const seed = representativeOrders.value.find((row) => Number(row.order_id) === orderId)
  activeOrder.value = seed ? { ...seed } : { order_id: orderId }
  activeOrderEvidence.value = []
  activeOrderError.value = ''
  activeOrderLoading.value = true
  orderDrawerVisible.value = true
  try {
    const detail = await monitorOrderAuditApi(orderId)
    if (!detail) {
      activeOrderError.value = '后端未返回订单档案'
      return
    }
    activeOrder.value = { ...detail }
    activeOrderEvidence.value = Array.isArray(detail.evidence_flow) ? detail.evidence_flow : []
  } catch (e) {
    activeOrderError.value = e?.response?.data?.detail || e?.message || '订单档案拉取失败'
  } finally {
    activeOrderLoading.value = false
  }
}

const renderTrendChart = () => {
  if (!chartRef.value) return
  if (!trendChart) trendChart = echarts.init(chartRef.value)
  const rows = trendRows.value
  trendChart.setOption({
    backgroundColor: 'transparent',
    color: ['#00e5ff', '#68fadd', '#ffb4ab'],
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(8, 13, 24, .96)',
      borderColor: 'rgba(0,229,255,.35)',
      textStyle: { color: '#e8fbff' },
    },
    legend: {
      top: 4,
      right: 6,
      textStyle: { color: '#bac9cc', fontSize: 11 },
      data: ['订单', '存证', '风险'],
    },
    grid: { left: 38, right: 18, top: 42, bottom: 28 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: rows.map((row) => String(row.date || '').slice(5)),
      axisLabel: { color: '#849396', fontSize: 11 },
      axisLine: { lineStyle: { color: 'rgba(0,229,255,.24)' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#849396', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(0,229,255,.08)' } },
    },
    series: [
      {
        name: '订单',
        type: 'line',
        smooth: true,
        data: rows.map((row) => Number(row.orders || 0)),
        areaStyle: { color: 'rgba(0,229,255,.12)' },
        lineStyle: { width: 3, shadowBlur: 10, shadowColor: 'rgba(0,229,255,.55)' },
        symbolSize: 6,
      },
      {
        name: '存证',
        type: 'line',
        smooth: true,
        data: rows.map((row) => Number(row.evidence || 0)),
        lineStyle: { width: 2 },
        symbolSize: 5,
      },
      {
        name: '风险',
        type: 'line',
        smooth: true,
        data: rows.map((row) => Number(row.risks || 0)),
        lineStyle: { width: 2, type: 'dashed' },
        symbolSize: 5,
      },
    ],
  })
  trendChart.resize()
}

const renderGaugeCharts = () => {
  if (!gaugeRef.value) return
  if (!gaugeChart) gaugeChart = echarts.init(gaugeRef.value)
  const coverageVal = Number(summary.value.audit_coverage_rate ?? 0)
  const closureVal = Number(summary.value.closure_rate ?? 0)

  const makeGauge = (name, value, color, center) => ({
    type: 'gauge',
    center,
    radius: '88%',
    startAngle: 180,
    endAngle: 0,
    min: 0,
    max: 100,
    splitNumber: 4,
    pointer: { show: false },
    axisLine: {
      lineStyle: {
        width: 14,
        color: [[value / 100, color], [1, 'rgba(255,255,255,.07)']],
      },
    },
    axisTick: { show: false },
    splitLine: { show: false },
    axisLabel: { show: false },
    detail: {
      valueAnimation: true,
      formatter: '{value}%',
      color,
      fontSize: 22,
      fontWeight: 700,
      fontFamily: '"JetBrains Mono", monospace',
      offsetCenter: [0, '-10%'],
    },
    title: {
      show: true,
      offsetCenter: [0, '30%'],
      color: 'rgba(186,201,204,.75)',
      fontSize: 11,
      fontFamily: 'inherit',
    },
    data: [{ value: Math.round(value), name }],
  })

  gaugeChart.setOption({
    backgroundColor: 'transparent',
    series: [
      makeGauge('审计覆盖率', coverageVal, '#00e5ff', ['27%', '78%']),
      makeGauge('监管闭环进度', closureVal, '#ebb2ff', ['73%', '78%']),
    ],
  })
  gaugeChart.resize()
}

const loadAuditChain = async () => {
  loading.value = true
  loadError.value = ''
  try {
    payload.value = (await monitorAuditChainApi()) || {}
    await nextTick()
    renderTrendChart()
    renderGaugeCharts()
  } catch (error) {
    loadError.value = error?.response?.data?.detail || error?.message || '审计链路暂不可用'
  } finally {
    loading.value = false
  }
}

watch(trendRows, () => nextTick(renderTrendChart), { deep: true })

onMounted(() => {
  // 不阻塞首帧渲染：先让外层 Layout 与本组件的骨架占位绘出，下一帧再发请求
  nextTick(() => {
    loadAuditChain().then(() => {
      if (chartRef.value || gaugeRef.value) {
        resizeObserver = new ResizeObserver(() => {
          trendChart?.resize()
          gaugeChart?.resize()
        })
        if (chartRef.value) resizeObserver.observe(chartRef.value)
        if (gaugeRef.value) resizeObserver.observe(gaugeRef.value)
      }
    })
  })
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  trendChart?.dispose()
  gaugeChart?.dispose()
})
</script>

<template>
  <section
    class="audit-core"
    v-loading="loading"
    element-loading-text="正在汇聚近 7 日全链路审计态势…"
    element-loading-background="rgba(8, 12, 22, 0.82)"
  >
    <div class="audit-grid-bg"></div>

    <header class="audit-hero">
      <div>
        <p class="audit-eyebrow">DAZONG REGULATORY COMMAND</p>
        <h1><span>NEURAL CORE</span> 全链路审计态势</h1>
        <strong>从下单到结算，每一步都有证据；从异常到闭环，每一次处理可追溯。</strong>
      </div>
      <div class="core-seal">
        <i></i>
        <span>CORE AUDIT</span>
        <b>{{ fmtNumber(summary.audit_coverage_rate, 1) }}%</b>
      </div>
    </header>

    <div v-if="loadError" class="empty-panel">
      <strong>审计链路暂不可用</strong>
      <span>{{ loadError }}</span>
      <button type="button" @click="loadAuditChain">重新加载</button>
    </div>

    <template v-else>
      <section class="kpi-grid">
        <article v-for="card in kpiCards" :key="card.key" class="glass-card kpi-card" :class="`tone-${card.tone}`">
          <div class="kpi-label">
            <span></span>
            <p>{{ card.label }}</p>
            <el-popover
              v-if="KPI_DESCRIPTIONS[card.key]"
              trigger="click"
              placement="bottom-end"
              :width="320"
              popper-class="metric-info-pop"
            >
              <template #reference>
                <button type="button" class="info-trigger" aria-label="查看指标说明">i</button>
              </template>
              <div class="metric-info">
                <h4>{{ card.label }}</h4>
                <p>{{ KPI_DESCRIPTIONS[card.key] }}</p>
              </div>
            </el-popover>
          </div>
          <div class="kpi-value">
            <strong>{{ card.value }}</strong>
            <em>{{ card.unit }}</em>
          </div>
          <small>{{ card.note }}</small>
        </article>
      </section>

      <section class="glass-card topology-panel">
        <div class="panel-title">
          <div>
            <p>BUSINESS AUDIT TOPOLOGY</p>
            <h2>全业务链路节点审计</h2>
          </div>
          <div class="legend">
            <span><i class="stable"></i>稳定</span>
            <span><i class="watch"></i>关注</span>
            <span><i class="risk"></i>风险</span>
          </div>
        </div>

        <div class="topology-line">
          <button
            v-for="stage in stages"
            :key="stage.key"
            type="button"
            class="audit-node"
            :class="stageTone(stage.status)"
            @click="openStage(stage)"
          >
            <span class="node-icon">{{ stageIconMap[stage.key] || 'LOG' }}</span>
            <strong>{{ stage.name }}</strong>
            <b>{{ fmtNumber(stage.count) }}</b>
            <em>{{ stage.status_label }}</em>
          </button>
        </div>
      </section>

      <section class="lower-grid">
        <article class="glass-card evidence-panel">
          <div class="panel-title compact">
            <div class="panel-title-text">
              <p>REAL-TIME EVIDENCE STREAM</p>
              <h2>
                实时审计证据流
                <el-popover trigger="click" placement="bottom-start" :width="340" popper-class="metric-info-pop">
                  <template #reference>
                    <button type="button" class="info-trigger info-trigger--inline" aria-label="查看面板说明">i</button>
                  </template>
                  <div class="metric-info">
                    <h4>{{ PANEL_DESCRIPTIONS.evidence.title }}</h4>
                    <p>{{ PANEL_DESCRIPTIONS.evidence.headline }}</p>
                    <small v-if="PANEL_DESCRIPTIONS.evidence.formula">{{ PANEL_DESCRIPTIONS.evidence.formula }}</small>
                  </div>
                </el-popover>
              </h2>
            </div>
            <button type="button" @click="loadAuditChain">刷新</button>
          </div>
          <div class="evidence-list">
            <div
              v-for="item in evidenceFlow.slice(0, 8)"
              :key="item.id"
              class="evidence-row"
              :class="[evidenceTone(item.level), { clickable: item.object_type === 'order' && item.object_id }]"
              @click="(item.object_type === 'order' && item.object_id) && openOrder(item.object_id)"
            >
              <time>{{ item.time_label || formatChinaDateTime(item.time) }}</time>
              <div>
                <p><span>[{{ item.kind }}]</span> {{ item.title }}</p>
                <small>{{ item.description }}</small>
              </div>
              <button
                v-if="item.object_type === 'order' && item.object_id"
                type="button"
                @click.stop="openOrder(item.object_id)"
              >
                档案
              </button>
            </div>
            <div v-if="!evidenceFlow.length" class="empty-inline">暂无审计证据流</div>
          </div>
        </article>

        <article class="glass-card trend-panel">
          <div class="panel-title compact">
            <div class="panel-title-text">
              <p>SEVEN DAY SIGNAL</p>
              <h2>
                7日审计趋势
                <el-popover trigger="click" placement="bottom-start" :width="340" popper-class="metric-info-pop">
                  <template #reference>
                    <button type="button" class="info-trigger info-trigger--inline" aria-label="查看面板说明">i</button>
                  </template>
                  <div class="metric-info">
                    <h4>{{ PANEL_DESCRIPTIONS.trend.title }}</h4>
                    <p>{{ PANEL_DESCRIPTIONS.trend.headline }}</p>
                  </div>
                </el-popover>
              </h2>
            </div>
          </div>
          <div ref="chartRef" class="trend-chart"></div>
          <div class="trend-stats">
            <span>今日存证 <b>{{ fmtNumber(summary.today_evidence_count) }}</b></span>
            <span>待关注 <b>{{ fmtNumber(summary.pending_attention) }}</b></span>
          </div>
          <div ref="gaugeRef" class="gauge-chart"></div>
        </article>

        <aside class="glass-card philosophy-panel">
          <div class="panel-title compact">
            <div class="panel-title-text">
              <p>AUDIT PHILOSOPHY</p>
              <h2>
                审计设计理念
                <el-popover trigger="click" placement="bottom-start" :width="340" popper-class="metric-info-pop">
                  <template #reference>
                    <button type="button" class="info-trigger info-trigger--inline" aria-label="查看面板说明">i</button>
                  </template>
                  <div class="metric-info">
                    <h4>{{ PANEL_DESCRIPTIONS.philosophy.title }}</h4>
                    <p>{{ PANEL_DESCRIPTIONS.philosophy.headline }}</p>
                  </div>
                </el-popover>
              </h2>
            </div>
          </div>
          <div class="philosophy-list">
            <div v-for="item in philosophy" :key="item.title" :class="`tone-${item.tone}`">
              <strong>{{ item.title }}</strong>
              <span>{{ item.text }}</span>
            </div>
          </div>
        </aside>
      </section>

      <section class="glass-card order-strip">
        <div class="panel-title compact order-strip-title">
          <div>
            <p>REPRESENTATIVE ORDER FILES</p>
            <h2>代表订单审计档案</h2>
          </div>
          <button type="button" class="more-orders-btn" @click="goAllOrders">查看全部订单 →</button>
        </div>
        <div class="order-cards">
          <button v-for="order in representativeOrders" :key="order.order_id" type="button" @click="openOrder(order)">
            <span>{{ order.order_no }}</span>
            <strong>{{ order.client_name }}</strong>
            <em>{{ order.status }} · {{ order.completed_stage_count }}/8 节点</em>
            <b :class="{ risk: order.risk_count > 0 }">{{ order.risk_count > 0 ? `${order.risk_count} 项风险` : '链路稳定' }}</b>
          </button>
        </div>
      </section>
    </template>

    <el-drawer v-model="stageDrawerVisible" direction="rtl" size="720px" :title="activeStage?.name || '链路节点'">
      <div class="dark-drawer" v-if="activeStage">
        <section v-if="STAGE_DESCRIPTIONS_HUMAN[activeStage.key]" class="stage-hero">
          <div class="stage-hero-head">
            <strong>本节点是什么</strong>
            <span class="stage-hero-status" :class="stageTone(activeStage.status)">{{ activeStage.status_label }}</span>
          </div>
          <p>{{ STAGE_DESCRIPTIONS_HUMAN[activeStage.key] }}</p>
        </section>
        <section class="drawer-summary">
          <div v-for="metric in stageMetricMeta" :key="metric.key">
            <span>
              {{ metric.label }}
              <el-popover
                v-if="STAGE_METRIC_DESCRIPTIONS[activeStage.key]?.[metric.key]"
                trigger="click"
                placement="bottom"
                :width="320"
                popper-class="metric-info-pop"
              >
                <template #reference>
                  <button type="button" class="info-trigger info-trigger--inline" aria-label="查看指标说明">i</button>
                </template>
                <div class="metric-info">
                  <h4>{{ activeStage.name }} · {{ metric.label }}</h4>
                  <p>{{ STAGE_METRIC_DESCRIPTIONS[activeStage.key][metric.key].headline }}</p>
                  <small v-if="STAGE_METRIC_DESCRIPTIONS[activeStage.key][metric.key].formula">
                    数据口径：{{ STAGE_METRIC_DESCRIPTIONS[activeStage.key][metric.key].formula }}
                  </small>
                </div>
              </el-popover>
            </span>
            <strong>{{ fmtNumber(activeStage[metric.field]) }}</strong>
          </div>
        </section>
        <p class="drawer-desc">{{ activeStage.description }}</p>
        <div class="drawer-table">
          <div v-for="(row, idx) in activeStage.items || []" :key="idx" class="drawer-row">
            <span v-for="[key, value] in Object.entries(row)" :key="key">
              <b>{{ fieldLabelZh(key) }}</b>
              <em>{{ displayValue(value, key) }}</em>
            </span>
          </div>
          <div v-if="!(activeStage.items || []).length" class="empty-inline">暂无明细</div>
        </div>
      </div>
    </el-drawer>

    <el-drawer v-model="orderDrawerVisible" direction="rtl" size="760px" :title="activeOrder?.order_no || '订单审计档案'">
      <div class="dark-drawer" v-if="activeOrder" v-loading="activeOrderLoading">
        <div v-if="activeOrderError" class="empty-panel">
          <strong>档案拉取失败</strong>
          <span>{{ activeOrderError }}</span>
          <button type="button" @click="openOrder(activeOrder?.order_id)">重试</button>
        </div>
        <EventDetailView
          :header="orderHeader"
          :subjects="orderSubjects"
          :metrics="orderMetrics"
          :timeline="orderTimeline"
          timeline-title="关联证据链"
        >
          <template #after-metrics>
            <div class="audit-stepper">
              <span v-for="stage in stages" :key="stage.key" :class="{ done: (activeOrder.completed_stage_count || 0) >= stages.indexOf(stage) + 1 }">{{ stage.name }}</span>
            </div>
          </template>
        </EventDetailView>
      </div>
    </el-drawer>

    <el-drawer v-model="ordersDrawerVisible" direction="rtl" size="980px" title="全部订单溯源">
      <div class="dark-drawer orders-pane">
        <div class="orders-filter">
          <label>状态
            <select v-model="ofStatus">
              <option value="">全部</option>
              <option v-for="o in MAIN_ORDER_STATUS_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </label>
          <label>订单号
            <input v-model="ofOrderNo" type="text" placeholder="订单号" @keyup.enter="loadOrders" />
          </label>
          <label>下单时间
            <input v-model="ofStart" type="date" /> <span class="sep">—</span> <input v-model="ofEnd" type="date" />
          </label>
          <button type="button" class="of-btn primary" @click="loadOrders">筛选</button>
          <button type="button" class="of-btn" @click="resetOrderFilter">重置</button>
        </div>

        <div class="orders-table-wrap" v-loading="ordersLoading">
          <table class="orders-table">
            <thead>
              <tr>
                <th style="width:200px">订单号</th>
                <th style="width:120px">状态</th>
                <th style="width:72px">异常</th>
                <th style="width:120px">金额</th>
                <th>创建时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!ordersLoading && !ordersList.length">
                <td colspan="5" class="of-empty">暂无订单</td>
              </tr>
              <tr
                v-for="row in ordersList"
                :key="row.id"
                class="of-row"
                :class="{ abnormal: row.has_abnormal }"
                @click="openOrder(row.id)"
              >
                <td class="of-mono">{{ row.order_no }}</td>
                <td>
                  <span class="of-status" :style="{ background: orderStatusTagColor(row.status) }">{{ orderStatusLabel(row.status) }}</span>
                </td>
                <td :class="row.has_abnormal ? 'of-warn' : 'of-dim'">{{ row.has_abnormal ? '是' : '否' }}</td>
                <td class="of-amount">¥{{ Number(row.total_amount || 0).toLocaleString() }}</td>
                <td class="of-dim">{{ formatChinaDateTime(row.created_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="orders-hint">共 {{ ordersList.length }} 单 · 点击任意订单查看审计档案</p>
      </div>
    </el-drawer>
  </section>
</template>

<style scoped>
.audit-core {
  position: relative;
  /* 父级 .stitch-host 已 height:100vh + overflow:hidden；本容器锁定 100vh 才能让自身 overflow:auto 生效 */
  height: 100vh;
  padding: 30px 34px 96px 124px;
  overflow-y: auto;
  overflow-x: hidden;
  color: #dfe2f3;
  background:
    radial-gradient(circle at 70% 12%, rgba(0, 229, 255, 0.10), transparent 28%),
    radial-gradient(circle at 18% 24%, rgba(114, 17, 153, 0.14), transparent 34%),
    #0a0e1a;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
}

.audit-grid-bg {
  position: fixed;
  inset: 0;
  pointer-events: none;
  opacity: .28;
  background-image:
    linear-gradient(rgba(0, 229, 255, .08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 229, 255, .08) 1px, transparent 1px);
  background-size: 42px 42px;
  mask-image: radial-gradient(circle at center, #000 0%, transparent 72%);
}

.audit-hero,
.kpi-grid,
.topology-panel,
.lower-grid,
.order-strip {
  position: relative;
  z-index: 1;
}

.audit-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 22px;
}

.audit-eyebrow,
.panel-title p {
  margin: 0 0 6px;
  color: #68fadd;
  font: 700 11px/1.2 "JetBrains Mono", monospace;
  letter-spacing: .14em;
}

.audit-hero h1 {
  margin: 0;
  color: #dffbff;
  font: 700 34px/1.15 "Space Grotesk", Inter, sans-serif;
  letter-spacing: 0;
}

.audit-hero h1 span {
  color: #c3f5ff;
  text-shadow: 0 0 18px rgba(0, 229, 255, .55);
}

.audit-hero strong {
  display: block;
  margin-top: 10px;
  color: #bac9cc;
  font-size: 14px;
  font-weight: 500;
}

.core-seal {
  position: relative;
  width: 126px;
  height: 126px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(0, 229, 255, .34);
  border-radius: 50%;
  background: radial-gradient(circle, rgba(0, 229, 255, .12), rgba(15, 19, 31, .64) 64%);
}

.core-seal i {
  position: absolute;
  inset: 8px;
  border-top: 2px solid #00e5ff;
  border-radius: 50%;
  animation: audit-spin 10s linear infinite;
}

.core-seal span,
.core-seal b {
  position: relative;
  z-index: 1;
}

.core-seal span {
  align-self: end;
  color: #9cf0ff;
  font: 700 10px/1 "JetBrains Mono", monospace;
  letter-spacing: .12em;
}

.core-seal b {
  align-self: start;
  color: #dffbff;
  font: 700 28px/1.1 "Space Grotesk", sans-serif;
}

@keyframes audit-spin {
  to { transform: rotate(360deg); }
}

.glass-card,
.empty-panel {
  border: 1px solid rgba(0, 218, 243, .22);
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(195, 245, 255, .035), transparent 36%), rgba(22, 27, 34, .66);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .04), 0 20px 50px rgba(0, 0, 0, .24);
  backdrop-filter: blur(12px);
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 18px;
  margin-bottom: 22px;
}

.kpi-card {
  min-height: 138px;
  padding: 18px 20px;
  border-left-width: 4px;
}

.tone-primary { border-left-color: #00e5ff; }
.tone-teal { border-left-color: #68fadd; }
.tone-violet { border-left-color: #ebb2ff; }
.tone-risk { border-left-color: #ffb4ab; }

.kpi-label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #bac9cc;
}

.kpi-label span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #00e5ff;
  box-shadow: 0 0 12px rgba(0, 229, 255, .75);
}

.kpi-label p {
  margin: 0;
  font: 700 12px/1 "JetBrains Mono", monospace;
}

.kpi-value {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-top: 22px;
}

.kpi-value strong {
  color: #c3f5ff;
  font: 700 42px/1 "Space Grotesk", sans-serif;
  text-shadow: 0 0 12px rgba(0, 229, 255, .28);
}

.kpi-value em {
  color: #68fadd;
  font: 700 12px/1 "JetBrains Mono", monospace;
  font-style: normal;
}

.kpi-card small {
  display: block;
  margin-top: 14px;
  color: #849396;
  font-size: 12px;
}

.topology-panel {
  padding: 28px 32px 32px;
  margin-bottom: 22px;
}

.panel-title {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 18px;
}

.panel-title h2 {
  margin: 0;
  color: #e8fbff;
  font: 700 25px/1.2 "Space Grotesk", sans-serif;
}

.panel-title.compact h2 {
  font-size: 20px;
}

.legend {
  display: flex;
  gap: 18px;
  color: #bac9cc;
  font: 600 12px/1 "JetBrains Mono", monospace;
}

.legend span {
  display: flex;
  align-items: center;
  gap: 7px;
}

.legend i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.stable { --node: #00e5ff; --node-rgb: 0, 229, 255; }
.watch { --node: #ebb2ff; --node-rgb: 235, 178, 255; }
.risk { --node: #ffb4ab; --node-rgb: 255, 180, 171; }

.legend i.stable { background: #00e5ff; box-shadow: 0 0 10px #00e5ff; }
.legend i.watch { background: #ebb2ff; box-shadow: 0 0 10px #ebb2ff; }
.legend i.risk { background: #ffb4ab; box-shadow: 0 0 10px #ffb4ab; }

.topology-line {
  position: relative;
  display: grid;
  grid-template-columns: repeat(8, minmax(96px, 1fr));
  gap: 10px;
  margin-top: 44px;
  padding: 30px 0 10px;
}

.topology-line::before {
  content: "";
  position: absolute;
  left: 4%;
  right: 4%;
  top: 58px;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(0, 229, 255, .56), transparent);
}

.audit-node {
  position: relative;
  z-index: 1;
  display: grid;
  justify-items: center;
  gap: 8px;
  min-width: 0;
  padding: 0 4px;
  border: 0;
  color: #dfe2f3;
  background: transparent;
  cursor: pointer;
}

.node-icon {
  width: 58px;
  height: 58px;
  display: grid;
  place-items: center;
  border: 2px solid var(--node);
  border-radius: 8px;
  color: var(--node);
  background: rgba(15, 19, 31, .9);
  box-shadow: 0 0 18px rgba(var(--node-rgb), .34);
  font: 800 13px/1 "JetBrains Mono", monospace;
}

.audit-node:hover .node-icon {
  transform: translateY(-3px);
  box-shadow: 0 0 26px rgba(var(--node-rgb), .56);
}

.audit-node strong,
.audit-node b,
.audit-node em {
  max-width: 100%;
  overflow: hidden;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.audit-node strong {
  font-size: 13px;
}

.audit-node b {
  color: #bac9cc;
  font: 700 12px/1 "JetBrains Mono", monospace;
}

.audit-node em {
  padding: 4px 8px;
  border-radius: 4px;
  color: var(--node);
  background: rgba(var(--node-rgb), .12);
  font: 700 10px/1 "JetBrains Mono", monospace;
  font-style: normal;
}

.lower-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(300px, .95fr) minmax(250px, .72fr);
  gap: 22px;
  margin-bottom: 22px;
}

.evidence-panel,
.trend-panel,
.philosophy-panel,
.order-strip {
  padding: 22px;
}

.panel-title button,
.empty-panel button {
  height: 32px;
  padding: 0 14px;
  border: 1px solid rgba(0, 229, 255, .34);
  border-radius: 6px;
  color: #9cf0ff;
  background: rgba(0, 229, 255, .08);
  cursor: pointer;
}

.order-strip-title {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.more-orders-btn {
  height: 34px;
  padding: 0 18px;
  border: 1px solid rgba(0, 229, 255, .4);
  border-radius: 6px;
  color: #bffcff;
  background: rgba(0, 229, 255, .1);
  font-weight: 700;
  cursor: pointer;
  transition: background 160ms ease, box-shadow 160ms ease;
}

.more-orders-btn:hover {
  background: rgba(0, 229, 255, .2);
  box-shadow: 0 0 16px rgba(0, 229, 255, .26);
}

/* —— 全部订单溯源抽屉 —— */
.orders-pane {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.orders-filter {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 14px;
  padding: 16px;
  border: 1px solid rgba(0, 229, 255, .16);
  border-radius: 10px;
  background: rgba(4, 12, 23, .56);
}

.orders-filter label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: rgba(130, 255, 231, .72);
  font-size: 12px;
  font-weight: 700;
}

.orders-filter select,
.orders-filter input {
  height: 36px;
  padding: 0 10px;
  border: 1px solid rgba(0, 229, 255, .22);
  border-radius: 6px;
  background: rgba(2, 10, 20, .72);
  color: #eaf8ff;
  font-size: 13px;
  color-scheme: dark;
}

.orders-filter input[type="text"] { width: 180px; }
.orders-filter input[type="date"] { width: 150px; }
.orders-filter .sep { color: rgba(221, 232, 241, .5); }

.of-btn {
  height: 36px;
  padding: 0 18px;
  border: 1px solid rgba(0, 229, 255, .3);
  border-radius: 6px;
  color: #9cf0ff;
  background: rgba(0, 229, 255, .08);
  font-weight: 700;
  cursor: pointer;
}

.of-btn.primary {
  color: #03161b;
  background: linear-gradient(135deg, #7fffee, #00d5ff);
  border-color: transparent;
}

.of-btn:hover { box-shadow: 0 0 14px rgba(0, 229, 255, .26); }

.orders-table-wrap {
  flex: 1;
  min-height: 200px;
  overflow: auto;
  border: 1px solid rgba(0, 229, 255, .12);
  border-radius: 10px;
}

.orders-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.orders-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 12px 14px;
  text-align: left;
  color: #bffcff;
  font-weight: 700;
  background: rgba(6, 16, 30, .96);
  border-bottom: 1px solid rgba(0, 229, 255, .18);
}

.orders-table td {
  padding: 12px 14px;
  border-bottom: 1px solid rgba(132, 147, 150, .12);
  color: #dfe8f2;
}

.of-row { cursor: pointer; transition: background 140ms ease; }
.of-row:hover { background: rgba(0, 229, 255, .08); }
.of-row.abnormal { background: rgba(255, 90, 110, .08); }
.of-row.abnormal:hover { background: rgba(255, 90, 110, .14); }

.of-mono { color: #eaf8ff; font-family: "JetBrains Mono", monospace; }
.of-amount { color: #8ff8ff; }
.of-dim { color: rgba(221, 232, 241, .6); }
.of-warn { color: #ff9faa; font-weight: 700; }
.of-empty { padding: 28px; text-align: center; color: rgba(221, 232, 241, .5); }

.of-status {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

.orders-hint {
  margin: 0;
  color: rgba(221, 232, 241, .5);
  font-size: 12px;
}

.evidence-list {
  margin-top: 18px;
}

.evidence-row {
  display: grid;
  grid-template-columns: 78px minmax(0, 1fr) auto;
  gap: 14px;
  padding: 13px 0;
  border-bottom: 1px solid rgba(132, 147, 150, .13);
}

.evidence-row.clickable {
  cursor: pointer;
  border-radius: 6px;
  padding: 13px 10px;
  margin: 0 -10px;
  transition: background 160ms ease, box-shadow 160ms ease;
}

.evidence-row.clickable:hover {
  background: rgba(0, 229, 255, .07);
  box-shadow: inset 0 0 0 1px rgba(0, 229, 255, .26);
}

.evidence-row time {
  color: #bac9cc;
  font: 600 12px/1.4 "JetBrains Mono", monospace;
}

.evidence-row p,
.evidence-row small {
  margin: 0;
}

.evidence-row p {
  color: #e8fbff;
  font-weight: 700;
}

.evidence-row p span {
  color: var(--node);
  font-family: "JetBrains Mono", monospace;
}

.evidence-row small {
  display: block;
  margin-top: 5px;
  color: #94a7ad;
  line-height: 1.55;
}

.evidence-row button {
  align-self: center;
  height: 28px;
  border: 1px solid rgba(0, 229, 255, .25);
  border-radius: 4px;
  color: #9cf0ff;
  background: rgba(0, 229, 255, .07);
  cursor: pointer;
}

.trend-chart {
  height: 250px;
  margin-top: 10px;
}

.gauge-chart {
  height: 200px;
  margin-top: 12px;
}

.trend-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.trend-stats span {
  padding: 12px;
  border: 1px solid rgba(132, 147, 150, .18);
  border-radius: 6px;
  color: #bac9cc;
  background: rgba(10, 14, 26, .42);
}

.trend-stats b {
  float: right;
  color: #68fadd;
}

.philosophy-list {
  display: grid;
  gap: 12px;
  margin-top: 18px;
}

.philosophy-list div {
  padding: 13px;
  border-left: 3px solid currentColor;
  border-radius: 6px;
  background: rgba(10, 14, 26, .46);
}

.philosophy-list strong {
  display: block;
  margin-bottom: 7px;
  color: currentColor;
  font: 800 11px/1 "JetBrains Mono", monospace;
  letter-spacing: .1em;
}

.philosophy-list span {
  color: #c9d6da;
  font-size: 13px;
  line-height: 1.55;
}

.philosophy-list .tone-primary { color: #00e5ff; }
.philosophy-list .tone-teal { color: #68fadd; }
.philosophy-list .tone-violet { color: #ebb2ff; }
.philosophy-list .tone-risk { color: #ffb4ab; }

.order-cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-top: 18px;
}

.order-cards button {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 14px;
  border: 1px solid rgba(0, 218, 243, .18);
  border-radius: 7px;
  color: #dfe2f3;
  text-align: left;
  background: rgba(10, 14, 26, .44);
  cursor: pointer;
}

.order-cards button:hover {
  border-color: rgba(0, 229, 255, .5);
}

.order-cards span,
.order-cards em,
.order-cards b {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.order-cards span {
  color: #9cf0ff;
  font: 800 12px/1 "JetBrains Mono", monospace;
}

.order-cards strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.order-cards em {
  color: #849396;
  font-size: 12px;
  font-style: normal;
}

.order-cards b {
  color: #68fadd;
  font-size: 12px;
}

.order-cards b.risk,
.order-file-head .risk {
  color: #ffb4ab;
}

.empty-panel {
  display: grid;
  gap: 12px;
  max-width: 520px;
  padding: 28px;
}

.empty-panel strong {
  color: #ffdad6;
  font-size: 20px;
}

.empty-panel span,
.empty-inline {
  color: #bac9cc;
}

.dark-drawer {
  color: #dfe2f3;
}

.drawer-summary,
.order-file-head {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 18px;
}

.order-file-head {
  grid-template-columns: repeat(4, 1fr);
}

.drawer-summary div,
.order-file-head div {
  padding: 14px;
  border: 1px solid rgba(0, 229, 255, .18);
  border-radius: 7px;
  background: rgba(10, 14, 26, .72);
}

.drawer-summary span,
.order-file-head span {
  display: block;
  margin-bottom: 8px;
  color: #849396;
  font-size: 12px;
}

.drawer-summary strong,
.order-file-head strong {
  color: #c3f5ff;
  font: 800 24px/1 "Space Grotesk", sans-serif;
}

.drawer-desc {
  color: #bac9cc;
  line-height: 1.7;
}

.drawer-table {
  display: grid;
  gap: 10px;
  margin-top: 18px;
}

.drawer-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding: 12px;
  border: 1px solid rgba(132, 147, 150, .14);
  border-radius: 7px;
  background: rgba(10, 14, 26, .56);
}

.drawer-row span {
  min-width: 0;
}

.drawer-row b,
.drawer-row em {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-row b {
  margin-bottom: 4px;
  color: #849396;
  font: 700 12px/1.2 "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
}

.drawer-row em {
  color: #e8fbff;
  font-style: normal;
}

.audit-stepper {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin: 18px 0 24px;
}

.audit-stepper span {
  padding: 10px;
  border: 1px solid rgba(132, 147, 150, .18);
  border-radius: 6px;
  color: #849396;
  text-align: center;
  background: rgba(10, 14, 26, .45);
}

.audit-stepper span.done {
  color: #00201a;
  border-color: rgba(104, 250, 221, .8);
  background: #68fadd;
}

.dark-drawer h3 {
  margin: 0 0 12px;
  color: #e8fbff;
}

.drawer-evidence .evidence-row {
  grid-template-columns: 84px 1fr;
}

:deep(.el-drawer) {
  background: #08111f;
  color: #e6f1ff;
}

:deep(.el-drawer__title) {
  color: #e6f1ff;
}

:deep(.el-drawer__close-btn) {
  color: #9cf0ff;
}

@media (max-width: 1280px) {
  .audit-core {
    padding-left: 112px;
  }
  .lower-grid {
    grid-template-columns: 1fr 1fr;
  }
  .philosophy-panel {
    grid-column: 1 / -1;
  }
  .order-cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 980px) {
  .audit-core {
    padding: 22px 16px 112px;
  }
  .audit-hero,
  .panel-title {
    flex-direction: column;
  }
  .core-seal {
    display: none;
  }
  .kpi-grid,
  .lower-grid,
  .order-cards {
    grid-template-columns: 1fr;
  }
  .topology-line {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin-top: 22px;
  }
  .topology-line::before {
    display: none;
  }
  .drawer-summary,
  .order-file-head,
  .drawer-row,
  .audit-stepper {
    grid-template-columns: 1fr;
  }
}

/* —— 指标说明 (i) 触发器 & 抽屉头部 hero —— */
.kpi-label {
  display: flex;
  align-items: center;
  gap: 8px;
  position: relative;
}
.kpi-label p {
  flex: 1;
  margin: 0;
}
.panel-title-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.panel-title-text h2 {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.info-trigger {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(0, 229, 255, 0.45);
  border-radius: 50%;
  background: rgba(0, 229, 255, 0.08);
  color: #9cf0ff;
  font: italic 700 11px/1 "Times New Roman", serif;
  cursor: pointer;
  transition: background 0.15s ease, transform 0.15s ease;
  padding: 0;
}
.info-trigger:hover {
  background: rgba(0, 229, 255, 0.22);
  transform: scale(1.06);
}
.info-trigger--inline {
  margin-left: 4px;
  vertical-align: middle;
}
.drawer-summary > div > span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.stage-hero {
  padding: 16px 18px;
  margin-bottom: 14px;
  border: 1px solid rgba(0, 229, 255, 0.22);
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(0, 229, 255, 0.07), rgba(11, 16, 28, 0.6));
}
.stage-hero-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.stage-hero-head strong {
  color: #9cf0ff;
  font-size: 13px;
  letter-spacing: 0.08em;
}
.stage-hero-status {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}
.stage-hero-status.stable { color: #b7ffe7; background: rgba(38, 166, 113, 0.22); border: 1px solid rgba(95, 227, 161, 0.35); }
.stage-hero-status.watch { color: #ffe7ad; background: rgba(255, 184, 77, 0.2); border: 1px solid rgba(255, 204, 102, 0.35); }
.stage-hero-status.risk { color: #ffc8d2; background: rgba(255, 83, 112, 0.18); border: 1px solid rgba(255, 122, 144, 0.35); }
.stage-hero p {
  margin: 0;
  color: #d8e7eb;
  line-height: 1.65;
}
</style>

<style>
/* el-popover 用 teleport 渲到 body 外，不能 scoped；给 popper-class 单独定主题 */
.metric-info-pop.el-popper {
  background: rgba(8, 12, 22, 0.96) !important;
  border: 1px solid rgba(0, 229, 255, 0.32) !important;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.5) !important;
  color: #dfe2f3 !important;
}
.metric-info-pop.el-popper .el-popper__arrow::before {
  background: rgba(8, 12, 22, 0.96) !important;
  border-color: rgba(0, 229, 255, 0.32) !important;
}
.metric-info-pop .metric-info h4 {
  margin: 0 0 8px;
  color: #9cf0ff;
  font-size: 14px;
  letter-spacing: 0.04em;
}
.metric-info-pop .metric-info p {
  margin: 0;
  color: #dfe2f3;
  font-size: 13px;
  line-height: 1.7;
}
.metric-info-pop .metric-info small {
  display: block;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed rgba(0, 229, 255, 0.18);
  color: #8ba0aa;
  font-size: 12px;
  line-height: 1.55;
}
</style>
