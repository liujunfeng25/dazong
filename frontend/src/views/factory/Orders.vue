<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { factoryHomeApi, factoryOrdersApi } from '../../api/factory'
import { formatChinaDateTime } from '../../utils/datetime'
import { MAIN_ORDER_STATUS_OPTIONS, orderStatusLabel, orderStatusTagColor } from '../../utils/orderStatus'

const router = useRouter()
const list = ref([])
const todo = ref({ pending_ship_orders: 0, in_progress_orders: 0, receivable_unsettled: 0 })
const fmtMoney = (v) => Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const loadTodo = async () => {
  try {
    const r = await factoryHomeApi()
    if (r?.todo) todo.value = r.todo
  } catch {
    /* 待办汇总失败不阻塞列表 */
  }
}
const status = ref('')
const orderNo = ref('')
const dateRange = ref([])
const loading = ref(false)
// 'created' = 按下单时间筛选；'delivery' = 按配送时间筛选
const dateMode = ref('created')

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
const goDetail = (row) => {
  if (row?.id != null) router.push(`/factory/orders/${row.id}`)
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
    list.value = await factoryOrdersApi({
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
  loadTodo()
  load()
})
</script>

<template>
  <div class="todo-bar">
    <div class="todo-chip warn">
      <span class="t-label">今日待发货</span>
      <strong class="t-val">{{ todo.pending_ship_orders }}<em>单</em></strong>
    </div>
    <div class="todo-chip">
      <span class="t-label">进行中订单</span>
      <strong class="t-val">{{ todo.in_progress_orders }}<em>单</em></strong>
    </div>
    <div class="todo-chip money">
      <span class="t-label">对配送商应收（未结）</span>
      <strong class="t-val">¥{{ fmtMoney(todo.receivable_unsettled) }}</strong>
    </div>
  </div>
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
      <el-select v-model="status" style="width: 180px">
        <el-option value="" label="全部状态" />
        <el-option
          v-for="o in MAIN_ORDER_STATUS_OPTIONS.filter((x) => ['下单', '配货', '发货', '收货', '收货确认'].includes(x.value))"
          :key="o.value"
          :value="o.value"
          :label="o.label"
        />
      </el-select>
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        :start-placeholder="dateMode === 'delivery' ? '配送开始日期' : '下单开始日期'"
        :end-placeholder="dateMode === 'delivery' ? '配送结束日期' : '下单结束日期'"
      />
      <el-button @click="load">筛选</el-button>
    </div>
  </el-card>
  <el-card>
    <el-table v-loading="loading" :data="list" border class="clickable-rows" @row-click="goDetail">
      <el-table-column prop="order_no" label="订单号" min-width="180" />
      <el-table-column prop="status" label="状态" width="140">
        <template #default="{ row }">
          <el-tag :color="orderStatusTagColor(row.status)" effect="dark">{{ orderStatusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="180">
        <template #default="{ row }">{{ formatChinaDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click.stop="goDetail(row)">查看</el-button>
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
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

/* 今日待办摘要条:任务优先,一眼知道要干嘛 */
.todo-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.todo-chip {
  flex: 1 1 180px;
  min-width: 150px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 16px;
  border: 1px solid #d4eede;
  border-radius: 12px;
  background: linear-gradient(135deg, #f1fbf5 0%, #ffffff 100%);
  text-align: left;
}
.todo-chip .t-label {
  font-size: 12px;
  color: #5b8c70;
}
.todo-chip .t-val {
  font-size: 24px;
  font-weight: 800;
  color: #15803d;
  font-family: 'DIN Alternate', 'JetBrains Mono', monospace;
  line-height: 1.1;
}
.todo-chip .t-val em {
  font-style: normal;
  font-size: 13px;
  font-weight: 600;
  color: #6b9b80;
  margin-left: 3px;
}
.todo-chip.warn {
  border-color: #b7e4c7;
}
.todo-chip.money .t-val {
  color: #16a34a;
}
</style>
