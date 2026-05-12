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
import { formatChinaDateTime } from '../../utils/datetime'
import { orderMainStatusTagType, orderStatusLabel } from '../../utils/orderStatus'

const route = useRoute()
const router = useRouter()
const detail = ref(null)
const loading = ref(false)
const detailItems = computed(() => {
  const snapshot = detail.value?.items_snapshot_json
  if (Array.isArray(snapshot) && snapshot.length) return snapshot
  const items = detail.value?.items_json
  return Array.isArray(items) ? items : []
})

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
  await ElMessageBox.confirm(
    '确认取消该订单吗？取消后不可恢复。',
    '取消确认',
    {
      type: 'warning',
      confirmButtonText: '确认取消',
      cancelButtonText: '再想想',
    },
  )
  await cancelOrderApi(route.params.id)
  ElMessage.success('订单已取消')
  await router.push(`/client/orders?refresh=${Date.now()}`)
}

// 售后投诉弹窗
const complaintVisible = ref(false)
const complaintReason = ref('')
const complaintImages = ref([]) // [{ url, name }]
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
  <el-card v-loading="loading" v-if="detail">
    <template #header>
      <div class="detail-header">
        <span class="font-semibold">订单详情：{{ detail.order_no }}</span>
        <el-tag :type="orderMainStatusTagType(detail.status)">{{ orderStatusLabel(detail.status) }}</el-tag>
      </div>
    </template>
    <el-descriptions :column="2" border>
      <el-descriptions-item label="订单号">{{ detail.order_no }}</el-descriptions-item>
      <el-descriptions-item label="金额">¥{{ Number(detail.total_amount || 0).toLocaleString() }}</el-descriptions-item>
      <el-descriptions-item label="异常标记">{{ detail.has_abnormal ? '是' : '否' }}</el-descriptions-item>
      <el-descriptions-item label="更新时间">{{ formatChinaDateTime(detail.updated_at) }}</el-descriptions-item>
    </el-descriptions>

    <el-alert
      v-if="hasOpenComplaint"
      type="warning"
      :closable="false"
      show-icon
      class="mt-3"
      title="已存在未关闭的售后投诉工单"
      description="运营会跟进处理，处理完成后将关闭工单。"
    />

    <div class="section-title">订单明细</div>
    <el-table v-if="detailItems.length" :data="detailItems" border class="detail-items-table">
      <el-table-column type="index" width="56" label="#" />
      <el-table-column label="商品" min-width="220">
        <template #default="{ row }">
          {{ row.product_name || row.product_id || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="数量" min-width="100" align="right">
        <template #default="{ row }">{{ Number(row.order_quantity ?? row.quantity ?? 0) }}</template>
      </el-table-column>
      <el-table-column label="单位" min-width="90" align="center">
        <template #default="{ row }">{{ row.unit || '—' }}</template>
      </el-table-column>
      <el-table-column label="单价" min-width="120" align="right">
        <template #default="{ row }">¥{{ Number(row.order_unit_price ?? row.unit_price ?? 0).toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="小计" min-width="140" align="right">
        <template #default="{ row }">
          ¥{{
            (
              Number(row.order_quantity ?? row.quantity ?? 0) *
              Number(row.order_unit_price ?? row.unit_price ?? 0)
            ).toFixed(2)
          }}
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-else description="暂无明细数据" :image-size="80" class="detail-empty" />

    <div class="actions">
      <el-button @click="router.back()">返回列表</el-button>
      <el-button v-if="detail.status === '下单'" type="danger" @click="cancel">取消订单</el-button>
      <el-button v-if="detail.status === '收货'" type="primary" @click="router.push(`/client/receive/${detail.id}`)">去收货</el-button>
      <el-button
        v-if="canComplain"
        type="warning"
        :disabled="hasOpenComplaint"
        @click="openComplaintDialog"
      >
        {{ hasOpenComplaint ? '已发起售后投诉' : '售后投诉' }}
      </el-button>
    </div>
  </el-card>

  <el-dialog v-model="complaintVisible" title="售后投诉" width="560px" destroy-on-close>
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
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          accept="image/*"
          :on-change="onComplaintFileChange"
        >
          <el-button :disabled="complaintImages.length >= 5">添加图片</el-button>
          <template #tip>
            <div class="muted small">最多 5 张，已上传 {{ complaintImages.length }}/5</div>
          </template>
        </el-upload>
        <div v-if="complaintImages.length" class="img-grid">
          <div v-for="(img, i) in complaintImages" :key="i" class="img-cell">
            <el-image :src="img.url" fit="cover" class="thumb" :preview-src-list="complaintImages.map(x => x.url)" :initial-index="i" />
            <el-button text type="danger" size="small" @click="removeComplaintImage(i)">移除</el-button>
          </div>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="complaintVisible = false">取消</el-button>
      <el-button type="primary" :loading="complaintSubmitting" @click="submitComplaint">
        提交投诉
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.actions {
  margin-top: 16px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.section-title {
  margin-top: 16px;
  margin-bottom: 10px;
  font-weight: 600;
  color: #0f172a;
}

.detail-items-table {
  margin-bottom: 6px;
}

.detail-empty {
  margin-top: 8px;
}

.muted {
  color: #94a3b8;
}

.small {
  font-size: 12px;
}

.img-grid {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.img-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.thumb {
  width: 80px;
  height: 80px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
</style>
