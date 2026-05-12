<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import * as XLSX from 'xlsx'
import { monitorReportsApi } from '../../api/monitor'

const period = ref('day')
const data = ref({ gmv_total: 0, orders_count: 0, delivery_performance: [] })
const chartRef = ref(null)
const loading = ref(false)
let chart = null
let resizeHandler = null

const load = async () => {
  loading.value = true
  try {
    data.value = await monitorReportsApi({ period: period.value })
    chart = chart || echarts.init(chartRef.value)
    chart.setOption({
      xAxis: { type: 'category', data: data.value.delivery_performance.map((i) => i.name) },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', data: data.value.delivery_performance.map((i) => i.score) }],
    })
  } finally {
    loading.value = false
  }
}

const exportExcel = () => {
  const rows = [
    { 指标: 'GMV总额', 值: data.value.gmv_total },
    { 指标: '订单数', 值: data.value.orders_count },
    ...data.value.delivery_performance.map((i) => ({ 指标: `配送商${i.name}`, 值: i.score })),
  ]
  const ws = XLSX.utils.json_to_sheet(rows)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'reports')
  XLSX.writeFile(wb, 'monitor-reports.xlsx')
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
      <el-select v-model="period" style="width: 120px" @change="load">
        <el-option value="day" label="日" />
        <el-option value="week" label="周" />
        <el-option value="month" label="月" />
      </el-select>
      <el-button class="ml-2" @click="exportExcel">导出Excel</el-button>
    </el-form>
  </el-card>
  <el-row :gutter="12">
    <el-col :span="10">
      <el-card v-loading="loading">
        <p>GMV总额：¥{{ Number(data.gmv_total || 0).toLocaleString() }}</p>
        <p>订单数：{{ data.orders_count }}</p>
      </el-card>
    </el-col>
    <el-col :span="14"><el-card v-loading="loading"><div ref="chartRef" class="h-80" /></el-card></el-col>
  </el-row>
</template>
