<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import TraceImagePreview from '../../components/TraceImagePreview.vue'
import { listReceivingDifferencesApi, reviewOrderReturnApi } from '../../api/orders'
import { formatChinaDateTime } from '../../utils/datetime'

const props = defineProps({
  role: { type: String, default: 'delivery' },
})

const router = useRouter()
const loading = ref(false)
const rows = ref([])
const current = ref(null)
const drawerVisible = ref(false)
const reviewingId = ref(null)
const dateMode = ref('created')
const filters = ref({
  order_no: '',
  client_keyword: '',
  supplier_keyword: '',
  reason: '',
  status: '',
  date_range: [],
})

const title = computed(() => (props.role === 'operation' ? '全平台收货差异' : '收货差异'))
const subtitle = computed(() =>
  props.role === 'operation'
    ? '集中查看客户签收时产生的少收退货单，核对扣减金额与关联账单。'
    : '集中查看本配送商订单的少收退货单，便于和客户、供货商及账单对账。',
)
const summary = computed(() => {
  const deduction = rows.value.reduce((sum, row) => sum + Number(row.deduction_amount || 0), 0)
  const orders = new Set(rows.value.map((row) => row.order_id).filter(Boolean))
  const units = new Set(rows.value.map((row) => row.measure_unit || 'kg'))
  const shortageAmount = rows.value.reduce((sum, row) => sum + Number(row.shortage_qty ?? row.shortage_kg ?? 0), 0)
  const shortageText =
    rows.value.length === 0
      ? '0'
      : units.size === 1
        ? quantityText(shortageAmount, Array.from(units)[0])
        : `${rows.value.length} 条`
  return { count: rows.value.length, orderCount: orders.size, shortageText, deduction }
})

const toDateStr = (d) => {
  if (!d) return ''
  const dt = new Date(d)
  const m = String(dt.getMonth() + 1).padStart(2, '0')
  const day = String(dt.getDate()).padStart(2, '0')
  return `${dt.getFullYear()}-${m}-${day}`
}

const kgText = (value) =>
  value === null || value === undefined || value === '' ? '—' : `${Number(value).toFixed(2).replace(/\.?0+$/, '')} kg`
const quantityText = (value, unit = 'kg') =>
  value === null || value === undefined || value === '' ? '—' : `${Number(value).toFixed(2).replace(/\.?0+$/, '')} ${unit || 'kg'}`
const lineQuantityText = (row, key, fallback, unit = row?.measure_unit || row?.unit || 'kg') =>
  row?.[`${key}_text`] || quantityText(row?.[key] ?? row?.[fallback], unit)
const moneyText = (value) => `¥${Number(value || 0).toFixed(2)}`
const roleLabel = (role) =>
  ({
    client: '客户',
    delivery: '配送商',
    supplier: '供应商/厂家',
    factory: '工厂',
    operation: '运营',
  }[role] || role || '—')
const statusTagType = (status) =>
  ({
    pending_delivery_review: 'warning',
    confirmed: 'success',
    rejected: 'danger',
    cancelled: 'info',
  }[status] || 'info')
const canReview = (row) => props.role === 'delivery' && row?.return_status === 'pending_delivery_review'

const initToday = () => {
  const now = new Date()
  filters.value.date_range = [now, now]
}

const applyQuickFilter = (mode) => {
  dateMode.value = mode
  initToday()
  load()
}

const load = async () => {
  loading.value = true
  try {
    const start = toDateStr(filters.value.date_range?.[0]) || undefined
    const end = toDateStr(filters.value.date_range?.[1]) || undefined
    const dateParams =
      dateMode.value === 'delivery'
        ? { expected_delivery_date_start: start, expected_delivery_date_end: end }
        : { created_date_start: start, created_date_end: end }
    rows.value = await listReceivingDifferencesApi({
      order_no: filters.value.order_no?.trim() || undefined,
      client_keyword: filters.value.client_keyword?.trim() || undefined,
      supplier_keyword: filters.value.supplier_keyword?.trim() || undefined,
      reason: filters.value.reason || undefined,
      status: filters.value.status || undefined,
      ...dateParams,
    })
  } finally {
    loading.value = false
  }
}

const reset = () => {
  filters.value = { order_no: '', client_keyword: '', supplier_keyword: '', reason: '', status: '', date_range: [] }
  dateMode.value = 'created'
  initToday()
  load()
}

const openDrawer = (row) => {
  current.value = row
  drawerVisible.value = true
}

const goOrder = (row = current.value) => {
  if (!row?.order_id) return
  const prefix = props.role === 'operation' ? '/operation' : props.role === 'client' ? '/client' : '/delivery'
  router.push(`${prefix}/orders/${row.order_id}`)
}

const reviewReturn = async (row, action) => {
  if (!row?.return_id) return
  let note = ''
  if (action === 'approve') {
    await ElMessageBox.confirm(`确认通过退货单 ${row.return_no}？通过后将按少收金额扣减未确认账单。`, '退货审核', {
      type: 'warning',
      confirmButtonText: '审核通过',
      cancelButtonText: '取消',
    })
  } else {
    const res = await ElMessageBox.prompt('请输入驳回原因', `驳回退货单 ${row.return_no}`, {
      inputType: 'textarea',
      inputPlaceholder: '说明驳回原因',
      inputValidator: (value) => String(value || '').trim().length >= 2 || '请填写至少2个字',
      confirmButtonText: '确认驳回',
      cancelButtonText: '取消',
    })
    note = String(res.value || '').trim()
  }
  reviewingId.value = row.return_id
  try {
    await reviewOrderReturnApi(row.return_id, { action, note })
    ElMessage.success(action === 'approve' ? '已审核通过' : '已驳回')
    await load()
    if (current.value?.return_id === row.return_id) {
      current.value = rows.value.find((item) => item.return_id === row.return_id) || current.value
    }
  } finally {
    reviewingId.value = null
  }
}

onMounted(() => {
  initToday()
  load()
})
</script>

<template>
  <div class="diff-page">
    <el-card class="mb-3" shadow="never">
      <template #header>
        <div class="page-head">
          <div>
            <div class="page-title">{{ title }}</div>
            <div class="page-subtitle">{{ subtitle }}</div>
          </div>
          <el-button type="primary" plain @click="load">刷新</el-button>
        </div>
      </template>
      <div class="summary-grid">
        <div class="summary-card">
          <span>差异明细</span>
          <strong>{{ summary.count }}</strong>
        </div>
        <div class="summary-card">
          <span>影响订单</span>
          <strong>{{ summary.orderCount }}</strong>
        </div>
        <div class="summary-card is-shortage">
          <span>少收数量</span>
          <strong>{{ summary.shortageText }}</strong>
        </div>
        <div class="summary-card is-money">
          <span>扣减金额</span>
          <strong>{{ moneyText(summary.deduction) }}</strong>
        </div>
      </div>
      <div class="quick-filter mt-3">
        <span class="quick-filter__label">快捷筛选</span>
        <div class="quick-filter__group">
          <button
            type="button"
            class="quick-chip"
            :class="{ 'is-active': dateMode === 'created' }"
            @click="applyQuickFilter('created')"
          >
            今日确认
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
      <div class="crud-toolbar mt-3">
        <el-input v-model="filters.order_no" placeholder="订单号" clearable style="width: 180px" />
        <el-input v-model="filters.client_keyword" placeholder="客户/食堂" clearable style="width: 180px" />
        <el-input v-model="filters.supplier_keyword" placeholder="供应商/厂家" clearable style="width: 180px" />
        <el-select v-model="filters.reason" placeholder="全部原因" clearable style="width: 140px">
          <el-option value="lack" label="缺货" />
          <el-option value="quality" label="质量问题" />
          <el-option value="other" label="其他" />
        </el-select>
        <el-select v-model="filters.status" placeholder="全部状态" clearable style="width: 140px">
          <el-option value="pending_delivery_review" label="待配送商审核" />
          <el-option value="confirmed" label="已确认" />
          <el-option value="rejected" label="已驳回" />
          <el-option value="cancelled" label="已取消" />
        </el-select>
        <el-date-picker
          v-model="filters.date_range"
          type="daterange"
          :start-placeholder="dateMode === 'delivery' ? '配送开始日期' : '确认开始日期'"
          :end-placeholder="dateMode === 'delivery' ? '配送结束日期' : '确认结束日期'"
        />
        <el-button type="primary" @click="load">筛选</el-button>
        <el-button @click="reset">重置</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="rows" border class="clickable-rows" @row-click="openDrawer">
        <el-table-column prop="return_no" label="退货单号" min-width="150" />
        <el-table-column prop="order_no" label="订单号" min-width="150" />
        <el-table-column prop="client_name" label="客户" min-width="140" show-overflow-tooltip />
        <el-table-column prop="canteen_name" label="食堂" min-width="120" show-overflow-tooltip />
        <el-table-column prop="delivery_name" label="配送商" min-width="140" show-overflow-tooltip />
        <el-table-column prop="supplier_name" label="供应商/厂家" min-width="150" show-overflow-tooltip />
        <el-table-column prop="product_name" label="商品" min-width="170" show-overflow-tooltip />
        <el-table-column label="规格/单位" width="120">
          <template #default="{ row }">{{ [row.spec, row.unit].filter(Boolean).join(' / ') || '—' }}</template>
        </el-table-column>
        <el-table-column label="下单量" width="110">
          <template #default="{ row }">{{ lineQuantityText(row, 'ordered', 'ordered_kg') }}</template>
        </el-table-column>
        <el-table-column label="实收量" width="110">
          <template #default="{ row }">{{ lineQuantityText(row, 'received', 'received_kg') }}</template>
        </el-table-column>
        <el-table-column label="差异" width="110">
          <template #default="{ row }"><span class="shortage-text">{{ row.shortage_text || row.diff_label || `-${quantityText(row.shortage_qty ?? row.shortage_kg, row.measure_unit)}` }}</span></template>
        </el-table-column>
        <el-table-column label="扣减金额" width="110">
          <template #default="{ row }">{{ moneyText(row.deduction_amount) }}</template>
        </el-table-column>
        <el-table-column label="原因" width="100">
          <template #default="{ row }">{{ row.reason_label || '—' }}</template>
        </el-table-column>
        <el-table-column label="确认时间" min-width="165">
          <template #default="{ row }">{{ formatChinaDateTime(row.confirmed_at || row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><el-tag :type="statusTagType(row.return_status)">{{ row.return_status_label }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click.stop="openDrawer(row)">查看</el-button>
            <el-button link @click.stop="goOrder(row)">订单</el-button>
            <el-button
              v-if="canReview(row)"
              type="success"
              link
              :loading="reviewingId === row.return_id"
              @click.stop="reviewReturn(row, 'approve')"
            >
              通过
            </el-button>
            <el-button
              v-if="canReview(row)"
              type="danger"
              link
              :loading="reviewingId === row.return_id"
              @click.stop="reviewReturn(row, 'reject')"
            >
              驳回
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="drawerVisible" title="收货少收退货单" size="640px" destroy-on-close>
      <template v-if="current">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="退货单号">{{ current.return_no }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(current.return_status)">{{ current.return_status_label }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="订单号">{{ current.order_no }}</el-descriptions-item>
          <el-descriptions-item label="客户">{{ current.client_name }}</el-descriptions-item>
          <el-descriptions-item label="食堂">{{ current.canteen_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="配送商">{{ current.delivery_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="供应商/厂家">{{ current.supplier_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="商品">{{ current.product_name }}</el-descriptions-item>
          <el-descriptions-item label="规格/单位">{{ [current.spec, current.unit].filter(Boolean).join(' / ') || '—' }}</el-descriptions-item>
          <el-descriptions-item label="下单量">{{ lineQuantityText(current, 'ordered', 'ordered_kg') }}</el-descriptions-item>
          <el-descriptions-item label="实收量">{{ lineQuantityText(current, 'received', 'received_kg') }}</el-descriptions-item>
          <el-descriptions-item label="差异"><span class="shortage-text">{{ current.shortage_text || current.diff_label }}</span></el-descriptions-item>
          <el-descriptions-item label="扣减金额">{{ moneyText(current.deduction_amount) }}</el-descriptions-item>
          <el-descriptions-item label="少收原因">{{ current.reason_label }}</el-descriptions-item>
          <el-descriptions-item label="说明">{{ current.reason_detail || '—' }}</el-descriptions-item>
          <el-descriptions-item label="审核意见">{{ current.review_note || '—' }}</el-descriptions-item>
          <el-descriptions-item label="审核时间">{{ current.reviewed_at ? formatChinaDateTime(current.reviewed_at) : '—' }}</el-descriptions-item>
        </el-descriptions>

        <div class="drawer-section">
          <div class="section-title">账单影响</div>
          <div class="billing-impact">
            <span>原订单金额：{{ moneyText(current.billing?.ordered_amount) }}</span>
            <span>实收计费：{{ moneyText(current.billing?.received_amount) }}</span>
            <span>扣减金额：{{ moneyText(current.billing?.deduction_amount) }}</span>
          </div>
          <el-alert
            type="warning"
            show-icon
            :closable="false"
            :title="current.return_status === 'pending_delivery_review' ? '该退货单待配送商审核，当前账单暂不扣减；审核通过后才会扣减未确认账单。' : '少收会扣减客户应付和配送商应付供应商/厂家的账单；超收只留痕，不增加应收应付。'"
          />
          <el-table v-if="(current.related_statements || []).length" :data="current.related_statements" border size="small" class="mt-2">
            <el-table-column prop="statement_no" label="账单号" min-width="180" />
            <el-table-column prop="direction" label="方向" width="80" />
            <el-table-column label="所属角色" width="120">
              <template #default="{ row }">{{ roleLabel(row.role) }}</template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100" />
            <el-table-column label="金额" width="110">
              <template #default="{ row }">{{ moneyText(row.amount) }}</template>
            </el-table-column>
          </el-table>
        </div>

        <div class="drawer-section">
          <div class="section-title">证据照片</div>
          <div v-if="(current.photo_urls || []).length" class="photo-list">
            <TraceImagePreview
              v-for="(url, index) in current.photo_urls"
              :key="url"
              :src="url"
              fit="cover"
              class="trace-thumb"
              :preview-list="current.photo_urls"
              :initial-index="index"
            />
          </div>
          <el-empty v-else description="暂无证据照片" :image-size="60" />
        </div>

        <div class="drawer-actions">
          <el-button type="primary" @click="goOrder()">查看订单详情</el-button>
          <el-button
            v-if="canReview(current)"
            type="success"
            :loading="reviewingId === current.return_id"
            @click="reviewReturn(current, 'approve')"
          >
            审核通过
          </el-button>
          <el-button
            v-if="canReview(current)"
            type="danger"
            plain
            :loading="reviewingId === current.return_id"
            @click="reviewReturn(current, 'reject')"
          >
            驳回
          </el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.page-title {
  font-size: 18px;
  font-weight: 800;
  color: #0f172a;
}
.page-subtitle {
  margin-top: 4px;
  color: #64748b;
  font-size: 13px;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.summary-card {
  padding: 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
}
.summary-card span {
  display: block;
  color: #64748b;
  font-size: 12px;
}
.summary-card strong {
  display: block;
  margin-top: 8px;
  font-size: 24px;
  color: #0f172a;
}
.summary-card.is-shortage strong {
  color: #dc2626;
}
.summary-card.is-money strong {
  color: #0f766e;
}
.quick-filter {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 12px;
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
  gap: 10px;
  flex-wrap: wrap;
}
.clickable-rows :deep(.el-table__row) {
  cursor: pointer;
}
.shortage-text {
  color: #dc2626;
  font-weight: 700;
}
.drawer-section {
  margin-top: 18px;
}
.section-title {
  margin-bottom: 10px;
  font-weight: 700;
  color: #0f172a;
}
.billing-impact {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}
.billing-impact span {
  padding: 10px;
  border-radius: 8px;
  background: #f8fafc;
  color: #334155;
  font-size: 13px;
}
.photo-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.trace-thumb {
  width: 96px;
  height: 72px;
  border-radius: 8px;
}
.drawer-actions {
  margin-top: 20px;
  text-align: right;
}
@media (max-width: 900px) {
  .summary-grid,
  .billing-impact {
    grid-template-columns: 1fr;
  }
}
</style>
