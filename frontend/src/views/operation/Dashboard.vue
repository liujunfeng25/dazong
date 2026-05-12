<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import {
  listOperationContractsApi,
  listOperationOrdersApi,
  listTicketsApi,
  operationDashboardApi,
} from '../../api/operation'
import OperationContractsTable from './OperationContractsTable.vue'
import { formatChinaClock, formatChinaDateTime } from '../../utils/datetime'

const router = useRouter()
const loading = ref(false)
const kpi = ref({ today_orders: 0, today_gmv: 0, abnormal_count: 0, ticket_count: 0 })
const orders = ref([])
const tickets = ref([])
const trendData = ref([])
const statusDist = ref({})
const contractsLoading = ref(false)
const contractsPreview = ref([])

const nowText = ref(formatChinaClock())
let clockTimer = null
const trendChartRef = ref(null)
const statusChartRef = ref(null)
const chartInstances = {}

const numberFmt = (v) => Number(v || 0).toLocaleString()

const isoDate = (date) => {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const buildTrend = (list) => {
  const map = new Map()
  list.forEach((item) => {
    const key = (item.created_at || '').slice(0, 10)
    if (!key) return
    map.set(key, (map.get(key) || 0) + 1)
  })
  const rows = []
  const today = new Date()
  for (let i = 6; i >= 0; i -= 1) {
    const day = new Date(today)
    day.setDate(today.getDate() - i)
    const key = isoDate(day)
    rows.push({ date: key.slice(5), count: map.get(key) || 0 })
  }
  return rows
}

const buildStatusDist = (list) => {
  const dist = {}
  list.forEach((item) => {
    const key = item.status || '未知'
    dist[key] = (dist[key] || 0) + 1
  })
  return dist
}

const renderCharts = () => {
  if (trendChartRef.value) {
    const ins = chartInstances.trend || echarts.init(trendChartRef.value)
    ins.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 30, right: 16, top: 24, bottom: 28 },
      xAxis: { type: 'category', data: trendData.value.map((i) => i.date), boundaryGap: false },
      yAxis: { type: 'value', splitLine: { lineStyle: { color: '#e2e8f0' } } },
      series: [
        {
          type: 'line',
          smooth: true,
          data: trendData.value.map((i) => i.count),
          areaStyle: { opacity: 0.16 },
        },
      ],
      color: ['#4f46e5'],
    })
    chartInstances.trend = ins
  }
  if (statusChartRef.value) {
    const ins = chartInstances.status || echarts.init(statusChartRef.value)
    ins.setOption({
      tooltip: { trigger: 'item' },
      legend: { bottom: 0 },
      series: [
        {
          type: 'pie',
          radius: ['44%', '72%'],
          data: Object.entries(statusDist.value).map(([name, value]) => ({ name, value })),
          label: { formatter: '{b}: {d}%' },
        },
      ],
      color: ['#4f46e5', '#0891b2', '#16a34a', '#f59e0b', '#dc2626', '#475569'],
    })
    chartInstances.status = ins
  }
}

const resizeCharts = () => {
  Object.values(chartInstances).forEach((ins) => ins?.resize())
}

const aiInsights = computed(() => {
  const trend = trendData.value || []
  const today = trend[trend.length - 1]?.count || 0
  const yest = trend[trend.length - 2]?.count || 0
  const delta = today - yest
  const trendText =
    delta > 0 ? `今日订单较昨日 +${delta}` : delta < 0 ? `今日订单较昨日 ${delta}` : '今日订单与昨日持平'
  const riskLevel = kpi.value.abnormal_count > 5 || kpi.value.ticket_count > 8 ? '高' : '中'
  return [
    {
      title: '经营趋势洞察',
      content: `${trendText}，建议重点关注新增客户来源与高频品类。`,
      level: delta >= 0 ? 'positive' : 'warning',
    },
    {
      title: '风险闭环建议',
      content: `当前异常 ${kpi.value.abnormal_count} 单，工单 ${kpi.value.ticket_count} 条，风险等级 ${riskLevel}。建议按“高优先级工单->责任人->截止时间”推进。`,
      level: riskLevel === '高' ? 'danger' : 'warning',
    },
    {
      title: '履约效率提示',
      content: '建议新增“下单-配货-发货-收货”漏斗跟踪，并对超时订单设自动预警阈值。',
      level: 'neutral',
    },
  ]
})

const load = async () => {
  loading.value = true
  try {
    const end = new Date()
    const start = new Date()
    start.setDate(end.getDate() - 6)
    const [kpiData, orderList, ticketList, trendOrders] = await Promise.all([
      operationDashboardApi(),
      listOperationOrdersApi(),
      listTicketsApi(),
      listOperationOrdersApi({ created_date_start: isoDate(start), created_date_end: isoDate(end) }),
    ])
    await loadContractsPreview()
    kpi.value = kpiData
    orders.value = (orderList || []).slice(0, 8)
    tickets.value = (ticketList || []).slice(0, 8)
    trendData.value = buildTrend(trendOrders || [])
    statusDist.value = buildStatusDist(trendOrders || [])
    await nextTick()
    renderCharts()
  } finally {
    loading.value = false
  }
}

const jump = (path) => router.push(path)

const CONTRACT_PREVIEW_LIMIT = 5

const loadContractsPreview = async () => {
  contractsLoading.value = true
  try {
    const rows = await listOperationContractsApi({ lifecycle: '生效中' })
    contractsPreview.value = (rows || []).slice(0, CONTRACT_PREVIEW_LIMIT)
  } catch {
    contractsPreview.value = []
  } finally {
    contractsLoading.value = false
  }
}

const goContractsMore = () => router.push('/operation/contracts')

const onPreviewContract = (row) => {
  router.push({ path: '/operation/contracts', query: { open: String(row.id) } })
}

onMounted(() => {
  load()
  nowText.value = formatChinaClock()
  clockTimer = setInterval(() => {
    nowText.value = formatChinaClock()
  }, 1000)
  window.addEventListener('resize', resizeCharts)
})
onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer)
  window.removeEventListener('resize', resizeCharts)
  Object.values(chartInstances).forEach((ins) => ins?.dispose())
})
</script>

<template>
  <div v-loading="loading" class="dashboard-page cockpit-bg">
    <el-card class="welcome-card">
      <div class="welcome-top">
        <div>
          <div class="welcome-title">运营智能驾驶舱</div>
          <div class="welcome-sub">当前时间：{{ nowText }}</div>
        </div>
        <div class="welcome-tag">决策模式</div>
      </div>
    </el-card>

    <el-row :gutter="16" class="mb-4">
      <el-col :span="6">
        <el-card class="kpi-card">
          <div class="kpi-label">今日订单</div>
          <div class="kpi-value">{{ numberFmt(kpi.today_orders) }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="kpi-card">
          <div class="kpi-label">今日 GMV</div>
          <div class="kpi-value">¥{{ numberFmt(kpi.today_gmv) }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="kpi-card">
          <div class="kpi-label">异常订单</div>
          <div class="kpi-value">{{ numberFmt(kpi.abnormal_count) }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="kpi-card">
          <div class="kpi-label">待处理工单</div>
          <div class="kpi-value">{{ numberFmt(kpi.ticket_count) }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="16">
        <el-row :gutter="16" class="mb-4">
          <el-col :span="12">
            <el-card class="chart-card">
              <template #header><span class="font-semibold">近7日订单趋势</span></template>
              <div ref="trendChartRef" class="chart-wrap" />
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card class="chart-card">
              <template #header><span class="font-semibold">订单状态分布</span></template>
              <div ref="statusChartRef" class="chart-wrap" />
            </el-card>
          </el-col>
        </el-row>
        <el-card class="mb-4">
          <template #header><span class="font-semibold">实时订单追踪</span></template>
          <el-table :data="orders" border>
            <el-table-column prop="order_no" label="订单号" min-width="140" />
            <el-table-column prop="status" label="状态" width="100" />
            <el-table-column prop="total_amount" label="金额" width="120" />
            <el-table-column label="更新时间" min-width="180">
              <template #default="{ row }">{{ formatChinaDateTime(row.updated_at) }}</template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card>
          <template #header><span class="font-semibold">异常工单闭环</span></template>
          <el-table :data="tickets" border>
            <el-table-column prop="id" label="工单ID" width="90" />
            <el-table-column prop="type" label="类别" min-width="130" />
            <el-table-column prop="status" label="状态" width="110" />
            <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="mb-4">
          <template #header><span class="font-semibold">AI 洞察建议</span></template>
          <div class="insight-list">
            <div
              v-for="item in aiInsights"
              :key="item.title"
              class="insight-card"
              :class="`insight-${item.level}`"
            >
              <div class="insight-title">{{ item.title }}</div>
              <div class="insight-content">{{ item.content }}</div>
            </div>
          </div>
        </el-card>
        <el-card class="mb-4">
          <template #header><span class="font-semibold">运营动作入口</span></template>
          <div class="quick-actions">
            <el-button type="primary" @click="jump('/operation/accounts')">账号管理</el-button>
            <el-button @click="jump('/operation/products')">商品管理</el-button>
            <el-button @click="jump('/operation/tickets')">工单处理</el-button>
            <el-button @click="jump('/operation/orders')">订单监控</el-button>
          </div>
        </el-card>
        <el-card>
          <template #header>
            <div class="contracts-card-head">
              <span class="font-semibold">合约履约快照</span>
              <el-button type="primary" link @click="goContractsMore">更多</el-button>
            </div>
          </template>
          <p class="contracts-card-tip">默认展示生命周期为「生效中」的合约（双方、合约期、期内订单汇总）。</p>
          <OperationContractsTable
            :data="contractsPreview"
            :loading="contractsLoading"
            compact
            :show-db-status="false"
            @view-contract="onPreviewContract"
          />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.dashboard-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: calc(100vh - 120px);
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

.welcome-tag {
  border-radius: 999px;
  background: #312e81;
  color: #fff;
  font-size: 12px;
  padding: 4px 12px;
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
  font-size: 26px;
  font-weight: 700;
  color: #1e1b4b;
}

.chart-card {
  border-radius: 14px;
}

.chart-wrap {
  height: 280px;
}

.insight-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.insight-card {
  border-radius: 12px;
  padding: 10px;
  border: 1px solid #dbeafe;
  background: #f8fafc;
}

.insight-title {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
}

.insight-content {
  margin-top: 6px;
  color: #475569;
  font-size: 12px;
  line-height: 1.5;
}

.insight-positive {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.insight-warning {
  border-color: #fde68a;
  background: #fffbeb;
}

.insight-danger {
  border-color: #fecaca;
  background: #fef2f2;
}

.insight-neutral {
  border-color: #e2e8f0;
  background: #f8fafc;
}

.quick-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.quick-actions :deep(.el-button) {
  width: 100%;
}

.contracts-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.contracts-card-tip {
  margin: 0 0 10px;
  font-size: 12px;
  color: #64748b;
  line-height: 1.4;
}

.mb-4 {
  margin-bottom: 16px;
}
</style>
