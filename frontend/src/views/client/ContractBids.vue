<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { awardTenderApi, listTenderBidsApi, tenderAwardContextApi } from '../../api/contracts'
import { formatChinaDateTime } from '../../utils/datetime'
import { useIsMobile } from '../../composables/useIsMobile'

const route = useRoute()
const router = useRouter()
const { isMobile } = useIsMobile()
const list = ref([])
const loading = ref(false)
const awarding = ref(false)
const awardContext = ref(null)

const tenderId = computed(() => Number(route.params.id) || 0)

const deliveryAwardInfo = (deliveryId) => {
  const map = awardContext.value?.per_delivery || {}
  return map[String(deliveryId)] || map[deliveryId] || { can_award: true, reason: '' }
}

const canAward = (deliveryId) => {
  if (awardContext.value?.status && awardContext.value.status !== '招标中') return false
  return deliveryAwardInfo(deliveryId).can_award !== false
}

const load = async () => {
  if (!tenderId.value) return
  loading.value = true
  try {
    const [bids, ctx] = await Promise.all([
      listTenderBidsApi(tenderId.value),
      tenderAwardContextApi(tenderId.value),
    ])
    list.value = bids
    awardContext.value = ctx
  } finally {
    loading.value = false
  }
}

const award = async (deliveryId) => {
  if (awarding.value) return
  const info = deliveryAwardInfo(deliveryId)
  if (!canAward(deliveryId)) {
    ElMessage.warning(info.reason || '该配送商当前不可定标')
    return
  }
  let confirmText = '确认将该配送单位设为中标吗？确认后将生成合约并结束本次招标。'
  if (info.reason) {
    confirmText = `${info.reason}\n\n${confirmText}`
  }
  if (awardContext.value?.has_overlap && awardContext.value?.message) {
    confirmText = `${awardContext.value.message}\n\n${confirmText}`
  }
  await ElMessageBox.confirm(confirmText, '中标确认', {
    type: 'warning',
    confirmButtonText: '确认中标',
    cancelButtonText: '取消',
    customClass: 'award-confirm-dialog',
    confirmButtonClass: 'award-confirm-btn',
    cancelButtonClass: 'award-cancel-btn',
  })
  awarding.value = true
  try {
    await awardTenderApi(tenderId.value, { delivery_id: deliveryId })
    ElMessage.success('中标已确认，正在跳转到我的合约')
    router.push('/client/contracts')
  } finally {
    awarding.value = false
  }
}

onMounted(load)
watch(() => route.fullPath, load)
</script>

<template>
  <!-- ── Mobile ── -->
  <div v-if="isMobile" v-loading="loading" class="m-page">
    <div class="m-bids-header">
      <div class="m-bids-header__title">招标 #{{ tenderId }}</div>
      <div v-if="awardContext" class="m-bids-header__sub">
        {{ awardContext.period_start }} ~ {{ awardContext.period_end }}
        <span v-if="awardContext.status" class="m-tender-status" :class="awardContext.status === '招标中' ? 'm-tender-status--active' : 'm-tender-status--closed'">
          {{ awardContext.status }}
        </span>
      </div>
    </div>

    <div v-if="awardContext?.has_overlap && awardContext?.message" class="m-overlap-alert">
      <span class="material-symbols-outlined" style="font-size:18px">warning</span>
      {{ awardContext.message }}
    </div>
    <div v-else-if="awardContext && awardContext.status !== '招标中'" class="m-info-alert">
      <span class="material-symbols-outlined" style="font-size:18px">info</span>
      本次招标已结束，无法再定标。
    </div>

    <div v-if="!list.length && !loading" class="m-empty">暂无报价</div>
    <div v-else class="m-bids-list">
      <div v-for="row in list" :key="row.delivery_id" class="m-bid-card" :class="{ 'is-winner': !canAward(row.delivery_id) && awardContext?.status === '已中标' }">
        <div class="m-bid-card__top">
          <span class="m-bid-card__name">{{ row.delivery_name || `配送方#${row.delivery_id}` }}</span>
          <span class="m-bid-card__rate">浮动率 {{ Number(row.price_float_rate || 0).toFixed(4) }}</span>
        </div>
        <div class="m-bid-card__time">报价时间：{{ formatChinaDateTime(row.created_at) }}</div>
        <div v-if="row.category_rates?.length" class="m-bid-cat-chips">
          <span v-for="item in row.category_rates" :key="item.category_id" class="m-bid-cat-chip">
            {{ item.category_name || `分类#${item.category_id}` }}：{{ Number(item.float_rate || 0).toFixed(4) }}
          </span>
        </div>
        <div v-if="deliveryAwardInfo(row.delivery_id).reason" class="m-bid-card__hint">
          {{ deliveryAwardInfo(row.delivery_id).reason }}
        </div>
        <div class="m-bid-card__actions">
          <el-button
            v-if="canAward(row.delivery_id)"
            type="primary"
            size="small"
            :loading="awarding"
            @click="award(row.delivery_id)"
          >
            确认中标
          </el-button>
          <el-tooltip v-else :content="deliveryAwardInfo(row.delivery_id).reason || '不可定标'" placement="top">
            <span><el-button size="small" disabled>不可定标</el-button></span>
          </el-tooltip>
        </div>
      </div>
    </div>
  </div>

  <!-- ── PC ── -->
  <el-card v-else v-loading="loading">
    <template #header>
      <div class="page-head">
        <div>
          <div class="page-title">招标 #{{ tenderId }} · 查看报价 / 定标</div>
          <div v-if="awardContext" class="page-sub">
            招标周期：{{ awardContext.period_start }} ~ {{ awardContext.period_end }}
            <el-tag
              v-if="awardContext.status"
              size="small"
              :type="awardContext.status === '招标中' ? 'warning' : 'info'"
              style="margin-left: 8px"
            >
              {{ awardContext.status }}
            </el-tag>
          </div>
        </div>
      </div>
    </template>

    <el-alert
      v-if="awardContext?.has_overlap && awardContext?.message"
      type="warning"
      :closable="false"
      show-icon
      class="overlap-alert"
    >
      <template #title>招标周期与现有合约重叠</template>
      <p class="overlap-message">{{ awardContext.message }}</p>
    </el-alert>

    <el-alert
      v-else-if="awardContext && awardContext.status !== '招标中'"
      type="info"
      :closable="false"
      show-icon
      class="overlap-alert"
    >
      本次招标已结束，无法再定标。
    </el-alert>

    <el-table :data="list" border empty-text="暂无报价">
      <el-table-column type="expand" width="50">
        <template #default="{ row }">
          <div class="category-rates">
            <div class="category-rates-title">分类报价明细</div>
            <div v-if="(row.category_rates || []).length" class="category-rate-list">
              <span
                v-for="item in row.category_rates"
                :key="`${row.delivery_id}-${item.category_id}`"
                class="rate-chip"
              >
                {{ item.category_name || `分类#${item.category_id}` }}：{{
                  Number(item.float_rate || 0).toFixed(4)
                }}
              </span>
            </div>
            <div v-else class="category-rates-empty">暂无分类报价明细</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="配送单位" min-width="180">
        <template #default="{ row }">
          {{ row.delivery_name || `配送方#${row.delivery_id}` }}
        </template>
      </el-table-column>
      <el-table-column prop="price_float_rate" label="上浮率" width="140">
        <template #default="{ row }">{{ Number(row.price_float_rate || 0).toFixed(4) }}</template>
      </el-table-column>
      <el-table-column label="报价时间" min-width="180">
        <template #default="{ row }">{{ formatChinaDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="定标说明" min-width="220">
        <template #default="{ row }">
          <span v-if="deliveryAwardInfo(row.delivery_id).reason" class="award-hint">
            {{ deliveryAwardInfo(row.delivery_id).reason }}
          </span>
          <span v-else class="award-hint muted">可定标</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" align="center">
        <template #default="{ row }">
          <el-tooltip
            v-if="!canAward(row.delivery_id)"
            :content="deliveryAwardInfo(row.delivery_id).reason || '不可定标'"
            placement="top"
          >
            <span>
              <el-button size="small" type="primary" disabled>中标</el-button>
            </span>
          </el-tooltip>
          <el-button
            v-else
            size="small"
            type="primary"
            :loading="awarding"
            :disabled="awarding"
            @click="award(row.delivery_id)"
          >
            中标
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.page-title {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}

.page-sub {
  margin-top: 6px;
  font-size: 13px;
  color: #64748b;
}

.overlap-alert {
  margin-bottom: 16px;
}

.overlap-message {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.5;
}

.category-rates {
  padding: 4px 8px;
}

.category-rates-title {
  font-weight: 600;
  margin-bottom: 8px;
}

.category-rate-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.rate-chip {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #334155;
}

.category-rates-empty {
  color: #94a3b8;
}

.award-hint {
  font-size: 12px;
  color: #b45309;
  line-height: 1.4;
}

.award-hint.muted {
  color: #64748b;
}

/* ── Mobile styles ── */
.m-page {
  font-family: var(--m-font-body);
  min-height: 100%;
  padding-bottom: 16px;
}
.m-bids-header {
  padding: 16px;
  background: var(--m-primary);
  color: var(--m-on-primary);
}
.m-bids-header__title {
  font-family: var(--m-font-display);
  font-size: 20px;
  font-weight: 800;
  margin-bottom: 4px;
}
.m-bids-header__sub {
  font-size: 13px;
  opacity: 0.85;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.m-tender-status {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 8px;
}
.m-tender-status--active { background: rgba(255,255,255,0.25); color: #fff; }
.m-tender-status--closed { background: rgba(255,255,255,0.15); color: rgba(255,255,255,0.8); }
.m-overlap-alert {
  margin: 12px 16px;
  padding: 10px 12px;
  background: #fef9c3;
  border: 1px solid #f59e0b;
  border-radius: 10px;
  color: #854d0e;
  font-size: 13px;
  display: flex;
  gap: 6px;
  align-items: flex-start;
}
.m-info-alert {
  margin: 12px 16px;
  padding: 10px 12px;
  background: var(--m-secondary-fixed);
  border: 1px solid var(--m-outline-variant);
  border-radius: 10px;
  color: var(--m-primary);
  font-size: 13px;
  display: flex;
  gap: 6px;
  align-items: flex-start;
}
.m-bids-list {
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.m-bid-card {
  background: var(--m-surface-container-lowest);
  border: 1px solid var(--m-outline-variant);
  border-radius: 12px;
  padding: 14px;
}
.m-bid-card.is-winner {
  border-color: var(--m-primary);
  background: var(--m-secondary-fixed);
}
.m-bid-card__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.m-bid-card__name {
  font-size: 15px;
  font-weight: 700;
  color: var(--m-on-surface);
}
.m-bid-card__rate {
  font-size: 14px;
  font-weight: 800;
  color: var(--m-primary);
  white-space: nowrap;
  font-family: var(--m-font-display);
}
.m-bid-card__time {
  font-size: 12px;
  color: var(--m-on-surface-variant);
  margin-bottom: 6px;
}
.m-bid-cat-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.m-bid-cat-chip {
  padding: 2px 8px;
  border-radius: 20px;
  background: var(--m-surface-container);
  color: var(--m-on-surface-variant);
  font-size: 11px;
}
.m-bid-card__hint {
  font-size: 12px;
  color: #b45309;
  margin-bottom: 8px;
}
.m-bid-card__actions { margin-top: 8px; }
.m-empty {
  text-align: center;
  color: var(--m-on-surface-variant);
  padding: 48px 16px;
  font-size: 14px;
}
</style>
