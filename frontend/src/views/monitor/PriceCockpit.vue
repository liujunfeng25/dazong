<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import {
  getZgFilters, getZgIndex, getZgQuality, getZgMap, getZgMovers, getZgSpread,
  getZgForecast, getZgHotSkus, getZgTimeseries, getZgCompare, getZgPrices,
  postZgBriefing, postZgDailyReportJson,
} from '../../api/zgncpjgwAnalytics'
import { COCKPIT_COLORS, glassTooltip, catAxis, valAxis, areaGradient, glowLine } from '../../utils/cockpitEchartsTheme'
import CockpitFx from '../../components/monitor/CockpitFx.vue'
import PanelCard from '../../components/monitor/PanelCard.vue'
import CountUp from '../../components/monitor/CountUp.vue'

const router = useRouter()

// —— 驾驶舱导航轨（替代通用监管端侧栏）——
const railModules = [
  { key: 'overview', code: 'CORE', label: '核心态势' },
  { key: 'price-cockpit', code: 'PRICE', label: '价格驾驶舱' },
  { key: 'mining', code: 'MINE', label: '数据挖掘' },
  { key: 'tianshu', code: 'TS', label: '天枢大屏' },
  { key: 'logistics', code: 'LOG', label: '履约监控' },
  { key: 'beijing-map', code: 'MAP', label: '北京全域' },
  { key: 'broadcast', code: 'CMD', label: '指挥广播' },
  { key: 'alerts', code: 'ALT', label: '预警管理' },
]
const activeRail = 'price-cockpit'
function goModule(key) {
  if (key === activeRail) return
  if (key === 'overview') { router.push('/monitor/dashboard'); return }
  router.push({ path: '/monitor/dashboard', query: { module: key } })
}

// —— 一键全屏 ——
const cockpitRef = ref(null)
const isFullscreen = ref(false)
function fsElement() {
  const d = document
  return d.fullscreenElement || d.webkitFullscreenElement || d.mozFullScreenElement || d.msFullscreenElement || null
}
function toggleFullscreen() {
  const el = cockpitRef.value
  if (!el) return
  if (fsElement()) {
    const exit = document.exitFullscreen || document.webkitExitFullscreen || document.mozCancelFullScreen || document.msExitFullscreen
    exit?.call(document)?.catch?.(() => {})
  } else {
    const req = el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen || el.msRequestFullscreen
    req?.call(el)?.catch?.(() => {})
  }
}
function onFsChange() {
  isFullscreen.value = Boolean(fsElement())
  // 全屏切换后画布尺寸变化，强制重绘各图表
  nextTick(() => setTimeout(() => {
    idxChart?.resize(); mapChart?.resize(); gaugeChart?.resize(); fcChart?.resize(); drawerChart?.resize()
  }, 140))
}

const PROV_FULL = { 北京: '北京市', 天津: '天津市', 上海: '上海市', 重庆: '重庆市', 河北: '河北省', 山西: '山西省', 辽宁: '辽宁省', 吉林: '吉林省', 黑龙江: '黑龙江省', 江苏: '江苏省', 浙江: '浙江省', 安徽: '安徽省', 福建: '福建省', 江西: '江西省', 山东: '山东省', 河南: '河南省', 湖北: '湖北省', 湖南: '湖南省', 广东: '广东省', 海南: '海南省', 四川: '四川省', 贵州: '贵州省', 云南: '云南省', 陕西: '陕西省', 甘肃: '甘肃省', 青海: '青海省', 内蒙古: '内蒙古自治区', 广西: '广西壮族自治区', 西藏: '西藏自治区', 宁夏: '宁夏回族自治区', 新疆: '新疆维吾尔自治区' }

// —— 状态 ——
const clock = ref('')
const idx = reactive({ overall_latest: null, overall_change_pct: null, base_date: '', latest_date: '', dates: [], overall: [], categories: [] })
const quality = reactive({ snapshot_date: '', parse_rate: null, suspicious_skus: null, distinct_skus: null, basket_size: null, basket_coverage: null, freshness_gap_days: null, health_score: null })
const movers = reactive({ gainers: [], losers: [], window: 7, latest_date: '' })
const spread = ref([])
const briefing = ref('')
const decisionBoard = ref({ headline: '', items: [] })
const hotSkus = ref([])
const hotSpark = ref([])

const cateOptions = ref([])
const mapCateId = ref('')
const mapMetric = ref('level')
const mapState = ref({ scope: '', metric: 'level', provinces: [] })
const fcSkuKey = ref('')
const forecast = ref({ status: '', ensemble: [], reliability: '', reliability_label: '', anchor_price: null, message: '' })
const fcHistory = ref({ dates: [], values: [] })
const moverWindow = ref(7)

const mapLoading = ref(false)
const fcLoading = ref(false)
const qualityLoading = ref(false)
const ready = ref(false)
const spot = ref(-1)

// —— 抽屉 ——
const drawerOpen = ref(false)
const drawerLabel = ref('')
const drawerLoading = ref(false)
const drawerStats = ref(null)
const drawerProvinces = ref([])
const drawerForecast = ref({})
const drawerRows = ref([])

// —— 图表实例 ——
const idxRef = ref(null); let idxChart = null
const mapRef = ref(null); let mapChart = null
const gaugeRef = ref(null); let gaugeChart = null
const fcRef = ref(null); let fcChart = null
const drawerChartRef = ref(null); let drawerChart = null
let ro = []
let clockTimer = null, refreshTimer = null, spotTimer = null
let mapSeq = 0, fcSeq = 0, moversSeq = 0

// —— 工具 ——
function tickClock() { clock.value = new Date().toLocaleTimeString('zh-CN', { hour12: false }) }

const fmtPct = (v) => (v == null || isNaN(v) ? '—' : `${v >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`)
const num = (v) => (v == null || v === '' || isNaN(v) ? null : Number(v))

function statsOf(vals) {
  const a = (vals || []).filter((v) => v != null && !isNaN(v)).map(Number)
  if (!a.length) return null
  return { min: Math.min(...a), max: Math.max(...a), avg: +(a.reduce((s, x) => s + x, 0) / a.length).toFixed(2), last: a[a.length - 1] }
}

function sparkline(vals, W = 120, H = 30) {
  const a = (vals || []).filter((v) => v != null && !isNaN(v)).map(Number)
  if (a.length < 2) return { pts: '', up: true }
  const min = Math.min(...a), max = Math.max(...a), span = (max - min) || 1, pad = 2
  const pts = a.map((v, i) => {
    const x = pad + (i / (a.length - 1)) * (W - 2 * pad)
    const y = pad + (1 - (v - min) / span) * (H - 2 * pad)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return { pts, up: a[a.length - 1] >= a[0] }
}

function debounce(fn, ms) {
  let t = null
  const w = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms) }
  w.cancel = () => clearTimeout(t)
  return w
}

// —— 派生 ——
const chgClass = computed(() => ((idx.overall_change_pct || 0) >= 0 ? 'up' : 'down'))
const qualityGrade = computed(() => {
  const s = quality.health_score
  if (s == null) return { label: '—', cls: 'mid' }
  if (s >= 85) return { label: '健康', cls: 'ok' }
  if (s >= 70) return { label: '一般', cls: 'warn' }
  return { label: '需关注', cls: 'risk' }
})
const gradeColor = computed(() => ({ ok: COCKPIT_COLORS.down, warn: COCKPIT_COLORS.warn, risk: COCKPIT_COLORS.up, mid: COCKPIT_COLORS.cyan }[qualityGrade.value.cls]))
const selectedCateName = computed(() => (cateOptions.value.find((c) => c.id === mapCateId.value) || {}).name || mapState.value.scope || '全部')
const mapTitle = computed(() => (mapMetric.value === 'level' ? '全国相对价格热力' : '全国价格周环比热力'))
const fcSkuOptions = computed(() => hotSkus.value.map((h) => ({ value: h.sku_key, label: h.label || h.sku_key })))
const fcLight = computed(() => ({ high: 'ok', mid: 'warn', low: 'risk' }[forecast.value.reliability] || 'warn'))
const fcLightText = computed(() => forecast.value.reliability_label || ({ ok: '高可靠', warn: '中等可靠', risk: '谨慎参考' }[fcLight.value] || '—'))
const fcDay14 = computed(() => { const e = forecast.value.ensemble || []; return e.length ? e[e.length - 1].yhat : null })
const fcOk = computed(() => (forecast.value.ensemble || []).length > 0)
const tickerItems = computed(() => [
  ...movers.gainers.slice(0, 8).map((r) => ({ t: 'up', text: `${r.goods_name} ${fmtPct(r.pct)}` })),
  ...movers.losers.slice(0, 8).map((r) => ({ t: 'down', text: `${r.goods_name} ${fmtPct(r.pct)}` })),
])
const levelClass = (lv) => {
  const s = String(lv || '')
  if (/高|risk|high|急|警/.test(s)) return 'risk'
  if (/中|mid|warn|关注/.test(s)) return 'warn'
  return 'ok'
}

// —— 地图 geojson ——
async function ensureChinaMap() {
  if (echarts.getMap && echarts.getMap('china')) return true
  try {
    const resp = await fetch('https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json', { cache: 'force-cache' })
    echarts.registerMap('china', await resp.json())
    return true
  } catch (e) { console.error('[cockpit] geojson failed', e); return false }
}

// —— 渲染 ——
function renderIndex() {
  if (!idxRef.value) return
  if (!idxChart) idxChart = echarts.init(idxRef.value)
  idxChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', ...glassTooltip },
    grid: { left: 38, right: 12, top: 12, bottom: 22 },
    xAxis: catAxis(idx.dates),
    yAxis: valAxis(),
    series: [{ type: 'line', smooth: true, showSymbol: false, data: idx.overall, lineStyle: glowLine(COCKPIT_COLORS.cyanCore, 2.6), areaStyle: { color: areaGradient(COCKPIT_COLORS.cyanCore, 0.26, 0.01) } }],
  }, true)
  idxChart.resize()
}

function renderGauge() {
  if (!gaugeRef.value) return
  if (!gaugeChart) gaugeChart = echarts.init(gaugeRef.value)
  const score = num(quality.health_score)
  gaugeChart.setOption({
    backgroundColor: 'transparent',
    series: [{
      type: 'gauge', min: 0, max: 100, radius: '100%', center: ['50%', '64%'],
      startAngle: 210, endAngle: -30,
      progress: { show: true, width: 9, roundCap: true, itemStyle: { color: gradeColor.value, shadowColor: gradeColor.value, shadowBlur: 12 } },
      axisLine: { lineStyle: { width: 9, color: [[1, 'rgba(255,255,255,.08)']] } },
      axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false }, pointer: { show: false }, anchor: { show: false },
      title: { show: false },
      detail: { valueAnimation: true, offsetCenter: [0, '2%'], fontSize: 32, fontWeight: 800, fontFamily: 'JetBrains Mono, monospace', color: gradeColor.value, formatter: score == null ? '—' : '{value}' },
      data: [{ value: score == null ? 0 : score }],
    }],
  }, true)
  gaugeChart.resize()
}

function renderMap() {
  if (!mapRef.value || !(echarts.getMap && echarts.getMap('china'))) return
  if (!mapChart) mapChart = echarts.init(mapRef.value)
  const isChg = mapMetric.value === 'chg7'
  const provs = (mapState.value.provinces || []).map((p) => ({ name: PROV_FULL[p.name] || p.name, value: num(p.value), short: p.name }))
  const vals = provs.map((d) => d.value).filter((v) => v != null)
  let visualMap
  if (isChg) {
    const m = Math.max(1, ...vals.map((v) => Math.abs(v)))
    visualMap = { min: -m, max: m, left: 14, bottom: 14, calculable: true, precision: 1, textStyle: { color: '#9fb3bc' }, inRange: { color: ['#5fe3a1', '#1f6f6a', '#0b1322', '#7a5224', '#ff7a90'] } }
  } else {
    const min = vals.length ? Math.min(...vals) : 0, max = vals.length ? Math.max(...vals) : 100
    visualMap = { min, max, left: 14, bottom: 14, calculable: true, textStyle: { color: '#9fb3bc' }, inRange: { color: ['#0b3a45', '#0f7a8c', '#00e5ff', '#ffcc66', '#ff7a90'] } }
  }
  mapChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item', ...glassTooltip,
      formatter: (p) => `${p.data?.short || p.name}<br/>${isChg ? '周环比' : '相对价格指数'}：${p.value == null || isNaN(p.value) ? '—' : (isChg ? fmtPct(p.value) : p.value)}`,
    },
    visualMap,
    series: [{
      type: 'map', map: 'china', roam: false, data: provs, label: { show: false },
      emphasis: { label: { show: true, color: '#fff' }, itemStyle: { areaColor: '#1a6b7a' } },
      itemStyle: { areaColor: 'rgba(16,26,44,.7)', borderColor: 'rgba(92,239,255,.28)' },
    }],
  }, true)
  mapChart.resize()
}

function renderForecast() {
  if (!fcRef.value) return
  if (!fcChart) fcChart = echarts.init(fcRef.value)
  const hDates = fcHistory.value.dates || []
  const hVals = fcHistory.value.values || []
  const ens = forecast.value.ensemble || []
  const fDates = ens.map((r) => r.date)
  const anchorIdx = hDates.length - 1
  const actual = [...hVals, ...fDates.map(() => null)]
  const lastActual = hVals.length ? hVals[hVals.length - 1] : (ens[0]?.yhat ?? null)
  const forecastLine = hDates.map((_, i) => (i === anchorIdx ? lastActual : null)).concat(ens.map((r) => r.yhat))
  const lower = hDates.map(() => null).concat(ens.map((r) => r.yhat_lower))
  const bandRange = hDates.map(() => null).concat(ens.map((r) => Number(((r.yhat_upper ?? 0) - (r.yhat_lower ?? 0)).toFixed(4))))
  const allDates = [...hDates, ...fDates]
  fcChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', ...glassTooltip },
    legend: { data: ['历史实价', '预测'], top: 2, right: 6, textStyle: { color: '#aebfc8', fontSize: 11 }, itemWidth: 14, itemHeight: 8 },
    grid: { left: 46, right: 16, top: 30, bottom: 34 },
    xAxis: catAxis(allDates, { axisLabel: { color: '#8aa0ab', fontSize: 9, rotate: 26 } }),
    yAxis: valAxis({ name: '元/斤', nameTextStyle: { color: '#8aa0ab', fontSize: 10 } }),
    series: [
      { name: '_lower', type: 'line', stack: 'conf', data: lower, lineStyle: { opacity: 0 }, symbol: 'none', silent: true, tooltip: { show: false } },
      { name: '置信区间', type: 'line', stack: 'conf', data: bandRange, lineStyle: { opacity: 0 }, symbol: 'none', areaStyle: { color: 'rgba(129,140,248,.20)' }, tooltip: { show: false } },
      { name: '历史实价', type: 'line', smooth: true, data: actual, showSymbol: false, lineStyle: glowLine(COCKPIT_COLORS.cyanCore, 3), areaStyle: { color: areaGradient(COCKPIT_COLORS.cyanCore, 0.12, 0) } },
      { name: '预测', type: 'line', smooth: true, data: forecastLine, showSymbol: false, lineStyle: { color: COCKPIT_COLORS.warn, width: 3, type: 'dashed' }, markLine: anchorIdx >= 0 ? { silent: true, symbol: 'none', lineStyle: { color: 'rgba(255,209,102,.5)', type: 'dotted' }, data: [{ xAxis: anchorIdx, label: { formatter: '今', color: '#ffd166', position: 'insideEndTop' } }] } : undefined },
    ],
  }, true)
  fcChart.resize()
  requestAnimationFrame(() => fcChart?.resize())
  setTimeout(() => fcChart?.resize(), 120)
}

// —— 加载 ——
async function loadMap() {
  const seq = ++mapSeq
  mapLoading.value = true
  try {
    const m = await getZgMap({ cate_id: mapCateId.value || '', metric: mapMetric.value }).catch(() => ({ provinces: [] }))
    if (seq !== mapSeq) return
    mapState.value = m || { provinces: [] }
    await nextTick(); renderMap()
  } finally { if (seq === mapSeq) mapLoading.value = false }
}

async function loadForecast() {
  const key = fcSkuKey.value
  if (!key) { forecast.value = { status: 'empty', ensemble: [], message: '请选择 SKU' }; fcHistory.value = { dates: [], values: [] }; await nextTick(); renderForecast(); return }
  const seq = ++fcSeq
  fcLoading.value = true
  try {
    const [fc, ts] = await Promise.all([
      getZgForecast({ sku_key: key, days: 14 }).catch(() => ({ status: 'failed', ensemble: [], message: '预测加载失败' })),
      getZgTimeseries({ sku_keys: [key], days: 30 }).catch(() => ({ dates: [], series: [] })),
    ])
    if (seq !== fcSeq) return
    forecast.value = fc || { status: 'empty', ensemble: [] }
    const ser = ts?.series?.[0]
    fcHistory.value = { dates: (ts?.dates || []).slice(-30), values: (ser?.values || []).slice(-30) }
    await nextTick(); renderForecast()
  } finally { if (seq === fcSeq) fcLoading.value = false }
}

async function loadMovers() {
  const seq = ++moversSeq
  const mv = await getZgMovers({ window: moverWindow.value, limit: 12 }).catch(() => ({}))
  if (seq !== moversSeq) return
  Object.assign(movers, { gainers: mv?.gainers || [], losers: mv?.losers || [], window: mv?.window || moverWindow.value, latest_date: mv?.latest_date || '' })
}

async function loadHotStrip() {
  const keys = hotSkus.value.map((h) => h.sku_key).filter(Boolean).slice(0, 8)
  if (!keys.length) { hotSpark.value = []; return }
  const ts = await getZgTimeseries({ sku_keys: keys, days: 30 }).catch(() => ({ series: [] }))
  const series = ts?.series || []
  hotSpark.value = hotSkus.value.slice(0, 8).map((h, i) => {
    const ser = series[i] || series.find((s) => s.name === h.label) || {}
    const sp = sparkline(ser.values)
    return { sku_key: h.sku_key, label: h.label || h.sku_key, pts: sp.pts, up: sp.up }
  })
}

async function loadCore() {
  qualityLoading.value = true
  const [filters, indexRes, q, mv, sp, hot] = await Promise.all([
    getZgFilters().catch(() => ({})),
    getZgIndex().catch(() => ({})),
    getZgQuality().catch(() => ({})),
    getZgMovers({ window: moverWindow.value, limit: 12 }).catch(() => ({})),
    getZgSpread({ limit: 12 }).catch(() => ({})),
    getZgHotSkus().catch(() => ({})),
  ])
  cateOptions.value = filters?.categories || []
  Object.assign(idx, indexRes || {})
  Object.assign(quality, q || {})
  Object.assign(movers, { gainers: mv?.gainers || [], losers: mv?.losers || [], window: mv?.window || moverWindow.value, latest_date: mv?.latest_date || '' })
  spread.value = sp?.rows || []
  const hotList = [...(hot?.configured || []).filter((x) => x.enabled !== false), ...(hot?.recommended || [])]
  const seen = new Set()
  hotSkus.value = hotList.filter((h) => h && h.sku_key && !seen.has(h.sku_key) && seen.add(h.sku_key)).slice(0, 10)
  qualityLoading.value = false
  if (!mapCateId.value && cateOptions.value.length) mapCateId.value = cateOptions.value[0].id
  if (!fcSkuKey.value && hotSkus.value.length) fcSkuKey.value = hotSkus.value[0].sku_key
  await ensureChinaMap()
  await nextTick()
  renderIndex(); renderGauge()
  await Promise.all([loadMap(), loadForecast(), loadHotStrip()])
  // 脱链尽力而为（依赖 LLM/VPN，失败不影响整屏）
  postZgBriefing().then((r) => { briefing.value = r?.briefing || '' }).catch(() => {})
  postZgDailyReportJson({ report_date: idx.latest_date || '' }).then((r) => { decisionBoard.value = r?.decision_board || { headline: '', items: [] } }).catch(() => {})
}

// —— 抽屉 ——
async function openDrawer(skuKey, label) {
  if (!skuKey) return
  drawerLabel.value = label || skuKey
  drawerOpen.value = true
  drawerLoading.value = true
  drawerStats.value = null; drawerProvinces.value = []; drawerForecast.value = {}; drawerRows.value = []
  try {
    const [ts, cmp, fc, pr] = await Promise.all([
      getZgTimeseries({ sku_keys: [skuKey], days: 60 }).catch(() => ({ dates: [], series: [] })),
      getZgCompare({ sku_key: skuKey }).catch(() => ({ labels: [], values: [] })),
      getZgForecast({ sku_key: skuKey, days: 14 }).catch(() => ({ status: 'failed' })),
      getZgPrices({ sku_key: skuKey, page: 1, page_size: 12 }).catch(() => ({ rows: [] })),
    ])
    const series = ts?.series?.[0]
    drawerStats.value = statsOf(series?.values)
    drawerProvinces.value = (cmp?.labels || []).map((n, i) => ({ name: n, value: num(cmp.values?.[i]) })).filter((p) => p.value != null).sort((a, b) => b.value - a.value)
    drawerForecast.value = fc || {}
    drawerRows.value = pr?.rows || []
    await nextTick()
    if (drawerChartRef.value) {
      if (!drawerChart) drawerChart = echarts.init(drawerChartRef.value)
      drawerChart.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis', ...glassTooltip },
        grid: { left: 44, right: 14, top: 14, bottom: 28 },
        xAxis: catAxis(ts?.dates || [], { axisLabel: { color: '#8aa0ab', fontSize: 9, rotate: 24 } }),
        yAxis: valAxis(),
        series: [{ type: 'line', smooth: true, showSymbol: false, data: series?.values || [], lineStyle: glowLine(COCKPIT_COLORS.cyanCore, 2.4), areaStyle: { color: areaGradient(COCKPIT_COLORS.cyanCore, 0.16, 0) } }],
      }, true)
      drawerChart.resize()
      requestAnimationFrame(() => drawerChart?.resize())
      setTimeout(() => drawerChart?.resize(), 120)
    }
  } finally { drawerLoading.value = false }
}
function onDrawerClosed() { drawerChart?.dispose(); drawerChart = null }
const drawerProvMax = computed(() => Math.max(1, ...drawerProvinces.value.map((p) => p.value || 0)))

// —— 联动监听（首屏加载后才生效）——
const debouncedMap = debounce(loadMap, 250)
const debouncedFc = debounce(loadForecast, 250)
const debouncedMovers = debounce(loadMovers, 250)
watch([mapCateId, mapMetric], () => { if (ready.value) debouncedMap() })
watch(fcSkuKey, () => { if (ready.value) debouncedFc() })
watch(moverWindow, () => { if (ready.value) debouncedMovers() })

// —— resize ——
function bindResize() {
  ro.forEach((o) => o.disconnect()); ro = []
  ;[[idxRef, () => idxChart], [mapRef, () => mapChart], [gaugeRef, () => gaugeChart], [fcRef, () => fcChart]].forEach(([r, getC]) => {
    if (r.value) { const o = new ResizeObserver(() => getC()?.resize()); o.observe(r.value); ro.push(o) }
  })
}

onMounted(async () => {
  tickClock(); clockTimer = setInterval(tickClock, 1000)
  document.addEventListener('fullscreenchange', onFsChange)
  document.addEventListener('webkitfullscreenchange', onFsChange)
  await loadCore()
  ready.value = true
  bindResize()
  refreshTimer = setInterval(loadCore, 120000)
  spotTimer = setInterval(() => { spot.value = (spot.value + 1) % 8 }, 8000)
})
onBeforeUnmount(() => {
  clearInterval(clockTimer); clearInterval(refreshTimer); clearInterval(spotTimer)
  document.removeEventListener('fullscreenchange', onFsChange)
  document.removeEventListener('webkitfullscreenchange', onFsChange)
  debouncedMap.cancel(); debouncedFc.cancel(); debouncedMovers.cancel()
  ro.forEach((o) => o.disconnect())
  idxChart?.dispose(); mapChart?.dispose(); gaugeChart?.dispose(); fcChart?.dispose(); drawerChart?.dispose()
})
</script>

<template>
  <section ref="cockpitRef" class="cockpit">
    <CockpitFx />

    <!-- 驾驶舱导航轨：默认收起，悬停展开 -->
    <nav class="ck-rail" aria-label="监管模块切换">
      <button
        v-for="m in railModules"
        :key="m.key"
        type="button"
        :class="{ active: m.key === activeRail }"
        :title="m.label"
        @click="goModule(m.key)"
      >
        <span>{{ m.code }}</span>
        <strong>{{ m.label }}</strong>
      </button>
    </nav>

    <div class="ck-inner">
      <!-- 顶部条 -->
      <header class="ck-head">
        <div class="ck-brand">
          <p class="ck-eyebrow"><i class="ck-live"></i>DAZONG · NATIONAL PRICE INTELLIGENCE COCKPIT</p>
          <h1>全国农产品价格驾驶舱</h1>
        </div>
        <div class="ck-headright">
          <div class="ck-clock">
            <span class="ck-clock-time">{{ clock }}</span>
            <span class="ck-clock-meta">{{ idx.latest_date ? `数据日 ${idx.latest_date}` : '实时监控' }}</span>
          </div>
          <button class="ck-fs" :title="isFullscreen ? '退出全屏' : '一键全屏'" @click="toggleFullscreen">
            <span class="ck-fs-icon">{{ isFullscreen ? '⛶' : '⛶' }}</span>{{ isFullscreen ? '退出全屏' : '全屏' }}
          </button>
          <button class="ck-back" @click="router.push('/monitor/dashboard?module=mining')">⟵ 返回</button>
        </div>
      </header>

      <!-- 三列网格 -->
      <div class="ck-grid">
        <!-- 左列 -->
        <div class="ck-col">
          <PanelCard class="p-auto" :index="0" :spotlight="spot === 0"
            eyebrow="NATIONAL PRICE INDEX" :title="`全国总指数 · 基期 ${idx.base_date || '—'}=100`">
            <div class="ck-index-head">
              <CountUp class="ck-bignum" :class="chgClass" :value="idx.overall_latest" :decimals="2" />
              <span class="ck-chg" :class="chgClass">
                {{ (idx.overall_change_pct || 0) >= 0 ? '▲' : '▼' }} {{ idx.overall_change_pct == null ? '—' : Math.abs(idx.overall_change_pct) + '%' }}
                <em>较基期</em>
              </span>
            </div>
            <div ref="idxRef" class="ck-index-chart"></div>
          </PanelCard>

          <PanelCard class="p-auto" :index="1" :spotlight="spot === 1" :loading="qualityLoading"
            eyebrow="DATA CREDIBILITY" title="数据可信度">
            <div class="ck-gauge-wrap">
              <div ref="gaugeRef" class="ck-gauge"></div>
              <span class="ck-grade-pill" :class="qualityGrade.cls">{{ qualityGrade.label }}</span>
            </div>
            <div class="ck-qmetrics">
              <div><span>价格解析率</span><strong>{{ quality.parse_rate == null ? '—' : quality.parse_rate + '%' }}</strong></div>
              <div><span>疑似脏数据</span><strong>{{ quality.suspicious_skus ?? '—' }}<em v-if="quality.distinct_skus">/{{ quality.distinct_skus }}</em></strong></div>
              <div><span>指数篮覆盖</span><strong>{{ quality.basket_coverage == null ? '—' : quality.basket_coverage + '%' }}</strong></div>
              <div><span>数据新鲜度</span><strong>{{ quality.freshness_gap_days == null ? '—' : (quality.freshness_gap_days <= 1 ? '新鲜' : quality.freshness_gap_days + ' 天前') }}</strong></div>
            </div>
          </PanelCard>

          <PanelCard class="p-1" :index="2" :spotlight="spot === 2"
            eyebrow="CATEGORY INDEX" title="分类指数走势">
            <div class="ck-catlist">
              <div v-for="c in (idx.categories || [])" :key="c.cate_id" class="ck-cat-row">
                <span class="ck-cat-name">{{ c.cate_name }}</span>
                <svg class="ck-cat-spark" viewBox="0 0 120 30" preserveAspectRatio="none">
                  <polyline :points="sparkline(c.series).pts" fill="none"
                    :stroke="sparkline(c.series).up ? COCKPIT_COLORS.up : COCKPIT_COLORS.down" stroke-width="1.6" />
                </svg>
                <strong class="ck-cat-val" :class="(c.change_pct || 0) >= 0 ? 'up' : 'down'">{{ c.latest }}</strong>
              </div>
              <div v-if="!(idx.categories || []).length" class="ck-empty">暂无分类数据</div>
            </div>
          </PanelCard>
        </div>

        <!-- 中列 -->
        <div class="ck-col ck-col-center">
          <PanelCard class="p-bigmap" :index="3" :spotlight="spot === 3" :loading="mapLoading"
            eyebrow="GEO HEATMAP" :title="mapTitle">
            <template #header>
              <el-select v-model="mapCateId" size="small" class="ck-sel ck-sel-cate" placeholder="分类">
                <el-option v-for="c in cateOptions" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
              <div class="seg">
                <button :class="{ active: mapMetric === 'level' }" @click="mapMetric = 'level'">相对价格</button>
                <button :class="{ active: mapMetric === 'chg7' }" @click="mapMetric = 'chg7'">周环比</button>
              </div>
            </template>
            <div class="ck-map-wrap">
              <div ref="mapRef" class="ck-map-chart"></div>
              <div class="ck-map-sweep"></div>
              <span class="ck-map-scope">{{ selectedCateName }} · {{ mapMetric === 'level' ? '>100 偏贵' : '红涨绿跌' }}</span>
              <div v-if="!mapLoading && !(mapState.provinces || []).length" class="ck-empty ck-map-empty">该口径暂无分省数据</div>
            </div>
          </PanelCard>

          <PanelCard class="p-fc" :index="4" :spotlight="spot === 4" :loading="fcLoading"
            eyebrow="AI FORECAST · 14D" title="AI 价格预测">
            <template #header>
              <span class="ck-light" :class="fcLight"><i></i>{{ fcLightText }}</span>
              <el-select v-model="fcSkuKey" size="small" filterable class="ck-sel ck-sel-sku" placeholder="选择 SKU">
                <el-option v-for="o in fcSkuOptions" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </template>
            <div class="ck-fc-body">
              <div v-show="fcOk" ref="fcRef" class="ck-fc-chart"></div>
              <div v-if="!fcLoading && !fcOk" class="ck-empty ck-fc-empty">{{ forecast.message || '暂无可用预测（样本不足或未训练）' }}</div>
              <div class="ck-fc-tiles" v-if="fcOk">
                <div><span>锚定现价</span><strong>{{ forecast.anchor_price ?? '—' }}</strong></div>
                <div><span>14日预测</span><strong class="hl">{{ fcDay14 == null ? '—' : Number(fcDay14).toFixed(2) }}</strong></div>
                <div><span>可靠度</span><strong :class="fcLight">{{ fcLightText }}</strong></div>
              </div>
            </div>
          </PanelCard>
        </div>

        <!-- 右列 -->
        <div class="ck-col">
          <PanelCard class="p-1" :index="5" :spotlight="spot === 5"
            eyebrow="PRICE MOVERS" :title="`价格异动 · 近 ${moverWindow} 日`">
            <template #header>
              <div class="seg">
                <button v-for="w in [7, 14, 30]" :key="w" :class="{ active: moverWindow === w }" @click="moverWindow = w">{{ w }}日</button>
              </div>
            </template>
            <div class="ck-rows">
              <div v-for="(r, i) in movers.gainers.slice(0, 6)" :key="'g' + i" class="ck-row clickable" @click="openDrawer(r.sku_key, r.goods_name)">
                <span class="rk up">↑</span><span class="nm">{{ r.goods_name }}</span><span class="up">{{ fmtPct(r.pct) }}</span>
              </div>
              <div v-for="(r, i) in movers.losers.slice(0, 6)" :key="'l' + i" class="ck-row clickable" @click="openDrawer(r.sku_key, r.goods_name)">
                <span class="rk down">↓</span><span class="nm">{{ r.goods_name }}</span><span class="down">{{ fmtPct(r.pct) }}</span>
              </div>
              <div v-if="!movers.gainers.length && !movers.losers.length" class="ck-empty">暂无异动数据</div>
            </div>
          </PanelCard>

          <PanelCard class="p-1" :index="6" :spotlight="spot === 6"
            eyebrow="ARBITRAGE" title="区域价差套利 TOP">
            <div class="ck-rows">
              <div v-for="(r, i) in spread.slice(0, 6)" :key="i" class="ck-row clickable" @click="openDrawer(r.sku_key, r.goods_name)">
                <span class="nm">{{ r.goods_name }}</span>
                <span v-if="r.cheapest && r.priciest" class="ck-route">{{ r.cheapest }}→{{ r.priciest }}</span>
                <span class="warn">{{ r.spread_pct }}%</span>
              </div>
              <div v-if="!spread.length" class="ck-empty">暂无价差数据</div>
            </div>
          </PanelCard>

          <PanelCard class="p-1" :index="7" :spotlight="spot === 7"
            eyebrow="DECISION BOARD" title="智能决策看板">
            <div class="ck-decision">
              <p v-if="decisionBoard.headline" class="ck-dec-head">{{ decisionBoard.headline }}</p>
              <div v-for="(it, i) in (decisionBoard.items || []).slice(0, 4)" :key="i" class="ck-dec-item" :class="levelClass(it.level)">
                <div class="ck-dec-top"><i class="ck-dec-dot"></i><strong>{{ it.title }}</strong></div>
                <p v-if="it.action" class="ck-dec-act">{{ it.action }}</p>
              </div>
              <div v-if="!(decisionBoard.items || []).length" class="ck-empty">决策看板生成中（依赖 AI，需联网）</div>
            </div>
          </PanelCard>
        </div>
      </div>

      <!-- 底部：异动跑马灯 + 热门 SKU 走势条 + AI 播报 -->
      <div class="ck-foot">
        <div class="ck-ticker">
          <span class="ck-ticker-tag">异动</span>
          <div class="ck-ticker-track">
            <span v-for="(it, i) in tickerItems" :key="i" :class="it.t">{{ it.text }}</span>
            <span v-for="(it, i) in tickerItems" :key="'b' + i" :class="it.t">{{ it.text }}</span>
            <span v-if="!tickerItems.length" class="up">实时行情加载中…</span>
          </div>
        </div>
        <div class="ck-hotstrip" v-if="hotSpark.length">
          <span class="ck-hot-label">热门 SKU</span>
          <button v-for="h in hotSpark" :key="h.sku_key" class="ck-hot" @click="openDrawer(h.sku_key, h.label)">
            <span class="ck-hot-name">{{ h.label }}</span>
            <svg class="ck-hot-spark" viewBox="0 0 120 30" preserveAspectRatio="none">
              <polyline :points="h.pts" fill="none" :stroke="h.up ? COCKPIT_COLORS.up : COCKPIT_COLORS.down" stroke-width="1.8" />
            </svg>
          </button>
        </div>
      </div>
      <div class="ck-brief" v-if="briefing">🧠 {{ briefing }}</div>
    </div>

    <!-- 下钻抽屉 -->
    <el-drawer v-model="drawerOpen" :with-header="false" size="460px" @closed="onDrawerClosed">
      <div class="ck-drawer" v-loading="drawerLoading" element-loading-background="rgba(5,10,20,.7)">
        <div class="ckd-head">
          <div>
            <p class="ck-eyebrow">SKU DRILL-DOWN</p>
            <h2>{{ drawerLabel }}</h2>
          </div>
          <button class="ckd-close" @click="drawerOpen = false">✕</button>
        </div>

        <div class="ckd-stats" v-if="drawerStats">
          <div><span>最新</span><strong>{{ drawerStats.last }}</strong></div>
          <div><span>均价</span><strong>{{ drawerStats.avg }}</strong></div>
          <div><span>最高</span><strong class="up">{{ drawerStats.max }}</strong></div>
          <div><span>最低</span><strong class="down">{{ drawerStats.min }}</strong></div>
        </div>

        <p class="ckd-title">价格走势（60 日）</p>
        <div ref="drawerChartRef" class="ckd-chart"></div>

        <div class="ckd-fc" v-if="(drawerForecast.ensemble || []).length">
          <p class="ckd-title">AI 预测</p>
          <div class="ckd-fc-row">
            <div><span>锚定现价</span><strong>{{ drawerForecast.anchor_price ?? '—' }}</strong></div>
            <div><span>14日预测</span><strong class="hl">{{ Number(drawerForecast.ensemble[drawerForecast.ensemble.length - 1].yhat).toFixed(2) }}</strong></div>
            <div><span>可靠度</span><strong>{{ drawerForecast.reliability_label || '—' }}</strong></div>
          </div>
        </div>

        <div class="ckd-prov" v-if="drawerProvinces.length">
          <p class="ckd-title">分省价格</p>
          <div v-for="p in drawerProvinces.slice(0, 8)" :key="p.name" class="ckd-prov-row">
            <span class="ckd-prov-name">{{ p.name }}</span>
            <div class="ckd-prov-bar"><i :style="{ width: ((p.value / drawerProvMax) * 100) + '%' }"></i></div>
            <strong>{{ p.value }}</strong>
          </div>
        </div>

        <div class="ckd-rows" v-if="drawerRows.length">
          <p class="ckd-title">最新报价明细</p>
          <div v-for="(r, i) in drawerRows.slice(0, 10)" :key="i" class="ckd-detail-row">
            <span>{{ r.date || r.price_date || '—' }}</span>
            <span class="ckd-dim">{{ r.district_name || r.district || r.area || '' }}</span>
            <strong>{{ r.price ?? '—' }}<em v-if="r.unit"> {{ r.unit }}</em></strong>
          </div>
        </div>
      </div>
    </el-drawer>
  </section>
</template>

<style scoped>
.cockpit {
  position: relative;
  height: 100vh;
  box-sizing: border-box;
  color: #dfe2f3;
  overflow: hidden;
  font-family: "Space Grotesk", Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
  background:
    radial-gradient(circle at 72% 4%, rgba(56, 189, 248, .14), transparent 42%),
    radial-gradient(circle at 8% 96%, rgba(129, 140, 248, .1), transparent 40%),
    linear-gradient(180deg, #060a14 0%, #0a1322 60%, #081020 100%);
}
.ck-inner { position: relative; z-index: 1; height: 100%; display: flex; flex-direction: column; box-sizing: border-box; padding: 16px 20px 12px 30px; }

/* 驾驶舱导航轨（替代通用监管端侧栏，悬停展开） */
.ck-rail {
  position: fixed; left: 0; top: 0; bottom: 0; z-index: 40;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px;
  width: 16px; padding: 18px 0;
  border-right: 1px solid rgba(92, 239, 255, .12);
  background: rgba(6, 12, 22, .25);
  overflow: visible;
  transition: width 180ms ease, background 180ms ease, border-color 180ms ease;
}
.ck-rail::before {
  content: ""; position: absolute; left: 5px; top: 50%; width: 4px; height: 48px; transform: translateY(-50%);
  border-radius: 999px; background: linear-gradient(180deg, rgba(92, 239, 255, .55), rgba(129, 140, 248, .45));
  opacity: .7; transition: opacity 180ms ease;
}
.ck-rail:hover, .ck-rail:focus-within { width: 118px; background: rgba(8, 16, 28, .86); border-color: rgba(92, 239, 255, .28); backdrop-filter: blur(14px); }
.ck-rail:hover::before, .ck-rail:focus-within::before { opacity: 0; }
.ck-rail button {
  width: 94px; min-height: 58px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 5px; padding: 6px;
  border: 1px solid rgba(92, 239, 255, .16); border-radius: 9px; color: #bac9cc; background: rgba(10, 18, 30, .72);
  cursor: pointer; opacity: 0; pointer-events: none; transform: translateX(-24px);
  transition: opacity 180ms ease, transform 180ms ease, border-color 180ms ease, background 180ms ease;
}
.ck-rail:hover button, .ck-rail:focus-within button { opacity: 1; pointer-events: auto; transform: translateX(0); }
.ck-rail button span { width: 46px; height: 24px; display: grid; place-items: center; color: #00201a; font: 800 10px/1 "JetBrains Mono", monospace; background: #68fadd; border-radius: 5px; }
.ck-rail button strong { width: 100%; overflow: hidden; text-align: center; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; font-weight: 700; }
.ck-rail button:hover { border-color: rgba(92, 239, 255, .4); background: rgba(92, 239, 255, .1); color: #dfe9f5; }
.ck-rail button.active { color: #dffbff; border-color: rgba(92, 239, 255, .62); background: rgba(92, 239, 255, .14); box-shadow: 0 0 18px rgba(92, 239, 255, .22); }
.ck-rail button.active span { background: #00e5ff; }

/* 顶部 */
.ck-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.ck-eyebrow { display: inline-flex; align-items: center; gap: 7px; margin: 0 0 4px; color: rgba(92, 239, 255, .7); font: 800 11px/1 "JetBrains Mono", monospace; letter-spacing: .16em; }
.ck-live { width: 8px; height: 8px; border-radius: 50%; background: #5ef0c8; box-shadow: 0 0 0 0 rgba(94, 240, 200, .6); animation: ckLive 1.8s ease-out infinite; }
@keyframes ckLive { 0% { box-shadow: 0 0 0 0 rgba(94, 240, 200, .55); } 70% { box-shadow: 0 0 0 7px rgba(94, 240, 200, 0); } 100% { box-shadow: 0 0 0 0 rgba(94, 240, 200, 0); } }
.ck-brand h1 {
  margin: 0; font-size: clamp(24px, 2.3vw, 36px); font-weight: 800; letter-spacing: .04em; line-height: 1.05;
  background: linear-gradient(110deg, #eafcff 0%, #7fe9ff 50%, #818cf8 110%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
  filter: drop-shadow(0 0 22px rgba(92, 239, 255, .3));
}
.ck-headright { display: flex; align-items: center; gap: 16px; }
.ck-clock { text-align: right; }
.ck-clock-time { display: block; font: 800 clamp(20px, 1.8vw, 28px)/1 "JetBrains Mono", monospace; color: #aef3ff; letter-spacing: .04em; text-shadow: 0 0 16px rgba(92, 239, 255, .4); }
.ck-clock-meta { display: block; margin-top: 4px; color: #7f939c; font-size: 11px; font-family: "JetBrains Mono", monospace; }
.ck-back, .ck-fs { border: 1px solid rgba(92, 239, 255, .35); color: #cdf6ff; background: rgba(92, 239, 255, .08); border-radius: 9px; padding: 9px 16px; cursor: pointer; font-weight: 700; font-size: 13px; transition: all .15s; }
.ck-back:hover, .ck-fs:hover { background: rgba(92, 239, 255, .2); box-shadow: 0 0 18px -4px rgba(92, 239, 255, .5); }
.ck-fs { display: inline-flex; align-items: center; gap: 6px; padding: 9px 14px; }
.ck-fs-icon { font-size: 15px; line-height: 1; }

/* 网格 */
.ck-grid { flex: 1 1 auto; min-height: 0; display: flex; gap: 14px; }
.ck-col { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px; min-height: 0; }
.ck-col-center { flex: 2; }
.p-auto { flex: 0 0 auto; }
.p-1 { flex: 1 1 0; min-height: 0; }
.p-bigmap { flex: 1.75 1 0; min-height: 0; }
.p-fc { flex: 1 1 0; min-height: 0; }

/* 总指数 */
.ck-index-head { display: flex; align-items: baseline; gap: 12px; }
.ck-bignum { font: 800 clamp(34px, 3vw, 50px)/1 "JetBrains Mono", monospace; color: #00e5ff; text-shadow: 0 0 22px rgba(0, 229, 255, .45); }
.ck-bignum.down { color: #5fe3a1; text-shadow: 0 0 22px rgba(95, 227, 161, .4); }
.ck-chg { font-weight: 800; font-size: 14px; color: #ff7a90; } .ck-chg.down { color: #5fe3a1; }
.ck-chg em { font-style: normal; color: #7f939c; font-weight: 600; font-size: 11px; margin-left: 4px; }
.ck-index-chart { height: clamp(96px, 11vh, 140px); margin-top: 6px; }

/* 可信度 */
.ck-gauge-wrap { position: relative; }
.ck-gauge { height: clamp(120px, 14vh, 158px); }
.ck-grade-pill { position: absolute; top: 4px; right: 0; padding: 3px 11px; border-radius: 999px; font-size: 12px; font-weight: 800; }
.ck-grade-pill.ok { color: #b7ffe7; background: rgba(38, 166, 113, .22); border: 1px solid rgba(95, 227, 161, .4); }
.ck-grade-pill.warn { color: #ffe7ad; background: rgba(255, 184, 77, .2); border: 1px solid rgba(255, 204, 102, .4); }
.ck-grade-pill.risk { color: #ffc8d2; background: rgba(255, 83, 112, .18); border: 1px solid rgba(255, 122, 144, .4); }
.ck-grade-pill.mid { color: #bdf1ff; background: rgba(92, 239, 255, .15); border: 1px solid rgba(92, 239, 255, .35); }
.ck-qmetrics { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 4px; }
.ck-qmetrics > div { padding: 7px 10px; border: 1px solid rgba(92, 239, 255, .12); border-radius: 8px; background: rgba(2, 10, 20, .45); }
.ck-qmetrics span { display: block; color: #8ba0aa; font-size: 11px; }
.ck-qmetrics strong { color: #dffbff; font-size: 16px; font-weight: 800; font-family: "JetBrains Mono", monospace; }
.ck-qmetrics em { font-style: normal; color: #7f939c; font-size: 11px; }

/* 分类走势 */
.ck-catlist { flex: 1 1 auto; overflow: auto; min-height: 0; }
.ck-cat-row { display: grid; grid-template-columns: 1fr 120px auto; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px solid rgba(255, 255, 255, .05); }
.ck-cat-name { color: #c7d9df; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ck-cat-spark { width: 120px; height: 22px; opacity: .9; }
.ck-cat-val { font-family: "JetBrains Mono", monospace; font-weight: 800; font-size: 14px; }
.ck-cat-val.up { color: #ff7a90; } .ck-cat-val.down { color: #5fe3a1; }

/* 地图 */
.ck-map-wrap { position: relative; flex: 1 1 auto; min-height: 0; display: flex; }
.ck-map-chart { flex: 1 1 auto; min-height: 180px; }
.ck-map-sweep { position: absolute; inset: 0; pointer-events: none; background: linear-gradient(115deg, transparent 40%, rgba(92, 239, 255, .07) 50%, transparent 60%); background-size: 280% 100%; animation: ckSweep 7s ease-in-out infinite; -webkit-mask-image: radial-gradient(ellipse 70% 70% at 50% 50%, #000, transparent 80%); mask-image: radial-gradient(ellipse 70% 70% at 50% 50%, #000, transparent 80%); }
@keyframes ckSweep { 0% { background-position: 130% 0; } 100% { background-position: -30% 0; } }
.ck-map-scope { position: absolute; top: 2px; right: 4px; color: #7f939c; font-size: 11px; font-family: "JetBrains Mono", monospace; }
.ck-map-empty { position: absolute; inset: 0; }

/* 预测 */
.ck-fc-body { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
.ck-fc-chart { flex: 1 1 auto; min-height: 130px; }
.ck-light { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 800; }
.ck-light i { width: 9px; height: 9px; border-radius: 50%; }
.ck-light.ok { color: #5fe3a1; background: rgba(95, 227, 161, .12); } .ck-light.ok i { background: #5fe3a1; box-shadow: 0 0 8px #5fe3a1; }
.ck-light.warn { color: #ffd166; background: rgba(255, 209, 102, .12); } .ck-light.warn i { background: #ffd166; box-shadow: 0 0 8px #ffd166; }
.ck-light.risk { color: #ff7a90; background: rgba(255, 122, 144, .12); } .ck-light.risk i { background: #ff7a90; box-shadow: 0 0 8px #ff7a90; }
.ck-fc-tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 6px; }
.ck-fc-tiles > div { padding: 6px 10px; border: 1px solid rgba(92, 239, 255, .12); border-radius: 8px; background: rgba(2, 10, 20, .45); }
.ck-fc-tiles span { display: block; color: #8ba0aa; font-size: 11px; }
.ck-fc-tiles strong { color: #dffbff; font-size: 17px; font-weight: 800; font-family: "JetBrains Mono", monospace; }
.ck-fc-tiles strong.hl { color: #ffd166; }
.ck-fc-tiles strong.ok { color: #5fe3a1; } .ck-fc-tiles strong.warn { color: #ffd166; } .ck-fc-tiles strong.risk { color: #ff7a90; }
.ck-fc-empty { position: relative; margin: auto; }

/* 行列表（异动/价差） */
.ck-rows { flex: 1 1 auto; overflow: auto; min-height: 0; }
.ck-row { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 7px; border-bottom: 1px solid rgba(255, 255, 255, .05); font-size: 13px; }
.ck-row.clickable { cursor: pointer; transition: background .12s; }
.ck-row.clickable:hover { background: rgba(92, 239, 255, .08); }
.ck-row .rk { font-weight: 900; font-size: 12px; }
.ck-row .rk.up, .ck-row .up { color: #ff7a90; } .ck-row .rk.down, .ck-row .down { color: #5fe3a1; }
.ck-row .nm { flex: 1 1 auto; color: #dfe2f3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ck-row .up, .ck-row .down, .ck-row .warn { font-weight: 800; font-family: "JetBrains Mono", monospace; }
.ck-row .warn { color: #ffd166; }
.ck-route { color: #8ba0aa; font-size: 11px; white-space: nowrap; }

/* 决策看板 */
.ck-decision { flex: 1 1 auto; overflow: auto; min-height: 0; }
.ck-dec-head { margin: 0 0 8px; color: #cdeef5; font-size: 12.5px; line-height: 1.5; }
.ck-dec-item { padding: 8px 10px; margin-bottom: 7px; border-radius: 8px; border-left: 3px solid; background: rgba(255, 255, 255, .03); }
.ck-dec-item.ok { border-color: #5fe3a1; } .ck-dec-item.warn { border-color: #ffd166; } .ck-dec-item.risk { border-color: #ff7a90; }
.ck-dec-top { display: flex; align-items: center; gap: 7px; }
.ck-dec-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.ck-dec-item.ok .ck-dec-dot { color: #5fe3a1; } .ck-dec-item.warn .ck-dec-dot { color: #ffd166; } .ck-dec-item.risk .ck-dec-dot { color: #ff7a90; }
.ck-dec-top strong { color: #e6f9ff; font-size: 13px; }
.ck-dec-act { margin: 4px 0 0 14px; color: #9fb3bc; font-size: 12px; line-height: 1.45; }

.ck-empty { display: grid; place-items: center; min-height: 60px; color: #7f939c; font-size: 12.5px; text-align: center; }

/* 底部 */
.ck-foot { display: flex; gap: 12px; margin-top: 12px; flex: 0 0 auto; }
.ck-ticker { flex: 1 1 auto; display: flex; align-items: center; height: 38px; overflow: hidden; border: 1px solid rgba(92, 239, 255, .16); border-radius: 9px; background: rgba(2, 10, 20, .5); }
.ck-ticker-tag { flex: 0 0 auto; padding: 0 14px; height: 100%; display: flex; align-items: center; background: rgba(92, 239, 255, .15); color: #aef3ff; font-weight: 800; font-size: 13px; }
.ck-ticker-track { display: inline-flex; gap: 34px; white-space: nowrap; animation: ckScroll 42s linear infinite; padding-left: 20px; }
.ck-ticker-track span { font-weight: 700; font-size: 13px; }
.ck-ticker-track span.up { color: #ff7a90; } .ck-ticker-track span.down { color: #5fe3a1; }
@keyframes ckScroll { from { transform: translateX(0); } to { transform: translateX(-50%); } }
.ck-hotstrip { flex: 0 0 auto; display: flex; align-items: center; gap: 8px; max-width: 52%; overflow: hidden; padding: 0 4px; }
.ck-hot-label { flex: 0 0 auto; color: rgba(92, 239, 255, .7); font: 800 10px/1 "JetBrains Mono", monospace; letter-spacing: .12em; }
.ck-hot { flex: 0 0 auto; display: flex; flex-direction: column; align-items: flex-start; gap: 1px; width: 108px; padding: 4px 8px; border: 1px solid rgba(92, 239, 255, .14); border-radius: 8px; background: rgba(2, 10, 20, .5); cursor: pointer; transition: all .14s; }
.ck-hot:hover { border-color: rgba(92, 239, 255, .45); background: rgba(92, 239, 255, .08); }
.ck-hot-name { font-size: 11px; color: #c7d9df; max-width: 92px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ck-hot-spark { width: 92px; height: 20px; }

.ck-brief { margin-top: 10px; flex: 0 0 auto; color: #eaf8ff; line-height: 1.55; font-size: 13px; padding: 8px 14px; border-left: 3px solid rgba(92, 239, 255, .6); background: rgba(255, 255, 255, .04); border-radius: 0 8px 8px 0; max-height: 56px; overflow: auto; }

/* el-select 暗化 */
.ck-sel { width: 132px; }
.ck-sel-sku { width: 168px; }
.ck-sel :deep(.el-select__wrapper) { background: rgba(2, 14, 26, .85); box-shadow: 0 0 0 1px rgba(92, 239, 255, .22) inset; min-height: 28px; }
.ck-sel :deep(.el-select__placeholder), .ck-sel :deep(.el-select__selected-item) { color: #dffbff; font-size: 12px; }

/* 分段控件 */
.seg { display: inline-flex; padding: 2px; gap: 2px; border-radius: 8px; background: rgba(0, 0, 0, .3); border: 1px solid rgba(92, 239, 255, .12); }
.seg button { height: 24px; padding: 0 10px; border: none; border-radius: 6px; background: transparent; color: rgba(186, 201, 204, .72); font-size: 12px; font-weight: 700; cursor: pointer; transition: all .14s; }
.seg button:hover { color: #dfe9f5; }
.seg button.active { background: rgba(92, 239, 255, .16); color: #5cefff; box-shadow: inset 0 0 0 1px rgba(92, 239, 255, .32); }

/* 抽屉 */
.ck-drawer { padding: 22px 20px; color: #dfe2f3; height: 100%; box-sizing: border-box; overflow: auto;
  background: linear-gradient(180deg, #0a1322 0%, #081020 100%); font-family: "Space Grotesk", system-ui, sans-serif; }
.ckd-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.ckd-head h2 { margin: 2px 0 0; color: #e6f9ff; font-size: 19px; }
.ckd-close { width: 30px; height: 30px; border: 1px solid rgba(92, 239, 255, .25); border-radius: 7px; background: transparent; color: #8ba0aa; font-size: 14px; cursor: pointer; }
.ckd-close:hover { color: #5cefff; border-color: rgba(92, 239, 255, .5); }
.ckd-title { margin: 16px 0 8px; color: rgba(92, 239, 255, .8); font: 800 11px/1 "JetBrains Mono", monospace; letter-spacing: .1em; text-transform: uppercase; }
.ckd-stats, .ckd-fc-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.ckd-fc-row { grid-template-columns: repeat(3, 1fr); }
.ckd-stats > div, .ckd-fc-row > div { padding: 9px 10px; border: 1px solid rgba(92, 239, 255, .14); border-radius: 8px; background: rgba(2, 10, 20, .5); text-align: center; }
.ckd-stats span, .ckd-fc-row span { display: block; color: #8ba0aa; font-size: 11px; margin-bottom: 3px; }
.ckd-stats strong, .ckd-fc-row strong { color: #dffbff; font-size: 16px; font-weight: 800; font-family: "JetBrains Mono", monospace; }
.ckd-stats strong.up { color: #ff7a90; } .ckd-stats strong.down { color: #5fe3a1; }
.ckd-fc-row strong.hl { color: #ffd166; }
.ckd-chart { height: 200px; }
.ckd-prov-row { display: grid; grid-template-columns: 80px 1fr 56px; align-items: center; gap: 10px; padding: 5px 0; }
.ckd-prov-name { color: #c7d9df; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ckd-prov-bar { height: 8px; border-radius: 999px; background: rgba(255, 255, 255, .06); overflow: hidden; }
.ckd-prov-bar i { display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #0f7a8c, #00e5ff); }
.ckd-prov-row strong { color: #dffbff; font-size: 13px; font-family: "JetBrains Mono", monospace; text-align: right; }
.ckd-detail-row { display: grid; grid-template-columns: 1fr 1fr auto; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid rgba(255, 255, 255, .05); font-size: 12px; }
.ckd-detail-row .ckd-dim { color: #8ba0aa; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ckd-detail-row strong { color: #dffbff; font-family: "JetBrains Mono", monospace; }
.ckd-detail-row em { font-style: normal; color: #7f939c; font-size: 11px; }
:deep(.el-drawer) { background: transparent; }
:deep(.el-drawer__body) { padding: 0; }

@media (max-width: 1280px) {
  .ck-grid { flex-direction: column; overflow: auto; }
  .ck-col, .ck-col-center { flex: none; }
  .p-1, .p-bigmap, .p-fc { flex: none; min-height: 260px; }
  .ck-foot { flex-direction: column; }
  .ck-hotstrip { max-width: 100%; flex-wrap: wrap; }
}
</style>
