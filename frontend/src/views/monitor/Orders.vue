<script setup>
import { onMounted, ref } from 'vue'
import { monitorOrdersApi } from '../../api/monitor'
import { formatChinaDateTime } from '../../utils/datetime'
import { MAIN_ORDER_STATUS_OPTIONS, orderStatusLabel, orderStatusTagColor } from '../../utils/orderStatus'

const list = ref([])
const status = ref('')
const orderNo = ref('')
const dateRange = ref([])
const active = ref(null)
const loading = ref(false)
const toDateStr = (d) => {
  const dt = new Date(d)
  const m = String(dt.getMonth() + 1).padStart(2, '0')
  const day = String(dt.getDate()).padStart(2, '0')
  return `${dt.getFullYear()}-${m}-${day}`
}
const initToday = () => {
  const now = new Date()
  dateRange.value = [now, now]
}

const load = async () => {
  loading.value = true
  try {
    const start = dateRange.value?.[0] ? toDateStr(dateRange.value[0]) : undefined
    const end = dateRange.value?.[1] ? toDateStr(dateRange.value[1]) : undefined
    list.value = await monitorOrdersApi({
      status: status.value || undefined,
      order_no: orderNo.value?.trim() || undefined,
      created_date_start: start,
      created_date_end: end,
    })
  } finally {
    loading.value = false
  }
}

const rowClassName = ({ row }) => (row.has_abnormal ? 'danger-row' : '')
onMounted(() => {
  initToday()
  load()
})
</script>

<template>
  <el-card class="mb-3">
    <el-form inline>
      <el-form-item label="状态">
        <el-select v-model="status" style="width: 180px">
          <el-option value="" label="全部" />
          <el-option v-for="o in MAIN_ORDER_STATUS_OPTIONS" :key="o.value" :value="o.value" :label="o.label" />
        </el-select>
      </el-form-item>
      <el-form-item label="订单号">
        <el-input v-model="orderNo" placeholder="订单号" style="width: 180px" />
      </el-form-item>
      <el-form-item label="时间">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="-"
          start-placeholder="开始"
          end-placeholder="结束"
        />
      </el-form-item>
      <el-button @click="load">筛选</el-button>
    </el-form>
  </el-card>
  <el-row :gutter="12">
    <el-col :span="14">
      <el-table v-loading="loading" :data="list" border @row-click="active = $event" row-key="id" :row-class-name="rowClassName">
        <el-table-column prop="order_no" label="订单号" min-width="150" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :color="orderStatusTagColor(row.status)" effect="dark">{{ orderStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="has_abnormal" label="异常">
          <template #default="{ row }"><span :class="row.has_abnormal ? 'text-red-500' : ''">{{ row.has_abnormal ? '是' : '否' }}</span></template>
        </el-table-column>
        <el-table-column prop="total_amount" label="金额" width="120">
          <template #default="{ row }">¥{{ Number(row.total_amount || 0).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="180">
          <template #default="{ row }">{{ formatChinaDateTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-col>
    <el-col :span="10">
      <el-card>
        <h3 class="mb-2">流转时间线</h3>
        <el-timeline v-if="active">
          <el-timeline-item timestamp="待履约">客户已下单</el-timeline-item>
          <el-timeline-item timestamp="配货中">分单/备货</el-timeline-item>
          <el-timeline-item timestamp="供货出库">分包方出库（行级）</el-timeline-item>
          <el-timeline-item timestamp="向客户送货">配送商→终端客户在途</el-timeline-item>
          <el-timeline-item timestamp="待确认收货">送达，待客户确认</el-timeline-item>
          <el-timeline-item timestamp="已收货/结算">确认收货与结算</el-timeline-item>
        </el-timeline>
      </el-card>
    </el-col>
  </el-row>
</template>

<style scoped>
:deep(.danger-row) {
  background: rgba(239, 68, 68, 0.12);
}
</style>
