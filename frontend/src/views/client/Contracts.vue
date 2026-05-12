<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listContractsApi, tenderMetaApi } from '../../api/contracts'

const router = useRouter()
const route = useRoute()
const list = ref([])
const status = ref('')
const loading = ref(false)
const categoryNameMap = ref({})
const deliveryNameMap = ref({})
const categoryNames = (row) =>
  (row.category_ids_json || []).map((id) => categoryNameMap.value[id] || `分类#${id}`).join('、')
const categoryRateRows = (row) =>
  (row.category_rates_json || []).map((i) => {
    const cid = Number(i.category_id)
    return {
      category_id: cid,
      category_name: categoryNameMap.value[cid] || `分类#${cid}`,
      float_rate: Number(i.float_rate || 0),
    }
  })
const statusType = (s) =>
  s === '生效中' || s === '执行中'
    ? 'success'
    : s === '已过期'
      ? 'info'
      : s === '待生效'
        ? 'info'
        : 'warning'
const percent = (rate) => `${(Number(rate || 0) * 100).toFixed(2)}%`
const todayStr = () => new Date().toISOString().slice(0, 10)
const isPendingEffective = (row) => row?.status === '已中标' && row?.period_start && row.period_start > todayStr()
const statusLabel = (row) => row.lifecycle_status || (isPendingEffective(row) ? '待生效' : row.status)
const statusTagType = (row) => statusType(row.lifecycle_status || (isPendingEffective(row) ? '待生效' : row.status))
const load = async () => {
  loading.value = true
  try {
    const [rows, meta] = await Promise.all([listContractsApi(), tenderMetaApi()])
    categoryNameMap.value = Object.fromEntries((meta.level1_categories || []).map((i) => [i.id, i.name]))
    deliveryNameMap.value = Object.fromEntries(
      (meta.deliveries || []).map((i) => [i.id, i.company_name || i.username || `配送方#${i.id}`]),
    )
    if (!status.value) list.value = rows
    else if (status.value === '执行中')
      list.value = rows.filter((i) => (i.lifecycle_status || '') === '生效中')
    else if (status.value === '已过期')
      list.value = rows.filter((i) => i.lifecycle_status === '已过期' || i.status === '已过期')
    else list.value = rows.filter((i) => i.status === status.value)
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(() => route.fullPath, load)
</script>

<template>
  <el-card class="mb-3">
    <el-form inline>
      <el-form-item>
        <el-button type="primary" @click="router.push('/client/contracts/new')">发起招标</el-button>
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="status" style="width: 160px" @change="load">
          <el-option value="" label="全部" />
          <el-option value="已中标" label="已中标" />
          <el-option value="执行中" label="执行中" />
          <el-option value="已过期" label="已过期" />
        </el-select>
      </el-form-item>
    </el-form>
  </el-card>
  <el-card>
    <el-table v-loading="loading" :data="list" border empty-text="暂无合约，请先发起招标">
      <el-table-column type="expand" width="56">
        <template #default="{ row }">
          <div class="contract-detail">
            <div><span class="detail-label">配送单位：</span>{{ deliveryNameMap[row.delivery_id] || `配送方#${row.delivery_id}` }}</div>
            <div><span class="detail-label">一级分类：</span>{{ categoryNames(row) || '—' }}</div>
            <div><span class="detail-label">开始日期：</span>{{ row.period_start || '—' }}</div>
            <div><span class="detail-label">结束日期：</span>{{ row.period_end || '—' }}</div>
            <div><span class="detail-label">平均浮动率：</span>{{ percent(row.price_float_rate) }}</div>
          </div>
          <div v-if="categoryRateRows(row).length" class="category-rate-panel">
            <div class="category-rate-title">各一级分类配送商浮动率</div>
            <div class="category-rate-grid">
              <div v-for="item in categoryRateRows(row)" :key="item.category_id" class="category-rate-item">
                <span class="cat-name">{{ item.category_name }}</span>
                <el-tag type="success" size="small">{{ percent(item.float_rate) }}</el-tag>
              </div>
            </div>
          </div>
          <div v-else class="category-rate-empty">暂无分类浮动率明细</div>
          <div class="contract-tip">
            提示：仅在合约生效期内（开始~结束）才可用于下单计价；未到开始日期时会在下单页隐藏该配送单位。
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="contract_no" label="合约编号" min-width="150" />
      <el-table-column label="配送单位" min-width="150">
        <template #default="{ row }">
          {{ deliveryNameMap[row.delivery_id] || `配送方#${row.delivery_id}` }}
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row)">{{ statusLabel(row) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="平均浮动率" width="120">
        <template #default="{ row }">{{ percent(row.price_float_rate) }}</template>
      </el-table-column>
      <el-table-column prop="period_start" label="开始" min-width="130" />
      <el-table-column prop="period_end" label="结束" min-width="130" />
    </el-table>
  </el-card>
</template>

<style scoped>
.contract-detail {
  display: grid;
  grid-template-columns: repeat(2, minmax(220px, 1fr));
  gap: 10px 20px;
  color: #334155;
  font-size: 13px;
  padding: 4px 8px;
}

.detail-label {
  color: #64748b;
}

.category-rate-panel {
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
}

.category-rate-title {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 8px;
}

.category-rate-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}

.category-rate-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid #e2e8f0;
}

.cat-name {
  color: #0f172a;
  font-size: 12px;
}

.category-rate-empty {
  margin-top: 10px;
  color: #94a3b8;
  font-size: 12px;
}

.contract-tip {
  margin-top: 8px;
  font-size: 12px;
  color: #64748b;
}
</style>
