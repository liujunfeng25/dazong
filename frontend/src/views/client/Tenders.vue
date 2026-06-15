<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listMyTendersApi, tenderMetaApi } from '../../api/contracts'
import { useIsMobile } from '../../composables/useIsMobile'

const router = useRouter()
const route = useRoute()
const { isMobile } = useIsMobile()
const loading = ref(false)
const list = ref([])
const categoryNameMap = ref({})
const deliveryNameMap = ref({})
const categoryNames = (row) =>
  (row.category_ids_json || []).map((id) => categoryNameMap.value[id] || `一级分类#${id}`).join('、')
const deliveryNames = (row) =>
  (row.delivery_ids_json || []).map((id) => deliveryNameMap.value[id] || `配送方#${id}`).join('、')
const statusType = computed(() => ({ 招标中: 'warning', 已中标: 'success', 已关闭: 'info' }))

const load = async () => {
  loading.value = true
  try {
    const [rows, meta] = await Promise.all([listMyTendersApi(), tenderMetaApi()])
    list.value = rows
    categoryNameMap.value = Object.fromEntries((meta.level1_categories || []).map((i) => [i.id, i.name]))
    deliveryNameMap.value = Object.fromEntries(
      (meta.deliveries || []).map((i) => [i.id, i.company_name || i.username || `配送方#${i.id}`]),
    )
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
    <div v-if="loading" class="m-empty">加载中...</div>
    <div v-else-if="!list.length" class="m-empty">暂无招标记录，先去发起招标</div>
    <div v-else class="m-tender-list">
      <div v-for="row in list" :key="row.id" class="m-tender-card">
        <div class="m-tender-card__top">
          <span class="m-tender-card__id">招标 #{{ row.id }}</span>
          <span class="m-tender-tag" :class="`m-tender-tag--${statusType[row.status] || 'info'}`">{{ row.status }}</span>
        </div>
        <div class="m-tender-card__cats">
          <span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle;margin-right:2px">category</span>
          {{ categoryNames(row) || '全部分类' }}
        </div>
        <div class="m-tender-card__delivery">
          <span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle;margin-right:2px">local_shipping</span>
          {{ deliveryNames(row) || '—' }}
        </div>
        <div class="m-tender-card__period">
          <span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle;margin-right:2px">date_range</span>
          {{ row.period_start || '—' }} ~ {{ row.period_end || '—' }}
        </div>
        <div class="m-tender-card__footer">
          <span class="m-tender-bid-count">{{ row.bid_count || 0 }} 个报价</span>
          <button class="m-tender-action-btn" @click="router.push(`/client/contracts/${row.id}/bids`)">
            查看报价 / 定标
            <span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle">chevron_right</span>
          </button>
        </div>
      </div>
    </div>

    <button class="m-fab-btn" @click="router.push('/client/contracts/new')">
      <span class="material-symbols-outlined">add</span>
      发起招标
    </button>
  </div>

  <!-- ── PC ── -->
  <el-card v-else>
    <el-table v-loading="loading" :data="list" border empty-text="暂无招标记录，先去发起招标">
      <el-table-column prop="id" label="招标编号" width="100" />
      <el-table-column label="一级分类" min-width="280">
        <template #default="{ row }">
          {{ categoryNames(row) || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="邀请配送方" min-width="220">
        <template #default="{ row }">{{ deliveryNames(row) }}</template>
      </el-table-column>
      <el-table-column prop="bid_count" label="已报价数" width="100" />
      <el-table-column prop="status" label="进度" width="120">
        <template #default="{ row }">
          <el-tag :type="statusType[row.status] || 'info'">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="period_start" label="开始" min-width="120" />
      <el-table-column prop="period_end" label="结束" min-width="120" />
      <el-table-column label="操作" width="180" align="center">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="router.push(`/client/contracts/${row.id}/bids`)">
            查看报价 / 选择中标
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>
<style scoped>
/* ── Mobile styles ── */
.m-page {
  font-family: var(--m-font-body);
  padding-bottom: 80px;
  position: relative;
  min-height: 100%;
}
.m-tender-list {
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.m-tender-card {
  background: var(--m-surface-container-lowest);
  border: 1px solid var(--m-outline-variant);
  border-radius: 12px;
  padding: 14px;
}
.m-tender-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.m-tender-card__id {
  font-size: 15px;
  font-weight: 700;
  color: var(--m-on-surface);
  font-family: var(--m-font-display);
}
.m-tender-tag {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: 8px;
}
.m-tender-tag--warning { background: #fef9c3; color: #854d0e; }
.m-tender-tag--success { background: #dcfce7; color: #15803d; }
.m-tender-tag--info { background: var(--m-surface-container-high); color: var(--m-on-surface-variant); }
.m-tender-card__cats,
.m-tender-card__delivery,
.m-tender-card__period {
  font-size: 13px;
  color: var(--m-on-surface-variant);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-tender-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}
.m-tender-bid-count {
  font-size: 13px;
  font-weight: 600;
  color: var(--m-secondary);
}
.m-tender-action-btn {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1.5px solid var(--m-primary);
  background: transparent;
  color: var(--m-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: var(--m-font-body);
  display: flex;
  align-items: center;
  gap: 2px;
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
