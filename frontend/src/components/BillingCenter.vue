<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowRight,
  Calendar,
  Check,
  Clock,
  CreditCard,
  Refresh,
  Search,
  Warning,
  Wallet,
} from '@element-plus/icons-vue'
import { useUserStore } from '../stores/user'
import {
  listReconciliationsApi,
  getReconciliationApi,
  confirmReconciliationApi,
  settleReconciliationApi,
  exportReconciliationApi,
} from '../api/bills'

const props = defineProps({
  title: { type: String, default: '账单中心' },
  description: { type: String, default: '按对手方与账期合并对账，确认一次、结清一次。' },
})

const userStore = useUserStore()
const role = computed(() => userStore.role)
const isDelivery = computed(() => role.value === 'delivery')
const isClient = computed(() => role.value === 'client')
const direction = ref('应付') // 配送商默认看「我要付」
// 采购端：对账单按食堂一张，默认只看当前食堂会话，可切全校合并
const reconScope = ref('current_canteen')

const loading = ref(false)
const recons = ref([])
const filters = ref({ status: '', keyword: '' })
const drawerVisible = ref(false)
const detailLoading = ref(false)
const activeRecon = ref(null)
const activeStatements = ref([])
const expandedOrders = ref({})

const money = (v) =>
  `¥${Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

// 单方向端：client 只应付；supplier/factory 只应收
const fixedDirection = computed(() => {
  if (role.value === 'client') return '应付'
  if (role.value === 'supplier' || role.value === 'factory') return '应收'
  return null
})
const activeDirection = computed(() => (isDelivery.value ? direction.value : fixedDirection.value))

const inDirection = (list) =>
  activeDirection.value ? list.filter((r) => r.direction === activeDirection.value) : list

const visibleRecons = computed(() => {
  let list = inDirection(recons.value)
  if (filters.value.status) list = list.filter((r) => r.status === filters.value.status)
  if (filters.value.keyword) {
    const k = filters.value.keyword
    list = list.filter(
      (r) =>
        (r.counterparty_name || '').includes(k) ||
        (r.period_label || '').includes(k) ||
        (r.canteen_name || '').includes(k),
    )
  }
  return list
})

const statusOrder = ['进行中', '待确认', '已确认', '部分结清', '已结清']
const statusMeta = {
  进行中: { label: '账期累计', hint: '等待关账' },
  待确认: { label: '待核对', hint: '确认金额' },
  已确认: { label: '已确认', hint: '等待付款' },
  部分结清: { label: '部分结清', hint: '仍有余额' },
  已结清: { label: '完成清算', hint: '账务闭环' },
}
const statusCounts = computed(() => {
  const counts = Object.fromEntries(statusOrder.map((status) => [status, 0]))
  for (const row of inDirection(recons.value)) {
    if (counts[row.status] !== undefined) counts[row.status] += 1
  }
  return counts
})

const summary = computed(() => {
  const list = inDirection(recons.value)
  return {
    label: activeDirection.value === '应收' ? '待收款' : '待付款',
    unsettled: list
      .filter((r) => r.status !== '已结清')
      .reduce((s, r) => s + Number(r.unsettled_amount || 0), 0),
    settled: list.reduce((s, r) => s + Number(r.settled_amount || 0), 0),
    pending: list.filter((r) => r.status !== '已结清').length,
    awaitingConfirm: list.filter((r) => r.status === '待确认').length,
    overdue: list.filter((r) => r.overdue).length,
  }
})

const roleCopy = computed(() => {
  if (role.value === 'client') return { eyebrow: 'SCHOOL PAYMENT LEDGER', counterparty: '配送服务方', action: '核对并完成学校付款' }
  if (role.value === 'supplier') return { eyebrow: 'SUPPLIER RECEIVABLE LEDGER', counterparty: '配送服务方', action: '跟踪配送商确认与到账' }
  if (role.value === 'factory') return { eyebrow: 'FACTORY RECEIVABLE LEDGER', counterparty: '配送服务方', action: '跟踪厂家货款清算进度' }
  return { eyebrow: 'SETTLEMENT CONTROL DESK', counterparty: '业务对手方', action: '统一管理应付与应收清算' }
})
const roleAccent = computed(() => ({
  client: '#4f7cff',
  delivery: '#0ea5e9',
  supplier: '#f97316',
  factory: '#22c55e',
})[role.value] || '#0ea5e9')

const directionCopy = computed(() => activeDirection.value === '应收'
  ? { title: '应收清算', label: '待收余额', helper: '由付款方完成结清，你可以跟踪确认与到账状态' }
  : { title: '应付清算', label: '待付余额', helper: '完成核对后可整月结清，结果会同步给收款方' })

const load = async () => {
  loading.value = true
  try {
    recons.value = await listReconciliationsApi(
      isClient.value ? { recon_scope: reconScope.value } : {},
    )
  } finally {
    loading.value = false
  }
}

const setScope = async (scope) => {
  if (reconScope.value === scope) return
  reconScope.value = scope
  await load()
}

const openDetail = async (row) => {
  activeRecon.value = row
  activeStatements.value = []
  expandedOrders.value = {}
  drawerVisible.value = true
  detailLoading.value = true
  try {
    const detail = await getReconciliationApi(row.id)
    activeRecon.value = { ...row, ...detail }
    activeStatements.value = detail.statements || []
  } catch {
    activeStatements.value = []
  } finally {
    detailLoading.value = false
  }
}

const canConfirm = (r) => r.status === '待确认'
const canSettle = (r) => r.direction === '应付' && (r.status === '已确认' || r.status === '部分结清')

const doConfirm = async (r) => {
  try {
    await ElMessageBox.confirm(
      `确认对「${r.counterparty_name}」账单 ${money(r.unsettled_amount ?? r.payable_amount)} 核对无误？确认后状态变为「已确认」，可进入结清环节。`,
      '核对确认',
      {
        confirmButtonText: '确认无误',
        cancelButtonText: '再核对一下',
        type: 'warning',
        customClass: 'bc-confirm-dialog',
      },
    )
  } catch {
    return
  }
  await confirmReconciliationApi(r.id, { remark: '已核对' })
  ElMessage.success('已确认对账单')
  await load()
  if (drawerVisible.value) await openDetail(recons.value.find((row) => row.id === r.id) || r)
}

const doSettle = async (r) => {
  try {
    await ElMessageBox.confirm(
      `确认整月结清给「${r.counterparty_name}」${money(r.unsettled_amount)}？系统会同步给收款方。`,
      '结清对账单',
      {
        confirmButtonText: '确认结清',
        cancelButtonText: '再核对一下',
        customClass: 'bc-confirm-dialog',
      },
    )
  } catch {
    return
  }
  await settleReconciliationApi(r.id, { amount: Number(r.unsettled_amount) })
  ElMessage.success('已结清对账单')
  await load()
  if (drawerVisible.value) await openDetail(recons.value.find((row) => row.id === r.id) || r)
}

const doExport = async (r) => {
  try {
    const blob = await exportReconciliationApi(r.id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `对账单-${r.counterparty_name}-${r.period_label}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('导出失败')
  }
}

const statusClass = (s) =>
  ({ 进行中: 'is-running', 待确认: 'is-pending', 已确认: 'is-confirmed', 部分结清: 'is-partial', 已结清: 'is-settled' })[s] ||
  'is-pending'

const orderText = (m) => {
  const ss = m.source_snapshot_json || {}
  const nums = ss.order_numbers || ss.order_ids
  if (Array.isArray(nums) && nums.length) return nums.join('、')
  return m.remark || `明细 #${m.id}`
}

// 单条账单（一张订单×对手方）下挂的商品明细：订货量/实收量、计费金额与少收扣减
const orderLines = (m) => {
  const ss = m.source_snapshot_json || {}
  if (Array.isArray(ss.allocations) && ss.allocations.length) {
    // 供货腿（供货价）：实收量 = 订货量 × 计费比例
    return ss.allocations.map((a, i) => {
      const ratio = Number(a.bill_ratio ?? 1)
      const orderedQty = Number(a.quantity || 0)
      const original = Number(a.original_amount ?? a.amount ?? 0)
      const billed = Number(a.amount || 0)
      return {
        name: a.product_name || `明细 #${i + 1}`,
        spec: a.spec || '',
        unit: a.unit || '',
        orderedQty,
        receivedQty: Math.round(orderedQty * ratio * 1000) / 1000,
        price: Number(a.unit_price || 0),
        original,
        billed,
        deduction: Math.max(0, original - billed),
        ratio,
      }
    })
  }
  const rb = ss.receiving_billing || {}
  if (Array.isArray(rb.lines) && rb.lines.length) {
    // 客户腿（客户价）：快照已带订货/实收量与扣减
    return rb.lines.map((l, i) => {
      const original = Number(l.ordered_amount ?? 0)
      const billed = Number(l.received_amount ?? 0)
      return {
        name: l.product_name || `明细 #${l.line_index ?? i + 1}`,
        spec: l.spec || '',
        unit: l.measure_unit || l.unit || '',
        orderedQty: Number(l.ordered_qty ?? l.ordered_kg ?? 0),
        receivedQty: Number(l.received_qty ?? l.received_kg ?? 0),
        price: Number(l.unit_price || 0),
        original,
        billed,
        deduction: Math.max(0, Number(l.deduction_amount ?? original - billed)),
        ratio: Number(l.bill_ratio ?? 1),
      }
    })
  }
  return []
}

// 本账单汇总（只统计本账单自己展示的行，避免供货腿误用整单合计）
const orderSummary = (m) => {
  const lines = orderLines(m)
  if (!lines.length) return null
  const original = lines.reduce((s, l) => s + Number(l.original || 0), 0)
  const billed = lines.reduce((s, l) => s + Number(l.billed || 0), 0)
  const deduction = lines.reduce((s, l) => s + Number(l.deduction || 0), 0)
  if (deduction < 0.01) return null
  return { original, billed, deduction }
}
const toggleOrder = (m) => {
  const has = orderLines(m).length
  if (!has) return
  expandedOrders.value = { ...expandedOrders.value, [m.id]: !expandedOrders.value[m.id] }
}

const settlementProgress = (row) => {
  const total = Number(row.payable_amount || 0)
  return total > 0 ? Math.min(100, Math.max(0, Number(row.settled_amount || 0) / total * 100)) : 0
}

const selectStatus = (status) => {
  filters.value.status = filters.value.status === status ? '' : status
}
const clearFilters = () => {
  filters.value = { status: '', keyword: '' }
}

onMounted(load)
</script>

<template>
  <div class="settlement-desk" v-loading="loading" element-loading-text="正在同步清算数据…">
    <header class="desk-hero">
      <div class="hero-copy">
        <p>{{ roleCopy.eyebrow }}</p>
        <div class="hero-title">
          <span class="hero-mark"><el-icon><CreditCard /></el-icon></span>
          <div>
            <h1>{{ title }}</h1>
            <span>{{ description }}</span>
          </div>
        </div>
      </div>
      <div class="hero-actions">
        <div v-if="isDelivery" class="direction-switch" aria-label="账务方向">
          <button type="button" :class="{ active: direction === '应付' }" @click="direction = '应付'">
            <span>PAYABLE</span>我要付
          </button>
          <button type="button" :class="{ active: direction === '应收' }" @click="direction = '应收'">
            <span>RECEIVABLE</span>别人付我
          </button>
        </div>
        <div v-if="isClient" class="direction-switch" aria-label="对账范围">
          <button type="button" :class="{ active: reconScope === 'current_canteen' }" @click="setScope('current_canteen')">
            <span>CANTEEN</span>当前食堂
          </button>
          <button type="button" :class="{ active: reconScope === 'school_merged' }" @click="setScope('school_merged')">
            <span>SCHOOL</span>全校合并
          </button>
        </div>
        <button type="button" class="refresh-button" :disabled="loading" @click="load">
          <el-icon><Refresh /></el-icon>刷新数据
        </button>
      </div>
    </header>

    <section class="balance-band">
      <div class="balance-primary">
        <span>{{ directionCopy.label }}</span>
        <strong>{{ money(summary.unsettled) }}</strong>
        <small>{{ directionCopy.helper }}</small>
      </div>
      <div class="balance-metric">
        <span>累计已结清</span>
        <strong>{{ money(summary.settled) }}</strong>
        <small>当前方向历史清算金额</small>
      </div>
      <div class="balance-metric">
        <span>待处理账期</span>
        <strong>{{ summary.pending }}<em>笔</em></strong>
        <small>其中 {{ summary.awaitingConfirm }} 笔等待核对</small>
      </div>
      <div class="balance-metric risk" :class="{ active: summary.overdue }">
        <span>逾期账期</span>
        <strong>{{ summary.overdue }}<em>笔</em></strong>
        <small>{{ summary.overdue ? '需要优先完成清算' : '当前没有逾期事项' }}</small>
      </div>
    </section>

    <section class="clearing-orbit">
      <div class="section-heading">
        <div>
          <p>SETTLEMENT ORBIT</p>
          <h2>账期清算轨道</h2>
        </div>
        <span>{{ roleCopy.action }}</span>
      </div>
      <div class="orbit-track">
        <button
          v-for="(status, index) in statusOrder"
          :key="status"
          type="button"
          class="orbit-node"
          :class="[statusClass(status), { selected: filters.status === status }]"
          @click="selectStatus(status)"
        >
          <span class="node-index">{{ String(index + 1).padStart(2, '0') }}</span>
          <div>
            <strong>{{ statusMeta[status].label }}</strong>
            <small>{{ statusMeta[status].hint }}</small>
          </div>
          <b>{{ statusCounts[status] }}</b>
        </button>
      </div>
    </section>

    <section class="ledger">
      <div class="ledger-head">
        <div>
          <p>COUNTERPARTY LEDGER</p>
          <h2>{{ directionCopy.title }}台账</h2>
          <span>按对手方和账期汇总，点击任意账期查看订单明细</span>
        </div>
        <div class="ledger-tools">
          <label class="search-field">
            <el-icon><Search /></el-icon>
            <input v-model.trim="filters.keyword" type="search" placeholder="搜索对手方或账期" />
          </label>
          <select v-model="filters.status" class="status-filter" aria-label="筛选账单状态">
            <option value="">全部状态</option>
            <option v-for="status in statusOrder" :key="status">{{ status }}</option>
          </select>
        </div>
      </div>

      <div v-if="!visibleRecons.length" class="ledger-empty">
        <span><el-icon><Wallet /></el-icon></span>
        <strong>当前筛选下暂无对账单</strong>
        <p>清除搜索条件或切换账务方向后查看。</p>
        <button v-if="filters.keyword || filters.status" type="button" @click="clearFilters">清除筛选</button>
      </div>

      <div v-else class="ledger-table">
        <div class="ledger-row ledger-columns" aria-hidden="true">
          <span>对手方 / 账期</span>
          <span>待结金额</span>
          <span>清算进度</span>
          <span>关键日期</span>
          <span>状态</span>
          <span>下一步</span>
        </div>
        <article
          v-for="row in visibleRecons"
          :key="row.id"
          class="ledger-row ledger-entry"
          :class="{ overdue: row.overdue }"
          tabindex="0"
          @click="openDetail(row)"
          @keydown.enter="openDetail(row)"
        >
          <div class="party-cell">
            <span class="party-avatar">{{ (row.counterparty_name || '对').slice(0, 1) }}</span>
            <div>
              <strong :title="row.counterparty_name">{{ row.counterparty_name || '未命名单位' }}</strong>
              <small>{{ row.period_label || '未设置账期' }} · {{ row.item_count }} 笔订单<template v-if="row.canteen_name"> · {{ row.canteen_name }}</template></small>
            </div>
          </div>
          <div class="amount-cell">
            <strong>{{ money(row.unsettled_amount) }}</strong>
            <small>账期总额 {{ money(row.payable_amount) }}</small>
          </div>
          <div class="progress-cell">
            <div><i :style="{ width: `${settlementProgress(row)}%` }"></i></div>
            <span>已结 {{ money(row.settled_amount) }} · {{ settlementProgress(row).toFixed(0) }}%</span>
          </div>
          <div class="date-cell">
            <span><el-icon><Calendar /></el-icon>关账 {{ row.close_at || '—' }}</span>
            <small>确认 {{ row.confirm_due_date || '—' }} · 付款 {{ row.payment_due_date || '—' }}</small>
          </div>
          <div class="state-cell">
            <span class="status-pill" :class="statusClass(row.status)">{{ row.status }}</span>
            <small v-if="row.overdue"><el-icon><Warning /></el-icon>已逾期</small>
            <small v-else-if="row.status === '进行中'"><el-icon><Clock /></el-icon>等待关账</small>
          </div>
          <div class="action-cell" @click.stop>
            <button v-if="canConfirm(row)" type="button" class="row-action confirm" @click="doConfirm(row)">核对无误</button>
            <button v-else-if="canSettle(row)" type="button" class="row-action settle" @click="doSettle(row)">去结清</button>
            <button v-else type="button" class="row-action detail" @click="openDetail(row)">
              查看详情<el-icon><ArrowRight /></el-icon>
            </button>
          </div>
        </article>
      </div>
    </section>

    <el-drawer
      v-model="drawerVisible"
      direction="rtl"
      size="min(720px, 94vw)"
      :with-header="false"
      class="billing-detail-drawer"
    >
      <div
        v-if="activeRecon"
        class="drawer-shell"
        :style="{ '--desk-accent': roleAccent }"
        v-loading="detailLoading"
      >
        <header class="drawer-head">
          <div>
            <p>RECONCILIATION DETAIL</p>
            <h2>{{ activeRecon.counterparty_name || '账单详情' }}</h2>
            <span>{{ activeRecon.period_label }}<template v-if="activeRecon.canteen_name"> · {{ activeRecon.canteen_name }}</template> · 对账单 {{ activeRecon.statement_no }}</span>
          </div>
          <button type="button" aria-label="关闭账单详情" @click="drawerVisible = false">×</button>
        </header>

        <section class="drawer-conclusion" :class="{ risk: activeRecon.overdue }">
          <span class="conclusion-icon">
            <el-icon><Warning v-if="activeRecon.overdue" /><Check v-else /></el-icon>
          </span>
          <div>
            <strong>{{ activeRecon.overdue ? '该账期已逾期，需要优先处理' : `${activeRecon.status}，清算状态正常` }}</strong>
            <small>{{ activeRecon.direction === '应收' ? '付款操作由对手方完成，本端同步查看到账状态。' : directionCopy.helper }}</small>
          </div>
          <span class="status-pill" :class="statusClass(activeRecon.status)">{{ activeRecon.status }}</span>
        </section>

        <section class="drawer-amounts">
          <div>
            <span>账期总额</span>
            <strong>{{ money(activeRecon.payable_amount) }}</strong>
            <em v-if="Number(activeRecon.adjust_amount)">含退货红冲 {{ money(activeRecon.adjust_amount) }}</em>
          </div>
          <div><span>已结清</span><strong>{{ money(activeRecon.settled_amount) }}</strong></div>
          <div class="primary"><span>{{ activeRecon.direction === '应收' ? '待收余额' : '待付余额' }}</span><strong>{{ money(activeRecon.unsettled_amount) }}</strong></div>
          <div><span>订单数量</span><strong>{{ activeRecon.item_count }}<em>笔</em></strong></div>
        </section>

        <section class="drawer-timeline">
          <div class="drawer-section-title"><p>CLEARING TIMELINE</p><h3>账期节点</h3></div>
          <div class="timeline-grid">
            <div><i></i><span>关账日期</span><strong>{{ activeRecon.close_at || '—' }}</strong></div>
            <div><i></i><span>确认期限</span><strong>{{ activeRecon.confirm_due_date || '—' }}</strong></div>
            <div :class="{ risk: activeRecon.overdue }"><i></i><span>付款期限</span><strong>{{ activeRecon.payment_due_date || '—' }}</strong></div>
          </div>
        </section>

        <section class="drawer-orders">
          <div class="drawer-section-title">
            <div><p>ORDER EVIDENCE</p><h3>订单明细</h3></div>
            <span>{{ activeStatements.length }} 条</span>
          </div>
          <div v-if="!detailLoading && !activeStatements.length" class="drawer-empty">该对账单暂无可展示明细</div>
          <div v-else class="detail-ledger">
            <div class="detail-ledger-head"><span>订单 / 说明</span><span>状态</span><span>金额</span></div>
            <div v-for="item in activeStatements" :key="item.id" class="detail-ledger-group">
              <div
                class="detail-ledger-row"
                :class="{ clickable: orderLines(item).length, open: expandedOrders[item.id], reversal: item.is_reversal }"
                @click="toggleOrder(item)"
              >
                <strong>
                  <span v-if="orderLines(item).length" class="caret">▸</span>
                  <span v-if="item.is_reversal" class="reversal-tag">退货红冲</span>
                  {{ orderText(item) }}
                </strong>
                <span>{{ item.status }}</span>
                <b>{{ money(item.amount) }}</b>
              </div>
              <div v-if="expandedOrders[item.id]" class="order-lines">
                <div class="order-line head"><span>商品</span><span>订货</span><span>实收</span><span>单价</span><span>计费金额</span></div>
                <div v-for="(l, i) in orderLines(item)" :key="i" class="order-line">
                  <span class="ol-name">
                    {{ l.name }}<em v-if="l.spec">（{{ l.spec }}）</em>
                    <i v-if="l.ratio < 0.9995" class="ol-ratio">计费 {{ Math.round(l.ratio * 100) }}%</i>
                  </span>
                  <span>{{ l.orderedQty }} {{ l.unit }}</span>
                  <span :class="{ 'ol-short': l.receivedQty < l.orderedQty }">{{ l.receivedQty }} {{ l.unit }}</span>
                  <span>{{ money(l.price) }}</span>
                  <span class="ol-amount">
                    <s v-if="l.deduction >= 0.01" class="ol-orig">{{ money(l.original) }}</s>
                    <b>{{ money(l.billed) }}</b>
                    <em v-if="l.deduction >= 0.01" class="ol-deduct">少收 -{{ money(l.deduction) }}</em>
                  </span>
                </div>
                <div v-if="orderSummary(item)" class="order-summary">
                  原订单 {{ money(orderSummary(item).original) }} · 实计 {{ money(orderSummary(item).billed) }} ·
                  <span class="os-deduct">少收扣减 -{{ money(orderSummary(item).deduction) }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <footer class="drawer-actions">
          <span>{{ activeRecon.direction === '应收' ? '收款方仅跟踪到账，结清由付款方发起。' : '确认或结清后将同步更新对手方账单。' }}</span>
          <div>
            <button type="button" class="secondary" @click="drawerVisible = false">返回台账</button>
            <button type="button" class="secondary" @click="doExport(activeRecon)">导出对账单</button>
            <button v-if="canConfirm(activeRecon)" type="button" class="primary" @click="doConfirm(activeRecon)">核对无误</button>
            <button v-if="canSettle(activeRecon)" type="button" class="settle" @click="doSettle(activeRecon)">确认结清</button>
          </div>
        </footer>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.settlement-desk {
  --desk-accent: var(--role-accent, #0ea5e9);
  --desk-ink: #172337;
  --desk-sub: #708095;
  --desk-muted: #9aa7b6;
  --desk-line: #e2e9f1;
  --desk-soft: #f5f8fb;
  --desk-risk: #e45d66;
  --desk-warn: #d99a36;
  --desk-success: #2b9a70;
  min-width: 0;
  padding: 2px 0 44px;
  color: var(--desk-ink);
  font-family: "Be Vietnam Pro", "PingFang SC", "Microsoft YaHei", sans-serif;
}
.desk-hero { display: flex; justify-content: space-between; gap: 30px; align-items: flex-end; padding: 8px 4px 22px; border-bottom: 1px solid rgba(96,119,145,.16); }
.hero-copy > p, .section-heading p, .ledger-head p, .drawer-head p, .drawer-section-title p { margin: 0 0 8px; color: color-mix(in srgb, var(--desk-accent) 74%, #43566d 26%); font: 800 10px/1 "JetBrains Mono", monospace; letter-spacing: .18em; }
.hero-title { display: flex; align-items: center; gap: 15px; }
.hero-mark { width: 46px; height: 46px; display: grid; place-items: center; border: 1px solid color-mix(in srgb, var(--desk-accent) 28%, #dce6ef 72%); border-radius: 14px; color: var(--desk-accent); background: color-mix(in srgb, var(--desk-accent) 7%, #fff 93%); font-size: 21px; }
.hero-title h1 { margin: 0; color: var(--desk-ink); font-size: clamp(26px, 2vw, 34px); font-weight: 800; letter-spacing: -.035em; }
.hero-title div > span { display: block; margin-top: 6px; color: var(--desk-sub); font-size: 13px; }
.hero-actions { display: flex; align-items: center; gap: 12px; }
.direction-switch { display: grid; grid-template-columns: repeat(2, 1fr); gap: 3px; padding: 4px; border: 1px solid var(--desk-line); border-radius: 12px; background: #eef3f8; }
.direction-switch button { min-width: 132px; padding: 8px 16px; border: 0; border-radius: 8px; color: #728196; background: transparent; cursor: pointer; font-size: 13px; font-weight: 700; }
.direction-switch button span { display: block; margin-bottom: 3px; color: #a2adba; font: 700 8px/1 "JetBrains Mono", monospace; letter-spacing: .12em; }
.direction-switch button.active { color: var(--desk-accent); background: #fff; box-shadow: 0 4px 16px rgba(35,55,80,.08); }
.direction-switch button.active span { color: color-mix(in srgb, var(--desk-accent) 58%, #9aa8b7 42%); }
.refresh-button { height: 44px; display: inline-flex; align-items: center; gap: 7px; padding: 0 16px; border: 1px solid var(--desk-line); border-radius: 11px; color: #52647a; background: rgba(255,255,255,.82); cursor: pointer; font-size: 12px; font-weight: 700; }
.balance-band { display: grid; grid-template-columns: 1.35fr repeat(3, 1fr); margin: 22px 0 18px; border: 1px solid var(--desk-line); border-radius: 16px; background: rgba(255,255,255,.88); box-shadow: 0 14px 38px rgba(48,72,101,.07); overflow: hidden; }
.balance-band > div { min-width: 0; padding: 22px 24px; border-right: 1px solid var(--desk-line); }
.balance-band > div:last-child { border-right: 0; }
.balance-band span { display: block; color: var(--desk-sub); font-size: 12px; }
.balance-band strong { display: block; margin: 9px 0 8px; color: var(--desk-ink); font: 800 clamp(22px, 2vw, 31px)/1 "JetBrains Mono", monospace; letter-spacing: -.04em; }
.balance-band em { margin-left: 5px; color: var(--desk-sub); font: 700 11px/1 inherit; font-style: normal; }
.balance-band small { display: block; color: var(--desk-muted); font-size: 10px; line-height: 1.4; }
.balance-primary { position: relative; background: linear-gradient(110deg, color-mix(in srgb, var(--desk-accent) 9%, #fff 91%), #fff 68%); }
.balance-primary::after { content: ""; position: absolute; left: 0; top: 20px; bottom: 20px; width: 3px; border-radius: 3px; background: var(--desk-accent); }
.balance-primary strong { color: color-mix(in srgb, var(--desk-accent) 82%, #17304d 18%); }
.balance-metric.risk.active strong { color: var(--desk-risk); }
.clearing-orbit, .ledger { border: 1px solid var(--desk-line); border-radius: 16px; background: rgba(255,255,255,.82); box-shadow: 0 12px 35px rgba(48,72,101,.055); }
.clearing-orbit { padding: 20px 24px 23px; }
.section-heading { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 18px; }
.section-heading h2, .ledger-head h2 { margin: 0; color: var(--desk-ink); font-size: 20px; }
.section-heading > span { color: var(--desk-sub); font-size: 11px; }
.orbit-track { position: relative; display: grid; grid-template-columns: repeat(5, 1fr); gap: 0; }
.orbit-track::before { content: ""; position: absolute; left: 7%; right: 7%; top: 22px; height: 1px; background: linear-gradient(90deg, color-mix(in srgb, var(--desk-accent) 35%, #dae4ed 65%), #dce4eb); }
.orbit-node { position: relative; z-index: 1; display: grid; grid-template-columns: 44px 1fr auto; gap: 10px; align-items: center; min-width: 0; padding: 0 14px 0 0; text-align: left; border: 0; color: inherit; background: transparent; cursor: pointer; }
.node-index { width: 42px; height: 42px; display: grid; place-items: center; border: 1px solid #cfd9e4; border-radius: 50%; color: #8796a7; background: #fff; font: 800 10px/1 "JetBrains Mono", monospace; box-shadow: 0 0 0 7px rgba(245,248,251,.94); }
.orbit-node strong, .orbit-node small { display: block; white-space: nowrap; }
.orbit-node strong { color: #3d4e64; font-size: 12px; }
.orbit-node small { margin-top: 4px; color: var(--desk-muted); font-size: 9px; }
.orbit-node b { color: #8492a3; font: 800 17px/1 "JetBrains Mono", monospace; }
.orbit-node.is-pending .node-index { color: var(--desk-warn); border-color: color-mix(in srgb, var(--desk-warn) 48%, #dbe3eb 52%); }
.orbit-node.is-confirmed .node-index, .orbit-node.is-partial .node-index { color: var(--desk-accent); border-color: color-mix(in srgb, var(--desk-accent) 48%, #dbe3eb 52%); }
.orbit-node.is-settled .node-index { color: var(--desk-success); border-color: color-mix(in srgb, var(--desk-success) 42%, #dbe3eb 58%); }
.orbit-node.selected .node-index { color: #fff; border-color: var(--desk-accent); background: var(--desk-accent); box-shadow: 0 0 0 7px color-mix(in srgb, var(--desk-accent) 9%, #fff 91%); }
.orbit-node.selected strong, .orbit-node.selected b { color: var(--desk-accent); }
.ledger { margin-top: 18px; overflow: hidden; }
.ledger-head { display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; padding: 22px 24px 18px; border-bottom: 1px solid var(--desk-line); }
.ledger-head > div:first-child > span { display: block; margin-top: 6px; color: var(--desk-sub); font-size: 11px; }
.ledger-tools { display: flex; gap: 8px; }
.search-field { min-width: 230px; height: 38px; display: flex; align-items: center; gap: 8px; padding: 0 12px; border: 1px solid var(--desk-line); border-radius: 9px; color: #91a0b0; background: var(--desk-soft); }
.search-field:focus-within { border-color: color-mix(in srgb, var(--desk-accent) 55%, #d8e1ea 45%); background: #fff; }
.search-field input { min-width: 0; flex: 1; border: 0; outline: 0; color: var(--desk-ink); background: transparent; font-size: 12px; }
.status-filter { height: 38px; padding: 0 30px 0 12px; border: 1px solid var(--desk-line); border-radius: 9px; outline: 0; color: #52647a; background: var(--desk-soft); font-size: 12px; }
.ledger-table { min-width: 1080px; }
.ledger-row { display: grid; grid-template-columns: minmax(220px,1.45fr) minmax(145px,.85fr) minmax(175px,1fr) minmax(220px,1.25fr) 110px 112px; gap: 16px; align-items: center; padding: 0 24px; }
.ledger-columns { min-height: 42px; color: #94a2b2; background: #f8fafc; font-size: 10px; }
.ledger-entry { position: relative; min-height: 86px; border-top: 1px solid #edf1f5; cursor: pointer; transition: background 150ms ease, box-shadow 150ms ease; }
.ledger-entry:hover, .ledger-entry:focus-visible { outline: 0; background: color-mix(in srgb, var(--desk-accent) 3%, #fff 97%); box-shadow: inset 3px 0 var(--desk-accent); }
.ledger-entry.overdue { box-shadow: inset 3px 0 var(--desk-risk); }
.party-cell { min-width: 0; display: flex; align-items: center; gap: 11px; }
.party-avatar { flex: 0 0 auto; width: 36px; height: 36px; display: grid; place-items: center; border-radius: 10px; color: var(--desk-accent); background: color-mix(in srgb, var(--desk-accent) 9%, #f5f8fb 91%); font-weight: 800; }
.party-cell div, .amount-cell, .progress-cell, .date-cell, .state-cell { min-width: 0; }
.party-cell strong, .party-cell small, .amount-cell strong, .amount-cell small, .date-cell span, .date-cell small { display: block; }
.party-cell strong { overflow: hidden; color: #26364a; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.party-cell small, .amount-cell small, .progress-cell span, .date-cell small, .state-cell small { margin-top: 5px; color: var(--desk-muted); font-size: 9px; }
.amount-cell strong { color: #25364a; font: 800 17px/1 "JetBrains Mono", monospace; }
.progress-cell > div { height: 4px; border-radius: 4px; background: #edf2f6; overflow: hidden; }
.progress-cell i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--desk-accent), color-mix(in srgb, var(--desk-accent) 48%, #5bd7c5 52%)); }
.date-cell span { display: flex; align-items: center; gap: 5px; color: #4f6278; font-size: 10px; }
.state-cell small { display: flex; align-items: center; gap: 4px; color: var(--desk-risk); }
.status-pill { display: inline-flex; padding: 5px 9px; border-radius: 999px; font-size: 10px; font-weight: 800; white-space: nowrap; }
.status-pill.is-running { color: #64758a; background: #eef2f6; }
.status-pill.is-pending { color: #ae711a; background: #fff4dd; }
.status-pill.is-confirmed { color: color-mix(in srgb, var(--desk-accent) 82%, #24415e 18%); background: color-mix(in srgb, var(--desk-accent) 9%, #fff 91%); }
.status-pill.is-partial { color: #177d88; background: #e8f7f8; }
.status-pill.is-settled { color: #288460; background: #eaf6f0; }
.row-action { min-width: 90px; height: 34px; display: inline-flex; justify-content: center; align-items: center; gap: 4px; padding: 0 12px; border-radius: 8px; cursor: pointer; font-size: 11px; font-weight: 800; }
.row-action.detail { border: 1px solid var(--desk-line); color: #5e7085; background: #fff; }
.row-action.confirm { border: 1px solid var(--desk-accent); color: #fff; background: var(--desk-accent); }
.row-action.settle { border: 1px solid var(--desk-success); color: #fff; background: var(--desk-success); }
.ledger-empty { min-height: 320px; display: grid; place-content: center; justify-items: center; text-align: center; }
.ledger-empty > span { width: 52px; height: 52px; display: grid; place-items: center; border-radius: 15px; color: var(--desk-accent); background: color-mix(in srgb, var(--desk-accent) 8%, #f4f7fa 92%); font-size: 23px; }
.ledger-empty strong { margin-top: 15px; font-size: 15px; }.ledger-empty p { margin: 6px 0 0; color: var(--desk-muted); font-size: 11px; }.ledger-empty button { margin-top: 14px; padding: 8px 13px; border: 1px solid var(--desk-line); border-radius: 8px; color: var(--desk-accent); background: #fff; cursor: pointer; }
:global(.billing-detail-drawer.el-drawer) { color: var(--desk-ink); background: #f8fafc; box-shadow: -22px 0 65px rgba(32,51,74,.18); }
:global(.billing-detail-drawer .el-drawer__body) { padding: 0; overflow: hidden; }
.drawer-shell { --desk-ink:#172337; --desk-sub:#708095; --desk-muted:#9aa7b6; --desk-line:#e2e9f1; --desk-risk:#e45d66; --desk-success:#2b9a70; height: 100%; display: grid; grid-template-rows: auto auto auto auto 1fr auto; overflow: hidden; color: var(--desk-ink); background: #f8fafc; }
.drawer-head { display: flex; justify-content: space-between; gap: 20px; padding: 28px 30px 22px; border-bottom: 1px solid var(--desk-line); background: #fff; }
.drawer-head h2 { margin: 0; color: var(--desk-ink); font-size: 24px; }.drawer-head div > span { display: block; margin-top: 7px; color: var(--desk-sub); font-size: 11px; }
.drawer-head > button { width: 34px; height: 34px; border: 1px solid var(--desk-line); border-radius: 50%; color: #77879a; background: #f7f9fb; cursor: pointer; font-size: 22px; }
.drawer-conclusion { display: grid; grid-template-columns: 42px 1fr auto; gap: 13px; align-items: center; margin: 18px 24px 0; padding: 15px; border: 1px solid color-mix(in srgb, var(--desk-accent) 16%, #e1e8ef 84%); border-radius: 12px; background: color-mix(in srgb, var(--desk-accent) 5%, #fff 95%); }
.drawer-conclusion.risk { border-color: #f2c7cb; background: #fff7f7; }.conclusion-icon { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 11px; color: var(--desk-success); background: #eaf6f0; }.drawer-conclusion.risk .conclusion-icon { color: var(--desk-risk); background: #fdebed; }
.drawer-conclusion strong, .drawer-conclusion small { display: block; }.drawer-conclusion strong { font-size: 13px; }.drawer-conclusion small { margin-top: 4px; color: var(--desk-sub); font-size: 10px; line-height: 1.45; }
.drawer-amounts { display: grid; grid-template-columns: repeat(4,1fr); margin: 16px 24px 0; border: 1px solid var(--desk-line); border-radius: 12px; background: #fff; overflow: hidden; }
.drawer-amounts div { min-width: 0; padding: 16px; border-right: 1px solid var(--desk-line); }.drawer-amounts div:last-child { border-right: 0; }.drawer-amounts span { display: block; color: var(--desk-sub); font-size: 9px; }.drawer-amounts strong { display: block; margin-top: 8px; color: #26364a; font: 800 15px/1 "JetBrains Mono", monospace; }.drawer-amounts .primary strong { color: var(--desk-accent); }.drawer-amounts em { margin-left: 3px; color: var(--desk-sub); font-size: 9px; font-style: normal; }
.drawer-timeline { margin: 19px 24px 0; }.drawer-section-title { display: flex; justify-content: space-between; align-items: flex-end; }.drawer-section-title h3 { margin: 0; font-size: 16px; }.drawer-section-title > span { color: var(--desk-sub); font-size: 10px; }
.timeline-grid { position: relative; display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; margin-top: 13px; }.timeline-grid::before { content:""; position:absolute; left: 16%; right:16%; top: 8px; height:1px; background:#dce4ec; }.timeline-grid div { position:relative; padding-top: 22px; }.timeline-grid i { position:absolute; z-index:1; top:3px; left:0; width:10px; height:10px; border:3px solid #fff; border-radius:50%; background:var(--desk-accent); box-shadow:0 0 0 1px color-mix(in srgb,var(--desk-accent) 35%,#dce4ec 65%); }.timeline-grid div.risk i { background: var(--desk-risk); }.timeline-grid span, .timeline-grid strong { display:block; }.timeline-grid span { color:var(--desk-muted); font-size:9px; }.timeline-grid strong { margin-top:5px; color:#46596f; font:700 11px/1 "JetBrains Mono",monospace; }
.drawer-orders { min-height: 0; display: grid; grid-template-rows: auto 1fr; margin: 20px 24px 0; overflow: hidden; }.detail-ledger { margin-top: 12px; overflow-y: auto; border: 1px solid var(--desk-line); border-radius: 11px; background: #fff; }.detail-ledger-head, .detail-ledger-row { display:grid; grid-template-columns: minmax(0,1fr) 90px 120px; gap:12px; align-items:center; padding: 11px 14px; }.detail-ledger-head { position:sticky; top:0; z-index:1; color:#94a2b2; background:#f7f9fb; font-size:9px; }.detail-ledger-row { border-top:1px solid #edf1f5; }.detail-ledger-row strong { min-width:0; overflow:hidden; color:#405267; font-size:11px; text-overflow:ellipsis; white-space:nowrap; }.detail-ledger-row span { color:var(--desk-sub); font-size:10px; }.detail-ledger-row b { text-align:right; color:#26364a; font:800 11px/1 "JetBrains Mono",monospace; }.drawer-empty { margin-top:12px; display:grid; place-items:center; min-height:120px; border:1px dashed var(--desk-line); border-radius:11px; color:var(--desk-muted); font-size:11px; }
.detail-ledger-group { border-top:1px solid #edf1f5; }
.detail-ledger-group:first-child { border-top:none; }
.detail-ledger-row.reversal { background: #fff6f6; }
.detail-ledger-row.reversal strong { color: var(--desk-risk); }
.detail-ledger-row.reversal b { color: var(--desk-risk); }
.reversal-tag { display:inline-block; margin-right:6px; padding:1px 6px; border-radius:6px; color:#fff; background:var(--desk-risk); font:800 9px/1.6 "JetBrains Mono",monospace; vertical-align:middle; }
.detail-ledger-group .detail-ledger-row { border-top:none; }
.detail-ledger-row.clickable { cursor:pointer; transition: background .15s; }
.detail-ledger-row.clickable:hover { background:#f7faff; }
.detail-ledger-row .caret { display:inline-block; margin-right:6px; color:var(--desk-accent); font-size:9px; transition: transform .18s; }
.detail-ledger-row.open .caret { transform: rotate(90deg); }
.order-lines { background:#f7f9fc; border-top:1px solid #edf1f5; padding:4px 14px 8px 28px; }
.order-line { display:grid; grid-template-columns: minmax(0,1fr) 60px 64px 64px 96px; gap:10px; align-items:center; padding:7px 0; border-bottom:1px dashed #e6ebf1; font-size:10px; color:#56697d; }
.order-line:last-child { border-bottom:none; }
.order-line.head { color:#9aa7b6; font-size:9px; letter-spacing:.04em; border-bottom:1px solid #e0e6ed; }
.order-line span:nth-child(n+2) { text-align:right; font-family:"JetBrains Mono",monospace; }
.order-line.head span:nth-child(n+2) { font-family:inherit; }
.order-line .ol-name { text-align:left; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#3c4d61; font-weight:600; }
.order-line .ol-name em { color:#9aa7b6; font-style:normal; font-weight:400; }
.order-line .ol-ratio { margin-left:6px; padding:0 5px; border-radius:5px; color:#b06a1c; background:#fdf1e0; font:700 8px/1.5 "JetBrains Mono",monospace; font-style:normal; vertical-align:middle; }
.order-line .ol-short { color:var(--desk-risk); font-weight:700; }
.order-line .ol-amount { display:flex; flex-direction:column; align-items:flex-end; line-height:1.35; }
.order-line .ol-amount .ol-orig { color:#a6b1bd; text-decoration:line-through; font-size:9px; }
.order-line .ol-amount b { color:#26364a; }
.order-line .ol-amount .ol-deduct { color:var(--desk-risk); font-size:8px; font-style:normal; }
.order-summary { margin-top:4px; padding:6px 0 2px; text-align:right; color:#7c8a9a; font:600 9px/1.4 "JetBrains Mono",monospace; }
.order-summary .os-deduct { color:var(--desk-risk); }
.drawer-actions { display:flex; justify-content:space-between; align-items:center; gap:20px; padding:16px 24px; border-top:1px solid var(--desk-line); background:#fff; }.drawer-actions > span { color:var(--desk-muted); font-size:9px; }.drawer-actions div { display:flex; gap:8px; }.drawer-actions button { height:36px; padding:0 15px; border-radius:8px; cursor:pointer; font-size:11px; font-weight:800; }.drawer-actions .secondary { border:1px solid var(--desk-line); color:#5f7084; background:#fff; }.drawer-actions .primary { border:1px solid var(--desk-accent); color:#fff; background:var(--desk-accent); }.drawer-actions .settle { border:1px solid var(--desk-success); color:#fff; background:var(--desk-success); }
@media (max-width: 1366px) {
  .balance-band > div { padding: 19px 18px; }
  .orbit-node { grid-template-columns: 42px 1fr; }.orbit-node b { grid-column: 2; font-size: 13px; }
  .ledger { overflow-x: auto; }.ledger-head { min-width: 1030px; }
}
@media (max-width: 900px) {
  .desk-hero, .ledger-head { align-items: stretch; flex-direction: column; }
  .hero-actions { justify-content: space-between; }.balance-band { grid-template-columns: repeat(2,1fr); }.balance-band > div:nth-child(2) { border-right:0; }.balance-band > div:nth-child(-n+2) { border-bottom:1px solid var(--desk-line); }
  .clearing-orbit { overflow-x:auto; }.section-heading, .orbit-track { min-width:760px; }
}
</style>

<!-- 非 scoped：弹窗 teleport 到 body，且 UnoCSS reset 会清空按钮底色，这里强制保证按钮文案可见 -->
<style>
.bc-confirm-dialog .el-message-box__btns .el-button {
  font-weight: 600;
}
.bc-confirm-dialog .el-message-box__btns .el-button--primary {
  background: var(--el-color-primary) !important;
  border-color: var(--el-color-primary) !important;
  color: #fff !important;
}
.bc-confirm-dialog .el-message-box__btns .el-button--primary > span {
  color: #fff !important;
}
.bc-confirm-dialog .el-message-box__btns .el-button:not(.el-button--primary) {
  background: #fff !important;
  border-color: #cbd5e1 !important;
  color: #334155 !important;
}
.bc-confirm-dialog .el-message-box__btns .el-button:not(.el-button--primary) > span {
  color: #334155 !important;
}
</style>
