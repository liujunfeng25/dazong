<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  listPeriodicQualityReportsApi,
  listPeriodicReportProductsApi,
  createPeriodicQualityReportRevisionApi,
  uploadPeriodicQualityReportApi,
} from '../../api/periodicQualityReports'
import { formatChinaDateTime } from '../../utils/datetime'

const QR_MAX_BYTES = 20 * 1024 * 1024
const list = ref([])
const products = ref([])
const loading = ref(false)
const uploadVisible = ref(false)
const uploadSubmitting = ref(false)
const uploadFileList = ref([])
const revisionTarget = ref(null)
const form = reactive({
  product_id: null,
  valid_from: '',
  valid_to: '',
  report_no: '',
})

function fileUrls(row) {
  if (Array.isArray(row.file_urls) && row.file_urls.length) return row.file_urls
  return row.file_url ? [row.file_url] : []
}

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

const load = async () => {
  loading.value = true
  try {
    const [rows, opts] = await Promise.all([
      listPeriodicQualityReportsApi(),
      listPeriodicReportProductsApi(),
    ])
    list.value = rows || []
    products.value = opts || []
  } finally {
    loading.value = false
  }
}

const openUpload = (productId = null) => {
  revisionTarget.value = null
  form.product_id = productId || products.value[0]?.id || null
  form.valid_from = ''
  form.valid_to = ''
  form.report_no = ''
  uploadFileList.value = []
  uploadVisible.value = true
}

const openRevision = (row) => {
  revisionTarget.value = row
  form.product_id = row.product_id
  form.valid_from = row.valid_from
  form.valid_to = row.valid_to
  form.report_no = `${row.report_no}-V${Number(row.version || 1) + 1}`
  uploadFileList.value = []
  uploadVisible.value = true
}

const dateValue = (value) => (value ? new Date(`${value}T00:00:00`) : null)

const periodDays = () => {
  const start = dateValue(form.valid_from)
  const end = dateValue(form.valid_to)
  if (!start || !end) return 0
  return Math.floor((end.getTime() - start.getTime()) / 86400000) + 1
}

const endDateDisabled = (date) => {
  const start = dateValue(form.valid_from)
  if (!start) return false
  const diff = Math.floor((date.getTime() - start.getTime()) / 86400000)
  return diff < 0 || diff > 365
}

const overlappingRows = () => {
  if (!form.product_id || !form.valid_from || !form.valid_to) return []
  return list.value.filter((row) => {
    if (Number(row.product_id) !== Number(form.product_id)) return false
    if (!['待审核', '已通过'].includes(row.status)) return false
    if (revisionTarget.value && Number(row.id) === Number(revisionTarget.value.id)) return false
    return row.valid_from <= form.valid_to && row.valid_to >= form.valid_from
  })
}

const submitUpload = async () => {
  if (!form.product_id || !form.valid_from || !form.valid_to) {
    ElMessage.warning('请选择商品并填写有效期')
    return
  }
  const days = periodDays()
  if (days <= 0) {
    ElMessage.warning('有效期结束日期不能早于开始日期')
    return
  }
  if (days > 366) {
    ElMessage.warning('周期报告有效期最长为 366 天')
    return
  }
  const conflicts = overlappingRows()
  if (conflicts.length) {
    ElMessage.warning(`有效期与报告 ${conflicts[0].report_no} 重叠`)
    return
  }
  const raws = (uploadFileList.value || []).map((f) => f.raw).filter(Boolean)
  if (!raws.length) {
    ElMessage.warning('请至少选择一个文件')
    return
  }
  uploadSubmitting.value = true
  try {
    const fd = new FormData()
    if (!revisionTarget.value) fd.append('product_id', String(form.product_id))
    fd.append('valid_from', form.valid_from)
    fd.append('valid_to', form.valid_to)
    fd.append('report_no', form.report_no || `PQR-${form.product_id}`)
    raws.forEach((file) => fd.append('files', file))
    if (revisionTarget.value) {
      await createPeriodicQualityReportRevisionApi(revisionTarget.value.id, fd)
      ElMessage.success('新版本已提交，原版本在审核期间继续生效')
    } else {
      await uploadPeriodicQualityReportApi(fd)
      ElMessage.success('已提交，等待运营审核')
    }
    uploadVisible.value = false
    await load()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '上传失败')
  } finally {
    uploadSubmitting.value = false
  }
}

onMounted(load)
</script>

<template>
  <el-card class="mb-3">
    <div class="crud-toolbar">
      <span class="font-semibold">周期质检报告</span>
      <div class="crud-actions">
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" :disabled="!products.length" @click="openUpload()">上传周期报告</el-button>
      </div>
    </div>
  </el-card>

  <el-alert
    v-if="!loading && !products.length"
    type="info"
    show-icon
    :closable="false"
    class="mb-3"
    title="暂无可上传周期报告的商品"
    description="只有运营端设置为周期报告模式、且当前账号可供货/指定生产的商品会出现在这里。"
  />

  <el-card>
    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="report_no" label="报告编号" min-width="150" />
      <el-table-column label="版本" width="100">
        <template #default="{ row }">
          V{{ row.version || 1 }}
          <el-tag v-if="row.revision_of_id" size="small" type="info">修订</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="product_name" label="商品" min-width="180" />
      <el-table-column label="有效期" min-width="190">
        <template #default="{ row }">
          {{ row.valid_from }} 至 {{ row.valid_to }}
          <div class="field-tip-inline">共 {{ row.period_days }} 天</div>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="审核状态" width="110">
        <template #default="{ row }">
          <el-tag
            :type="
              row.status === '已通过'
                ? 'success'
                : row.status === '已驳回'
                  ? 'danger'
                  : row.status === '已失效'
                    ? 'info'
                    : 'warning'
            "
          >
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="effective_status" label="生效状态" width="110" />
      <el-table-column label="附件" min-width="140">
        <template #default="{ row }">
          <el-space wrap>
            <el-link
              v-for="(url, idx) in fileUrls(row)"
              :key="url"
              :href="url"
              target="_blank"
              type="primary"
            >
              附件{{ idx + 1 }}
            </el-link>
          </el-space>
        </template>
      </el-table-column>
      <el-table-column label="上传时间" min-width="170">
        <template #default="{ row }">{{ formatChinaDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="110" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.status === '已通过' && !row.superseded_by_id"
            link
            type="primary"
            :disabled="row.upload_eligible === false"
            @click="openRevision(row)"
          >
            提交新版本
          </el-button>
          <span v-else-if="row.superseded_by_id">已被 #{{ row.superseded_by_id }} 替代</span>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog
    v-model="uploadVisible"
    :title="revisionTarget ? `提交新版本（原报告 #${revisionTarget.id}）` : '上传周期质检报告'"
    width="620px"
    destroy-on-close
  >
    <el-form label-width="100px">
      <el-form-item label="商品">
        <el-select
          v-model="form.product_id"
          filterable
          :disabled="Boolean(revisionTarget)"
          placeholder="请选择周期报告商品"
        >
          <el-option
            v-for="p in products"
            :key="p.id"
            :label="`${p.name}${p.spec ? ' / ' + p.spec : ''}`"
            :value="p.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="有效期">
        <div class="date-row">
          <el-date-picker v-model="form.valid_from" value-format="YYYY-MM-DD" type="date" placeholder="开始日期" />
          <span>至</span>
          <el-date-picker
            v-model="form.valid_to"
            value-format="YYYY-MM-DD"
            type="date"
            placeholder="结束日期"
            :disabled-date="endDateDisabled"
          />
        </div>
      </el-form-item>
      <el-form-item label="报告编号">
        <el-input v-model="form.report_no" :placeholder="`默认 PQR-${form.product_id || ''}`" />
      </el-form-item>
      <el-form-item label="文件">
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
      <div v-if="form.product_id" class="field-tip">
        有效期最长 366 天，且不能与其他待审核或已通过报告重叠。
        <template v-if="revisionTarget">新版本通过前，原版本继续覆盖订单。</template>
      </div>
    </el-form>
    <template #footer>
      <el-button @click="uploadVisible = false">取消</el-button>
      <el-button type="primary" :loading="uploadSubmitting" @click="submitUpload">提交审核</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.crud-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.crud-actions,
.date-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.field-tip {
  margin-left: 100px;
  color: #909399;
  font-size: 12px;
}
.field-tip-inline {
  color: #909399;
  font-size: 12px;
}
</style>
