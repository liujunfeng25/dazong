<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listPeriodicQualityReportsApi,
  reviewPeriodicQualityReportApi,
} from '../../api/periodicQualityReports'
import { formatChinaDateTime } from '../../utils/datetime'

const list = ref([])
const loading = ref(false)
const filters = reactive({ status: '' })
const rejectVisible = ref(false)
const rejectTarget = ref(null)
const rejectReason = ref('')

function fileUrls(row) {
  if (Array.isArray(row.file_urls) && row.file_urls.length) return row.file_urls
  return row.file_url ? [row.file_url] : []
}

const load = async () => {
  loading.value = true
  try {
    list.value = await listPeriodicQualityReportsApi({ status: filters.status || undefined })
  } finally {
    loading.value = false
  }
}

const approve = async (row) => {
  const replacement = row.revision_of_id
    ? `。通过后将使原报告 #${row.revision_of_id} 失效`
    : ''
  await ElMessageBox.confirm(
    `确认通过 ${row.valid_from} 至 ${row.valid_to}（共 ${row.period_days} 天）的报告${replacement}？`,
    '确认审核通过',
    { type: 'warning', confirmButtonText: '确认通过', cancelButtonText: '取消' },
  )
  await reviewPeriodicQualityReportApi(row.id, { status: '已通过' })
  ElMessage.success('已审核通过')
  await load()
}

const openReject = (row) => {
  rejectTarget.value = row
  rejectReason.value = row.reject_reason || ''
  rejectVisible.value = true
}

const submitReject = async () => {
  const reason = rejectReason.value.trim()
  if (!reason) {
    ElMessage.warning('请填写驳回原因')
    return
  }
  await reviewPeriodicQualityReportApi(rejectTarget.value.id, {
    status: '已驳回',
    reject_reason: reason,
  })
  ElMessage.success('已驳回')
  rejectVisible.value = false
  await load()
}

onMounted(load)
</script>

<template>
  <el-card class="mb-3">
    <div class="crud-toolbar">
      <el-form inline class="crud-form">
        <el-form-item>
          <el-select v-model="filters.status" clearable placeholder="审核状态" style="width: 150px">
            <el-option value="待审核" label="待审核" />
            <el-option value="已通过" label="已通过" />
            <el-option value="已驳回" label="已驳回" />
            <el-option value="已失效" label="已失效" />
          </el-select>
        </el-form-item>
        <el-form-item><el-button @click="load">查询</el-button></el-form-item>
      </el-form>
      <el-button @click="load">刷新</el-button>
    </div>
  </el-card>

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
      <el-table-column prop="provider_name" label="供货主体" min-width="180" />
      <el-table-column label="有效期" min-width="190">
        <template #default="{ row }">
          {{ row.valid_from }} 至 {{ row.valid_to }}
          <div class="cell-tip">共 {{ row.period_days }} 天</div>
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
      <el-table-column label="校验" min-width="150">
        <template #default="{ row }">
          <el-tag v-if="!row.upload_eligible" type="danger">上传资格已失效</el-tag>
          <el-tag v-else-if="row.has_overlap_conflict" type="danger">
            与 #{{ row.conflict_report_ids.join('、#') }} 冲突
          </el-tag>
          <el-tag v-else type="success">校验正常</el-tag>
        </template>
      </el-table-column>
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
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button
            link
            type="success"
            :disabled="row.status !== '待审核' || !row.upload_eligible || row.has_overlap_conflict"
            @click="approve(row)"
          >
            通过
          </el-button>
          <el-button link type="danger" :disabled="row.status !== '待审核'" @click="openReject(row)">
            驳回
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="rejectVisible" title="驳回周期报告" width="480px">
    <el-input v-model="rejectReason" type="textarea" :rows="4" placeholder="请输入驳回原因" />
    <template #footer>
      <el-button @click="rejectVisible = false">取消</el-button>
      <el-button type="danger" @click="submitReject">确认驳回</el-button>
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
.crud-form {
  margin-bottom: 0;
}
.cell-tip {
  color: #909399;
  font-size: 12px;
}
</style>
