<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { cancelOrderApi, orderDetailApi } from '../../api/orders'
import {
  createComplaintApi,
  getOpenComplaintApi,
  uploadComplaintImageApi,
} from '../../api/complaints'
import ComplaintProgress from '../../components/ComplaintProgress.vue'
import OrderLogisticsMapCard from '../../components/OrderLogisticsMapCard.vue'
import QualityReportReadonly from '../../components/QualityReportReadonly.vue'
import TraceImagePreview from '../../components/TraceImagePreview.vue'
import { formatChinaDateTime } from '../../utils/datetime'
import { orderStatusLabel, orderStatusTagColor } from '../../utils/orderStatus'
import { useIsMobile } from '../../composables/useIsMobile'
import { buildFulfillmentActual, dash } from '../../utils/fulfillmentMeta'

const route = useRoute()
const router = useRouter()
const detail = ref(null)
const loading = ref(false)
const { isMobile } = useIsMobile()
const colSpan = computed(() => (isMobile.value ? 24 : 12))

const FLOW = ['下单', '配货', '发货', '收货', '收货确认', '已结算']
const isCancelled = computed(() => detail.value?.status === '取消')
const stepIndex = computed(() => {
  const s = detail.value?.status
  if (!s || s === '取消') return -1
  const i = FLOW.indexOf(s)
  return i >= 0 ? i : 0
})

const pctRate = (r) => `${(Number(r || 0) * 100).toFixed(2)}%`

const orderItems = computed(() => {
  if (Array.isArray(detail.value?.order_items) && detail.value.order_items.length) {
    return detail.value.order_items
  }
  // 兜底：旧快照字段
  const snap = detail.value?.items_snapshot_json
  if (Array.isArray(snap) && snap.length) return snap
  const items = detail.value?.items_json
  return Array.isArray(items) ? items : []
})
const qualityGroups = computed(() => detail.value?.line_alloc_groups || [])
const hasQuality = computed(() => qualityGroups.value.some((g) => (g.allocations || []).length))

const expectedDeliveryText = computed(() => {
  const d = detail.value?.expected_delivery_date
  const dateStr = d != null && d !== '' ? String(d).slice(0, 10) : ''
  const slot = (detail.value?.expected_delivery_slot || '').trim()
  if (dateStr && slot) return `${dateStr} ${slot}`
  if (dateStr) return dateStr
  if (slot) return slot
  return '—'
})
const fulfillmentActual = computed(() => buildFulfillmentActual(detail.value || {}))

const receiveSignatures = computed(() => {
  const sig = detail.value?.receive_signatures_json || {}
  return {
    warehouse: sig.warehouse_signature_url || sig.warehouse_signature || '',
    carrier: sig.carrier_signature_url || sig.carrier_signature || '',
  }
})
const hasReceiveSignatures = computed(
  () => Boolean(receiveSignatures.value.warehouse || receiveSignatures.value.carrier),
)

const receivingStatusLabel = (status) =>
  ({ confirmed: '已确认', pending: '待称重', draft: '草稿' })[status] || status || '—'
const shortageReasonLabel = (code) =>
  ({ lack: '缺货', quality: '质量问题', other: '其他' })[code] || code || '—'
const kgText = (value) => (value === null || value === undefined || value === '' ? '—' : `${Number(value).toFixed(2).replace(/\.?0+$/, '')} kg`)
const receiveQtyText = (row, key, fallback) => row?.[`${key}_text`] || kgText(row?.[key] ?? row?.[fallback])
const receivingDiffClass = (row) => ({
  shortage: 'receive-diff-shortage',
  overage: 'receive-diff-overage',
})[row?.diff_type] || 'receive-diff-normal'
const receivingDiffText = (row) => row?.diff_label || kgText(row?.diff_kg_signed || 0)
const returnStatusLabel = (status) =>
  ({ pending_delivery_review: '待配送商审核', confirmed: '已确认', rejected: '已驳回', draft: '草稿', cancelled: '已取消' })[status] || status || '—'

const complaintTickets = computed(() => detail.value?.complaint_tickets || [])
const timelineEvents = computed(() => {
  const full = detail.value?.process_timeline || []
  if (full.length) return full
  return detail.value?.status_timeline || []
})
const timelineTypeLabel = (type) => ({ order_status: '订单', audit: '留痕' })[type] || '流程'
const timelineTypeTag = (type) => ({ order_status: 'primary', audit: 'info' })[type] || 'info'
const timelineTitle = (ev) => {
  if (ev.action_title) return ev.action_title
  if (ev.from_status) return `${ev.from_status} → ${ev.to_status}`
  return ev.to_status || '流程记录'
}
const timelineActor = (ev) => ev.actor_name || ev.actor_role_label || '系统'

const COMPLAINT_ALLOWED = new Set(['收货确认', '已结算'])
const canComplain = computed(() => COMPLAINT_ALLOWED.has(detail.value?.status))
const openComplaint = ref(null)
const hasOpenComplaint = computed(() => !!openComplaint.value?.exists)

const loadOpenComplaint = async () => {
  if (!detail.value || !canComplain.value) {
    openComplaint.value = null
    return
  }
  try {
    openComplaint.value = await getOpenComplaintApi(route.params.id)
  } catch {
    openComplaint.value = null
  }
}

const load = async () => {
  loading.value = true
  try {
    detail.value = await orderDetailApi(route.params.id)
    await loadOpenComplaint()
  } finally {
    loading.value = false
  }
}

const cancel = async () => {
  await ElMessageBox.confirm('确认取消该订单吗？取消后不可恢复。', '取消确认', {
    type: 'warning',
    confirmButtonText: '确认取消',
    cancelButtonText: '再想想',
  })
  await cancelOrderApi(route.params.id)
  ElMessage.success('订单已取消')
  await router.push(`/client/orders?refresh=${Date.now()}`)
}

// 售后投诉弹窗
const complaintVisible = ref(false)
const complaintReason = ref('')
const complaintImages = ref([])
const complaintSubmitting = ref(false)

const openComplaintDialog = () => {
  complaintReason.value = ''
  complaintImages.value = []
  complaintVisible.value = true
}

const onComplaintFileChange = async (file) => {
  if (complaintImages.value.length >= 5) {
    ElMessage.warning('最多上传 5 张图片')
    return
  }
  const raw = file?.raw
  if (!raw) return
  if (!String(raw.type || '').startsWith('image/')) {
    ElMessage.warning('仅允许上传图片')
    return
  }
  const fd = new FormData()
  fd.append('file', raw)
  try {
    const res = await uploadComplaintImageApi(fd)
    complaintImages.value.push({ url: res.url, name: raw.name })
    ElMessage.success('图片已上传')
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '图片上传失败')
  }
}

const removeComplaintImage = (idx) => {
  complaintImages.value.splice(idx, 1)
}

const submitComplaint = async () => {
  const reason = (complaintReason.value || '').trim()
  if (!reason) {
    ElMessage.warning('请填写投诉原因')
    return
  }
  if (reason.length > 500) {
    ElMessage.warning('投诉原因最多 500 字')
    return
  }
  complaintSubmitting.value = true
  try {
    await createComplaintApi({
      order_id: Number(route.params.id),
      reason,
      image_urls: complaintImages.value.map((i) => i.url),
    })
    ElMessage.success('投诉已提交，运营会尽快跟进')
    complaintVisible.value = false
    await loadOpenComplaint()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '提交失败')
  } finally {
    complaintSubmitting.value = false
  }
}

onMounted(load)
watch(
  () => `${route.params.id || ''}:${route.query._notify_refresh || ''}`,
  () => {
    if (route.params.id) load()
  },
)
</script>

<template>
  <!-- ── Mobile ── -->
  <div v-if="isMobile" v-loading="loading" class="m-detail-page">
    <template v-if="detail">
      <!-- Status banner -->
      <div class="m-status-banner" :style="{ background: orderStatusTagColor(detail.status) }">
        <div class="m-status-banner__label">{{ orderStatusLabel(detail.status) }}</div>
        <div class="m-status-banner__no">{{ detail.order_no }}</div>
        <div class="m-status-banner__time">{{ formatChinaDateTime(detail.updated_at) }}</div>
      </div>

      <!-- Progress stepper -->
      <div class="m-card m-stepper-card">
        <div v-if="isCancelled" class="m-hint">该订单已取消</div>
        <div v-else class="m-mobile-stepper">
          <div
            v-for="(st, idx) in FLOW"
            :key="st"
            class="m-mobile-step"
            :class="{ done: idx < stepIndex, active: idx === stepIndex }"
          >
            <div class="m-mobile-step__dot" />
            <div class="m-mobile-step__label">{{ st }}</div>
          </div>
        </div>
      </div>

      <!-- Alert -->
      <el-alert v-if="hasOpenComplaint" type="warning" :closable="false" show-icon title="已存在未关闭的售后投诉工单" class="m-alert-item" />

      <!-- Info cards -->
      <div class="m-card">
        <div class="m-card__title">配送信息</div>
        <div class="m-info-rows">
          <div class="m-info-row"><span class="m-info-label">约定送达</span><span>{{ expectedDeliveryText }}</span></div>
          <div class="m-info-row"><span class="m-info-label">配送地址</span><span>{{ detail.delivery_address || detail.canteen?.address || '—' }}</span></div>
          <div class="m-info-row"><span class="m-info-label">配送商</span><span>{{ detail.delivery?.company_name || detail.delivery?.username || '—' }}</span></div>
          <div class="m-info-row"><span class="m-info-label">配送状态</span><span>{{ fulfillmentActual.deliveryStatus || '—' }}</span></div>
        </div>
      </div>

      <div class="m-card">
        <div class="m-card__title">金额</div>
        <div class="m-amount-big">¥{{ Number(detail.total_amount || 0).toLocaleString() }}</div>
        <div class="m-info-rows">
          <div class="m-info-row"><span class="m-info-label">本单应付</span><span>¥{{ Number(detail.order_settlement?.canteen_payable_amount ?? detail.total_amount ?? 0).toLocaleString() }}</span></div>
          <div v-if="detail.contract" class="m-info-row"><span class="m-info-label">合约</span><span>{{ detail.contract.contract_no }}</span></div>
          <div v-if="detail.contract" class="m-info-row"><span class="m-info-label">整单浮动率</span><span>{{ pctRate(detail.contract.price_float_rate) }}</span></div>
        </div>
      </div>

      <!-- Order items -->
      <div class="m-card">
        <div class="m-card__title">订单明细（{{ orderItems.length }} 项）</div>
        <div v-if="orderItems.length" class="m-items-list">
          <div v-for="(row, i) in orderItems" :key="i" class="m-item-row">
            <div class="m-item-name">{{ row.product_name || row.product_id || '—' }}</div>
            <div class="m-item-sub">{{ row.spec || '' }} {{ row.unit || '' }} × {{ Number(row.quantity ?? row.order_quantity ?? 0) }}</div>
            <div class="m-item-amount">¥{{ Number(row.amount ?? (Number(row.quantity ?? row.order_quantity ?? 0) * Number(row.unit_price ?? row.order_unit_price ?? 0))).toFixed(2) }}</div>
          </div>
        </div>
        <div v-else class="m-hint">暂无明细</div>
      </div>

      <!-- Timeline -->
      <div v-if="timelineEvents.length" class="m-card">
        <div class="m-card__title">流程时间线</div>
        <div class="m-timeline">
          <div v-for="(ev, i) in timelineEvents" :key="i" class="m-timeline-item">
            <div class="m-timeline-dot" />
            <div class="m-timeline-body">
              <div class="m-timeline-title">{{ timelineTitle(ev) }}</div>
              <div class="m-timeline-actor">{{ timelineActor(ev) }} · {{ ev.created_at ? formatChinaDateTime(ev.created_at) : '' }}</div>
              <div v-if="ev.description" class="m-timeline-desc">{{ ev.description }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Actions bottom bar -->
      <div class="m-action-bar">
        <el-button v-if="detail.status === '下单'" type="danger" @click="cancel">取消订单</el-button>
        <el-button v-if="detail.status === '收货'" type="primary" @click="router.push(`/client/receive/${detail.id}`)">去收货</el-button>
        <el-button v-if="canComplain" type="warning" :disabled="hasOpenComplaint" @click="openComplaintDialog">
          {{ hasOpenComplaint ? '已发起投诉' : '售后投诉' }}
        </el-button>
      </div>
    </template>
    <el-empty v-else-if="!loading" description="暂无数据" />
  </div>

  <!-- ── PC ── -->
  <div v-else v-loading="loading" class="client-detail">
    <template v-if="detail">
      <div class="detail-head cockpit-bg">
        <div class="head-row">
          <el-button text type="primary" @click="router.push('/client/orders')">返回订单列表</el-button>
          <div class="head-tags">
            <el-tag :color="orderStatusTagColor(detail.status)" effect="dark" size="large">
              {{ orderStatusLabel(detail.status) }}
            </el-tag>
            <el-tag v-if="detail.has_abnormal" type="danger" effect="dark" class="pulse-tag">异常</el-tag>
          </div>
        </div>
        <div class="order-title">{{ detail.order_no }}</div>
        <div class="order-sub">
          创建时间 {{ formatChinaDateTime(detail.created_at) }} · 更新时间 {{ formatChinaDateTime(detail.updated_at) }}
        </div>
      </div>

      <el-alert
        v-if="hasOpenComplaint"
        type="warning"
        :closable="false"
        show-icon
        class="mb-3"
        title="已存在未关闭的售后投诉工单"
        description="运营会跟进处理，处理完成后将关闭工单。"
      />

      <el-card class="mb-3 progress-card" shadow="never">
        <template #header><span class="font-semibold">订单进度</span></template>
        <div v-if="isCancelled" class="cancel-hint">该订单已取消，不展示履约进度。</div>
        <div v-else class="stepper">
          <div
            v-for="(st, idx) in FLOW"
            :key="st"
            class="step"
            :class="{ done: idx < stepIndex, active: idx === stepIndex, todo: idx > stepIndex }"
          >
            <div class="step-dot" />
            <div class="step-label">{{ st }}</div>
          </div>
        </div>
      </el-card>

      <OrderLogisticsMapCard
        class="mb-3"
        :order-id="detail.id"
        :tracking="detail.logistics_tracking"
        title="配送动态"
      />

      <el-row :gutter="16" class="mb-3">
        <el-col :span="colSpan">
          <el-card shadow="never" class="h-full">
            <template #header><span class="font-semibold">配送信息</span></template>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="约定送达">{{ expectedDeliveryText }}</el-descriptions-item>
              <el-descriptions-item label="送货地址">{{ detail.delivery_address || detail.canteen?.address || '—' }}</el-descriptions-item>
              <el-descriptions-item label="配送商">{{ detail.delivery?.company_name || detail.delivery?.username || '—' }}</el-descriptions-item>
              <el-descriptions-item label="配送商电话">{{ detail.delivery?.contact_phone || '—' }}</el-descriptions-item>
              <el-descriptions-item label="发车车次">{{ dash(fulfillmentActual.routeNo) }}</el-descriptions-item>
              <el-descriptions-item label="配送车辆">{{ dash(fulfillmentActual.vehicleNo) }}</el-descriptions-item>
              <el-descriptions-item label="司机">{{ dash(fulfillmentActual.driverName) }}</el-descriptions-item>
              <el-descriptions-item label="实际发车">{{ formatChinaDateTime(fulfillmentActual.departedAt) }}</el-descriptions-item>
              <el-descriptions-item label="真正送达时间">{{ formatChinaDateTime(fulfillmentActual.arrivedAt) }}</el-descriptions-item>
              <el-descriptions-item label="配送状态">{{ dash(fulfillmentActual.deliveryStatus) }}</el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>
        <el-col :span="colSpan">
          <el-card shadow="never" class="h-full">
            <template #header><span class="font-semibold">金额与合约</span></template>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="订单总额">¥{{ Number(detail.total_amount || 0).toLocaleString() }}</el-descriptions-item>
              <el-descriptions-item label="本单应付">
                ¥{{ Number(detail.order_settlement?.canteen_payable_amount ?? detail.total_amount ?? 0).toLocaleString() }}
              </el-descriptions-item>
              <el-descriptions-item v-if="detail.contract" label="合约号">{{ detail.contract.contract_no }}</el-descriptions-item>
              <el-descriptions-item v-if="detail.contract" label="合约有效期">
                {{ detail.contract.period_start }} ~ {{ detail.contract.period_end }}
              </el-descriptions-item>
              <el-descriptions-item v-if="detail.contract" label="整单上浮率">{{ pctRate(detail.contract.price_float_rate) }}</el-descriptions-item>
            </el-descriptions>
            <template v-if="detail.contract?.category_rates?.length">
              <div class="block-sub-title">按一级品类上浮</div>
              <el-table :data="detail.contract.category_rates" size="small" border>
                <el-table-column prop="category_name" label="品类" min-width="100" />
                <el-table-column label="上浮率" width="110">
                  <template #default="{ row }">{{ pctRate(row.float_rate) }}</template>
                </el-table-column>
              </el-table>
            </template>
          </el-card>
        </el-col>
      </el-row>

      <el-card class="mb-3" shadow="never">
        <template #header><span class="font-semibold">订单明细</span></template>
        <el-table v-if="orderItems.length" :data="orderItems" border size="small">
          <el-table-column type="index" width="56" label="#" />
          <el-table-column label="商品" min-width="200">
            <template #default="{ row }">{{ row.product_name || row.product_id || '—' }}</template>
          </el-table-column>
          <el-table-column label="规格" min-width="100">
            <template #default="{ row }">{{ row.spec || '—' }}</template>
          </el-table-column>
          <el-table-column label="单位" width="80" align="center">
            <template #default="{ row }">{{ row.unit || '—' }}</template>
          </el-table-column>
          <el-table-column label="数量" width="100" align="right">
            <template #default="{ row }">{{ Number(row.quantity ?? row.order_quantity ?? 0) }}</template>
          </el-table-column>
          <el-table-column label="单价" width="110" align="right">
            <template #default="{ row }">¥{{ Number(row.unit_price ?? row.order_unit_price ?? 0).toFixed(2) }}</template>
          </el-table-column>
          <el-table-column label="小计" width="130" align="right">
            <template #default="{ row }">
              ¥{{ Number(row.amount ?? (Number(row.quantity ?? row.order_quantity ?? 0) * Number(row.unit_price ?? row.order_unit_price ?? 0))).toFixed(2) }}
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="暂无明细数据" :image-size="80" />
      </el-card>

      <el-card v-if="hasQuality" class="mb-3" shadow="never">
        <template #header>
          <span class="font-semibold">质检报告</span>
          <span class="muted small ml-2">按商品行展示，确保到货食安可追溯</span>
        </template>
        <div v-for="grp in qualityGroups" :key="grp.line_no" class="quality-line">
          <div class="quality-line-head">第 {{ grp.line_no }} 行 · {{ grp.product_name }}</div>
          <div
            v-for="a in grp.allocations || []"
            :key="a.id"
            class="quality-row"
          >
            <QualityReportReadonly
              :quality-report="a.quality_report"
              :quality-report-mode="a.quality_report_mode"
              :quality-covered-by="a.quality_covered_by"
              :periodic-quality-report="a.periodic_quality_report"
              :missing-quality-shipped="a.missing_quality_shipped"
            />
          </div>
        </div>
      </el-card>

      <el-card v-if="(detail.receiving_lines || []).length" class="mb-3" shadow="never">
        <template #header>
          <span class="font-semibold">收货称重与退货留痕</span>
          <span class="muted small ml-2">
            实收合计 {{ detail.receiving_total_kg ?? '—' }} kg · 确认 {{ detail.receiving_confirmed_count }}/{{ detail.receiving_total_lines }}
          </span>
        </template>
        <el-table :data="detail.receiving_lines || []" border size="small">
          <el-table-column prop="line_index" label="行" width="60" />
          <el-table-column prop="product_name" label="商品" min-width="140" show-overflow-tooltip />
          <el-table-column label="规格/单位" width="110">
            <template #default="{ row }">{{ [row.spec, row.unit].filter(Boolean).join(' / ') || '—' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">{{ receivingStatusLabel(row.status) }}</template>
          </el-table-column>
          <el-table-column label="下单量" width="110">
            <template #default="{ row }">{{ receiveQtyText(row, 'ordered', 'ordered_kg') }}</template>
          </el-table-column>
          <el-table-column label="锁定重量" width="110">
            <template #default="{ row }">{{ kgText(row.draft_kg) }}</template>
          </el-table-column>
          <el-table-column label="实收量" width="110">
            <template #default="{ row }">{{ receiveQtyText(row, 'received', 'received_kg') }}</template>
          </el-table-column>
          <el-table-column label="差异" width="100">
            <template #default="{ row }">
              <span :class="receivingDiffClass(row)">{{ receivingDiffText(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="少收原因" width="110">
            <template #default="{ row }">{{ row.reason_label || shortageReasonLabel(row.shortage_reason_code) }}</template>
          </el-table-column>
          <el-table-column prop="shortage_reason_detail" label="说明" min-width="150" show-overflow-tooltip />
          <el-table-column label="称重照片" min-width="120">
            <template #default="{ row }">
              <TraceImagePreview v-if="row.lock_photo_url" :src="row.lock_photo_url" fit="cover" class="trace-thumb" :preview-list="[row.lock_photo_url]" />
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="退货照片" min-width="160">
            <template #default="{ row }">
              <TraceImagePreview
                v-for="(url, i) in (row.return_photo_urls || [])"
                :key="url"
                :src="url"
                fit="cover"
                class="trace-thumb mr-1"
                :preview-list="row.return_photo_urls || []"
                :initial-index="i"
              />
              <span v-if="!(row.return_photo_urls || []).length" class="muted">—</span>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="detail.receiving_billing" class="billing-hint">
          原订单金额 ¥{{ detail.receiving_billing.ordered_amount ?? '—' }} · 实收计费 ¥{{ detail.receiving_billing.received_amount ?? '—' }} · 扣减 ¥{{ detail.receiving_billing.deduction_amount ?? '—' }}
        </div>
        <div v-if="detail.order_return" class="return-block">
          <div class="block-sub-title">收货少收退货单</div>
          <div class="small muted mb-2">{{ detail.order_return.return_no }} · {{ detail.order_return.status_label || returnStatusLabel(detail.order_return.status) }}</div>
          <div v-if="detail.order_return.review_note || detail.order_return.reviewed_at" class="small muted mb-2">
            审核：{{ detail.order_return.review_note || '—' }} · {{ detail.order_return.reviewed_at || '未审核' }}
          </div>
          <el-table :data="detail.order_return.lines || []" border size="small">
            <el-table-column prop="line_index" label="行" width="60" />
            <el-table-column prop="product_name" label="商品" min-width="140" show-overflow-tooltip />
            <el-table-column label="下单量" width="110">
              <template #default="{ row }">{{ receiveQtyText(row, 'ordered', 'ordered_kg') }}</template>
            </el-table-column>
            <el-table-column label="实收量" width="110">
              <template #default="{ row }">{{ receiveQtyText(row, 'received', 'received_kg') }}</template>
            </el-table-column>
            <el-table-column label="差异" width="110">
              <template #default="{ row }"><span class="receive-diff-shortage">{{ row.diff_label || `-${kgText(row.delta_kg)}` }}</span></template>
            </el-table-column>
            <el-table-column label="扣减金额" width="110">
              <template #default="{ row }">¥{{ row.deduction_amount ?? '—' }}</template>
            </el-table-column>
            <el-table-column label="原因" width="100">
              <template #default="{ row }">{{ row.reason_label || shortageReasonLabel(row.reason_code) }}</template>
            </el-table-column>
          </el-table>
        </div>
        <div v-if="hasReceiveSignatures" class="sig-block">
          <div class="block-sub-title">收货双签</div>
          <div class="sig-grid">
            <div v-if="receiveSignatures.warehouse">
              <div class="muted small">收货方</div>
              <TraceImagePreview :src="receiveSignatures.warehouse" fit="contain" class="sig-img" :preview-list="[receiveSignatures.warehouse]" />
            </div>
            <div v-if="receiveSignatures.carrier">
              <div class="muted small">送货方</div>
              <TraceImagePreview :src="receiveSignatures.carrier" fit="contain" class="sig-img" :preview-list="[receiveSignatures.carrier]" />
            </div>
          </div>
        </div>
      </el-card>

      <el-row :gutter="16" class="mb-3">
        <el-col :span="colSpan">
          <el-card shadow="never" class="h-full">
            <template #header>
              <div class="timeline-card-head">
                <span class="font-semibold">流程时间线</span>
                <span class="muted small">订单、配送、收货与结算进度</span>
              </div>
            </template>
            <el-timeline v-if="timelineEvents.length" class="process-timeline">
              <el-timeline-item
                v-for="(ev, i) in timelineEvents"
                :key="i"
                :timestamp="ev.created_at ? formatChinaDateTime(ev.created_at) : ''"
              >
                <div class="timeline-event">
                  <div class="timeline-event-head">
                    <span class="timeline-title">{{ timelineTitle(ev) }}</span>
                    <el-tag size="small" :type="timelineTypeTag(ev.event_type)">
                      {{ timelineTypeLabel(ev.event_type) }}
                    </el-tag>
                  </div>
                  <div v-if="ev.from_status || ev.to_status" class="timeline-flow muted small">
                    <span v-if="ev.from_status">{{ ev.from_status }}</span>
                    <span v-if="ev.from_status && ev.to_status"> → </span>
                    <span v-if="ev.to_status">{{ ev.to_status }}</span>
                  </div>
                  <div class="timeline-actor">操作方：{{ timelineActor(ev) }}</div>
                  <div v-if="ev.description" class="timeline-desc">{{ ev.description }}</div>
                </div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else description="暂无流程记录" :image-size="60" />
          </el-card>
        </el-col>
        <el-col :span="colSpan">
          <el-card v-if="complaintTickets.length" shadow="never" class="h-full">
            <template #header><span class="font-semibold">售后处理进度</span></template>
            <div v-for="t in complaintTickets" :key="t.ticket_id" class="complaint-flow-block">
              <div class="small muted mb-2">工单 #{{ t.ticket_id }} · {{ t.status }}</div>
              <ComplaintProgress :phase="t.phase" />
              <div v-if="t.operation_resolution" class="small mt-2">
                <span class="font-semibold">运营结案：</span>{{ t.operation_resolution }}
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <div class="actions">
        <el-button v-if="detail.status === '下单'" type="danger" @click="cancel">取消订单</el-button>
        <el-button v-if="detail.status === '收货'" type="primary" @click="router.push(`/client/receive/${detail.id}`)">去收货</el-button>
        <el-button v-if="canComplain" type="warning" :disabled="hasOpenComplaint" @click="openComplaintDialog">
          {{ hasOpenComplaint ? '已发起售后投诉' : '售后投诉' }}
        </el-button>
      </div>
    </template>
    <el-empty v-else-if="!loading" description="暂无数据" />
  </div>

  <el-dialog v-model="complaintVisible" title="售后投诉" width="560px" :fullscreen="isMobile" destroy-on-close>
    <el-form label-width="96px">
      <el-form-item label="订单号">
        <span>{{ detail?.order_no }}</span>
      </el-form-item>
      <el-form-item label="投诉原因">
        <el-input
          v-model="complaintReason"
          type="textarea"
          :rows="5"
          maxlength="500"
          show-word-limit
          placeholder="请描述具体问题（最多 500 字）"
        />
      </el-form-item>
      <el-form-item label="图片">
        <el-upload :auto-upload="false" :show-file-list="false" accept="image/*" :on-change="onComplaintFileChange">
          <el-button :disabled="complaintImages.length >= 5">添加图片</el-button>
          <template #tip>
            <div class="muted small">最多 5 张，已上传 {{ complaintImages.length }}/5</div>
          </template>
        </el-upload>
        <div v-if="complaintImages.length" class="img-grid">
          <div v-for="(img, i) in complaintImages" :key="i" class="img-cell">
            <el-image :src="img.url" fit="cover" class="thumb" :preview-src-list="complaintImages.map((x) => x.url)" :initial-index="i" />
            <el-button text type="danger" size="small" @click="removeComplaintImage(i)">移除</el-button>
          </div>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="complaintVisible = false">取消</el-button>
      <el-button type="primary" :loading="complaintSubmitting" @click="submitComplaint">提交投诉</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.client-detail {
  display: flex;
  flex-direction: column;
}

.cockpit-bg {
  background:
    radial-gradient(circle at 10% 18%, rgba(99, 102, 241, 0.12), transparent 28%),
    radial-gradient(circle at 85% 90%, rgba(14, 116, 144, 0.1), transparent 35%),
    linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
  border-radius: 16px;
  padding: 16px 20px;
  border: 1px solid #e2e8f0;
  margin-bottom: 16px;
}
.head-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.head-tags {
  display: flex;
  gap: 8px;
  align-items: center;
}
.order-title {
  font-size: 22px;
  font-weight: 700;
  color: #1e1b4b;
  margin-top: 8px;
}
.order-sub {
  font-size: 13px;
  color: #64748b;
  margin-top: 4px;
}
.pulse-tag {
  animation: pulseTag 1.5s ease-in-out infinite;
}
@keyframes pulseTag {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.65; }
}

.progress-card {
  border-radius: 14px;
}
.cancel-hint {
  color: #94a3b8;
  font-size: 14px;
}
.stepper {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 0;
}
.step {
  flex: 1;
  text-align: center;
  position: relative;
}
.step::after {
  content: '';
  position: absolute;
  top: 10px;
  left: 50%;
  width: 100%;
  height: 3px;
  background: #e2e8f0;
  z-index: 0;
}
.step:last-child::after { display: none; }
.step-dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  margin: 0 auto 8px;
  position: relative;
  z-index: 1;
  border: 3px solid #e2e8f0;
  background: #fff;
}
.step.done .step-dot { background: #4f46e5; border-color: #4f46e5; }
.step.done::after { background: linear-gradient(90deg, #4f46e5, #6366f1); }
.step.active .step-dot {
  border-color: #6366f1;
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.25);
}
.step.active::after { background: linear-gradient(90deg, #6366f1 0%, #e2e8f0 100%); }
.step.todo .step-dot { background: #f1f5f9; }
.step-label { font-size: 12px; color: #475569; }
.step.done .step-label { color: #312e81; font-weight: 600; }
.step.active .step-label { color: #4f46e5; font-weight: 700; }

.h-full { height: 100%; }

.timeline-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.process-timeline {
  padding-top: 4px;
}

.timeline-event {
  display: flex;
  flex-direction: column;
  gap: 6px;
  line-height: 1.45;
}

.timeline-event-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.timeline-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.timeline-flow {
  color: #334155;
  font-weight: 600;
}

.timeline-actor {
  color: #475569;
  font-size: 13px;
}

.timeline-desc {
  color: #64748b;
  font-size: 12px;
  word-break: break-word;
}

.block-sub-title {
  margin: 12px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.billing-hint,
.return-block {
  margin-top: 12px;
}

.billing-hint {
  padding: 10px 12px;
  border-radius: 8px;
  background: #f8fafc;
  color: #475569;
  font-size: 13px;
}

.receive-diff-shortage {
  color: #dc2626;
  font-weight: 700;
}

.receive-diff-overage {
  color: #059669;
  font-weight: 700;
}

.receive-diff-normal {
  color: #334155;
  font-weight: 600;
}
.quality-line + .quality-line {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #e2e8f0;
}
.quality-line-head {
  font-weight: 600;
  font-size: 13px;
  color: #1e293b;
  margin-bottom: 8px;
}
.quality-row + .quality-row { margin-top: 6px; }
.complaint-flow-block + .complaint-flow-block {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed #e2e8f0;
}
.sig-block { margin-top: 12px; }
.sig-grid { display: flex; gap: 16px; flex-wrap: wrap; }
.sig-img {
  width: 140px;
  height: 90px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.actions {
  margin-top: 4px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.muted { color: #94a3b8; }
.small { font-size: 12px; }
.trace-thumb {
  width: 72px;
  height: 48px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
}
.img-grid { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 10px; }
.img-cell { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.thumb { width: 80px; height: 80px; border-radius: 8px; border: 1px solid #e2e8f0; }

/* ── Mobile styles ── */
.m-detail-page {
  font-family: var(--m-font-body);
  padding-bottom: 80px;
}
.m-status-banner {
  padding: 16px;
  color: #fff;
}
.m-status-banner__label {
  font-size: 12px;
  font-weight: 600;
  opacity: 0.85;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}
.m-status-banner__no {
  font-family: var(--m-font-display);
  font-size: 18px;
  font-weight: 800;
  margin-bottom: 2px;
}
.m-status-banner__time {
  font-size: 12px;
  opacity: 0.75;
}
.m-card {
  background: var(--m-surface-container-lowest);
  border: 1px solid var(--m-outline-variant);
  border-radius: 12px;
  margin: 10px 14px;
  padding: 14px;
}
.m-stepper-card {
  padding: 12px 10px;
}
.m-card__title {
  font-family: var(--m-font-display);
  font-size: 14px;
  font-weight: 700;
  color: var(--m-on-surface);
  margin-bottom: 10px;
}
.m-hint {
  font-size: 13px;
  color: var(--m-on-surface-variant);
}
.m-mobile-stepper {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}
.m-mobile-step {
  flex: 1;
  text-align: center;
  position: relative;
}
.m-mobile-step::after {
  content: '';
  position: absolute;
  top: 8px;
  left: 50%;
  width: 100%;
  height: 2px;
  background: var(--m-outline-variant);
}
.m-mobile-step:last-child::after { display: none; }
.m-mobile-step__dot {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  margin: 0 auto 4px;
  position: relative;
  z-index: 1;
  background: var(--m-surface-container-high);
  border: 2px solid var(--m-outline-variant);
}
.m-mobile-step.done .m-mobile-step__dot { background: var(--m-primary); border-color: var(--m-primary); }
.m-mobile-step.active .m-mobile-step__dot { border-color: var(--m-primary); box-shadow: 0 0 0 3px rgba(0,50,134,0.2); }
.m-mobile-step.done::after { background: var(--m-primary); }
.m-mobile-step__label { font-size: 10px; color: var(--m-on-surface-variant); }
.m-mobile-step.done .m-mobile-step__label { color: var(--m-primary); font-weight: 600; }
.m-mobile-step.active .m-mobile-step__label { color: var(--m-primary); font-weight: 700; }
.m-alert-item { margin: 8px 14px; }
.m-info-rows { display: flex; flex-direction: column; gap: 8px; }
.m-info-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  color: var(--m-on-surface);
}
.m-info-label {
  flex: none;
  width: 70px;
  color: var(--m-on-surface-variant);
  font-size: 12px;
}
.m-amount-big {
  font-family: var(--m-font-display);
  font-size: 24px;
  font-weight: 800;
  color: var(--m-primary);
  margin-bottom: 10px;
}
.m-items-list { display: flex; flex-direction: column; gap: 8px; }
.m-item-row {
  padding: 10px;
  background: var(--m-surface-container-low);
  border-radius: 8px;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 2px 8px;
}
.m-item-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--m-on-surface);
  grid-column: 1;
}
.m-item-sub {
  font-size: 12px;
  color: var(--m-on-surface-variant);
  grid-column: 1;
}
.m-item-amount {
  font-size: 14px;
  font-weight: 700;
  color: var(--m-primary);
  grid-column: 2;
  grid-row: 1 / 3;
  align-self: center;
  white-space: nowrap;
}
.m-timeline { display: flex; flex-direction: column; gap: 12px; }
.m-timeline-item {
  display: flex;
  gap: 10px;
  padding-left: 4px;
  position: relative;
}
.m-timeline-item::before {
  content: '';
  position: absolute;
  left: 8px;
  top: 18px;
  bottom: -12px;
  width: 1px;
  background: var(--m-outline-variant);
}
.m-timeline-item:last-child::before { display: none; }
.m-timeline-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--m-primary);
  flex: none;
  margin-top: 4px;
}
.m-timeline-body { flex: 1; min-width: 0; }
.m-timeline-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--m-on-surface);
}
.m-timeline-actor {
  font-size: 11px;
  color: var(--m-on-surface-variant);
  margin-top: 2px;
}
.m-timeline-desc {
  font-size: 12px;
  color: var(--m-on-surface-variant);
  margin-top: 2px;
}
.m-action-bar {
  position: fixed;
  bottom: calc(64px + env(safe-area-inset-bottom, 0px));
  left: 0;
  right: 0;
  display: flex;
  gap: 10px;
  padding: 10px 16px;
  background: var(--m-surface-container-lowest);
  border-top: 1px solid var(--m-outline-variant);
  z-index: 20;
}
</style>
