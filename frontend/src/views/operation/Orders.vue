<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listOperationOrdersApi } from '../../api/operation'
import { formatChinaDateTime } from '../../utils/datetime'
import { MAIN_ORDER_STATUS_OPTIONS, orderStatusLabel, orderStatusTagColor } from '../../utils/orderStatus'

const status = ref('')
const orderNo = ref('')
const dateRange = ref([])
const list = ref([])
const loading = ref(false)
const differenceFilter = ref('')
const filteredList = computed(() =>
  list.value.filter((row) => {
    if (!differenceFilter.value) return true
    if (differenceFilter.value === 'any') return Boolean(row.receiving_difference?.has_receiving_difference)
    return row.receiving_difference?.difference_type === differenceFilter.value
  }),
)
const router = useRouter()
// 'created' = 按下单时间筛选；'delivery' = 按配送时间筛选
const dateMode = ref('created')
const goDetail = (row) => {
  const id = row?.id ?? row?.order_id
  const n = Number(id)
  if (!Number.isFinite(n) || n <= 0) return
  router.push(`/operation/orders/${n}`).catch(() => {})
}
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
const applyQuickFilter = (mode) => {
  dateMode.value = mode
  initToday()
  load()
}
const receivingDifferenceText = (diff, type) => {
  if (!diff) return '—'
  if (type === 'shortage') return diff.shortage_text || diff.diff_label || `${diff.shortage_qty ?? diff.shortage_kg ?? 0} ${diff.measure_unit || 'kg'}`
  if (type === 'overage') return diff.overage_text || diff.diff_label || `${diff.overage_qty ?? diff.overage_kg ?? 0} ${diff.measure_unit || 'kg'}`
  return diff.diff_label || '—'
}
const load = async () => {
  loading.value = true
  try {
    const start = dateRange.value?.[0] ? toDateStr(dateRange.value[0]) : undefined
    const end = dateRange.value?.[1] ? toDateStr(dateRange.value[1]) : undefined
    const dateParams =
      dateMode.value === 'delivery'
        ? { expected_delivery_date_start: start, expected_delivery_date_end: end }
        : { created_date_start: start, created_date_end: end }
    list.value = await listOperationOrdersApi({
      status: status.value || undefined,
      order_no: orderNo.value?.trim() || undefined,
      ...dateParams,
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
    <div class="quick-filter">
      <span class="quick-filter__label">快捷筛选</span>
      <div class="quick-filter__group">
        <button
          type="button"
          class="quick-chip"
          :class="{ 'is-active': dateMode === 'created' }"
          @click="applyQuickFilter('created')"
        >
          今日下单
        </button>
        <button
          type="button"
          class="quick-chip"
          :class="{ 'is-active': dateMode === 'delivery' }"
          @click="applyQuickFilter('delivery')"
        >
          今日配送
        </button>
      </div>
    </div>
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
        <el-form-item label="收货差异">
          <el-select v-model="differenceFilter" placeholder="全部" clearable style="width: 150px">
            <el-option value="" label="全部" />
            <el-option value="any" label="有差异" />
            <el-option value="shortage" label="少收退货" />
            <el-option value="overage" label="多收留痕" />
          </el-select>
        </el-form-item>
        <el-form-item :label="dateMode === 'delivery' ? '配送时间' : '下单时间'">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            :start-placeholder="dateMode === 'delivery' ? '配送开始日期' : '下单开始日期'"
            :end-placeholder="dateMode === 'delivery' ? '配送结束日期' : '下单结束日期'"
          />
        </el-form-item>
      </el-form>
      <div class="crud-actions">
        <el-button @click="load">筛选</el-button>
      </div>
    </div>
  </el-card>
  <el-card>
    <template #header><span class="font-semibold">订单监控总览</span></template>
    <el-table v-loading="loading" :data="filteredList" border class="clickable-rows" @row-click="goDetail">
      <el-table-column prop="order_no" label="订单号" min-width="150" />
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :color="orderStatusTagColor(row.status)" effect="dark">
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
      <el-table-column label="收货差异" width="150">
        <template #default="{ row }">
          <el-tag v-if="row.receiving_difference?.difference_type === 'shortage'" type="danger" effect="plain">
            少收 {{ receivingDifferenceText(row.receiving_difference, 'shortage') }}
          </el-tag>
          <el-tag v-else-if="row.receiving_difference?.difference_type === 'overage'" type="success" effect="plain">
            多收 {{ receivingDifferenceText(row.receiving_difference, 'overage') }}
          </el-tag>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" min-width="180">
        <template #default="{ row }">{{ formatChinaDateTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link @click.stop="goDetail(row)">查看详情</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<style scoped>
.clickable-rows :deep(.el-table__row) {
  cursor: pointer;
}
.quick-filter {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.quick-filter__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}
.quick-filter__group {
  display: inline-flex;
  gap: 8px;
  padding: 4px;
  background: var(--el-fill-color-light);
  border-radius: 10px;
}
.quick-chip {
  padding: 6px 18px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--el-text-color-regular);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}
.quick-chip:hover {
  color: var(--el-color-primary);
}
.quick-chip.is-active {
  background: var(--el-color-primary);
  color: #fff;
  box-shadow: 0 2px 8px rgba(64, 128, 255, 0.28);
}
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
