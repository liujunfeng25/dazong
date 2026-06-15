<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listContractsApi, tenderMetaApi } from '../../api/contracts'
import { useIsMobile } from '../../composables/useIsMobile'

const router = useRouter()
const route = useRoute()
const { isMobile } = useIsMobile()
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
  <!-- ── Mobile ── -->
  <div v-if="isMobile" class="m-page">
    <div class="m-filter-bar">
      <div class="m-status-tabs">
        <button class="m-status-tab" :class="{ 'is-active': !status }" @click="status = ''; load()">全部</button>
        <button class="m-status-tab" :class="{ 'is-active': status === '已中标' }" @click="status = '已中标'; load()">已中标</button>
        <button class="m-status-tab" :class="{ 'is-active': status === '执行中' }" @click="status = '执行中'; load()">执行中</button>
        <button class="m-status-tab" :class="{ 'is-active': status === '已过期' }" @click="status = '已过期'; load()">已过期</button>
      </div>
    </div>

    <div v-if="loading" class="m-empty">加载中...</div>
    <div v-else-if="!list.length" class="m-empty">暂无合约，请先发起招标</div>
    <div v-else class="m-contract-list">
      <div v-for="row in list" :key="row.id" class="m-contract-card">
        <div class="m-contract-card__top">
          <span class="m-contract-card__no">{{ row.contract_no }}</span>
          <span class="m-contract-tag" :class="`m-contract-tag--${statusTagType(row)}`">{{ statusLabel(row) }}</span>
        </div>
        <div class="m-contract-card__delivery">
          <span class="material-symbols-outlined" style="font-size:16px;vertical-align:middle;margin-right:4px">local_shipping</span>
          {{ deliveryNameMap[row.delivery_id] || `配送方#${row.delivery_id}` }}
        </div>
        <div class="m-contract-card__period">
          <span class="material-symbols-outlined" style="font-size:16px;vertical-align:middle;margin-right:4px">date_range</span>
          {{ row.period_start || '—' }} ~ {{ row.period_end || '—' }}
        </div>
        <div class="m-contract-card__rate">
          平均浮动率 <strong>{{ percent(row.price_float_rate) }}</strong>
        </div>
        <div v-if="categoryRateRows(row).length" class="m-category-chips">
          <span v-for="item in categoryRateRows(row)" :key="item.category_id" class="m-cat-chip">
            {{ item.category_name }}：{{ percent(item.float_rate) }}
          </span>
        </div>
      </div>
    </div>

    <button class="m-fab-btn" @click="router.push('/client/contracts/new')">
      <span class="material-symbols-outlined">add</span>
      发起招标
    </button>
  </div>

  <!-- ── PC ── -->
  <template v-else>
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

@media (max-width: 768px) {
  .contract-detail {
    grid-template-columns: 1fr;
  }
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

/* ── Mobile styles ── */
.m-page {
  font-family: var(--m-font-body);
  padding-bottom: 80px;
  position: relative;
  min-height: 100%;
}
.m-filter-bar {
  padding: 12px 16px;
  border-bottom: 1px solid var(--m-outline-variant);
  background: var(--m-surface-container-lowest);
}
.m-status-tabs {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}
.m-status-tabs::-webkit-scrollbar { display: none; }
.m-status-tab {
  flex: none;
  padding: 6px 16px;
  border-radius: 20px;
  border: 1.5px solid var(--m-outline-variant);
  background: transparent;
  color: var(--m-on-surface-variant);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.18s;
}
.m-status-tab.is-active {
  background: var(--m-primary);
  border-color: var(--m-primary);
  color: var(--m-on-primary);
}
.m-contract-list {
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.m-contract-card {
  background: var(--m-surface-container-lowest);
  border: 1px solid var(--m-outline-variant);
  border-radius: 12px;
  padding: 14px;
}
.m-contract-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.m-contract-card__no {
  font-size: 14px;
  font-weight: 700;
  color: var(--m-on-surface);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-contract-tag {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 8px;
  flex: none;
}
.m-contract-tag--success { background: #dcfce7; color: #15803d; }
.m-contract-tag--info { background: var(--m-surface-container-high); color: var(--m-on-surface-variant); }
.m-contract-tag--warning { background: #fef9c3; color: #854d0e; }
.m-contract-card__delivery,
.m-contract-card__period {
  font-size: 13px;
  color: var(--m-on-surface-variant);
  margin-bottom: 4px;
}
.m-contract-card__rate {
  font-size: 13px;
  color: var(--m-on-surface);
  margin-top: 6px;
}
.m-category-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.m-cat-chip {
  padding: 3px 10px;
  border-radius: 20px;
  background: var(--m-secondary-fixed);
  color: var(--m-primary);
  font-size: 12px;
  font-weight: 500;
}
.m-fab-btn {
  position: fixed;
  bottom: calc(80px + env(safe-area-inset-bottom, 0px));
  right: 16px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 20px;
  border-radius: 28px;
  border: none;
  background: var(--m-primary);
  color: var(--m-on-primary);
  font-size: 14px;
  font-weight: 700;
  box-shadow: 0 4px 16px rgba(0,50,134,0.32);
  cursor: pointer;
  font-family: var(--m-font-body);
}
.m-fab-btn .material-symbols-outlined { font-size: 20px; }
.m-empty {
  text-align: center;
  color: var(--m-on-surface-variant);
  padding: 48px 16px;
  font-size: 14px;
}
</style>
