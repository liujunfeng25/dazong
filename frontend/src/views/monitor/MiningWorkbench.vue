<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { formatChinaDateTime } from '../../utils/datetime'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import * as XLSX from 'xlsx'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getAnalyticsDates,
  getBackfillStatus,
  getForecastAccuracy,
  getForecastAnalysis,
  getForecastFactors,
  getForecastOverview,
  getForecastPredict,
  getForecastTrainStatus,
  getMarketSentiment,
  getProductHints,
  getTimeseries,
  postBackfill,
  postBackfillDismiss,
  postForecastRetrain,
  postBatchRetrainAll,
  getBatchRetrainStatus,
} from '../../api/xinfadiAnalytics'
import {
  getZgFilters,
  getZgOverview,
  getZgProductHints,
  getZgTimeseries,
  getZgCompare,
  getZgPrices,
  getZgIndex,
  getZgQuality,
  getZgQualityFlags,
  postZgQualityFlagAction,
  postZgQualityFlagVerifyRecrawl,
  getZgMap,
  getZgMovers,
  getZgChangeRanking,
  getZgSpread,
  getZgForecast,
  postZgBriefing,
  postZgDailyReportJson,
  postZgDailyReportPdf,
  getZgBackfillPreview,
  postZgBackfill,
  getZgBackfillStatus,
  getZgCredentials,
  putZgCredentials,
  postZgCredentialsTest,
  postZgRebuild,
  getZgRebuildStatus,
  getZgForecastStatus,
  getZgHotSkus,
  putZgHotSkus,
  postZgForecastTrain,
} from '../../api/zgncpjgwAnalytics'

const QUICK_PRESETS = ['大白菜', '小白菜', '圆白菜', '娃娃菜']
const dayOptions = [7, 14, 30]
const router = useRouter()

const activeTab = ref('national')
const trendsLoaded = ref(false)
const bootLoading = ref(false)
const chartLoading = ref(false)
const productSearchLoading = ref(false)
const cachedDates = ref([])
const dateRange = ref([])
const selectedProds = ref([])
const productOptions = ref([])
const cat1 = ref('')
const tsData = ref({})
const detailRows = ref([])
const detailOpen = ref([])
const sentiment = reactive({ has_data: false, change_pct: null, direction: 'flat', message: '' })
const kpi = reactive({ calendarDays: 0, daysWithPoint: 0, prodCount: 0, lastDayAvgText: '—' })
const chartRef = ref(null)
let trendChart = null
let trendResizeObserver = null
let productSearchTimer = null

// —— 智能预测主视觉（聚焦单品种：历史实价 + 未来预测带）——
const focusProduct = ref('')
const focusPredict = ref({})
const focusHistory = ref({ dates: [], values: [] })
const focusLoading = ref(false)
const focusChartRef = ref(null)
let focusChart = null
let focusResizeObserver = null

const forecastLoading = ref(false)
const overviewRows = ref([])
const overviewTotal = ref(0)
const overviewPage = ref(1)
const overviewPageSize = ref(50)
const overviewQuery = ref('')
const overviewSortBy = ref('updated_at')
const overviewSortOrder = ref('desc')
const onlyTrainable = ref(false)
const onlyUsable = ref(false)
const selectedOverviewRows = ref([])
const detailVisible = ref(false)
const forecastDays = ref(30)
const currentProduct = ref('')
const activeOverviewRow = ref(null)
const forecastPayload = ref({})
const factorsPayload = ref([])
const analysisPayload = ref({})
const accuracyPayload = ref({})
const trainStatus = ref({})
const mainChartRef = ref(null)
const factorChartRef = ref(null)
const decompChartRef = ref(null)
let mainChart = null
let factorChart = null
let decompChart = null
let trainPollTimer = null

const backfillVisible = ref(false)
const backfillLoading = ref(false)
const backfillStatus = ref({ running: false, finished: false, total: 0, processed: 0, success: 0, current: null, progress_pct: 0, logs: [] })
const backfillTerminalRef = ref(null)
let backfillPollTimer = null

// 批量重训（全部/筛选命中可训练品种）
const trainableTotal = ref(0)
const batchVisible = ref(false)
const batchLoading = ref(false)
const batchStatus = ref({ running: false, finished: false, total: 0, processed: 0, success: 0, failed: 0, current: null, progress_pct: 0, logs: [] })
const batchTerminalRef = ref(null)
let batchPollTimer = null

const sentDirClass = computed(() => {
  if (sentiment.direction === 'up') return 'dir-up'
  if (sentiment.direction === 'down') return 'dir-down'
  return 'dir-flat'
})

const forecastRows = computed(() => forecastPayload.value?.ensemble || [])

const focusEnsemble = computed(() => focusPredict.value?.ensemble || [])
const focusStats = computed(() => {
  const p = focusPredict.value || {}
  const ens = focusEnsemble.value
  const current = Number(p.anchor_price ?? NaN)
  const next = ens[0] ? Number(ens[0].yhat) : NaN
  const day7 = ens.length ? Number(ens[Math.min(6, ens.length - 1)].yhat) : NaN
  const changePct = Number.isFinite(current) && current > 0 && Number.isFinite(next)
    ? (next - current) / current * 100 : null
  const acc = p.accuracy || {}
  const mape = acc.mape != null ? Number(acc.mape) : null
  const hit = acc.hit_rate != null ? Number(acc.hit_rate) : null
  // 可靠度以后端诚实评级为准（综合样本充足度+MAPE+方向命中），不再前端只看 MAPE
  const light = { high: 'ok', mid: 'warn', low: 'risk' }[p.reliability] || 'warn'
  const lows = ens.map((r) => Number(r.yhat_lower)).filter(Number.isFinite)
  const highs = ens.map((r) => Number(r.yhat_upper)).filter(Number.isFinite)
  return {
    product: p.product_name || focusProduct.value,
    current, next, day7, changePct, mape, hit, light,
    sampleCount: p.sample_count ?? null,
    reliabilityLabel: p.reliability_label || null,
    reliabilityReason: p.reliability_reason || '',
    sigma: p.sigma != null ? Number(p.sigma) : null,
    level: p.level != null ? Number(p.level) : null,
    bounds: Array.isArray(p.bounds) ? p.bounds : null,
    anchorDate: p.anchor_date || '',
    bandLo: lows.length ? Math.min(...lows) : null,
    bandHi: highs.length ? Math.max(...highs) : null,
    status: p.status,
  }
})
const focusLightText = computed(() => focusStats.value.reliabilityLabel || ({ ok: '高可靠', warn: '中等可靠', risk: '谨慎参考' }[focusStats.value.light] || '—'))
const aiConclusion = computed(() => {
  const s = focusStats.value
  if (s.status && s.status !== 'ok') {
    return s.status === 'insufficient' ? `${s.product}：有效历史不足，暂不出具预测结论。` : `${s.product}：暂无可用预测。`
  }
  if (!Number.isFinite(s.current) || !s.bandLo) return '—'
  const dir = s.changePct == null ? '窄幅' : s.changePct > 1.5 ? '温和上行' : s.changePct < -1.5 ? '温和下行' : '窄幅'
  const mapeText = s.mape != null ? `，近 14 日回测误差 ${s.mape}%（方向命中 ${s.hit ?? '—'}%）` : ''
  const reason = s.reliabilityReason ? `（${s.reliabilityReason}）` : ''
  return `${s.product} 锚定最新实价 ${money(s.current)} 元，预计一周内在 ${money(s.bandLo)}~${money(s.bandHi)} 元区间${dir}波动${mapeText}，可靠度${focusLightText.value}${reason}。`
})

// 算法/公式悬浮说明（体现 AI 实时计算，非凭空捏造）
const tipCurrent = '新发地最新交易日的批发均价，作为 AI 预测的锚点。'
const tipNext = computed(() => `AI 集成实时计算：以最新实价为锚，融合 均值回归(50%) + 持稳(30%) + 阻尼趋势(20%) 在对数空间外推次日。单日涨跌按近 60 日波动率 σ${focusStats.value.sigma != null ? `≈${(focusStats.value.sigma * 100).toFixed(1)}%` : ''} 封顶，结果裁剪到近 180 日合理区间${focusStats.value.bounds ? ` ${focusStats.value.bounds[0]}~${focusStats.value.bounds[1]} 元` : ''}，并向近 30 日中枢${focusStats.value.level != null ? ` ${focusStats.value.level} 元` : ''}缓慢回归。`)
const tip7 = '同一集成模型外推第 7 日；置信区间宽度随天数按 σ·√h 展开（h 为天数），越往后越宽，表示不确定性增大。'
const tipBacktest = '近 14 日「走动式回测」：用历史数据逐日预测次日、再与真实价比对。MAPE = 平均绝对百分比误差（越低越准）；方向命中 = 涨/跌方向判对的比例（须 > 50% 才比随机有效）。'
const tipLight = computed(() => `综合「样本充足度 + 回测 MAPE + 方向命中率」三项评级：样本≥120天且误差≤12%且命中≥55%→高可靠；样本不足30天或命中<45%→谨慎参考。当前：${focusStats.value.reliabilityReason || '—'}。`)
const summary = computed(() => {
  const rows = forecastRows.value
  const avgConf = rows.length ? rows.reduce((sum, row) => sum + Number(row.confidence || 0), 0) / rows.length : 0
  const first = rows[0]
  return {
    sampleCount: forecastPayload.value?.sample_count || activeOverviewRow.value?.sample_days || activeOverviewRow.value?.sample_days_total || 0,
    modelVersion: forecastPayload.value?.model_version || activeOverviewRow.value?.model_version || '—',
    firstDate: first?.date || '—',
    nextDay: first?.yhat != null ? money(first.yhat) : '—',
    confidence: rows.length ? pct(avgConf) : '—',
  }
})
const reliabilityStatus = computed(() => {
  const rows = forecastRows.value
  const avgConf = rows.length ? rows.reduce((sum, row) => sum + Number(row.confidence || 0), 0) / rows.length : 0
  const mape = Number(accuracyPayload.value?.accuracy?.mape ?? accuracyPayload.value?.mape ?? 0)
  if (avgConf >= 0.85 && (!mape || mape <= 15)) return { label: '绿灯：高可靠', className: 'ok', note: '可作为主要采购定价参考。' }
  if (avgConf >= 0.75 && (!mape || mape <= 25)) return { label: '黄灯：中可靠', className: 'warn', note: '建议结合当日行情复核。' }
  return { label: '红灯：谨慎使用', className: 'risk', note: '仅作预警，建议短周期重训或人工复核。' }
})
const bossActionText = computed(() => {
  if (reliabilityStatus.value.className === 'ok') return '可直接用于采购定价'
  if (reliabilityStatus.value.className === 'warn') return '结合当日行情复核'
  return '仅作预警参考'
})
const topFactorText = computed(() => {
  const rows = factorsPayload.value?.feature_importance || factorsPayload.value?.factors || factorsPayload.value || []
  const first = Array.isArray(rows) ? rows[0] : null
  if (!first) return '暂无'
  return `${first.feature || first.name || '特征'}（权重 ${Number(first.importance ?? first.weight ?? first.value ?? 0).toFixed(3)}）`
})
const backfillRunning = computed(() => !!backfillStatus.value.running)
const backfillProgressStatus = computed(() => {
  if (backfillStatus.value.running) return undefined
  if (backfillStatus.value.finished && (backfillStatus.value.success || 0) > 0) return 'success'
  if (backfillStatus.value.finished) return 'warning'
  return undefined
})

function money(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return Number(value).toFixed(3)
}

function pct(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return `${(Number(value) * 100).toFixed(1)}%`
}

function fmtDuration(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return '计算中'
  const sec = Math.max(0, Math.round(Number(seconds)))
  if (sec < 60) return `${sec}秒`
  const mins = Math.floor(sec / 60)
  const rest = sec % 60
  if (mins < 60) return `${mins}分${String(rest).padStart(2, '0')}秒`
  const hours = Math.floor(mins / 60)
  return `${hours}小时${String(mins % 60).padStart(2, '0')}分`
}

function fmtDate(date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function parseYmd(text) {
  const [y, m, d] = String(text).split('-').map(Number)
  return new Date(y, m - 1, d)
}

function defaultDateRange() {
  const end = new Date()
  const start = new Date(end)
  start.setDate(start.getDate() - 29)
  if (!cachedDates.value.length) return [fmtDate(start), fmtDate(end)]
  const min = parseYmd(cachedDates.value[0])
  return [fmtDate(start < min ? min : start), fmtDate(end)]
}

function fallbackDateRange() {
  const end = new Date()
  const start = new Date(end)
  start.setDate(start.getDate() - 29)
  return [fmtDate(start), fmtDate(end)]
}

function disabledDate(date) {
  const today = new Date()
  today.setHours(23, 59, 59, 999)
  if (date > today) return true
  if (!cachedDates.value.length) return false
  const s = fmtDate(date)
  return s < cachedDates.value[0]
}

async function loadProductOptions(q = '') {
  productSearchLoading.value = true
  try {
    const res = await getProductHints({ q, limit: q ? 800 : 800 })
    const names = res.names || (res.rows || []).map((row) => row.product_name)
    productOptions.value = [...new Set([...selectedProds.value, ...names])].sort((a, b) => a.localeCompare(b, 'zh-CN'))
  } finally {
    productSearchLoading.value = false
  }
}

function onProductRemoteQuery(raw) {
  if (productSearchTimer) clearTimeout(productSearchTimer)
  productSearchTimer = setTimeout(() => loadProductOptions((raw || '').trim()), 250)
}

function onProductDropdownVisible(visible) {
  if (visible && !productOptions.value.length) loadProductOptions('')
}

function addQuickProduct(product) {
  if (!productOptions.value.includes(product)) productOptions.value.push(product)
  if (!selectedProds.value.includes(product)) selectedProds.value.push(product)
}

function updateKpi(payload) {
  const cal = payload.calendar_dates || []
  const meta = payload.meta || {}
  kpi.calendarDays = cal.length
  kpi.daysWithPoint = meta.points_with_value || 0
  kpi.prodCount = meta.prod_count || 0
  const lastIdx = cal.length - 1
  const prices = (payload.series || []).map((ser) => ser.avg?.[lastIdx]).filter((v) => v != null)
  kpi.lastDayAvgText = prices.length ? money(prices.reduce((a, b) => a + Number(b), 0) / prices.length) : '—'
}

function renderTrendChart() {
  if (!chartRef.value) return
  if (!trendChart) trendChart = echarts.init(chartRef.value)
  const cal = tsData.value.calendar_dates || []
  const colors = ['#00e5ff', '#68fadd', '#f0a6ff', '#ffcc66', '#7aa7ff', '#ff7a90']
  trendChart.setOption({
    color: colors,
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(8, 13, 24, .96)', borderColor: 'rgba(0,229,255,.35)', textStyle: { color: '#e8fbff' } },
    legend: { top: 6, textStyle: { color: '#c7d9df' }, type: 'scroll' },
    grid: { left: 50, right: 24, top: 52, bottom: 72 },
    xAxis: { type: 'category', data: cal, boundaryGap: false, axisLabel: { color: '#93a8b2', rotate: 28 }, axisLine: { lineStyle: { color: 'rgba(0,229,255,.25)' } } },
    yAxis: { type: 'value', name: '元/斤', nameTextStyle: { color: '#93a8b2' }, axisLabel: { color: '#93a8b2' }, splitLine: { lineStyle: { color: 'rgba(0,229,255,.09)' } } },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 22, bottom: 16, borderColor: 'rgba(0,229,255,.2)', textStyle: { color: '#93a8b2' } }],
    series: (tsData.value.series || []).map((ser, idx) => ({
      name: ser.name,
      type: 'line',
      smooth: true,
      connectNulls: false,
      showSymbol: true,
      symbolSize: 5,
      lineStyle: { width: 2 },
      areaStyle: { opacity: idx === 0 ? 0.14 : 0.05 },
      data: ser.avg || [],
    })),
  }, true)
  trendChart.resize()
  // 首屏容器宽高可能尚为 0（模块刚切入/抽屉刚显示），延迟两帧再 resize 兜底，避免渲成空图需手点刷新
  requestAnimationFrame(() => trendChart?.resize())
  setTimeout(() => trendChart?.resize(), 120)
  trendResizeObserver?.disconnect()
  trendResizeObserver = new ResizeObserver(() => trendChart?.resize())
  trendResizeObserver.observe(chartRef.value)
}

async function loadTrends() {
  if (!selectedProds.value.length) {
    ElMessage.warning('请至少选择一个品名')
    return
  }
  chartLoading.value = true
  try {
    const [start, end] = dateRange.value || []
    const payload = await getTimeseries({ start_date: start, end_date: end, prod_names: selectedProds.value, cat1: cat1.value })
    tsData.value = payload || {}
    detailRows.value = payload.detail_rows || []
    updateKpi(payload || {})
    await nextTick()
    renderTrendChart()
  } finally {
    chartLoading.value = false
  }
}

async function loadFocusForecast() {
  const product = focusProduct.value || selectedProds.value[0] || QUICK_PRESETS[0]
  if (!product) return
  focusProduct.value = product
  focusLoading.value = true
  try {
    const [start, end] = dateRange.value || []
    const [pred, ts] = await Promise.all([
      getForecastPredict({ product, days: 14 }),
      getTimeseries({ start_date: start, end_date: end, prod_names: [product] }),
    ])
    focusPredict.value = pred || {}
    const cal = ts?.calendar_dates || []
    const ser = (ts?.series || []).find((s) => s.name === product) || (ts?.series || [])[0]
    focusHistory.value = ser
      ? { dates: cal.slice(-30), values: (ser.avg || []).slice(-30) }
      : { dates: [], values: [] }
  } catch (error) {
    console.error('[mining] focus forecast failed', error)
    focusPredict.value = {}
    focusHistory.value = { dates: [], values: [] }
  } finally {
    focusLoading.value = false
    await nextTick()
    renderFocusChart()
  }
}

function renderFocusChart() {
  if (!focusChartRef.value) return
  if (!focusChart) focusChart = echarts.init(focusChartRef.value)
  const hDates = focusHistory.value.dates || []
  const hVals = focusHistory.value.values || []
  const ens = focusEnsemble.value
  const fDates = ens.map((r) => r.date)
  const anchorIdx = hDates.length - 1
  // 实价线：历史 + 未来留空
  const actual = [...hVals, ...fDates.map(() => null)]
  // 预测线：历史留空、在锚点接上最后实价，再接未来 yhat（实现平滑相接）
  const lastActual = hVals.length ? hVals[hVals.length - 1] : (ens[0]?.yhat ?? null)
  const forecast = hDates.map((_, i) => (i === anchorIdx ? lastActual : null)).concat(ens.map((r) => r.yhat))
  const lower = hDates.map(() => null).concat(ens.map((r) => r.yhat_lower))
  const bandRange = hDates.map(() => null).concat(ens.map((r) => Number((r.yhat_upper - r.yhat_lower).toFixed(4))))
  const allDates = [...hDates, ...fDates]
  focusChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(8,13,24,.96)', borderColor: 'rgba(0,229,255,.35)', textStyle: { color: '#e8fbff' } },
    legend: { data: ['历史实价', '预测'], top: 4, textStyle: { color: '#c7d9df' } },
    grid: { left: 48, right: 24, top: 40, bottom: 40 },
    xAxis: { type: 'category', boundaryGap: false, data: allDates, axisLabel: { color: '#93a8b2', rotate: 28 }, axisLine: { lineStyle: { color: 'rgba(0,229,255,.25)' } } },
    yAxis: { type: 'value', name: '元/斤', scale: true, nameTextStyle: { color: '#93a8b2' }, axisLabel: { color: '#93a8b2' }, splitLine: { lineStyle: { color: 'rgba(0,229,255,.09)' } } },
    series: [
      // 置信带（下界 + 区间宽度堆叠，半透明）
      { name: '_lower', type: 'line', stack: 'conf', data: lower, lineStyle: { opacity: 0 }, symbol: 'none', silent: true, tooltip: { show: false } },
      { name: '置信区间', type: 'line', stack: 'conf', data: bandRange, lineStyle: { opacity: 0 }, symbol: 'none', areaStyle: { color: 'rgba(0,229,255,.16)' }, tooltip: { show: false } },
      { name: '历史实价', type: 'line', smooth: true, data: actual, showSymbol: false, lineStyle: { color: '#00e5ff', width: 3 }, areaStyle: { color: 'rgba(0,229,255,.10)' } },
      { name: '预测', type: 'line', smooth: true, data: forecast, showSymbol: false, lineStyle: { color: '#ffd166', width: 3, type: 'dashed' }, markLine: anchorIdx >= 0 ? { silent: true, symbol: 'none', lineStyle: { color: 'rgba(255,209,102,.55)', type: 'dotted' }, data: [{ xAxis: anchorIdx, label: { formatter: '今天', color: '#ffd166', position: 'insideEndTop' } }] } : undefined },
    ],
  }, true)
  focusChart.resize()
  requestAnimationFrame(() => focusChart?.resize())
  setTimeout(() => focusChart?.resize(), 120)
  focusResizeObserver?.disconnect()
  focusResizeObserver = new ResizeObserver(() => focusChart?.resize())
  focusResizeObserver.observe(focusChartRef.value)
}

async function bootTrends() {
  if (trendsLoaded.value) return
  trendsLoaded.value = true
  bootLoading.value = true
  // 1) 立即给默认日期范围与常用品种，避免依赖慢接口；这样首屏不会因为 dates / products 接口阻塞而超时报错
  dateRange.value = fallbackDateRange()
  if (!selectedProds.value.length) selectedProds.value = [...QUICK_PRESETS]
  productOptions.value = [...new Set([...productOptions.value, ...QUICK_PRESETS])]
  if (!focusProduct.value) focusProduct.value = selectedProds.value[0] || QUICK_PRESETS[0]
  try {
    // 2) 先发主体图表请求；它带的 prod_names + 默认 30 天日期能让后端走索引、几百毫秒返回
    await loadTrends().catch((error) => {
      console.error('[mining] initial trends failed', error)
    })
  } finally {
    bootLoading.value = false
  }
  // 2b) 拉聚焦品种的智能预测（历史已就绪，可直接画贯通图）
  loadFocusForecast()
  // 3) 元数据接口（全量 dates / sentiment / products 列表）单独异步，失败不影响主图
  Promise.allSettled([getAnalyticsDates(), getMarketSentiment(), loadProductOptions('')]).then((results) => {
    const [datesRes, sentRes] = results
    if (datesRes.status === 'fulfilled') {
      const dates = datesRes.value || {}
      cachedDates.value = dates.dates || dates.data_dates || []
    }
    if (sentRes.status === 'fulfilled') {
      Object.assign(sentiment, sentRes.value || {})
    }
    // 加载完商品后再尝试把当前选择对齐到真实存在的品种
    const real = QUICK_PRESETS.filter((item) => productOptions.value.includes(item))
    if (real.length) selectedProds.value = real
  })
}

function overviewReliabilityLabel(value) {
  return value === 'high' ? '绿灯' : value === 'mid' ? '黄灯' : value === 'low' ? '红灯' : '未评估'
}

async function loadOverview(reset = false) {
  if (reset) overviewPage.value = 1
  forecastLoading.value = true
  try {
    const res = await getForecastOverview({
      q: overviewQuery.value,
      page: overviewPage.value,
      page_size: overviewPageSize.value,
      sort_by: overviewSortBy.value,
      sort_order: overviewSortOrder.value,
      only_trainable: onlyTrainable.value,
      only_usable: onlyUsable.value,
    })
    overviewRows.value = res.items || res.rows || []
    overviewTotal.value = res.total || overviewRows.value.length
  } finally {
    forecastLoading.value = false
  }
  loadTrainableTotal()
}

// 全部/筛选命中的可训练品种数（跨页真实总数），用于按钮文案与批量重训范围
async function loadTrainableTotal() {
  try {
    const res = await getForecastOverview({ q: overviewQuery.value, page: 1, page_size: 1, only_trainable: true, only_usable: onlyUsable.value })
    trainableTotal.value = res.total || 0
  } catch {
    /* 忽略，仅影响按钮数字 */
  }
}

function onOverviewSelectionChange(rows) {
  selectedOverviewRows.value = rows || []
}

function canSelectForBatch(row) {
  return !!row.can_train
}

async function openForecastDetail(row) {
  activeOverviewRow.value = row
  currentProduct.value = row.product || row.product_name
  detailVisible.value = true
  await runPredict()
}

async function runPredict() {
  if (!currentProduct.value) return
  const [pred, factors, analysis, accuracy, status] = await Promise.all([
    getForecastPredict({ product: currentProduct.value, days: forecastDays.value }),
    getForecastFactors(currentProduct.value),
    getForecastAnalysis(currentProduct.value),
    getForecastAccuracy(currentProduct.value),
    getForecastTrainStatus(currentProduct.value),
  ])
  forecastPayload.value = pred || {}
  factorsPayload.value = factors || []
  analysisPayload.value = analysis || {}
  accuracyPayload.value = accuracy || {}
  trainStatus.value = status || {}
  await nextTick()
  renderForecastCharts()
}

function renderForecastCharts() {
  const rows = forecastRows.value
  if (mainChartRef.value) {
    if (!mainChart) mainChart = echarts.init(mainChartRef.value)
    const models = forecastPayload.value.models || {}
    mainChart.setOption({
      tooltip: { trigger: 'axis', backgroundColor: 'rgba(8,13,24,.96)', borderColor: 'rgba(0,229,255,.35)', textStyle: { color: '#e8fbff' } },
      legend: { top: 8, textStyle: { color: '#c7d9df' } },
      grid: { left: 50, right: 22, top: 56, bottom: 54 },
      xAxis: { type: 'category', data: rows.map((row) => row.date), axisLabel: { color: '#93a8b2', rotate: 24 } },
      yAxis: { type: 'value', axisLabel: { color: '#93a8b2' }, splitLine: { lineStyle: { color: 'rgba(0,229,255,.09)' } } },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 10 }],
      series: [
        { name: '集成预测', type: 'line', smooth: true, data: rows.map((row) => row.yhat), lineStyle: { color: '#ffd166', width: 3 } },
        { name: '置信下界', type: 'line', smooth: true, data: rows.map((row) => row.yhat_lower), lineStyle: { color: '#8da2ff', type: 'dashed' } },
        { name: '置信上界', type: 'line', smooth: true, data: rows.map((row) => row.yhat_upper), lineStyle: { color: '#68fadd', type: 'dashed' } },
        { name: 'Prophet', type: 'line', smooth: true, data: (models.prophet || []).map((row) => row.yhat), lineStyle: { color: '#ff7a90' } },
        { name: 'LSTM', type: 'line', smooth: true, data: (models.lstm || []).map((row) => row.yhat), lineStyle: { color: '#caa8ff' } },
        { name: 'XGBoost', type: 'line', smooth: true, data: (models.xgboost || []).map((row) => row.yhat), lineStyle: { color: '#68fadd' } },
      ],
    }, true)
    mainChart.resize()
  }
  const factors = factorsPayload.value.feature_importance || factorsPayload.value.factors || factorsPayload.value || []
  if (factorChartRef.value) {
    if (!factorChart) factorChart = echarts.init(factorChartRef.value)
    const top = Array.isArray(factors) ? factors.slice(0, 8).reverse() : []
    factorChart.setOption({
      grid: { left: 88, right: 18, top: 16, bottom: 24 },
      xAxis: { type: 'value', axisLabel: { color: '#93a8b2' }, splitLine: { lineStyle: { color: 'rgba(0,229,255,.08)' } } },
      yAxis: { type: 'category', data: top.map((x) => x.feature || x.name), axisLabel: { color: '#c7d9df' } },
      series: [{ type: 'bar', data: top.map((x) => Number(x.importance ?? x.weight ?? x.value ?? 0)), itemStyle: { color: '#00e5ff' } }],
    }, true)
    factorChart.resize()
  }
  if (decompChartRef.value) {
    if (!decompChart) decompChart = echarts.init(decompChartRef.value)
    decompChart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 44, right: 18, top: 20, bottom: 36 },
      xAxis: { type: 'category', data: rows.map((row) => row.date), axisLabel: { color: '#93a8b2' } },
      yAxis: { type: 'value', axisLabel: { color: '#93a8b2' }, splitLine: { lineStyle: { color: 'rgba(0,229,255,.08)' } } },
      series: [{ name: '趋势', type: 'line', smooth: true, data: rows.map((row) => row.yhat), areaStyle: { opacity: 0.15 }, lineStyle: { color: '#f0a6ff' } }],
    }, true)
    decompChart.resize()
  }
}

async function runRetrain(product = currentProduct.value) {
  if (!product) return
  await postForecastRetrain(product)
  ElMessage.success(`${product} 已进入训练队列`)
  startTrainPoll(product)
}

function startTrainPoll(product) {
  if (trainPollTimer) clearInterval(trainPollTimer)
  trainPollTimer = setInterval(async () => {
    trainStatus.value = await getForecastTrainStatus(product)
    if (['done', 'failed'].includes(trainStatus.value.status)) {
      clearInterval(trainPollTimer)
      trainPollTimer = null
      await loadOverview(false)
      if (detailVisible.value && currentProduct.value === product) await runPredict()
    }
  }, 1200)
}

function clearBatchPoll() {
  if (batchPollTimer) {
    clearInterval(batchPollTimer)
    batchPollTimer = null
  }
}

function scrollBatchTerminal() {
  nextTick(() => {
    const el = batchTerminalRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

// 轮询批量重训进度：finished 即停；带 60 次（约 90 秒无进展）停滞保护，绝不无限转圈
function pollBatchUntilDone() {
  clearBatchPoll()
  let lastProcessed = -1
  let stalls = 0
  batchPollTimer = setInterval(async () => {
    try {
      const s = await getBatchRetrainStatus()
      batchStatus.value = s
      scrollBatchTerminal()
      if (s.processed === lastProcessed) {
        stalls += 1
      } else {
        stalls = 0
        lastProcessed = s.processed
      }
      if (s.finished || !s.running) {
        clearBatchPoll()
        await loadOverview(false)
        ElMessage.success(`批量重训结束：成功 ${s.success || 0}，失败 ${s.failed || 0}，共 ${s.total || 0}`)
        return
      }
      if (stalls >= 60) {
        clearBatchPoll()
        ElMessage.warning('批量重训进度长时间无更新，已停止刷新；可稍后重新打开查看。')
      }
    } catch {
      clearBatchPoll()
      ElMessage.error('读取批量重训进度失败')
    }
  }, 1500)
}

async function runBatchRetrain() {
  batchVisible.value = true
  batchLoading.value = true
  try {
    // 若已有批量重训在跑，直接接续显示进度
    const cur = await getBatchRetrainStatus()
    if (cur?.running) {
      batchStatus.value = cur
      pollBatchUntilDone()
      return
    }
    const res = await postBatchRetrainAll({
      q: overviewQuery.value,
      only_trainable: true,
      only_usable: onlyUsable.value,
    })
    if (res?.started === false && !res?.running) {
      ElMessage.info(res?.message || '没有可训练的品种')
      batchStatus.value = { ...batchStatus.value, finished: true, logs: [res?.message || '没有可训练的品种'] }
      return
    }
    ElMessage.success(res?.message || '已提交批量重训')
    batchStatus.value = await getBatchRetrainStatus()
    scrollBatchTerminal()
    pollBatchUntilDone()
  } catch (e) {
    ElMessage.error('提交批量重训失败')
  } finally {
    batchLoading.value = false
  }
}

async function runOneClickSync() {
  backfillVisible.value = true
  await confirmBackfill({ waitForDone: true })
  await runBatchRetrain()
}

function clearBackfillPoll() {
  if (backfillPollTimer) {
    clearInterval(backfillPollTimer)
    backfillPollTimer = null
  }
}

function resetBackfillDisplayIdle() {
  backfillStatus.value = {
    running: false,
    finished: false,
    total: 0,
    processed: 0,
    success: 0,
    current: null,
    progress_pct: 0,
    logs: [
      '提示：补抓按「日期范围」对比 MySQL：该日已有行情则跳过，仅对缺失日逐日抓取；与当前选择的品名无关。',
      '标准模式日间隔约 3～5 秒（XINFADI_BACKFILL_DAY_PAUSE_MIN/MAX）；',
      '慢速模式日间隔约 12～25 秒（XINFADI_BACKFILL_SLOW_DAY_PAUSE_MIN/MAX），分页冷却 3～7 秒，遇 403/429 自动长退避并清空会话重试。',
    ],
  }
}

function scrollBackfillTerminal() {
  nextTick(() => {
    const el = backfillTerminalRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function pollBackfillUntilDone({ waitForDone = false } = {}) {
  clearBackfillPoll()
  const tick = async (resolve) => {
    backfillStatus.value = await getBackfillStatus()
    scrollBackfillTerminal()
    if (!backfillStatus.value.running && backfillStatus.value.finished) {
      clearBackfillPoll()
      await loadTrends()
      ElMessage.success('补抓结束，图表已刷新')
      resolve?.(backfillStatus.value)
      return true
    }
    return false
  }
  if (!waitForDone) {
    backfillPollTimer = setInterval(() => tick(), 650)
    return Promise.resolve(backfillStatus.value)
  }
  return new Promise((resolve) => {
    backfillPollTimer = setInterval(() => tick(resolve), 650)
  })
}

async function openBackfillDialog() {
  backfillVisible.value = true
  clearBackfillPoll()
  resetBackfillDisplayIdle()
  try {
    const status = await getBackfillStatus()
    if (status?.running) {
      backfillStatus.value = status
      scrollBackfillTerminal()
      pollBackfillUntilDone()
    }
  } catch {
    ElMessage.error('读取补抓状态失败')
  }
}

async function confirmBackfill({ waitForDone = false } = {}) {
  if (!dateRange.value?.length) {
    ElMessage.warning('请先选择日期范围')
    return
  }
  backfillLoading.value = true
  clearBackfillPoll()
  try {
    const [start_date, end_date] = dateRange.value
    const res = await postBackfill({ start_date, end_date })
    if (res?.error) {
      backfillStatus.value = { ...backfillStatus.value, logs: [String(res.error)] }
      ElMessage.error(res.error)
      return
    }
    if (res?.started === false) {
      backfillStatus.value = { ...backfillStatus.value, finished: true, logs: [res.message || '所选区间内没有缺失的库内数据，无需补抓'] }
      ElMessage.info(res.message || '无需补抓')
      return
    }
    backfillStatus.value = await getBackfillStatus()
    scrollBackfillTerminal()
    ElMessage.success(res?.message || '已开始补抓')
    await pollBackfillUntilDone({ waitForDone })
  } finally {
    backfillLoading.value = false
  }
}

function todayYmd() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** 慢补结束日：优先用行情趋势日期选择器的结束日，否则今天 */
function backfillEndDateYmd() {
  const dr = dateRange.value
  if (Array.isArray(dr) && dr.length >= 2 && dr[1]) return dr[1]
  return todayYmd()
}

async function confirmSlowBackfillFrom2024() {
  const end_date = backfillEndDateYmd()
  try {
    await ElMessageBox.confirm(
      `将从 2024-01-01 慢速补抓到 ${end_date}。\n结束日取自上方「行情趋势」日期范围的结束日；若未选完整范围则结束日为今天。\n慢速模式策略：分页冷却 3～7 秒，日级别冷却约 12～25 秒，UA/Referer/Cookie 完整模拟浏览器；遇 403/429（被反爬识别）自动长退避（25～240 秒）并清空会话重试，避免触发风控被封 IP。\n该任务跨度长（约 500 天）预计需要数小时；可保持页面打开实时查看日志，或关闭后下次进入接续观察进度。是否开始？`,
      '慢速补抓（自 2024-01-01）',
      { type: 'warning', confirmButtonText: '开始慢补', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  backfillLoading.value = true
  clearBackfillPoll()
  try {
    const res = await postBackfill({ start_date: '2024-01-01', end_date, slow: true })
    if (res?.error) {
      backfillStatus.value = { ...backfillStatus.value, logs: [String(res.error)] }
      ElMessage.error(res.error)
      return
    }
    if (res?.started === false) {
      backfillStatus.value = { ...backfillStatus.value, finished: true, logs: [res.message || '所选区间内没有缺失的库内数据，无需补抓'] }
      ElMessage.info(res.message || '无需补抓')
      return
    }
    backfillStatus.value = await getBackfillStatus()
    scrollBackfillTerminal()
    ElMessage.success(res?.message || '已开始慢速补抓')
    await pollBackfillUntilDone({ waitForDone: false })
  } finally {
    backfillLoading.value = false
  }
}

// ============ 全国农产品价格（中农价格网 zgncpjgw）============
const nationLoaded = ref(false)
const natChartLoading = ref(false)
const natOverviewLoading = ref(false)
const natCompareLoading = ref(false)
const natDetailLoading = ref(false)
const natProductSearchLoading = ref(false)
const natDateRange = ref([])
const natDistrict = ref('')
const natCategory = ref('')
const natScate = ref('')
const natProds = ref([])
const natProductOptions = ref([])
const natDistrictOptions = ref([])
const natCategoryOptions = ref([])
const natSubcategories = ref([]) // [{cate_id, name}]
const natScateOptions = computed(() =>
  natCategory.value
    ? natSubcategories.value.filter((s) => s.cate_id === natCategory.value)
    : natSubcategories.value,
)
const natKpi = reactive({
  total_rows: 0,
  distinct_goods: 0,
  distinct_skus: 0,
  distinct_districts: 0,
  distinct_categories: 0,
  days_covered: 0,
  cumulative_rows: 0,
  earliest_date: '',
  latest_date: '—',
  snapshot_date: '',
})

function formatNatRowCount(n) {
  const v = Number(n) || 0
  if (v >= 10000) return `${(v / 10000).toFixed(2)} 万`
  return v.toLocaleString()
}
const natCategoryBreakdown = ref([])
const natTsData = ref({ dates: [], series: [] })
const natCompareData = ref({ date: '', labels: [], values: [] })
const natDetailRows = ref([])
const natDetailTotal = ref(0)
const natDetailPage = ref(1)
const natDetailPageSize = ref(20)
const natTopGoods = ref([]) // 数据驱动的热门 SKU（来自 overview.top_skus，元素 {sku_key,label,...}）
const natSkuLabels = ref({}) // sku_key → 显示label（品名 规格）
const natGap = ref({ days: 0, latest: '', target: '', dismissed: false }) // 数据缺口提示（只提示不强制）
const SKU_SEP = ''
function skuName(skuKey) { return (skuKey || '').split(SKU_SEP)[0] || '' }
function rememberSku(list) { (list || []).forEach((s) => { if (s && s.sku_key) natSkuLabels.value[s.sku_key] = s.label || s.sku_key }) }
const natProds0Label = computed(() => natSkuLabels.value[natProds.value[0]] || skuName(natProds.value[0]) || '—')
const natAnalysisSkuOptions = computed(() =>
  natProds.value.map((k) => ({
    value: k,
    label: natSkuLabels.value[k] || skuName(k) || k,
  })),
)
const natPrimarySku = computed({
  get: () => natProds.value[0] || '',
  set: (key) => { if (key) setPrimaryNatSku(key) },
})
const natForecastScopeLabel = computed(() => natForecastDistrictName.value ? `${natForecastDistrictName.value}口径` : '全国口径')
const natMapProvinceOptions = computed(() => {
  const nameToId = new Map((natDistrictOptions.value || []).map((d) => [d.name, d.id]))
  return (natMapData.value.provinces || [])
    .map((p) => ({
      name: p.name,
      value: p.value,
      numericValue: Number(p.value),
      id: nameToId.get(p.name) || '',
    }))
    .filter((p) => p.name)
    .sort((a, b) => {
      const av = Number.isFinite(a.numericValue) ? a.numericValue : -Infinity
      const bv = Number.isFinite(b.numericValue) ? b.numericValue : -Infinity
      return bv - av
    })
})
const natForecastShowProgress = computed(() => {
  const s = natForecastTraining.value || {}
  return !!s.running || (s.finished && Number(s.total) > 0)
})
const natForecastStatusText = computed(() => {
  if (natFcLoading.value && natForecast.value?.status === 'loading') {
    return `正在读取 ${natForecastScopeLabel.value} 的预测结果…`
  }
  const s = natForecastTraining.value || {}
  if (s.running) return s.message || `预测训练中：已完成 ${s.processed || 0}/${s.total || 0}`
  if (s.finished && Number(s.total) > 0) return s.message || '预测已更新'
  return s.message || '切换省份后将自动读取该口径的预测快照；无快照可点「更新当前预测」'
})
const natForecastProgressPct = computed(() => {
  const v = Number(natForecastTraining.value?.display_progress_pct ?? natForecastTraining.value?.progress_pct ?? 0)
  if (!Number.isFinite(v)) return 0
  return Math.max(0, Math.min(100, Math.round(v)))
})
const natForecastProgressStatus = computed(() => {
  const s = natForecastTraining.value || {}
  if (s.running) return undefined
  if (s.finished && Number(s.failed || 0) > 0) return 'warning'
  if (s.finished) return 'success'
  return undefined
})
const natForecastProgressMeta = computed(() => {
  if (!natForecastShowProgress.value) return ''
  const s = natForecastTraining.value || {}
  const parts = []
  if (s.training_scope) parts.push(s.training_scope)
  if (s.total) parts.push(`任务 ${s.processed || 0}/${s.total}`)
  if (s.eta_text) parts.push(s.eta_text)
  if (s.success) parts.push(`成功 ${s.success}`)
  if (s.failed) parts.push(`失败 ${s.failed}`)
  if (s.updated_at) parts.push(formatChinaDateTime(s.updated_at).slice(0, 16))
  return parts.join(' · ')
})
const natForecastPipelineLines = computed(() => {
  const s = natForecastTraining.value || {}
  const lines = Array.isArray(s.detail_lines) ? s.detail_lines.filter(Boolean) : []
  if (lines.length) return lines.slice(-5)
  if (s.training_scope) return [`训练范围：${s.training_scope}`]
  return ['训练范围：当前 SKU · 全国及有数据省份']
})
const natForecastEtaText = computed(() => {
  const s = natForecastTraining.value || {}
  const parts = []
  if (s.elapsed_seconds != null) parts.push(`已用 ${fmtDuration(s.elapsed_seconds)}`)
  if (s.remaining_seconds != null) parts.push(`预计剩余 ${fmtDuration(s.remaining_seconds)}`)
  if (s.speed_text) parts.push(`速度 ${s.speed_text}`)
  return parts.join(' · ')
})
const natForecastIsBatch = computed(() => ['popular_batch', 'all_batch'].includes(natForecastTraining.value?.scope_mode))
const natHotActiveCount = computed(() => activeNatHotSkus().length)
const natHotEstimateTaskCount = computed(() => natHotSkuEstimate.value?.task_count || natHotActiveCount.value * 13)
const natHotEstimateText = computed(() => natHotSkuEstimate.value?.estimated_total_text || fmtDuration(natHotSkuEstimate.value?.estimated_total_seconds || natHotEstimateTaskCount.value * 8))
const heroMetricTop = computed(() => {
  if (activeTab.value !== 'national') return `${cachedDates.value.length} 天行情`
  const cum = natKpi.cumulative_rows
  return cum ? `${formatNatRowCount(cum)} 条入库` : `${natKpi.days_covered || 0} 天行情`
})
const heroMetricBottom = computed(() => activeTab.value === 'national' ? `${(natKpi.distinct_skus || 0).toLocaleString()} 个 SKU` : `${selectedProds.value.length} 个品种`)
const natIndexBasketText = computed(() => {
  const meta = natIndex.basket_meta || {}
  const provinces = Number(meta.province_count || natKpi.distinct_districts || 0)
  const size = Number(meta.basket_size || 0)
  const sizeText = size >= 10000 ? `约 ${(size / 10000).toFixed(2)} 万` : size.toLocaleString()
  return `${provinces || '—'} 省 · 指数篮子 ${sizeText} SKU（基期与最新日均有价）`
})
const natTrainingEstimate = computed(() => natTrainingMode.value === 'all_batch' ? natAllSkuEstimate.value : natHotSkuEstimate.value)
const natTrainingSkuCount = computed(() => natTrainingMode.value === 'all_batch' ? (natAllSkuEstimate.value?.sku_count || 0) : natHotActiveCount.value)
const natTrainingTaskCount = computed(() => natTrainingEstimate.value?.task_count || 0)
const natTrainingEstimateText = computed(() => natTrainingEstimate.value?.estimated_total_text || fmtDuration(natTrainingEstimate.value?.estimated_total_seconds || 0))
// —— 旗舰模块：指数 / 热力地图 / 预测 / 异动 / 价差 / AI 日报 ——
const natIndexLoading = ref(false)
const natIndex = reactive({ overall_latest: null, overall_change_pct: null, base_date: '', latest_date: '', dates: [], overall: [], categories: [] })
const natQualityLoading = ref(false)
const natQuality = reactive({ snapshot_date: '', parse_rate: null, suspicious_skus: null, distinct_skus: null, basket_size: null, basket_coverage: null, freshness_gap_days: null, health_score: null, quality_trend: [] })
const natSuspiciousVisible = ref(false)
const natQualityFlagDate = ref('')
const natSuspiciousLoading = ref(false)
const natSuspiciousRows = ref([])
const natSuspiciousMeta = reactive({ snapshot_date: '', ratio_threshold: 5, total: 0 })
const natQualityFlagSeverity = ref('')
const natQualityFlagStatus = ref('')
const natQualityFlagQuery = ref('')
const correctingFlagId = ref(null)
const natQualityGrade = computed(() => {
  const s = natQuality.health_score
  if (s == null) return { label: '—', cls: 'mid' }
  if (s >= 85) return { label: '健康', cls: 'ok' }
  if (s >= 70) return { label: '一般', cls: 'warn' }
  return { label: '需关注', cls: 'risk' }
})
const natIndexRef = ref(null)
let natIndexChart = null
let natIndexRO = null
const natMapLoading = ref(false)
const natMapData = ref({ scope: '', metric: 'level', provinces: [] })
const natForecastDistrictId = ref('')
const natForecastDistrictName = ref('')
const natForecastTraining = ref({ running: false, finished: false, status: 'idle', phase: 'idle', phase_label: '等待训练', training_scope: '', progress_pct: 0, total: 0, processed: 0, success: 0, failed: 0, message: '未启动预测训练', detail_lines: [], updated_at: '' })
let natForecastPollTimer = null
const natTrainingCenterVisible = ref(false)
const natTrainingCenterMinimized = ref(false)
const natTrainingDetailsOpen = ref(true)
const natHotSkuLoading = ref(false)
const natHotSkuSaving = ref(false)
const natHotSkuPick = ref('')
const natHotSkuConfigured = ref([])
const natHotSkuRecommended = ref([])
const natHotSkuUsingRecommended = ref(true)
const natHotSkuEstimate = ref({ sku_count: 0, task_count: 0, estimated_total_seconds: 0, estimated_total_text: '' })
const natAllSkuEstimate = ref({ sku_count: 0, task_count: 0, estimated_total_seconds: 0, estimated_total_text: '' })
/** 筛选区「快捷添加」：优先客户配置/系统推荐热门 SKU，未加载时回退 overview.top_skus */
const natQuickPickSkus = computed(() => {
  const hot = activeNatHotSkus()
  if (hot.length) return hot
  return natTopGoods.value || []
})
const natTrainingMode = ref('popular_batch')
const natIndexSelectedCateIds = ref([])
const natMapRef = ref(null)
let natMapChart = null
let natMapRO = null
let chinaMapReady = false
const natFcLoading = ref(false)
const natForecast = ref({ status: '', ensemble: [], history: [] })
let natForecastReqSeq = 0
const natFcRef = ref(null)
let natFcChart = null
let natFcRO = null
// 预测图模式：false=清洗后(默认)，true=原始报价(未过质量规则)
const natForecastRawMode = ref(false)
const natForecastHasRaw = computed(() => {
  const fc = natForecast.value || {}
  return (fc.raw_history || []).length > (fc.history || []).length
})

function natForecastScopeKey() {
  return `${natProds.value[0] || ''}|${natForecastDistrictId.value || ''}`
}

function resetNatForecastViewForScopeChange() {
  natForecastRawMode.value = false
  natForecast.value = {
    status: 'loading',
    ensemble: [],
    history: [],
    message: `正在读取 ${natForecastScopeLabel.value} 的历史与预测…`,
    district_id: natForecastDistrictId.value || 0,
    scope: natForecastDistrictId.value ? 'province' : 'national',
  }
  if (!natForecastTraining.value.running) {
    natForecastTraining.value = {
      running: false,
      finished: false,
      status: 'idle',
      phase: 'idle',
      phase_label: '切换口径',
      training_scope: '',
      scope_mode: '',
      progress_pct: 0,
      display_progress_pct: 0,
      total: 0,
      processed: 0,
      success: 0,
      failed: 0,
      remaining_seconds: null,
      eta_text: '',
      elapsed_seconds: null,
      speed_text: '',
      message: `正在读取 ${natForecastScopeLabel.value} 的预测结果…`,
      detail_lines: [`当前口径：${natForecastScopeLabel.value}`],
      updated_at: '',
    }
  }
  nextTick(() => natFcChart?.clear())
}

function forecastQualityHintShort(hint) {
  if (!hint) return ''
  if (hint.includes('疑似脏数据')) {
    return '疑似脏数据：训练样本已按质量规则排除，热力地图仍为源站原始报价'
  }
  return hint.length > 64 ? `${hint.slice(0, 64)}…` : hint
}

function syncNatForecastTrainingDisplayFromResult(fc) {
  if (natForecastTraining.value.running) return
  const scopeLine = `当前口径：${natForecastScopeLabel.value}`
  if (fc?.status === 'ok' || (fc?.ensemble || []).length) {
    const lines = [scopeLine]
    if (fc.winner_model) lines.push(`冠军模型：${fc.winner_model}`)
    if (fc.sample_count != null) lines.push(`有效样本：${fc.sample_count} 天`)
    natForecastTraining.value = {
      ...natForecastTraining.value,
      running: false,
      finished: false,
      status: 'idle',
      phase: 'idle',
      phase_label: '预测快照已就绪',
      progress_pct: 0,
      display_progress_pct: 0,
      message: `已加载 ${natForecastScopeLabel.value} 的本地预测快照`,
      detail_lines: lines,
    }
    return
  }
  if (fc?.status === 'needs_training') {
    const lines = [scopeLine]
    if (fc.sample_count != null) lines.push(`历史样本：${fc.sample_count} 天`)
    if (fc.raw_sample_count != null && fc.raw_sample_count !== fc.sample_count) {
      lines.push(`原始报价：${fc.raw_sample_count} 天（未过质量规则）`)
    }
    const hint = fc.quality_hint || ''
    natForecastTraining.value = {
      ...natForecastTraining.value,
      running: false,
      finished: false,
      status: 'idle',
      phase: 'idle',
      phase_label: hint ? '源站数据质量问题' : '暂无预测快照',
      progress_pct: 0,
      display_progress_pct: 0,
      training_scope: '',
      eta_text: '',
      message: hint
        ? forecastQualityHintShort(hint)
        : (fc.message || '该口径尚未训练预测，可点击「更新当前预测」'),
      detail_lines: lines,
    }
    return
  }
  if (fc?.status === 'insufficient') {
    const lines = [scopeLine]
    if (fc.sample_count != null) lines.push(`有效样本：${fc.sample_count} 天`)
    if (fc.raw_sample_count != null && fc.raw_sample_count !== fc.sample_count) {
      lines.push(`原始报价：${fc.raw_sample_count} 天（未过质量规则）`)
    }
    const hint = fc.quality_hint || ''
    const reason = fc.reliability_reason || fc.message || '有效样本不足 30 天，不生成正式预测曲线'
    if (!hint) lines.push(reason)
    natForecastTraining.value = {
      ...natForecastTraining.value,
      running: false,
      finished: false,
      status: 'idle',
      phase: 'idle',
      phase_label: hint ? '源站数据质量问题' : '样本不足',
      progress_pct: 0,
      display_progress_pct: 0,
      training_scope: '',
      eta_text: '',
      message: hint ? forecastQualityHintShort(hint) : reason,
      detail_lines: lines,
    }
    return
  }
  if (fc?.status && fc.status !== 'loading') {
    natForecastTraining.value = {
      ...natForecastTraining.value,
      running: false,
      finished: false,
      message: fc.message || `已读取 ${natForecastScopeLabel.value} 数据`,
      phase_label: fc.reliability_label || '已读取',
      detail_lines: [scopeLine],
    }
  }
}

function onNatForecastScopeChange() {
  resetNatForecastViewForScopeChange()
  return loadNatForecast()
}
const natMoversLoading = ref(false)
const natMoversDistrict = ref('')
const natMoversCategory = ref('')
const natMoversScate = ref('')
const natMoversWindow = ref(7)
const NAT_MOVERS_WINDOW_OPTIONS = [3, 5, 7, 14, 30]
const natMovers = reactive({ latest_date: '', window: 7, district_id: null, district_name: '', gainers: [], losers: [] })
const natMoversMoreVisible = ref(false)
const natMoversMoreLoading = ref(false)
const natMoversFull = reactive({ latest_date: '', window: 7, gainers: [], losers: [] })
const natSpreadLoading = ref(false)
const natSpread = ref([])
const natSpreadMoreVisible = ref(false)
const natSpreadMoreLoading = ref(false)
const natSpreadFull = ref([])
const natSpreadDate = ref('')
const natQualityPolicy = ref('strict')
const natMoverQualitySummary = ref({ excluded_count: 0, flagged_included_count: 0 })
const natSpreadQualitySummary = ref({ excluded_count: 0, flagged_included_count: 0 })
/** 卡片区预览（各约 6 条）是否已拉取；Top100 仅在点击「更多」时请求 */
const natMoversSpreadPreviewDone = ref(false)
let natMoversSpreadIO = null

// 涨跌幅排名（统计日 vs 前 N 日均价；与异动雷达独立）
const NAT_CHANGE_BASELINE_OPTIONS = [3, 5, 7, 14]
const natChangeBaselineDays = ref(3)
const natChangeDistrict = ref(4)
const natChangeCategory = ref('')
const natChangeScate = ref('')
const natChangeLoading = ref(false)
const natChangePreviewDone = ref(false)
const natChangeRank = reactive({ latest_date: '', gainers: [], losers: [] })
const natChangeRankGainRef = ref(null)
const natChangeRankLossRef = ref(null)
let natChangeRankGainChart = null
let natChangeRankLossChart = null
let natChangeIO = null
let natChangeRankRO = null

const natChangeScateOptions = computed(() =>
  natChangeCategory.value
    ? natSubcategories.value.filter((s) => s.cate_id === natChangeCategory.value)
    : natSubcategories.value,
)

const natChangeCompareHint = computed(() => {
  const days = natChangeRank.baseline_days || natChangeBaselineDays.value || 3
  const date = natChangeRank.latest_date || '—'
  return `日期：${date}（结果取自更新日价与前${days}日均价对比）`
})

const natChangeFilterSummary = computed(() => {
  const parts = []
  const d = (natDistrictOptions.value || []).find((x) => x.id === natChangeDistrict.value)
  parts.push(d?.name || '全国')
  const c = (natCategoryOptions.value || []).find((x) => x.id === natChangeCategory.value)
  if (c?.name) parts.push(c.name)
  if (natChangeScate.value) parts.push(natChangeScate.value)
  parts.push(`前 ${natChangeBaselineDays.value || 3} 日`)
  return parts.join(' · ')
})

const natChangeRankReady = computed(() => natChangePreviewDone.value && !natChangeLoading.value)

const natChangeRankEmptyAll = computed(
  () =>
    natChangeRankReady.value
    && !(natChangeRank.gainers || []).length
    && !(natChangeRank.losers || []).length,
)

function natChangeRequestParams() {
  return {
    district_id: natChangeDistrict.value || '',
    cate_id: natChangeCategory.value || '',
    scate: natChangeScate.value || '',
    baseline_days: natChangeBaselineDays.value || 3,
  }
}

function buildChangeRankBarOption(rows, colorStops) {
  const list = [...(rows || [])].slice(0, 10).reverse()
  const names = list.map((r) => {
    const n = r.goods_name || r.label || ''
    return n.length > 14 ? `${n.slice(0, 14)}…` : n
  })
  const vals = list.map((r) => Math.abs(Number(r.pct) || 0))
  const maxV = Math.max(...vals, 1)
  return {
    backgroundColor: 'transparent',
    grid: { left: 4, right: 48, top: 4, bottom: 4, containLabel: true },
    xAxis: { type: 'value', max: maxV * 1.15, show: false },
    yAxis: {
      type: 'category',
      data: names,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#b8cdd6', fontSize: 11 },
    },
    series: [{
      type: 'bar',
      data: vals,
      barWidth: 14,
      itemStyle: {
        borderRadius: [0, 6, 6, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, colorStops),
      },
      label: {
        show: true,
        position: 'right',
        color: '#dffbff',
        fontSize: 11,
        fontWeight: 700,
        formatter: (p) => `${p.value}%`,
      },
    }],
  }
}

function renderNatChangeRankCharts() {
  const gainers = [...(natChangeRank.gainers || [])]
  const losersRaw = [...(natChangeRank.losers || [])]
  const losers = losersRaw.map((r) => ({ ...r, pct: Math.abs(r.pct) }))
  if (natChangeRankGainRef.value) {
    if (!natChangeRankGainChart) natChangeRankGainChart = echarts.init(natChangeRankGainRef.value)
    natChangeRankGainChart.off('click')
    if (!gainers.length) {
      natChangeRankGainChart.clear()
    } else {
      natChangeRankGainChart.setOption(
        buildChangeRankBarOption(gainers, [
          { offset: 0, color: '#ffb347' },
          { offset: 1, color: '#ff6b6b' },
        ]),
        true,
      )
      natChangeRankGainChart.on('click', (p) => {
        const row = [...gainers].reverse()[p.dataIndex]
        if (row) drillNatMover(row)
      })
    }
  }
  if (natChangeRankLossRef.value) {
    if (!natChangeRankLossChart) natChangeRankLossChart = echarts.init(natChangeRankLossRef.value)
    natChangeRankLossChart.off('click')
    if (!losersRaw.length) {
      natChangeRankLossChart.clear()
    } else {
      natChangeRankLossChart.setOption(
        buildChangeRankBarOption(losers, [
          { offset: 0, color: '#8ee4b8' },
          { offset: 1, color: '#3ecf8e' },
        ]),
        true,
      )
      natChangeRankLossChart.on('click', (p) => {
        const row = [...losersRaw].reverse()[p.dataIndex]
        if (row) drillNatMover(row)
      })
    }
  }
}

function setupNatChangeChartResize() {
  natChangeRankRO?.disconnect()
  const rankEl = document.getElementById('zgsec-change-rank')
  if (rankEl) {
    natChangeRankRO = new ResizeObserver(() => {
      natChangeRankGainChart?.resize()
      natChangeRankLossChart?.resize()
    })
    natChangeRankRO.observe(rankEl)
  }
}

async function loadNatChangeRanking() {
  natChangeLoading.value = true
  try {
    const res = await getZgChangeRanking({ ...natChangeRequestParams(), limit: 10 })
    Object.assign(natChangeRank, res || { gainers: [], losers: [] })
    await nextTick()
    renderNatChangeRankCharts()
    setupNatChangeChartResize()
  } catch (e) {
    console.error('[mining] zg change ranking failed', e)
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载涨跌幅排名失败')
  } finally {
    natChangeLoading.value = false
  }
}

function onNatChangeCategoryChange() {
  natChangeScate.value = ''
  if (natChangePreviewDone.value) loadNatChangeRanking()
}

function onNatChangeFilterChange() {
  if (natChangePreviewDone.value) loadNatChangeRanking()
}

function onNatChangeBaselineChange() {
  if (natChangePreviewDone.value) loadNatChangeRanking()
}

async function loadNatChangePreview(force = false) {
  if (natChangePreviewDone.value && !force) return
  await loadNatChangeRanking()
  natChangePreviewDone.value = true
}

function setupNatChangeLazy() {
  nextTick(() => {
    const el = document.getElementById('zgsec-change-rank')
    if (!el || natChangeIO) return
    natChangeIO = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          loadNatChangePreview()
          natChangeIO?.disconnect()
          natChangeIO = null
        }
      },
      { rootMargin: '120px', threshold: 0.05 },
    )
    natChangeIO.observe(el)
  })
}

function disposeNatChangeCharts() {
  natChangeRankGainChart?.dispose()
  natChangeRankLossChart?.dispose()
  natChangeRankGainChart = null
  natChangeRankLossChart = null
  natChangeRankRO?.disconnect()
  natChangeRankRO = null
}

const natBriefingLoading = ref(false)
const natBriefing = ref('')
const natBriefingReport = ref(null)
const natBriefingSource = ref('')
const natBackfillVisible = ref(false)
const natBackfillLoading = ref(false)
const natBackfillPreview = ref({
  latest_date: '',
  end_date: '',
  start_date: '',
  missing_days: [],
  day_count: 0,
  message: '',
})
const natBackfillStatus = ref({
  running: false,
  finished: false,
  total: 0,
  processed: 0,
  success: 0,
  sub_total: 0,
  sub_processed: 0,
  current: null,
  progress_pct: 0,
  phase: 'crawl',
  rebuild_pct: 0,
  logs: [],
  message: '',
})
const natBackfillTerminalRef = ref(null)
let natBackfillPollTimer = null
const natCredVisible = ref(false)
const natCredLoading = ref(false)
const natCredTestLoading = ref(false)
const natCredForm = reactive({
  username: '',
  password: '',
})
const natCredMeta = ref({ source: '', updated_at: '', hint: '' })
const natCredTestResult = ref(null)
// 12 省短名 → ECharts/DataV 全名
const PROV_FULL = { 北京: '北京市', 天津: '天津市', 上海: '上海市', 河北: '河北省', 江苏: '江苏省', 湖北: '湖北省', 湖南: '湖南省', 福建: '福建省', 广东: '广东省', 河南: '河南省', 浙江: '浙江省', 安徽: '安徽省' }
const natTrendRef = ref(null)
const natCompareRef = ref(null)
let natTrendChart = null
let natCompareChart = null
let natTrendResizeObserver = null
let natCompareResizeObserver = null
let natProductSearchTimer = null

function natFallbackDateRange() {
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 29)
  const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return [ymd(start), ymd(end)]
}

async function onNatProductRemoteQuery(query) {
  if (natProductSearchTimer) clearTimeout(natProductSearchTimer)
  natProductSearchTimer = setTimeout(async () => {
    natProductSearchLoading.value = true
    try {
      const res = await getZgProductHints({ q: query || '' })
      const hints = res?.products || []
      rememberSku(hints)
      // 选项为 {value: sku_key, label}；保留已选项以便回显
      const selected = natProds.value.map((k) => ({ value: k, label: natSkuLabels.value[k] || k }))
      const merged = new Map()
      ;[...selected, ...hints.map((s) => ({ value: s.sku_key, label: s.label }))].forEach((o) => merged.set(o.value, o))
      natProductOptions.value = [...merged.values()]
    } catch (error) {
      console.error('[mining] zg product hints failed', error)
    } finally {
      natProductSearchLoading.value = false
    }
  }, 220)
}

async function loadNatOverview() {
  natOverviewLoading.value = true
  try {
    // KPI 单日快照：取所选区间末日，未选则后端默认最新采集日
    const end = (natDateRange.value || [])[1] || ''
    const res = await getZgOverview({
      date: end,
      district_id: natDistrict.value || '',
      cate_id: natCategory.value || '',
      scate: natScate.value || '',
    })
    Object.assign(natKpi, {
      total_rows: res?.total_rows || 0,
      distinct_goods: res?.distinct_goods || 0,
      distinct_skus: res?.distinct_skus || 0,
      distinct_districts: res?.distinct_districts || 0,
      distinct_categories: res?.distinct_categories || 0,
      snapshot_date: res?.snapshot_date || '',
    })
    natCategoryBreakdown.value = res?.category_breakdown || []
    natTopGoods.value = res?.top_skus || []
    rememberSku(natTopGoods.value)
  } finally {
    natOverviewLoading.value = false
  }
}

async function loadNatTimeseries() {
  if (!natProds.value.length) {
    ElMessage.warning('请至少选择一个 SKU')
    return
  }
  natChartLoading.value = true
  try {
    const [start, end] = natDateRange.value || []
    const res = await getZgTimeseries({
      sku_keys: natProds.value,
      district_id: natDistrict.value || '',
      start_date: start,
      end_date: end,
    })
    natTsData.value = res || { dates: [], series: [] }
    await nextTick()
    renderNatTrend()
  } finally {
    natChartLoading.value = false
  }
}

async function loadNatCompare(sku) {
  const key = sku || natProds.value[0]
  if (!key) return
  natCompareLoading.value = true
  try {
    const res = await getZgCompare({ sku_key: key })
    natCompareData.value = res || { date: '', labels: [], values: [] }
    await nextTick()
    renderNatCompare()
  } finally {
    natCompareLoading.value = false
  }
}

async function loadNatDetail() {
  natDetailLoading.value = true
  try {
  const [start, end] = natDateRange.value || []
  const sku = natProds.value[0] || ''
  // 选中具体 SKU 时明细精确锁定该 SKU（规格/单位一致）；未选则按分类/子类宽泛浏览
  const res = await getZgPrices(sku ? {
    start_date: start,
    end_date: end,
    district_id: natDistrict.value || '',
    sku_key: sku,
    page: natDetailPage.value,
    page_size: natDetailPageSize.value,
  } : {
    start_date: start,
    end_date: end,
    district_id: natDistrict.value || '',
    cate_id: natCategory.value || '',
    scate: natScate.value || '',
    page: natDetailPage.value,
    page_size: natDetailPageSize.value,
  })
  natDetailRows.value = res?.rows || []
  natDetailTotal.value = res?.total || 0
  } finally {
    natDetailLoading.value = false
  }
}

function renderNatTrend() {
  if (!natTrendRef.value) return
  if (!natTrendChart) natTrendChart = echarts.init(natTrendRef.value)
  const dates = natTsData.value.dates || []
  const colors = ['#00e5ff', '#68fadd', '#f0a6ff', '#ffcc66', '#7aa7ff', '#ff7a90']
  natTrendChart.setOption({
    color: colors,
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(8, 13, 24, .96)', borderColor: 'rgba(0,229,255,.35)', textStyle: { color: '#e8fbff' } },
    legend: { top: 6, textStyle: { color: '#c7d9df' }, type: 'scroll' },
    grid: { left: 50, right: 24, top: 52, bottom: 72 },
    xAxis: { type: 'category', data: dates, boundaryGap: false, axisLabel: { color: '#93a8b2', rotate: 28 }, axisLine: { lineStyle: { color: 'rgba(0,229,255,.25)' } } },
    yAxis: { type: 'value', name: '元', nameTextStyle: { color: '#93a8b2' }, axisLabel: { color: '#93a8b2' }, splitLine: { lineStyle: { color: 'rgba(0,229,255,.09)' } } },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 22, bottom: 16, borderColor: 'rgba(0,229,255,.2)', textStyle: { color: '#93a8b2' } }],
    series: (natTsData.value.series || []).map((ser, idx) => ({
      name: ser.name,
      type: 'line',
      smooth: true,
      connectNulls: false,
      showSymbol: true,
      symbolSize: 5,
      lineStyle: { width: 2 },
      areaStyle: { opacity: idx === 0 ? 0.14 : 0.05 },
      data: ser.values || [],
    })),
  }, true)
  natTrendChart.resize()
  requestAnimationFrame(() => natTrendChart?.resize())
  setTimeout(() => natTrendChart?.resize(), 120)
  natTrendResizeObserver?.disconnect()
  natTrendResizeObserver = new ResizeObserver(() => natTrendChart?.resize())
  natTrendResizeObserver.observe(natTrendRef.value)
}

function renderNatCompare() {
  if (!natCompareRef.value) return
  if (!natCompareChart) natCompareChart = echarts.init(natCompareRef.value)
  const labels = natCompareData.value.labels || []
  const values = natCompareData.value.values || []
  natCompareChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(8, 13, 24, .96)', borderColor: 'rgba(0,229,255,.35)', textStyle: { color: '#e8fbff' } },
    grid: { left: 60, right: 24, top: 20, bottom: 64 },
    xAxis: { type: 'category', data: labels, axisLabel: { color: '#93a8b2', rotate: 32, interval: 0 }, axisLine: { lineStyle: { color: 'rgba(0,229,255,.25)' } } },
    yAxis: { type: 'value', name: '均价', nameTextStyle: { color: '#93a8b2' }, axisLabel: { color: '#93a8b2' }, splitLine: { lineStyle: { color: 'rgba(0,229,255,.09)' } } },
    series: [{
      type: 'bar',
      data: values,
      barMaxWidth: 34,
      itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#00e5ff' }, { offset: 1, color: 'rgba(0,229,255,.25)' }]), borderRadius: [4, 4, 0, 0] },
    }],
  }, true)
  natCompareChart.resize()
  requestAnimationFrame(() => natCompareChart?.resize())
  setTimeout(() => natCompareChart?.resize(), 120)
  natCompareResizeObserver?.disconnect()
  natCompareResizeObserver = new ResizeObserver(() => natCompareChart?.resize())
  natCompareResizeObserver.observe(natCompareRef.value)
}

// 品种/趋势/对比/明细/预测/地图 并行发起，互不阻塞；任一失败不影响其它卡片
function refreshNatSections() {
  loadNatTimeseries().catch((e) => console.error('[mining] zg timeseries failed', e))
  loadNatCompare(natProds.value[0]).catch((e) => console.error('[mining] zg compare failed', e))
  loadNatDetail().catch((e) => console.error('[mining] zg detail failed', e))
  loadNatForecast().catch((e) => console.error('[mining] zg forecast failed', e))
  loadNatMap().catch((e) => console.error('[mining] zg map failed', e))
}

async function loadNatIndex() {
  natIndexLoading.value = true
  try {
    const res = await getZgIndex()
    Object.assign(natIndex, res || {})
    await nextTick()
    renderNatIndex()
  } finally {
    natIndexLoading.value = false
  }
}

async function loadNatQuality() {
  natQualityLoading.value = true
  try {
    Object.assign(natQuality, (await getZgQuality()) || {})
  } finally {
    natQualityLoading.value = false
  }
}

async function openNatSuspiciousDialog() {
  // 历史浏览器：始终可打开，未选日期时默认最新快照日
  if (!natQualityFlagDate.value) natQualityFlagDate.value = natQuality.snapshot_date || ''
  natSuspiciousVisible.value = true
  natSuspiciousLoading.value = true
  natSuspiciousRows.value = []
  try {
    const res = await getZgQualityFlags({
      date: natQualityFlagDate.value || '',
      severity: natQualityFlagSeverity.value,
      status: natQualityFlagStatus.value,
      q: natQualityFlagQuery.value,
      limit: 500,
    })
    natSuspiciousRows.value = res?.rows || []
    Object.assign(natSuspiciousMeta, {
      snapshot_date: res?.snapshot_date || natQuality.snapshot_date || '',
      ratio_threshold: res?.ratio_threshold ?? 5,
      total: res?.total ?? natSuspiciousRows.value.length,
    })
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载疑似脏数据列表失败')
    natSuspiciousVisible.value = false
  } finally {
    natSuspiciousLoading.value = false
  }
}

async function reloadNatQualityFlags() {
  if (!natSuspiciousVisible.value) return
  await openNatSuspiciousDialog()
}

// 趋势条：归一化高度 + 点击切换日期
const natQualityTrendMax = computed(() =>
  Math.max(1, ...(natQuality.quality_trend || []).map((d) => Number(d.high || 0) + Number(d.medium || 0))),
)
function qualityTrendBarHeight(d) {
  const v = Number(d.high || 0) + Number(d.medium || 0)
  return Math.round((v / natQualityTrendMax.value) * 100)
}
async function selectQualityTrendDay(d) {
  if (!d?.date) return
  natQualityFlagDate.value = d.date
  await reloadNatQualityFlags()
}

function qualityStatusLabel(status) {
  return {
    open: '待处理',
    confirmed_valid: '已确认有效',
    corrected: '已修正',
    quarantined: '已隔离',
    resolved: '已恢复',
  }[status] || status || '—'
}

const QUALITY_SKU_SEP = '\u001f'

function splitQualitySkuKey(skuKey) {
  const parts = String(skuKey || '').split(QUALITY_SKU_SEP)
  while (parts.length < 5) parts.push('')
  return {
    goods_name: parts[0] || '',
    spec: parts[1] || '',
    unit: parts[2] || '',
    scate_name: parts[4] || '',
  }
}

function qualitySkuLabel(row) {
  const parsed = splitQualitySkuKey(row?.sku_key)
  const gn = row?.goods_name || parsed.goods_name
  const spec = parsed.spec
  const unit = parsed.unit
  const scate = row?.scate_name || parsed.scate_name
  let label = spec ? `${gn} ${spec}`.trim() : `${gn}${unit ? `（${unit}）` : ''}`
  if (scate) label = `${label} · ${scate}`
  return label.trim() || gn || '—'
}

async function drillQualityFlag(row) {
  if (!row?.sku_key) {
    ElMessage.warning('缺少 SKU 标识')
    return
  }
  const dataDate = row?.data_date || natSuspiciousMeta.snapshot_date
  if (dataDate) {
    const end = new Date(`${dataDate}T00:00:00`)
    const start = new Date(end)
    start.setDate(start.getDate() - 29)
    const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    natDateRange.value = [ymd(start), dataDate]
  }
  natSuspiciousVisible.value = false
  await drillNatMover({
    sku_key: row.sku_key,
    label: qualitySkuLabel(row),
    goods_name: row.goods_name,
  })
}

function qualityFlagDate(row) {
  return row?.data_date || natSuspiciousMeta.snapshot_date || '—'
}

function formatVerifyPriceSnapshot(snapshot) {
  if (!snapshot) return '—'
  const minPart = snapshot.min_province
    ? `${snapshot.min_province} ${snapshot.min_price ?? '—'}`
    : `${snapshot.min_price ?? '—'}`
  const maxPart = snapshot.max_province
    ? `${snapshot.max_province} ${snapshot.max_price ?? '—'}`
    : `${snapshot.max_price ?? '—'}`
  const ratio = snapshot.ratio != null ? ` · 倍数 ${snapshot.ratio}×` : ''
  return `低 ${minPart} / 高 ${maxPart}${ratio}`
}

async function verifyQualityFlagByRecrawl(row) {
  if (correctingFlagId.value != null) return
  try {
    await ElMessageBox.confirm(
      `将对「${row.goods_name}」在统计日 ${row.data_date || natSuspiciousMeta.snapshot_date || '—'} 重新爬取官网价格，核验是否已修正。预计需数十秒，是否继续？`,
      '二次爬虫核验',
      { type: 'info', confirmButtonText: '开始核验', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  correctingFlagId.value = row.id
  try {
    const res = await postZgQualityFlagVerifyRecrawl(row.id)
    const detail = [
      res?.message || (res?.updated ? '官网价格已更新，本地数据已同步' : '二次爬虫确认数据并未更新'),
      '',
      `核验前：${formatVerifyPriceSnapshot(res?.before)}`,
      `核验后：${formatVerifyPriceSnapshot(res?.after)}`,
    ].join('\n')
    await ElMessageBox.alert(detail, res?.updated ? '官网已更新' : '数据未变化', {
      type: res?.updated ? 'success' : 'warning',
      confirmButtonText: '知道了',
    })
    await Promise.all([loadNatQuality(), reloadNatQualityFlags(), loadNatMoversSpreadPreview(true)])
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '二次爬虫核验失败')
  } finally {
    correctingFlagId.value = null
  }
}

async function actOnQualityFlag(row, action) {
  const actionLabel = { isolate: '隔离', restore: '恢复参与计算' }[action]
  if (!actionLabel) return
  await ElMessageBox.confirm(`确认对「${row.goods_name}」执行${actionLabel}？`, '质量数据处置', {
    type: action === 'isolate' ? 'warning' : 'info',
  })
  await postZgQualityFlagAction(row.id, {
    action,
    note: actionLabel,
  })
  ElMessage.success('质量状态已更新，相关派生指标已重建')
  await Promise.all([loadNatQuality(), reloadNatQualityFlags(), loadNatMoversSpreadPreview(true)])
}

// PDF 日报（LLM + 库内真实数据）
const natDailyReportVisible = ref(false)
const natDailyReportLoading = ref(false)
const natDailyReportPdfLoading = ref(false)
const natDailyReport = ref({ title: '', sections: [], source: '', generated_at: '' })

function natDailyReportRequestBody() {
  const [start, end] = natDateRange.value || []
  const body = {
    report_date: natKpi.snapshot_date || natKpi.latest_date || '',
    appendix_sku_key: natProds.value[0] || '',
    appendix_start_date: start || '',
    appendix_end_date: end || '',
  }
  if (natDistrict.value) body.district_id = Number(natDistrict.value)
  if (natCategory.value) body.cate_id = Number(natCategory.value)
  return body
}

function natDailyReportPreviewText() {
  const r = natDailyReport.value || {}
  const lines = [(r.title || '全国农产品价格日报'), `来源：${r.source || '—'} · ${r.generated_at || ''}`, '']
  const board = r.decision_board || {}
  if (board.headline) {
    lines.push('【智能决策看板】', board.headline, '')
    ;(board.items || []).slice(0, 4).forEach((it) => {
      lines.push(`  [${it.level}] ${it.title}`)
      lines.push(`    建议：${it.action || ''}`)
    })
    lines.push('')
  }
  ;(r.sections || []).forEach((sec) => {
    lines.push(sec.heading || '')
    const paras = Array.isArray(sec.paragraphs)
      ? sec.paragraphs
      : sec.paragraphs
        ? [String(sec.paragraphs)]
        : []
    paras.forEach((p) => lines.push(`  ${p}`))
    lines.push('')
  })
  return lines.join('\n').trim() || '点击「生成日报」预览正文（数据来自系统，叙述由 LLM 排版）'
}

async function generateNatDailyReportPreview() {
  natDailyReportLoading.value = true
  try {
    natDailyReport.value = await postZgDailyReportJson(natDailyReportRequestBody())
    ElMessage.success('日报正文已生成，可下载 PDF')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '日报生成失败')
  } finally {
    natDailyReportLoading.value = false
  }
}

async function openNatDailyReportDialog() {
  natDailyReportVisible.value = true
  if (!(natDailyReport.value?.sections || []).length) {
    await generateNatDailyReportPreview()
  }
}

function downloadBlobFile(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function downloadNatDailyReportPdf() {
  natDailyReportPdfLoading.value = true
  try {
    const blob = await postZgDailyReportPdf(natDailyReportRequestBody())
    const rd = natKpi.snapshot_date || natKpi.latest_date || 'report'
    downloadBlobFile(blob, `全国农产品价格日报_${rd}.pdf`)
    ElMessage.success('PDF 已下载')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || 'PDF 下载失败')
  } finally {
    natDailyReportPdfLoading.value = false
  }
}

// 导出 Excel 明细数据（多 sheet）
const natExporting = ref(false)
async function exportNatExcelData() {
  natExporting.value = true
  try {
    const wb = XLSX.utils.book_new()
    // KPI + 可信度
    const kpi = [
      { 指标: '当日记录数', 值: natKpi.total_rows }, { 指标: '当日SKU数', 值: natKpi.distinct_skus },
      { 指标: '覆盖省份', 值: natKpi.distinct_districts }, { 指标: '商品分类', 值: natKpi.distinct_categories },
      { 指标: '采集天数', 值: natKpi.days_covered }, { 指标: '最新采集日', 值: natKpi.latest_date },
      { 指标: '全国总指数', 值: natIndex.overall_latest }, { 指标: '总指数较基期%', 值: natIndex.overall_change_pct },
      { 指标: '数据可信度', 值: natQuality.health_score }, { 指标: '价格可解析率%', 值: natQuality.parse_rate },
      { 指标: '疑似脏数据SKU', 值: natQuality.suspicious_skus }, { 指标: '指数篮子覆盖%', 值: natQuality.basket_coverage },
    ]
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(kpi), 'KPI与可信度')
    // 指数序列（总 + 分类）
    const idxRows = (natIndex.dates || []).map((d, i) => {
      const row = { 日期: d, 全国总指数: natIndex.overall?.[i] ?? '' }
      ;(natIndex.categories || []).forEach((c) => { row[c.cate_name] = c.series?.[i] ?? '' })
      return row
    })
    if (idxRows.length) XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(idxRows), '价格指数')
    // 异动榜
    const mv = [
      ...(natMovers.gainers || []).map((r) => ({ 类型: '涨', SKU: r.goods_name, 分类: r.cate_name, 上期价: r.old, 最新价: r.new, '涨跌%': r.pct })),
      ...(natMovers.losers || []).map((r) => ({ 类型: '跌', SKU: r.goods_name, 分类: r.cate_name, 上期价: r.old, 最新价: r.new, '涨跌%': r.pct })),
    ]
    if (mv.length) XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(mv), '价格异动榜')
    // 价差榜
    const sp = (natSpread.value || []).map((r) => ({ SKU: r.goods_name, 分类: r.cate_name, '价差%': r.spread_pct, 最低价: r.min_price, 最高价: r.max_price, 最便宜省: r.cheapest, 最贵省: r.priciest, 省覆盖: r.province_count }))
    if (sp.length) XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(sp), '区域价差榜')
    // 明细（当前主选 SKU 全量）
    const sku = natProds.value[0]
    if (sku) {
      const [start, end] = natDateRange.value || []
      const dr = await getZgPrices({ start_date: start, end_date: end, district_id: natDistrict.value || '', sku_key: sku, page: 1, page_size: 1000 }).catch(() => ({ rows: [] }))
      const detail = (dr?.rows || []).map((r) => ({ 采集日: r.crawl_date, 省份: r.district_name, 分类: r.cate_name, 子类: r.scate_name, 品名: r.goods_name, 规格: r.spec, 价格: r.price, 单位: r.unit, 产地: r.place, 更新日: r.update_date }))
      if (detail.length) XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(detail), '行情明细')
    }
    XLSX.writeFile(wb, `全国农产品价格_${natKpi.snapshot_date || natKpi.latest_date || ''}.xlsx`)
    ElMessage.success('报表已导出')
  } catch (e) {
    ElMessage.error('导出失败：' + (e?.message || e))
  } finally {
    natExporting.value = false
  }
}

// —— SKU 深度抽屉 ——
const natSkuDrawerOpen = ref(false)
const natSkuDrawerLoading = ref(false)
const natSkuDrawerKey = ref('')
const natSkuDrawerLabel = ref('')
const natSkuDrawerStats = ref(null)
const natSkuDrawerProvinces = ref([])
const natSkuDrawerForecast = ref({})
const natSkuDrawerRows = ref([])
const natSkuDrawerChartRef = ref(null)
let natSkuDrawerChart = null

function _statsOf(values) {
  const v = (values || []).filter((x) => x != null).slice().sort((a, b) => a - b)
  if (!v.length) return null
  const q = (p) => v[Math.min(v.length - 1, Math.round(p * (v.length - 1)))]
  const mean = v.reduce((a, b) => a + b, 0) / v.length
  return { min: v[0], max: v[v.length - 1], mean: Math.round(mean * 100) / 100, median: q(0.5), p10: q(0.1), p90: q(0.9), n: v.length }
}

async function openNatSkuDrawer(skuKey, label) {
  if (!skuKey) return
  natSkuDrawerKey.value = skuKey
  natSkuDrawerLabel.value = label || natSkuLabels.value[skuKey] || skuName(skuKey)
  natSkuDrawerOpen.value = true
  natSkuDrawerLoading.value = true
  natSkuDrawerStats.value = null
  natSkuDrawerProvinces.value = []
  natSkuDrawerForecast.value = {}
  natSkuDrawerRows.value = []
  try {
    const [start, end] = natDateRange.value || []
    const [ts, cmp, fc, pr] = await Promise.all([
      getZgTimeseries({ sku_keys: [skuKey], start_date: start, end_date: end }).catch(() => ({ dates: [], series: [] })),
      getZgCompare({ sku_key: skuKey }).catch(() => ({ labels: [], values: [] })),
      getZgForecast({ sku_key: skuKey, days: 14 }).catch(() => ({ status: 'failed' })),
      getZgPrices({ sku_key: skuKey, start_date: start, end_date: end, page: 1, page_size: 20 }).catch(() => ({ rows: [] })),
    ])
    const series = ts?.series?.[0]
    natSkuDrawerStats.value = _statsOf(series?.values)
    natSkuDrawerProvinces.value = (cmp?.labels || []).map((n, i) => ({ name: n, value: cmp.values?.[i] }))
    natSkuDrawerForecast.value = fc || {}
    natSkuDrawerRows.value = pr?.rows || []
    await nextTick()
    // mini 走势
    if (natSkuDrawerChartRef.value) {
      if (!natSkuDrawerChart) natSkuDrawerChart = echarts.init(natSkuDrawerChartRef.value)
      natSkuDrawerChart.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis', backgroundColor: 'rgba(8,13,24,.96)', borderColor: 'rgba(0,229,255,.35)', textStyle: { color: '#e8fbff' } },
        grid: { left: 44, right: 14, top: 16, bottom: 30 },
        xAxis: { type: 'category', data: ts?.dates || [], boundaryGap: false, axisLabel: { color: '#93a8b2', fontSize: 10, rotate: 24 } },
        yAxis: { type: 'value', scale: true, axisLabel: { color: '#93a8b2', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(0,229,255,.08)' } } },
        series: [{ type: 'line', smooth: true, showSymbol: false, data: series?.values || [], lineStyle: { color: '#00e5ff', width: 2.5 }, areaStyle: { color: 'rgba(0,229,255,.12)' } }],
      }, true)
      natSkuDrawerChart.resize()
    }
  } finally {
    natSkuDrawerLoading.value = false
  }
}
function onNatSkuDrawerClosed() {
  natSkuDrawerChart?.dispose()
  natSkuDrawerChart = null
}

const NAT_SECTIONS = [
  { id: 'zgsec-index', label: '指数' },
  { id: 'zgsec-map', label: '地图' },
  { id: 'zgsec-trend', label: '趋势' },
  { id: 'zgsec-change-rank', label: '涨跌' },
  { id: 'zgsec-movers', label: '异动' },
  { id: 'zgsec-spread', label: '价差' },
  { id: 'zgsec-detail', label: '明细' },
]
function scrollToNatSection(id) {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function downloadNatChart(chart, name) {
  if (!chart) return
  const url = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#0b101c' })
  const a = document.createElement('a')
  a.href = url
  a.download = `${name}_${natKpi.snapshot_date || ''}.png`
  a.click()
}

function renderNatIndex() {
  if (!natIndexRef.value) return
  if (!natIndexChart) natIndexChart = echarts.init(natIndexRef.value)
  const dates = natIndex.dates || []
  const selected = natIndexSelectedCateIds.value || []
  const series = [
    { name: '全国总指数', type: 'line', smooth: true, showSymbol: false, data: natIndex.overall || [], lineStyle: { color: '#00e5ff', width: 3 }, areaStyle: { color: 'rgba(0,229,255,.12)' },
      markLine: { silent: true, symbol: 'none', lineStyle: { color: 'rgba(255,255,255,.25)', type: 'dashed' }, data: [{ yAxis: 100, label: { formatter: '基期100', color: '#9fb3bc' } }] } },
  ]
  ;(natIndex.categories || []).filter((c) => selected.includes(c.cate_id)).forEach((c) => {
    series.push({ name: c.cate_name, type: 'line', smooth: true, showSymbol: false, data: c.series || [], lineStyle: { width: 2.5 } })
  })
  natIndexChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(8,13,24,.96)', borderColor: 'rgba(0,229,255,.35)', textStyle: { color: '#e8fbff' } },
    legend: {
      show: series.length > 1,
      top: 0,
      right: 8,
      textStyle: { color: '#c7d9df', fontSize: 11 },
      type: 'scroll',
      width: '42%',
    },
    grid: { left: 44, right: 18, top: 34, bottom: 36 },
    xAxis: { type: 'category', data: dates, boundaryGap: false, axisLabel: { color: '#93a8b2', rotate: 24 }, axisLine: { lineStyle: { color: 'rgba(0,229,255,.25)' } } },
    yAxis: { type: 'value', name: '指数', scale: true, nameTextStyle: { color: '#93a8b2' }, axisLabel: { color: '#93a8b2' }, splitLine: { lineStyle: { color: 'rgba(0,229,255,.09)' } } },
    series,
  }, true)
  natIndexChart.resize()
  requestAnimationFrame(() => natIndexChart?.resize())
  natIndexRO?.disconnect()
  natIndexRO = new ResizeObserver(() => natIndexChart?.resize())
  natIndexRO.observe(natIndexRef.value)
}

function toggleNatIndexCate(cateId) {
  const cur = new Set(natIndexSelectedCateIds.value || [])
  if (cur.has(cateId)) cur.delete(cateId)
  else cur.add(cateId)
  natIndexSelectedCateIds.value = [...cur]
  nextTick(() => renderNatIndex())
}

async function ensureChinaMap() {
  if (chinaMapReady) return true
  if (echarts.getMap && echarts.getMap('china')) { chinaMapReady = true; return true }
  try {
    const resp = await fetch('https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json', { cache: 'force-cache' })
    const geo = await resp.json()
    echarts.registerMap('china', geo)
    chinaMapReady = true
    return true
  } catch (e) {
    console.error('[mining] load china geojson failed', e)
    return false
  }
}

async function loadNatMap() {
  natMapLoading.value = true
  try {
    const key = natProds.value[0] || ''
    if (!key) { natMapData.value = { scope: '', metric: 'level', provinces: [] }; return }
    const [res] = await Promise.all([getZgMap({ sku_key: key, metric: 'level' }), ensureChinaMap()])
    natMapData.value = res || { scope: '', metric: 'level', provinces: [] }
    await nextTick()
    renderNatMap()
  } finally {
    natMapLoading.value = false
  }
}

function renderNatMap() {
  if (!natMapRef.value || !chinaMapReady) return
  if (!natMapChart) natMapChart = echarts.init(natMapRef.value)
  const provinces = natMapData.value.provinces || []
  const data = provinces.map((p) => ({ name: PROV_FULL[p.name] || p.name, value: p.value, short: p.name }))
  const vals = data.map((d) => d.value)
  const min = vals.length ? Math.min(...vals) : 0
  const max = vals.length ? Math.max(...vals) : 1
  natMapChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', backgroundColor: 'rgba(8,13,24,.96)', borderColor: 'rgba(0,229,255,.35)', textStyle: { color: '#e8fbff' },
      formatter: (p) => `${p.data?.short || p.name}<br/>中位价：${p.value == null || isNaN(p.value) ? '—' : p.value}` },
    visualMap: { min, max, left: 12, bottom: 12, calculable: true, textStyle: { color: '#9fb3bc' },
      inRange: { color: ['#0b3a45', '#0f7a8c', '#00e5ff', '#ffcc66', '#ff7a90'] } },
    series: [{
      type: 'map', map: 'china', roam: false, data,
      layoutCenter: ['50%', '59%'],
      layoutSize: '116%',
      label: { show: false }, emphasis: { label: { show: true, color: '#fff' }, itemStyle: { areaColor: '#1a6b7a' } },
      selectedMode: 'single',
      select: { itemStyle: { areaColor: '#ffd166', borderColor: '#fff6c7', borderWidth: 1.5 }, label: { show: true, color: '#061018', fontWeight: 800 } },
      itemStyle: { areaColor: 'rgba(20,30,48,.6)', borderColor: 'rgba(0,229,255,.25)' },
    }],
  }, true)
  natMapChart.off('click')
  natMapChart.on('click', (params) => {
    const short = params?.data?.short
    if (!short) return
    drillNatProvince(short)
  })
  if (natForecastDistrictName.value) {
    natMapChart.dispatchAction({ type: 'select', name: PROV_FULL[natForecastDistrictName.value] || natForecastDistrictName.value })
  }
  natMapChart.resize()
  requestAnimationFrame(() => natMapChart?.resize())
  natMapRO?.disconnect()
  natMapRO = new ResizeObserver(() => natMapChart?.resize())
  natMapRO.observe(natMapRef.value)
}

async function loadNatForecast() {
  const key = natProds.value[0] || ''
  if (!key) return
  const scopeKey = natForecastScopeKey()
  const reqId = ++natForecastReqSeq
  natFcLoading.value = true
  try {
    const res = await getZgForecast({ sku_key: key, district_id: natForecastDistrictId.value || '', days: 14 })
    if (reqId !== natForecastReqSeq || scopeKey !== natForecastScopeKey()) return
    const expectedDid = String(natForecastDistrictId.value || '')
    const resDid = res?.district_id != null ? String(res.district_id) : expectedDid
    if (res?.scope === 'province' && resDid !== expectedDid) return
    natForecast.value = res || { status: 'empty', ensemble: [], history: [] }
    syncNatForecastTrainingDisplayFromResult(natForecast.value)
    await nextTick()
    renderNatForecast()
  } finally {
    if (reqId === natForecastReqSeq) natFcLoading.value = false
  }
}

function selectNatForecastProvince(name) {
  const opt = natMapProvinceOptions.value.find((p) => p.name === name)
  const district = (natDistrictOptions.value || []).find((d) => d.name === name)
  natForecastDistrictId.value = String(opt?.id || district?.id || '')
  natForecastDistrictName.value = opt?.name || district?.name || name || ''
  onNatForecastScopeChange().catch((e) => console.error('[mining] zg forecast failed', e))
  nextTick(() => renderNatMap())
}

// 点地图省份：地图/预测跟随 + 把顶部省份筛选也切到该省，联动 KPI/明细（异动/价差为跨省榜单，保持全国）
function drillNatProvince(name) {
  selectNatForecastProvince(name)
  const opt = natMapProvinceOptions.value.find((p) => p.name === name) || (natDistrictOptions.value || []).find((d) => d.name === name)
  const id = opt?.id || ''
  if (!id || natDistrict.value === id) return
  natDistrict.value = id
  natDetailPage.value = 1
  loadNatOverview().catch((e) => console.error('[mining] zg overview failed', e))
  loadNatDetail().catch((e) => console.error('[mining] zg detail failed', e))
  ElMessage.success(`已下钻到 ${name}：KPI 与明细已按该省筛选（在上方「省份」清除可恢复全国）`)
}

function clearNatForecastProvince() {
  natForecastDistrictId.value = ''
  natForecastDistrictName.value = ''
  onNatForecastScopeChange().catch((e) => console.error('[mining] zg forecast failed', e))
  nextTick(() => renderNatMap())
}

function renderNatForecast() {
  if (!natFcRef.value) return
  if (!natFcChart) natFcChart = echarts.init(natFcRef.value)
  const fc = natForecast.value || {}
  if (fc.status === 'loading') {
    natFcChart.clear()
    return
  }
  // 原始报价模式：只画未过质量规则的原始序列，被剔除的天标红点，不外推预测
  if (natForecastRawMode.value && (fc.raw_history || []).length) {
    const raw = fc.raw_history || []
    const excluded = new Set(fc.excluded_dates || [])
    const rDates = raw.map((r) => r.date)
    const rVals = raw.map((r) => r.price)
    const exPoints = raw.map((r) => (excluded.has(r.date) ? r.price : null))
    natFcChart.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis', backgroundColor: 'rgba(8,13,24,.96)', borderColor: 'rgba(228,93,102,.5)', textStyle: { color: '#e8fbff' },
        formatter: (ps) => {
          const d = ps?.[0]?.axisValue || ''
          const v = ps?.[0]?.data
          return `${d}<br/>原始报价：${v ?? '—'} 元${excluded.has(d) ? '<br/><span style="color:#ff8a90">⚠ 被质量规则剔除</span>' : ''}`
        },
      },
      legend: { data: ['原始报价', '被剔除'], top: 4, textStyle: { color: '#c7d9df' } },
      grid: { left: 48, right: 20, top: 38, bottom: 38 },
      xAxis: { type: 'category', boundaryGap: false, data: rDates, axisLabel: { color: '#93a8b2', rotate: 26 }, axisLine: { lineStyle: { color: 'rgba(0,229,255,.25)' } } },
      yAxis: { type: 'value', name: '元', scale: true, nameTextStyle: { color: '#93a8b2' }, axisLabel: { color: '#93a8b2' }, splitLine: { lineStyle: { color: 'rgba(0,229,255,.09)' } } },
      series: [
        { name: '原始报价', type: 'line', smooth: true, data: rVals, showSymbol: false, lineStyle: { color: '#00e5ff', width: 2 }, areaStyle: { color: 'rgba(0,229,255,.08)' } },
        { name: '被剔除', type: 'scatter', data: exPoints, symbolSize: 8, itemStyle: { color: '#e45d66' } },
      ],
    }, true)
    natFcChart.resize()
    requestAnimationFrame(() => natFcChart?.resize())
    natFcRO?.disconnect()
    natFcRO = new ResizeObserver(() => natFcChart?.resize())
    natFcRO.observe(natFcRef.value)
    return
  }
  const hist = fc.history || []
  const ens = fc.ensemble || []
  const hDates = hist.map((r) => r.date)
  const hVals = hist.map((r) => r.price)
  const fDates = ens.map((r) => r.date)
  const allDates = [...hDates, ...fDates]
  const anchorIdx = hDates.length - 1
  const actual = [...hVals, ...fDates.map(() => null)]
  const lastActual = hVals.length ? hVals[hVals.length - 1] : null
  const forecast = hDates.map((_, i) => (i === anchorIdx ? lastActual : null)).concat(ens.map((r) => r.yhat))
  const lower = hDates.map(() => null).concat(ens.map((r) => r.yhat_lower))
  const band = hDates.map(() => null).concat(ens.map((r) => Number((r.yhat_upper - r.yhat_lower).toFixed(3))))
  natFcChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(8,13,24,.96)', borderColor: 'rgba(0,229,255,.35)', textStyle: { color: '#e8fbff' } },
    legend: { data: ['历史实价', '预测'], top: 4, textStyle: { color: '#c7d9df' } },
    grid: { left: 48, right: 20, top: 38, bottom: 38 },
    xAxis: { type: 'category', boundaryGap: false, data: allDates, axisLabel: { color: '#93a8b2', rotate: 26 }, axisLine: { lineStyle: { color: 'rgba(0,229,255,.25)' } } },
    yAxis: { type: 'value', name: '元', scale: true, nameTextStyle: { color: '#93a8b2' }, axisLabel: { color: '#93a8b2' }, splitLine: { lineStyle: { color: 'rgba(0,229,255,.09)' } } },
    series: [
      { name: '_lower', type: 'line', stack: 'band', data: lower, lineStyle: { opacity: 0 }, symbol: 'none', silent: true, tooltip: { show: false } },
      { name: '置信区间', type: 'line', stack: 'band', data: band, lineStyle: { opacity: 0 }, symbol: 'none', areaStyle: { color: 'rgba(255,209,102,.16)' }, tooltip: { show: false } },
      { name: '历史实价', type: 'line', smooth: true, data: actual, showSymbol: false, lineStyle: { color: '#00e5ff', width: 3 }, areaStyle: { color: 'rgba(0,229,255,.10)' } },
      { name: '预测', type: 'line', smooth: true, data: forecast, showSymbol: false, lineStyle: { color: '#ffd166', width: 3, type: 'dashed' },
        markLine: anchorIdx >= 0 ? { silent: true, symbol: 'none', lineStyle: { color: 'rgba(255,209,102,.5)', type: 'dotted' }, data: [{ xAxis: anchorIdx, label: { formatter: '今', color: '#ffd166' } }] } : undefined },
    ],
  }, true)
  natFcChart.resize()
  requestAnimationFrame(() => natFcChart?.resize())
  natFcRO?.disconnect()
  natFcRO = new ResizeObserver(() => natFcChart?.resize())
  natFcRO.observe(natFcRef.value)
}

watch(natForecastRawMode, () => renderNatForecast())

const natMoversScateOptions = computed(() =>
  natMoversCategory.value
    ? natSubcategories.value.filter((s) => s.cate_id === natMoversCategory.value)
    : natSubcategories.value,
)

const natMoversScopeLabel = computed(() => {
  if (natMovers.district_name) return natMovers.district_name
  if (!natMoversDistrict.value) return '全国'
  const d = (natDistrictOptions.value || []).find((x) => x.id === natMoversDistrict.value)
  return d?.name || '所选省份'
})

const natMoversFilterDesc = computed(() => {
  const parts = [natMoversScopeLabel.value]
  if (natMoversCategory.value) {
    const c = (natCategoryOptions.value || []).find((x) => x.id === natMoversCategory.value)
    let cat = c?.name || '所选分类'
    if (natMoversScate.value) cat += ` · ${natMoversScate.value}`
    parts.push(cat)
  }
  return parts.join(' · ')
})

function natMoversRequestParams(limit = 8) {
  return {
    window: natMoversWindow.value || 7,
    limit,
    cate_id: natMoversCategory.value || '',
    scate: natMoversScate.value || '',
    district_id: natMoversDistrict.value || '',
    quality_policy: natQualityPolicy.value,
  }
}

function onNatMoversCategoryChange() {
  natMoversScate.value = ''
  onNatMoversFilterChange()
}

async function loadNatMovers() {
  natMoversLoading.value = true
  try {
    const res = await getZgMovers(natMoversRequestParams(8))
    Object.assign(natMovers, res || { gainers: [], losers: [] })
    natMoverQualitySummary.value = res?.quality_summary || { excluded_count: 0, flagged_included_count: 0 }
  } finally {
    natMoversLoading.value = false
  }
}

function onNatMoversFilterChange() {
  resetNatMoversSpreadFull()
  if (natMoversSpreadPreviewDone.value) {
    loadNatMovers().catch((e) => console.error('[mining] zg movers filter failed', e))
  }
}

async function loadNatSpread() {
  natSpreadLoading.value = true
  try {
    const res = await getZgSpread({
      limit: 8,
      cate_id: natCategory.value || '',
      scate: natScate.value || '',
      quality_policy: natQualityPolicy.value,
    })
    natSpread.value = res?.rows || []
    natSpreadDate.value = res?.date || ''
    natSpreadQualitySummary.value = res?.quality_summary || { excluded_count: 0, flagged_included_count: 0 }
  } finally {
    natSpreadLoading.value = false
  }
}

function resetNatMoversSpreadFull() {
  Object.assign(natMoversFull, { latest_date: '', window: natMoversWindow.value || 7, gainers: [], losers: [] })
  natSpreadFull.value = []
}

/** 卡片预览：滚动到模块附近才拉取（limit 小），不占用首屏 */
async function loadNatMoversSpreadPreview(force = false) {
  if (natMoversSpreadPreviewDone.value && !force) return
  await Promise.all([loadNatMovers(), loadNatSpread()])
  natMoversSpreadPreviewDone.value = true
}

function setupNatMoversSpreadLazy() {
  nextTick(() => {
    const el = document.getElementById('zgsec-movers')
    if (!el || natMoversSpreadIO) return
    natMoversSpreadIO = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          loadNatMoversSpreadPreview()
          natMoversSpreadIO?.disconnect()
          natMoversSpreadIO = null
        }
      },
      { rootMargin: '100px', threshold: 0.05 },
    )
    natMoversSpreadIO.observe(el)
  })
}

/** Top100：仅点击「更多」时请求，进入页面不预加载 */
async function openNatMoversMore() {
  natMoversMoreVisible.value = true
  natMoversMoreLoading.value = true
  try {
    const res = await getZgMovers(natMoversRequestParams(100))
    Object.assign(natMoversFull, res || { gainers: [], losers: [] })
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载异动榜失败')
    natMoversMoreVisible.value = false
  } finally {
    natMoversMoreLoading.value = false
  }
}

async function openNatSpreadMore() {
  natSpreadMoreVisible.value = true
  natSpreadMoreLoading.value = true
  try {
    const res = await getZgSpread({
      limit: 100,
      cate_id: natCategory.value || '',
      scate: natScate.value || '',
      quality_policy: natQualityPolicy.value,
    })
    natSpreadFull.value = res?.rows || []
    natSpreadDate.value = res?.date || natSpreadDate.value
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载价差榜失败')
    natSpreadMoreVisible.value = false
  } finally {
    natSpreadMoreLoading.value = false
  }
}

function onNatMoversMoreRow(row) {
  drillNatMover(row)
  natMoversMoreVisible.value = false
}

function onNatSpreadRow(row) {
  drillNatSpread(row)
}

async function drillNatSpread(row) {
  if (!row?.sku_key) {
    ElMessage.warning('该品种缺少 SKU 标识，无法联动')
    return
  }
  await drillNatMover({ sku_key: row.sku_key, label: row.goods_name, goods_name: row.goods_name })
  natSpreadMoreVisible.value = false
}

async function genNatBriefing() {
  natBriefingLoading.value = true
  try {
    const res = await postZgBriefing()
    natBriefing.value = res?.briefing || ''
    natBriefingReport.value = res?.report || null
    natBriefingSource.value = res?.source || ''
  } catch (e) {
    natBriefing.value = ''
    natBriefingReport.value = null
    natBriefingSource.value = ''
    natBriefing.value = '生成失败，请稍后重试'
  } finally {
    natBriefingLoading.value = false
  }
}

const fcStats = computed(() => {
  const fc = natForecast.value || {}
  const ens = fc.ensemble || []
  return {
    status: fc.status,
    label: fc.reliability_label || '—',
    grade: fc.reliability || 'low',
    anchor: fc.anchor_price,
    next: ens[0]?.yhat,
    day7: ens[6]?.yhat,
    mape: fc.accuracy?.mape,
    hit: fc.accuracy?.hit_rate,
    reason: fc.reliability_reason || '',
    winner: fc.winner_model || '—',
    trainedAt: fc.trained_at ? formatChinaDateTime(fc.trained_at).slice(0, 16) : '—',
    dataDate: fc.data_latest_date || '—',
    sampleCount: fc.sample_count || 0,
    rawSampleCount: fc.raw_sample_count ?? null,
    qualityHint: fc.quality_hint || '',
    method: fc.method || '',
  }
})

function addNatProduct(item) {
  // item 为 {sku_key,label}
  const key = item.sku_key
  rememberSku([item])
  if (!natProds.value.includes(key)) natProds.value = [...natProds.value, key]
  if (!natProductOptions.value.some((o) => o.value === key)) {
    natProductOptions.value = [...natProductOptions.value, { value: key, label: item.label }]
  }
  loadNatTimeseries().catch((e) => console.error('[mining] zg timeseries failed', e))
  loadNatCompare(natProds.value[0]).catch((e) => console.error('[mining] zg compare failed', e))
}

async function drillNatMover(row) {
  if (!row?.sku_key) return
  const item = { sku_key: row.sku_key, label: row.label || row.goods_name || row.sku_key }
  rememberSku([item])
  const optMap = new Map(natProductOptions.value.map((o) => [o.value, o]))
  optMap.set(item.sku_key, { value: item.sku_key, label: item.label })
  natProductOptions.value = [...optMap.values()]
  natProds.value = [item.sku_key]
  if (natMoversDistrict.value) {
    natDistrict.value = natMoversDistrict.value
    natForecastDistrictId.value = String(natMoversDistrict.value)
    const d = (natDistrictOptions.value || []).find((x) => x.id === natMoversDistrict.value)
    natForecastDistrictName.value = d?.name || natMovers.district_name || ''
  } else {
    natForecastDistrictId.value = ''
    natForecastDistrictName.value = ''
  }
  natDetailPage.value = 1
  resetNatForecastViewForScopeChange()
  refreshNatSections()
  ElMessage.success(`已联动查看：${item.label}`)
  await nextTick()
  natMapRef.value?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
}

const natTrendEmpty = computed(() => {
  if (natChartLoading.value) return false
  const series = natTsData.value.series || []
  return !series.some((s) => (s.values || []).some((v) => v != null))
})
const natCompareEmpty = computed(() => !natCompareLoading.value && !(natCompareData.value.labels || []).length)

// 已选 SKU 当前价（从趋势序列派生：末个非空=最新价，首末算区间涨跌）
const natSkuPrices = computed(() => {
  const series = natTsData.value.series || []
  return series.map((s) => {
    const vals = (s.values || []).filter((v) => v != null)
    const last = vals.length ? vals[vals.length - 1] : null
    const first = vals.length ? vals[0] : null
    const chg = first && first > 0 && last != null ? ((last - first) / first) * 100 : null
    return { sku_key: s.sku_key, name: s.name, last, chg }
  })
})

function refreshPrimaryNatSkuViews() {
  const key = natProds.value[0]
  if (!key) return
  loadNatCompare(key).catch((e) => console.error('[mining] zg compare failed', e))
  loadNatMap().catch((e) => console.error('[mining] zg map failed', e))
  onNatForecastScopeChange().catch((e) => console.error('[mining] zg forecast failed', e))
  natDetailPage.value = 1
  loadNatDetail().catch((e) => console.error('[mining] zg detail failed', e))
}

function setPrimaryNatSku(skuKey) {
  if (!skuKey || natProds.value[0] === skuKey) return
  // 把该 SKU 挪到首位 = 主选，驱动 地图/预测/对比/明细
  natProds.value = [skuKey, ...natProds.value.filter((k) => k !== skuKey)]
}

watch(() => natProds.value[0], (key, oldKey) => {
  if (!nationLoaded.value || !key || key === oldKey) return
  // 首次赋值由 bootNational / refreshNatSections 统一加载，避免重复请求
  if (!oldKey) return
  refreshPrimaryNatSkuViews()
})

const natBackfillRunning = computed(() => !!natBackfillStatus.value.running)
const natBackfillProgressStatus = computed(() => {
  if (natBackfillStatus.value.running) return undefined
  if (natBackfillStatus.value.finished && (natBackfillStatus.value.success || 0) > 0) return 'success'
  if (natBackfillStatus.value.finished) return 'warning'
  return undefined
})
const natBackfillProgressPct = computed(() => {
  const s = natBackfillStatus.value || {}
  if (s.phase === 'rebuild' && s.running) {
    return Math.min(100, Math.round(Number(s.rebuild_pct || 0)))
  }
  return Math.min(100, Math.round(Number(s.progress_pct ?? s.progress ?? 0)))
})

function natTodayYmd() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function natYesterdayYmd() {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function backfillLogText(status, fallback = '等待启动') {
  const logs = status?.logs
  if (Array.isArray(logs) && logs.length) return logs.join('\n')
  return status?.message || fallback
}

function mergeNatBackfillStatus(remote) {
  const st = remote || {}
  const logs = Array.isArray(st.logs) && st.logs.length
    ? st.logs
    : (st.message ? [st.message] : natBackfillStatus.value.logs)
  natBackfillStatus.value = { ...natBackfillStatus.value, ...st, logs }
}

function clearNatBackfillPoll() {
  if (natBackfillPollTimer) {
    clearInterval(natBackfillPollTimer)
    natBackfillPollTimer = null
  }
}

function clearNatForecastPoll() {
  if (natForecastPollTimer) {
    clearInterval(natForecastPollTimer)
    natForecastPollTimer = null
  }
}

function resetNatBackfillDisplayIdle() {
  natBackfillStatus.value = {
    running: false,
    finished: false,
    total: 0,
    processed: 0,
    success: 0,
    sub_total: 0,
    sub_processed: 0,
    current: null,
    progress_pct: 0,
    phase: 'crawl',
    rebuild_pct: 0,
    logs: [
      '中农价格网补抓：对比库内最新采集日，仅补缺失日期/缺失省份，已齐全日跳过。',
      '进度条按「省」推进（单日约 12 省），避免长时间停在 0%。',
      '目标结束日默认为昨天（网站通常 18:00 后更新当日价）。',
    ],
    message: '',
  }
}

function scrollNatBackfillTerminal() {
  nextTick(() => {
    const el = natBackfillTerminalRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function refreshNatAfterBackfill() {
  await loadNatFilters()
  await loadNatOverview().catch((e) => console.error('[mining] zg overview failed', e))
  refreshNatSections()
  loadNatIndex().catch((e) => console.error('[mining] zg index failed', e))
  resetNatMoversSpreadFull()
  natMoversSpreadPreviewDone.value = false
  loadNatMoversSpreadPreview(true).catch((e) => console.error('[mining] zg movers/spread failed', e))
}

async function loadNatForecastStatus() {
  const st = await getZgForecastStatus().catch(() => null)
  if (st) natForecastTraining.value = st
  return st
}

async function loadNatHotSkus() {
  natHotSkuLoading.value = true
  try {
    const res = await getZgHotSkus()
    natHotSkuConfigured.value = (res?.configured || []).map((x) => ({ ...x, enabled: x.enabled !== false }))
    natHotSkuRecommended.value = res?.recommended || []
    natHotSkuUsingRecommended.value = !!res?.using_recommended
    natHotSkuEstimate.value = res?.estimate || { sku_count: 0, task_count: 0, estimated_total_seconds: 0, estimated_total_text: '' }
    natAllSkuEstimate.value = res?.all_estimate || { sku_count: 0, task_count: 0, estimated_total_seconds: 0, estimated_total_text: '' }
    rememberSku([...(natHotSkuConfigured.value || []), ...(natHotSkuRecommended.value || [])])
  } finally {
    natHotSkuLoading.value = false
  }
}

function activeNatHotSkus() {
  const source = natHotSkuConfigured.value.length ? natHotSkuConfigured.value : natHotSkuRecommended.value
  return (source || []).filter((x) => x.enabled !== false)
}

async function openNatTrainingCenter() {
  natTrainingCenterVisible.value = true
  natTrainingCenterMinimized.value = false
  await loadNatHotSkus().catch((e) => {
    console.error('[mining] zg hot skus failed', e)
    ElMessage.error('读取热门 SKU 配置失败')
  })
  await loadNatForecastStatus()
  if (natForecastTraining.value?.running) pollNatForecastUntilDone()
}

function minimizeNatTrainingCenter() {
  natTrainingCenterVisible.value = false
  natTrainingCenterMinimized.value = true
  if (natForecastTraining.value?.running) pollNatForecastUntilDone()
}

function onNatTrainingCenterClosed() {
  if (natForecastTraining.value?.running) natTrainingCenterMinimized.value = true
}

async function saveNatHotSkus(items = natHotSkuConfigured.value) {
  natHotSkuSaving.value = true
  try {
    const res = await putZgHotSkus({ items: (items || []).map((x) => ({ sku_key: x.sku_key, label: x.label || natSkuLabels.value[x.sku_key] || x.sku_key, enabled: x.enabled !== false })) })
    natHotSkuConfigured.value = (res?.configured || []).map((x) => ({ ...x, enabled: x.enabled !== false }))
    natHotSkuUsingRecommended.value = false
    natHotSkuEstimate.value = res?.estimate || natHotSkuEstimate.value
    natAllSkuEstimate.value = res?.all_estimate || natAllSkuEstimate.value
    rememberSku(natHotSkuConfigured.value)
    const optMap = new Map(natProductOptions.value.map((o) => [o.value, o]))
    natQuickPickSkus.value.forEach((s) => optMap.set(s.sku_key, { value: s.sku_key, label: s.label || natSkuLabels.value[s.sku_key] || s.sku_key }))
    natProductOptions.value = [...optMap.values()]
    ElMessage.success('热门 SKU 配置已保存')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存热门 SKU 失败')
  } finally {
    natHotSkuSaving.value = false
  }
}

async function saveRecommendedNatHotSkus() {
  const items = (natHotSkuRecommended.value || []).map((x) => ({ ...x, enabled: true }))
  await saveNatHotSkus(items)
}

function addNatHotSku(item) {
  if (!item?.sku_key) return
  if (natHotSkuConfigured.value.some((x) => x.sku_key === item.sku_key)) {
    ElMessage.info('该 SKU 已在热门列表中')
    return
  }
  natHotSkuConfigured.value = [...natHotSkuConfigured.value, { sku_key: item.sku_key, label: item.label || item.sku_key, enabled: true }]
  rememberSku([item])
}

function addPickedNatHotSku() {
  const key = natHotSkuPick.value
  const opt = natProductOptions.value.find((x) => x.value === key)
  if (!key) return
  addNatHotSku({ sku_key: key, label: opt?.label || natSkuLabels.value[key] || key })
  natHotSkuPick.value = ''
}

function removeNatHotSku(index) {
  natHotSkuConfigured.value = natHotSkuConfigured.value.filter((_, i) => i !== index)
}

function moveNatHotSku(index, dir) {
  const next = [...natHotSkuConfigured.value]
  const to = index + dir
  if (to < 0 || to >= next.length) return
  const [item] = next.splice(index, 1)
  next.splice(to, 0, item)
  natHotSkuConfigured.value = next
}

function pollNatForecastUntilDone() {
  clearNatForecastPoll()
  const tick = async () => {
    const st = await loadNatForecastStatus()
    if (st && !st.running) {
      clearNatForecastPoll()
      await loadNatForecast()
      return true
    }
    return false
  }
  tick()
  natForecastPollTimer = setInterval(tick, 900)
}

async function trainNatForecastNow() {
  const key = natProds.value[0] || ''
  try {
    const res = await postZgForecastTrain({ sku_key: key, district_id: natForecastDistrictId.value || '', scope_mode: 'single_current' })
    if (res?.started === false) {
      ElMessage.info(res.message || '已有预测训练任务在运行')
    } else {
      ElMessage.success(res?.message || '已开始后台训练预测')
    }
    pollNatForecastUntilDone()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '启动预测训练失败')
  }
}

async function trainNatHotSkusNow() {
  if (!activeNatHotSkus().length) {
    ElMessage.warning('请先设置至少 1 个启用的热门 SKU')
    return
  }
  try {
    const res = await postZgForecastTrain({ scope_mode: 'popular_batch' })
    if (res?.started === false) {
      ElMessage.info(res.message || '已有预测训练任务在运行')
    } else {
      ElMessage.success(res?.message || '已开始训练预测')
    }
    pollNatForecastUntilDone()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '启动热门 SKU 训练失败')
  }
}

const natRebuilding = ref(false)
let natRebuildTimer = null
async function rebuildNatDerived() {
  // 安全网：全量重建派生表（指数/异动/预测序列）。正常补抓已会自动重建，此处兜底。
  natRebuilding.value = true
  try {
    const res = await postZgRebuild()
    if (res?.started === false) { ElMessage.info(res.message || '已有重建任务在运行'); }
    else ElMessage.success('已开始后台重建派生指标…')
    if (natRebuildTimer) clearInterval(natRebuildTimer)
    natRebuildTimer = setInterval(async () => {
      const st = await getZgRebuildStatus().catch(() => null)
      if (st && st.running === false) {
        clearInterval(natRebuildTimer); natRebuildTimer = null
        natRebuilding.value = false
        await refreshNatAfterBackfill()
        ElMessage.success(st.message || '派生指标已重建，页面已刷新')
      }
    }, 3000)
  } catch (e) {
    natRebuilding.value = false
    ElMessage.error(e?.response?.data?.detail || e?.message || '重建失败')
  }
}

function pollNatBackfillUntilDone() {
  clearNatBackfillPoll()
  const tick = async () => {
    mergeNatBackfillStatus(await getZgBackfillStatus())
    scrollNatBackfillTerminal()
    if (!natBackfillStatus.value.running && natBackfillStatus.value.finished) {
      clearNatBackfillPoll()
      await refreshNatAfterBackfill()
      await loadNatForecastStatus()
      if (natForecastTraining.value?.running) pollNatForecastUntilDone()
      const failed = natBackfillStatus.value.status === 'failed'
      if (failed) {
        ElMessage.error(natBackfillStatus.value.message || '补抓失败，请查看日志')
      } else {
        ElMessage.success('全国农产品价格补抓完成，页面已刷新')
      }
      return true
    }
    return false
  }
  void tick()
  natBackfillPollTimer = setInterval(() => tick(), 650)
}

async function loadNatBackfillPreview() {
  const end_date = natYesterdayYmd()
  natBackfillPreview.value = await getZgBackfillPreview({ end_date })
}

async function openNatCredDialog() {
  natCredVisible.value = true
  natCredTestResult.value = null
  natCredLoading.value = true
  try {
    const res = await getZgCredentials()
    natCredForm.username = res?.username || ''
    natCredForm.password = res?.password || ''
    natCredMeta.value = {
      source: res?.source || '',
      updated_at: res?.updated_at || '',
      hint: res?.hint || '',
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '读取账号配置失败')
  } finally {
    natCredLoading.value = false
  }
}

async function saveNatCredentials() {
  const username = (natCredForm.username || '').trim()
  const password = natCredForm.password || ''
  if (!username) {
    ElMessage.warning('请填写手机号')
    return
  }
  if (!password) {
    ElMessage.warning('请填写密码')
    return
  }
  natCredLoading.value = true
  try {
    const res = await putZgCredentials({ username, password })
    natCredForm.username = res?.username || username
    natCredForm.password = res?.password || password
    natCredMeta.value = {
      source: res?.source || 'database',
      updated_at: res?.updated_at || '',
      hint: '账号已保存',
    }
    natCredTestResult.value = null
    ElMessage.success(res?.message || '已保存')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    natCredLoading.value = false
  }
}

async function testNatCredentials() {
  const username = (natCredForm.username || '').trim()
  const password = natCredForm.password || ''
  if (!username || !password) {
    ElMessage.warning('请先填写手机号与密码')
    return
  }
  natCredTestLoading.value = true
  natCredTestResult.value = null
  try {
    const res = await postZgCredentialsTest({ username, password })
    natCredTestResult.value = res
    if (res?.ok) {
      ElMessage.success(res.message || '登录成功')
    } else if (res?.error_kind === 'auth') {
      ElMessage.error(res.message || '账号或密码错误')
    } else if (res?.error_kind === 'network' || res?.error_kind === 'waf') {
      ElMessage.warning(res.message || '网络或 WAF 异常')
    } else {
      ElMessage.warning(res.message || '登录失败')
    }
  } catch (e) {
    const raw = e?.response?.data?.detail || e?.message || '测试失败'
    const isTimeout = e?.code === 'ECONNABORTED' || /timeout/i.test(String(raw))
    const msg = isTimeout
      ? '测试登录超时：若正在补抓请稍后再试；否则请重启后端服务后重试。'
      : raw
    natCredTestResult.value = { ok: false, message: msg, error_kind: 'other' }
    ElMessage.error(msg)
  } finally {
    natCredTestLoading.value = false
  }
}

async function openNatBackfillDialog() {
  natBackfillVisible.value = true
  clearNatBackfillPoll()
  clearNatForecastPoll()
  resetNatBackfillDisplayIdle()
  try {
    await loadNatBackfillPreview()
    const status = await getZgBackfillStatus()
    if (status?.running) {
      mergeNatBackfillStatus(status)
      scrollNatBackfillTerminal()
      pollNatBackfillUntilDone()
    }
  } catch {
    ElMessage.error('读取补抓状态失败')
  }
}

async function confirmNatBackfill() {
  const preview = natBackfillPreview.value || {}
  if (!(preview.day_count > 0)) {
    ElMessage.info(preview.message || '暂无缺失日期，无需补抓')
    natBackfillStatus.value = {
      ...natBackfillStatus.value,
      finished: true,
      logs: [preview.message || '无需补抓'],
    }
    return
  }
  try {
    await ElMessageBox.confirm(
      `库内最新：${preview.latest_date || '—'}\n待补：${preview.start_date} ~ ${preview.end_date}（${preview.day_count} 天）\n\n仅补缺失省份，已齐全日跳过。是否开始？`,
      '全国农产品价格 · 补抓',
      { type: 'info', confirmButtonText: '开始抓取', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  natBackfillLoading.value = true
  clearNatBackfillPoll()
  try {
    const res = await postZgBackfill({
      start_date: preview.start_date,
      end_date: preview.end_date,
      slow: false,
      forecast_sku_keys: natProds.value || [],
    })
    if (res?.detail) {
      ElMessage.error(typeof res.detail === 'string' ? res.detail : '补抓启动失败')
      return
    }
    mergeNatBackfillStatus(await getZgBackfillStatus())
    scrollNatBackfillTerminal()
    ElMessage.success(res?.message || '已开始补抓')
    pollNatBackfillUntilDone()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '补抓启动失败')
  } finally {
    natBackfillLoading.value = false
  }
}

function applyNatFilters() {
  natDetailPage.value = 1
  loadNatOverview().catch((e) => console.error('[mining] zg overview failed', e))
  resetNatMoversSpreadFull()
  if (natMoversSpreadPreviewDone.value) {
    loadNatMoversSpreadPreview(true).catch((e) => console.error('[mining] zg movers/spread failed', e))
  }
  refreshNatSections()
}

function loadNatFilters() {
  return getZgFilters().then((res) => {
    natDistrictOptions.value = res?.districts || []
    const bj = (res?.districts || []).find((d) => d.name === '北京')
    if (bj) natChangeDistrict.value = bj.id
    natCategoryOptions.value = res?.categories || []
    natSubcategories.value = res?.subcategories || []
    natKpi.days_covered = res?.days_covered || 0
    natKpi.cumulative_rows = res?.cumulative_rows || 0
    natKpi.earliest_date = res?.earliest_date || res?.date_range?.min || ''
    natKpi.latest_date = res?.latest_date || '—'
    const max = res?.date_range?.max
    const min = res?.date_range?.min
    if (max) {
      const startDate = new Date(max)
      startDate.setDate(startDate.getDate() - 29)
      const startYmd = startDate.toISOString().slice(0, 10)
      natDateRange.value = [min && min > startYmd ? min : startYmd, max]
    }
  }).catch((error) => console.error('[mining] zg filters failed', error))
}

async function bootNational() {
  if (nationLoaded.value) return
  // 立即放开布局，各卡片各自转圈
  natDateRange.value = natFallbackDateRange()
  nationLoaded.value = true
  // 短链：先拿到真实最新日（消除"查今天=无数据"竞态），再按真实日期范围出 KPI+热门品种，最后并行出图表/明细
  await loadNatFilters()
  await Promise.all([
    loadNatOverview().catch((e) => console.error('[mining] zg overview failed', e)),
    loadNatHotSkus().catch((e) => console.error('[mining] zg hot skus failed', e)),
  ])
  // 默认 SKU：优先客户配置热门 SKU，否则系统推荐/快照日覆盖最广
  const quickPicks = natQuickPickSkus.value
  if (!natProds.value.length && quickPicks.length) {
    natProds.value = [quickPicks[0].sku_key]
  }
  // 选项 = 快捷添加热门 SKU + 已选（{value,label}）
  const optMap = new Map(natProductOptions.value.map((o) => [o.value, o]))
  quickPicks.forEach((s) => optMap.set(s.sku_key, { value: s.sku_key, label: s.label || natSkuLabels.value[s.sku_key] || s.sku_key }))
  natProds.value.forEach((k) => { if (!optMap.has(k)) optMap.set(k, { value: k, label: natSkuLabels.value[k] || k }) })
  natProductOptions.value = [...optMap.values()]
  refreshNatSections()
  // 全局模块（与品种无关）：指数 / 质量；异动·价差预览滚动到模块后再拉，Top100 仅点「更多」
  loadNatIndex().catch((e) => console.error('[mining] zg index failed', e))
  setupNatMoversSpreadLazy()
  setupNatChangeLazy()
  loadNatQuality().catch((e) => console.error('[mining] zg quality failed', e))
  loadNatForecastStatus().then((st) => { if (st?.running) pollNatForecastUntilDone() }).catch(() => {})
  checkNatGap() // 只提示不强制
}

async function checkNatGap() {
  try {
    const p = await getZgBackfillPreview({ end_date: natYesterdayYmd() })
    natGap.value = { days: p?.day_count || 0, latest: p?.latest_date || '', target: p?.end_date || '', dismissed: false }
  } catch (e) {
    // 静默：缺口提示失败不影响主体
  }
}

watch([onlyTrainable, onlyUsable, overviewSortBy, overviewSortOrder], () => loadOverview(true))
watch(activeTab, (tab) => {
  if (tab === 'forecast' && !overviewRows.value.length) loadOverview(true)
  if (tab === 'trends') {
    if (!trendsLoaded.value) bootTrends()
    else nextTick(() => { renderTrendChart(); renderFocusChart() })
  }
  if (tab === 'national') {
    if (!nationLoaded.value) bootNational()
    else nextTick(() => { renderNatTrend(); renderNatCompare(); renderNatIndex(); renderNatMap(); renderNatForecast() })
  }
})
watch(forecastDays, () => {
  if (detailVisible.value && currentProduct.value) runPredict()
})
watch(focusProduct, (val, old) => {
  if (val && val !== old) loadFocusForecast()
})

onMounted(async () => {
  await bootNational()
})

onBeforeUnmount(() => {
  trendChart?.dispose()
  focusChart?.dispose()
  mainChart?.dispose()
  factorChart?.dispose()
  decompChart?.dispose()
  natTrendChart?.dispose()
  natCompareChart?.dispose()
  clearNatBackfillPoll()
  natMoversSpreadIO?.disconnect()
  natMoversSpreadIO = null
  natChangeIO?.disconnect()
  natChangeIO = null
  disposeNatChangeCharts()
  natIndexChart?.dispose()
  natMapChart?.dispose()
  natFcChart?.dispose()
  natSkuDrawerChart?.dispose()
  trendResizeObserver?.disconnect()
  focusResizeObserver?.disconnect()
  natTrendResizeObserver?.disconnect()
  natCompareResizeObserver?.disconnect()
  natIndexRO?.disconnect()
  natMapRO?.disconnect()
  natFcRO?.disconnect()
  if (productSearchTimer) clearTimeout(productSearchTimer)
  if (natProductSearchTimer) clearTimeout(natProductSearchTimer)
  if (natRebuildTimer) clearInterval(natRebuildTimer)
  if (trainPollTimer) clearInterval(trainPollTimer)
  clearBackfillPoll()
  clearBatchPoll()
  postBackfillDismiss().catch(() => {})
})
</script>

<template>
  <section class="mine-workbench">
    <header class="mine-hero">
      <div class="hero-aura" aria-hidden="true"></div>
      <div class="hero-main">
        <p class="eyebrow"><i class="eyebrow-pulse"></i>MULTI-SOURCE PRICE INTELLIGENCE</p>
        <h1>数据智能挖掘中心</h1>
        <p class="hero-desc">多源农产品价格智能挖掘：新发地批发行情 + 全国中农价格网行情；覆盖多品种趋势、价格预测、区域对比与经营结论。</p>
      </div>
      <div class="hero-metrics">
        <span class="hm-top">{{ heroMetricTop }}</span>
        <strong class="hm-bottom">{{ heroMetricBottom }}</strong>
      </div>
    </header>

    <el-tabs v-model="activeTab" class="mine-tabs">
      <el-tab-pane label="全国农产品价格" name="national">
        <div class="nat-wrap">
          <div class="panel filter-panel">
            <el-form :inline="true" @submit.prevent>
              <el-form-item label="日期范围">
                <el-date-picker v-model="natDateRange" type="daterange" range-separator="至" start-placeholder="开始" end-placeholder="结束" value-format="YYYY-MM-DD" />
              </el-form-item>
              <el-form-item label="省份">
                <el-select v-model="natDistrict" clearable filterable placeholder="全部省份" style="width: 150px">
                  <el-option v-for="d in natDistrictOptions" :key="d.id" :label="d.name" :value="d.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="分类">
                <el-select v-model="natCategory" clearable filterable placeholder="全部分类" style="width: 140px" @change="natScate = ''">
                  <el-option v-for="c in natCategoryOptions" :key="c.id" :label="c.name" :value="c.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="子类">
                <el-select v-model="natScate" clearable filterable placeholder="全部子类" style="width: 140px">
                  <el-option v-for="s in natScateOptions" :key="s.cate_id + '|' + s.name" :label="s.name" :value="s.name" />
                </el-select>
              </el-form-item>
              <el-form-item label="SKU（品名·规格）">
                <el-select v-model="natProds" multiple filterable remote reserve-keyword collapse-tags collapse-tags-tooltip :remote-method="onNatProductRemoteQuery" :loading="natProductSearchLoading" placeholder="搜品名选规格，如 可乐 → 330ml/听" style="min-width: 320px" @visible-change="(v) => v && onNatProductRemoteQuery('')">
                  <el-option v-for="opt in natProductOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="natChartLoading" @click="applyNatFilters">查询分析</el-button>
                <el-button type="primary" plain :loading="natDailyReportLoading" @click="openNatDailyReportDialog">📄 导出 PDF 日报</el-button>
                <el-button plain :loading="natExporting" @click="exportNatExcelData">⬇ 导出 Excel 数据</el-button>
                <el-button plain @click="router.push('/monitor/price-cockpit')">🖥 价格驾驶舱大屏</el-button>
                <el-button type="warning" plain :disabled="natBackfillRunning" @click="openNatBackfillDialog">补抓</el-button>
                <el-button plain :loading="natRebuilding" @click="rebuildNatDerived">重建指标</el-button>
                <el-button plain @click="openNatCredDialog">配置</el-button>
                <el-button type="success" plain @click="openNatTrainingCenter">预测训练中心</el-button>
              </el-form-item>
            </el-form>
            <div class="quick-picks" v-if="natQuickPickSkus.length">
              <span>热门 SKU 快捷添加：</span>
              <button v-for="item in natQuickPickSkus" :key="item.sku_key" type="button" @click="addNatProduct(item)">{{ item.label }}</button>
            </div>
          </div>

          <el-alert
            v-if="natGap.days > 0 && !natGap.dismissed"
            type="warning"
            class="nat-gap-alert"
            :closable="true"
            show-icon
            @close="natGap.dismissed = true"
          >
            <template #title>
              检测到 {{ natGap.days }} 天数据缺口（库内最新 {{ natGap.latest || '—' }}，可补抓至 {{ natGap.target || '—' }}）。请点击补抓；指数/异动/预测会随之自动刷新。
            </template>
            <el-button size="small" type="warning" plain style="margin-top: 6px" @click="openNatBackfillDialog">去补抓</el-button>
          </el-alert>

          <div class="zg-secnav">
            <span class="zg-secnav-label">快速跳转</span>
            <button v-for="s in NAT_SECTIONS" :key="s.id" type="button" @click="scrollToNatSection(s.id)">{{ s.label }}</button>
          </div>

          <div class="kpi-grid nat-kpi" v-loading="natOverviewLoading">
            <div class="kpi-cumulative"><strong>{{ formatNatRowCount(natKpi.cumulative_rows) }}</strong><span>累计入库条数</span></div>
            <div><strong>{{ natKpi.days_covered }}</strong><span>采集天数</span></div>
            <div><strong>{{ natKpi.earliest_date || '—' }}</strong><span>最早采集日</span></div>
            <div><strong>{{ natKpi.latest_date }}</strong><span>最新采集日</span></div>
            <div><strong>{{ natKpi.total_rows.toLocaleString() }}</strong><span>当日记录数</span></div>
            <div><strong>{{ natKpi.distinct_skus.toLocaleString() }}</strong><span>当日 SKU 数</span></div>
            <div><strong>{{ natKpi.distinct_districts }}</strong><span>覆盖省份</span></div>
            <div><strong>{{ natKpi.distinct_categories }}</strong><span>商品分类</span></div>
          </div>
          <p v-if="natKpi.snapshot_date" class="nat-snap-note">
            累计 {{ formatNatRowCount(natKpi.cumulative_rows) }} 条（{{ natKpi.earliest_date || '—' }} ~ {{ natKpi.latest_date }}，{{ natKpi.days_covered }} 天）；
            下方「当日」指标快照日 {{ natKpi.snapshot_date }}（随筛选/日期范围变）· SKU = 品名 + 一级分类 + 二级分类 + 规格 + 单位
          </p>

          <!-- 数据可信度面板 -->
          <div class="panel zg-quality" v-loading="natQualityLoading">
            <div class="zq-score" :class="natQualityGrade.cls">
              <span class="zq-label">数据可信度</span>
              <strong class="zq-num">{{ natQuality.health_score ?? '—' }}</strong>
              <span class="pill" :class="natQualityGrade.cls">{{ natQualityGrade.label }}</span>
            </div>
            <div class="zq-metrics">
              <el-tooltip placement="top" content="最新采集日里 price 字段能成功解析为数值的行占比；越高说明源数据越干净。">
                <div class="zq-cell"><span>价格可解析率 ?</span><strong>{{ natQuality.parse_rate ?? '—' }}%</strong></div>
              </el-tooltip>
              <el-tooltip placement="top" content="同一 SKU 当日各省报价最高/最低 > 5 倍的数量，疑似单位/包装记录错误；点击可查看明细并联动分析。">
                <div
                  class="zq-cell zq-cell-clickable"
                  role="button"
                  tabindex="0"
                  @click="openNatSuspiciousDialog"
                  @keydown.enter="openNatSuspiciousDialog"
                >
                  <span>疑似脏数据 SKU ?</span>
                  <strong>{{ natQuality.suspicious_skus ?? '—' }}</strong><em>/ {{ natQuality.distinct_skus ?? '—' }}</em>
                  <div v-if="(natQuality.quality_trend || []).length" class="zq-spark">
                    <i
                      v-for="d in natQuality.quality_trend"
                      :key="d.date"
                      class="zq-spark-bar"
                      :class="{ risk: (d.high || 0) > 0 }"
                      :style="{ height: Math.max(8, qualityTrendBarHeight(d)) + '%' }"
                    />
                  </div>
                  <span class="zq-cell-hint">点击查看 · 近 30 日趋势</span>
                </div>
              </el-tooltip>
              <el-tooltip placement="top" content="进入价格指数篮子(基期与最新日均有价)的 SKU 占当日全部 SKU 的比例；越高指数代表性越强。">
                <div class="zq-cell"><span>指数篮子覆盖 ?</span><strong>{{ natQuality.basket_coverage ?? '—' }}%</strong><em>{{ natQuality.basket_size ?? '—' }} 个</em></div>
              </el-tooltip>
              <el-tooltip placement="top" content="最新采集日距今天数；0~1 天为新鲜，越大越需补抓。">
                <div class="zq-cell"><span>数据新鲜度 ?</span><strong>{{ natQuality.freshness_gap_days == null ? '—' : (natQuality.freshness_gap_days <= 1 ? '新鲜' : natQuality.freshness_gap_days + ' 天前') }}</strong><em>{{ natQuality.snapshot_date }}</em></div>
              </el-tooltip>
            </div>
          </div>

          <!-- 大综价格指数（Jevons 几何均值价比，单位无关） -->
          <div id="zgsec-index" class="panel zg-index-panel" v-loading="natIndexLoading">
            <div class="zg-index-grid">
              <div class="zg-index-hero">
                <p class="eyebrow">
                  全国农产品价格总指数 · 基期 {{ natIndex.base_date || '—' }} = 100
                  <el-tooltip placement="top" popper-class="fh-tip"
                    content="对全市场约 1.58 万个 SKU 做 Jevons 几何均值价比(单位无关、抗离群)，反映整体价格涨跌，不是某个商品的价格。">
                    <u class="zg-help">?</u>
                  </el-tooltip>
                </p>
                <p class="zg-basket-note">{{ natIndexBasketText }}</p>
                <div class="zg-index-num" :class="(natIndex.overall_change_pct || 0) >= 0 ? 'up' : 'down'">
                  {{ natIndex.overall_latest ?? '—' }}<small class="zg-index-unit">指数</small>
                </div>
                <div class="zg-index-chg" :class="(natIndex.overall_change_pct || 0) >= 0 ? 'up' : 'down'">
                  {{ (natIndex.overall_change_pct || 0) >= 0 ? '▲' : '▼' }} {{ natIndex.overall_change_pct == null ? '—' : Math.abs(natIndex.overall_change_pct) + '%' }}
                  <span>较基期</span>
                </div>
                <p class="zg-index-disclaimer">全市场综合指数 · <b>非单品价格</b>（看具体品价请见下方明细/对比）</p>
                <div class="zg-cat-chips">
                  <button
                    v-for="c in (natIndex.categories || [])"
                    :key="c.cate_id"
                    type="button"
                    class="pill cat-toggle"
                    :class="[(c.change_pct || 0) >= 0 ? 'ok' : 'risk', { active: natIndexSelectedCateIds.includes(c.cate_id) }]"
                    @click="toggleNatIndexCate(c.cate_id)"
                  >
                    {{ c.cate_name }} {{ c.latest }}
                  </button>
                </div>
              </div>
              <div class="zg-index-chart">
                <div ref="natIndexRef" class="index-chart"></div>
              </div>
            </div>
          </div>

          <!-- 热力地图 + AI 预测 并排 -->
          <div class="zg-two-col">
            <div id="zgsec-map" class="panel chart-panel" v-loading="natMapLoading">
              <div class="panel-head">
                <strong>全国价格热力地图</strong>
                <span class="panel-head-meta">
                  <el-select
                    v-if="natAnalysisSkuOptions.length"
                    v-model="natPrimarySku"
                    filterable
                    size="small"
                    class="nat-primary-sku-select"
                    placeholder="选择已分析 SKU"
                  >
                    <el-option v-for="opt in natAnalysisSkuOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                  </el-select>
                  <em v-else class="panel-head-suffix">请先在上方选择 SKU</em>
                  <span v-if="natAnalysisSkuOptions.length" class="panel-head-suffix">· 各省中位价</span>
                  <button class="dl-btn" @click="downloadNatChart(natMapChart, '热力地图')">⬇图片</button>
                </span>
              </div>
              <div class="chart-stack map-province-layout">
                <div ref="natMapRef" class="map-chart"></div>
                <div class="province-picker">
                  <div class="province-picker__head">
                    <strong>有数据省份</strong>
                    <button type="button" :class="{ active: !natForecastDistrictId }" @click="clearNatForecastProvince">全国</button>
                  </div>
                  <button
                    v-for="p in natMapProvinceOptions"
                    :key="p.name"
                    type="button"
                    :class="{ active: natForecastDistrictName === p.name }"
                    @click="selectNatForecastProvince(p.name)"
                  >
                    <span>{{ p.name }}</span><em>{{ p.value }}</em>
                  </button>
                </div>
                <div v-if="!natMapLoading && !(natMapData.provinces || []).length" class="nat-empty">该品种暂无分省数据</div>
              </div>
            </div>
            <div class="panel chart-panel" v-loading="natFcLoading">
              <div class="panel-head">
                <div class="panel-head-title-stack">
                  <strong>AI 价格预测 · {{ natForecastScopeLabel }}</strong>
                  <span v-if="natAnalysisSkuOptions.length" class="panel-head-meta panel-head-meta--inline">
                    <label>分析 SKU</label>
                    <el-select v-model="natPrimarySku" filterable size="small" class="nat-primary-sku-select">
                      <el-option v-for="opt in natAnalysisSkuOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                    </el-select>
                  </span>
                </div>
                <div class="forecast-head-actions">
                  <el-radio-group v-if="natForecastHasRaw" v-model="natForecastRawMode" size="small" class="fc-mode-toggle">
                    <el-radio-button :value="false">清洗后</el-radio-button>
                    <el-radio-button :value="true">原始报价</el-radio-button>
                  </el-radio-group>
                  <button class="dl-btn" @click="downloadNatChart(natFcChart, 'AI预测')">⬇图片</button>
                  <el-popover placement="bottom-end" width="360" trigger="click">
                    <template #reference><button type="button" class="text-link">预测说明</button></template>
                    <div class="forecast-explain">
                      <p>系统会先用历史数据模拟过去的预测，比较 XGBoost、锚定均值回归、移动均值基线谁更准，再选择当前最可靠的冠军模型。</p>
                      <p>绿灯表示历史回测表现较好；黄灯表示可参考但需结合行情；红灯表示样本少或误差大。</p>
                      <p>回测误差 3% 表示用同样方法预测过去一段时间时，平均偏差约为 3%。预测不是保证价格，而是参考区间。</p>
                    </div>
                  </el-popover>
                  <span class="pill" :class="fcStats.grade">{{ fcStats.label }}</span>
                </div>
              </div>
              <div class="forecast-status-row">
                <div class="forecast-progress-main">
                  <div class="forecast-progress-head">
                    <span>{{ natForecastStatusText }}</span>
                    <em v-if="natForecastProgressMeta">{{ natForecastProgressMeta }}</em>
                  </div>
                  <el-progress
                    v-if="natForecastShowProgress"
                    :percentage="natForecastProgressPct"
                    :status="natForecastProgressStatus"
                    :indeterminate="!!natForecastTraining.running"
                    :striped="!!natForecastTraining.running"
                    :striped-flow="!!natForecastTraining.running"
                    :stroke-width="8"
                  />
                  <div class="forecast-pipeline">
                    <span class="forecast-pipeline__title">
                      {{ natForecastTraining.phase_label || '训练流水线' }}
                      <el-popover v-if="fcStats.qualityHint" placement="bottom-start" width="360" trigger="click">
                        <template #reference><button type="button" class="forecast-hint-link">详情</button></template>
                        <p class="forecast-hint-pop">{{ fcStats.qualityHint }}</p>
                      </el-popover>
                    </span>
                    <ul>
                      <li v-for="line in natForecastPipelineLines" :key="line">
                        {{ line }}
                        <el-tooltip v-if="line.includes('未过质量规则')" placement="top" popper-class="fh-tip"
                          content="「原始报价」是源站对该 SKU 报过价的总天数；「历史样本」是过完质量规则（剔除跨省价异常/高风险，必要时校正）后真正可用于训练的天数。两者之差即被质量规则剔除的可疑数据。">
                          <u class="zg-help">?</u>
                        </el-tooltip>
                      </li>
                    </ul>
                  </div>
                </div>
                <button type="button" :disabled="!!natForecastTraining.running" @click="trainNatForecastNow">
                  {{ natForecastTraining.running ? '训练中' : '更新当前预测' }}
                </button>
              </div>
              <div class="chart-stack">
                <p v-if="natForecastRawMode" class="fc-raw-note">
                  原始报价视图：原始 {{ (natForecast.raw_history || []).length }} 天 · 清洗后 {{ (natForecast.history || []).length }} 天 ·
                  <span class="fc-raw-dot">红点</span>为被质量规则剔除的天（原始视图不外推预测）
                </p>
                <div ref="natFcRef" class="nat-forecast-chart"></div>
                <div
                  v-if="!natFcLoading && fcStats.status && fcStats.status !== 'ok' && fcStats.status !== 'loading' && !fcStats.qualityHint"
                  class="nat-empty"
                >
                  {{ natForecast.message || '暂不可预测' }}
                </div>
              </div>
              <div class="fc-tiles" v-if="fcStats.status === 'ok'">
                <div><span>当前实价</span><strong>{{ fcStats.anchor ?? '—' }}</strong></div>
                <div><span>明日预测</span><strong>{{ fcStats.next ?? '—' }}</strong></div>
                <div><span>7 日预测</span><strong>{{ fcStats.day7 ?? '—' }}</strong></div>
                <div><span>回测误差</span><strong>{{ fcStats.mape != null ? fcStats.mape + '%' : '—' }}</strong></div>
                <div><span>冠军模型</span><strong>{{ fcStats.winner }}</strong></div>
                <div><span>样本天数</span><strong>{{ fcStats.sampleCount }}</strong></div>
                <div><span>数据日期</span><strong>{{ fcStats.dataDate }}</strong></div>
                <div><span>训练时间</span><strong>{{ fcStats.trainedAt }}</strong></div>
              </div>
            </div>
          </div>

          <!-- 涨跌幅排名 -->
          <div id="zgsec-change-rank" class="panel zg-change-rank-panel" v-loading="natChangeLoading">
            <div class="panel-head zg-change-rank-head">
              <div class="zg-change-rank-title-row">
                <strong>涨跌幅排名</strong>
                <span class="panel-head-meta nat-change-rank-filters">
                  <el-select
                    v-model="natChangeDistrict"
                    clearable
                    filterable
                    placeholder="全国"
                    size="small"
                    class="nat-change-province-select"
                    @change="onNatChangeFilterChange"
                  >
                    <el-option v-for="d in natDistrictOptions" :key="'ch-' + d.id" :label="d.name" :value="d.id" />
                  </el-select>
                  <el-select
                    v-model="natChangeCategory"
                    clearable
                    filterable
                    placeholder="全部分类"
                    size="small"
                    class="nat-change-cate-select"
                    @change="onNatChangeCategoryChange"
                  >
                    <el-option v-for="c in natCategoryOptions" :key="'chc-' + c.id" :label="c.name" :value="c.id" />
                  </el-select>
                  <el-select
                    v-model="natChangeScate"
                    clearable
                    filterable
                    placeholder="全部子类"
                    size="small"
                    class="nat-change-scate-select"
                    :disabled="!natChangeCategory"
                    @change="onNatChangeFilterChange"
                  >
                    <el-option v-for="s in natChangeScateOptions" :key="'chs-' + s.cate_id + '|' + s.name" :label="s.name" :value="s.name" />
                  </el-select>
                  <el-select
                    v-model="natChangeBaselineDays"
                    size="small"
                    class="nat-change-baseline-select"
                    @change="onNatChangeBaselineChange"
                  >
                    <el-option v-for="d in NAT_CHANGE_BASELINE_OPTIONS" :key="'chb-' + d" :label="`前 ${d} 日`" :value="d" />
                  </el-select>
                </span>
              </div>
              <span class="zg-change-rank-meta">{{ natChangeCompareHint }}</span>
            </div>
            <p v-if="!natChangePreviewDone && !natChangeLoading" class="nat-snap-note">滚动到此处时加载涨跌幅排名</p>
            <p v-else-if="natChangeRankEmptyAll" class="nat-snap-note zg-rank-empty-hint">
              在「{{ natChangeFilterSummary }}」下暂无涨跌幅排名：需同时有统计日价与前 N 日均价，且涨跌幅在合理区间内。
              可尝试切换省份/分类，或改为「前 5 日」「前 7 日」。
            </p>
            <div v-show="natChangePreviewDone || natChangeLoading" class="zg-rank-grid">
                <div class="zg-rank-col">
                  <div class="zg-rank-h up">涨幅排名</div>
                  <div class="zg-rank-chart-wrap">
                    <div ref="natChangeRankGainRef" class="zg-rank-chart" />
                    <div
                      v-if="natChangeRankReady && !(natChangeRank.gainers || []).length && !natChangeRankEmptyAll"
                      class="nat-empty zg-rank-empty"
                    >
                      <span>暂无涨幅数据</span>
                      <span class="zg-rank-empty-sub">{{ natChangeFilterSummary }}</span>
                    </div>
                  </div>
                </div>
                <div class="zg-rank-col">
                  <div class="zg-rank-h down">跌幅排名</div>
                  <div class="zg-rank-chart-wrap">
                    <div ref="natChangeRankLossRef" class="zg-rank-chart" />
                    <div
                      v-if="natChangeRankReady && !(natChangeRank.losers || []).length && !natChangeRankEmptyAll"
                      class="nat-empty zg-rank-empty"
                    >
                      <span>暂无跌幅数据</span>
                      <span class="zg-rank-empty-sub">{{ natChangeFilterSummary }}</span>
                    </div>
                  </div>
                </div>
            </div>
          </div>

          <!-- 异动雷达 + 区域价差 并排 -->
          <div class="zg-two-col">
            <div id="zgsec-movers" class="panel" v-loading="natMoversLoading">
              <div class="panel-head">
                <strong>价格异动雷达 · 近 {{ natMovers.window || natMoversWindow }} 日</strong>
                <el-tooltip placement="top" popper-class="fh-tip"
                  content="「全国价」是当天各地区上报价的中位数自动聚合而成（非单一官方来源）。涨跌幅 =（最新采集日中位价 − N 日前中位价）/ N 日前中位价；已剔除省份覆盖不足(<6 省)与 |涨跌|>150% 的异常，并按「严格清洗」排除高风险 SKU。指定省份时改用该省各市场报价中位数。">
                  <u class="zg-help">?</u>
                </el-tooltip>
                <span class="panel-head-meta nat-movers-head-meta">
                  <el-select
                    v-model="natMoversWindow"
                    size="small"
                    class="nat-movers-window-select"
                    @change="onNatMoversFilterChange"
                  >
                    <el-option v-for="w in NAT_MOVERS_WINDOW_OPTIONS" :key="'mw-' + w" :label="`近 ${w} 日`" :value="w" />
                  </el-select>
                  <el-select
                    v-model="natMoversCategory"
                    clearable
                    filterable
                    placeholder="全部分类"
                    size="small"
                    class="nat-movers-cate-select"
                    @change="onNatMoversCategoryChange"
                  >
                    <el-option v-for="c in natCategoryOptions" :key="'mvc-' + c.id" :label="c.name" :value="c.id" />
                  </el-select>
                  <el-select
                    v-model="natMoversScate"
                    clearable
                    filterable
                    placeholder="全部子类"
                    size="small"
                    class="nat-movers-scate-select"
                    :disabled="!natMoversCategory"
                    @change="onNatMoversFilterChange"
                  >
                    <el-option v-for="s in natMoversScateOptions" :key="'mvs-' + s.cate_id + '|' + s.name" :label="s.name" :value="s.name" />
                  </el-select>
                  <el-select
                    v-model="natMoversDistrict"
                    clearable
                    filterable
                    placeholder="全国"
                    size="small"
                    class="nat-movers-province-select"
                    @change="onNatMoversFilterChange"
                  >
                    <el-option v-for="d in natDistrictOptions" :key="'mv-' + d.id" :label="d.name" :value="d.id" />
                  </el-select>
                  <el-select
                    v-model="natQualityPolicy"
                    size="small"
                    class="nat-movers-window-select"
                    @change="() => loadNatMoversSpreadPreview(true)"
                  >
                    <el-option label="严格清洗" value="strict" />
                    <el-option label="风险标记" value="warn" />
                    <el-option label="全部数据" value="all" />
                  </el-select>
                  <span>{{ natMoversFilterDesc }} · {{ natMovers.latest_date }}</span>
                  <el-button type="primary" link size="small" @click="openNatMoversMore">更多</el-button>
                </span>
              </div>
              <p v-if="!natMoversSpreadPreviewDone && !natMoversLoading && !natSpreadLoading" class="nat-snap-note">
                榜单数据将在滚动到此处时加载；完整 Top100 请点击「更多」
              </p>
              <p v-else class="nat-quality-filter-note">
                已过滤 {{ natMoverQualitySummary.excluded_count || 0 }} 个高风险 SKU
                <span v-if="natMoverQualitySummary.flagged_included_count"> · 结果含 {{ natMoverQualitySummary.flagged_included_count }} 个风险标记</span>
              </p>
              <div class="movers-cols">
                <div>
                  <div class="movers-h up">▲ {{ natMovers.window || natMoversWindow }} 日涨幅榜</div>
                  <template v-if="(natMovers.gainers || []).length">
                    <div v-for="r in natMovers.gainers.slice(0,6)" :key="'g'+(r.sku_key||r.goods_name)" class="mover-row clickable" title="点击联动地图、预测和走势" @click="drillNatMover(r)">
                      <span class="mover-name">{{ r.goods_name }}</span>
                      <span class="mover-pct up">+{{ r.pct }}%</span>
                    </div>
                  </template>
                  <p v-else-if="natMoversSpreadPreviewDone && !natMoversLoading" class="nat-snap-note movers-empty">暂无涨幅数据，可放宽筛选条件</p>
                </div>
                <div>
                  <div class="movers-h down">▼ {{ natMovers.window || natMoversWindow }} 日跌幅榜</div>
                  <template v-if="(natMovers.losers || []).length">
                    <div v-for="r in natMovers.losers.slice(0,6)" :key="'l'+(r.sku_key||r.goods_name)" class="mover-row clickable" title="点击联动地图、预测和走势" @click="drillNatMover(r)">
                      <span class="mover-name">{{ r.goods_name }}</span>
                      <span class="mover-pct down">{{ r.pct }}%</span>
                    </div>
                  </template>
                  <p v-else-if="natMoversSpreadPreviewDone && !natMoversLoading" class="nat-snap-note movers-empty">暂无跌幅数据，可放宽筛选条件</p>
                </div>
              </div>
            </div>
            <div id="zgsec-spread" class="panel" v-loading="natSpreadLoading">
              <div class="panel-head">
                <strong>区域价差套利榜</strong>
                <span class="panel-head-meta">
                  <span>跨省中位价差{{ natSpreadDate ? `（${natSpreadDate}）` : '' }}</span>
                  <el-button type="primary" link size="small" @click="openNatSpreadMore">更多</el-button>
                </span>
              </div>
              <p class="nat-quality-filter-note">
                已过滤 {{ natSpreadQualitySummary.excluded_count || 0 }} 个异常候选 · 净价差按运输成本 8% 估算
              </p>
              <el-table
                v-if="natSpread.length"
                :data="natSpread.slice(0,6)"
                stripe
                size="small"
                class="spread-table-clickable"
                highlight-current-row
                @row-click="onNatSpreadRow"
              >
                <el-table-column prop="goods_name" label="品种" min-width="120" show-overflow-tooltip />
                <el-table-column prop="cate_name" label="分类" width="84" />
                <el-table-column label="价差" width="92"><template #default="{ row }"><span class="pill warn">{{ row.spread_pct }}%</span></template></el-table-column>
                <el-table-column label="净价差" width="80"><template #default="{ row }">{{ row.net_spread_pct }}%</template></el-table-column>
                <el-table-column label="低→高" min-width="110"><template #default="{ row }">{{ row.cheapest }}→{{ row.priciest }}</template></el-table-column>
              </el-table>
              <p v-else-if="natMoversSpreadPreviewDone && !natSpreadLoading" class="nat-snap-note">暂无跨省价差数据（需至少 6 省有报价且价差在合理区间）</p>
            </div>
          </div>

          <!-- AI 行情日报 -->
          <div class="panel zg-briefing" v-loading="natBriefingLoading">
            <div class="panel-head">
              <strong>🧠 AI 行情日报</strong>
              <span v-if="natBriefingSource" class="briefing-src-tag">{{ natBriefingSource === 'llm' ? 'AI 润色' : '规则引擎' }}</span>
              <el-button type="primary" size="small" :loading="natBriefingLoading" @click="genNatBriefing">生成今日洞察</el-button>
            </div>
            <div v-if="natBriefingReport" class="briefing-report">
              <p class="briefing-headline">{{ natBriefingReport.headline }}</p>
              <p v-if="natBriefingReport.outlook" class="briefing-outlook">{{ natBriefingReport.outlook }}</p>
              <div
                v-for="(sec, si) in (natBriefingReport.sections || [])"
                :key="si"
                class="briefing-sec"
              >
                <h4 class="briefing-sec-title">{{ sec.title }}</h4>
                <p v-if="sec.content" class="briefing-sec-body">{{ sec.content }}</p>
                <ul v-if="sec.items && sec.items.length" class="briefing-sec-list">
                  <li v-for="(it, ii) in sec.items" :key="ii">{{ it.line || it }}</li>
                </ul>
              </div>
            </div>
            <p v-else-if="natBriefing && !natBriefingReport" class="briefing-text">{{ natBriefing }}</p>
            <p v-else class="nat-snap-note">点击「生成今日洞察」：经数据清洗与聚合后，输出市场环境、板块异动、分类涨跌展望与分省要点（口径：统计日价相对前 3 日均价）。</p>
          </div>

          <div id="zgsec-trend" class="panel chart-panel" v-loading="natChartLoading">
            <div class="panel-head">
              <strong>品种价格走势</strong>
              <span class="ph-right">多 SKU 叠加对比<button class="dl-btn" @click="downloadNatChart(natTrendChart, '价格走势')">⬇图片</button></span>
            </div>
            <div v-if="natSkuPrices.length" class="sku-price-strip">
              <button
                v-for="p in natSkuPrices"
                :key="p.sku_key"
                type="button"
                class="sku-price-card"
                :class="{ active: p.sku_key === natProds[0] }"
                @click="setPrimaryNatSku(p.sku_key)"
              >
                <span class="spc-name">{{ p.name }}</span>
                <span class="spc-price">{{ p.last == null ? '—' : '¥' + p.last }}</span>
                <span v-if="p.chg != null" class="spc-chg" :class="p.chg >= 0 ? 'up' : 'down'">{{ p.chg >= 0 ? '+' : '' }}{{ p.chg.toFixed(1) }}%</span>
              </button>
            </div>
            <div class="chart-stack">
              <div ref="natTrendRef" class="trend-chart"></div>
              <div v-if="natTrendEmpty" class="nat-empty">所选品种在该区间暂无报价数据，换个品种或日期试试</div>
            </div>
          </div>

          <div class="panel chart-panel" v-loading="natCompareLoading">
            <div class="panel-head">
              <strong>各省份价格对比</strong>
              <span class="panel-head-meta">
                <el-select
                  v-if="natAnalysisSkuOptions.length"
                  v-model="natPrimarySku"
                  filterable
                  size="small"
                  class="nat-primary-sku-select"
                  placeholder="选择已分析 SKU"
                >
                  <el-option v-for="opt in natAnalysisSkuOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
                <span v-if="natCompareData.date" class="panel-head-suffix">· {{ natCompareData.date }} 各省最新中位价</span>
              </span>
            </div>
            <div class="chart-stack">
              <div ref="natCompareRef" class="compare-chart"></div>
              <div v-if="natCompareEmpty" class="nat-empty">该品种暂无分省份报价</div>
            </div>
          </div>

          <div id="zgsec-detail" class="panel" v-loading="natDetailLoading">
            <div class="table-head">
              <strong>行情明细</strong>
              <span class="panel-head-meta">
                <button v-if="natProds.length" class="dl-btn" @click="openNatSkuDrawer(natProds[0], natProds0Label)">🔍 SKU 深度详情</button>
                <template v-if="natAnalysisSkuOptions.length">
                  <el-select v-model="natPrimarySku" filterable size="small" class="nat-primary-sku-select" placeholder="选择已分析 SKU">
                    <el-option v-for="opt in natAnalysisSkuOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                  </el-select>
                  <span class="panel-head-suffix">· 各省/各日同口径</span>
                </template>
                <template v-else>数据来源：中国农产品价格信息网（zgncpjgw.com）</template>
              </span>
            </div>
            <el-table :data="natDetailRows" stripe max-height="520" size="small">
              <el-table-column prop="crawl_date" label="采集日" width="108" />
              <el-table-column prop="district_name" label="省份" width="92" />
              <el-table-column prop="cate_name" label="分类" width="92" />
              <el-table-column prop="scate_name" label="子类" width="100" show-overflow-tooltip />
              <el-table-column prop="goods_name" label="品名" min-width="120" show-overflow-tooltip />
              <el-table-column prop="spec" label="规格" min-width="110" show-overflow-tooltip />
              <el-table-column prop="price" label="价格" width="100" />
              <el-table-column prop="unit" label="单位" width="76" />
              <el-table-column prop="place" label="产地" min-width="110" show-overflow-tooltip />
              <el-table-column prop="update_date" label="更新日" width="108" />
            </el-table>
            <div class="pager-row">
              <span>共 {{ natDetailTotal.toLocaleString() }} 条</span>
              <el-pagination background layout="total, prev, pager, next" :total="natDetailTotal" :current-page="natDetailPage" :page-size="natDetailPageSize" @current-change="(p) => { natDetailPage = p; loadNatDetail() }" />
            </div>
          </div>

          <!-- SKU 深度抽屉 -->
          <el-drawer v-model="natSkuDrawerOpen" direction="rtl" size="46%" :with-header="false" class="sku-drawer" @closed="onNatSkuDrawerClosed">
            <div class="skud-shell" v-loading="natSkuDrawerLoading">
              <div class="skud-head">
                <div>
                  <p class="eyebrow">SKU 深度详情</p>
                  <h2>{{ natSkuDrawerLabel || '—' }}</h2>
                </div>
                <button class="dl-btn" @click="natSkuDrawerOpen = false">关闭</button>
              </div>

              <div class="skud-block">
                <p class="skud-title">价格统计（区间内日中位价序列）</p>
                <div class="skud-stats" v-if="natSkuDrawerStats">
                  <div><span>最低</span><strong>¥{{ natSkuDrawerStats.min }}</strong></div>
                  <div><span>P10</span><strong>¥{{ natSkuDrawerStats.p10 }}</strong></div>
                  <div><span>中位</span><strong>¥{{ natSkuDrawerStats.median }}</strong></div>
                  <div><span>均值</span><strong>¥{{ natSkuDrawerStats.mean }}</strong></div>
                  <div><span>P90</span><strong>¥{{ natSkuDrawerStats.p90 }}</strong></div>
                  <div><span>最高</span><strong>¥{{ natSkuDrawerStats.max }}</strong></div>
                </div>
                <p v-else class="nat-snap-note">暂无足够数据</p>
              </div>

              <div class="skud-block">
                <p class="skud-title">价格走势</p>
                <div ref="natSkuDrawerChartRef" class="skud-chart"></div>
              </div>

              <div class="skud-block" v-if="natSkuDrawerForecast.status === 'ok'">
                <p class="skud-title">AI 预测 · <span class="pill" :class="natSkuDrawerForecast.reliability">{{ natSkuDrawerForecast.reliability_label }}</span></p>
                <div class="skud-fc">
                  <div><span>当前实价</span><strong>¥{{ natSkuDrawerForecast.anchor_price }}</strong></div>
                  <div><span>明日预测</span><strong>¥{{ (natSkuDrawerForecast.ensemble || [])[0]?.yhat ?? '—' }}</strong></div>
                  <div><span>回测误差</span><strong>{{ natSkuDrawerForecast.accuracy?.mape != null ? natSkuDrawerForecast.accuracy.mape + '%' : '—' }}</strong></div>
                </div>
              </div>

              <div class="skud-block">
                <p class="skud-title">各省最新中位价</p>
                <div class="skud-prov">
                  <div v-for="p in natSkuDrawerProvinces" :key="p.name" class="skud-prov-row">
                    <span>{{ p.name }}</span><strong>¥{{ p.value }}</strong>
                  </div>
                  <p v-if="!natSkuDrawerProvinces.length" class="nat-snap-note">暂无分省数据</p>
                </div>
              </div>

              <div class="skud-block">
                <p class="skud-title">最近报价明细</p>
                <el-table :data="natSkuDrawerRows" stripe size="small" max-height="260">
                  <el-table-column prop="crawl_date" label="采集日" width="104" />
                  <el-table-column prop="district_name" label="省份" width="80" />
                  <el-table-column prop="price" label="价格" width="80" />
                  <el-table-column prop="unit" label="单位" width="64" />
                  <el-table-column prop="place" label="产地" min-width="100" show-overflow-tooltip />
                </el-table>
              </div>
            </div>
          </el-drawer>
        </div>
      </el-tab-pane>

      <el-tab-pane label="行情趋势" name="trends">
        <el-skeleton v-if="bootLoading" :rows="8" animated />
        <template v-else>
          <div class="sentiment-card">
            <span>整体价格景气度</span>
            <strong :class="sentDirClass">
              {{ sentiment.direction === 'up' ? '↑' : sentiment.direction === 'down' ? '↓' : '→' }}
              {{ sentiment.change_pct == null ? '—' : `${Math.abs(sentiment.change_pct).toFixed(2)}%` }}
            </strong>
            <p>{{ sentiment.message || '暂无景气度数据' }}</p>
          </div>

          <div class="panel forecast-hero" v-loading="focusLoading">
            <div class="fh-head">
              <div>
                <p class="eyebrow">AI PRICE FORECAST · 锚定实价 · 实时计算</p>
                <h3>智能价格预测 · {{ focusStats.product || '—' }}</h3>
              </div>
              <div class="fh-focus">
                <span>聚焦品种（支持搜索任意品名）</span>
                <el-select
                  v-model="focusProduct"
                  filterable
                  remote
                  reserve-keyword
                  :remote-method="onProductRemoteQuery"
                  :loading="productSearchLoading"
                  placeholder="输入品名联想搜索，如 土豆 / 西红柿"
                  class="fh-select"
                  @visible-change="onProductDropdownVisible"
                >
                  <el-option v-for="name in productOptions" :key="name" :label="name" :value="name" />
                </el-select>
                <div class="fh-chips">
                  <button v-for="p in QUICK_PRESETS" :key="p" type="button" :class="{ active: focusProduct === p }" @click="focusProduct = p">{{ p }}</button>
                </div>
              </div>
            </div>
            <div class="fh-body">
              <div class="fh-chart"><div ref="focusChartRef" class="focus-chart"></div></div>
              <div class="fh-side">
                <el-tooltip placement="left" :content="tipLight" popper-class="fh-tip">
                  <div class="fh-light tip-card" :class="focusStats.light"><i></i><b>{{ focusLightText }}</b><u>?</u></div>
                </el-tooltip>
                <div class="fh-tiles">
                  <el-tooltip placement="top" :content="tipCurrent" popper-class="fh-tip">
                    <div class="tip-card"><span>当前实价 <u>?</u></span><strong>{{ money(focusStats.current) }}</strong></div>
                  </el-tooltip>
                  <el-tooltip placement="top" :content="tipNext" popper-class="fh-tip">
                    <div class="tip-card">
                      <span>明日预测 <u>?</u></span>
                      <strong :class="focusStats.changePct > 0 ? 'up' : focusStats.changePct < 0 ? 'down' : ''">{{ money(focusStats.next) }}</strong>
                      <em v-if="focusStats.changePct != null" :class="focusStats.changePct > 0 ? 'up' : focusStats.changePct < 0 ? 'down' : ''">{{ focusStats.changePct >= 0 ? '+' : '' }}{{ focusStats.changePct.toFixed(1) }}%</em>
                    </div>
                  </el-tooltip>
                  <el-tooltip placement="bottom" :content="tip7" popper-class="fh-tip">
                    <div class="tip-card"><span>7 日预测 <u>?</u></span><strong>{{ money(focusStats.day7) }}</strong></div>
                  </el-tooltip>
                  <el-tooltip placement="bottom" :content="tipBacktest" popper-class="fh-tip">
                    <div class="tip-card"><span>回测误差 <u>?</u></span><strong>{{ focusStats.mape != null ? focusStats.mape + '%' : '—' }}</strong><em v-if="focusStats.hit != null">方向命中 {{ focusStats.hit }}%</em></div>
                  </el-tooltip>
                </div>
              </div>
            </div>
            <p class="fh-ai">🧠 {{ aiConclusion }}</p>
          </div>

          <div class="panel filter-panel">
            <el-form :inline="true" @submit.prevent>
              <el-form-item label="日期范围">
                <el-date-picker v-model="dateRange" type="daterange" range-separator="至" start-placeholder="开始" end-placeholder="结束" value-format="YYYY-MM-DD" :disabled-date="disabledDate" />
              </el-form-item>
              <el-form-item label="品名">
                <el-select v-model="selectedProds" multiple filterable remote reserve-keyword collapse-tags collapse-tags-tooltip :remote-method="onProductRemoteQuery" :loading="productSearchLoading" placeholder="输入关键字搜索" style="min-width: 320px" @visible-change="onProductDropdownVisible">
                  <el-option v-for="name in productOptions" :key="name" :label="name" :value="name" />
                </el-select>
              </el-form-item>
              <el-form-item label="一级分类">
                <el-input v-model="cat1" clearable placeholder="留空不限" style="width: 140px" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="chartLoading" @click="loadTrends">刷新图表</el-button>
                <el-button plain @click="openBackfillDialog">补全缺失数据</el-button>
              </el-form-item>
            </el-form>
            <div class="quick-picks">
              <span>常用品类快捷添加：</span>
              <button v-for="item in QUICK_PRESETS" :key="item" type="button" @click="addQuickProduct(item)">{{ item }}</button>
            </div>
          </div>

          <div class="kpi-grid">
            <div><strong>{{ kpi.calendarDays }}</strong><span>统计天数</span></div>
            <div><strong>{{ kpi.daysWithPoint }}</strong><span>有报价点数</span></div>
            <div><strong>{{ kpi.prodCount }}</strong><span>品种数</span></div>
            <div><strong>{{ kpi.lastDayAvgText }}</strong><span>区间末日均</span></div>
          </div>

          <div class="panel chart-panel">
            <div class="panel-head"><strong>批发均价走势</strong><span>无数据日为断点，支持缩放查看</span></div>
            <div ref="chartRef" class="trend-chart"></div>
          </div>

          <el-collapse v-model="detailOpen" class="detail-collapse">
            <el-collapse-item title="历史数据明细（运营 / 分析用，默认折叠）" name="detail">
              <el-table :data="detailRows" stripe max-height="360" size="small">
                <el-table-column prop="发布日期" label="日期" width="112" />
                <el-table-column prop="品名" label="品名" min-width="110" show-overflow-tooltip />
                <el-table-column prop="一级分类" label="一级分类" width="100" />
                <el-table-column prop="平均价" label="平均价" width="90" />
                <el-table-column prop="最低价" label="最低价" width="90" />
                <el-table-column prop="最高价" label="最高价" width="90" />
                <el-table-column prop="产地" label="产地" min-width="110" show-overflow-tooltip />
                <el-table-column prop="单位" label="单位" width="80" />
              </el-table>
            </el-collapse-item>
          </el-collapse>
        </template>
      </el-tab-pane>

      <el-tab-pane label="价格预测" name="forecast">
        <div class="panel overview-panel">
          <div class="table-head">
            <strong>预测总览工作台</strong>
            <div class="overview-actions">
              <el-input v-model="overviewQuery" clearable placeholder="搜索品名" style="width: 180px" @keyup.enter="loadOverview(true)" @clear="loadOverview(true)" />
              <el-button @click="loadOverview(true)">查询</el-button>
              <el-select v-model="overviewSortBy" style="width: 128px">
                <el-option label="按更新时间" value="updated_at" />
                <el-option label="按新鲜度" value="freshness" />
                <el-option label="按置信度" value="confidence" />
                <el-option label="按预测价" value="price" />
                <el-option label="按样本数" value="sample_days" />
              </el-select>
              <el-select v-model="overviewSortOrder" style="width: 92px">
                <el-option label="降序" value="desc" />
                <el-option label="升序" value="asc" />
              </el-select>
              <span class="switch-line">可训练 <el-switch v-model="onlyTrainable" /></span>
              <span class="switch-line">绿/黄 <el-switch v-model="onlyUsable" /></span>
              <el-button :loading="forecastLoading" @click="loadOverview(false)">刷新</el-button>
              <el-button type="warning" plain :disabled="!trainableTotal" :loading="batchStatus.running" @click="runBatchRetrain">批量重训（{{ overviewQuery ? '筛选 ' : '全部 ' }}{{ trainableTotal }}）</el-button>
              <el-button type="primary" plain @click="runOneClickSync">一键同步（补抓+重训）</el-button>
            </div>
          </div>
          <el-table :data="overviewRows" stripe size="small" max-height="470" @selection-change="onOverviewSelectionChange">
            <el-table-column type="selection" width="42" :selectable="canSelectForBatch" />
            <el-table-column prop="product" label="品名" min-width="120" />
            <el-table-column label="操作" width="142">
              <template #default="{ row }">
                <el-button size="small" @click="openForecastDetail(row)">详情</el-button>
                <el-button size="small" type="warning" plain :disabled="!row.can_train" @click="runRetrain(row.product)">重训</el-button>
              </template>
            </el-table-column>
            <el-table-column label="训练资格" width="100">
              <template #default="{ row }"><span class="pill" :class="row.can_train ? 'ok' : 'risk'">{{ row.can_train ? '可训练' : '数据不足' }}</span></template>
            </el-table-column>
            <el-table-column prop="sample_days" label="近365天样本" width="115" />
            <el-table-column label="次日预测价" width="110"><template #default="{ row }">{{ money(row.next_price) }}</template></el-table-column>
            <el-table-column label="置信度" width="90"><template #default="{ row }">{{ pct(row.confidence) }}</template></el-table-column>
            <el-table-column label="红黄绿灯" width="100"><template #default="{ row }"><span class="pill" :class="row.reliability">{{ overviewReliabilityLabel(row.reliability) }}</span></template></el-table-column>
            <el-table-column prop="freshness_text" label="新鲜度" width="90" />
            <el-table-column prop="updated_at" label="更新时间" min-width="155" />
            <el-table-column prop="model_version" label="模型版本" min-width="130" />
            <el-table-column label="说明" min-width="220" show-overflow-tooltip><template #default="{ row }">{{ row.blocked_reason || row.train_stage || '—' }}</template></el-table-column>
          </el-table>
          <div class="pager-row">
            <span>当前筛选后 {{ overviewTotal }} 条</span>
            <el-pagination background layout="total, prev, pager, next" :total="overviewTotal" :current-page="overviewPage" :page-size="overviewPageSize" @current-change="(p) => { overviewPage = p; loadOverview(false) }" />
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="历史明细" name="history">
        <div class="panel">
          <div class="panel-head"><strong>历史数据明细</strong><span>复用行情趋势的当前日期范围和品名选择</span></div>
          <el-table :data="detailRows" stripe max-height="620" size="small">
            <el-table-column prop="发布日期" label="日期" width="112" />
            <el-table-column prop="品名" label="品名" min-width="130" />
            <el-table-column prop="一级分类" label="一级分类" width="110" />
            <el-table-column prop="平均价" label="平均价" width="100" />
            <el-table-column prop="最低价" label="最低价" width="100" />
            <el-table-column prop="最高价" label="最高价" width="100" />
            <el-table-column prop="产地" label="产地" min-width="140" show-overflow-tooltip />
            <el-table-column prop="单位" label="单位" width="90" />
          </el-table>
        </div>
      </el-tab-pane>

    </el-tabs>

    <el-drawer v-model="detailVisible" direction="rtl" size="72%" :with-header="false" class="forecast-drawer" @closed="() => { mainChart?.dispose(); factorChart?.dispose(); decompChart?.dispose(); mainChart = null; factorChart = null; decompChart = null }">
      <div class="drawer-shell">
        <section class="drawer-hero">
          <div>
            <h2>新发地价格预测引擎</h2>
            <p>Prophet（趋势模型）+ LSTM（短期波动模型）+ XGBoost（特征回归模型）融合，提供未来价格区间与可解释依据。</p>
          </div>
          <button type="button" @click="detailVisible = false">收起详情</button>
        </section>
        <div class="drawer-toolbar">
          <el-select v-model="currentProduct" filterable remote reserve-keyword :remote-method="onProductRemoteQuery" :loading="productSearchLoading" style="width: 260px" @visible-change="onProductDropdownVisible">
            <el-option v-for="name in productOptions" :key="name" :label="name" :value="name" />
          </el-select>
          <el-segmented v-model="forecastDays" :options="dayOptions.map((d) => ({ label: `${d}天`, value: d }))" />
          <el-button type="primary" @click="runPredict">生成预测</el-button>
          <el-button type="warning" plain @click="runRetrain()">重新训练</el-button>
        </div>

        <section class="boss-card">
          <div class="boss-head"><strong>经营结论</strong><span class="pill" :class="reliabilityStatus.className">{{ reliabilityStatus.label }}</span></div>
          <div class="boss-grid">
            <div><span>{{ summary.firstDate }} 参考价</span><strong>{{ summary.nextDay }} 元/斤</strong></div>
            <div><span>平均置信度</span><strong>{{ summary.confidence }}</strong></div>
            <div><span>模型版本</span><strong>{{ summary.modelVersion }}</strong></div>
            <div><span>建议动作</span><strong>{{ bossActionText }}</strong></div>
          </div>
          <p>{{ reliabilityStatus.note }} 预测结果来自训练快照，不使用历史行情冒充未来价格。</p>
        </section>

        <div v-if="trainStatus.status === 'training'" class="train-card">
          <strong>模型训练中：{{ trainStatus.stage || '排队中' }}</strong>
          <el-progress :percentage="Number(trainStatus.progress || 0)" striped striped-flow />
        </div>

        <div class="drawer-kpis">
          <div><strong>{{ summary.sampleCount }}</strong><span>训练样本天数</span></div>
          <div><strong>{{ summary.modelVersion }}</strong><span>模型版本</span></div>
          <div><strong>{{ summary.nextDay }}</strong><span>首个预测均价</span></div>
          <div><strong>{{ summary.confidence }}</strong><span>平均置信度</span></div>
        </div>
        <div class="policy-row"><span>当前策略</span><strong>Rolling Window 365 天</strong><strong>Auto Retrain 7 天</strong></div>

        <div class="panel chart-panel"><div class="panel-head"><strong>预测主图（历史 + 三模型 + 集成区间）</strong></div><div ref="mainChartRef" class="forecast-chart"></div></div>
        <div class="mini-grid">
          <div class="panel"><div class="panel-head"><strong>趋势分解</strong></div><div ref="decompChartRef" class="mini-chart"></div></div>
          <div class="panel"><div class="panel-head"><strong>影响因子权重</strong></div><div ref="factorChartRef" class="mini-chart"></div><p class="mini-note">主导因子：{{ topFactorText }}</p></div>
          <div class="panel"><div class="panel-head"><strong>回测准确率</strong></div><div class="acc-list"><p v-for="(value, key) in (accuracyPayload.accuracy || accuracyPayload || {})" :key="key"><span>{{ key }}</span><strong>{{ value }}</strong></p></div></div>
        </div>
        <div class="panel">
          <div class="panel-head"><strong>预测明细</strong></div>
          <el-table :data="forecastRows" stripe size="small" max-height="360">
            <el-table-column prop="date" label="日期" width="115" />
            <el-table-column label="预测均价" width="110"><template #default="{ row }">{{ money(row.yhat) }}</template></el-table-column>
            <el-table-column label="下界" width="110"><template #default="{ row }">{{ money(row.yhat_lower) }}</template></el-table-column>
            <el-table-column label="上界" width="110"><template #default="{ row }">{{ money(row.yhat_upper) }}</template></el-table-column>
            <el-table-column label="置信度" width="100"><template #default="{ row }">{{ pct(row.confidence) }}</template></el-table-column>
            <el-table-column prop="trend" label="趋势" width="100" />
          </el-table>
        </div>
      </div>
    </el-drawer>

    <el-dialog v-model="backfillVisible" title="批量补抓行情" width="680px" append-to-body class="mine-backfill-dialog" @closed="() => { clearBackfillPoll(); postBackfillDismiss().catch(() => {}); resetBackfillDisplayIdle() }">
      <div class="backfill-dialog-inner">
        <p class="dialog-hint">
          按当前<strong>日期范围</strong>：先查 MySQL 中已有 <code>crawl_date</code> 的日期，<strong>已有则跳过</strong>；仅对缺失日调用新发地接口，日与日期间隔约 <strong>3～5 秒</strong>。VPN 或当日尚未更新导致失败时会写入日志，不影响已入库历史行情。
          <span class="dialog-hint-sub">左侧「从 2024-01-01 慢补至今」固定从 2024-01-01 起<strong>慢速补抓</strong>到<strong>本页日期范围的结束日</strong>（未选完整范围则用今天）；分页冷却 3～7 秒、日间隔 12～25 秒、UA/Referer/Cookie 完整模拟浏览器；遇 403/429 自动长退避（25～240 秒）并清空会话重试。任务时间较长，可关闭页面后续访问，会接续显示进度。</span>
        </p>
        <el-progress
          :percentage="Math.min(100, Math.round(Number(backfillStatus.progress_pct || backfillStatus.progress || 0)))"
          :status="backfillProgressStatus"
          :stroke-width="10"
        />
        <div class="backfill-meta">
          <span v-if="backfillStatus.total">{{ backfillStatus.processed || 0 }} / {{ backfillStatus.total }} 日</span>
          <span v-if="backfillStatus.current">当前：{{ backfillStatus.current }}</span>
          <span v-if="backfillStatus.success">成功：{{ backfillStatus.success }}</span>
        </div>
        <div ref="backfillTerminalRef" class="backfill-terminal">
          <pre class="backfill-log">{{ backfillLogText(backfillStatus) }}</pre>
        </div>
      </div>
      <template #footer>
        <div class="backfill-footer">
          <el-button
            type="warning"
            plain
            :loading="backfillLoading"
            :disabled="backfillRunning"
            @click="confirmSlowBackfillFrom2024"
          >
            从 2024-01-01 慢补至今
          </el-button>
          <div class="backfill-footer-right">
            <el-button @click="backfillVisible = false">关闭</el-button>
            <el-button type="primary" :loading="backfillLoading" :disabled="backfillRunning" @click="confirmBackfill">{{ backfillRunning ? '抓取中...' : '开始补抓' }}</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="natBackfillVisible"
      title="全国农产品价格 · 补抓"
      width="680px"
      append-to-body
      class="mine-backfill-dialog"
      @closed="() => { clearNatBackfillPoll(); resetNatBackfillDisplayIdle() }"
    >
      <div class="backfill-dialog-inner">
        <p class="dialog-hint">
          自动对比库内<strong>最新采集日</strong>与<strong>昨天</strong>（{{ natBackfillPreview.end_date || natYesterdayYmd() }}），列出待补日期；点击开始后仅补<strong>缺失省份</strong>，已齐全日跳过，入库表 <code>zgncpjgw_price_crawl</code>。
        </p>
        <p v-if="natBackfillPreview.message" class="dialog-hint-sub">{{ natBackfillPreview.message }}</p>
        <p v-if="natBackfillPreview.missing_days?.length" class="dialog-hint-sub">
          待补日期：{{ natBackfillPreview.missing_days.join('、') }}
        </p>
        <el-progress
          :percentage="natBackfillProgressPct"
          :status="natBackfillProgressStatus"
          :stroke-width="10"
          :striped="natBackfillRunning && natBackfillStatus.phase === 'crawl'"
          :striped-flow="natBackfillRunning && natBackfillStatus.phase === 'crawl'"
        />
        <div class="backfill-meta">
          <span v-if="natBackfillStatus.message">{{ natBackfillStatus.message }}</span>
          <span v-if="natBackfillStatus.sub_total">
            · 省份 {{ natBackfillStatus.sub_processed || 0 }} / {{ natBackfillStatus.sub_total }}
          </span>
          <span v-if="natBackfillStatus.total">
            · 日期 {{ natBackfillStatus.processed || 0 }} / {{ natBackfillStatus.total }}
          </span>
          <span v-if="natBackfillStatus.current">· 当前：{{ natBackfillStatus.current }}</span>
          <span v-if="natBackfillStatus.success">· 成功日：{{ natBackfillStatus.success }}</span>
        </div>
        <div v-if="natBackfillStatus.phase === 'rebuild' || natBackfillStatus.phase === 'done'" class="rebuild-stage">
          <div class="rebuild-stage-head"><span>派生指标重建（指数 / 异动 / 预测）</span></div>
          <el-progress
            :percentage="Math.min(100, Math.round(Number(natBackfillStatus.rebuild_pct || 0)))"
            :status="natBackfillStatus.phase === 'done' ? 'success' : undefined"
            :stroke-width="10"
          />
        </div>
        <div ref="natBackfillTerminalRef" class="backfill-terminal">
          <pre class="backfill-log">{{ backfillLogText(natBackfillStatus) }}</pre>
        </div>
      </div>
      <template #footer>
        <div class="backfill-footer">
          <div class="backfill-footer-right" style="width: 100%; justify-content: flex-end">
            <el-button @click="natBackfillVisible = false">关闭</el-button>
            <el-button
              type="primary"
              :loading="natBackfillLoading"
              :disabled="natBackfillRunning || !(natBackfillPreview.day_count > 0)"
              @click="confirmNatBackfill"
            >
              {{ natBackfillRunning ? '抓取中...' : '开始抓取' }}
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="natDailyReportVisible"
      title="全国农产品价格 · PDF 日报"
      width="720px"
      append-to-body
      class="mine-backfill-dialog"
    >
      <div v-loading="natDailyReportLoading" class="backfill-dialog-inner">
        <p class="dialog-hint">
          基于库内真实数据生成：<strong>SVG 行情图表</strong>、<strong>AI 决策看板</strong>（高/中/低优先级 + 可执行建议）、
          LLM 润色正文；若已选 SKU/省份，含附录走势图与跨省对比。
        </p>
        <pre class="nat-daily-report-preview">{{ natDailyReportPreviewText() }}</pre>
      </div>
      <template #footer>
        <div class="backfill-footer">
          <div class="backfill-footer-right" style="width: 100%; justify-content: flex-end">
            <el-button @click="natDailyReportVisible = false">关闭</el-button>
            <el-button :loading="natDailyReportLoading" @click="generateNatDailyReportPreview">重新生成</el-button>
            <el-button
              type="primary"
              :loading="natDailyReportPdfLoading"
              :disabled="natDailyReportLoading || !(natDailyReport.sections || []).length"
              @click="downloadNatDailyReportPdf"
            >
              下载 PDF
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="natSuspiciousVisible"
      title="疑似脏数据 SKU 明细"
      width="1040px"
      append-to-body
      class="mine-backfill-dialog nat-rank-dialog nat-quality-dialog"
    >
      <p class="dialog-hint">
        统计日 {{ natSuspiciousMeta.snapshot_date || '—' }} · 统一质量规则识别跨省价格倍数异常 · 共 {{ natSuspiciousMeta.total }} 个
        · 历史每天均已检测落库，可切换日期回看
      </p>
      <div v-if="(natQuality.quality_trend || []).length" class="dq-trend">
        <span class="dq-trend-label">近 30 日异常</span>
        <div class="dq-trend-bars">
          <el-tooltip
            v-for="d in natQuality.quality_trend"
            :key="d.date"
            placement="top"
            popper-class="fh-tip"
            :content="`${d.date} · 高 ${d.high || 0} · 中 ${d.medium || 0}`"
          >
            <i
              class="dq-bar"
              :class="{ risk: (d.high || 0) > 0, active: d.date === natQualityFlagDate }"
              :style="{ height: Math.max(6, qualityTrendBarHeight(d)) + '%' }"
              @click="selectQualityTrendDay(d)"
            />
          </el-tooltip>
        </div>
      </div>
      <div class="quality-workbench-filters">
        <el-date-picker
          v-model="natQualityFlagDate"
          type="date"
          value-format="YYYY-MM-DD"
          :clearable="false"
          placeholder="选择日期"
          :disabled-date="(t) => natQuality.snapshot_date && t > new Date(natQuality.snapshot_date)"
          @change="reloadNatQualityFlags"
        />
        <el-input v-model="natQualityFlagQuery" clearable placeholder="搜索 SKU / 原因" @keyup.enter="reloadNatQualityFlags" />
        <el-select v-model="natQualityFlagSeverity" clearable placeholder="全部级别" @change="reloadNatQualityFlags">
          <el-option label="高风险" value="high" />
          <el-option label="中风险" value="medium" />
        </el-select>
        <el-select v-model="natQualityFlagStatus" clearable placeholder="全部状态" @change="reloadNatQualityFlags">
          <el-option label="待处理" value="open" />
          <el-option label="已隔离" value="quarantined" />
          <el-option label="已修正" value="corrected" />
        </el-select>
        <el-button type="primary" @click="reloadNatQualityFlags">查询</el-button>
      </div>
      <el-table
        v-loading="natSuspiciousLoading"
        :data="natSuspiciousRows"
        stripe
        size="small"
        max-height="480"
        class="nat-dialog-table spread-table-clickable"
      >
        <el-table-column type="index" width="48" label="#" />
        <el-table-column label="品种·规格" min-width="240">
          <template #default="{ row }">
            <div class="quality-sku-cell">
              <div class="quality-sku-name" :title="qualitySkuLabel(row)">{{ qualitySkuLabel(row) }}</div>
              <button type="button" class="quality-sku-query" title="按本条脏数据的精确 SKU 联动页顶查询" @click.stop="drillQualityFlag(row)">
                去查询
              </button>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="cate_name" label="分类" width="80" />
        <el-table-column label="最低价" width="72" align="right" prop="min_price" />
        <el-table-column label="最高价" width="72" align="right" prop="max_price" />
        <el-table-column label="倍数" width="64" align="right">
          <template #default="{ row }"><span class="pill warn nat-dialog-pill">{{ row.price_ratio }}×</span></template>
        </el-table-column>
        <el-table-column label="级别" width="72">
          <template #default="{ row }"><span class="pill" :class="row.severity === 'high' ? 'risk' : 'warn'">{{ row.severity === 'high' ? '高风险' : '中风险' }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="92">
          <template #default="{ row }">{{ qualityStatusLabel(row.status) }}</template>
        </el-table-column>
        <el-table-column label="判定依据" min-width="280">
          <template #default="{ row }">
            <div class="quality-reason-cell">
              <span class="quality-flag-date">异常数据日 {{ qualityFlagDate(row) }}</span>
              <span class="quality-flag-reason" :title="row.reason">{{ row.reason || '—' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="处置" width="150">
          <template #default="{ row }">
            <div class="quality-action-btns">
              <el-tooltip content="重新爬取官网价格，核验源站是否已修正；有更新则本地同步，无更新则保持待处理" placement="top">
                <el-button
                  link
                  type="primary"
                  size="small"
                  :loading="correctingFlagId === row.id"
                  :disabled="correctingFlagId != null && correctingFlagId !== row.id"
                  @click.stop="verifyQualityFlagByRecrawl(row)"
                >
                  修正
                </el-button>
              </el-tooltip>
              <el-tooltip
                v-if="row.status !== 'quarantined'"
                content="将该 SKU 从指数/异动/预测聚合中排除，列表仍可见"
                placement="top"
              >
                <el-button link type="danger" size="small" @click.stop="actOnQualityFlag(row, 'isolate')">隔离</el-button>
              </el-tooltip>
              <el-tooltip v-else content="恢复参与指数/异动/预测聚合计算" placement="top">
                <el-button link type="warning" size="small" @click.stop="actOnQualityFlag(row, 'restore')">恢复</el-button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button class="nat-dialog-close-btn" @click="natSuspiciousVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="natMoversMoreVisible"
      :title="`价格异动雷达 · ${natMoversFilterDesc} · 近 ${natMoversFull.window || natMoversWindow} 日 · Top 100`"
      width="1040px"
      append-to-body
      class="mine-backfill-dialog nat-rank-dialog"
    >
      <p class="dialog-hint">
        {{ natMoversFilterDesc }} · 统计日 {{ natMoversFull.latest_date || natMovers.latest_date || '—' }} · 近 {{ natMoversFull.window || natMoversWindow }} 日涨跌 · 点击行联动地图 / 预测 / 走势
      </p>
      <div v-loading="natMoversMoreLoading" class="movers-more-grid">
        <div class="movers-more-col">
          <div class="movers-h up">▲ {{ natMoversFull.window || natMoversWindow }} 日涨幅榜 TOP {{ (natMoversFull.gainers || []).length }}</div>
          <el-table
            :data="natMoversFull.gainers || []"
            stripe
            size="small"
            max-height="420"
            class="nat-dialog-table spread-table-clickable"
            @row-click="onNatMoversMoreRow"
          >
            <el-table-column type="index" width="48" label="#" />
            <el-table-column prop="goods_name" label="品种" min-width="140" show-overflow-tooltip />
            <el-table-column prop="cate_name" label="分类" width="72" />
            <el-table-column label="涨跌%" width="72" align="right">
              <template #default="{ row }"><span class="mover-pct up">+{{ row.pct }}%</span></template>
            </el-table-column>
            <el-table-column label="价" width="108" align="right">
              <template #default="{ row }"><span class="nat-dialog-price">{{ row.old }} → {{ row.new }}</span></template>
            </el-table-column>
          </el-table>
        </div>
        <div class="movers-more-col">
          <div class="movers-h down">▼ {{ natMoversFull.window || natMoversWindow }} 日跌幅榜 TOP {{ (natMoversFull.losers || []).length }}</div>
          <el-table
            :data="natMoversFull.losers || []"
            stripe
            size="small"
            max-height="420"
            class="nat-dialog-table spread-table-clickable"
            @row-click="onNatMoversMoreRow"
          >
            <el-table-column type="index" width="48" label="#" />
            <el-table-column prop="goods_name" label="品种" min-width="140" show-overflow-tooltip />
            <el-table-column prop="cate_name" label="分类" width="72" />
            <el-table-column label="涨跌%" width="72" align="right">
              <template #default="{ row }"><span class="mover-pct down">{{ row.pct }}%</span></template>
            </el-table-column>
            <el-table-column label="价" width="108" align="right">
              <template #default="{ row }"><span class="nat-dialog-price">{{ row.old }} → {{ row.new }}</span></template>
            </el-table-column>
          </el-table>
        </div>
      </div>
      <template #footer>
        <el-button class="nat-dialog-close-btn" @click="natMoversMoreVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="natSpreadMoreVisible"
      title="区域价差套利榜 · Top 100"
      width="880px"
      append-to-body
      class="mine-backfill-dialog nat-rank-dialog"
    >
      <p class="dialog-hint">
        {{ natSpreadDate ? `统计日 ${natSpreadDate}` : '' }} · 跨省中位价差（截尾）· 点击行联动地图 / 预测 / 走势
      </p>
      <el-table
        v-loading="natSpreadMoreLoading"
        :data="natSpreadFull"
        stripe
        size="small"
        max-height="480"
        class="nat-dialog-table spread-table-clickable"
        @row-click="onNatSpreadRow"
      >
        <el-table-column type="index" width="48" label="#" />
        <el-table-column prop="goods_name" label="品种" min-width="150" show-overflow-tooltip />
        <el-table-column prop="cate_name" label="分类" width="80" />
        <el-table-column label="价差" width="80" align="right">
          <template #default="{ row }"><span class="pill warn nat-dialog-pill">{{ row.spread_pct }}%</span></template>
        </el-table-column>
        <el-table-column label="净价差" width="72" align="right">
          <template #default="{ row }">{{ row.net_spread_pct }}%</template>
        </el-table-column>
        <el-table-column label="低→高" min-width="108" show-overflow-tooltip>
          <template #default="{ row }"><span class="nat-dialog-price">{{ row.cheapest }} → {{ row.priciest }}</span></template>
        </el-table-column>
        <el-table-column label="价" width="100" align="right">
          <template #default="{ row }"><span class="nat-dialog-price">{{ row.min_price }} ~ {{ row.max_price }}</span></template>
        </el-table-column>
        <el-table-column prop="province_count" label="省数" width="52" align="center" />
        <el-table-column prop="sample_count" label="样本" width="52" align="center" />
      </el-table>
      <template #footer>
        <el-button class="nat-dialog-close-btn" @click="natSpreadMoreVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="natCredVisible"
      title="全国农产品价格 · 采集账号"
      width="520px"
      append-to-body
      class="mine-backfill-dialog"
    >
      <div v-loading="natCredLoading" class="backfill-dialog-inner">
        <p class="dialog-hint">
          用于登录 <strong>中农价格网（zgncpjgw.com）</strong> 抓取行情。密码默认掩码显示，点击输入框右侧眼睛可查看明文。
        </p>
        <p v-if="natCredMeta.hint" class="dialog-hint-sub">{{ natCredMeta.hint }}</p>
        <p v-if="natCredMeta.updated_at" class="dialog-hint-sub">
          来源：{{ natCredMeta.source === 'database' ? '页面已保存' : '环境变量 .env' }}
          <span v-if="natCredMeta.updated_at"> · 更新于 {{ formatChinaDateTime(natCredMeta.updated_at) }}</span>
        </p>
        <el-form label-width="88px" @submit.prevent>
          <el-form-item label="手机号">
            <el-input v-model="natCredForm.username" maxlength="32" placeholder="中农价格网登录手机号" clearable />
          </el-form-item>
          <el-form-item label="密码">
            <el-input
              v-model="natCredForm.password"
              type="password"
              show-password
              maxlength="128"
              placeholder="登录密码"
              autocomplete="new-password"
            />
          </el-form-item>
        </el-form>
        <p
          v-if="natCredTestResult"
          class="dialog-hint-sub"
          :style="{ color: natCredTestResult.ok ? 'var(--el-color-success)' : (natCredTestResult.error_kind === 'auth' ? 'var(--el-color-danger)' : 'var(--el-color-warning)') }"
        >
          {{ natCredTestResult.ok ? '✓' : '✗' }} {{ natCredTestResult.message }}
        </p>
        <p class="dialog-hint-sub">
          「测试登录」需启动浏览器过网站防护，一般 <strong>15～60 秒</strong> 才有结果，请耐心等待勿重复点击。
        </p>
        <p class="dialog-hint-sub">
          若补抓失败且日志出现「账号或密码错误」，请在此修改密码后测试并保存；该情况与系统 bug 无关。
        </p>
      </div>
      <template #footer>
        <div class="backfill-footer">
          <div class="backfill-footer-right" style="width: 100%; justify-content: flex-end">
            <el-button @click="natCredVisible = false">关闭</el-button>
            <el-button :loading="natCredTestLoading" :disabled="natCredTestLoading" @click="testNatCredentials">
              {{ natCredTestLoading ? '测试中…' : '测试登录' }}
            </el-button>
            <el-button type="primary" :loading="natCredLoading" @click="saveNatCredentials">保存</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="natTrainingCenterVisible"
      title="全国农产品价格 · 预测训练中心"
      width="760px"
      append-to-body
      class="mine-backfill-dialog nat-training-dialog"
      @closed="onNatTrainingCenterClosed"
    >
      <div v-loading="natHotSkuLoading" class="backfill-dialog-inner">
        <p class="dialog-hint">
          这里训练的是<strong>热门 SKU 批量预测</strong>，用于维护多个品的预测快照；右侧预测图卡片的“更新当前预测”只训练<strong>当前 SKU + 当前省份/全国口径</strong>，两者互不冲突。
          <span class="dialog-hint-sub">热门 SKU 可由客户自行维护；未配置时系统会按最新日覆盖省份数和样本量推荐前 20 个，并明确标记为“系统推荐”。</span>
          <span class="dialog-hint-sub">训练只针对「热门 SKU」（默认系统推荐前 20 个，可自行增删）；不再提供全量训练，避免一次跑数万 SKU 拖垮系统。</span>
        </p>
        <div class="train-summary-grid">
          <div><span>训练范围</span><strong>{{ natHotSkuUsingRecommended ? '系统推荐热门 SKU' : '客户配置热门 SKU' }}</strong></div>
          <div><span>SKU 数</span><strong>{{ natTrainingSkuCount }}</strong></div>
          <div><span>预计任务</span><strong>{{ natTrainingTaskCount }}</strong></div>
          <div><span>预计总耗时</span><strong>约 {{ natTrainingEstimateText }}</strong></div>
        </div>
        <div class="training-actions">
          <el-button type="primary" :disabled="!!natForecastTraining.running || !activeNatHotSkus().length" @click="trainNatHotSkusNow">
            {{ natForecastTraining.running ? '训练中...' : '开始训练热门 SKU' }}
          </el-button>
          <el-button :loading="natHotSkuSaving" :disabled="!natHotSkuConfigured.length" @click="saveNatHotSkus()">保存热门 SKU 设置</el-button>
          <el-button v-if="natHotSkuUsingRecommended" plain @click="saveRecommendedNatHotSkus">保存系统推荐为热门 SKU</el-button>
          <el-button plain @click="natTrainingDetailsOpen = !natTrainingDetailsOpen">{{ natTrainingDetailsOpen ? '收起详情' : '显示详情' }}</el-button>
          <el-button plain @click="minimizeNatTrainingCenter">最小化</el-button>
        </div>
        <div class="train-estimate-line">
          <span v-if="natForecastEtaText">{{ natForecastEtaText }}</span>
          <span v-else>预计耗时会随实际训练速度动态修正，不代表保证完成时间。</span>
        </div>
        <el-progress
          :percentage="natForecastProgressPct"
          :status="natForecastProgressStatus"
          :striped="!!natForecastTraining.running"
          :striped-flow="!!natForecastTraining.running"
          :stroke-width="12"
        />
        <div class="backfill-meta">
          <span v-if="natForecastTraining.total">任务：{{ natForecastTraining.processed || 0 }} / {{ natForecastTraining.total }}</span>
          <span v-if="natForecastTraining.phase_label">阶段：{{ natForecastTraining.phase_label }}</span>
          <span v-if="natForecastTraining.success">成功：{{ natForecastTraining.success }}</span>
          <span v-if="natForecastTraining.failed">失败：{{ natForecastTraining.failed }}</span>
          <span v-if="natForecastTraining.speed_text">速度：{{ natForecastTraining.speed_text }}</span>
        </div>
        <div class="hot-sku-editor">
          <div class="hot-sku-editor__head">
            <strong>热门 SKU 设置</strong>
            <span>{{ natHotSkuUsingRecommended ? '当前使用系统推荐，保存后改为客户配置。' : '客户配置会覆盖系统推荐。' }}</span>
          </div>
          <div class="hot-sku-add">
            <el-select
              v-model="natHotSkuPick"
              filterable
              remote
              reserve-keyword
              clearable
              :remote-method="onNatProductRemoteQuery"
              :loading="natProductSearchLoading"
              placeholder="搜索并添加热门 SKU"
              style="width: 360px"
              @visible-change="(v) => v && onNatProductRemoteQuery('')"
            >
              <el-option v-for="opt in natProductOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
            <el-button @click="addPickedNatHotSku">添加</el-button>
          </div>
          <div class="hot-sku-list">
            <div
              v-for="(item, index) in (natHotSkuConfigured.length ? natHotSkuConfigured : natHotSkuRecommended)"
              :key="item.sku_key"
              class="hot-sku-row"
            >
              <el-switch v-model="item.enabled" :disabled="!natHotSkuConfigured.length" />
              <span>{{ item.label || item.sku_key }}</span>
              <em>{{ natHotSkuConfigured.length ? '客户配置' : '系统推荐' }}</em>
              <button v-if="natHotSkuConfigured.length" type="button" @click="moveNatHotSku(index, -1)">上移</button>
              <button v-if="natHotSkuConfigured.length" type="button" @click="moveNatHotSku(index, 1)">下移</button>
              <button v-if="natHotSkuConfigured.length" type="button" @click="removeNatHotSku(index)">删除</button>
            </div>
          </div>
        </div>
        <div v-if="natTrainingDetailsOpen" class="forecast-pipeline training-detail-box">
          <span class="forecast-pipeline__title">{{ natForecastTraining.phase_label || '训练流水线' }}</span>
          <ul>
            <li v-for="line in natForecastPipelineLines" :key="line">
                        {{ line }}
                        <el-tooltip v-if="line.includes('未过质量规则')" placement="top" popper-class="fh-tip"
                          content="「原始报价」是源站对该 SKU 报过价的总天数；「历史样本」是过完质量规则（剔除跨省价异常/高风险，必要时校正）后真正可用于训练的天数。两者之差即被质量规则剔除的可疑数据。">
                          <u class="zg-help">?</u>
                        </el-tooltip>
                      </li>
          </ul>
        </div>
      </div>
    </el-dialog>

    <div
      v-if="natTrainingCenterMinimized && (natForecastTraining.running || natForecastTraining.finished)"
      class="training-float"
      @click="openNatTrainingCenter"
    >
      <div>
        <strong>{{ natForecastTraining.running ? '预测训练中' : '预测已更新' }}</strong>
        <span>{{ natForecastTraining.phase_label || natForecastTraining.message }}</span>
      </div>
      <em>{{ natForecastProgressPct }}%</em>
      <small>{{ natForecastTraining.eta_text || natForecastEtaText }}</small>
    </div>

    <el-dialog v-model="batchVisible" title="批量重训" width="680px" append-to-body class="mine-backfill-dialog" @closed="clearBatchPoll">
      <div class="backfill-dialog-inner">
        <p class="dialog-hint">
          对<strong>{{ overviewQuery ? '当前筛选命中的' : '全库' }}</strong>可训练品种（近 365 天有效样本 ≥ 120 天）逐个重训：<strong>串行执行、一次一个</strong>，训练在后台线程进行，<strong>不影响其他页面/接口</strong>。全量品种较多，整个过程可能数十分钟至数小时，可关闭弹窗，任务仍在后台继续。
        </p>
        <el-progress
          :percentage="Math.min(100, Math.round(Number(batchStatus.progress_pct || 0)))"
          :status="batchStatus.finished ? (batchStatus.failed ? 'warning' : 'success') : undefined"
          :stroke-width="10"
        />
        <div class="backfill-meta">
          <span v-if="batchStatus.total">{{ batchStatus.processed || 0 }} / {{ batchStatus.total }} 个</span>
          <span v-if="batchStatus.current">当前：{{ batchStatus.current }}</span>
          <span v-if="batchStatus.success">成功：{{ batchStatus.success }}</span>
          <span v-if="batchStatus.failed">失败：{{ batchStatus.failed }}</span>
        </div>
        <div ref="batchTerminalRef" class="backfill-terminal">
          <pre class="backfill-log">{{ (batchStatus.logs || ['等待启动']).join('\n') }}</pre>
        </div>
      </div>
      <template #footer>
        <div class="backfill-footer">
          <div class="backfill-footer-right">
            <el-button @click="batchVisible = false">关闭</el-button>
            <el-button type="warning" :loading="batchLoading" :disabled="batchStatus.running" @click="runBatchRetrain">{{ batchStatus.running ? '训练中...' : '开始批量重训' }}</el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.mine-workbench {
  height: 100vh;
  box-sizing: border-box;
  padding: 24px 28px 40px 124px;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-gutter: stable;
  color: #dfe2f3;
  background:
    radial-gradient(circle at 68% 18%, rgba(0, 229, 255, 0.11), transparent 35%),
    linear-gradient(180deg, #0b101c 0%, #101522 100%);
}
.mine-hero,
.panel,
.sentiment-card,
.kpi-grid > div,
.boss-card,
.drawer-kpis > div,
.train-card,
.policy-row {
  border: 1px solid rgba(0, 229, 255, 0.18);
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(17, 24, 39, 0.92), rgba(11, 16, 28, 0.88));
  box-shadow: inset 0 1px 0 rgba(255,255,255,.04), 0 18px 40px rgba(0,0,0,.24);
}
.eyebrow { margin: 0 0 8px; color: #68fadd; font: 800 12px/1 "JetBrains Mono", monospace; letter-spacing: .16em; }
.mine-hero {
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 30px 32px;
  margin-bottom: 18px;
}
/* 氛围光晕 + 点阵纹理（纯装饰） */
.hero-aura {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.hero-aura::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(130% 150% at 94% -25%, rgba(0, 229, 255, .18), transparent 55%),
    radial-gradient(90% 130% at 102% 130%, rgba(104, 250, 221, .1), transparent 60%);
}
.hero-aura::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image: radial-gradient(rgba(0, 229, 255, .12) 1px, transparent 1.4px);
  background-size: 22px 22px;
  -webkit-mask-image: linear-gradient(100deg, transparent 38%, #000 105%);
  mask-image: linear-gradient(100deg, transparent 38%, #000 105%);
  opacity: .55;
}
.hero-main { position: relative; z-index: 1; min-width: 0; }
.mine-hero .eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 13px;
  padding: 5px 13px 5px 10px;
  border: 1px solid rgba(104, 250, 221, .28);
  border-radius: 999px;
  background: rgba(104, 250, 221, .06);
  color: #68fadd;
  font: 800 11px/1 "JetBrains Mono", monospace;
  letter-spacing: .18em;
}
.eyebrow-pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #5ef0c8;
  box-shadow: 0 0 0 0 rgba(94, 240, 200, .6);
  animation: heroPulse 1.9s ease-out infinite;
}
@keyframes heroPulse {
  0% { box-shadow: 0 0 0 0 rgba(94, 240, 200, .55); }
  70% { box-shadow: 0 0 0 7px rgba(94, 240, 200, 0); }
  100% { box-shadow: 0 0 0 0 rgba(94, 240, 200, 0); }
}
.mine-hero h1 {
  margin: 0;
  font-size: 36px;
  font-weight: 800;
  line-height: 1.08;
  letter-spacing: -.012em;
  background: linear-gradient(118deg, #eafcff 0%, #7fe9ff 52%, #68fadd 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  filter: drop-shadow(0 0 22px rgba(0, 229, 255, .22));
}
.mine-hero .hero-desc {
  margin: 12px 0 0;
  max-width: 640px;
  color: #9fb3bc;
  font-size: 13.5px;
  line-height: 1.62;
}
.hero-metrics {
  position: relative;
  z-index: 1;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
  min-width: 176px;
  padding: 16px 22px;
  border: 1px solid rgba(0, 229, 255, .24);
  border-radius: 14px;
  background: linear-gradient(158deg, rgba(0, 229, 255, .12), rgba(4, 12, 24, .35));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .06), 0 14px 34px -18px rgba(0, 229, 255, .4);
}
.hero-metrics .hm-top { color: #9fb3bc; font-size: 12.5px; font-weight: 600; }
.hero-metrics .hm-bottom {
  font: 800 26px/1 "Space Grotesk", "JetBrains Mono", monospace;
  font-variant-numeric: tabular-nums;
  color: #9cf0ff;
  text-shadow: 0 0 18px rgba(0, 229, 255, .3);
}
@media (max-width: 900px) {
  .mine-hero { flex-direction: column; align-items: flex-start; }
  .hero-metrics { align-items: flex-start; width: 100%; }
}
.mine-tabs :deep(.el-tabs__item) { color: #a8bbc5; font-weight: 700; font-size: 15px; padding: 0 20px; transition: color .15s ease; }
.mine-tabs :deep(.el-tabs__item:hover) { color: #cdeef5; }
.mine-tabs :deep(.el-tabs__item.is-active) { color: #9cf0ff; }
.mine-tabs :deep(.el-tabs__active-bar) { background: linear-gradient(90deg, #68fadd, #00e5ff); height: 3px; border-radius: 3px; box-shadow: 0 0 12px rgba(0, 229, 255, .5); }
.mine-tabs :deep(.el-tabs__nav-wrap::after) { background-color: rgba(0, 229, 255, .12); }
.sentiment-card { display: flex; align-items: center; gap: 18px; padding: 18px 20px; margin-bottom: 16px; }
.sentiment-card span { color: #c7d9df; font-weight: 800; }
.sentiment-card strong { font-size: 30px; }
.sentiment-card p { margin: 0; color: #9fb3bc; }
.dir-up { color: #ff7a90; }
.dir-down { color: #5fe3a1; }
.dir-flat { color: #9cf0ff; }
.panel { padding: 18px 20px; margin-bottom: 16px; }

/* —— 智能预测主视觉 —— */
.forecast-hero { border: 1px solid rgba(0,229,255,.22); border-radius: 12px; background: linear-gradient(135deg, rgba(0,229,255,.08), rgba(8,14,26,.66)); }
.forecast-hero .eyebrow { color: rgba(103,255,219,.7); font: 700 11px/1.4 "JetBrains Mono", monospace; letter-spacing: .12em; margin: 0 0 4px; }
.fh-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.fh-head h3 { margin: 0; color: #dffbff; font-size: 22px; font-weight: 800; }
.fh-focus { text-align: right; }
.fh-focus > span { color: #8ba0aa; font-size: 12px; }
.fh-select { width: 260px; margin-top: 6px; }
.fh-chips { display: flex; gap: 8px; margin-top: 8px; justify-content: flex-end; flex-wrap: wrap; }
.fh-chips button { border: 1px solid rgba(0,229,255,.28); color: #dffbff; background: rgba(2,10,20,.7); border-radius: 999px; padding: 5px 14px; cursor: pointer; font-weight: 700; transition: all .15s ease; }
.fh-chips button.active { color: #02161b; background: linear-gradient(135deg, #7fffee, #00d5ff); border-color: transparent; box-shadow: 0 0 14px rgba(0,229,255,.3); }
.fh-body { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(240px, 1fr); gap: 18px; }
.fh-chart { min-width: 0; }
.focus-chart { height: 320px; }
.fh-side { display: flex; flex-direction: column; gap: 12px; }
.fh-light { display: flex; align-items: center; gap: 8px; padding: 8px 14px; border-radius: 999px; font-weight: 800; align-self: flex-start; }
.fh-light i { width: 12px; height: 12px; border-radius: 50%; }
.fh-light.ok { color: #5fe3a1; background: rgba(95,227,161,.12); } .fh-light.ok i { background: #5fe3a1; box-shadow: 0 0 10px #5fe3a1; }
.fh-light.warn { color: #ffd166; background: rgba(255,209,102,.12); } .fh-light.warn i { background: #ffd166; box-shadow: 0 0 10px #ffd166; }
.fh-light.risk { color: #ff7a90; background: rgba(255,122,144,.12); } .fh-light.risk i { background: #ff7a90; box-shadow: 0 0 10px #ff7a90; }
.fh-tiles { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.fh-tiles > div { padding: 12px 14px; border: 1px solid rgba(0,229,255,.14); border-radius: 10px; background: rgba(2,10,20,.5); }
.fh-tiles span { display: block; color: #8ba0aa; font-size: 12px; margin-bottom: 4px; }
.fh-tiles strong { color: #dffbff; font-size: 22px; font-weight: 800; }
.fh-tiles strong.up, .fh-tiles em.up { color: #ff7a90; }
.fh-tiles strong.down, .fh-tiles em.down { color: #5fe3a1; }
.fh-tiles em { font-style: normal; margin-left: 6px; font-size: 12px; color: #8ba0aa; }
.tip-card { cursor: help; }
.fh-tiles .tip-card span u, .fh-light u { text-decoration: none; display: inline-flex; align-items: center; justify-content: center; width: 14px; height: 14px; border-radius: 50%; border: 1px solid rgba(0,229,255,.4); color: rgba(0,229,255,.8); font-size: 10px; line-height: 1; margin-left: 4px; }
.fh-light u { border-color: currentColor; color: currentColor; opacity: .7; }
.fh-ai { margin: 14px 0 0; padding: 12px 16px; border-left: 3px solid rgba(0,229,255,.6); border-radius: 0 8px 8px 0; background: rgba(255,255,255,.04); color: #eaf8ff; line-height: 1.6; }
@media (max-width: 1200px) { .fh-body { grid-template-columns: 1fr; } }

.filter-panel :deep(.el-form-item__label) { color: #c7d9df; }
.quick-picks { display: flex; align-items: center; gap: 10px; color: #8ba0aa; }
.quick-picks button { border: 1px solid rgba(0,229,255,.28); color: #dffbff; background: rgba(0,229,255,.08); border-radius: 999px; padding: 5px 12px; cursor: pointer; }
.kpi-grid, .drawer-kpis, .boss-grid, .mini-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 16px; }
.kpi-grid > div, .drawer-kpis > div { padding: 18px; text-align: center; }
.kpi-grid strong, .drawer-kpis strong { display: block; color: #dffbff; font-size: 28px; }
.kpi-grid span, .drawer-kpis span { color: #8ba0aa; font-size: 12px; }
/* —— KPI 卡片高级化（仅作用于 kpi-grid，不影响 drawer/boss/mini）—— */
.kpi-grid > div {
  position: relative;
  overflow: hidden;
  transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}
.kpi-grid > div::before {
  content: '';
  position: absolute;
  left: 0; right: 0; top: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(0, 229, 255, .65), transparent);
  opacity: 0;
  transition: opacity .2s ease;
}
.kpi-grid > div:hover {
  transform: translateY(-3px);
  border-color: rgba(0, 229, 255, .42);
  box-shadow: 0 22px 42px -20px rgba(0, 229, 255, .34), inset 0 1px 0 rgba(255, 255, 255, .06);
}
.kpi-grid > div:hover::before { opacity: 1; }
.kpi-grid strong {
  font-family: "Space Grotesk", "JetBrains Mono", monospace;
  font-variant-numeric: tabular-nums;
  letter-spacing: -.01em;
}
.kpi-grid span { display: block; margin-top: 6px; letter-spacing: .02em; }
.nat-kpi .kpi-cumulative {
  border-color: rgba(126, 232, 255, .42);
  background: linear-gradient(135deg, rgba(0, 229, 255, .15), rgba(11, 16, 28, .9));
}
.panel-head, .table-head, .boss-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.panel-head-meta { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.nat-movers-head-meta { gap: 6px; }
.nat-movers-window-select { width: 88px; }
.nat-movers-cate-select { width: 108px; }
.nat-movers-scate-select { width: 100px; }
.nat-movers-province-select { width: 96px; }
.nat-movers-window-select :deep(.el-input__wrapper),
.nat-movers-cate-select :deep(.el-input__wrapper),
.nat-movers-scate-select :deep(.el-input__wrapper),
.nat-movers-province-select :deep(.el-input__wrapper) {
  background: rgba(0, 229, 255, .06);
  box-shadow: 0 0 0 1px rgba(0, 229, 255, .22) inset;
}
.panel-head-meta--inline { justify-content: flex-start; margin-top: 6px; }
.panel-head-meta--inline label { color: #8ba0aa; font-size: 12px; font-style: normal; font-weight: 700; }
.panel-head-title-stack { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; min-width: 0; }
.panel-head-suffix { color: #8ba0aa; font-size: 13px; font-style: normal; font-weight: 400; }
.nat-primary-sku-select { width: min(300px, 40vw); }
.nat-primary-sku-select :deep(.el-input__wrapper) { background: rgba(2, 16, 28, .85); box-shadow: 0 0 0 1px rgba(0, 229, 255, .22) inset; }
.nat-primary-sku-select :deep(.el-input__inner) { color: #dffbff; }
.panel-head strong, .table-head strong, .boss-head strong { color: #dffbff; font-size: 18px; }
.panel-head span { color: #7f939c; }
.trend-chart { height: 430px; }
.compare-chart { height: 360px; }
.nat-kpi { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.nat-kpi .kpi-cumulative strong { color: #7ee8ff; }
@media (max-width: 1200px) { .nat-kpi { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.nat-snap-note { margin: -8px 0 16px; color: #7f939c; font-size: 12px; }
.zg-quality { display: grid; grid-template-columns: minmax(180px, 220px) minmax(0, 1fr); gap: 18px; align-items: center; }
.zq-score { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.zq-label { color: #8ba0aa; font-size: 12px; }
.zq-num { font: 800 44px/1 "JetBrains Mono", monospace; }
.zq-score.ok .zq-num { color: #5fe3a1; } .zq-score.warn .zq-num { color: #ffd166; } .zq-score.risk .zq-num { color: #ff7a90; } .zq-score.mid .zq-num { color: #9cf0ff; }
.zq-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.zq-cell { padding: 10px 12px; border: 1px solid rgba(0,229,255,.14); border-radius: 8px; background: rgba(2,10,20,.5); cursor: help; }
.zq-cell-clickable { cursor: pointer; transition: border-color .15s, background .15s, box-shadow .15s; }
.zq-cell-clickable:hover { border-color: rgba(255, 184, 77, .45); background: rgba(255, 184, 77, .08); box-shadow: 0 0 12px rgba(255, 184, 77, .12); }
.zq-cell-hint { display: block; margin-top: 6px; color: #67e8f9; font-size: 11px; font-weight: 700; }
.zq-cell span { display: block; color: #8ba0aa; font-size: 12px; margin-bottom: 4px; }
.zq-cell strong { color: #dffbff; font-size: 20px; font-weight: 800; }
.zq-cell em { font-style: normal; color: #7f939c; font-size: 12px; margin-left: 6px; }
@media (max-width: 1200px) { .zg-quality { grid-template-columns: 1fr; } .zq-metrics { grid-template-columns: repeat(2, 1fr); } }
.ph-right { display: inline-flex; align-items: center; gap: 10px; }
.dl-btn { border: 1px solid rgba(0,229,255,.28); color: #9cf0ff; background: rgba(0,229,255,.06); border-radius: 6px; padding: 2px 8px; font-size: 12px; cursor: pointer; white-space: nowrap; }
.dl-btn:hover { background: rgba(0,229,255,.14); }
.dl-btn-float { position: absolute; top: 6px; right: 6px; z-index: 2; }
.zg-index-chart { position: relative; }
.zg-secnav { position: sticky; top: 0; z-index: 5; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 0 0 14px; padding: 8px 12px; border: 1px solid rgba(0,229,255,.18); border-radius: 8px; background: rgba(11,16,28,.92); backdrop-filter: blur(4px); }
.zg-secnav-label { color: #68fadd; font: 800 11px/1 "JetBrains Mono", monospace; letter-spacing: .1em; }
.zg-secnav button { border: 1px solid rgba(0,229,255,.25); color: #dffbff; background: rgba(0,229,255,.06); border-radius: 999px; padding: 4px 14px; font-size: 13px; cursor: pointer; transition: all .15s ease; }
.zg-secnav button:hover { background: rgba(0,229,255,.16); border-color: rgba(0,229,255,.5); }
.sku-drawer :deep(.el-drawer) { background: #0b101c; }
.skud-shell { padding: 20px 22px; color: #dfe2f3; }
.skud-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.skud-head h2 { margin: 4px 0 0; color: #dffbff; font-size: 20px; }
.skud-block { margin-bottom: 18px; }
.skud-title { margin: 0 0 8px; color: #9cf0ff; font-size: 13px; font-weight: 800; }
.skud-stats { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; }
.skud-stats > div, .skud-fc > div { padding: 8px 10px; border: 1px solid rgba(0,229,255,.14); border-radius: 8px; background: rgba(2,10,20,.5); text-align: center; }
.skud-stats span, .skud-fc span { display: block; color: #8ba0aa; font-size: 11px; margin-bottom: 4px; }
.skud-stats strong, .skud-fc strong { color: #dffbff; font-size: 16px; font-weight: 800; }
.skud-fc { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.skud-chart { height: 180px; }
.skud-prov { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
.skud-prov-row { display: flex; justify-content: space-between; padding: 6px 10px; border-bottom: 1px solid rgba(255,255,255,.06); }
.skud-prov-row span { color: #c7d9df; } .skud-prov-row strong { color: #dffbff; }
@media (max-width: 1200px) { .skud-stats { grid-template-columns: repeat(3, 1fr); } }
.nat-gap-alert { margin-bottom: 14px; }
/* 深色 loading 遮罩，避免在深色卡片上闪白 */
:deep(.el-loading-mask) { background-color: rgba(8, 13, 24, 0.6); }
:deep(.el-loading-spinner .path) { stroke: #00e5ff; }
:deep(.el-loading-spinner .el-loading-text) { color: #9cf0ff; }
.zg-help { display: inline-flex; align-items: center; justify-content: center; width: 14px; height: 14px; border-radius: 50%; border: 1px solid rgba(0,229,255,.45); color: rgba(0,229,255,.85); font-size: 10px; text-decoration: none; margin-left: 4px; cursor: help; vertical-align: middle; }
.zg-index-unit { font-size: 14px; font-weight: 700; color: #7f939c; margin-left: 6px; letter-spacing: 0; }
.zg-index-disclaimer { margin: 8px 0 0; color: #8ba0aa; font-size: 12px; }
.zg-index-disclaimer b { color: #ffd166; }
.sku-price-strip { display: flex; flex-wrap: wrap; gap: 10px; margin: 4px 0 14px; }
.sku-price-card { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; min-width: 150px; padding: 8px 12px; border: 1px solid rgba(0,229,255,.18); border-radius: 8px; background: rgba(2,10,20,.5); cursor: pointer; transition: all .15s ease; }
.sku-price-card:hover { border-color: rgba(0,229,255,.45); }
.sku-price-card.active { border-color: #00e5ff; background: rgba(0,229,255,.12); box-shadow: 0 0 12px rgba(0,229,255,.2); }
.spc-name { color: #c7d9df; font-size: 12px; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.spc-price { color: #dffbff; font-size: 20px; font-weight: 800; font-family: "JetBrains Mono", monospace; }
.spc-chg { font-size: 12px; font-weight: 700; }
.spc-chg.up { color: #ff7a90; }
.spc-chg.down { color: #5fe3a1; }
.rebuild-stage { margin-top: 12px; padding-top: 10px; border-top: 1px dashed rgba(0,229,255,.18); }
.rebuild-stage-head { color: #9cf0ff; font-size: 12px; font-weight: 700; margin-bottom: 6px; }
.chart-stack { position: relative; }
.map-province-layout { display: grid; grid-template-columns: minmax(0, 1fr) 206px; gap: 14px; align-items: stretch; }
.nat-empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: #7f939c; font-size: 14px; pointer-events: none; text-align: center; padding: 18px 24px; }
.forecast-hint-link {
  margin-left: 8px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #67e8f9;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}
.forecast-hint-link:hover { color: #9cf0ff; text-decoration: underline; }
.forecast-hint-pop { margin: 0; color: #c7e8f0; font-size: 12px; line-height: 1.65; }
.zg-index-grid { display: grid; grid-template-columns: minmax(220px, 320px) minmax(0, 1fr); gap: 18px; align-items: center; }
.zg-index-num { font: 800 56px/1 "JetBrains Mono", monospace; color: #00e5ff; text-shadow: 0 0 22px rgba(0,229,255,.4); }
.zg-basket-note { margin: 4px 0 10px; color: #9fe8f5; font-size: 13px; font-weight: 700; }
.zg-index-num.down { color: #5fe3a1; text-shadow: 0 0 22px rgba(95,227,161,.4); }
.zg-index-chg { margin-top: 6px; font-size: 16px; font-weight: 800; color: #ff7a90; }
.zg-index-chg.down { color: #5fe3a1; }
.zg-index-chg span { color: #8ba0aa; font-weight: 600; margin-left: 6px; font-size: 12px; }
.zg-cat-chips {
  display: flex; flex-wrap: wrap; gap: 6px; margin-top: 14px;
  max-height: 108px; overflow-y: auto; padding-right: 4px;
}
.zg-cat-chips::-webkit-scrollbar { width: 4px; }
.zg-cat-chips::-webkit-scrollbar-thumb { background: rgba(0,229,255,.25); border-radius: 4px; }
.cat-toggle { cursor: pointer; border: 1px solid currentColor; }
.cat-toggle.active { box-shadow: 0 0 0 1px rgba(255,255,255,.36), 0 0 14px rgba(0,229,255,.24); }
.index-chart { height: 220px; }
.map-chart { height: 460px; min-width: 0; }
.nat-forecast-chart { height: 278px; }
.province-picker { min-height: 0; height: 460px; max-height: 460px; overflow: auto; padding: 12px; border: 1px solid rgba(0,229,255,.18); border-radius: 8px; background: linear-gradient(180deg, rgba(2,16,28,.72) 0%, rgba(2,10,20,.42) 100%); box-shadow: inset 0 1px 0 rgba(255,255,255,.04); }
.province-picker__head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.province-picker__head strong { color: #dffbff; font-size: 13px; }
.province-picker button { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 7px; padding: 9px 10px; border: 1px solid rgba(0,229,255,.18); border-radius: 7px; color: #ccecf4; background: rgba(0,229,255,.055); cursor: pointer; }
.province-picker__head button { width: auto; margin: 0; padding: 5px 9px; font-size: 12px; }
.province-picker button:hover, .province-picker button.active { color: #06202c; border-color: rgba(255,209,102,.76); background: linear-gradient(180deg, #ffe08a 0%, #ffd166 100%); }
.province-picker em { font-style: normal; font-family: "JetBrains Mono", monospace; font-size: 13px; font-weight: 800; opacity: .95; }
.zg-change-rank-panel { margin-bottom: 16px; }
.zg-change-rank-head {
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 10px 16px;
}
.zg-change-rank-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.nat-change-rank-filters { gap: 8px; }
.nat-change-province-select { width: 108px; }
.nat-change-cate-select { width: 120px; }
.nat-change-scate-select { width: 108px; }
.nat-change-baseline-select { width: 88px; }
.nat-change-province-select :deep(.el-input__wrapper),
.nat-change-cate-select :deep(.el-input__wrapper),
.nat-change-scate-select :deep(.el-input__wrapper),
.nat-change-baseline-select :deep(.el-input__wrapper) {
  background: rgba(0, 229, 255, .06);
  box-shadow: 0 0 0 1px rgba(0, 229, 255, .22) inset;
}
.zg-change-rank-meta {
  flex: 1 1 100%;
  font-size: 12px;
  color: #8ba0aa;
  text-align: right;
  line-height: 1.4;
}
@media (min-width: 900px) {
  .zg-change-rank-meta { flex: 1 1 auto; text-align: right; }
}
.zg-rank-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.zg-rank-col { min-width: 0; }
.zg-rank-h { font-weight: 800; font-size: 13px; margin-bottom: 8px; }
.zg-rank-h.up { color: #ff9a6b; }
.zg-rank-h.down { color: #5fe3a1; }
.zg-rank-chart-wrap { position: relative; width: 100%; min-height: 280px; }
.zg-rank-chart { width: 100%; height: 360px; min-height: 280px; cursor: pointer; }
.zg-rank-empty { flex-direction: column; gap: 8px; padding: 0 20px; line-height: 1.5; }
.zg-rank-empty-sub { font-size: 12px; color: #6d838c; max-width: 280px; text-align: center; }
.zg-rank-empty-hint { margin: 0 0 12px; padding: 10px 12px; border-radius: 8px; background: rgba(255,255,255,.04); border: 1px dashed rgba(127,147,156,.35); }
.movers-empty { margin: 8px 0 0; min-height: 48px; }
@media (max-width: 1200px) {
  .zg-rank-grid { grid-template-columns: 1fr; }
  .zg-change-rank-meta { text-align: left; }
}
.zg-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.zg-two-col > .panel { margin-bottom: 16px; }
@media (max-width: 1200px) { .zg-index-grid, .zg-two-col, .map-province-layout { grid-template-columns: 1fr; } .province-picker { height: auto; max-height: 220px; } .map-chart { height: 400px; } }
.forecast-head-actions { display: inline-flex; align-items: center; gap: 10px; }
.fc-mode-toggle { margin-right: 2px; }
.fc-raw-note { margin: 0 0 6px; padding: 5px 10px; border-radius: 6px; background: rgba(228,93,102,.08); color: #c7d9df; font-size: 11px; line-height: 1.5; }
.fc-raw-note .fc-raw-dot { color: #e45d66; font-weight: 700; }
.text-link { border: none; padding: 0; color: #67e8f9; background: transparent; cursor: pointer; font-weight: 700; }
.forecast-explain p { margin: 0 0 8px; color: #344054; line-height: 1.6; font-size: 13px; }
.forecast-status-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; margin: -4px 0 8px; padding: 8px 10px; border: 1px solid rgba(0,229,255,.13); border-radius: 8px; background: linear-gradient(90deg, rgba(0,229,255,.075) 0%, rgba(0,229,255,.025) 100%); color: #9fb3bc; font-size: 12px; }
.forecast-progress-main { flex: 1; min-width: 0; }
.forecast-progress-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 5px; }
.forecast-progress-head span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #a8c8d3; }
.forecast-progress-head em { flex-shrink: 0; font-style: normal; color: #67e8f9; font-family: "JetBrains Mono", monospace; font-size: 11px; }
.forecast-pipeline { margin-top: 6px; padding-top: 6px; border-top: 1px dashed rgba(0,229,255,.14); }
.forecast-pipeline__title { display: block; margin-bottom: 3px; color: #67e8f9; font-size: 11px; font-weight: 800; }
.forecast-pipeline ul { margin: 0; padding: 0; list-style: none; display: grid; gap: 2px; }
.forecast-pipeline li { position: relative; padding-left: 12px; color: #8fb4c0; line-height: 1.35; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.forecast-pipeline li::before { content: ""; position: absolute; left: 0; top: .55em; width: 5px; height: 5px; border-radius: 50%; background: #00e5ff; box-shadow: 0 0 8px rgba(0,229,255,.7); }
.forecast-status-row button { flex-shrink: 0; border: 1px solid rgba(0,229,255,.32); color: #dffbff; background: rgba(0,229,255,.08); border-radius: 7px; padding: 5px 9px; cursor: pointer; }
.forecast-status-row button:hover { border-color: rgba(103,232,249,.72); color: #fff; }
.forecast-status-row button:disabled { cursor: not-allowed; opacity: .55; border-color: rgba(148,163,184,.24); color: #94a3b8; background: rgba(148,163,184,.08); }
.train-summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 12px 0; }
.train-summary-grid > div { padding: 10px 12px; border: 1px solid rgba(0,229,255,.16); border-radius: 8px; background: rgba(2,10,20,.45); }
.train-summary-grid span { display: block; color: #8ba0aa; font-size: 12px; }
.train-summary-grid strong { display: block; margin-top: 5px; color: #dffbff; font-size: 16px; }
.training-actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
.training-mode-row { display: flex; align-items: center; gap: 12px; margin: 12px 0 8px; color: #c7d9df; }
.training-mode-row > span { font-weight: 800; }
.train-estimate-line { margin: 8px 0; color: #9fe8f5; font-size: 12px; }
.hot-sku-editor { margin-top: 14px; padding-top: 12px; border-top: 1px dashed rgba(0,229,255,.18); }
.hot-sku-editor__head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
.hot-sku-editor__head strong { color: #dffbff; }
.hot-sku-editor__head span { color: #8ba0aa; font-size: 12px; }
.hot-sku-add { display: flex; gap: 8px; margin-bottom: 10px; }
.hot-sku-list { max-height: 260px; overflow: auto; display: grid; gap: 7px; }
.hot-sku-row { display: grid; grid-template-columns: 44px minmax(0, 1fr) auto auto auto auto; align-items: center; gap: 8px; padding: 8px 10px; border: 1px solid rgba(0,229,255,.13); border-radius: 8px; background: rgba(0,229,255,.045); }
.hot-sku-row span { color: #dffbff; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hot-sku-row em { font-style: normal; color: #8ba0aa; font-size: 12px; }
.hot-sku-row button { border: 1px solid rgba(0,229,255,.24); border-radius: 6px; padding: 4px 7px; color: #c7f4ff; background: rgba(0,229,255,.06); cursor: pointer; }
.hot-sku-row button:hover { border-color: rgba(103,232,249,.7); color: #fff; }
.training-detail-box { margin-top: 12px; padding: 10px; border: 1px solid rgba(0,229,255,.12); border-radius: 8px; background: rgba(2,10,20,.42); }
.training-float { position: fixed; top: 92px; right: 24px; z-index: 3000; width: 310px; padding: 12px 14px; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px 12px; border: 1px solid rgba(0,229,255,.36); border-radius: 10px; color: #dffbff; background: linear-gradient(135deg, rgba(3,18,31,.96), rgba(5,48,64,.94)); box-shadow: 0 16px 50px rgba(0,0,0,.36), 0 0 28px rgba(0,229,255,.12); cursor: pointer; }
.training-float strong { display: block; font-size: 14px; }
.training-float span { display: block; margin-top: 3px; color: #8fd6e4; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.training-float em { grid-row: 1 / span 2; align-self: center; font-style: normal; font: 800 24px/1 "JetBrains Mono", monospace; color: #67e8f9; }
.training-float small { grid-column: 1 / -1; color: #ffd166; font-size: 12px; }
.fc-tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 10px; }
.fc-tiles > div { padding: 8px 10px; border: 1px solid rgba(0,229,255,.14); border-radius: 8px; background: rgba(2,10,20,.5); }
.fc-tiles span { display: block; color: #8ba0aa; font-size: 11px; }
.fc-tiles strong { color: #dffbff; font-size: 18px; font-weight: 800; }
.movers-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.movers-more-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
}
.movers-more-col { min-width: 0; overflow: hidden; }
@media (max-width: 1000px) {
  .movers-more-grid { grid-template-columns: 1fr; }
}
.spread-table-clickable :deep(.el-table__row) { cursor: pointer; }
.spread-table-clickable :deep(.el-table__row:hover) { background: rgba(0,229,255,.08) !important; }
.movers-h { font-weight: 800; font-size: 13px; margin-bottom: 8px; }
.movers-h.up { color: #ff7a90; } .movers-h.down { color: #5fe3a1; }
.mover-row { display: flex; justify-content: space-between; gap: 8px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,.06); }
.mover-row.clickable { cursor: pointer; padding: 7px 8px; border-radius: 6px; }
.mover-row.clickable:hover { background: rgba(0,229,255,.08); border-color: rgba(0,229,255,.18); }
.mover-name { color: #dfe2f3; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mover-pct { font-weight: 800; font-size: 13px; white-space: nowrap; }
.mover-pct.up { color: #ff7a90; } .mover-pct.down { color: #5fe3a1; }
.briefing-text { color: #eaf8ff; line-height: 1.8; white-space: pre-wrap; padding: 12px 16px; border-left: 3px solid rgba(0,229,255,.6); background: rgba(255,255,255,.04); border-radius: 0 8px 8px 0; margin: 0; }
.briefing-src-tag { font-size: 11px; color: rgba(0,229,255,.75); margin-right: auto; margin-left: 10px; padding: 2px 8px; border: 1px solid rgba(0,229,255,.25); border-radius: 4px; }
.briefing-report { padding: 4px 0 8px; }
.briefing-headline { color: #fff; font-size: 15px; font-weight: 600; line-height: 1.55; margin: 0 0 10px; padding: 10px 14px; background: linear-gradient(90deg, rgba(0,229,255,.12), transparent); border-radius: 8px; border-left: 3px solid #00e5ff; }
.briefing-outlook { color: #b8e4f0; font-size: 13px; line-height: 1.65; margin: 0 0 14px; padding: 0 4px; }
.briefing-sec { margin-bottom: 12px; padding: 10px 12px; background: rgba(255,255,255,.03); border-radius: 8px; border: 1px solid rgba(255,255,255,.06); }
.briefing-sec-title { margin: 0 0 8px; font-size: 13px; color: #00e5ff; font-weight: 600; letter-spacing: .02em; }
.briefing-sec-body { margin: 0 0 6px; color: #d4eef8; font-size: 13px; line-height: 1.7; }
.briefing-sec-list { margin: 0; padding-left: 18px; color: #c8e6f2; font-size: 12px; line-height: 1.75; }
.briefing-sec-list li { margin-bottom: 4px; }
.nat-daily-report-preview {
  max-height: 360px; overflow: auto; margin: 0; padding: 12px 14px;
  color: #eaf8ff; line-height: 1.65; white-space: pre-wrap; font-size: 12px;
  border: 1px solid rgba(0,229,255,.2); border-radius: 8px; background: rgba(0,0,0,.25);
}
.detail-collapse { --el-collapse-header-bg-color: rgba(11,16,28,.88); --el-collapse-content-bg-color: rgba(11,16,28,.88); --el-collapse-header-text-color: #dffbff; --el-collapse-content-text-color: #dfe2f3; border-color: rgba(0,229,255,.18); }
.overview-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 10px; }
.switch-line { display: inline-flex; align-items: center; gap: 6px; color: #a8bbc5; }
.pill { display: inline-flex; align-items: center; padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 800; }
.pill.ok, .pill.high { color: #b7ffe7; background: rgba(38, 166, 113, .22); border: 1px solid rgba(95,227,161,.35); }
.pill.warn, .pill.mid { color: #ffe7ad; background: rgba(255, 184, 77, .2); border: 1px solid rgba(255,204,102,.35); }
.pill.risk, .pill.low { color: #ffc8d2; background: rgba(255, 83, 112, .18); border: 1px solid rgba(255,122,144,.35); }
.pager-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 14px; color: #8ba0aa; }
.drawer-shell { padding: 22px; color: #dfe2f3; background: #0b101c; min-height: 100%; }
.drawer-hero { display: flex; justify-content: space-between; gap: 18px; padding: 22px; border-radius: 8px; background: linear-gradient(135deg, rgba(40, 52, 70, .96), rgba(19, 28, 46, .96)); }
.drawer-hero h2 { margin: 0; color: #fff; }
.drawer-hero p { color: #c8d4dc; }
.drawer-hero button { height: 34px; border: 1px solid rgba(0,229,255,.35); color: #dffbff; background: rgba(0,229,255,.08); border-radius: 7px; padding: 0 14px; }
.drawer-toolbar { display: flex; align-items: center; gap: 12px; margin: 14px 0; }
.boss-card { padding: 18px 20px; margin-bottom: 16px; }
.boss-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.boss-grid div { padding: 14px; border-radius: 8px; background: rgba(6, 12, 24, .68); }
.boss-grid span, .boss-card p { color: #9fb3bc; }
.boss-grid strong { display: block; margin-top: 8px; color: #fff; font-size: 18px; }
.train-card { padding: 14px 16px; margin-bottom: 16px; }
.policy-row { display: flex; align-items: center; gap: 12px; padding: 12px 14px; margin-bottom: 16px; }
.policy-row strong { color: #9cf0ff; }
.forecast-chart { height: 430px; }
.mini-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.mini-chart { height: 250px; }
.mini-note { margin: 8px 0 0; color: #9fb3bc; }
.acc-list p { display: flex; justify-content: space-between; color: #9fb3bc; border-bottom: 1px solid rgba(255,255,255,.08); padding: 9px 0; margin: 0; }
.acc-list strong { color: #dffbff; }
.dialog-hint { color: #a8bbc5; margin-top: 0; line-height: 1.65; }
.nat-quality-filter-note { margin: 6px 0 10px; color: #8ba0aa; font-size: 12px; }
.quality-workbench-filters { display: grid; grid-template-columns: minmax(180px, 1fr) 130px 150px auto; gap: 8px; margin-bottom: 12px; }
.dialog-hint-sub { display: block; margin-top: 10px; color: #8ba0aa; font-size: 12px; line-height: 1.55; }
.backfill-meta { display: flex; flex-wrap: wrap; gap: 16px; margin: 8px 0 12px; color: #8ba0aa; font: 12px/1.4 "JetBrains Mono", monospace; }
.backfill-terminal { min-height: 220px; max-height: 360px; overflow: auto; padding: 12px; border: 1px solid rgba(0,229,255,.18); border-radius: 8px; background: #07101d; }
.backfill-log { margin: 0; color: #9cf0ff; white-space: pre-wrap; word-break: break-word; font: 12px/1.6 "JetBrains Mono", monospace; }
:deep(.el-table) { --el-table-bg-color: transparent; --el-table-tr-bg-color: rgba(8, 13, 24, .62); --el-table-header-bg-color: rgba(10, 18, 32, .9); --el-table-row-hover-bg-color: rgba(0, 229, 255, .1); --el-table-text-color: #dfe2f3; --el-table-header-text-color: #dffbff; --el-table-border-color: rgba(0,229,255,.12); background: transparent; color: #dfe2f3; }
:deep(.el-table th.el-table__cell) { background: rgba(10, 18, 32, .96) !important; color: #dffbff; }
:deep(.el-table tr),
:deep(.el-table td.el-table__cell) { background: rgba(8, 13, 24, .72) !important; color: #dfe2f3; }
:deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) { background: rgba(15, 24, 40, .82) !important; }
:deep(.el-table__body tr:hover > td.el-table__cell) { background: rgba(0, 229, 255, .11) !important; }
:deep(.el-input__wrapper), :deep(.el-select__wrapper) { background: rgba(8, 13, 24, .78); box-shadow: 0 0 0 1px rgba(0,229,255,.18) inset; }
:deep(.el-input__inner), :deep(.el-select__placeholder), :deep(.el-select__selected-item) { color: #dfe2f3; }
:deep(.el-drawer) { background: #0b101c; }
@media (max-width: 1180px) {
  .mine-workbench { padding-left: 18px; padding-bottom: 120px; }
  .kpi-grid, .drawer-kpis, .boss-grid, .mini-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .overview-actions { justify-content: flex-start; }
}
</style>

<style>
.fh-tip.el-popper { max-width: 340px; line-height: 1.7; font-size: 13px; }
.mine-backfill-dialog.el-dialog {
  color: #dfe2f3;
  border: 1px solid rgba(0, 229, 255, .22);
  border-radius: 10px;
  background: #0b101c;
  box-shadow: 0 24px 70px rgba(0, 0, 0, .48);
}
.mine-backfill-dialog .el-dialog__title { color: #dffbff; font-weight: 800; }
.mine-backfill-dialog .el-dialog__headerbtn .el-dialog__close { color: #c7d9df; }
.mine-backfill-dialog .el-dialog__body { color: #dfe2f3; }
.mine-backfill-dialog .el-dialog__footer {
  border-top: 1px solid rgba(0, 229, 255, .12);
  background: rgba(8, 13, 24, .82);
}
.mine-backfill-dialog .backfill-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  width: 100%;
}
.mine-backfill-dialog .backfill-footer-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-left: auto;
}
.mine-backfill-dialog .el-button {
  border-color: rgba(0, 229, 255, .28);
  color: #dffbff;
  background: rgba(8, 13, 24, .72);
}
.mine-backfill-dialog .el-button--primary {
  color: #00201a;
  border-color: #68fadd;
  background: #68fadd;
}

/* Top100 弹窗：暗色表格 + 可读 pill，修复双表重叠与白底表头 */
.nat-rank-dialog .el-dialog__body { padding-top: 8px; }
.nat-rank-dialog .dialog-hint { margin-bottom: 12px; color: #9fb3bc; font-size: 13px; }
.nat-rank-dialog .nat-dialog-table {
  width: 100% !important;
  --el-table-bg-color: rgba(6, 14, 26, 0.92);
  --el-table-tr-bg-color: rgba(6, 14, 26, 0.92);
  --el-table-header-bg-color: rgba(0, 229, 255, 0.14);
  --el-table-header-text-color: #9cf0ff;
  --el-table-text-color: #dffbff;
  --el-table-row-hover-bg-color: rgba(0, 229, 255, 0.1);
  --el-table-current-row-bg-color: rgba(0, 229, 255, 0.14);
  --el-table-border-color: rgba(0, 229, 255, 0.16);
  --el-fill-color-lighter: rgba(0, 229, 255, 0.06);
  background: transparent;
}
.nat-rank-dialog .nat-dialog-table .el-table__inner-wrapper::before { background-color: rgba(0, 229, 255, 0.12); }
.nat-rank-dialog .nat-dialog-table th.el-table__cell {
  background: rgba(0, 229, 255, 0.14) !important;
  color: #9cf0ff !important;
  font-weight: 700;
}
.nat-rank-dialog .nat-dialog-table td.el-table__cell {
  background: rgba(6, 14, 26, 0.85) !important;
  color: #dffbff !important;
  border-bottom-color: rgba(0, 229, 255, 0.1) !important;
}
.nat-rank-dialog .nat-dialog-table .el-table__body tr.el-table__row--striped td.el-table__cell {
  background: rgba(0, 229, 255, 0.04) !important;
}
.nat-rank-dialog .nat-dialog-table .el-table__empty-text { color: #8ba0aa; }
.nat-rank-dialog .nat-dialog-pill,
.nat-rank-dialog .nat-dialog-price { color: #c7e8f0; font-size: 12px; }
.nat-rank-dialog .pill.warn.nat-dialog-pill {
  color: #1a1208 !important;
  background: linear-gradient(180deg, #ffd166 0%, #f5a623 100%) !important;
  border: 1px solid rgba(255, 209, 102, 0.65) !important;
  font-weight: 800;
}
.nat-rank-dialog .mover-pct.up { color: #ff7a90; font-weight: 800; }
.nat-rank-dialog .mover-pct.down { color: #5fe3a1; font-weight: 800; }
.nat-rank-dialog .movers-h { margin-bottom: 8px; }
.nat-rank-dialog .nat-dialog-close-btn {
  color: #dffbff !important;
  border-color: rgba(0, 229, 255, 0.35) !important;
  background: rgba(0, 229, 255, 0.1) !important;
}
.nat-rank-dialog .nat-dialog-close-btn:hover {
  color: #fff !important;
  border-color: rgba(103, 232, 249, 0.75) !important;
  background: rgba(0, 229, 255, 0.2) !important;
}
.nat-quality-dialog .quality-action-btns {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: nowrap;
}
.dq-trend {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  margin: 4px 0 10px;
}
.dq-trend-label {
  flex: 0 0 auto;
  color: #94a2b2;
  font-size: 10px;
  line-height: 1;
  padding-bottom: 2px;
}
.dq-trend-bars {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 36px;
  flex: 1 1 auto;
  min-width: 0;
}
.dq-bar {
  flex: 1 1 0;
  min-width: 3px;
  border-radius: 2px 2px 0 0;
  background: #3a8f6f;
  opacity: 0.75;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.15s;
}
.dq-bar:hover { opacity: 1; }
.dq-bar.risk { background: var(--desk-risk, #e45d66); }
.dq-bar.active {
  opacity: 1;
  outline: 1px solid #cfd8e2;
  transform: scaleY(1.04);
}
.zq-spark {
  display: flex;
  align-items: flex-end;
  gap: 1.5px;
  height: 20px;
  margin: 6px 0 2px;
}
.zq-spark-bar {
  flex: 1 1 0;
  min-width: 2px;
  border-radius: 1px;
  background: #3a8f6f;
  opacity: 0.7;
}
.zq-spark-bar.risk { background: var(--desk-risk, #e45d66); }
.nat-quality-dialog .quality-action-btns .el-button.is-link {
  padding: 0 2px;
  font-weight: 700;
}
.nat-quality-dialog .quality-sku-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  line-height: 1.35;
}
.nat-quality-dialog .quality-sku-name {
  color: #dffbff;
  font-weight: 700;
  word-break: break-word;
}
.nat-quality-dialog .quality-sku-meta {
  color: #8ba0aa;
  font-size: 11px;
}
.nat-quality-dialog .quality-sku-query {
  margin-top: 4px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #67e8f9;
  font-size: 11px;
  font-weight: 800;
  cursor: pointer;
}
.nat-quality-dialog .quality-sku-query:hover {
  color: #9cf0ff;
  text-decoration: underline;
}
.nat-quality-dialog .quality-reason-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  line-height: 1.45;
}
.nat-quality-dialog .quality-flag-date {
  display: inline-flex;
  align-self: flex-start;
  padding: 2px 8px;
  border-radius: 999px;
  color: #ffd166;
  background: rgba(255, 209, 102, 0.14);
  border: 1px solid rgba(255, 209, 102, 0.35);
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}
.nat-quality-dialog .quality-flag-reason {
  color: #c7e8f0;
  font-size: 12px;
  word-break: break-word;
}
</style>
