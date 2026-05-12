<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { contractDetailApi, listContractsApi, tenderMetaApi } from '../../api/contracts'

const route = useRoute()
const list = ref([])
const loading = ref(false)
const categoryNameMap = ref({})
const filters = reactive({ lifecycle: '', keyword: '' })

const drawerVisible = ref(false)
const detailLoading = ref(false)
const detail = ref(null)

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

const percent = (rate) => `${(Number(rate || 0) * 100).toFixed(2)}%`

const lifecycleTagType = (s) => {
  if (s === '生效中') return 'success'
  if (s === '待生效') return 'info'
  if (s === '已过期') return 'info'
  if (s === '已中标' || s === '招标中') return 'warning'
  return ''
}

const load = async () => {
  loading.value = true
  try {
    const params = {}
    if (filters.lifecycle) params.lifecycle = filters.lifecycle
    const kw = (filters.keyword || '').trim()
    if (kw) params.keyword = kw
    const [rows, meta] = await Promise.all([listContractsApi(params), tenderMetaApi()])
    list.value = rows || []
    categoryNameMap.value = Object.fromEntries((meta.level1_categories || []).map((i) => [i.id, i.name]))
  } catch {
    ElMessage.error('加载合约列表失败')
    list.value = []
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  filters.lifecycle = ''
  filters.keyword = ''
  load()
}

const openDetail = async (row) => {
  drawerVisible.value = true
  detail.value = null
  detailLoading.value = true
  try {
    detail.value = await contractDetailApi(row.id)
  } catch {
    ElMessage.error('加载合约详情失败')
    drawerVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

onMounted(load)
watch(() => route.fullPath, load)
</script>

<template>
  <div class="contracts-page">
    <el-card class="filter-card" shadow="never">
      <el-form :model="filters" class="filter-form" label-width="72px" @submit.prevent="load">
        <el-form-item label="合约状态">
          <el-select v-model="filters.lifecycle" clearable placeholder="全部状态" style="width: 200px" @change="load">
            <el-option label="待生效" value="待生效" />
            <el-option label="生效中" value="生效中" />
            <el-option label="已过期" value="已过期" />
            <el-option label="招标中" value="招标中" />
            <el-option label="已中标" value="已中标" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input
            v-model="filters.keyword"
            clearable
            placeholder="合约号 / 客户名称 / 地址"
            style="width: 280px"
            @keyup.enter="load"
          />
        </el-form-item>
        <el-form-item class="filter-actions">
          <el-button type="primary" @click="load">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="table-card" shadow="never">
      <el-table
        v-loading="loading"
        :data="list"
        border
        stripe
        empty-text="暂无合约数据"
        class="contracts-table"
        :header-cell-style="{ background: '#f8fafc', color: '#475569', fontWeight: '600' }"
      >
        <el-table-column type="expand" width="52">
          <template #default="{ row }">
            <div class="expand-inner">
              <div class="expand-grid">
                <div><span class="detail-label">一级分类</span>{{ categoryNames(row) || '—' }}</div>
                <div><span class="detail-label">定标状态</span>{{ row.status || '—' }}</div>
                <div><span class="detail-label">浮动率</span>{{ percent(row.price_float_rate) }}</div>
              </div>
              <div v-if="categoryRateRows(row).length" class="category-rate-panel">
                <div class="category-rate-title">各一级分类浮动率</div>
                <div class="category-rate-grid">
                  <div v-for="item in categoryRateRows(row)" :key="item.category_id" class="category-rate-item">
                    <span class="cat-name">{{ item.category_name }}</span>
                    <el-tag type="success" size="small">{{ percent(item.float_rate) }}</el-tag>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="contract_no" label="合约号" min-width="130" fixed="left" />
        <el-table-column label="客户名称" min-width="140">
          <template #default="{ row }">
            <span class="cell-strong">{{ row.client_name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="客户地址" min-width="200">
          <template #default="{ row }">
            <span class="cell-muted">{{ row.client_address || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合约周期" min-width="200">
          <template #default="{ row }">
            <div class="period-block">
              <div class="period-line">
                <span class="period-tag">起</span>
                <span>{{ row.period_start || '—' }}</span>
              </div>
              <div class="period-line">
                <span class="period-tag end">止</span>
                <span>{{ row.period_end || '—' }}</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="合约状态" width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="lifecycleTagType(row.lifecycle_status)" effect="light" round size="small">
              {{ row.lifecycle_status || row.status || '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="平均浮动率" width="118" align="right">
          <template #default="{ row }">{{ percent(row.price_float_rate) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="112" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="openDetail(row)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="drawerVisible" title="合约详情" size="420px" destroy-on-close>
      <div v-loading="detailLoading" class="drawer-body">
        <template v-if="detail">
          <div class="detail-section">
            <div class="detail-title">基本信息</div>
            <div class="detail-rows">
              <div class="detail-row"><span>合约号</span><b>{{ detail.contract_no }}</b></div>
              <div class="detail-row">
                <span>合约状态</span>
                <el-tag :type="lifecycleTagType(detail.lifecycle_status)" size="small">
                  {{ detail.lifecycle_status || detail.status }}
                </el-tag>
              </div>
              <div class="detail-row"><span>定标状态</span>{{ detail.status }}</div>
            </div>
          </div>
          <div class="detail-section">
            <div class="detail-title">客户信息</div>
            <div class="detail-rows">
              <div class="detail-row"><span>客户名称</span>{{ detail.client_name || '—' }}</div>
              <div class="detail-row align-top"><span>客户地址</span>{{ detail.client_address || '—' }}</div>
            </div>
          </div>
          <div class="detail-section">
            <div class="detail-title">周期与计价</div>
            <div class="detail-rows">
              <div class="detail-row"><span>开始日期</span>{{ detail.period_start }}</div>
              <div class="detail-row"><span>结束日期</span>{{ detail.period_end }}</div>
              <div class="detail-row"><span>平均浮动率</span>{{ percent(detail.price_float_rate) }}</div>
            </div>
          </div>
          <div class="detail-section">
            <div class="detail-title">分类范围</div>
            <p class="detail-text">{{ categoryNames(detail) || '—' }}</p>
            <div v-if="categoryRateRows(detail).length" class="category-rate-grid drawer-rates">
              <div v-for="item in categoryRateRows(detail)" :key="item.category_id" class="category-rate-item">
                <span class="cat-name">{{ item.category_name }}</span>
                <el-tag type="success" size="small">{{ percent(item.float_rate) }}</el-tag>
              </div>
            </div>
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.contracts-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-card :deep(.el-card__body) {
  padding-bottom: 8px;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
}

.filter-form :deep(.el-form-item) {
  margin-bottom: 8px;
}

.filter-actions :deep(.el-form-item__content) {
  margin-left: 0 !important;
}

.table-card :deep(.el-card__body) {
  padding-top: 12px;
}

.contracts-table {
  width: 100%;
}

.cell-strong {
  font-weight: 600;
  color: #0f172a;
}

.cell-muted {
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
}

.period-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: #334155;
}

.period-line {
  display: flex;
  align-items: center;
  gap: 8px;
}

.period-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  flex-shrink: 0;
}

.period-tag.end {
  background: linear-gradient(135deg, #94a3b8, #64748b);
}

.expand-inner {
  padding: 8px 12px 16px;
  background: #fafbfc;
  border-radius: 8px;
  margin: 4px 0;
}

.expand-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px 24px;
  font-size: 13px;
  color: #334155;
}

.detail-label {
  display: inline-block;
  min-width: 72px;
  margin-right: 8px;
  color: #94a3b8;
}

.category-rate-panel {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed #e2e8f0;
}

.category-rate-title {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 10px;
}

.category-rate-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
}

.drawer-rates {
  margin-top: 8px;
}

.category-rate-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.cat-name {
  font-size: 13px;
  color: #334155;
}

.drawer-body {
  min-height: 120px;
}

.detail-section {
  margin-bottom: 22px;
}

.detail-title {
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #f1f5f9;
}

.detail-rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 14px;
  color: #334155;
}

.detail-row {
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 12px;
  align-items: center;
}

.detail-row.align-top {
  align-items: start;
}

.detail-row span:first-child {
  color: #94a3b8;
  font-size: 13px;
}

.detail-text {
  margin: 0;
  font-size: 14px;
  color: #334155;
  line-height: 1.6;
}
</style>
