<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ComplaintProgress from '../../components/ComplaintProgress.vue'
import { listDeliveryComplaintsApi, respondDeliveryComplaintApi } from '../../api/delivery'
import { formatChinaDateTime } from '../../utils/datetime'

const router = useRouter()
const list = ref([])
const loading = ref(false)
const drawerVisible = ref(false)
const current = ref(null)
const responseText = ref('')

const phaseLabel = (p) =>
  ({
    delivery_handling: '待配送处理',
    operation_review: '待运营结案',
    closed: '已关闭',
  }[p] || p || '—')

const canRespond = computed(
  () => current.value && current.value.phase === 'delivery_handling' && current.value.status !== '已关闭',
)

const load = async () => {
  loading.value = true
  try {
    list.value = await listDeliveryComplaintsApi()
  } finally {
    loading.value = false
  }
}

const openDrawer = (row) => {
  current.value = row
  responseText.value = ''
  drawerVisible.value = true
}

const submit = async () => {
  if (!current.value?.ticket_id) return
  const text = responseText.value.trim()
  if (!text) {
    ElMessage.warning('请填写处理意见')
    return
  }
  try {
    await respondDeliveryComplaintApi(current.value.ticket_id, { response: text })
    ElMessage.success('已提交')
    drawerVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提交失败')
  }
}

const goOrder = (orderId) => {
  if (orderId) router.push(`/delivery/orders/${orderId}`)
}

onMounted(load)
</script>

<template>
  <el-card>
    <template #header>
      <span class="font-semibold">售后工单</span>
    </template>

    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="ticket_id" label="编号" width="80" />
      <el-table-column label="订单" min-width="160">
        <template #default="{ row }">
          <el-button link type="primary" @click="goOrder(row.order_id)">{{ row.order_no || `#${row.order_id}` }}</el-button>
        </template>
      </el-table-column>
      <el-table-column label="阶段" width="120">
        <template #default="{ row }">
          <el-tag v-if="row.phase === 'delivery_handling'" type="warning" size="small">{{ phaseLabel(row.phase) }}</el-tag>
          <el-tag v-else-if="row.phase === 'operation_review'" type="primary" size="small">{{ phaseLabel(row.phase) }}</el-tag>
          <el-tag v-else type="success" size="small">{{ phaseLabel(row.phase) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="投诉内容" min-width="200" show-overflow-tooltip />
      <el-table-column label="创建时间" min-width="160">
        <template #default="{ row }">{{ formatChinaDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link @click="openDrawer(row)">查看 / 处理</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-drawer v-model="drawerVisible" title="售后投诉处理" size="520px" destroy-on-close>
    <template v-if="current">
      <ComplaintProgress :phase="current.phase" />
      <div class="mt-3 small muted">工单 #{{ current.ticket_id }} · {{ current.status }}</div>
      <el-divider />
      <div class="mb-2 font-semibold">客户投诉</div>
      <div class="mb-3">{{ current.description }}</div>
      <div v-if="(current.attachments_json || []).length" class="thumb-row mb-3">
        <el-image
          v-for="(url, i) in current.attachments_json"
          :key="i"
          :src="url"
          :preview-src-list="current.attachments_json"
          :initial-index="i"
          class="thumb"
          fit="cover"
          preview-teleported
        />
      </div>
      <div v-if="current.delivery_response" class="mb-3">
        <div class="font-semibold small">已提交的处理意见</div>
        <div>{{ current.delivery_response }}</div>
        <div class="muted small">{{ formatChinaDateTime(current.delivery_responded_at) }}</div>
      </div>
      <div v-if="current.operation_resolution" class="mb-3">
        <div class="font-semibold small">运营结案</div>
        <div>{{ current.operation_resolution }}</div>
      </div>
      <template v-if="canRespond">
        <el-input v-model="responseText" type="textarea" :rows="5" placeholder="请填写处理意见" />
        <el-button class="mt-2" type="primary" @click="submit">提交处理意见</el-button>
      </template>
      <el-alert
        v-else-if="current.phase === 'operation_review'"
        type="info"
        :closable="false"
        title="已提交意见，等待运营审核结案"
        class="mt-2"
      />
    </template>
  </el-drawer>
</template>

<style scoped>
.small {
  font-size: 12px;
}
.muted {
  color: #64748b;
}

.thumb-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.thumb {
  width: 80px;
  height: 80px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
</style>
