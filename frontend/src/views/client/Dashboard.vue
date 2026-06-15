<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { clientDashboardApi } from '../../api/clientPortal'
import { useIsMobile } from '../../composables/useIsMobile'

const router = useRouter()
const { isMobile } = useIsMobile()
const loading = ref(false)
const scope = ref('canteen')
const canteenName = ref('')
const kpi = ref({
  month_spend: 0,
  month_orders: 0,
  avg_order: 0,
  to_receive: 0,
  in_progress: 0,
  abnormal: 0,
  payable_outstanding: 0,
})
const trendData = ref([])
const categoryDist = ref([])
const productTop = ref([])

const numberFmt = (v) => Number(v || 0).toLocaleString()
const moneyFmt = (v) => `¥${Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`

const kpiSpan = computed(() => (isMobile.value ? 12 : 6))
const chartSpan = computed(() => (isMobile.value ? 24 : 8))

const trendChartRef = ref(null)
const categoryChartRef = ref(null)
const productChartRef = ref(null)
const mTrendRef = ref(null)
const chartInstances = {}

// 移动端 KPI 色卡模型（语义色编码 + 点击下钻目标）
const kpiCards = computed(() => [
  { key: 'spend', label: '本月采购额', value: moneyFmt(kpi.value.month_spend), icon: 'payments', tone: 'green', nav: { path: '/client/orders', query: { range: 'month' } } },
  { key: 'orders', label: '本月订单数', value: numberFmt(kpi.value.month_orders), icon: 'receipt_long', tone: 'teal', nav: { path: '/client/orders', query: { range: 'month' } } },
  { key: 'receive', label: '待收货', value: numberFmt(kpi.value.to_receive), icon: 'local_shipping', tone: 'amber', nav: { path: '/client/orders', query: { status: '收货', range: 'all' } } },
  { key: 'payable', label: '应付未结', value: moneyFmt(kpi.value.payable_outstanding), icon: 'account_balance_wallet', tone: 'terracotta', nav: { path: '/client/bills' } },
  { key: 'progress', label: '进行中订单', value: numberFmt(kpi.value.in_progress), icon: 'pending_actions', tone: 'indigo', nav: { path: '/client/orders', query: { view: 'in_progress', range: 'all' } } },
  { key: 'abnormal', label: '异常订单', value: numberFmt(kpi.value.abnormal), icon: 'release_alert', tone: kpi.value.abnormal > 0 ? 'red' : 'muted', nav: { path: '/client/orders', query: { view: 'abnormal', range: 'all' } } },
])
const onKpiClick = (c) => { if (c.nav) router.push(c.nav) }
const quickActions = [
  { label: '新建订单', icon: 'add_shopping_cart', tone: 'green', path: '/client/orders/new' },
  { label: '我的订单', icon: 'receipt_long', tone: 'teal', path: '/client/orders' },
  { label: '发起招标', icon: 'gavel', tone: 'amber', path: '/client/contracts/new' },
  { label: '我的账单', icon: 'account_balance_wallet', tone: 'terracotta', path: '/client/bills' },
]
const CHART_COLORS = ['#4f46e5', '#0891b2', '#16a34a', '#f59e0b', '#dc2626', '#475569', '#8b5cf6']

const renderCharts = () => {
  if (mTrendRef.value) {
    const ins = chartInstances.mTrend || echarts.init(mTrendRef.value)
    ins.setOption({
      grid: { left: 2, right: 2, top: 8, bottom: 2 },
      xAxis: { type: 'category', show: false, boundaryGap: false, data: trendData.value.map((i) => i.date) },
      yAxis: { type: 'value', show: false, scale: true },
      tooltip: { trigger: 'axis', valueFormatter: (v) => moneyFmt(v) },
      series: [{
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: trendData.value.map((i) => i.spend),
        lineStyle: { width: 2.5, color: 'rgba(255,255,255,0.95)' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(255,255,255,0.42)' },
            { offset: 1, color: 'rgba(255,255,255,0)' },
          ]),
        },
      }],
    })
    chartInstances.mTrend = ins
  }
  if (trendChartRef.value) {
    const ins = chartInstances.trend || echarts.init(trendChartRef.value)
    ins.setOption({
      tooltip: { trigger: 'axis', valueFormatter: (v) => moneyFmt(v) },
      grid: { left: 40, right: 16, top: 24, bottom: 28 },
      xAxis: { type: 'category', data: trendData.value.map((i) => i.date), boundaryGap: false },
      yAxis: { type: 'value', splitLine: { lineStyle: { color: '#e2e8f0' } } },
      series: [{ type: 'line', smooth: true, data: trendData.value.map((i) => i.spend), areaStyle: { opacity: 0.16 } }],
      color: ['#4f46e5'],
    })
    chartInstances.trend = ins
  }
  if (categoryChartRef.value) {
    const ins = chartInstances.category || echarts.init(categoryChartRef.value)
    ins.setOption({
      tooltip: { trigger: 'item', formatter: (p) => `${p.name}: ${moneyFmt(p.value)} (${p.percent}%)` },
      legend: { bottom: 0, type: 'scroll' },
      series: [
        {
          type: 'pie',
          radius: ['44%', '70%'],
          center: ['50%', '44%'],
          avoidLabelOverlap: true,
          data: categoryDist.value.map((i) => ({ name: i.name, value: i.value })),
          label: { show: false },
          labelLine: { show: false },
        },
      ],
      color: CHART_COLORS,
    })
    chartInstances.category = ins
  }
  if (productChartRef.value) {
    const ins = chartInstances.product || echarts.init(productChartRef.value)
    const rows = [...productTop.value].reverse()
    ins.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => moneyFmt(v) },
      grid: { left: 8, right: 24, top: 16, bottom: 8, containLabel: true },
      xAxis: { type: 'value', splitLine: { lineStyle: { color: '#e2e8f0' } } },
      yAxis: { type: 'category', data: rows.map((r) => r.name) },
      series: [{ type: 'bar', data: rows.map((r) => r.amount), barWidth: '60%', itemStyle: { color: '#16a34a', borderRadius: [0, 4, 4, 0] } }],
    })
    chartInstances.product = ins
  }
}

const resizeCharts = () => Object.values(chartInstances).forEach((ins) => ins?.resize())

const load = async () => {
  loading.value = true
  try {
    const res = await clientDashboardApi(scope.value)
    canteenName.value = res?.canteen_name || ''
    kpi.value = res?.kpi || kpi.value
    trendData.value = res?.trend || []
    categoryDist.value = res?.category_dist || []
    productTop.value = res?.product_top || []
    await nextTick()
    renderCharts()
  } finally {
    loading.value = false
  }
}

const setScope = (s) => {
  if (scope.value === s) return
  scope.value = s
  load()
}

const jump = (path) => router.push(path)

onMounted(() => {
  load()
  window.addEventListener('resize', resizeCharts)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  Object.values(chartInstances).forEach((ins) => ins?.dispose())
})
</script>

<template>
  <!-- ── Mobile ── -->
  <div v-if="isMobile" class="m-page">
    <section class="m-hero">
      <div class="m-hero__scope">
        <button class="m-scope-chip" :class="{ 'is-active': scope === 'canteen' }" @click="setScope('canteen')">本食堂</button>
        <button class="m-scope-chip" :class="{ 'is-active': scope === 'all' }" @click="setScope('all')">全部食堂</button>
      </div>
      <div class="m-hero__label">
        <span class="material-symbols-outlined m-hero__leaf">eco</span>
        本月采购额 · {{ scope === 'all' ? '全部食堂' : (canteenName || '本食堂') }}
      </div>
      <div class="m-hero__value">{{ moneyFmt(kpi.month_spend) }}</div>
      <div class="m-hero__meta">{{ numberFmt(kpi.month_orders) }} 笔订单 · 平均 {{ moneyFmt(kpi.avg_order) }}</div>
      <div ref="mTrendRef" class="m-hero__spark" />
    </section>

    <div class="m-kpi-grid">
      <div
        v-for="c in kpiCards"
        :key="c.key"
        class="m-kpi-card"
        :class="[`tone-${c.tone}`, { 'is-tappable': c.nav }]"
        @click="onKpiClick(c)"
      >
        <span class="material-symbols-outlined m-kpi-ic">{{ c.icon }}</span>
        <div class="m-kpi-text">
          <div class="m-kpi-label">{{ c.label }}</div>
          <div class="m-kpi-value">{{ c.value }}</div>
        </div>
        <span v-if="c.nav" class="material-symbols-outlined m-kpi-arrow">chevron_right</span>
      </div>
    </div>

    <div class="m-section-title">快捷操作</div>
    <div class="m-quick-grid">
      <button v-for="a in quickActions" :key="a.path" class="m-quick-btn" @click="jump(a.path)">
        <span class="m-quick-ic" :class="`tone-${a.tone}`">
          <span class="material-symbols-outlined">{{ a.icon }}</span>
        </span>
        <span class="m-quick-label">{{ a.label }}</span>
      </button>
    </div>

    <template v-if="categoryDist.length">
      <div class="m-section-title">品类采购分布<span class="m-section-sub">近 30 日</span></div>
      <div class="m-cat-list">
        <div v-for="(c, i) in categoryDist.slice(0, 5)" :key="c.name" class="m-cat-row">
          <span class="m-cat-dot" :style="{ background: CHART_COLORS[i % CHART_COLORS.length] }" />
          <span class="m-cat-name">{{ c.name }}</span>
          <span class="m-cat-val">{{ moneyFmt(c.value) }}</span>
        </div>
      </div>
    </template>
  </div>

  <!-- ── PC ── -->
  <div v-else v-loading="loading" class="dashboard-page cockpit-bg">
    <el-card class="welcome-card">
      <div class="welcome-top">
        <div>
          <div class="welcome-title">采购看板</div>
          <div class="welcome-sub">
            数据范围：{{ scope === 'all' ? '全部食堂汇总' : `当前食堂 · ${canteenName || '—'}` }}
          </div>
        </div>
        <div class="scope-switch">
          <button type="button" class="scope-chip" :class="{ 'is-active': scope === 'canteen' }" @click="setScope('canteen')">本食堂</button>
          <button type="button" class="scope-chip" :class="{ 'is-active': scope === 'all' }" @click="setScope('all')">全部食堂</button>
        </div>
      </div>
    </el-card>

    <el-row :gutter="16">
      <el-col :span="kpiSpan"><el-card class="kpi-card"><div class="kpi-label">本月采购额</div><div class="kpi-value">{{ moneyFmt(kpi.month_spend) }}</div></el-card></el-col>
      <el-col :span="kpiSpan"><el-card class="kpi-card"><div class="kpi-label">本月订单</div><div class="kpi-value">{{ numberFmt(kpi.month_orders) }}</div></el-card></el-col>
      <el-col :span="kpiSpan"><el-card class="kpi-card"><div class="kpi-label">平均单值</div><div class="kpi-value">{{ moneyFmt(kpi.avg_order) }}</div></el-card></el-col>
      <el-col :span="kpiSpan"><el-card class="kpi-card"><div class="kpi-label">待收货</div><div class="kpi-value">{{ numberFmt(kpi.to_receive) }}</div></el-card></el-col>
      <el-col :span="kpiSpan"><el-card class="kpi-card"><div class="kpi-label">进行中订单</div><div class="kpi-value">{{ numberFmt(kpi.in_progress) }}</div></el-card></el-col>
      <el-col :span="kpiSpan"><el-card class="kpi-card"><div class="kpi-label">异常订单</div><div class="kpi-value">{{ numberFmt(kpi.abnormal) }}</div></el-card></el-col>
      <el-col :span="kpiSpan"><el-card class="kpi-card"><div class="kpi-label">应付未结</div><div class="kpi-value">{{ moneyFmt(kpi.payable_outstanding) }}</div></el-card></el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="chartSpan">
        <el-card class="chart-card">
          <template #header><span class="font-semibold">近 7 日采购趋势</span></template>
          <div ref="trendChartRef" class="chart-wrap" />
        </el-card>
      </el-col>
      <el-col :span="chartSpan">
        <el-card class="chart-card">
          <template #header><span class="font-semibold">品类采购分布（近30日）</span></template>
          <div v-if="categoryDist.length" ref="categoryChartRef" class="chart-wrap" />
          <el-empty v-else description="暂无数据" :image-size="60" class="chart-wrap chart-empty" />
        </el-card>
      </el-col>
      <el-col :span="chartSpan">
        <el-card class="chart-card">
          <template #header><span class="font-semibold">常购商品 TOP（近90日）</span></template>
          <div v-if="productTop.length" ref="productChartRef" class="chart-wrap" />
          <el-empty v-else description="暂无数据" :image-size="60" class="chart-wrap chart-empty" />
        </el-card>
      </el-col>
    </el-row>

    <el-card>
      <template #header><span class="font-semibold">快捷操作</span></template>
      <div class="quick-actions">
        <el-button type="primary" @click="jump('/client/orders/new')">新建订单</el-button>
        <el-button @click="jump('/client/orders')">我的订单</el-button>
        <el-button @click="jump('/client/bills')">我的账单</el-button>
        <el-button @click="jump('/client/contracts')">我的合约</el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.dashboard-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.cockpit-bg {
  background:
    radial-gradient(circle at 10% 18%, rgba(99, 102, 241, 0.12), transparent 28%),
    radial-gradient(circle at 85% 90%, rgba(14, 116, 144, 0.12), transparent 35%),
    linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
  border-radius: 16px;
  padding: 10px;
}
.welcome-card {
  border-radius: 14px;
  border: 1px solid #e2e8f0;
}
.welcome-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.welcome-title {
  font-size: 18px;
  font-weight: 600;
}
.welcome-sub {
  margin-top: 6px;
  color: #64748b;
  font-size: 13px;
}
.scope-switch {
  display: inline-flex;
  gap: 6px;
  padding: 4px;
  background: var(--el-fill-color-light);
  border-radius: 10px;
}
.scope-chip {
  padding: 6px 16px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--el-text-color-regular);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}
.scope-chip.is-active {
  background: var(--el-color-primary);
  color: #fff;
  box-shadow: 0 2px 8px rgba(79, 124, 255, 0.28);
}
.kpi-card {
  border-radius: 14px;
  border: 1px solid #e2e8f0;
  margin-bottom: 16px;
}
.kpi-label {
  color: #64748b;
  font-size: 13px;
}
.kpi-value {
  margin-top: 8px;
  font-size: 22px;
  font-weight: 700;
  color: #1e1b4b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chart-card {
  border-radius: 14px;
  margin-bottom: 16px;
}
.chart-wrap {
  height: 280px;
}
.chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
}
.quick-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

/* ── Mobile styles：鲜活食材风 ── */
.m-page {
  padding: 0 0 24px;
  font-family: var(--m-font-body);
  background: var(--m-surface);
  min-height: 100%;
}

/* Hero */
.m-hero {
  position: relative;
  background:
    radial-gradient(120% 90% at 100% 0%, rgba(242, 160, 61, 0.30) 0%, transparent 55%),
    linear-gradient(150deg, var(--m-primary) 0%, var(--m-primary-container) 100%);
  color: var(--m-on-primary);
  padding: 16px 18px 18px;
  border-radius: 0 0 26px 26px;
  margin-bottom: 18px;
  overflow: hidden;
  box-shadow: 0 10px 26px rgba(31, 122, 83, 0.26);
}
.m-hero__scope {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}
.m-scope-chip {
  padding: 5px 16px;
  border-radius: 20px;
  border: 1.5px solid rgba(255, 255, 255, 0.55);
  background: transparent;
  color: rgba(255, 255, 255, 0.85);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}
.m-scope-chip.is-active {
  background: rgba(255, 255, 255, 0.22);
  color: #fff;
  border-color: #fff;
  font-weight: 700;
}
.m-hero__label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  opacity: 0.92;
}
.m-hero__leaf { font-size: 17px; }
.m-hero__value {
  font-family: var(--m-font-accent);
  font-size: 38px;
  font-weight: 600;
  line-height: 1.1;
  margin-top: 4px;
  letter-spacing: 0.5px;
}
.m-hero__meta {
  font-size: 12.5px;
  opacity: 0.82;
  margin-top: 4px;
}
.m-hero__spark {
  height: 50px;
  margin: 8px -4px -4px;
}

/* KPI 色卡 */
.m-kpi-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 11px;
  padding: 0 16px;
  margin-bottom: 22px;
}
.m-kpi-card {
  display: flex;
  align-items: center;
  gap: 11px;
  background: var(--m-surface-container-lowest);
  border: 1px solid var(--m-outline-variant);
  border-radius: 16px;
  padding: 13px 12px;
  box-shadow: 0 2px 10px rgba(35, 39, 31, 0.05);
  transition: transform 0.14s ease, box-shadow 0.14s ease;
}
.m-kpi-card:active {
  transform: translateY(1px);
  box-shadow: 0 1px 5px rgba(35, 39, 31, 0.08);
}
.m-kpi-ic {
  flex: none;
  width: 40px;
  height: 40px;
  border-radius: 13px;
  display: grid;
  place-items: center;
  font-size: 22px;
}
.m-kpi-text { min-width: 0; flex: 1; }
.m-kpi-card.is-tappable { cursor: pointer; }
.m-kpi-arrow {
  flex: none;
  font-size: 18px;
  color: var(--m-outline-variant);
  margin: -4px -2px 0 -4px;
  align-self: flex-start;
}
.m-kpi-label {
  font-size: 12px;
  color: var(--m-on-surface-variant);
  margin-bottom: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.m-kpi-value {
  font-family: var(--m-font-accent);
  font-size: 20px;
  font-weight: 600;
  color: var(--m-on-surface);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 语义色：图标芯片底+字 */
.tone-green   .m-kpi-ic, .m-kpi-card.tone-green   .m-kpi-ic { background: #dff1e7; color: var(--m-primary); }
.tone-teal    .m-kpi-ic, .m-kpi-card.tone-teal    .m-kpi-ic { background: #d4eeee; color: var(--m-teal); }
.tone-amber   .m-kpi-ic, .m-kpi-card.tone-amber   .m-kpi-ic { background: var(--m-accent-soft); color: #c87f1e; }
.tone-terracotta .m-kpi-ic { background: #f6e0da; color: var(--m-terracotta); }
.tone-indigo  .m-kpi-ic { background: #e1e4f6; color: var(--m-indigo); }
.tone-red     .m-kpi-ic { background: var(--m-error-container); color: var(--m-error); }
.tone-muted   .m-kpi-ic { background: var(--m-surface-container-high); color: var(--m-on-surface-variant); }
.m-kpi-card.tone-red .m-kpi-value { color: var(--m-error); }

/* 区块标题 */
.m-section-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-family: var(--m-font-accent);
  font-size: 18px;
  font-weight: 600;
  color: var(--m-on-surface);
  padding: 0 16px;
  margin-bottom: 12px;
}
.m-section-sub {
  font-family: var(--m-font-body);
  font-size: 12px;
  font-weight: 500;
  color: var(--m-on-surface-variant);
}

/* 快捷操作 tile */
.m-quick-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 11px;
  padding: 0 16px;
  margin-bottom: 24px;
}
.m-quick-btn {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 14px 14px;
  border: 1px solid var(--m-outline-variant);
  border-radius: 16px;
  background: var(--m-surface-container-lowest);
  color: var(--m-on-surface);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 2px 10px rgba(35, 39, 31, 0.05);
  transition: transform 0.14s ease, box-shadow 0.14s ease;
}
.m-quick-btn:active {
  transform: translateY(1px);
  box-shadow: 0 1px 5px rgba(35, 39, 31, 0.08);
}
.m-quick-ic {
  flex: none;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  display: grid;
  place-items: center;
}
.m-quick-ic .material-symbols-outlined { font-size: 21px; }
.m-quick-ic.tone-green { background: #dff1e7; color: var(--m-primary); }
.m-quick-ic.tone-teal { background: #d4eeee; color: var(--m-teal); }
.m-quick-ic.tone-amber { background: var(--m-accent-soft); color: #c87f1e; }
.m-quick-ic.tone-terracotta { background: #f6e0da; color: var(--m-terracotta); }
.m-quick-label { min-width: 0; }

/* 品类分布 */
.m-cat-list {
  margin: 0 16px;
  background: var(--m-surface-container-lowest);
  border: 1px solid var(--m-outline-variant);
  border-radius: 16px;
  padding: 4px 14px;
  box-shadow: 0 2px 10px rgba(35, 39, 31, 0.05);
}
.m-cat-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 0;
  border-bottom: 1px solid var(--m-surface-container-high);
}
.m-cat-row:last-child { border-bottom: none; }
.m-cat-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
}
.m-cat-name {
  flex: 1;
  font-size: 13.5px;
  color: var(--m-on-surface);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.m-cat-val {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--m-on-surface-variant);
  font-variant-numeric: tabular-nums;
}
</style>
