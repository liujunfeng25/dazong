<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { supplierOrdersApi } from '../../api/supplier'
import { formatChinaDateTime } from '../../utils/datetime'
import { orderStatusLabel } from '../../utils/orderStatus'

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
    list.value = await supplierOrdersApi({
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
      <el-select v-model="status" style="width: 160px">
        <el-option value="" label="全部状态" />
        <el-option value="pending_ship" label="待发货" />
        <el-option value="shipped" label="已发货" />
        <el-option value="completed" label="已完成" />
        <el-option value="cancelled" label="已取消" />
      </el-select>
      <el-date-picker v-model="dateRange" type="daterange" start-placeholder="开始日期" end-placeholder="结束日期" />
      <el-button @click="load">筛选</el-button>
    </div>
  </el-card>
  <el-card>
    <template #header>
      <span class="font-semibold">配送分包订单</span>
      <span class="text-xs text-slate-500 font-normal ml-2">
        客户向配送商下单，配送商再分包给多家供货商；此处仅展示「分包给本户」的订单，详情仅含本户分包行。商务与结算对手方为配送商。
      </span>
    </template>
    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="order_no" label="订单号" min-width="160" />
      <el-table-column prop="client_name" label="终端收货方" min-width="130" show-overflow-tooltip />
      <el-table-column prop="delivery_name" label="分包配送商" min-width="130" show-overflow-tooltip />
      <el-table-column label="期望送达" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.expected_delivery_date || '-' }}{{ row.expected_delivery_slot ? ' ' + row.expected_delivery_slot : '' }}
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag
            :type="
              row.supplier_status === 'completed' || row.supplier_status === 'shipped'
                ? 'success'
                : row.supplier_status === 'cancelled'
                  ? 'danger'
                  : 'warning'
            "
          >
            {{ row.supplier_status_text || orderStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="本户分包金额" width="130">
        <template #default="{ row }">
          ¥{{ Number((row.supply_portion_amount ?? row.total_amount) || 0).toLocaleString() }}
        </template>
      </el-table-column>
      <el-table-column label="更新时间" min-width="180">
        <template #default="{ row }">{{ formatChinaDateTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="center">
        <template #default="{ row }">
          <el-button size="small" @click="router.push(`/supplier/orders/${row.id}`)">查看</el-button>
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
</style>
