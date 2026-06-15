<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listOrdersApi } from '../../api/orders'
import { formatChinaDateTime } from '../../utils/datetime'
import { MAIN_ORDER_STATUS_OPTIONS, orderStatusLabel, orderStatusTagColor } from '../../utils/orderStatus'
import { DELIVERY_STAGE_FILTER_OPTIONS, deliveryStageLabel, deliveryStageTagType } from '../../utils/deliveryStage'

const router = useRouter()
const route = useRoute()
const list = ref([])
const status = ref('')
const orderNo = ref('')
const dateRange = ref([])
const loading = ref(false)
// 'created' = 按下单时间筛选；'delivery' = 按配送时间筛选
const dateMode = ref('created')
// 阶段筛选（客户端对已返回列表按 stage.code 过滤），'' = 全部阶段
const stageFilter = ref('')
const differenceFilter = ref('')
const filteredList = computed(() =>
  list.value.filter((r) => {
    if (stageFilter.value && r?.stage?.code !== stageFilter.value) return false
    if (differenceFilter.value === 'any' && !r?.receiving_difference?.has_receiving_difference) return false
    if (
      differenceFilter.value &&
      differenceFilter.value !== 'any' &&
      r?.receiving_difference?.difference_type !== differenceFilter.value
    ) return false
    return true
  }),
)
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
const goDetail = (row) => {
  if (row?.id != null) router.push(`/delivery/orders/${row.id}`)
}

/** 期望配送日 + 时段（与订单字段一致） */
const formatExpectedDelivery = (row) => {
  const raw = row?.expected_delivery_date
  const dateStr = raw != null && raw !== '' ? String(raw).slice(0, 10) : ''
  const slot = (row?.expected_delivery_slot || '').trim()
  if (dateStr && slot) return `${dateStr} ${slot}`
  if (dateStr) return dateStr
  if (slot) return slot
  return '—'
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
    list.value = await listOrdersApi({
      status: status.value || undefined,
      order_no: orderNo.value?.trim() || undefined,
      ...dateParams,
    })
  } finally {
    loading.value = false
  }
}
onMounted(() => {
  if (route.query.stage) stageFilter.value = String(route.query.stage)
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
      <el-input v-model="orderNo" placeholder="订单号" clearable style="width: 180px" />
      <el-select v-model="status" style="width: 160px">
        <el-option value="" label="全部状态" />
        <el-option v-for="o in MAIN_ORDER_STATUS_OPTIONS" :key="o.value" :value="o.value" :label="o.label" />
      </el-select>
      <el-select v-model="stageFilter" placeholder="全部阶段" clearable style="width: 160px">
        <el-option value="" label="全部阶段" />
        <el-option v-for="o in DELIVERY_STAGE_FILTER_OPTIONS" :key="o.value" :value="o.value" :label="o.label" />
      </el-select>
      <el-select v-model="differenceFilter" placeholder="收货差异" clearable style="width: 150px">
        <el-option value="" label="全部" />
        <el-option value="any" label="有差异" />
        <el-option value="shortage" label="少收退货" />
        <el-option value="overage" label="多收留痕" />
      </el-select>
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        :start-placeholder="dateMode === 'delivery' ? '配送开始日期' : '下单开始日期'"
        :end-placeholder="dateMode === 'delivery' ? '配送结束日期' : '下单结束日期'"
      />
      <el-button @click="load">刷新</el-button>
    </div>
  </el-card>
  <el-card>
    <template #header><span class="font-semibold">配送订单</span></template>
    <el-table v-loading="loading" :data="filteredList" border class="clickable-rows" @row-click="goDetail">
      <el-table-column prop="order_no" label="订单号" min-width="160" />
      <el-table-column prop="canteen_name" label="食堂" min-width="120" show-overflow-tooltip />
      <el-table-column prop="client_name" label="客户名称" min-width="140" show-overflow-tooltip />
      <el-table-column prop="delivery_address" label="送货地址" min-width="200" show-overflow-tooltip />
      <el-table-column label="下单时间" min-width="170">
        <template #default="{ row }">{{ formatChinaDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="配送时间" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">{{ formatExpectedDelivery(row) }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="110">
        <template #default="{ row }">
          <el-tag :color="orderStatusTagColor(row.status)" effect="dark">{{ orderStatusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="当前阶段" width="130">
        <template #default="{ row }">
          <el-tag v-if="row.stage?.code" :type="deliveryStageTagType(row.stage.code)" effect="plain">
            {{ deliveryStageLabel(row.stage.code) }}
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="total_amount" label="金额" width="130">
        <template #default="{ row }">¥{{ Number(row.total_amount || 0).toLocaleString() }}</template>
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
      <el-table-column label="操作" width="100" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click.stop="goDetail(row)">详情</el-button>
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
</style>
