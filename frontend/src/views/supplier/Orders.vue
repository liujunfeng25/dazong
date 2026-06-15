<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { supplierHomeApi, supplierOrdersApi } from '../../api/supplier'
import { formatChinaDateTime } from '../../utils/datetime'
import { orderStatusLabel } from '../../utils/orderStatus'

const router = useRouter()
const list = ref([])
const todo = ref({ pending_ship_orders: 0, in_progress_orders: 0, receivable_unsettled: 0 })
const fmtMoney = (v) => Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const loadTodo = async () => {
  try {
    const r = await supplierHomeApi()
    if (r?.todo) todo.value = r.todo
  } catch {
    /* 待办汇总失败不阻塞列表 */
  }
}
const focusPendingShip = () => {
  // 业务规则:当日分的单当日发货,故"今日待发货"按「今日配送 + 未出库」口径,与待办条一致
  status.value = 'pending_ship'
  dateMode.value = 'delivery'
  initToday()
  load()
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
  if (row?.id != null) router.push(`/supplier/orders/${row.id}`)
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
    list.value = await supplierOrdersApi({
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
    <button type="button" class="todo-chip warn" @click="focusPendingShip">
      <span class="t-label">今日待发货</span>
      <strong class="t-val">{{ todo.pending_ship_orders }}<em>单</em></strong>
    </button>
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
      <el-select v-model="status" style="width: 160px">
        <el-option value="" label="全部状态" />
        <el-option value="pending_ship" label="待发货" />
        <el-option value="shipped" label="已发货" />
        <el-option value="completed" label="已完成" />
        <el-option value="cancelled" label="已取消" />
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
    <template #header>
      <span class="font-semibold">配送分包订单</span>
      <span class="text-xs text-slate-500 font-normal ml-2">
        客户向配送商下单，配送商再分包给多家供货商；此处仅展示「分包给本户」的订单，详情仅含本户分包行。商务与结算对手方为配送商。
      </span>
    </template>
    <el-table v-loading="loading" :data="list" class="clickable-rows app-table" @row-click="goDetail">
      <el-table-column label="订单号" min-width="160">
        <template #default="{ row }"><span class="cell-mono">{{ row.order_no }}</span></template>
      </el-table-column>
      <el-table-column prop="client_name" label="终端收货方" min-width="130" show-overflow-tooltip />
      <el-table-column prop="delivery_name" label="分包配送商" min-width="130" show-overflow-tooltip />
      <el-table-column label="期望送达" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.expected_delivery_date || '-' }}{{ row.expected_delivery_slot ? ' ' + row.expected_delivery_slot : '' }}
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <span class="st-pill" :class="row.supplier_status"><i></i>{{ row.supplier_status_text || orderStatusLabel(row.status) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本户分包金额" width="130">
        <template #default="{ row }">
          <strong class="cell-amount">¥{{ Number((row.supply_portion_amount ?? row.total_amount) || 0).toLocaleString() }}</strong>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" min-width="180">
        <template #default="{ row }">{{ formatChinaDateTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" class="view-btn" @click.stop="goDetail(row)">查看</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <div class="app-empty">
          <div class="ae-icon">📦</div>
          <p class="ae-title">暂无配送分包订单</p>
          <p class="ae-sub">点上方「今日待发货」或切换「今日下单 / 今日配送」试试</p>
        </div>
      </template>
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
  border: 1px solid #fde4d2;
  border-radius: 12px;
  background: linear-gradient(135deg, #fff7f1 0%, #ffffff 100%);
  text-align: left;
}
.todo-chip.warn {
  border-color: #f8c9a3;
  cursor: pointer;
  transition: box-shadow 0.15s, transform 0.15s;
}
.todo-chip.warn:hover {
  box-shadow: 0 6px 16px -6px rgba(234, 88, 12, 0.4);
  transform: translateY(-1px);
}
.todo-chip .t-label {
  font-size: 12px;
  color: #94734f;
}
.todo-chip .t-val {
  font-size: 24px;
  font-weight: 800;
  color: #c2410c;
  font-family: 'DIN Alternate', 'JetBrains Mono', monospace;
  line-height: 1.1;
}
.todo-chip .t-val em {
  font-style: normal;
  font-size: 13px;
  font-weight: 600;
  color: #b08968;
  margin-left: 3px;
}
.todo-chip.money .t-val {
  color: #ea580c;
}

/* ===== 内页共享皮肤:让列表/表单继承门面精致度(供货商橙系) ===== */
/* 卡片 chrome */
:deep(.el-card) {
  border-radius: 14px;
  border-color: #eef0f4;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
/* 表格主题化 */
.app-table :deep(.el-table__header-wrapper th.el-table__cell) {
  background: linear-gradient(180deg, #fff6ef 0%, #fdeee2 100%);
  color: #93571f;
  font-weight: 700;
  border-bottom: 1px solid #f3dcc8;
}
.app-table :deep(.el-table__row) {
  cursor: pointer;
  transition: background 0.12s ease;
}
.app-table :deep(.el-table__row:hover > td.el-table__cell) {
  background: #fff7f0 !important;
}
.app-table :deep(td.el-table__cell) {
  border-bottom: 1px solid #f5eee6;
}
.app-table :deep(.el-table__inner-wrapper::before) {
  background: #f0e6dc;
}
/* 等宽数字 / 订单号 */
.cell-mono {
  font-family: 'JetBrains Mono', 'DIN Alternate', monospace;
  font-size: 13px;
  color: #475569;
  letter-spacing: 0.02em;
}
.cell-amount {
  font-family: 'JetBrains Mono', 'DIN Alternate', monospace;
  font-weight: 800;
  font-size: 14px;
  color: #c2410c;
}
/* 品牌状态药丸 */
.st-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 11px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}
.st-pill i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.st-pill.pending_ship { background: #fff1e6; color: #c2410c; }
.st-pill.pending_ship i { background: #ea580c; }
.st-pill.shipped { background: #e8f1ff; color: #1d4ed8; }
.st-pill.shipped i { background: #2563eb; }
.st-pill.completed { background: #e9f9ef; color: #15803d; }
.st-pill.completed i { background: #16a34a; }
.st-pill.cancelled { background: #f1f5f9; color: #64748b; }
.st-pill.cancelled i { background: #94a3b8; }
/* 操作按钮 */
.view-btn {
  border-color: #f3d2b4;
  color: #c2410c;
}
.view-btn:hover {
  background: #fff1e6;
  border-color: #ea580c;
  color: #c2410c;
}
/* 引导空态 */
.app-empty {
  padding: 30px 0 26px;
}
.app-empty .ae-icon {
  font-size: 34px;
  opacity: 0.65;
}
.app-empty .ae-title {
  margin: 10px 0 2px;
  font-size: 14px;
  font-weight: 700;
  color: #6b7686;
}
.app-empty .ae-sub {
  font-size: 12px;
  color: #aab4c2;
}
</style>
