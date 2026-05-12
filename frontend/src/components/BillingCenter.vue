<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Checked, CreditCard, Refresh } from '@element-plus/icons-vue'
import {
  confirmBillingStatementApi,
  listBillingStatementsApi,
  settleBillingStatementApi,
} from '../api/bills'
import { formatChinaDateTime } from '../utils/datetime'

const props = defineProps({
  title: { type: String, default: '账单中心' },
  description: { type: String, default: '按账期查看应收应付，订单明细可展开核对。' },
})

const loading = ref(false)
const statements = ref([])
const active = ref(null)

const money = (value) => `¥${Number(value || 0).toLocaleString()}`
const remainingAmount = (row) => Math.max(0, Number(row?.amount || 0) - Number(row?.settled_amount || 0))
const canPay = (row) => row?.direction === '应付' && row?.status !== '已结清'
const orders = computed(() => active.value?.source_snapshot_json?.orders || [])
const allocations = computed(() => active.value?.source_snapshot_json?.allocations || [])
const businessTitle = (row) => {
  if (!row) return '业务账单'
  if (row.role === 'client' && row.direction === '应付') return '我应付给配送商'
  if (row.role === 'delivery' && row.direction === '应收') return '客户（食堂）待付给我'
  if (row.role === 'delivery' && row.direction === '应付') return '我应付给供货商/厂家'
  if (['supplier', 'factory'].includes(row.role) && row.direction === '应收') return '配送商待付给我'
  return row.display_title || row.remark || '业务账单'
}
const summary = computed(() => {
  const payable = statements.value.filter((item) => item.direction === '应付')
  const receivable = statements.value.filter((item) => item.direction === '应收')
  return {
    payable: payable.reduce((sum, item) => sum + remainingAmount(item), 0),
    receivable: receivable.reduce((sum, item) => sum + remainingAmount(item), 0),
    unsettled: statements.value.filter((item) => item.status !== '已结清').length,
  }
})

const load = async () => {
  loading.value = true
  try {
    statements.value = await listBillingStatementsApi()
    active.value = statements.value[0] || null
  } finally {
    loading.value = false
  }
}

const confirmStatement = async (row) => {
  await confirmBillingStatementApi(row.id, { remark: '已核对' })
  ElMessage.success('已确认账单')
  await load()
}

const settleStatement = async (row) => {
  const amount = remainingAmount(row)
  await ElMessageBox.confirm(`确认已完成付款 ${money(amount)}？系统会同步给收款方。`, '结清账单', {
    confirmButtonText: '确认结清',
    cancelButtonText: '再核对一下',
    type: 'warning',
  })
  await settleBillingStatementApi(row.id, { amount, remark: '付款方已结清' })
  ElMessage.success('已结清账单')
  await load()
}

onMounted(load)
</script>

<template>
  <div class="billing-center">
    <section class="billing-head">
      <div>
        <div class="title-row">
          <el-icon><CreditCard /></el-icon>
          <h1>{{ props.title }}</h1>
        </div>
        <p>{{ props.description }}</p>
      </div>
      <el-button type="primary" :loading="loading" @click="load">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </section>

    <section class="summary-grid">
      <div class="metric">
        <span>本期待付款</span>
        <strong>{{ money(summary.payable) }}</strong>
      </div>
      <div class="metric">
        <span>本期待收款</span>
        <strong>{{ money(summary.receivable) }}</strong>
      </div>
      <div class="metric">
        <span>未完成账单</span>
        <strong>{{ summary.unsettled }}</strong>
      </div>
    </section>

    <section class="workbench">
      <el-card shadow="never" class="list-panel">
        <template #header>
          <div class="panel-title">账单列表</div>
        </template>
        <el-skeleton v-if="loading" :rows="6" animated />
        <el-empty v-else-if="!statements.length" description="暂无需要处理的账单" />
        <div v-else class="statement-list">
          <button
            v-for="item in statements"
            :key="item.id"
            type="button"
            class="statement-card"
            :class="{ active: active?.id === item.id }"
            @click="active = item"
          >
            <span class="statement-main">{{ businessTitle(item) }}</span>
            <span class="statement-meta">
              <span>对方：{{ item.counterparty_name || '未命名单位' }}</span>
              <span>涉及订单：{{ (item.order_numbers || []).join('、') || '见详情' }}</span>
            </span>
            <span class="statement-bottom">
              <strong>{{ money(item.amount) }}</strong>
              <el-tag :type="item.status === '已结清' ? 'success' : item.direction === '应付' ? 'warning' : 'info'">
                {{ item.status }}
              </el-tag>
            </span>
          </button>
        </div>
      </el-card>

      <el-card shadow="never" class="detail-panel">
        <template #header>
          <div class="panel-title">账单详情</div>
        </template>
        <el-empty v-if="!active" description="请选择一条账单" />
        <div v-else class="detail-body">
          <div class="detail-top">
            <div>
              <div class="detail-title">{{ businessTitle(active) }}</div>
              <div class="detail-sub">账单号：{{ active.statement_no }}</div>
            </div>
            <el-tag :type="active.direction === '应付' ? 'warning' : 'success'">{{ active.direction }}</el-tag>
          </div>

          <div class="amount-row">
            <div><span>本期应结金额</span><strong>{{ money(active.amount) }}</strong></div>
            <div><span>已结清</span><strong>{{ money(active.settled_amount) }}</strong></div>
            <div><span>剩余未结</span><strong>{{ money(remainingAmount(active)) }}</strong></div>
          </div>

          <el-alert :title="active.action_hint" type="info" show-icon :closable="false" />

          <div class="action-row" v-if="canPay(active)">
            <el-button @click="confirmStatement(active)">
              <el-icon><Checked /></el-icon>
              核对无误
            </el-button>
            <el-button type="primary" @click="settleStatement(active)">确认已付款</el-button>
          </div>

          <div class="section-title">涉及订单</div>
          <el-table :data="orders" border>
            <el-table-column prop="order_no" label="订单号" min-width="160" />
            <el-table-column label="订单金额" width="140">
              <template #default="{ row }">{{ money(row.amount) }}</template>
            </el-table-column>
          </el-table>

          <template v-if="allocations.length">
            <div class="section-title">商品明细</div>
            <el-table :data="allocations" border>
              <el-table-column prop="product_name" label="商品" min-width="160" />
              <el-table-column prop="spec" label="规格" min-width="120" />
              <el-table-column prop="quantity" label="数量" width="100" />
              <el-table-column prop="unit" label="单位" width="80" />
              <el-table-column label="金额" width="140">
                <template #default="{ row }">{{ money(row.amount) }}</template>
              </el-table-column>
            </el-table>
          </template>

          <div class="detail-foot">创建时间：{{ formatChinaDateTime(active.created_at) }}</div>
        </div>
      </el-card>
    </section>
  </div>
</template>

<style scoped>
.billing-center {
  display: grid;
  gap: 16px;
}
.billing-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 18px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: #fff;
}
.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
h1 {
  margin: 0;
  font-size: 22px;
}
p {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.metric {
  padding: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: #fff;
}
.metric span {
  color: var(--el-text-color-secondary);
}
.metric strong {
  display: block;
  margin-top: 8px;
  font-size: 22px;
}
.workbench {
  display: grid;
  grid-template-columns: minmax(300px, 0.9fr) minmax(0, 1.6fr);
  gap: 16px;
}
.list-panel,
.detail-panel {
  border-radius: 8px;
}
.panel-title,
.section-title {
  font-weight: 700;
}
.statement-list {
  display: grid;
  gap: 10px;
}
.statement-card {
  display: grid;
  gap: 8px;
  width: 100%;
  padding: 14px;
  text-align: left;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
}
.statement-card.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.statement-main {
  font-weight: 700;
}
.statement-meta,
.statement-bottom {
  display: flex;
  gap: 10px;
  justify-content: space-between;
  flex-wrap: wrap;
  color: var(--el-text-color-secondary);
}
.detail-body {
  display: grid;
  gap: 16px;
}
.detail-top,
.action-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}
.detail-title {
  font-size: 20px;
  font-weight: 800;
}
.detail-sub,
.detail-foot {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
}
.amount-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.amount-row div {
  padding: 14px;
  border-radius: 8px;
  background: #f8fafc;
}
.amount-row span {
  display: block;
  color: var(--el-text-color-secondary);
}
.amount-row strong {
  display: block;
  margin-top: 8px;
  font-size: 18px;
}
@media (max-width: 900px) {
  .billing-head,
  .detail-top,
  .action-row {
    flex-direction: column;
    align-items: stretch;
  }
  .summary-grid,
  .workbench,
  .amount-row {
    grid-template-columns: 1fr;
  }
}
</style>
