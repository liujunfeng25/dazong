<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { factoryOrderDetailApi } from '../../api/factory'
import {
  listQualityReportsByOrderApi,
  uploadQualityReportByAllocationApi,
} from '../../api/qualityReports'

const route = useRoute()
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
      const k = `${r.product_id}`
      if (!legacy[k]) legacy[k] = r
    }
  }
  for (const row of allocations || []) {
    const aid = toInt(row.allocation_id)
    const pid = toInt(row.product_id)
    row.quality_report = byAlloc[aid] || legacy[`${pid}`] || null
    row.missing_quality = !row.quality_report
  }
}

const load = async () => {
  loading.value = true
  try {
    const d = await factoryOrderDetailApi(route.params.id)
    let reports = []
    try {
      reports = await listQualityReportsByOrderApi(route.params.id)
    } catch {
      reports = []
    }
    detail.value = d
    mergeQualityReports(d.items, reports)
  } finally {
    loading.value = false
  }
}

const uploadVisible = ref(false)
const uploadTarget = ref(null)
const uploadReportNo = ref('')
const uploadFile = ref(null)
const uploadSubmitting = ref(false)

const openUpload = (row) => {
  uploadTarget.value = row
  uploadReportNo.value =
    row.quality_report?.report_no || `QR-${row.allocation_id}-${Date.now().toString().slice(-6)}`
  uploadFile.value = null
  uploadVisible.value = true
}

const onUploadFile = (f) => {
  uploadFile.value = f?.raw || null
}

const submitUpload = async () => {
  if (!uploadTarget.value?.allocation_id) return
  if (!uploadFile.value) {
    ElMessage.warning('请选择质检文件')
    return
  }
  uploadSubmitting.value = true
  try {
    const fd = new FormData()
    fd.append('allocation_id', String(uploadTarget.value.allocation_id))
    fd.append('report_no', (uploadReportNo.value || '').trim() || `QR-${uploadTarget.value.allocation_id}`)
    fd.append('file', uploadFile.value)
    await uploadQualityReportByAllocationApi(fd)
    ElMessage.success('质检报告已上传')
    uploadVisible.value = false
    await load()
  } finally {
    uploadSubmitting.value = false
  }
}

const items = computed(() => detail.value?.items || [])
const qualityTotalCount = computed(() => items.value.length)
const qualityUploadedCount = computed(() => items.value.filter((r) => r.quality_report).length)
const qualityMissingAny = computed(() => items.value.some((r) => r.missing_quality))

onMounted(load)

watch(
  () => `${route.params.id || ''}:${route.query._notify_refresh || ''}`,
  () => {
    if (route.params.id) load()
  },
)
</script>

<template>
  <el-card v-loading="loading">
    <template #header>工厂订单明细 - {{ detail?.order_no || '-' }}</template>
    <el-alert
      v-if="qualityMissingAny"
      type="error"
      :closable="false"
      show-icon
      class="mb-3"
      title="质检缺失"
      description="本厂仍有分单未上传质检报告，请尽快补传。仅当全部分单补齐后，相关异常才可能消除。"
    />
    <div v-if="items.length" class="tips">
      质检上传进度：{{ qualityUploadedCount }}/{{ qualityTotalCount }} 条分单已上传
    </div>

    <el-table :data="items" border>
      <el-table-column prop="line_no" label="行号" width="80" />
      <el-table-column prop="product_name" label="商品" min-width="160" />
      <el-table-column label="规格" min-width="120">
        <template #default="{ row }">{{ row.spec || '-' }}</template>
      </el-table-column>
      <el-table-column prop="quantity" label="数量" width="100" />
      <el-table-column prop="unit" label="单位" width="80" />
      <el-table-column prop="status" label="分单状态" width="120" />
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
    </el-table>

    <el-dialog v-model="uploadVisible" title="上传质检报告" width="480px" destroy-on-close>
      <el-form label-width="96px">
        <el-form-item label="分单行ID">
          <span>{{ uploadTarget?.allocation_id }}</span>
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
.tips {
  margin-bottom: 10px;
  font-size: 12px;
  color: #64748b;
}

.qr-no {
  margin-left: 6px;
  font-size: 12px;
  color: #475569;
}
</style>
