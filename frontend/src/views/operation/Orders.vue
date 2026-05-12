<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listOperationOrdersApi } from '../../api/operation'
import { formatChinaDateTime } from '../../utils/datetime'
import { MAIN_ORDER_STATUS_OPTIONS, orderMainStatusTagType, orderStatusLabel } from '../../utils/orderStatus'

const status = ref('')
const orderNo = ref('')
const dateRange = ref([])
const list = ref([])
const loading = ref(false)
const router = useRouter()
const goDetail = (row) => router.push(`/operation/orders/${row.id}`)
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
    list.value = await listOperationOrdersApi({
      status: status.value || undefined,
      order_no: orderNo.value?.trim() || undefined,
      created_date_start: start,
      created_date_end: end,
    })
  } finally {
    loading.value = false
  }
}
onMounted(() => {
  initToday()
  load()
})
</script>

<template>
  <el-card class="mb-3">
    <div class="crud-toolbar">
      <el-form inline class="crud-form">
        <el-form-item label="状态">
          <el-select v-model="status" style="width: 180px">
            <el-option value="" label="全部" />
            <el-option v-for="o in MAIN_ORDER_STATUS_OPTIONS" :key="o.value" :value="o.value" :label="o.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="订单号">
          <el-input v-model="orderNo" placeholder="订单号" clearable style="width: 180px" />
        </el-form-item>
        <el-form-item label="时间">
          <el-date-picker v-model="dateRange" type="daterange" start-placeholder="开始日期" end-placeholder="结束日期" />
        </el-form-item>
      </el-form>
      <div class="crud-actions">
        <el-button @click="load">筛选</el-button>
      </div>
    </div>
  </el-card>
  <el-card>
    <template #header><span class="font-semibold">订单监控总览</span></template>
    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="order_no" label="订单号" min-width="150" />
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="orderMainStatusTagType(row.status)">
            {{ orderStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="total_amount" label="金额" width="130">
        <template #default="{ row }">¥{{ Number(row.total_amount || 0).toLocaleString() }}</template>
      </el-table-column>
      <el-table-column prop="has_abnormal" label="异常">
        <template #default="{ row }">
          <el-tag :type="row.has_abnormal ? 'danger' : 'success'">{{ row.has_abnormal ? '是' : '否' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" min-width="180">
        <template #default="{ row }">{{ formatChinaDateTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link @click="goDetail(row)">查看详情</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<style scoped>
.crud-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.crud-form {
  margin-bottom: 0;
}

.crud-actions {
  display: flex;
  align-items: center;
}
</style>
