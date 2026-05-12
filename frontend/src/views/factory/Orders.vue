<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { factoryOrdersApi } from '../../api/factory'
import { formatChinaDateTime } from '../../utils/datetime'
import { MAIN_ORDER_STATUS_OPTIONS, orderStatusLabel } from '../../utils/orderStatus'

const router = useRouter()
const list = ref([])
const status = ref('')
const orderNo = ref('')
const dateRange = ref([])
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
    list.value = await factoryOrdersApi({
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
      <el-input v-model="orderNo" placeholder="订单号" clearable style="width: 180px" />
      <el-select v-model="status" style="width: 180px">
        <el-option value="" label="全部状态" />
        <el-option
          v-for="o in MAIN_ORDER_STATUS_OPTIONS.filter((x) => ['下单', '配货', '发货', '收货', '收货确认'].includes(x.value))"
          :key="o.value"
          :value="o.value"
          :label="o.label"
        />
      </el-select>
      <el-date-picker v-model="dateRange" type="daterange" start-placeholder="开始日期" end-placeholder="结束日期" />
      <el-button @click="load">筛选</el-button>
    </div>
  </el-card>
  <el-card>
    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="order_no" label="订单号" min-width="180" />
      <el-table-column prop="status" label="状态" width="140">
        <template #default="{ row }">{{ orderStatusLabel(row.status) }}</template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="180">
        <template #default="{ row }">{{ formatChinaDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button size="small" @click="router.push(`/factory/orders/${row.id}`)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<style scoped>
.crud-toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
</style>
