<script setup>
import { onMounted, ref } from 'vue'
import BillingCenter from '../../components/BillingCenter.vue'
import { listBillingStatementsApi } from '../../api/bills'
import { useIsMobile } from '../../composables/useIsMobile'

const { isMobile } = useIsMobile()
const loading = ref(false)
const statements = ref([])

const load = async () => {
  loading.value = true
  try {
    statements.value = await listBillingStatementsApi()
  } finally {
    loading.value = false
  }
}

const payable = () => statements.value.filter(s => s.direction === '应付')
const payableTotal = () => payable().reduce((sum, s) => sum + Math.max(0, Number(s.amount || 0) - Number(s.settled_amount || 0)), 0)
const unsettledCount = () => statements.value.filter(s => s.status !== '已结清').length
const monthTotal = () => statements.value.reduce((sum, s) => sum + Number(s.amount || 0), 0)

const statusClass = (s) => ({
  '已结清': 'm-bill-tag--settled',
  '待结算': 'm-bill-tag--pending',
  '确认中': 'm-bill-tag--confirming',
})[s] || 'm-bill-tag--pending'

const money = (v) => `¥${Number(v || 0).toLocaleString()}`

onMounted(() => {
  if (isMobile.value) load()
})
</script>

<template>
  <!-- ── Mobile ── -->
  <div v-if="isMobile" v-loading="loading" class="m-page">
    <div class="m-summary-card">
      <div class="m-summary-item">
        <div class="m-summary-label">本期账单</div>
        <div class="m-summary-value">{{ money(monthTotal()) }}</div>
      </div>
      <div class="m-summary-divider" />
      <div class="m-summary-item">
        <div class="m-summary-label">待支付</div>
        <div class="m-summary-value m-summary-value--warn">{{ money(payableTotal()) }}</div>
      </div>
      <div class="m-summary-divider" />
      <div class="m-summary-item">
        <div class="m-summary-label">未结清</div>
        <div class="m-summary-value">{{ unsettledCount() }} 笔</div>
      </div>
    </div>

    <div v-if="!statements.length && !loading" class="m-empty">暂无账单</div>
    <div v-else class="m-bills-list">
      <div v-for="s in statements" :key="s.id" class="m-bill-card">
        <div class="m-bill-card__top">
          <span class="m-bill-card__period">{{ s.period_label || s.period_month || '—' }}</span>
          <span class="m-bill-tag" :class="statusClass(s.status)">{{ s.status || '待结算' }}</span>
        </div>
        <div class="m-bill-card__counterparty">
          {{ s.counterparty_name || s.display_title || '—' }}
        </div>
        <div class="m-bill-card__amounts">
          <div class="m-bill-card__amount">
            <div class="m-bill-amount-label">账单金额</div>
            <div class="m-bill-amount-value">{{ money(s.amount) }}</div>
          </div>
          <div class="m-bill-card__amount">
            <div class="m-bill-amount-label">已结算</div>
            <div class="m-bill-amount-value m-bill-amount-value--settled">{{ money(s.settled_amount) }}</div>
          </div>
          <div class="m-bill-card__amount">
            <div class="m-bill-amount-label">待支付</div>
            <div class="m-bill-amount-value m-bill-amount-value--pending">{{ money(Math.max(0, Number(s.amount || 0) - Number(s.settled_amount || 0))) }}</div>
          </div>
        </div>
        <div v-if="s.payment_due_date" class="m-bill-card__due">
          付款截止：{{ s.payment_due_date }}
        </div>
      </div>
    </div>
  </div>

  <!-- ── PC ── -->
  <BillingCenter
    v-else
    title="学校付款账簿"
    description="按配送服务方与账期汇总学校应付，核对订单后完成确认与结清。"
  />
</template>

<style scoped>
/* ── Mobile styles ── */
.m-page {
  font-family: var(--m-font-body);
  min-height: 100%;
  padding-bottom: 16px;
}
.m-summary-card {
  background: linear-gradient(135deg, var(--m-primary) 0%, var(--m-primary-container) 100%);
  color: var(--m-on-primary);
  margin: 12px 16px;
  border-radius: 14px;
  padding: 20px 16px;
  display: flex;
  align-items: stretch;
  gap: 0;
}
.m-summary-item {
  flex: 1;
  text-align: center;
}
.m-summary-label {
  font-size: 12px;
  opacity: 0.8;
  margin-bottom: 6px;
}
.m-summary-value {
  font-family: var(--m-font-display);
  font-size: 18px;
  font-weight: 800;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.m-summary-value--warn { color: #fde68a; }
.m-summary-divider {
  width: 1px;
  background: rgba(255,255,255,0.25);
  margin: 0 4px;
}
.m-bills-list {
  padding: 0 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.m-bill-card {
  background: var(--m-surface-container-lowest);
  border: 1px solid var(--m-outline-variant);
  border-radius: 12px;
  padding: 14px;
}
.m-bill-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.m-bill-card__period {
  font-family: var(--m-font-display);
  font-size: 15px;
  font-weight: 700;
  color: var(--m-on-surface);
}
.m-bill-tag {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: 8px;
}
.m-bill-tag--settled { background: #dcfce7; color: #15803d; }
.m-bill-tag--pending { background: #fef9c3; color: #854d0e; }
.m-bill-tag--confirming { background: var(--m-secondary-fixed); color: var(--m-primary); }
.m-bill-card__counterparty {
  font-size: 13px;
  color: var(--m-on-surface-variant);
  margin-bottom: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-bill-card__amounts {
  display: flex;
  gap: 8px;
}
.m-bill-card__amount {
  flex: 1;
  background: var(--m-surface-container-low);
  border-radius: 8px;
  padding: 8px;
  text-align: center;
}
.m-bill-amount-label {
  font-size: 11px;
  color: var(--m-on-surface-variant);
  margin-bottom: 3px;
}
.m-bill-amount-value {
  font-size: 13px;
  font-weight: 700;
  color: var(--m-on-surface);
}
.m-bill-amount-value--settled { color: #15803d; }
.m-bill-amount-value--pending { color: #b45309; }
.m-bill-card__due {
  margin-top: 8px;
  font-size: 12px;
  color: var(--m-on-surface-variant);
}
.m-empty {
  text-align: center;
  color: var(--m-on-surface-variant);
  padding: 48px 16px;
  font-size: 14px;
}
</style>
