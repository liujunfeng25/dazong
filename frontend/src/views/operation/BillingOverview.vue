<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { QuestionFilled, Refresh } from '@element-plus/icons-vue'
import {
  getBillingOverviewApi,
  getOperationBillingStatementDetailApi,
  getOperationBillingStatementsApi,
  listBillingStatementsGroupedApi,
} from '../../api/bills'
import { formatChinaDateTime } from '../../utils/datetime'

const router = useRouter()
const loading = ref(false)
const totals = ref({ client_delivery_unsettled: 0, delivery_supplier_unsettled: 0, statement_count: 0, settled_count: 0 })
const upcoming = ref([])
const overdueConfirm = ref([])
const overduePayment = ref([])
const activeTab = ref('confirm')

const viewMode = ref('overview') // 'overview' | 'grouped'

const cycleTypeLabel = (value) => ({ daily: '按天', weekly: '按周', monthly: '按月' }[value] || value || '')

const money = (v) => `¥${Number(v || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const directionTag = (d) => (d === '应付' ? 'warning' : 'success')
const statusTag = (s) => {
  switch (s) {
    case '已结清': return 'success'
    case '部分结清': return 'warning'
    case '已确认': return ''
    default: return 'info'
  }
}

const STATUS_OPTIONS = ['待确认', '已确认', '部分结清', '已结清']
const RELATION_OPTIONS = [
  { value: 'client_delivery', label: '客户→配送商' },
  { value: 'delivery_supplier', label: '配送商→供货商/厂家' },
]
const DIRECTION_OPTIONS = [
  { value: '应收', label: '应收' },
  { value: '应付', label: '应付' },
]

/** 筛选状态 */
const filterState = reactive({
  relation_type: '',
  direction: '',
  status: [],
  cycle_id: null,
  counterparty_keyword: '',
  keyword: '',
  period_range: null, // [Date, Date] | null
})
const listPage = ref(1)
const listPageSize = ref(20)
const listLoading = ref(false)
const listItems = ref([])
const listTotal = ref(0)
const listSummary = ref({ amount_sum: 0, unsettled_sum: 0, count_by_status: {} })
const detailSectionRef = ref(null)

const detailVisible = ref(false)
const detailLoading = ref(false)
const detailPayload = ref(null)

const isoDate = (d) => {
  if (!d) return ''
  const dd = new Date(d)
  const y = dd.getFullYear()
  const m = String(dd.getMonth() + 1).padStart(2, '0')
  const day = String(dd.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const buildListParams = () => {
  const p = {
    page: listPage.value,
    page_size: listPageSize.value,
  }
  if (filterState.relation_type) p.relation_type = filterState.relation_type
  if (filterState.direction) p.direction = filterState.direction
  if (filterState.status?.length) p.status = filterState.status.join(',')
  if (filterState.cycle_id) p.cycle_id = filterState.cycle_id
  if (filterState.counterparty_keyword?.trim()) p.counterparty_keyword = filterState.counterparty_keyword.trim()
  if (filterState.keyword?.trim()) p.keyword = filterState.keyword.trim()
  if (filterState.period_range?.length === 2) {
    p.period_from = isoDate(filterState.period_range[0])
    p.period_to = isoDate(filterState.period_range[1])
  }
  return p
}

const load = async () => {
  loading.value = true
  try {
    const data = await getBillingOverviewApi()
    totals.value = data.totals || totals.value
    upcoming.value = data.upcoming_close || []
    overdueConfirm.value = data.overdue_confirm || []
    overduePayment.value = data.overdue_payment || []
  } catch (e) {
    ElMessage.error('加载账单总览失败')
  } finally {
    loading.value = false
  }
}

const loadList = async () => {
  listLoading.value = true
  try {
    const res = await getOperationBillingStatementsApi(buildListParams())
    listItems.value = res?.items || []
    listTotal.value = Number(res?.total || 0)
    listSummary.value = res?.summary || { amount_sum: 0, unsettled_sum: 0, count_by_status: {} }
  } catch (e) {
    // 全局拦截器已 toast
    listItems.value = []
    listTotal.value = 0
  } finally {
    listLoading.value = false
  }
}

const scrollToDetail = async () => {
  await nextTick()
  const target = detailSectionRef.value?.$el || detailSectionRef.value
  target?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
}

const applyFilter = async () => {
  listPage.value = 1
  await loadList()
  await scrollToDetail()
}

const resetFilter = async () => {
  filterState.relation_type = ''
  filterState.direction = ''
  filterState.status = []
  filterState.cycle_id = null
  filterState.counterparty_keyword = ''
  filterState.keyword = ''
  filterState.period_range = null
  listPage.value = 1
  await loadList()
}

const onPageChange = async (p) => {
  listPage.value = p
  await loadList()
}

/** KPI 卡 → 联动筛选 */
const applyKpiFilter = async (kind) => {
  filterState.cycle_id = null
  filterState.counterparty_keyword = ''
  filterState.keyword = ''
  filterState.period_range = null
  if (kind === 'client_delivery_unsettled') {
    filterState.relation_type = 'client_delivery'
    filterState.direction = '应付'
    filterState.status = ['待确认', '已确认', '部分结清']
  } else if (kind === 'delivery_supplier_unsettled') {
    filterState.relation_type = 'delivery_supplier'
    filterState.direction = '应付'
    filterState.status = ['待确认', '已确认', '部分结清']
  } else if (kind === 'settled') {
    filterState.relation_type = ''
    filterState.direction = ''
    filterState.status = ['已结清']
  } else {
    // total
    filterState.relation_type = ''
    filterState.direction = ''
    filterState.status = []
  }
  listPage.value = 1
  await loadList()
  await scrollToDetail()
}

/** 即将关账 banner 行点击 */
const applyUpcomingFilter = async (item) => {
  filterState.status = []
  filterState.direction = ''
  filterState.relation_type = item.relation_type || ''
  // 后端 upcoming 行无 cycle_id 字段，按 relation + 账期范围圈定
  filterState.cycle_id = null
  filterState.period_range = null
  filterState.counterparty_keyword = ''
  filterState.keyword = ''
  listPage.value = 1
  await loadList()
  await scrollToDetail()
}

/** 行点击 → 打开详情 drawer */
const openStatementDetail = async (id) => {
  if (!id) return
  detailVisible.value = true
  detailLoading.value = true
  detailPayload.value = null
  try {
    detailPayload.value = await getOperationBillingStatementDetailApi(id)
  } catch (e) {
    // 全局拦截器已 toast
  } finally {
    detailLoading.value = false
  }
}

const switchToMirror = async () => {
  const mid = detailPayload.value?.mirror?.id
  if (mid) await openStatementDetail(mid)
}

const dueDateColor = (dueStr) => {
  if (!dueStr) return ''
  try {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const d = new Date(dueStr)
    d.setHours(0, 0, 0, 0)
    const diff = (d.getTime() - today.getTime()) / 86400000
    if (diff < 0) return 'color:#dc2626;font-weight:700' // 已过
    if (diff === 0) return 'color:#ea580c;font-weight:700' // 今天
    return 'color:#0f172a'
  } catch {
    return ''
  }
}

const goOrder = (orderId) => {
  if (!orderId) return
  router.push(`/operation/orders/${orderId}`)
}

const overdueConfirmSorted = computed(() =>
  [...overdueConfirm.value].sort((a, b) => Number(b.overdue_days || 0) - Number(a.overdue_days || 0)),
)
const overduePaymentSorted = computed(() =>
  [...overduePayment.value].sort((a, b) => Number(b.overdue_days || 0) - Number(a.overdue_days || 0)),
)

/* ============ 按账期汇总（grouped）视图 ============ */
const groupedLoading = ref(false)
const groupedItems = ref([])
const expandedGroups = ref([])
const groupedFilter = reactive({
  relation_type: '',
  direction: '',
  period_label: '',
  counterparty_keyword: '',
})

const buildGroupedParams = () => {
  const p = {}
  if (groupedFilter.relation_type) p.relation_type = groupedFilter.relation_type
  if (groupedFilter.direction) p.direction = groupedFilter.direction
  if (groupedFilter.period_label?.trim()) p.period_label = groupedFilter.period_label.trim()
  if (groupedFilter.counterparty_keyword?.trim()) p.counterparty_keyword = groupedFilter.counterparty_keyword.trim()
  return p
}

const loadGrouped = async () => {
  groupedLoading.value = true
  try {
    const res = await listBillingStatementsGroupedApi(buildGroupedParams())
    groupedItems.value = Array.isArray(res) ? res : []
    expandedGroups.value = []
  } catch (e) {
    groupedItems.value = []
  } finally {
    groupedLoading.value = false
  }
}

const applyGroupedFilter = async () => {
  await loadGrouped()
}

const resetGroupedFilter = async () => {
  groupedFilter.relation_type = ''
  groupedFilter.direction = ''
  groupedFilter.period_label = ''
  groupedFilter.counterparty_keyword = ''
  await loadGrouped()
}

const groupKey = (g) => `${g.period_label}|${g.direction}`

const escapeCsv = (value) => {
  const s = value == null ? '' : String(value)
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

const STATEMENT_CSV_HEADER = ['账单号', '方向', '状态', '账期', '账期模式', '关账日', '确认到期日', '付款到期日', '金额', '已结金额', '对方', '涉及订单号', '创建时间']

const statementCsvRow = (r) =>
  [
    escapeCsv(r.statement_no),
    escapeCsv(r.direction),
    escapeCsv(r.status),
    escapeCsv(r.period_label || ''),
    escapeCsv(r.cycle_type_label || cycleTypeLabel(r.cycle_type)),
    escapeCsv(r.close_at || ''),
    escapeCsv(r.confirm_due_date || ''),
    escapeCsv(r.payment_due_date || ''),
    escapeCsv(r.amount),
    escapeCsv(r.settled_amount),
    escapeCsv(r.counterparty_name || ''),
    escapeCsv((r.order_numbers || []).join(' | ')),
    escapeCsv(r.created_at ? formatChinaDateTime(r.created_at) : ''),
  ].join(',')

const downloadCsv = (lines, filename) => {
  const blob = new Blob([`﻿${lines.join('\n')}`], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const exportGroupCsv = (g) => {
  if (!g?.statements?.length) {
    ElMessage.warning('该账期暂无账单')
    return
  }
  const lines = []
  lines.push(`账期,${escapeCsv(g.period_label)},${escapeCsv(g.period_start)} 至 ${escapeCsv(g.period_end)}`)
  lines.push(`方向,${escapeCsv(g.direction)},关账日,${escapeCsv(g.close_at)}`)
  lines.push(`合计金额,${escapeCsv(g.total_amount)},已结清,${escapeCsv(g.settled_amount)},未结清,${escapeCsv(g.unsettled_amount)}`)
  lines.push(`账单数,${escapeCsv(g.statement_count)},超期数,${escapeCsv(g.overdue_count)}`)
  lines.push('')
  lines.push(STATEMENT_CSV_HEADER.join(','))
  for (const r of g.statements) lines.push(statementCsvRow(r))
  downloadCsv(lines, `对账单_${g.period_label}_${g.direction}.csv`)
  ElMessage.success(`已导出 ${g.period_label} ${g.direction} 对账单`)
}

const onSwitchView = async (mode) => {
  viewMode.value = mode
  if (mode === 'grouped' && !groupedItems.value.length) {
    await loadGrouped()
  }
}

onMounted(async () => {
  await load()
  await loadList()
})
</script>

<template>
  <div class="billing-overview">
    <el-card shadow="never" class="hero-card">
      <div class="hero-row">
        <div>
          <div class="title">账单总览</div>
          <div class="subtitle">
            汇总系统内所有应收应付。账单逐笔生成，本页按账期归属计算到期日与异常清单；下方可按任意维度筛选与下钻查看详情。
          </div>
        </div>
        <div class="actions">
          <el-radio-group :model-value="viewMode" @change="onSwitchView">
            <el-radio-button label="overview">对账总览</el-radio-button>
            <el-radio-button label="grouped">按账期汇总</el-radio-button>
          </el-radio-group>
          <el-button
            :loading="loading || groupedLoading"
            @click="() => (viewMode === 'grouped' ? loadGrouped() : (load(), loadList()))"
          >
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </div>
    </el-card>

    <template v-if="viewMode === 'overview'">
    <section class="kpi-grid">
      <div class="kpi-card kpi-clickable" @click="applyKpiFilter('client_delivery_unsettled')">
        <span>客户→配送商 未结清</span>
        <strong>{{ money(totals.client_delivery_unsettled) }}</strong>
        <span class="kpi-hint">食堂尚未付给配送商。点击查看明细。</span>
      </div>
      <div class="kpi-card kpi-clickable" @click="applyKpiFilter('delivery_supplier_unsettled')">
        <span>配送商→供货商/厂家 未结清</span>
        <strong>{{ money(totals.delivery_supplier_unsettled) }}</strong>
        <span class="kpi-hint">配送商尚未付给上游。点击查看明细。</span>
      </div>
      <div class="kpi-card kpi-clickable" @click="applyKpiFilter('total')">
        <span>
          账单总数
          <el-tooltip
            content="每笔业务自动生成「应收 + 应付」双向镜像账单，所以总数 = 实际业务笔数 × 2"
            placement="top"
          >
            <el-icon class="tip-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </span>
        <strong>{{ totals.statement_count }}</strong>
        <span class="kpi-hint">含应收/应付双向镜像。点击查看全部。</span>
      </div>
      <div class="kpi-card kpi-clickable" @click="applyKpiFilter('settled')">
        <span>
          已结清
          <el-tooltip content="镜像两张账单都已全额付清的账单条数。" placement="top">
            <el-icon class="tip-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </span>
        <strong>{{ totals.settled_count }}</strong>
        <span class="kpi-hint">含应收应付两侧。点击查看明细。</span>
      </div>
    </section>

    <el-alert
      v-if="upcoming.length"
      type="warning"
      :closable="false"
      show-icon
      :title="`未来 7 天内有 ${upcoming.length} 个账期即将关账`"
    >
      <template #default>
        <div class="upcoming-tip">
          关账日 = 周期截止，进入催收阶段。点击某一条可下钻到该关系链的账单明细。
        </div>
        <ul class="upcoming-list">
          <li
            v-for="item in upcoming"
            :key="item.relation_type + item.close_at"
            class="upcoming-item"
            @click="applyUpcomingFilter(item)"
          >
            <strong>{{ item.title }}</strong>
            <span>账期 {{ item.period_label }}</span>
            <span>{{ item.close_at }} 关账</span>
            <el-tag size="small" :type="item.days_to_close <= 1 ? 'danger' : 'warning'">
              {{ item.days_to_close === 0 ? '今天关账' : `还有 ${item.days_to_close} 天` }}
            </el-tag>
          </li>
        </ul>
      </template>
    </el-alert>

    <el-card shadow="never">
      <el-tabs v-model="activeTab">
        <el-tab-pane name="confirm">
          <template #label>
            <span>
              超期未确认 ({{ overdueConfirm.length }})
              <el-tooltip
                content="客户/配送商在确认到期日前没点击「确认账单」。点击任意行查看详情。"
                placement="top"
              >
                <el-icon class="tip-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </span>
          </template>
          <el-empty v-if="!overdueConfirm.length" description="无超期未确认账单" />
          <el-table
            v-else
            :data="overdueConfirmSorted"
            border
            class="clickable-table"
            @row-click="(row) => openStatementDetail(row.id)"
          >
            <el-table-column prop="statement_no" label="账单号" min-width="200" />
            <el-table-column label="账期" width="120">
              <template #default="{ row }">{{ row.period_label }}</template>
            </el-table-column>
            <el-table-column label="方向" width="80">
              <template #default="{ row }">
                <el-tag :type="directionTag(row.direction)" size="small">{{ row.direction }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="角色" width="100" prop="role" />
            <el-table-column label="对手方" min-width="160" prop="counterparty_name" />
            <el-table-column label="金额" width="140">
              <template #default="{ row }">{{ money(row.amount) }}</template>
            </el-table-column>
            <el-table-column label="确认到期日" width="140" prop="confirm_due_date" />
            <el-table-column label="超期天数" width="100">
              <template #default="{ row }">
                <el-tag type="danger" size="small">{{ row.overdue_days }} 天</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="创建时间" width="170">
              <template #default="{ row }">{{ row.created_at ? formatChinaDateTime(row.created_at) : '' }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane name="payment">
          <template #label>
            <span>
              超期未付款 ({{ overduePayment.length }})
              <el-tooltip
                content="已确认但未在付款到期日前付清。点击任意行查看详情。"
                placement="top"
              >
                <el-icon class="tip-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </span>
          </template>
          <el-empty v-if="!overduePayment.length" description="无超期未付款账单" />
          <el-table
            v-else
            :data="overduePaymentSorted"
            border
            class="clickable-table"
            @row-click="(row) => openStatementDetail(row.id)"
          >
            <el-table-column prop="statement_no" label="账单号" min-width="200" />
            <el-table-column label="账期" width="120">
              <template #default="{ row }">{{ row.period_label }}</template>
            </el-table-column>
            <el-table-column label="方向" width="80">
              <template #default="{ row }">
                <el-tag :type="directionTag(row.direction)" size="small">{{ row.direction }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="角色" width="100" prop="role" />
            <el-table-column label="对手方" min-width="160" prop="counterparty_name" />
            <el-table-column label="金额" width="140">
              <template #default="{ row }">{{ money(row.amount) }}</template>
            </el-table-column>
            <el-table-column label="未结金额" width="140">
              <template #default="{ row }">{{ money(row.unsettled_amount) }}</template>
            </el-table-column>
            <el-table-column label="付款到期日" width="140" prop="payment_due_date" />
            <el-table-column label="超期天数" width="100">
              <template #default="{ row }">
                <el-tag type="danger" size="small">{{ row.overdue_days }} 天</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-card ref="detailSectionRef" shadow="never" class="detail-section">
      <template #header>
        <div class="detail-section-header">
          <span class="detail-section-title">账单明细</span>
          <span class="detail-section-sub">按筛选条件查询；点击 KPI 卡 / 即将关账提示 / 超期表行会自动联动筛选或弹出详情</span>
        </div>
      </template>

      <el-form inline class="filter-form" @submit.prevent="applyFilter">
        <el-form-item label="账期">
          <el-date-picker
            v-model="filterState.period_range"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            style="width: 260px"
          />
        </el-form-item>
        <el-form-item label="关系链">
          <el-select v-model="filterState.relation_type" clearable placeholder="全部" style="width: 200px">
            <el-option
              v-for="opt in RELATION_OPTIONS"
              :key="opt.value"
              :value="opt.value"
              :label="opt.label"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="方向">
          <el-select v-model="filterState.direction" clearable placeholder="全部" style="width: 120px">
            <el-option
              v-for="opt in DIRECTION_OPTIONS"
              :key="opt.value"
              :value="opt.value"
              :label="opt.label"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="filterState.status"
            multiple
            collapse-tags
            clearable
            placeholder="全部"
            style="width: 220px"
          >
            <el-option v-for="s in STATUS_OPTIONS" :key="s" :value="s" :label="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="对手方">
          <el-input v-model="filterState.counterparty_keyword" clearable placeholder="企业名关键字" style="width: 200px" />
        </el-form-item>
        <el-form-item label="账单号">
          <el-input v-model="filterState.keyword" clearable placeholder="账单号 / 订单号" style="width: 200px" />
        </el-form-item>
        <el-form-item>
          <el-button @click="resetFilter">重置</el-button>
          <el-button type="primary" :loading="listLoading" @click="applyFilter">应用</el-button>
        </el-form-item>
      </el-form>

      <div class="detail-summary">
        <span>当前筛选共 <strong>{{ listTotal }}</strong> 张</span>
        <span>·</span>
        <span>总额 <strong>{{ money(listSummary.amount_sum) }}</strong></span>
        <span>·</span>
        <span>未结清 <strong>{{ money(listSummary.unsettled_sum) }}</strong></span>
        <span>·</span>
        <span>
          <el-tag size="small" type="info">待确认 {{ listSummary.count_by_status?.['待确认'] || 0 }}</el-tag>
          <el-tag size="small">已确认 {{ listSummary.count_by_status?.['已确认'] || 0 }}</el-tag>
          <el-tag size="small" type="warning">部分结清 {{ listSummary.count_by_status?.['部分结清'] || 0 }}</el-tag>
          <el-tag size="small" type="success">已结清 {{ listSummary.count_by_status?.['已结清'] || 0 }}</el-tag>
        </span>
      </div>

      <el-table
        v-loading="listLoading"
        :data="listItems"
        border
        class="clickable-table"
        @row-click="(row) => openStatementDetail(row.id)"
      >
        <el-table-column prop="statement_no" label="账单号" min-width="200" />
        <el-table-column label="账期" width="120">
          <template #default="{ row }">{{ row.period_label }}</template>
        </el-table-column>
        <el-table-column label="方向" width="80">
          <template #default="{ row }">
            <el-tag :type="directionTag(row.direction)" size="small">{{ row.direction }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="角色" width="100" prop="role" />
        <el-table-column label="对手方" min-width="160" prop="counterparty_name" />
        <el-table-column label="金额" width="120">
          <template #default="{ row }">{{ money(row.amount) }}</template>
        </el-table-column>
        <el-table-column label="未结清" width="120">
          <template #default="{ row }">{{ money(row.unsettled_amount) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="确认到期" width="120" prop="confirm_due_date" />
        <el-table-column label="付款到期" width="120" prop="payment_due_date" />
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ row.created_at ? formatChinaDateTime(row.created_at) : '' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click.stop="openStatementDetail(row.id)">详情</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="无匹配账单" :image-size="64" />
        </template>
      </el-table>

      <div class="pagination-row">
        <el-pagination
          background
          layout="total, prev, pager, next, sizes"
          :current-page="listPage"
          :page-size="listPageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="listTotal"
          @current-change="onPageChange"
          @size-change="(s) => { listPageSize = s; listPage = 1; loadList() }"
        />
      </div>
    </el-card>
    </template>

    <template v-else-if="viewMode === 'grouped'">
    <el-card shadow="never" class="grouped-section">
      <template #header>
        <div class="grouped-header">
          <div>
            <span class="grouped-title">按账期汇总（对账单视图）</span>
            <span class="grouped-sub">按「账期 × 方向」聚合全平台账单，每组可展开看明细 + 单组导出 CSV 作为对账单使用。</span>
          </div>
        </div>
      </template>

      <el-form inline class="grouped-filter" @submit.prevent="applyGroupedFilter">
        <el-form-item label="关系链">
          <el-select v-model="groupedFilter.relation_type" clearable placeholder="全部" style="width: 200px">
            <el-option label="客户→配送商" value="client_delivery" />
            <el-option label="配送商→供货商/厂家" value="delivery_supplier" />
          </el-select>
        </el-form-item>
        <el-form-item label="方向">
          <el-select v-model="groupedFilter.direction" clearable placeholder="全部" style="width: 120px">
            <el-option label="应收" value="应收" />
            <el-option label="应付" value="应付" />
          </el-select>
        </el-form-item>
        <el-form-item label="账期">
          <el-input v-model="groupedFilter.period_label" clearable placeholder="如 2026-05 / 2026-W22 / 2026-05-26" style="width: 240px" />
        </el-form-item>
        <el-form-item label="对手方">
          <el-input v-model="groupedFilter.counterparty_keyword" clearable placeholder="企业名关键字" style="width: 200px" />
        </el-form-item>
        <el-form-item>
          <el-button @click="resetGroupedFilter">重置</el-button>
          <el-button type="primary" :loading="groupedLoading" @click="applyGroupedFilter">应用</el-button>
        </el-form-item>
      </el-form>

      <el-empty
        v-if="!groupedLoading && !groupedItems.length"
        description="无匹配账期分组"
        :image-size="80"
      />

      <el-collapse v-else v-model="expandedGroups" v-loading="groupedLoading">
        <el-collapse-item
          v-for="g in groupedItems"
          :key="groupKey(g)"
          :name="groupKey(g)"
        >
          <template #title>
            <div class="group-title">
              <strong>{{ g.period_label }}</strong>
              <el-tag :type="directionTag(g.direction)" size="small">{{ g.direction }}</el-tag>
              <el-tag size="small" type="info">{{ cycleTypeLabel(g.cycle_type) || g.cycle_type_label || '' }}</el-tag>
              <span class="group-title-sub">
                共 {{ g.statement_count }} 张 ·
                总额 <strong>{{ money(g.total_amount) }}</strong> ·
                未结清 <strong>{{ money(g.unsettled_amount) }}</strong>
                <span v-if="g.overdue_count" class="group-overdue"> · 超期 {{ g.overdue_count }} 张</span>
              </span>
            </div>
          </template>
          <div class="group-meta">
            <span>账期范围：<strong>{{ g.period_start }} ~ {{ g.period_end }}</strong></span>
            <span>关账日：<strong>{{ g.close_at }}</strong></span>
            <span v-if="g.confirm_due_date">确认到期：<strong>{{ g.confirm_due_date }}</strong></span>
            <span v-if="g.payment_due_date">付款到期：<strong>{{ g.payment_due_date }}</strong></span>
            <span class="group-meta-spacer" />
            <el-button size="small" type="primary" plain @click.stop="exportGroupCsv(g)">导出 CSV</el-button>
          </div>
          <el-table
            :data="g.statements"
            border
            size="small"
            class="clickable-table group-table"
            @row-click="(row) => openStatementDetail(row.id)"
          >
            <el-table-column prop="statement_no" label="账单号" min-width="200" />
            <el-table-column label="角色" width="100" prop="role" />
            <el-table-column label="对手方" min-width="160" prop="counterparty_name" />
            <el-table-column label="金额" width="120">
              <template #default="{ row }">{{ money(row.amount) }}</template>
            </el-table-column>
            <el-table-column label="已结" width="110">
              <template #default="{ row }">{{ money(row.settled_amount) }}</template>
            </el-table-column>
            <el-table-column label="未结" width="110">
              <template #default="{ row }">{{ money(row.unsettled_amount) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="创建时间" width="170">
              <template #default="{ row }">{{ row.created_at ? formatChinaDateTime(row.created_at) : '' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="80" fixed="right">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click.stop="openStatementDetail(row.id)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </el-card>
    </template>

    <el-drawer
      v-model="detailVisible"
      size="60%"
      destroy-on-close
      :title="`账单详情 - ${detailPayload?.statement?.statement_no || ''}`"
    >
      <div v-loading="detailLoading" class="detail-body">
        <template v-if="detailPayload?.statement">
          <section class="detail-meta">
            <div><span>账单号</span><strong>{{ detailPayload.statement.statement_no }}</strong></div>
            <div>
              <span>状态</span>
              <strong>
                <el-tag :type="statusTag(detailPayload.statement.status)" size="small">
                  {{ detailPayload.statement.status }}
                </el-tag>
              </strong>
            </div>
            <div>
              <span>方向</span>
              <strong>
                <el-tag :type="directionTag(detailPayload.statement.direction)" size="small">
                  {{ detailPayload.statement.direction }}
                </el-tag>
              </strong>
            </div>
            <div><span>角色</span><strong>{{ detailPayload.statement.role }}</strong></div>
            <div><span>对手方</span><strong>{{ detailPayload.statement.counterparty_name }}</strong></div>
            <div><span>账期</span><strong>{{ detailPayload.statement.period_label || '—' }}</strong></div>
          </section>

          <section v-if="detailPayload.cycle" class="detail-block">
            <div class="block-title">
              关键日期
              <el-tag size="small" type="info" effect="plain" class="cycle-scope-tag">
                来自全局规则 · 此关系链下所有对手方共用
              </el-tag>
            </div>
            <div class="detail-meta detail-meta-3">
              <div>
                <span>关账日</span>
                <strong :style="dueDateColor(detailPayload.cycle.close_at)">
                  {{ detailPayload.cycle.close_at || '—' }}
                </strong>
              </div>
              <div>
                <span>确认到期日</span>
                <strong :style="dueDateColor(detailPayload.cycle.confirm_due_date)">
                  {{ detailPayload.cycle.confirm_due_date || '—' }}
                </strong>
              </div>
              <div>
                <span>付款到期日</span>
                <strong :style="dueDateColor(detailPayload.cycle.payment_due_date)">
                  {{ detailPayload.cycle.payment_due_date || '—' }}
                </strong>
              </div>
            </div>
            <div class="block-sub">
              周期类型：{{ detailPayload.cycle.cycle_type || '—' }}；关账日号：{{ detailPayload.cycle.close_day ?? '—' }}；
              确认期限：关账后 {{ detailPayload.cycle.confirm_due_days ?? '—' }} 天；
              付款期限：关账后 {{ detailPayload.cycle.payment_due_days ?? '—' }} 天
            </div>
          </section>

          <section class="detail-block">
            <div class="block-title">金额</div>
            <div class="detail-meta detail-meta-4">
              <div><span>总额</span><strong>{{ money(detailPayload.statement.amount) }}</strong></div>
              <div><span>已确认</span><strong>{{ money(detailPayload.statement.confirmed_amount) }}</strong></div>
              <div><span>已结清</span><strong>{{ money(detailPayload.statement.settled_amount) }}</strong></div>
              <div><span>未结清</span><strong>{{ money(detailPayload.statement.unsettled_amount) }}</strong></div>
            </div>
          </section>

          <section v-if="detailPayload.mirror" class="detail-block">
            <div class="block-title">镜像账单（对方视角）</div>
            <div class="mirror-card" @click="switchToMirror">
              <div class="mirror-row">
                <strong>{{ detailPayload.mirror.statement_no }}</strong>
                <el-tag :type="directionTag(detailPayload.mirror.direction)" size="small">
                  {{ detailPayload.mirror.direction }}
                </el-tag>
                <el-tag :type="statusTag(detailPayload.mirror.status)" size="small">
                  {{ detailPayload.mirror.status }}
                </el-tag>
              </div>
              <div class="mirror-row mirror-sub">
                <span>角色：{{ detailPayload.mirror.role }}</span>
                <span>金额：{{ money(detailPayload.mirror.amount) }}</span>
                <span>已结清：{{ money(detailPayload.mirror.settled_amount) }}</span>
                <span class="mirror-link">点击切换到对方视角 →</span>
              </div>
            </div>
          </section>

          <section class="detail-block">
            <div class="block-title">关联订单</div>
            <el-empty v-if="!detailPayload.orders?.length" description="未找到关联订单" :image-size="60" />
            <el-table v-else :data="detailPayload.orders" border>
              <el-table-column label="订单号" min-width="180">
                <template #default="{ row }">
                  <el-button link type="primary" @click="goOrder(row.id)">{{ row.order_no }}</el-button>
                </template>
              </el-table-column>
              <el-table-column label="期望送达" width="140" prop="expected_delivery_date" />
              <el-table-column label="时段" width="140" prop="expected_delivery_slot" />
              <el-table-column label="金额" width="120">
                <template #default="{ row }">{{ money(row.amount) }}</template>
              </el-table-column>
              <el-table-column label="状态" width="100" prop="status" />
            </el-table>
          </section>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.billing-overview {
  display: grid;
  gap: 16px;
}
.hero-card {
  border-radius: 8px;
}
.hero-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}
.title {
  font-size: 22px;
  font-weight: 700;
}
.subtitle {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
}
.actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.kpi-card {
  display: grid;
  gap: 6px;
  padding: 16px;
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  transition: border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
}
.kpi-clickable {
  cursor: pointer;
}
.kpi-clickable:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 6px 16px rgba(64, 96, 220, 0.10);
  transform: translateY(-1px);
}
.kpi-card span {
  color: var(--el-text-color-secondary);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.kpi-card strong {
  font-size: 22px;
  color: #0f172a;
}
.kpi-hint {
  font-size: 12px;
}
.tip-icon {
  color: #94a3b8;
  cursor: help;
}

.upcoming-list {
  margin: 6px 0 0;
  padding-left: 18px;
  display: grid;
  gap: 4px;
}
.upcoming-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 6px;
  transition: background 120ms ease;
}
.upcoming-item:hover {
  background: rgba(234, 179, 8, 0.10);
}
.upcoming-tip {
  font-size: 12px;
  color: #92400e;
  margin-bottom: 4px;
}

.clickable-table :deep(.el-table__row) {
  cursor: pointer;
}
.clickable-table :deep(.el-table__row):hover > td {
  background-color: #f1f5fb !important;
}

.detail-section :deep(.el-card__header) {
  padding: 12px 16px;
}
.detail-section-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
.detail-section-title {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}
.detail-section-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.filter-form {
  margin-bottom: 8px;
}
.detail-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #475569;
  margin-bottom: 10px;
  padding: 8px 12px;
  background: #f8fafc;
  border-radius: 6px;
}
.detail-summary strong {
  color: #0f172a;
}
.detail-summary .el-tag {
  margin-right: 4px;
}
.pagination-row {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

.grouped-section :deep(.el-card__header) {
  padding: 12px 16px;
}
.grouped-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.grouped-title {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
  margin-right: 10px;
}
.grouped-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.grouped-filter {
  margin-bottom: 8px;
}
.group-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
}
.group-title strong {
  color: #0f172a;
  font-size: 15px;
}
.group-title-sub {
  margin-left: auto;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.group-title-sub strong {
  color: #0f172a;
  font-size: 13px;
  margin: 0 2px;
}
.group-overdue {
  color: #dc2626;
  font-weight: 600;
  margin-left: 4px;
}
.group-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #475569;
  padding: 8px 12px;
  background: #f8fafc;
  border-radius: 6px;
  margin-bottom: 10px;
}
.group-meta strong {
  color: #0f172a;
  margin-left: 2px;
}
.group-meta-spacer {
  flex: 1;
}
.group-table {
  margin-top: 4px;
}

.detail-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.detail-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}
.detail-meta-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.detail-meta-4 {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
.detail-meta div {
  padding: 9px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
}
.detail-meta span {
  display: block;
  font-size: 12px;
  color: #64748b;
  margin-bottom: 4px;
}
.detail-meta strong {
  color: #0f172a;
  font-size: 14px;
}

.detail-block .block-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.cycle-scope-tag {
  font-weight: normal;
}
.block-sub {
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
}
.mirror-card {
  padding: 12px;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  background: #f8fafc;
  cursor: pointer;
  transition: border-color 120ms ease;
}
.mirror-card:hover {
  border-color: var(--el-color-primary);
}
.mirror-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.mirror-row.mirror-sub {
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
}
.mirror-row.mirror-sub .mirror-link {
  margin-left: auto;
  color: var(--el-color-primary);
}

@media (max-width: 960px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .hero-row {
    flex-direction: column;
  }
  .detail-meta-3,
  .detail-meta-4 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
