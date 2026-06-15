<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import OperationContractsTable from './OperationContractsTable.vue'
import {
  getOperationContractApi,
  listOperationContractOrdersApi,
  listOperationContractsApi,
} from '../../api/operation'
import { formatChinaDateTime } from '../../utils/datetime'
import { contractDbStatusTagType, contractLifecycleTagType } from '../../utils/contractStatus'
import { MAIN_ORDER_STATUS_OPTIONS, orderStatusLabel, orderStatusTagColor } from '../../utils/orderStatus'

const router = useRouter()
const route = useRoute()

const loading = ref(false)
const list = ref([])
const lifecycle = ref('生效中')
const keyword = ref('')
const dbStatus = ref('')

const drawerVisible = ref(false)
const drawerLoading = ref(false)
const contractDetail = ref(null)
const activeContractId = ref(null)

const orderLoading = ref(false)
const orderList = ref([])
const orderStatus = ref('')
const orderNo = ref('')
const orderDateRange = ref([])

const LIFECYCLE_OPTIONS = [
  { value: '', label: '全部' },
  { value: '待生效', label: '待生效' },
  { value: '生效中', label: '履约中（生效中）' },
  { value: '已过期', label: '已过期' },
  { value: '招标中', label: '招标中' },
  { value: '已中标', label: '已中标' },
]

const DB_STATUS_OPTIONS = [
  { value: '', label: '全部' },
  { value: '招标中', label: '招标中' },
  { value: '已中标', label: '已中标' },
  { value: '已过期', label: '已过期' },
]

const toDateStr = (d) => {
  if (!d) return undefined
  const dt = new Date(d)
  const m = String(dt.getMonth() + 1).padStart(2, '0')
  const day = String(dt.getDate()).padStart(2, '0')
  return `${dt.getFullYear()}-${m}-${day}`
}

const loadList = async () => {
  loading.value = true
  try {
    const params = {}
    if (lifecycle.value) params.lifecycle = lifecycle.value
    if (keyword.value?.trim()) params.keyword = keyword.value.trim()
    if (dbStatus.value) params.db_status = dbStatus.value
    list.value = await listOperationContractsApi(params)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载合约失败')
    list.value = []
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  lifecycle.value = '生效中'
  keyword.value = ''
  dbStatus.value = ''
  loadList()
}

const openDrawer = async (row) => {
  activeContractId.value = row.id
  drawerVisible.value = true
  drawerLoading.value = true
  contractDetail.value = null
  orderStatus.value = ''
  orderNo.value = ''
  orderDateRange.value = []
  try {
    contractDetail.value = await getOperationContractApi(row.id)
    await loadOrders()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载合约详情失败')
  } finally {
    drawerLoading.value = false
  }
}

const loadOrders = async () => {
  if (!activeContractId.value) return
  orderLoading.value = true
  try {
    const params = {}
    if (orderStatus.value) params.status = orderStatus.value
    if (orderNo.value?.trim()) params.order_no = orderNo.value.trim()
    if (orderDateRange.value?.[0]) params.expected_date_start = toDateStr(orderDateRange.value[0])
    if (orderDateRange.value?.[1]) params.expected_date_end = toDateStr(orderDateRange.value[1])
    const raw = await listOperationContractOrdersApi(activeContractId.value, params)
    orderList.value = Array.isArray(raw) ? raw : []
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载订单失败')
    orderList.value = []
  } finally {
    orderLoading.value = false
  }
}

const goOrderDetail = (row) => {
  const id = row?.id ?? row?.order_id
  const n = Number(id)
  if (!Number.isFinite(n) || n <= 0) {
    ElMessage.error('无法打开订单详情：缺少有效的订单 ID')
    return
  }
  router.push(`/operation/orders/${n}`).catch(() => {})
}

const tryOpenFromQuery = async () => {
  const raw = route.query.open ?? route.query.openContractId
  const id = raw != null && raw !== '' ? Number(raw) : NaN
  if (!Number.isFinite(id) || id <= 0) return
  const row = list.value.find((r) => Number(r.id) === id)
  if (row) await openDrawer(row)
  else await openDrawer({ id })
}

onMounted(async () => {
  await loadList()
  await tryOpenFromQuery()
})

const pct = (r) => `${(Number(r || 0) * 100).toFixed(2)}%`
</script>

<template>
  <div class="contracts-page">
    <el-card class="mb-3">
      <div class="crud-toolbar">
        <el-form inline class="crud-form">
          <el-form-item label="生命周期">
            <el-select v-model="lifecycle" style="width: 200px" @change="loadList">
              <el-option v-for="o in LIFECYCLE_OPTIONS" :key="o.value || 'all'" :value="o.value" :label="o.label" />
            </el-select>
          </el-form-item>
          <el-form-item label="定标状态">
            <el-select v-model="dbStatus" style="width: 140px" clearable placeholder="全部" @change="loadList">
              <el-option v-for="o in DB_STATUS_OPTIONS" :key="o.value || 'all'" :value="o.value" :label="o.label" />
            </el-select>
            <div class="field-tip">定标状态 = 招标是否结束、是否已中标落档、是否已记过期；与「生命周期」含义不同，见表头问号说明。</div>
          </el-form-item>
          <el-form-item label="关键词">
            <el-input
              v-model="keyword"
              placeholder="合约号 / 采购方 / 地址 / 配送方"
              clearable
              style="width: 240px"
              @keyup.enter="loadList"
            />
          </el-form-item>
        </el-form>
        <div class="crud-actions">
          <el-button type="primary" @click="loadList">筛选</el-button>
          <el-button @click="resetFilters">重置为履约中</el-button>
        </div>
      </div>
    </el-card>

    <el-card>
      <template #header><span class="font-semibold">合约列表</span></template>
      <OperationContractsTable
        :data="list"
        :loading="loading"
        :compact="false"
        :show-db-status="true"
        @view-contract="openDrawer"
      />
    </el-card>

    <el-drawer v-model="drawerVisible" title="合约详情" size="720px" destroy-on-close>
      <div v-loading="drawerLoading">
        <template v-if="contractDetail">
          <el-descriptions :column="2" border class="mb-4">
            <el-descriptions-item label="合约号">{{ contractDetail.contract_no }}</el-descriptions-item>
            <el-descriptions-item label="生命周期">
              <el-tag :type="contractLifecycleTagType(contractDetail.lifecycle_status)" size="small" effect="dark">
                {{ contractDetail.lifecycle_status }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="采购方">{{ contractDetail.client_name }}</el-descriptions-item>
            <el-descriptions-item label="配送方">{{ contractDetail.delivery_name }}</el-descriptions-item>
            <el-descriptions-item label="合约期" :span="2">
              {{ contractDetail.period_start }} ~ {{ contractDetail.period_end }}
            </el-descriptions-item>
            <el-descriptions-item label="定标状态">
              <el-tag :type="contractDbStatusTagType(contractDetail.status)" size="small" effect="plain">
                {{ contractDetail.status }}
              </el-tag>
              <span class="desc-hint">（招标中 / 已中标 / 已过期）</span>
            </el-descriptions-item>
            <el-descriptions-item label="综合上浮率">{{ pct(contractDetail.price_float_rate) }}</el-descriptions-item>
            <el-descriptions-item label="合约内订单数">{{ contractDetail.order_count ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="合约内订单金额">
              ¥{{ Number(contractDetail.order_total_amount || 0).toLocaleString() }}
            </el-descriptions-item>
          </el-descriptions>

          <div class="subhead">本合约订单（与下单时「配送日落在合约期内」一致）</div>
          <el-card shadow="never" class="inner-filter">
            <el-form inline>
              <el-form-item label="状态">
                <el-select v-model="orderStatus" style="width: 170px" clearable @change="loadOrders">
                  <el-option value="" label="全部" />
                  <el-option v-for="o in MAIN_ORDER_STATUS_OPTIONS" :key="o.value" :value="o.value" :label="o.label" />
                </el-select>
              </el-form-item>
              <el-form-item label="订单号">
                <el-input v-model="orderNo" clearable style="width: 160px" @keyup.enter="loadOrders" />
              </el-form-item>
              <el-form-item label="有效配送日">
                <el-date-picker
                  v-model="orderDateRange"
                  type="daterange"
                  start-placeholder="开始"
                  end-placeholder="结束"
                  @change="loadOrders"
                />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="loadOrders">筛选订单</el-button>
              </el-form-item>
            </el-form>
          </el-card>

          <el-table v-loading="orderLoading" :data="orderList" border class="mt-3" @row-click="goOrderDetail">
            <el-table-column prop="order_no" label="订单号" min-width="150" />
            <el-table-column prop="status" label="状态" width="120">
              <template #default="{ row }">
                <el-tag :color="orderStatusTagColor(row.status)" effect="dark">{{ orderStatusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="total_amount" label="金额" width="120">
              <template #default="{ row }">¥{{ Number(row.total_amount || 0).toLocaleString() }}</template>
            </el-table-column>
            <el-table-column prop="expected_delivery_date" label="期望配送日" width="130" />
            <el-table-column label="异常" width="80">
              <template #default="{ row }">
                <el-tag v-if="row.has_abnormal" type="danger" size="small">是</el-tag>
                <span v-else>—</span>
              </template>
            </el-table-column>
            <el-table-column label="更新时间" min-width="170">
              <template #default="{ row }">{{ formatChinaDateTime(row.updated_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100" align="center">
              <template #default="{ row }">
                <el-button type="primary" link @click.stop="goOrderDetail(row)">订单详情</el-button>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.contracts-page {
  min-height: 400px;
}
.subhead {
  font-weight: 600;
  margin-bottom: 10px;
  color: #334155;
}
.inner-filter {
  margin-bottom: 8px;
}
.mt-3 {
  margin-top: 12px;
}
.mb-3 {
  margin-bottom: 12px;
}
.mb-4 {
  margin-bottom: 16px;
}
.crud-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.crud-form {
  flex: 1;
}
.crud-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.field-tip {
  margin-top: 6px;
  max-width: 360px;
  color: #909399;
  font-size: 12px;
  line-height: 1.45;
}

.desc-hint {
  margin-left: 8px;
  font-size: 12px;
  color: #94a3b8;
}
</style>
