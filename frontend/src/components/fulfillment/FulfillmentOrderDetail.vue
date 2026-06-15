<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  orderDetailApi,
  printAllocationLabelApi,
  printAllocationLabelsApi,
  printLabelApi,
  shipOrderApi,
} from '../../api/orders'
import {
  appendQualityReportByAllocationApi,
  listQualityReportsByOrderApi,
  replaceQualityReportAttachmentApi,
  uploadQualityReportByAllocationApi,
} from '../../api/qualityReports'
import { formatChinaDateTime } from '../../utils/datetime'
import { orderStatusLabel } from '../../utils/orderStatus'
import { useUserStore } from '../../stores/user'
import { buildFulfillmentActual, dash } from '../../utils/fulfillmentMeta'
import TraceImagePreview from '../TraceImagePreview.vue'

const props = defineProps({
  shipListPath: { type: String, required: true },
  periodicReportsPath: { type: String, required: true },
})

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const detail = ref(null)
const loading = ref(false)
const printBusy = ref(false)
const selectedRows = ref([])
const allocationTableRef = ref(null)

const mergeQualityReports = (allocations, reports) => {
  const byAlloc = {}
  const legacy = {}
  const toInt = (v) => parseInt(v, 10)
  for (const r of reports || []) {
    if (r.allocation_id != null) {
      byAlloc[toInt(r.allocation_id)] = r
    } else {
      const k = `${r.product_id}:${r.supplier_id}`
      if (!legacy[k]) legacy[k] = r
    }
  }
  for (const row of allocations || []) {
    const rid = toInt(row.id)
    const pid = toInt(row.product_id)
    const sid = toInt(row.supplier_id)
    row.quality_report = byAlloc[rid] || legacy[`${pid}:${sid}`] || null
    if (row.quality_report_mode === 'periodic' && row.periodic_quality_report) {
      row.quality_covered_by = 'periodic'
      row.missing_quality = false
    } else if (row.quality_report) {
      row.quality_covered_by = 'batch'
      row.missing_quality = false
    } else {
      row.quality_covered_by = null
      row.missing_quality = true
    }
  }
}

const QR_MAX_BYTES = 20 * 1024 * 1024

function reportFileUrls(rep) {
  if (!rep) return []
  if (Array.isArray(rep.file_urls) && rep.file_urls.length) return rep.file_urls
  if (rep.file_url) return [rep.file_url]
  return []
}

function isPdfUrl(url) {
  const u = (url || '').split('?')[0].toLowerCase()
  return u.endsWith('.pdf')
}

const labelPrintCountText = (row) => {
  const n = Number(row?.label_print_count || 0)
  return n > 0 ? `已打 ${n} 次` : '未打印'
}

const load = async () => {
  loading.value = true
  try {
    const d = await orderDetailApi(route.params.id)
    let reports = []
    try {
      reports = await listQualityReportsByOrderApi(route.params.id)
    } catch {
      reports = []
    }
    mergeQualityReports(d.allocations, reports)
    detail.value = d
    selectedRows.value = []
    allocationTableRef.value?.clearSelection?.()
  } finally {
    loading.value = false
  }
}

const myUserId = computed(() => Number(userStore.userInfo?.id || 0))
const myAllocations = computed(() =>
  (detail.value?.allocations || []).filter((row) => Number(row.supplier_id || 0) === myUserId.value),
)

const qualityUploadedCount = computed(
  () => myAllocations.value.filter((r) => r.quality_report || r.quality_covered_by === 'periodic').length,
)
const qualityTotalCount = computed(() => myAllocations.value.length)

const qualityMissingAfterShip = computed(() => myAllocations.value.some((r) => r.missing_quality))
const fulfillmentActual = computed(() => buildFulfillmentActual(detail.value || {}))

const hasSelectedRows = computed(() => selectedRows.value.length > 0)

const canShip = computed(() => {
  if ((detail.value?.supplier_status || '') !== 'pending_ship') return false
  if (!detail.value?.my_can_ship_by_print) return false
  if (detail.value?.has_delivery_allocation && detail.value?.my_allocations_shipped) return false
  return true
})

const shipButtonText = computed(() =>
  canShip.value ? '发货' : (detail.value?.supplier_status || '') === 'shipped' ? '已发货' : '发货',
)

const onSelectionChange = (rows) => {
  selectedRows.value = rows || []
}

const runPrint = async (fn) => {
  if (printBusy.value) return
  printBusy.value = true
  try {
    await fn()
    ElMessage.success('标签打印已提交')
    await load()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '打印失败')
  } finally {
    printBusy.value = false
  }
}

const printAllLabels = () =>
  runPrint(() => printLabelApi(route.params.id))

const printSelectedLabels = () => {
  const ids = selectedRows.value.map((r) => Number(r.id)).filter((id) => id > 0)
  if (!ids.length) {
    ElMessage.warning('请先勾选要打印的分单行')
    return
  }
  return runPrint(() => printAllocationLabelsApi(route.params.id, ids))
}

const printRowLabel = (row) => {
  if (!row?.id) return
  return runPrint(() => printAllocationLabelApi(route.params.id, row.id))
}

const shipOrder = async () => {
  try {
    await shipOrderApi(route.params.id)
    ElMessage.success('发货成功')
    await router.push(props.shipListPath)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '发货失败')
  }
}

const buildPrintHtml = (title, rows) => {
  const body = rows
    .map(
      (row, idx) => `
      <tr>
        <td>${idx + 1}</td>
        <td>${row.line_no || '-'}</td>
        <td>${row.product_name || '-'}</td>
        <td>${row.spec || '-'}</td>
        <td>${row.unit || '-'}</td>
        <td>${row.quantity ?? '-'}</td>
        <td>${Number(row.unit_price || 0).toFixed(2)}</td>
        <td>${Number(row.amount || 0).toFixed(2)}</td>
        <td>${row.status || '-'}</td>
      </tr>
    `,
    )
    .join('')
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${title}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; padding: 20px; }
    h2 { margin: 0 0 12px; }
    .meta { margin-bottom: 12px; color: #334155; font-size: 13px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { border: 1px solid #cbd5e1; padding: 6px; text-align: left; }
    th { background: #f1f5f9; }
  </style>
</head>
<body>
  <h2>${title}</h2>
  <div class="meta">订单号：${detail.value?.order_no || '-'} ｜ 打印时间：${new Date().toLocaleString()}</div>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>原行号</th>
        <th>商品</th>
        <th>规格</th>
        <th>单位</th>
        <th>数量</th>
        <th>单价</th>
        <th>金额</th>
        <th>状态</th>
      </tr>
    </thead>
    <tbody>${body}</tbody>
  </table>
</body>
</html>`
}

const openPrintWindow = (title, rows) => {
  if (!rows?.length) {
    ElMessage.warning('当前无可打印的分单明细')
    return
  }
  const win = window.open('', '_blank', 'width=980,height=760')
  if (!win) {
    ElMessage.error('浏览器拦截了打印窗口，请允许弹窗后重试')
    return
  }
  win.document.open()
  win.document.write(buildPrintHtml(title, rows))
  win.document.close()
  win.focus()
  win.print()
}

const printMyAllocations = () => openPrintWindow('本户分包明细打印', myAllocations.value)
const goPeriodicReports = () => router.push(props.periodicReportsPath)

const uploadVisible = ref(false)
const uploadMode = ref('full')
const uploadTarget = ref(null)
const uploadReportNo = ref('')
const uploadFileList = ref([])
const uploadSubmitting = ref(false)
const existingReportUrls = ref([])

const galleryVisible = ref(false)
const galleryUrls = ref([])
const galleryIndex = ref(0)
const galleryAllocId = ref(null)

const replaceFileInput = ref(null)
let pendingReplaceAllocId = null
let pendingReplaceIndex = null

const beforeQrUpload = (rawFile) => {
  if (rawFile.size > QR_MAX_BYTES) {
    ElMessage.error('单张不能超过 20MB')
    return false
  }
  const ok =
    /^image\/(jpeg|png|gif|webp)$/i.test(rawFile.type) ||
    rawFile.type === 'application/pdf' ||
    /\.(jpe?g|png|gif|webp|pdf)$/i.test(rawFile.name || '')
  if (!ok) {
    ElMessage.error('仅支持 JPG、PNG、GIF、WebP、PDF')
    return false
  }
  return true
}

const openUpload = (row) => {
  uploadMode.value = 'full'
  uploadTarget.value = row
  uploadReportNo.value = row.quality_report?.report_no || `QR-${row.id}-${Date.now().toString().slice(-6)}`
  uploadFileList.value = []
  existingReportUrls.value = reportFileUrls(row.quality_report)
  uploadVisible.value = true
}

const openAppend = (row) => {
  if (!row.quality_report) {
    openUpload(row)
    return
  }
  uploadMode.value = 'append'
  uploadTarget.value = row
  uploadFileList.value = []
  uploadVisible.value = true
}

const openReportInNewTab = (url) => {
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}

const openGallery = (allocId, urls, startIndex = 0) => {
  if (!urls?.length) return
  galleryAllocId.value = allocId
  galleryUrls.value = [...urls]
  galleryIndex.value = Math.min(Math.max(0, startIndex), urls.length - 1)
  galleryVisible.value = true
}

const pickReplaceCurrent = () => {
  pendingReplaceAllocId = galleryAllocId.value
  pendingReplaceIndex = galleryIndex.value
  replaceFileInput.value?.click?.()
}

const onReplaceFileChange = async (e) => {
  const input = e.target
  const file = input.files?.[0]
  input.value = ''
  if (!file || pendingReplaceAllocId == null || pendingReplaceIndex == null) return
  if (!beforeQrUpload(file)) return
  try {
    const fd = new FormData()
    fd.append('file', file)
    await replaceQualityReportAttachmentApi(pendingReplaceAllocId, pendingReplaceIndex, fd)
    ElMessage.success('已替换')
    galleryVisible.value = false
    uploadVisible.value = false
    await load()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '替换失败')
  } finally {
    pendingReplaceAllocId = null
    pendingReplaceIndex = null
  }
}

const submitUpload = async () => {
  if (!uploadTarget.value?.id) return
  const raws = (uploadFileList.value || []).map((f) => f.raw).filter(Boolean)
  if (!raws.length) {
    ElMessage.warning(
      uploadMode.value === 'append' ? '请选择要追加的文件' : '请至少选择一个文件（整批上传或整批替换）',
    )
    return
  }
  uploadSubmitting.value = true
  try {
    if (uploadMode.value === 'append') {
      const fd = new FormData()
      raws.forEach((file) => fd.append('files', file))
      await appendQualityReportByAllocationApi(uploadTarget.value.id, fd)
      ElMessage.success('已追加照片')
    } else {
      const fd = new FormData()
      fd.append('allocation_id', String(uploadTarget.value.id))
      fd.append('report_no', (uploadReportNo.value || '').trim() || `QR-${uploadTarget.value.id}`)
      raws.forEach((file) => fd.append('files', file))
      await uploadQualityReportByAllocationApi(fd)
      ElMessage.success('质检报告已上传')
    }
    uploadVisible.value = false
    await load()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  } finally {
    uploadSubmitting.value = false
  }
}

onMounted(load)

watch(
  () => `${route.params.id || ''}:${route.query._notify_refresh || ''}`,
  () => {
    if (route.params.id) load()
  },
)

defineExpose({ load })
</script>

<template>
  <div v-if="detail" class="fulfillment-detail">
  <el-card v-loading="loading" class="fulfillment-card">
    <el-alert
      v-if="qualityMissingAfterShip"
      type="error"
      :closable="false"
      show-icon
      class="mb-3"
      title="质检缺失异常"
      description="本户仍有分单未上传质检报告，请尽快补传。仅当本户全部分单质检补齐后，相关异常才可能消除。"
    />
    <template #header>
      <div class="detail-header">
        <span class="font-semibold">配送分包：{{ detail.order_no }}</span>
        <el-tag
          :type="
            detail.supplier_status === 'completed' || detail.supplier_status === 'shipped'
              ? 'success'
              : detail.supplier_status === 'cancelled'
                ? 'danger'
                : 'warning'
          "
        >
          {{ detail.supplier_status_text || orderStatusLabel(detail.status) }}
        </el-tag>
      </div>
    </template>

    <el-descriptions :column="2" border>
      <el-descriptions-item label="订单号">{{ detail.order_no }}</el-descriptions-item>
      <el-descriptions-item label="本户分包金额">
        ¥{{ Number((detail.supply_portion_amount ?? detail.total_amount) || 0).toLocaleString() }}
      </el-descriptions-item>
      <el-descriptions-item label="终端收货方">{{ detail.client_name || '-' }}</el-descriptions-item>
      <el-descriptions-item label="分包配送商">{{ detail.delivery_name || '-' }}</el-descriptions-item>
      <el-descriptions-item label="期望送达日">{{ detail.expected_delivery_date || '-' }}</el-descriptions-item>
      <el-descriptions-item label="配送时段">{{ detail.expected_delivery_slot || '-' }}</el-descriptions-item>
      <el-descriptions-item label="发车车次">{{ dash(fulfillmentActual.routeNo) }}</el-descriptions-item>
      <el-descriptions-item label="配送车辆">{{ dash(fulfillmentActual.vehicleNo) }}</el-descriptions-item>
      <el-descriptions-item label="司机">{{ dash(fulfillmentActual.driverName) }}</el-descriptions-item>
      <el-descriptions-item label="实际发车">{{ formatChinaDateTime(fulfillmentActual.departedAt) }}</el-descriptions-item>
      <el-descriptions-item label="真正送达时间">{{ formatChinaDateTime(fulfillmentActual.arrivedAt) }}</el-descriptions-item>
      <el-descriptions-item label="配送状态">{{ dash(fulfillmentActual.deliveryStatus) }}</el-descriptions-item>
      <el-descriptions-item label="送货地址" :span="2">{{ detail.delivery_address || '-' }}</el-descriptions-item>
      <el-descriptions-item label="状态">{{ detail.supplier_status_text || orderStatusLabel(detail.status) }}</el-descriptions-item>
      <el-descriptions-item label="分拣状态">
        <el-tag :type="detail.my_can_ship_by_print ? 'success' : 'warning'">
          {{ detail.my_sort_status_text || (detail.my_label_printed ? '分拣完成' : '待分拣') }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="更新时间">{{ formatChinaDateTime(detail.updated_at) }}</el-descriptions-item>
      <el-descriptions-item label="分拣完成时间">{{ formatChinaDateTime(detail.my_sorted_at) || '-' }}</el-descriptions-item>
    </el-descriptions>

    <div class="actions">
      <el-button :loading="printBusy" @click="printAllLabels">打印全部标签</el-button>
      <el-button :disabled="!hasSelectedRows" :loading="printBusy" @click="printSelectedLabels">
        打印所选标签
      </el-button>
      <el-button :disabled="!myAllocations.length" @click="printMyAllocations">打印分包明细（网页）</el-button>
      <el-button :type="canShip ? 'primary' : 'default'" :disabled="!canShip" @click="shipOrder">
        {{ shipButtonText }}
      </el-button>
    </div>
    <div class="tips">
      说明：订单由终端客户下给配送商，本页为配送商分包给本户的履约任务；结算与商务关系以配送商为准。
    </div>
    <div class="tips">发货前置：每条分单至少云打印过 1 次标签即可发货。</div>
    <div class="tips">
      已打标签行：{{ detail.my_line_label_printed_count || 0 }}/{{ detail.my_line_label_total || 0 }}
      <span v-if="(detail.my_unprinted_line_count || 0) > 0">，剩余{{ detail.my_unprinted_line_count }}行未打印</span>
      <span v-if="(detail.my_total_label_print_count || 0) > 0">
        ｜累计云打印 {{ detail.my_total_label_print_count }} 次
      </span>
    </div>
    <div v-if="detail.has_delivery_allocation" class="tips">
      本户发货进度：{{ detail.my_allocation_shipped || 0 }}/{{ detail.my_allocation_total || 0 }}
    </div>
    <div v-if="myAllocations.length" class="tips">
      质检上传进度：{{ qualityUploadedCount }}/{{ qualityTotalCount }} 条分单已上传
    </div>

    <el-divider content-position="left">本户分包执行明细</el-divider>
    <div class="table-scroll">
    <el-table
      ref="allocationTableRef"
      :data="myAllocations"
      border
      size="small"
      row-key="id"
      table-layout="auto"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="48" />
      <el-table-column prop="line_no" label="原行号" width="80" />
      <el-table-column prop="product_name" label="商品" min-width="160" show-overflow-tooltip />
      <el-table-column prop="spec" label="规格" min-width="100" show-overflow-tooltip />
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
      <el-table-column label="标签打印" width="120">
        <template #default="{ row }">
          <el-tag :type="Number(row.label_print_count || 0) > 0 ? 'success' : 'warning'">
            {{ labelPrintCountText(row) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="质检报告" min-width="200">
        <template #default="{ row }">
          <template v-if="row.quality_covered_by === 'periodic' && row.periodic_quality_report">
            <div class="qr-cell">
              <div class="qr-cell-head">
                <el-tag type="success" size="small">周期报告</el-tag>
                <span class="qr-no">{{ row.periodic_quality_report.report_no }}</span>
              </div>
              <div class="qr-count">
                {{ row.periodic_quality_report.valid_from }} 至 {{ row.periodic_quality_report.valid_to }}
              </div>
              <div class="qr-actions">
                <el-button
                  type="primary"
                  link
                  size="small"
                  @click="openReportInNewTab(reportFileUrls(row.periodic_quality_report)[0])"
                >打开</el-button>
                <el-button
                  type="primary"
                  link
                  size="small"
                  @click="openGallery(row.id, reportFileUrls(row.periodic_quality_report), 0)"
                >预览</el-button>
              </div>
            </div>
          </template>
          <template v-else-if="row.quality_report">
            <div class="qr-cell">
              <div class="qr-cell-head">
                <el-tag :type="row.quality_report.status === '已通过' ? 'success' : 'info'" size="small">
                  {{ row.quality_report.status }}
                </el-tag>
                <span class="qr-no">{{ row.quality_report.report_no }}</span>
              </div>
              <div v-if="reportFileUrls(row.quality_report).length" class="qr-cell-body">
                <div
                  class="qr-thumb-hit"
                  title="点击预览"
                  @click="openGallery(row.id, reportFileUrls(row.quality_report), 0)"
                >
                  <img
                    v-if="!isPdfUrl(reportFileUrls(row.quality_report)[0])"
                    :src="reportFileUrls(row.quality_report)[0]"
                    class="qr-thumb-img"
                    alt=""
                  />
                  <span v-else class="qr-thumb-img pdf">PDF</span>
                </div>
                <span class="qr-count">共 {{ reportFileUrls(row.quality_report).length }} 张</span>
              </div>
              <div class="qr-actions">
                <el-button
                  type="primary"
                  link
                  size="small"
                  @click="openReportInNewTab(reportFileUrls(row.quality_report)[0])"
                >打开</el-button>
                <el-button
                  type="primary"
                  link
                  size="small"
                  @click="openGallery(row.id, reportFileUrls(row.quality_report), 0)"
                >预览</el-button>
                <el-button type="success" link size="small" @click="openAppend(row)">新增照片</el-button>
                <el-button type="warning" link size="small" @click="openUpload(row)">整批替换</el-button>
              </div>
            </div>
          </template>
          <template v-else-if="row.quality_report_mode === 'periodic'">
            <el-tag type="danger" size="small">缺周期质检</el-tag>
            <el-button type="primary" link size="small" class="ml-1" @click="goPeriodicReports">上传周期报告</el-button>
          </template>
          <template v-else>
            <el-tag type="danger" size="small">缺质检</el-tag>
            <el-button type="primary" link size="small" class="ml-1" @click="openUpload(row)">上传</el-button>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="110" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" :loading="printBusy" @click="printRowLabel(row)">
            打印标签
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    </div>

    <el-divider v-if="(detail.receiving_lines || []).length" content-position="left">收货称重与退货留痕</el-divider>
    <div v-if="(detail.receiving_lines || []).length" class="table-scroll">
    <el-table :data="detail.receiving_lines || []" border size="small">
      <el-table-column prop="line_no" label="行号" width="80" />
      <el-table-column prop="product_name" label="商品" min-width="180" />
      <el-table-column label="实收" width="110">
        <template #default="{ row }">{{ row.confirmed_kg ?? '-' }} kg</template>
      </el-table-column>
      <el-table-column label="少收/退货" width="130">
        <template #default="{ row }">{{ row.shortage_delta_kg ?? 0 }} kg</template>
      </el-table-column>
      <el-table-column label="原因" width="120">
        <template #default="{ row }">{{ row.shortage_reason_label || '-' }}</template>
      </el-table-column>
      <el-table-column prop="shortage_reason_detail" label="说明" min-width="160" />
      <el-table-column label="锁定照片" width="110">
        <template #default="{ row }">
          <TraceImagePreview
            v-if="row.lock_photo_url"
            :src="row.lock_photo_url"
            fit="cover"
            class="trace-thumb"
            :preview-list="[row.lock_photo_url]"
          />
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="退货证据" min-width="180">
        <template #default="{ row }">
          <template v-if="(row.return_photo_urls || []).length">
            <TraceImagePreview
              v-for="(url, i) in row.return_photo_urls"
              :key="url"
              :src="url"
              fit="cover"
              class="trace-thumb mr-1"
              :preview-list="row.return_photo_urls"
              :initial-index="i"
            />
          </template>
          <span v-else>-</span>
        </template>
      </el-table-column>
    </el-table>
    </div>

    <el-dialog
      v-model="uploadVisible"
      :title="uploadMode === 'append' ? '追加质检照片' : '上传质检报告'"
      width="620px"
      destroy-on-close
    >
      <el-alert
        v-if="uploadMode === 'append'"
        type="info"
        :closable="false"
        show-icon
        class="mb-3"
        title="追加说明"
        :description="`当前已有 ${uploadTarget && reportFileUrls(uploadTarget.quality_report).length} 张，将把所选文件追加到末尾（总数不超过 20 张）。`"
      />
      <el-alert
        v-else
        type="info"
        :closable="false"
        show-icon
        class="mb-3"
        title="上传说明"
        description="支持 JPG、PNG、GIF、WebP、PDF；单张不超过 20MB；单次最多 20 个文件。可多选一次性上传。预览中可逐张替换；「整批替换」将覆盖当前全部附件。"
      />
      <el-form label-width="96px">
        <el-form-item label="分单行ID">
          <span>{{ uploadTarget?.id }}</span>
        </el-form-item>
        <template v-if="uploadMode === 'full'">
          <el-form-item label="报告编号">
            <el-input v-model="uploadReportNo" placeholder="报告编号" />
          </el-form-item>
          <el-form-item v-if="existingReportUrls.length" label="当前附件">
            <div class="qr-dialog-thumbs">
              <template v-for="(u, i) in existingReportUrls" :key="'ex-' + i">
                <div class="qr-thumb-hit" @click="openGallery(uploadTarget?.id, existingReportUrls, i)">
                  <img v-if="!isPdfUrl(u)" :src="u" class="qr-thumb-img" alt="" />
                  <span v-else class="qr-thumb-img pdf">PDF</span>
                </div>
              </template>
              <span class="qr-count">共 {{ existingReportUrls.length }} 张 · 点击可预览/替换单张</span>
            </div>
          </el-form-item>
        </template>
        <el-form-item :label="uploadMode === 'append' ? '追加文件' : '选择文件'">
          <el-upload
            v-model:file-list="uploadFileList"
            :auto-upload="false"
            multiple
            :limit="20"
            list-type="picture-card"
            :before-upload="beforeQrUpload"
            accept=".jpg,.jpeg,.png,.gif,.webp,.pdf,image/*"
          >
            <el-icon><Plus /></el-icon>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploadSubmitting" @click="submitUpload">
          {{ uploadMode === 'append' ? '确定追加' : '提交' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="galleryVisible"
      title="质检附件预览"
      width="720px"
      append-to-body
      align-center
      destroy-on-close
      @closed="galleryUrls = []"
    >
      <div v-if="galleryUrls.length" class="gal-toolbar">
        <el-button size="small" :disabled="galleryIndex <= 0" @click="galleryIndex--">上一张</el-button>
        <span class="gal-counter">{{ galleryIndex + 1 }} / {{ galleryUrls.length }}</span>
        <el-button size="small" :disabled="galleryIndex >= galleryUrls.length - 1" @click="galleryIndex++">下一张</el-button>
        <el-button type="warning" size="small" @click="pickReplaceCurrent">替换当前张</el-button>
      </div>
      <div v-if="galleryUrls.length" class="gal-body">
        <iframe
          v-if="isPdfUrl(galleryUrls[galleryIndex])"
          :src="galleryUrls[galleryIndex]"
          class="gal-frame"
          title="pdf"
        />
        <img v-else :src="galleryUrls[galleryIndex]" class="gal-img-native" alt="" />
      </div>
    </el-dialog>

    <input
      ref="replaceFileInput"
      type="file"
      class="sr-only"
      accept=".jpg,.jpeg,.png,.gif,.webp,.pdf,image/jpeg,image/png,image/gif,image/webp,application/pdf"
      @change="onReplaceFileChange"
    />
  </el-card>
  </div>
</template>

<style scoped>
.fulfillment-detail {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
}

.fulfillment-card {
  width: 100%;
  max-width: 100%;
}

.fulfillment-card :deep(.el-card__body) {
  min-width: 0;
}

.table-scroll {
  width: 100%;
  max-width: 100%;
  overflow-x: auto;
}

.table-scroll :deep(.el-table) {
  min-width: 960px;
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.detail-header .font-semibold {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.actions {
  margin-top: 16px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tips {
  margin-top: 8px;
  font-size: 12px;
  color: #64748b;
}

.qr-no {
  margin-left: 6px;
  font-size: 12px;
  color: #475569;
}

.qr-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}

.qr-cell-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.qr-cell-body {
  display: flex;
  align-items: center;
  gap: 8px;
}

.qr-thumb-hit {
  flex-shrink: 0;
  cursor: pointer;
  line-height: 0;
}

.qr-thumb-img {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
  display: block;
  vertical-align: top;
}

.qr-thumb-img.pdf {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #f1f5f9;
  font-size: 11px;
  color: #64748b;
  box-sizing: border-box;
}

.trace-thumb {
  width: 54px;
  height: 54px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.qr-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
}

.qr-actions :deep(.el-button) {
  padding: 0 2px;
  height: auto;
  min-height: 22px;
}

.qr-dialog-thumbs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.qr-count {
  font-size: 12px;
  color: #64748b;
}

.sr-only {
  position: absolute;
  width: 0;
  height: 0;
  opacity: 0;
  pointer-events: none;
}

.gal-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin-bottom: 12px;
}

.gal-counter {
  font-size: 13px;
  color: #475569;
  min-width: 4em;
}

.gal-body {
  min-height: 360px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0f172a08;
  border-radius: 8px;
}

.gal-frame {
  width: 100%;
  height: 520px;
  border: none;
}

.gal-img-native {
  max-width: 100%;
  max-height: min(520px, 72vh);
  width: auto;
  height: auto;
  object-fit: contain;
  image-orientation: from-image;
}
</style>
