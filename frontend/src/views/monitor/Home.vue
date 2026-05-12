<script setup>
import { onMounted, ref } from 'vue'
import { monitorDashboardApi } from '../../api/monitor'
import { formatChinaDateTime } from '../../utils/datetime'

const loading = ref(false)
const state = ref({
  today_orders: 0,
  today_gmv: 0,
  active_vehicles: 0,
  pending_alerts: 0,
  latest_alerts: [],
  latest_orders: [],
})

const load = async () => {
  loading.value = true
  try {
    state.value = await monitorDashboardApi()
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <el-row :gutter="16" class="mb-3">
      <el-col :span="6"><el-card>今日订单：{{ state.today_orders }}</el-card></el-col>
      <el-col :span="6"><el-card>今日GMV：¥{{ Number(state.today_gmv || 0).toLocaleString() }}</el-card></el-col>
      <el-col :span="6"><el-card>活跃车辆：{{ state.active_vehicles }}</el-card></el-col>
      <el-col :span="6"><el-card>待处理预警：{{ state.pending_alerts }}</el-card></el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card>
          <template #header><span class="font-semibold">最新订单动态</span></template>
          <el-table :data="state.latest_orders || []" border>
            <el-table-column prop="order_no" label="订单号" min-width="140" />
            <el-table-column prop="new_status" label="状态" width="120" />
            <el-table-column label="时间" min-width="180">
              <template #default="{ row }">{{ formatChinaDateTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header><span class="font-semibold">最新预警</span></template>
          <el-table :data="state.latest_alerts || []" border>
            <el-table-column prop="level" label="级别" width="100" />
            <el-table-column prop="type" label="类型" width="130" />
            <el-table-column prop="description" label="描述" min-width="180" />
            <el-table-column label="时间" min-width="180">
              <template #default="{ row }">{{ formatChinaDateTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>
