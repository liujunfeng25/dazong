<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ComplaintProgress from '../../components/ComplaintProgress.vue'
import { operationOrderDetailApi } from '../../api/operation'
import { formatChinaDateTime } from '../../utils/datetime'
import { orderMainStatusTagType, orderStatusLabel } from '../../utils/orderStatus'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const detail = ref(null)

const FLOW = ['下单', '配货', '发货', '收货', '收货确认', '已结算']

const load = async () => {
  loading.value = true
  try {
    detail.value = await operationOrderDetailApi(route.params.id)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载失败')
    detail.value = null
  } finally {
    loading.value = false
  }
}

const stepIndex = computed(() => {
  const s = detail.value?.status
  if (!s || s === '取消') return -1
  const i = FLOW.indexOf(s)
  return i >= 0 ? i : 0
})

const isCancelled = computed(() => detail.value?.status === '取消')

const pctRate = (r) => `${(Number(r || 0) * 100).toFixed(2)}%`

const bannerText = computed(() => {
  const f = detail.value?.abnormal_flags
  if (!f?.missing_quality_shipped) return ''
  const n = f.missing_quality_shipped_count ?? f.missing_quality_count
  return `已有 ${n} 条分单处于「已出库」（已从供货商发出）但仍缺失质检报告，订单已标异常，请督促供货商补传。`
})

const qualityCompletionText = computed(() => {
  const total = Number(detail.value?.allocations?.length || 0)
  const miss = Number(detail.value?.abnormal_flags?.missing_quality_count || 0)
  const uploaded = Math.max(total - miss, 0)
  return `${uploaded}/${total}`
})

/** 售后投诉工单附图（来自运营订单详情接口 complaint_attachments） */
const complaintAttachments = computed(() => detail.value?.complaint_attachments || [])
/** 分单涉及的供货商（去重）；无分单时为空 */
const allocationSuppliers = computed(() => detail.value?.allocation_suppliers || [])
const complaintTickets = computed(() => detail.value?.complaint_tickets || [])

const goBack = () => router.push('/operation/orders')

onMounted(load)
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
            <el-tag :type="orderMainStatusTagType(detail.status)" size="large">
              {{ orderStatusLabel(detail.status) }}
            </el-tag>
            <el-tag v-if="detail.has_abnormal" type="danger" effect="dark" class="pulse-tag">异常</el-tag>
          </div>
        </div>
        <div class="order-title">{{ detail.order_no }}</div>
        <div class="order-sub">创建时间 {{ formatChinaDateTime(detail.created_at) }} · 更新时间 {{ formatChinaDateTime(detail.updated_at) }}</div>
      </div>

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
                <el-descriptions-item label="该单上浮率（合约加权）">
                  {{
                    detail.contract.order_float_rate == null
                      ? '—'
                      : pctRate(detail.contract.order_float_rate)
                  }}
                </el-descriptions-item>
                <el-descriptions-item
                  v-if="detail.contract.order_realized_float_rate != null && detail.contract.order_realized_float_rate !== undefined"
                  label="实付较指导价"
                >
                  {{ pctRate(detail.contract.order_realized_float_rate) }}
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
              <el-descriptions-item label="服务时长">{{ detail.service_duration_min }} 分钟</el-descriptions-item>
              <el-descriptions-item label="订单总额">¥{{ Number(detail.total_amount || 0).toLocaleString() }}</el-descriptions-item>
              <el-descriptions-item label="总重/总体积">
                {{ detail.total_weight_kg ?? '—' }} kg / {{ detail.total_volume_m3 ?? '—' }} m³
              </el-descriptions-item>
              <el-descriptions-item label="收货称重合计">{{ detail.receiving_total_kg ?? '—' }} kg</el-descriptions-item>
              <el-descriptions-item label="称重行确认">{{ detail.receiving_confirmed_count }}/{{ detail.receiving_total_lines }}</el-descriptions-item>
              <el-descriptions-item label="缺斤少两行数">{{ detail.shortage_line_count || 0 }}</el-descriptions-item>
            </el-descriptions>
            <div v-if="detail.receive_signatures_json" class="sig-block mt-2">
              <div class="small font-semibold mb-1">双签</div>
              <div class="sig-grid">
                <div v-if="detail.receive_signatures_json.warehouse_signature">
                  <div class="muted small">收货方</div>
                  <el-image
                    :src="detail.receive_signatures_json.warehouse_signature"
                    fit="contain"
                    class="sig-img"
                    :preview-src-list="[detail.receive_signatures_json.warehouse_signature]"
                  />
                </div>
                <div v-if="detail.receive_signatures_json.carrier_signature">
                  <div class="muted small">送货方</div>
                  <el-image
                    :src="detail.receive_signatures_json.carrier_signature"
                    fit="contain"
                    class="sig-img"
                    :preview-src-list="[detail.receive_signatures_json.carrier_signature]"
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
              <span class="muted small ml-2">每条分单需对应一份质检报告；发货后仍缺失将标异常</span>
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
                <el-table-column label="质检" min-width="200">
                  <template #default="{ row }">
                    <template v-if="row.quality_report">
                      <el-tag :type="row.quality_report.status === '已通过' ? 'success' : 'info'" size="small">
                        {{ row.quality_report.status }}
                      </el-tag>
                      <span class="small ml-1">{{ row.quality_report.report_no }}</span>
                      <el-button
                        v-if="row.quality_report.file_url"
                        link
                        type="primary"
                        size="small"
                        tag="a"
                        :href="row.quality_report.file_url"
                        target="_blank"
                        rel="noopener"
                      >打开</el-button>
                    </template>
                    <template v-else>
                      <el-tag type="danger" size="small">缺质检</el-tag>
                      <el-tag
                        v-if="row.missing_quality_shipped"
                        type="danger"
                        effect="plain"
                        size="small"
                        class="ml-1"
                      >异常</el-tag>
                    </template>
                  </template>
                </el-table-column>
              </el-table>
            </div>
            <el-empty v-if="!(detail.line_alloc_groups || []).length" description="暂无分单数据" />
          </el-card>
        </el-col>
        <el-col :span="10">
          <el-card shadow="never" class="mb-3">
            <template #header><span class="font-semibold">在途物流</span></template>
            <el-descriptions v-if="detail.delivery_record" :column="1" border size="small">
              <el-descriptions-item label="司机">{{ detail.delivery_record.driver_name }}</el-descriptions-item>
              <el-descriptions-item label="车牌">{{ detail.delivery_record.vehicle_no }}</el-descriptions-item>
              <el-descriptions-item label="状态">{{ detail.delivery_record.status }}</el-descriptions-item>
              <el-descriptions-item label="发车">{{ detail.delivery_record.departed_at || '—' }}</el-descriptions-item>
              <el-descriptions-item label="到达">{{ detail.delivery_record.arrived_at || '—' }}</el-descriptions-item>
            </el-descriptions>
            <el-empty v-else description="暂无配送执行记录" :image-size="60" />
          </el-card>

          <el-card shadow="never" class="mb-3">
            <template #header><span class="font-semibold">状态时间线</span></template>
            <el-timeline>
              <el-timeline-item
                v-for="(ev, i) in detail.status_timeline || []"
                :key="i"
                :timestamp="ev.created_at ? formatChinaDateTime(ev.created_at) : ''"
              >
                <span v-if="ev.from_status">{{ ev.from_status }} → </span>{{ ev.to_status }}
                <span class="muted small">（操作人 #{{ ev.actor_user_id }}）</span>
              </el-timeline-item>
            </el-timeline>
          </el-card>

          <el-card v-if="complaintAttachments.length" shadow="never" class="mb-3 complaint-proof-card">
            <template #header><span class="font-semibold">售后投诉凭证</span></template>
            <div
              v-for="block in complaintAttachments"
              :key="block.ticket_id"
              class="complaint-block"
            >
              <div class="complaint-meta small muted">
                工单 #{{ block.ticket_id }} · {{ block.status }}
                <span v-if="block.created_at"> · {{ formatChinaDateTime(block.created_at) }}</span>
              </div>
              <div v-if="block.description" class="complaint-desc small">{{ block.description }}</div>
              <div class="complaint-img-row">
                <el-image
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
              <div v-if="t.description" class="small mt-2">投诉：{{ t.description }}</div>
              <div v-if="t.delivery_response" class="small mt-2">
                <span class="font-semibold">配送意见：</span>{{ t.delivery_response }}
              </div>
              <div v-if="t.operation_resolution" class="small mt-2">
                <span class="font-semibold">运营结案：</span>{{ t.operation_resolution }}
              </div>
            </div>
          </el-card>

          <el-card v-if="detail.order_return" shadow="never">
            <template #header><span class="font-semibold">缺收退货单</span></template>
            <div class="small mb-2">{{ detail.order_return.return_no }} · {{ detail.order_return.status }}</div>
            <el-table :data="detail.order_return.lines || []" border size="small">
              <el-table-column prop="line_index" label="行" width="50" />
              <el-table-column prop="product_name" label="商品" min-width="120" />
              <el-table-column prop="delta_kg" label="差额(kg)" width="100" />
              <el-table-column prop="reason_code" label="原因码" width="90" />
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never">
        <template #header><span class="font-semibold">收货称重明细</span></template>
        <el-table :data="detail.receiving_lines || []" border size="small">
          <el-table-column prop="line_index" label="行" width="60" />
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column prop="draft_kg" label="草稿(kg)" width="100" />
          <el-table-column prop="confirmed_kg" label="确认(kg)" width="100" />
          <el-table-column prop="shortage_delta_kg" label="差额(kg)" width="100" />
          <el-table-column prop="shortage_reason_code" label="原因码" width="100" />
          <el-table-column prop="shortage_reason_detail" label="说明" min-width="160" show-overflow-tooltip />
          <el-table-column label="确认时间" min-width="160">
            <template #default="{ row }">{{ row.confirmed_at ? formatChinaDateTime(row.confirmed_at) : '—' }}</template>
          </el-table-column>
        </el-table>
      </el-card>
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

.complaint-flow-block + .complaint-flow-block {
  border-top: 1px dashed #e2e8f0;
  padding-top: 12px;
}
</style>
