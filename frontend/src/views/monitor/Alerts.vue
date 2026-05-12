<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { closeMonitorAlertApi, monitorAlertsApi } from '../../api/monitor'
import { formatChinaYearMonth } from '../../utils/datetime'

const level = ref('')
const status = ref('')
const list = ref([])
const trendRef = ref(null)
const expanded = ref({})
const loading = ref(false)
let chart = null
let resizeHandler = null
const levelLabel = (value) => ({ high: '高', medium: '中', low: '低' }[value] || value)
const statusLabel = (value) => ({ open: '待处理', closed: '已关闭' }[value] || value)
const closeAlert = async (row) => {
  await closeMonitorAlertApi(row.id)
  await load()
}

const load = async () => {
  loading.value = true
  try {
    list.value = await monitorAlertsApi({ level: level.value || undefined, status: status.value || undefined })
    const monthly = {}
    list.value.forEach((a) => {
      const k = formatChinaYearMonth(a.created_at) || 'unknown'
      monthly[k] = (monthly[k] || 0) + 1
    })
    chart = chart || echarts.init(trendRef.value)
    chart.setOption({
      xAxis: { type: 'category', data: Object.keys(monthly) },
      yAxis: { type: 'value' },
      series: [{ type: 'line', smooth: true, data: Object.values(monthly) }],
    })
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  resizeHandler = () => chart && chart.resize()
  window.addEventListener('resize', resizeHandler)
})

onBeforeUnmount(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  if (chart) chart.dispose()
})
</script>

<template>
  <el-card class="mb-3">
    <el-form inline>
      <el-select v-model="level" placeholder="级别" style="width: 120px">
        <el-option value="" label="全部级别" />
        <el-option value="high" label="高" />
        <el-option value="medium" label="中" />
        <el-option value="low" label="低" />
      </el-select>
      <el-select v-model="status" placeholder="状态" style="width: 120px" class="ml-2">
        <el-option value="" label="全部状态" />
        <el-option value="open" label="待处理" />
        <el-option value="closed" label="已关闭" />
      </el-select>
      <el-button class="ml-2" @click="load">筛选</el-button>
    </el-form>
  </el-card>
  <el-row :gutter="12">
    <el-col :span="14">
      <el-table v-loading="loading" :data="list" border>
        <el-table-column prop="id" label="编号" width="70" />
        <el-table-column prop="level" label="级别" width="90">
          <template #default="{ row }">
            <el-tag :type="row.level === 'high' ? 'danger' : row.level === 'medium' ? 'warning' : 'info'">{{ levelLabel(row.level) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="100" />
        <el-table-column prop="description" label="描述" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'closed' ? 'success' : 'danger'">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="处置" width="120">
          <template #default="{ row }">
            <el-button size="small" type="success" :disabled="row.status === 'closed'" @click="closeAlert(row)">关闭</el-button>
          </template>
        </el-table-column>
        <el-table-column label="详情" width="120">
          <template #default="{ row }">
            <el-button link type="primary" @click="expanded[row.id] = !expanded[row.id]">{{ expanded[row.id] ? '收起' : '展开' }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-card v-for="row in list.filter((i) => expanded[i.id])" :key="`detail-${row.id}`" class="mt-2 border border-slate-200">
        <div class="text-sm">{{ row.description }}</div>
      </el-card>
    </el-col>
    <el-col :span="10"><el-card><div ref="trendRef" class="h-80" /></el-card></el-col>
  </el-row>
</template>
