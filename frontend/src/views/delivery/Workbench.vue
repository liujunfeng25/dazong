<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { deliveryDashboardApi, deliveryWorkbenchApi } from '../../api/delivery'
import FleetMonitorMapCard from '../../components/FleetMonitorMapCard.vue'

const router = useRouter()
const loading = ref(false)
const stages = ref([])
const total = ref(0)

// BI 看板数据
const kpi = ref({
  today_orders: 0,
  today_gmv: 0,
  month_gmv: 0,
  month_profit: 0,
  in_progress_orders: 0,
  receivable_outstanding: 0,
})
const trendData = ref([])
const stageDist = ref({})
const supplierTop = ref([])

const numberFmt = (v) => Number(v || 0).toLocaleString()
const moneyFmt = (v) => `¥${Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`

const trendChartRef = ref(null)
const statusChartRef = ref(null)
const supplierChartRef = ref(null)
const todoSectionRef = ref(null)
const chartInstances = {}

const scrollToTodo = () => {
  todoSectionRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
const CHART_COLORS = ['#4f46e5', '#0891b2', '#16a34a', '#f59e0b', '#dc2626', '#475569', '#8b5cf6']

const renderCharts = () => {
  if (trendChartRef.value) {
    const ins = chartInstances.trend || echarts.init(trendChartRef.value)
    ins.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 30, right: 16, top: 24, bottom: 28 },
      xAxis: { type: 'category', data: trendData.value.map((i) => i.date), boundaryGap: false },
      yAxis: { type: 'value', splitLine: { lineStyle: { color: '#e2e8f0' } } },
      series: [{ type: 'line', smooth: true, data: trendData.value.map((i) => i.count), areaStyle: { opacity: 0.16 } }],
      color: ['#4f46e5'],
    })
    chartInstances.trend = ins
  }
  if (statusChartRef.value) {
    const ins = chartInstances.status || echarts.init(statusChartRef.value)
    ins.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { bottom: 0, type: 'scroll' },
      series: [
        {
          type: 'pie',
          radius: ['44%', '70%'],
          center: ['50%', '44%'],
          avoidLabelOverlap: true,
          data: Object.entries(stageDist.value).map(([name, value]) => ({ name, value })),
          label: { show: false },
          labelLine: { show: false },
        },
      ],
      color: CHART_COLORS,
    })
    chartInstances.status = ins
  }
  if (supplierChartRef.value) {
    const ins = chartInstances.supplier || echarts.init(supplierChartRef.value)
    const rows = [...supplierTop.value].reverse()
    ins.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => moneyFmt(v) },
      grid: { left: 8, right: 24, top: 16, bottom: 8, containLabel: true },
      xAxis: { type: 'value', splitLine: { lineStyle: { color: '#e2e8f0' } } },
      yAxis: { type: 'category', data: rows.map((r) => r.supplier_name) },
      series: [
        {
          type: 'bar',
          data: rows.map((r) => r.amount),
          barWidth: '60%',
          itemStyle: { color: '#0891b2', borderRadius: [0, 4, 4, 0] },
        },
      ],
    })
    chartInstances.supplier = ins
  }
}

const resizeCharts = () => {
  Object.values(chartInstances).forEach((ins) => ins?.resize())
}

// 流程总览：接单 → 分单 → 排线 → 分拣 → 取货发车 → 送达
const FLOW_STEPS = [
  { key: 'order', label: '接单', desc: '客户下单' },
  { key: 'split', label: '智能分单', desc: '分配供货商/工厂' },
  { key: 'route', label: '智能排线', desc: '按配送日排车' },
  { key: 'sort', label: '现场分拣', desc: '分检端扫码' },
  { key: 'pickup', label: '取货发车', desc: '确认取货' },
  { key: 'deliver', label: '送达', desc: '确认送达' },
]

const stageCardClass = (code) =>
  ({
    await_split: 'sc-danger',
    await_ship: 'sc-warning',
    await_sort: 'sc-warning',
    await_pickup: 'sc-primary',
    delivering: 'sc-primary',
    await_receive: 'sc-info',
    await_settle: 'sc-info',
  })[code] || 'sc-info'

const load = async () => {
  loading.value = true
  try {
    const [wb, dash] = await Promise.all([deliveryWorkbenchApi(), deliveryDashboardApi()])
    stages.value = wb?.stages || []
    total.value = Number(wb?.total || 0)
    kpi.value = dash?.kpi || kpi.value
    trendData.value = dash?.trend || []
    stageDist.value = dash?.stage_dist || {}
    supplierTop.value = dash?.supplier_top || []
    await nextTick()
    renderCharts()
  } finally {
    loading.value = false
  }
}

const pendingCount = computed(() =>
  stages.value
    .filter((s) => ['await_split', 'await_pickup', 'delivering'].includes(s.code))
    .reduce((sum, s) => sum + Number(s.count || 0), 0),
)

const goStage = (stage) => {
  if (stage.action_route) {
    router.push(stage.action_route)
  } else {
    router.push({ path: '/delivery/orders', query: { stage: stage.code } })
  }
}

const goOrder = (id) => router.push(`/delivery/orders/${id}`)

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
  <div v-loading="loading" class="workbench">
    <div class="wb-head cockpit-bg">
      <div class="wb-head-top">
        <div>
          <div class="wb-title">配送工作台</div>
          <div class="wb-sub">进行中订单 {{ total }} 单 · 待你处理 {{ pendingCount }} 单</div>
        </div>
        <div class="wb-head-actions">
          <el-button type="primary" plain @click="scrollToTodo">待办引导</el-button>
          <el-button text type="primary" @click="load">刷新</el-button>
        </div>
      </div>
      <div class="flow-strip">
        <template v-for="(s, i) in FLOW_STEPS" :key="s.key">
          <div class="flow-node">
            <div class="flow-label">{{ s.label }}</div>
            <div class="flow-desc">{{ s.desc }}</div>
          </div>
          <el-icon v-if="i < FLOW_STEPS.length - 1" class="flow-arrow"><ArrowRight /></el-icon>
        </template>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :span="4">
        <el-card class="kpi-card">
          <div class="kpi-label">今日订单</div>
          <div class="kpi-value">{{ numberFmt(kpi.today_orders) }}</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="kpi-card">
          <div class="kpi-label">今日 GMV</div>
          <div class="kpi-value">{{ moneyFmt(kpi.today_gmv) }}</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="kpi-card">
          <div class="kpi-label">本月 GMV</div>
          <div class="kpi-value">{{ moneyFmt(kpi.month_gmv) }}</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="kpi-card">
          <div class="kpi-label">本月毛利</div>
          <div class="kpi-value">{{ moneyFmt(kpi.month_profit) }}</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="kpi-card">
          <div class="kpi-label">进行中订单</div>
          <div class="kpi-value">{{ numberFmt(kpi.in_progress_orders) }}</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="kpi-card">
          <div class="kpi-label">应收未结</div>
          <div class="kpi-value">{{ moneyFmt(kpi.receivable_outstanding) }}</div>
        </el-card>
      </el-col>
    </el-row>

    <FleetMonitorMapCard scope="delivery" title="车队实时监控" :height="500" />

    <el-row :gutter="16">
      <el-col :span="8">
        <el-card class="chart-card">
          <template #header><span class="font-semibold">近 7 日订单趋势</span></template>
          <div ref="trendChartRef" class="chart-wrap" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="chart-card">
          <template #header><span class="font-semibold">订单阶段分布（近30日）</span></template>
          <div ref="statusChartRef" class="chart-wrap" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="chart-card">
          <template #header><span class="font-semibold">供货商协同 TOP（近90日）</span></template>
          <div v-if="supplierTop.length" ref="supplierChartRef" class="chart-wrap" />
          <el-empty v-else description="暂无分单数据" :image-size="60" class="chart-wrap chart-empty" />
        </el-card>
      </el-col>
    </el-row>

    <div ref="todoSectionRef" class="section-title">待办引导</div>
    <div class="stage-grid">
      <el-card
        v-for="stage in stages"
        :key="stage.code"
        shadow="hover"
        class="stage-card"
        :class="stageCardClass(stage.code)"
      >
        <div class="stage-card-head">
          <span class="stage-name">{{ stage.label }}</span>
          <span class="stage-count">{{ stage.count }}</span>
        </div>
        <div class="stage-hint">{{ stage.hint }}</div>
        <div v-if="stage.items?.length" class="stage-items">
          <div
            v-for="it in stage.items.slice(0, 3)"
            :key="it.id"
            class="stage-item"
            @click="goOrder(it.id)"
          >
            <span class="oi-no">{{ it.order_no }}</span>
            <span class="oi-meta">{{ it.client_name || '—' }}<span v-if="it.expected_delivery_date"> · {{ it.expected_delivery_date }}</span></span>
          </div>
          <div v-if="stage.count > 3" class="stage-more">还有 {{ stage.count - 3 }} 单…</div>
        </div>
        <div v-else class="stage-empty">暂无待办</div>
        <div class="stage-action">
          <el-button
            v-if="stage.count > 0"
            type="primary"
            size="small"
            :plain="!stage.action_route"
            @click="goStage(stage)"
          >
            {{ stage.action_route ? (stage.code === 'await_split' ? '去智能分单' : '去智能排线') : '查看订单' }}
          </el-button>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.workbench {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.cockpit-bg {
  background:
    radial-gradient(circle at 10% 18%, rgba(99, 102, 241, 0.12), transparent 28%),
    radial-gradient(circle at 85% 90%, rgba(14, 116, 144, 0.1), transparent 35%),
    linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
  border-radius: 16px;
  padding: 18px 20px;
  border: 1px solid #e2e8f0;
}

.wb-head-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.wb-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.wb-title {
  font-size: 20px;
  font-weight: 700;
  color: #1e1b4b;
}

.wb-sub {
  font-size: 13px;
  color: #64748b;
  margin-top: 4px;
}

.flow-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
  flex-wrap: wrap;
}

.flow-node {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 8px 14px;
  text-align: center;
  min-width: 96px;
}

.flow-label {
  font-size: 13px;
  font-weight: 600;
  color: #4f46e5;
}

.flow-desc {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 2px;
}

.flow-arrow {
  color: #c7d2fe;
}

.kpi-card {
  border-radius: 14px;
  border: 1px solid #e2e8f0;
}
.kpi-label {
  color: #64748b;
  font-size: 13px;
}
.kpi-value {
  margin-top: 8px;
  font-size: 24px;
  font-weight: 700;
  color: #1e1b4b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chart-card {
  border-radius: 14px;
}
.chart-wrap {
  height: 280px;
}
.chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
}
.section-title {
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
  margin-top: 4px;
}
.stage-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}

.stage-card {
  border-radius: 14px;
  border-top: 4px solid #cbd5e1;
}

.stage-card.sc-danger {
  border-top-color: #ef4444;
}
.stage-card.sc-warning {
  border-top-color: #f59e0b;
}
.stage-card.sc-primary {
  border-top-color: #4f46e5;
}
.stage-card.sc-info {
  border-top-color: #94a3b8;
}

.stage-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.stage-name {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
}

.stage-count {
  font-size: 26px;
  font-weight: 700;
  color: #4f46e5;
}

.stage-hint {
  font-size: 12px;
  color: #64748b;
  margin-top: 6px;
  line-height: 1.5;
  min-height: 36px;
}

.stage-items {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.stage-item {
  display: flex;
  flex-direction: column;
  padding: 6px 8px;
  background: #f8fafc;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.stage-item:hover {
  background: #eef2ff;
}

.oi-no {
  font-size: 12px;
  font-weight: 600;
  color: #334155;
}

.oi-meta {
  font-size: 11px;
  color: #94a3b8;
}

.stage-more {
  font-size: 11px;
  color: #94a3b8;
  padding-left: 4px;
}

.stage-empty {
  margin-top: 10px;
  font-size: 12px;
  color: #cbd5e1;
}

.stage-action {
  margin-top: 12px;
}
</style>
