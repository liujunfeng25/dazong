<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import ComplaintProgress from '../../components/ComplaintProgress.vue'
import OrderLogisticsMapCard from '../../components/OrderLogisticsMapCard.vue'
import QualityReportReadonly from '../../components/QualityReportReadonly.vue'
import SmartImage from '../../components/SmartImage.vue'
import TraceImagePreview from '../../components/TraceImagePreview.vue'
import { respondDeliveryComplaintApi } from '../../api/delivery'
import { deliverOrderApi, orderDetailApi, pickupOrderApi } from '../../api/orders'
import { formatChinaDateTime } from '../../utils/datetime'
import { orderStatusLabel, orderStatusTagColor } from '../../utils/orderStatus'
import { DELIVERY_STAGE_HINT, DELIVERY_STAGE_META, deliveryStageFromDetail } from '../../utils/deliveryStage'
import { buildFulfillmentActual, dash } from '../../utils/fulfillmentMeta'

const route = useRoute()
const router = useRouter()
const detail = ref(null)
const loading = ref(false)
const complaintResponse = ref('')

const FLOW = ['下单', '配货', '发货', '收货', '收货确认', '已结算']

const load = async () => {
  loading.value = true
  try {
    detail.value = await orderDetailApi(route.params.id)
    complaintResponse.value = ''
  } finally {
    loading.value = false
  }
}

const canPickup = computed(
  () => {
    if (!['下单', '配货'].includes(detail.value?.status || '')) return false
    if ((detail.value?.allocation_total || 0) <= 0) return true
    return Boolean(
      detail.value?.all_allocations_shipped &&
        detail.value?.delivery_sort_all_done &&
        detail.value?.dispatch_trip?.status === '运输中',
    )
  },
)
const canDeliver = computed(() => (detail.value?.status || '') === '发货')
const pickupBlockerText = computed(() => {
  const rows = detail.value?.pickup_blockers || []
  if (!rows.length) return ''
  return rows.map((r) => `${r.supplier_name}（剩余${r.remaining_count}行）`).join('、')
})
const deliverySortProgressText = computed(() => {
  const total = Number(detail.value?.delivery_sort_total || 0)
  const done = Number(detail.value?.delivery_sort_done || 0)
  if (total <= 0) return '无分检任务'
  return `${done}/${total}`
})
const deliverySortBlockerText = computed(() => {
  const total = Number(detail.value?.delivery_sort_total || 0)
  if (total <= 0 || detail.value?.delivery_sort_all_done) return ''
  const done = Number(detail.value?.delivery_sort_done || 0)
  return `当前仍有 ${Math.max(total - done, 0)} 条分单未完成分检`
})
const dispatchProgressText = computed(() => {
  const trip = detail.value?.dispatch_trip
  if (!trip) return '未生成发车车次'
  const loaded = Number(detail.value?.dispatch_loaded_count || 0)
  const notLoaded = Number(detail.value?.dispatch_not_loaded_count || 0)
  const total = Number(detail.value?.dispatch_items?.length || 0)
  const notLoadedText = notLoaded > 0 ? `，未随车 ${notLoaded}` : ''
  return `${trip.route_no || '-'} · ${trip.vehicle_no || '未分配车辆'} · ${trip.status || '-'} · 已装车 ${loaded}/${total}${notLoadedText}`
})
const dispatchBlockerText = computed(() => {
  if ((detail.value?.allocation_total || 0) <= 0) return ''
  if (!detail.value?.all_allocations_shipped || !detail.value?.delivery_sort_all_done) return ''
  const trip = detail.value?.dispatch_trip
  if (!trip) return '请先在智能排线中保存发车计划并分配司机车辆'
  if (trip.status !== '运输中') return `车次 ${trip.route_no || '-'} 尚未发车，请先执行整车发车或异常发车`
  return ''
})

const stepIndex = computed(() => {
  const s = detail.value?.status
  if (!s || s === '取消') return -1
  const i = FLOW.indexOf(s)
  return i >= 0 ? i : 0
})

const isCancelled = computed(() => detail.value?.status === '取消')

const currentStage = computed(() => (detail.value ? deliveryStageFromDetail(detail.value) : null))
const stageMeta = computed(() => (currentStage.value ? DELIVERY_STAGE_META[currentStage.value] : null))
const stageHint = computed(() => (currentStage.value ? DELIVERY_STAGE_HINT[currentStage.value] : ''))
/** 下一步引导动作：跳转类（去分单/排线）或就地操作类（取货/送达）；其余为等待型无动作 */
const nextAction = computed(() => {
  const code = currentStage.value
  if (code === 'await_split') return { kind: 'nav', label: '去智能分单', route: '/delivery/smart-split' }
  if (code === 'await_ship')
    return { kind: 'nav', label: '去智能排线安排车辆（建议）', route: '/delivery/smart-routing', plain: true }
  if (code === 'await_pickup') {
    if (dispatchBlockerText.value) {
      return {
        kind: 'nav',
        label: detail.value?.dispatch_trip ? '去发车计划处理车次' : '去智能排线保存车次',
        route: detail.value?.dispatch_trip ? '/delivery/smart-routing?tab=dispatch' : '/delivery/smart-routing',
        plain: true,
      }
    }
    return { kind: 'pickup', label: '确认取货' }
  }
  if (code === 'delivering') return { kind: 'deliver', label: '确认送达' }
  return null
})
const onNextAction = () => {
  const a = nextAction.value
  if (!a) return
  if (a.kind === 'nav') router.push(a.route)
  else if (a.kind === 'pickup') pickup()
  else if (a.kind === 'deliver') deliver()
}

const pctRate = (r) => `${(Number(r || 0) * 100).toFixed(2)}%`

const bannerText = computed(() => {
  const f = detail.value?.abnormal_flags
  if (!f?.missing_quality_shipped) return ''
  const n = f.missing_quality_shipped_count ?? f.missing_quality_count
  return `已有 ${n} 条分单处于「已出库」但仍缺失质检报告，订单已标异常，请督促供货商补传。`
})

const qualityCompletionText = computed(() => {
  const total = Number(detail.value?.allocations?.length || 0)
  const miss = Number(detail.value?.abnormal_flags?.missing_quality_count || 0)
  const uploaded = Math.max(total - miss, 0)
  return `${uploaded}/${total}`
})

const complaintAttachments = computed(() => detail.value?.complaint_attachments || [])
/** 分单涉及的供货商（去重）；无分单时为空，不展示所谓「主单供货商」 */
const allocationSuppliers = computed(() => detail.value?.allocation_suppliers || [])
const complaintTickets = computed(() => detail.value?.complaint_tickets || [])
const myComplaintTicket = computed(() => detail.value?.my_complaint_ticket || null)
const timelineEvents = computed(() => {
  const full = detail.value?.process_timeline || []
  if (full.length) return full
  return detail.value?.status_timeline || []
})
const timelineTypeLabel = (type) =>
  ({ order_status: '订单', allocation_status: '分单', supplier_action: '供货', audit: '留痕' })[type] || '流程'
const timelineTypeTag = (type) =>
  ({ order_status: 'primary', allocation_status: 'success', supplier_action: 'warning', audit: 'info' })[type] || 'info'
const timelineTitle = (ev) => {
  if (ev.action_title) return ev.action_title
  if (ev.from_status) return `${ev.from_status} → ${ev.to_status}`
  return ev.to_status || '流程记录'
}
const timelineActor = (ev) => {
  const name = ev.actor_name || (ev.actor_user_id != null ? `用户 #${ev.actor_user_id}` : '—')
  const role = ev.actor_role_label ? `（${ev.actor_role_label}）` : ''
  return `${name}${role}`
}
const receiveSignatures = computed(() => {
  const sig = detail.value?.receive_signatures_json || {}
  const warehouse = sig.warehouse_signature_url || sig.warehouse_signature || ''
  const carrier = sig.carrier_signature_url || sig.carrier_signature || ''
  return { warehouse, carrier }
})
const hasReceiveSignatures = computed(() => Boolean(receiveSignatures.value.warehouse || receiveSignatures.value.carrier))

const receivingStatusLabel = (status) => {
  const map = {
    confirmed: '已确认',
    pending: '待称重',
    draft: '草稿',
  }
  return map[status] || status || '—'
}

const shortageReasonLabel = (code) => {
  const map = {
    lack: '缺货',
    quality: '质量问题',
    other: '其他',
  }
  return map[code] || code || '—'
}
const kgText = (value) => (value === null || value === undefined || value === '' ? '—' : `${Number(value).toFixed(2).replace(/\.?0+$/, '')} kg`)
const receiveQtyText = (row, key, fallback) => row?.[`${key}_text`] || kgText(row?.[key] ?? row?.[fallback])
const receivingDiffClass = (row) => ({
  shortage: 'receive-diff-shortage',
  overage: 'receive-diff-overage',
})[row?.diff_type] || 'receive-diff-normal'
const receivingDiffText = (row) => row?.diff_label || kgText(row?.diff_kg_signed || 0)
const returnStatusLabel = (status) =>
  ({ pending_delivery_review: '待配送商审核', confirmed: '已确认', rejected: '已驳回', draft: '草稿', cancelled: '已取消' })[status] || status || '—'

const canSubmitComplaintResponse = computed(
  () => myComplaintTicket.value && myComplaintTicket.value.phase === 'delivery_handling',
)

const submitComplaintResponse = async () => {
  const t = myComplaintTicket.value
  if (!t?.ticket_id) return
  const text = complaintResponse.value.trim()
  if (!text) {
    ElMessage.warning('请填写处理意见')
    return
  }
  try {
    await respondDeliveryComplaintApi(t.ticket_id, { response: text })
    ElMessage.success('已提交处理意见')
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提交失败')
  }
}

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

const pickup = async () => {
  const supplierList =
    (detail.value?.allocation_status_summary || [])
      .map((i) => `${i.supplier_name}（${i.allocation_shipped}/${i.allocation_total}）`)
      .join('、') || '无分单'
  const lineCount = Number(detail.value?.allocation_total || 0)
  const sortProgress = deliverySortProgressText.value
  const dispatchProgress = dispatchProgressText.value
  try {
    await ElMessageBox.confirm(
      `订单号：${detail.value?.order_no || '-'}\n待取货分单行：${lineCount}\n供货商进度：${supplierList}\n分检进度：${sortProgress}\n发车车次：${dispatchProgress}\n\n确认取货表示您已从各供货点集货完成，主单将进入「向客户送货中」。是否继续？`,
      '确认取货',
      {
        type: 'warning',
        confirmButtonText: '确认取货',
        cancelButtonText: '取消',
        customClass: 'danger-confirm-dialog',
        confirmButtonClass: 'danger-confirm-btn',
      },
    )
  } catch {
    return
  }
  try {
    await pickupOrderApi(route.params.id)
    ElMessage.success('已确认取货，正送往客户途中')
  } catch (err) {
    const detailMsg = err?.response?.data?.detail || '确认取货失败'
    if (String(detailMsg).includes('仍有供货商未发货')) {
      ElMessage.error(`${detailMsg}，请刷新分单进度后重试。`)
    } else {
      ElMessage.error(detailMsg)
    }
    await load()
    return
  }
  await load()
}

const deliver = async () => {
  try {
    await deliverOrderApi(route.params.id)
    ElMessage.success('已确认送达')
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '确认送达失败')
  }
  await load()
}

const goBack = () => router.push('/delivery/orders')

onMounted(load)

watch(
  () => `${route.params.id || ''}:${route.query._notify_refresh || ''}`,
  () => {
    if (route.params.id) load()
  },
)
</script>

<template>
  <div v-loading="loading" class="op-detail-wrap">
    <template v-if="detail">
      <el-alert v-if="bannerText" type="error" :closable="false" show-icon class="mb-3">
        <template #default>
          <div>{{ bannerText }}</div>
          <div class="small mt-1">质检补齐进度：{{ qualityCompletionText }} 条分单已上传</div>
        </template>
      </el-alert>

      <div class="detail-head cockpit-bg">
        <div class="head-row">
          <el-button text type="primary" @click="goBack">返回订单列表</el-button>
          <div class="head-tags">
            <el-tag :color="orderStatusTagColor(detail.status)" effect="dark" size="large">
              {{ orderStatusLabel(detail.status) }}
            </el-tag>
            <el-tag v-if="detail.has_abnormal" type="danger" effect="dark" class="pulse-tag">异常</el-tag>
          </div>
        </div>
        <div class="order-title">{{ detail.order_no }}</div>
        <div class="order-sub">创建时间 {{ formatChinaDateTime(detail.created_at) }} · 更新时间 {{ formatChinaDateTime(detail.updated_at) }}</div>
      </div>

      <el-card v-if="!isCancelled && stageMeta" class="mb-3 next-step-card" shadow="never">
        <div class="ns-row">
          <div class="ns-left">
            <div class="ns-label">当前阶段</div>
            <el-tag :type="stageMeta.tagType" effect="dark" size="large">{{ stageMeta.label }}</el-tag>
          </div>
          <div class="ns-mid">
            <div class="ns-hint">{{ stageHint }}</div>
            <div v-if="currentStage === 'await_sort'" class="ns-sub">分检进度：{{ deliverySortProgressText }}</div>
            <div v-else-if="currentStage === 'await_ship'" class="ns-sub">
              供货商发货进度：{{ detail.allocation_shipped || 0 }}/{{ detail.allocation_total || 0 }}
            </div>
            <div v-else-if="currentStage === 'await_pickup'" class="ns-sub">发车车次：{{ dispatchProgressText }}</div>
          </div>
          <div v-if="nextAction" class="ns-right">
            <el-button
              type="primary"
              size="large"
              :plain="nextAction.plain"
              :disabled="(nextAction.kind === 'pickup' && !canPickup) || (nextAction.kind === 'deliver' && !canDeliver)"
              @click="onNextAction"
            >
              {{ nextAction.label }}
            </el-button>
          </div>
        </div>
      </el-card>

      <el-card class="mb-3 progress-card" shadow="never">
        <template #header><span class="font-semibold">订单进度</span></template>
        <div v-if="isCancelled" class="cancel-hint">该订单已取消，不展示履约进度。</div>
        <div v-else class="stepper">
          <div
            v-for="(st, idx) in FLOW"
            :key="st"
            class="step"
            :class="{
              done: idx < stepIndex,
              active: idx === stepIndex,
              todo: idx > stepIndex,
            }"
          >
            <div class="step-dot" />
            <div class="step-label">{{ st }}</div>
          </div>
        </div>
      </el-card>

      <div v-if="detail.allocation_total > 0" class="tips mb-2">
        供货商发货进度：{{ detail.allocation_shipped || 0 }}/{{ detail.allocation_total || 0 }}
        <span v-if="!detail.all_allocations_shipped">（需全部发货后才可确认取货）</span>
        <span class="ml-2">分检进度：{{ deliverySortProgressText }}</span>
        <span v-if="!detail.delivery_sort_all_done">（需全部分检完成后才可确认取货）</span>
        <span class="ml-2">发车车次：{{ dispatchProgressText }}</span>
        <span v-if="dispatchBlockerText">（需完成发车计划后才可确认取货）</span>
      </div>
      <el-alert
        v-if="!canPickup && pickupBlockerText"
        class="mb-3"
        type="warning"
        :closable="false"
        :title="`当前仍有供货商未完成发货：${pickupBlockerText}`"
      />
      <el-alert
        v-if="!canPickup && deliverySortBlockerText"
        class="mb-3"
        type="warning"
        :closable="false"
        :title="deliverySortBlockerText"
      />
      <el-alert
        v-if="!canPickup && dispatchBlockerText"
        class="mb-3"
        type="warning"
        :closable="false"
        :title="dispatchBlockerText"
      />

      <el-row :gutter="16" class="mb-3">
        <el-col :span="8">
          <el-card shadow="never" class="h-full">
            <template #header><span class="font-semibold">合约与上浮</span></template>
            <template v-if="detail.contract">
              <el-descriptions :column="1" border size="small">
                <el-descriptions-item label="合约号">{{ detail.contract.contract_no }}</el-descriptions-item>
                <el-descriptions-item label="有效期">
                  {{ detail.contract.period_start }} ~ {{ detail.contract.period_end }}
                </el-descriptions-item>
                <el-descriptions-item label="整单上浮率">{{ pctRate(detail.contract.price_float_rate) }}</el-descriptions-item>
                <el-descriptions-item label="本单综合上浮率">
                  {{
                    detail.contract.order_float_rate == null ? '—' : pctRate(detail.contract.order_float_rate)
                  }}
                </el-descriptions-item>
                <el-descriptions-item
                  v-if="detail.contract.order_realized_float_rate != null && detail.contract.order_realized_float_rate !== undefined"
                  label="实付较指导价"
                >
                  {{ pctRate(detail.contract.order_realized_float_rate) }}
                </el-descriptions-item>
                <el-descriptions-item
                  v-if="detail.contract.delivery_profit_amount != null && detail.contract.delivery_profit_amount !== undefined"
                  label="本单利润"
                >
                  <span class="profit-amount">¥{{ Number(detail.contract.delivery_profit_amount || 0).toFixed(2) }}</span>
                  <div class="profit-hint muted small">
                    食堂应付 ¥{{ Number(detail.contract.canteen_payable_amount || 0).toFixed(2) }}
                    − 应付供货商 ¥{{ Number(detail.contract.supplier_payable_amount || 0).toFixed(2) }}
                  </div>
                </el-descriptions-item>
              </el-descriptions>
              <div v-if="detail.contract.category_rates?.length" class="mt-2 text-sm text-slate-600">按一级品类上浮</div>
              <el-table
                v-if="detail.contract.category_rates?.length"
                :data="detail.contract.category_rates"
                size="small"
                border
                class="mt-1"
              >
                <el-table-column prop="category_name" label="品类" min-width="100" />
                <el-table-column label="上浮率" width="100">
                  <template #default="{ row }">{{ pctRate(row.float_rate) }}</template>
                </el-table-column>
              </el-table>
            </template>
            <el-empty v-else description="未匹配到期望配送日内的已中标合约" :image-size="60" />
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="never" class="h-full">
            <template #header><span class="font-semibold">交易主体</span></template>
            <div class="party-block">
              <div class="party-title">终端客户</div>
              <div>{{ detail.client?.company_name || detail.client?.username || '—' }}</div>
              <div class="muted">{{ detail.client?.contact_phone || '' }}</div>
              <div class="muted small">{{ detail.client?.address || '' }}</div>
            </div>
            <div class="party-sub-block">
              <div class="party-title">履约食堂</div>
              <div>{{ detail.canteen?.name || detail.canteen_name || '—' }}</div>
              <div class="muted">{{ detail.canteen?.contact_phone || '' }}</div>
              <div class="muted small">{{ detail.canteen?.address || detail.delivery_address || '' }}</div>
            </div>
            <el-divider />
            <div class="party-block">
              <div class="party-title">配送商</div>
              <div>{{ detail.delivery?.company_name || detail.delivery?.username || '—' }}</div>
              <div class="muted">{{ detail.delivery?.contact_phone || '' }}</div>
            </div>
            <el-divider />
            <div class="party-block">
              <div class="party-title">
                供货商（分单）
                <span v-if="allocationSuppliers.length > 1" class="muted small font-normal">
                  （共 {{ allocationSuppliers.length }} 家）
                </span>
              </div>
              <template v-if="allocationSuppliers.length">
                <div
                  v-for="s in allocationSuppliers"
                  :key="s.id"
                  class="allocation-supplier-row"
                >
                  <div>{{ s.company_name || s.username || '—' }}</div>
                  <div class="muted">{{ s.contact_phone || '' }}</div>
                </div>
              </template>
              <div v-else class="muted small">暂无分包供货商（待配送商分单后显示）</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="never" class="h-full">
            <template #header><span class="font-semibold">履约关键指标</span></template>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="约定送达日">{{ detail.expected_delivery_date || '—' }}</el-descriptions-item>
              <el-descriptions-item label="配送时段">{{ detail.expected_delivery_slot || '—' }}</el-descriptions-item>
              <el-descriptions-item label="发车车次">{{ dash(fulfillmentActual.routeNo) }}</el-descriptions-item>
              <el-descriptions-item label="配送车辆">{{ dash(fulfillmentActual.vehicleNo) }}</el-descriptions-item>
              <el-descriptions-item label="司机">{{ dash(fulfillmentActual.driverName) }}</el-descriptions-item>
              <el-descriptions-item label="计划发车">{{ dash(fulfillmentActual.plannedDeparture) }}</el-descriptions-item>
              <el-descriptions-item label="实际发车">{{ formatChinaDateTime(fulfillmentActual.departedAt) }}</el-descriptions-item>
              <el-descriptions-item label="真正送达时间">{{ formatChinaDateTime(fulfillmentActual.arrivedAt) }}</el-descriptions-item>
              <el-descriptions-item label="配送状态">{{ dash(fulfillmentActual.deliveryStatus) }}</el-descriptions-item>
              <el-descriptions-item label="服务时长">{{ detail.service_duration_min }} 分钟</el-descriptions-item>
              <el-descriptions-item label="订单总额">¥{{ Number(detail.total_amount || 0).toLocaleString() }}</el-descriptions-item>
              <el-descriptions-item label="总重/总体积">
                {{ detail.total_weight_kg ?? '—' }} kg / {{ detail.total_volume_m3 ?? '—' }} m³
              </el-descriptions-item>
              <el-descriptions-item label="收货称重合计">{{ detail.receiving_total_kg ?? '—' }} kg</el-descriptions-item>
              <el-descriptions-item label="称重行确认">{{ detail.receiving_confirmed_count }}/{{ detail.receiving_total_lines }}</el-descriptions-item>
              <el-descriptions-item label="缺斤少两行数">{{ detail.shortage_line_count || 0 }}</el-descriptions-item>
            </el-descriptions>
            <div v-if="hasReceiveSignatures" class="sig-block mt-2">
              <div class="small font-semibold mb-1">双签</div>
              <div class="sig-grid">
                <div v-if="receiveSignatures.warehouse">
                  <div class="muted small">收货方</div>
                  <SmartImage
                    :src="receiveSignatures.warehouse"
                    fit="contain"
                    class="sig-img"
                    :preview-src-list="[receiveSignatures.warehouse]"
                  />
                </div>
                <div v-if="receiveSignatures.carrier">
                  <div class="muted small">送货方</div>
                  <SmartImage
                    :src="receiveSignatures.carrier"
                    fit="contain"
                    class="sig-img"
                    :preview-src-list="[receiveSignatures.carrier]"
                  />
                </div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-card class="mb-3" shadow="never">
        <template #header><span class="font-semibold">送货地址</span></template>
        {{ detail.delivery_address || '—' }}
      </el-card>

      <el-row :gutter="16" class="mb-3">
        <el-col :span="14">
          <el-card shadow="never" class="mb-3">
            <template #header><span class="font-semibold">订单明细</span></template>
            <el-table :data="detail.order_items || []" border size="small">
              <el-table-column prop="line_no" label="行号" width="60" />
              <el-table-column prop="product_name" label="商品" min-width="160" />
              <el-table-column prop="spec" label="规格" width="100" />
              <el-table-column prop="unit" label="单位" width="70" />
              <el-table-column prop="quantity" label="数量" width="90" />
              <el-table-column label="单价" width="100">
                <template #default="{ row }">¥{{ Number(row.unit_price || 0).toFixed(2) }}</template>
              </el-table-column>
              <el-table-column label="金额" width="110">
                <template #default="{ row }">¥{{ Number(row.amount || 0).toLocaleString() }}</template>
              </el-table-column>
              <el-table-column label="拆单" width="90">
                <template #default="{ row }">
                  <el-tag v-if="(detail.line_alloc_groups || []).find((g) => g.line_no === row.line_no)?.is_split" type="warning" size="small">已拆</el-tag>
                  <span v-else>否</span>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <el-card shadow="never">
            <template #header>
              <span class="font-semibold">分单与质检</span>
              <span class="muted small ml-2">每条分单需对应一份质检报告</span>
            </template>
            <div v-for="grp in detail.line_alloc_groups || []" :key="grp.line_no" class="line-group mb-4">
              <div class="line-group-head">
                <span class="font-medium">第 {{ grp.line_no }} 行 · {{ grp.product_name }}</span>
                <el-tag v-if="grp.is_split" type="warning" size="small">拆成 {{ grp.allocations?.length }} 条分单</el-tag>
                <el-tag v-else type="success" size="small">未拆单（1 条分单）</el-tag>
              </div>
              <el-table :data="grp.allocations || []" border size="small">
                <el-table-column prop="id" label="分单ID" width="80" />
                <el-table-column prop="supplier_name" label="分包供货商" min-width="140" />
                <el-table-column prop="quantity" label="数量" width="80" />
                <el-table-column label="单价" width="100">
                  <template #default="{ row }">¥{{ Number(row.unit_price || 0).toFixed(2) }}</template>
                </el-table-column>
                <el-table-column label="金额" width="110">
                  <template #default="{ row }">¥{{ Number(row.amount || 0).toLocaleString() }}</template>
                </el-table-column>
                <el-table-column prop="status" label="分单状态" width="110" />
                <el-table-column label="质检" min-width="260">
                  <template #default="{ row }">
                    <QualityReportReadonly
                      :quality-report="row.quality_report"
                      :missing-quality-shipped="row.missing_quality_shipped"
                    />
                  </template>
                </el-table-column>
              </el-table>
            </div>
            <el-empty v-if="!(detail.line_alloc_groups || []).length" description="暂无分单数据" />
          </el-card>
        </el-col>
        <el-col :span="10">
          <OrderLogisticsMapCard
            class="mb-3"
            :order-id="detail.id"
            :tracking="detail.logistics_tracking"
            title="在途物流"
          />

          <el-card shadow="never" class="mb-3">
            <template #header>
              <div class="timeline-card-head">
                <span class="font-semibold">流程时间线</span>
                <span class="muted small">订单流转、分单、分检、称重与结算留痕</span>
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

          <el-card v-if="complaintAttachments.length" shadow="never" class="mb-3 complaint-proof-card">
            <template #header><span class="font-semibold">售后投诉凭证</span></template>
            <div v-for="block in complaintAttachments" :key="block.ticket_id" class="complaint-block">
              <div class="complaint-meta small muted">
                工单 #{{ block.ticket_id }} · {{ block.status }}
                <span v-if="block.created_at"> · {{ formatChinaDateTime(block.created_at) }}</span>
              </div>
              <div v-if="block.description" class="complaint-desc small">{{ block.description }}</div>
              <div class="complaint-img-row">
                <SmartImage
                  v-for="(url, i) in block.images"
                  :key="`${block.ticket_id}-${i}`"
                  :src="url"
                  :preview-src-list="block.images"
                  :initial-index="i"
                  fit="cover"
                  class="complaint-thumb"
                  preview-teleported
                />
              </div>
            </div>
          </el-card>

          <el-card v-if="complaintTickets.length" shadow="never" class="mb-3">
            <template #header><span class="font-semibold">客诉处理进度</span></template>
            <div v-for="t in complaintTickets" :key="t.ticket_id" class="complaint-flow-block mb-4">
              <div class="small muted mb-2">工单 #{{ t.ticket_id }} · {{ t.status }}</div>
              <ComplaintProgress :phase="t.phase" />
              <div v-if="t.delivery_response" class="small mt-2">
                <span class="font-semibold">配送意见：</span>{{ t.delivery_response }}
              </div>
              <div v-if="t.operation_resolution" class="small mt-1">
                <span class="font-semibold">运营结案：</span>{{ t.operation_resolution }}
              </div>
            </div>
          </el-card>

          <el-card v-if="myComplaintTicket" shadow="never" class="mb-3">
            <template #header><span class="font-semibold">售后投诉处理</span></template>
            <ComplaintProgress :phase="myComplaintTicket.phase" />
            <div class="small muted mt-2 mb-2">工单 #{{ myComplaintTicket.ticket_id }}</div>
            <div class="small mb-2">{{ myComplaintTicket.description }}</div>
            <div v-if="canSubmitComplaintResponse" class="mt-2">
              <el-input v-model="complaintResponse" type="textarea" :rows="4" placeholder="请填写处理意见" />
              <el-button class="mt-2" type="primary" @click="submitComplaintResponse">提交处理意见</el-button>
            </div>
            <el-alert
              v-else-if="myComplaintTicket.phase === 'operation_review'"
              type="info"
              :closable="false"
              title="已提交处理意见，等待运营审核结案"
              class="mt-2"
            />
          </el-card>

          <el-card v-if="detail.order_return" shadow="never">
            <template #header><span class="font-semibold">收货少收退货单</span></template>
            <div class="small mb-2">{{ detail.order_return.return_no }} · {{ detail.order_return.status_label || returnStatusLabel(detail.order_return.status) }}</div>
            <div v-if="detail.order_return.review_note || detail.order_return.reviewed_at" class="small muted mb-2">
              审核：{{ detail.order_return.review_note || '—' }} · {{ detail.order_return.reviewed_at || '未审核' }}
            </div>
            <el-table :data="detail.order_return.lines || []" border size="small">
              <el-table-column prop="line_index" label="行" width="50" />
              <el-table-column prop="product_name" label="商品" min-width="120" />
              <el-table-column label="下单量" width="110">
                <template #default="{ row }">{{ receiveQtyText(row, 'ordered', 'ordered_kg') }}</template>
              </el-table-column>
              <el-table-column label="实收量" width="110">
                <template #default="{ row }">{{ receiveQtyText(row, 'received', 'received_kg') }}</template>
              </el-table-column>
              <el-table-column label="差异" width="110">
                <template #default="{ row }"><span class="receive-diff-shortage">{{ row.diff_label || `-${kgText(row.delta_kg)}` }}</span></template>
              </el-table-column>
              <el-table-column label="扣减金额" width="100">
                <template #default="{ row }">¥{{ row.deduction_amount ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="原因" width="90">
                <template #default="{ row }">{{ row.reason_label || shortageReasonLabel(row.reason_code) }}</template>
              </el-table-column>
              <el-table-column prop="reason_detail" label="说明" min-width="140" show-overflow-tooltip />
              <el-table-column label="证据照片" min-width="150">
                <template #default="{ row }">
                  <SmartImage
                    v-for="(url, i) in (row.photo_urls || [])"
                    :key="url"
                    :src="url"
                    fit="cover"
                    class="trace-thumb mr-1"
                    :preview-src-list="row.photo_urls || []"
                    :initial-index="i"
                  />
                  <span v-if="!(row.photo_urls || []).length" class="muted">—</span>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never" class="mb-3">
        <template #header><span class="font-semibold">收货称重明细</span></template>
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
          <el-table-column prop="shortage_reason_detail" label="说明" min-width="160" show-overflow-tooltip />
          <el-table-column label="锁定照片" min-width="120">
            <template #default="{ row }">
              <TraceImagePreview v-if="row.lock_photo_url" :src="row.lock_photo_url" fit="cover" class="trace-thumb" :preview-list="[row.lock_photo_url]" />
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="退货照片" min-width="150">
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
          <el-table-column label="确认时间" min-width="160">
            <template #default="{ row }">{{ row.confirmed_at ? formatChinaDateTime(row.confirmed_at) : '—' }}</template>
          </el-table-column>
        </el-table>
        <div v-if="detail.receiving_billing" class="billing-hint">
          原订单金额 ¥{{ detail.receiving_billing.ordered_amount ?? '—' }} · 实收计费 ¥{{ detail.receiving_billing.received_amount ?? '—' }} · 扣减 ¥{{ detail.receiving_billing.deduction_amount ?? '—' }}
        </div>
        <div class="receive-signatures mt-3">
          <div class="small font-semibold mb-2">收货双签</div>
          <div v-if="hasReceiveSignatures" class="receive-signature-grid">
            <div class="receive-signature-card">
              <div class="muted small mb-1">收货方签字</div>
              <TraceImagePreview
                v-if="receiveSignatures.warehouse"
                :src="receiveSignatures.warehouse"
                fit="contain"
                class="receive-signature-img"
                :preview-list="[receiveSignatures.warehouse]"
              />
              <span v-else class="muted">—</span>
            </div>
            <div class="receive-signature-card">
              <div class="muted small mb-1">送货方签字</div>
              <TraceImagePreview
                v-if="receiveSignatures.carrier"
                :src="receiveSignatures.carrier"
                fit="contain"
                class="receive-signature-img"
                :preview-list="[receiveSignatures.carrier]"
              />
              <span v-else class="muted">—</span>
            </div>
          </div>
          <span v-else class="muted">—</span>
        </div>
      </el-card>

      <el-descriptions :column="3" border class="mb-3 legacy-desc">
        <el-descriptions-item label="客户名称">{{ detail.client_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="送货地址">{{ detail.delivery_address || '-' }}</el-descriptions-item>
        <el-descriptions-item label="配送时间">{{ expectedDeliveryText }}</el-descriptions-item>
      </el-descriptions>

      <el-divider content-position="left">供货商分单进度</el-divider>
      <el-table :data="detail.allocation_status_summary || []" border size="small" class="mb-3">
        <el-table-column prop="supplier_name" label="供货商" min-width="180" />
        <el-table-column label="该单金额" width="140">
          <template #default="{ row }">¥{{ Number(row.total_amount || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="进度" width="180">
          <template #default="{ row }">{{ row.allocation_shipped }}/{{ row.allocation_total }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.all_shipped ? 'success' : 'warning'">{{ row.all_shipped ? '已完成' : '待完成' }}</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <el-divider content-position="left">分单执行明细（扁平）</el-divider>
      <el-table :data="detail.allocations || []" border size="small" class="mb-3">
        <el-table-column prop="line_no" label="原行号" width="80" />
        <el-table-column prop="supplier_name" label="供货商" min-width="180" />
        <el-table-column prop="product_name" label="商品" min-width="220" />
        <el-table-column prop="spec" label="规格" min-width="140" />
        <el-table-column prop="unit" label="单位" width="90" />
        <el-table-column prop="quantity" label="分配数量" width="110" />
        <el-table-column label="分配单价" width="120">
          <template #default="{ row }">¥{{ Number(row.unit_price || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="分配金额" width="130">
          <template #default="{ row }">¥{{ Number(row.amount || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="分单状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.status === '已出库' ? 'success' : 'info'">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <el-divider content-position="left">地图（可折叠占位）</el-divider>
      <div class="text-sm text-gray-600 mb-2">当前以明细复核为主，地图模块暂保留占位。</div>
      <div class="map-placeholder mt-2 bg-gray-100 flex items-center justify-center">地图区域占位</div>
    </template>
    <el-empty v-else-if="!loading" description="暂无数据" />
  </div>
</template>

<style scoped>
.op-detail-wrap {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.tips {
  font-size: 12px;
  color: #64748b;
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

.detail-head .head-row {
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
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.65;
  }
}

.progress-card {
  border-radius: 14px;
}

.next-step-card {
  border-radius: 14px;
  border: 1px solid #c7d2fe;
  background: linear-gradient(180deg, #f5f7ff 0%, #eef2ff 100%);
}

.ns-row {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
}

.ns-left {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ns-label {
  font-size: 12px;
  color: #64748b;
}

.ns-mid {
  flex: 1;
  min-width: 200px;
}

.ns-hint {
  font-size: 14px;
  color: #1e293b;
  font-weight: 500;
  line-height: 1.5;
}

.ns-sub {
  font-size: 12px;
  color: #64748b;
  margin-top: 4px;
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

.step:last-child::after {
  display: none;
}

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

.step.done .step-dot {
  background: #4f46e5;
  border-color: #4f46e5;
}

.step.done::after {
  background: linear-gradient(90deg, #4f46e5, #6366f1);
}

.step.active .step-dot {
  border-color: #6366f1;
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.25);
  animation: glowDot 2s ease-in-out infinite;
}

.step.active::after {
  background: linear-gradient(90deg, #6366f1 0%, #e2e8f0 100%);
}

.step.todo .step-dot {
  background: #f1f5f9;
}

.step-label {
  font-size: 12px;
  color: #475569;
}

.step.done .step-label {
  color: #312e81;
  font-weight: 600;
}

.step.active .step-label {
  color: #4f46e5;
  font-weight: 700;
}

@keyframes glowDot {
  0%,
  100% {
    box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.2);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(99, 102, 241, 0.12);
  }
}

.party-block {
  font-size: 14px;
}

.party-sub-block {
  margin-top: 12px;
  padding: 10px 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 14px;
}

.party-title {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 4px;
}

.allocation-supplier-row + .allocation-supplier-row {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #e2e8f0;
}

.profit-amount {
  font-weight: 600;
  color: #0f766e;
}

.profit-hint {
  margin-top: 4px;
  line-height: 1.4;
}

.muted {
  color: #64748b;
}

.muted.small,
.small {
  font-size: 12px;
}

.sig-grid {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.sig-img {
  width: 120px;
  height: 80px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.line-group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.h-full {
  height: 100%;
}

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

.billing-hint {
  margin-top: 12px;
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

.complaint-block + .complaint-block {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed #e2e8f0;
}

.complaint-meta {
  margin-bottom: 6px;
}

.complaint-desc {
  color: #334155;
  margin-bottom: 10px;
  line-height: 1.5;
}

.complaint-img-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.complaint-thumb {
  width: 88px;
  height: 88px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  cursor: zoom-in;
  background: #f8fafc;
}

.trace-thumb {
  width: 72px;
  height: 48px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  cursor: zoom-in;
}

.receive-signatures {
  border-top: 1px solid #e2e8f0;
  padding-top: 12px;
}

.receive-signature-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(180px, 1fr));
  gap: 12px;
}

.receive-signature-card {
  min-height: 96px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px;
  background: #f8fafc;
}

.receive-signature-img {
  width: 100%;
  height: 96px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #fff;
  cursor: zoom-in;
}

.complaint-flow-block + .complaint-flow-block {
  border-top: 1px dashed #e2e8f0;
  padding-top: 12px;
}

.map-placeholder {
  min-height: 200px;
  border-radius: 8px;
  color: #64748b;
  font-size: 14px;
}

.legacy-desc {
  margin-top: 8px;
}

</style>
