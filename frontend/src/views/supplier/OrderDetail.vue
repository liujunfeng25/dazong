<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { orderDetailApi, printAllocationLabelApi, printLabelApi, shipOrderApi } from '../../api/orders'
import { listQualityReportsByOrderApi, uploadQualityReportByAllocationApi } from '../../api/qualityReports'
import { formatChinaDateTime } from '../../utils/datetime'
import { orderStatusLabel } from '../../utils/orderStatus'
import { useUserStore } from '../../stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const detail = ref(null)
const loading = ref(false)

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
    row.missing_quality = !row.quality_report
  }
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
  } finally {
    loading.value = false
  }
}

const myUserId = computed(() => Number(userStore.userInfo?.id || 0))
const myAllocations = computed(() =>
  (detail.value?.allocations || []).filter((row) => Number(row.supplier_id || 0) === myUserId.value),
)

const qualityUploadedCount = computed(
  () => myAllocations.value.filter((r) => r.quality_report).length,
)
const qualityTotalCount = computed(() => myAllocations.value.length)

/** 顶部告警按“本户全量分单”口径：任一分单缺质检即保持告警，直到全部补齐。 */
const qualityMissingAfterShip = computed(() =>
  myAllocations.value.some((r) => r.missing_quality),
)
const canPrintLabel = computed(() => ['下单', '配货'].includes(detail.value?.status || ''))
const canShip = computed(() => {
  if ((detail.value?.supplier_status || '') !== 'pending_ship') return false
  if (!detail.value?.my_can_ship_by_print) return false
  if (detail.value?.has_delivery_allocation && detail.value?.my_allocations_shipped) return false
  return true
})
const shipButtonText = computed(() =>
  canShip.value ? '发货' : (detail.value?.supplier_status || '') === 'shipped' ? '已发货' : '发货',
)

const action = async (type, row = null) => {
  try {
    if (type === 'label') await printLabelApi(route.params.id)
    if (type === 'line-label' && row?.id) await printAllocationLabelApi(route.params.id, row.id)
    if (type === 'ship') {
      await shipOrderApi(route.params.id)
      ElMessage.success('发货成功')
      await router.push('/supplier/orders')
      return
    }
    if (type !== 'ship') ElMessage.success('操作成功')
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  }
  await load()
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

const uploadVisible = ref(false)
const uploadTarget = ref(null)
const uploadReportNo = ref('')
const uploadFile = ref(null)
const uploadSubmitting = ref(false)

const openUpload = (row) => {
  uploadTarget.value = row
  uploadReportNo.value = row.quality_report?.report_no || `QR-${row.id}-${Date.now().toString().slice(-6)}`
  uploadFile.value = null
  uploadVisible.value = true
}

const onUploadFile = (f) => {
  uploadFile.value = f?.raw || null
}

const submitUpload = async () => {
  if (!uploadTarget.value?.id) return
  if (!uploadFile.value) {
    ElMessage.warning('请选择质检文件')
    return
  }
  uploadSubmitting.value = true
  try {
    const fd = new FormData()
    fd.append('allocation_id', String(uploadTarget.value.id))
    fd.append('report_no', (uploadReportNo.value || '').trim() || `QR-${uploadTarget.value.id}`)
    fd.append('file', uploadFile.value)
    await uploadQualityReportByAllocationApi(fd)
    ElMessage.success('质检报告已上传')
    uploadVisible.value = false
    await load()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '上传失败')
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
</script>

<template>
  <el-card v-loading="loading" v-if="detail">
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
      <el-button :disabled="!canPrintLabel" @click="action('label')">打印标签，分拣完成</el-button>
      <el-button :disabled="!myAllocations.length" @click="printMyAllocations">打印本户分包明细</el-button>
      <el-button
        :type="canShip ? 'primary' : 'default'"
        :disabled="!canShip"
        @click="action('ship')"
      >
        {{ shipButtonText }}
      </el-button>
    </div>
    <div class="tips">
      说明：订单由终端客户下给配送商，本页为配送商分包给本户的履约任务；结算与商务关系以配送商为准。
    </div>
    <div class="tips">发货前置：满足其一即可向配送商标记发货——整单标签已打印，或全部行级标签均已打印。</div>
    <div class="tips">
      行级标签进度：{{ detail.my_line_label_printed_count || 0 }}/{{ detail.my_line_label_total || 0 }}
      <span v-if="(detail.my_unprinted_line_count || 0) > 0">，剩余{{ detail.my_unprinted_line_count }}行未打印</span>
    </div>
    <div v-if="detail.has_delivery_allocation" class="tips">
      本户发货进度：{{ detail.my_allocation_shipped || 0 }}/{{ detail.my_allocation_total || 0 }}
    </div>
    <div v-if="myAllocations.length" class="tips">
      质检上传进度：{{ qualityUploadedCount }}/{{ qualityTotalCount }} 条分单已上传
    </div>

    <el-divider content-position="left">本户分包执行明细</el-divider>
    <el-table :data="myAllocations" border size="small">
      <el-table-column prop="line_no" label="原行号" width="80" />
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
      <el-table-column label="标签状态" width="120">
        <template #default="{ row }">
          <el-tag :type="row.line_label_printed ? 'success' : 'warning'">
            {{ row.line_label_printed ? '已打印' : '未打印' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="质检报告" min-width="220">
        <template #default="{ row }">
          <template v-if="row.quality_report">
            <el-tag :type="row.quality_report.status === '已通过' ? 'success' : 'info'" size="small">
              {{ row.quality_report.status }}
            </el-tag>
            <span class="qr-no">{{ row.quality_report.report_no }}</span>
            <el-button
              v-if="row.quality_report.file_url"
              link
              type="primary"
              size="small"
              tag="a"
              :href="row.quality_report.file_url"
              target="_blank"
              rel="noopener"
            >预览</el-button>
            <el-button link type="warning" size="small" @click="openUpload(row)">替换</el-button>
          </template>
          <template v-else>
            <el-tag type="danger" size="small">缺质检</el-tag>
            <el-button link type="primary" size="small" @click="openUpload(row)">上传</el-button>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="打印" width="110" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="action('line-label', row)">打印行标签</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="uploadVisible" title="上传质检报告" width="480px" destroy-on-close>
      <el-form label-width="96px">
        <el-form-item label="分单行ID">
          <span>{{ uploadTarget?.id }}</span>
        </el-form-item>
        <el-form-item label="报告编号">
          <el-input v-model="uploadReportNo" placeholder="报告编号" />
        </el-form-item>
        <el-form-item label="文件">
          <el-upload :auto-upload="false" :limit="1" :on-change="onUploadFile">
            <el-button>选择文件</el-button>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploadSubmitting" @click="submitUpload">提交</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<style scoped>
.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
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
</style>
