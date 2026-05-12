<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ComplaintProgress from '../../components/ComplaintProgress.vue'
import { listTicketsApi, resolveComplaintTicketApi, updateTicketApi } from '../../api/operation'
import { formatChinaDateTime } from '../../utils/datetime'
import { useUserStore } from '../../stores/user'
import { can } from '../../utils/permissions'

const router = useRouter()
const list = ref([])
/** 与工单行 row.status 区分，避免表格内偶发解析歧义 */
const statusFilter = ref('')
const typeFilter = ref('')
const userStore = useUserStore()
const loading = ref(false)

const resolveDrawer = ref(false)
const resolveRow = ref(null)
const resolutionText = ref('')

const TICKET_TYPES = ['异常订单', '售后投诉', '配送异常']

const load = async () => {
  loading.value = true
  try {
    list.value = await listTicketsApi({
      status: statusFilter.value || undefined,
      type: typeFilter.value || undefined,
    })
  } finally {
    loading.value = false
  }
}

const process = async (row, nextStatus) => {
  try {
    await updateTicketApi(row.id, { status: nextStatus })
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

const phaseLabel = (row) => {
  if (row.type !== '售后投诉') return '—'
  return (
    {
      delivery_handling: '待配送反馈',
      operation_review: '待运营结案',
      closed: '已关闭',
    }[row.phase] || row.phase || '—'
  )
}

const openResolve = (row) => {
  resolveRow.value = row
  resolutionText.value = ''
  resolveDrawer.value = true
}

const submitResolve = async () => {
  const text = resolutionText.value.trim()
  if (!text) {
    ElMessage.warning('请填写运营结案意见')
    return
  }
  try {
    await resolveComplaintTicketApi(resolveRow.value.id, { resolution: text })
    ElMessage.success('已结案')
    resolveDrawer.value = false
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '结案失败')
  }
}

const operationRole = computed(() => userStore.userInfo?.role || userStore.role || '')

const statusTagType = (s) => {
  if (s === '已关闭') return 'success'
  if (s === '处理中') return 'warning'
  return 'danger'
}

const typeTagType = (t) => {
  if (t === '配送异常') return 'warning'
  if (t === '售后投诉') return 'info'
  return 'danger'
}

const goToOrder = (orderId) => {
  if (!orderId) return
  router.push(`/operation/orders/${orderId}`)
}

const counts = computed(() => {
  const total = list.value.length
  const pending = list.value.filter((r) => r.status === '待处理').length
  const doing = list.value.filter((r) => r.status === '处理中').length
  const done = list.value.filter((r) => r.status === '已关闭').length
  return { total, pending, doing, done }
})

onMounted(load)
</script>

<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span class="font-semibold">工单处理中心</span>
        <div class="counts">
          <el-tag type="danger">待处理 {{ counts.pending }}</el-tag>
          <el-tag type="warning">处理中 {{ counts.doing }}</el-tag>
          <el-tag type="success">已关闭 {{ counts.done }}</el-tag>
          <span class="muted">合计 {{ counts.total }}</span>
        </div>
      </div>
    </template>

    <div class="crud-toolbar mb-3">
      <el-select v-model="typeFilter" style="width: 160px" @change="load">
        <el-option value="" label="全部类型" />
        <el-option v-for="t in TICKET_TYPES" :key="t" :value="t" :label="t" />
      </el-select>
      <el-select v-model="statusFilter" style="width: 160px" @change="load">
        <el-option value="" label="全部状态" />
        <el-option value="待处理" label="待处理" />
        <el-option value="处理中" label="处理中" />
        <el-option value="已关闭" label="已关闭" />
      </el-select>
    </div>

    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="id" label="编号" width="70" />
      <el-table-column label="订单" min-width="160">
        <template #default="{ row }">
          <el-button link type="primary" @click="goToOrder(row.order_id)">
            {{ row.order_no || `#${row.order_id}` }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="110">
        <template #default="{ row }">
          <el-tag :type="typeTagType(row.type)" size="small">{{ row.type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="阶段" width="120">
        <template #default="{ row }">
          <span v-if="row.type !== '售后投诉'" class="muted">—</span>
          <el-tag v-else-if="row.phase === 'delivery_handling'" type="warning" size="small">{{ phaseLabel(row) }}</el-tag>
          <el-tag v-else-if="row.phase === 'operation_review'" type="primary" size="small">{{ phaseLabel(row) }}</el-tag>
          <el-tag v-else type="success" size="small">{{ phaseLabel(row) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="描述" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">{{ row.description }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="160">
        <template #default="{ row }">{{ formatChinaDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="260" align="center" fixed="right">
        <template #default="{ row }">
          <div class="op-btns">
            <el-button
              v-if="can(operationRole, 'ticket:handle') && row.status === '待处理'"
              size="small"
              type="warning"
              plain
              @click="process(row, '处理中')"
            >
              处理中
            </el-button>
            <el-button
              v-if="
                can(operationRole, 'ticket:handle') &&
                row.type === '售后投诉' &&
                row.phase === 'operation_review' &&
                row.status !== '已关闭'
              "
              size="small"
              type="success"
              plain
              @click="openResolve(row)"
            >
              审核结案
            </el-button>
            <el-button
              v-else-if="
                can(operationRole, 'ticket:handle') &&
                row.type !== '售后投诉' &&
                row.status !== '已关闭'
              "
              size="small"
              type="success"
              plain
              @click="process(row, '已关闭')"
            >
              处理完成
            </el-button>
            <span
              v-if="
                can(operationRole, 'ticket:handle') &&
                row.type === '售后投诉' &&
                row.phase === 'delivery_handling' &&
                row.status !== '已关闭'
              "
              class="muted"
            >等待配送反馈</span>
            <span v-if="!can(operationRole, 'ticket:handle')" class="muted">无操作权限</span>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-drawer v-model="resolveDrawer" title="售后投诉审核结案" size="520px" destroy-on-close>
    <template v-if="resolveRow">
      <ComplaintProgress :phase="resolveRow.phase" />
      <div class="small muted mt-2 mb-2">工单 #{{ resolveRow.id }} · {{ resolveRow.order_no }}</div>
      <div class="mb-2">{{ resolveRow.description }}</div>
      <div v-if="(resolveRow.attachments_json || []).length" class="thumb-row mb-3">
        <el-image
          v-for="(url, i) in resolveRow.attachments_json"
          :key="i"
          :src="url"
          :preview-src-list="resolveRow.attachments_json"
          :initial-index="i"
          class="thumb"
          fit="cover"
          preview-teleported
        />
      </div>
      <el-divider />
      <div v-if="resolveRow.delivery_response" class="mb-3">
        <div class="font-semibold small">配送商处理意见</div>
        <div>{{ resolveRow.delivery_response }}</div>
        <div class="muted small">{{ formatChinaDateTime(resolveRow.delivery_responded_at) }}</div>
      </div>
      <el-input v-model="resolutionText" type="textarea" :rows="5" placeholder="请填写运营结案意见（必填）" />
      <el-button class="mt-2" type="primary" @click="submitResolve">确认结案</el-button>
    </template>
  </el-drawer>
</template>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.counts {
  display: flex;
  gap: 8px;
  align-items: center;
}

.muted {
  color: #94a3b8;
  font-size: 12px;
}

.crud-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.op-btns {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
}

.thumb-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.thumb {
  width: 72px;
  height: 72px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.small {
  font-size: 12px;
}
</style>
