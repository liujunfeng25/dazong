<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowRight, QuestionFilled, WarningFilled } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { deliveryOrderPoolApi, smartSplitCommitApi, smartSplitPreviewApi } from '../../api/delivery'
import { orderStatusLabel } from '../../utils/orderStatus'

const loading = ref(false)
const committing = ref(false)
const orderPool = ref([])
const selectedOrderIds = ref([])
const splitResults = ref([])
/** 分单结果表格：按当前选中的供货商 id 筛选展示，'' 表示全部 */
const supplierViewFilterId = ref('')
const scoreBarRefs = new Map()
const scoreBarCharts = new Map()
const mode = ref('normal')
/** 配额统计周期：与后端 smart-split 的 quota_window 一致，可改；拆行/上限/阈值由模式预设不可在此改 */
const quotaWindow = ref('week')
const modeMeta = ref({
  mode: 'normal',
  mode_label: '均衡协同',
  allow_split: false,
  max_suppliers_per_order: 2,
  split_quantity_threshold: 2,
  quota_window: 'week',
})

const PARAM_HELP = {
  allow_split:
    '是否允许把同一订单行拆成多条记录分给不同供货商。关闭时一行只能对应一家，减少协同成本；开启时可在满足阈值条件下拆行分散供货。',
  max_suppliers:
    '单个订单内最多允许多少家供货商同时参与。数字越大越分散、集货协调成本越高，由当前模式在系统内预设。',
  split_threshold:
    '当某行订购数量小于等于该值时，引擎不会自动拆成多行，避免小单被切得过碎。具体是否允许拆行还受上方「拆行开关」约束。',
  quota_window:
    '统计「历史已确认分单」的时间范围，用于计算各供货商份额（软配额）。周更敏感、月更平滑、季看长期结构。修改后请重新点「生成建议」刷新快照。',
}

const modeOptions = [
  { value: 'eco', label: '成本优先', desc: '优先控制采购成本，兼顾路程与评分，最多2家供货商' },
  { value: 'normal', label: '均衡协同', desc: '成本/配额/路程/评分均衡，默认不拆行，最多2家供货商' },
  { value: 'sport', label: '多源保障', desc: '分散供货、可拆行，最多3家供货商' },
]

/** 与后端 `delivery._mode_config` 保持一致，用于切换模式时立即刷新引擎说明（无需先点生成建议） */
const MODE_DEFS = {
  eco: {
    mode_label: '成本优先',
    allow_split: false,
    max_suppliers_per_order: 2,
    split_quantity_threshold: 2,
    weights: { price: 0.55, quota: 0.1, distance: 0.2, rating: 0.1, stability: 0.05 },
  },
  normal: {
    mode_label: '均衡协同',
    allow_split: false,
    max_suppliers_per_order: 2,
    split_quantity_threshold: 2,
    weights: { price: 0.35, quota: 0.2, distance: 0.2, rating: 0.15, stability: 0.1 },
  },
  sport: {
    mode_label: '多源保障',
    allow_split: true,
    max_suppliers_per_order: 3,
    split_quantity_threshold: 2,
    weights: { price: 0.25, quota: 0.35, distance: 0.15, rating: 0.15, stability: 0.1 },
  },
}

const loadOrderPool = async () => {
  orderPool.value = await deliveryOrderPoolApi()
}

const globalRowIndex = (row) => splitResults.value.indexOf(row)

const filteredSplitResults = computed(() => {
  const fid = String(supplierViewFilterId.value || '').trim()
  if (!fid) return splitResults.value
  const id = Number(fid)
  if (!Number.isFinite(id) || id <= 0) return splitResults.value
  return splitResults.value.filter((r) => Number(r.supplier_id) === id)
})

/** 当前结果中出现过的供货商，用于筛选下拉 */
const supplierFilterOptions = computed(() => {
  const labelById = new Map()
  for (const r of splitResults.value) {
    const sid = Number(r.supplier_id || 0)
    if (!sid) continue
    if (labelById.has(sid)) continue
    const so = (r.supplier_options || []).find((x) => Number(x.id) === sid)
    const name = (so && so.label) || `供货商#${sid}`
    labelById.set(sid, name)
  }
  const opts = [{ value: '', label: '全部供货商' }]
  ;[...labelById.entries()]
    .sort((a, b) => a[0] - b[0])
    .forEach(([id, label]) => {
      opts.push({ value: String(id), label: `${label}` })
    })
  return opts
})

const allOrdersSelected = computed(
  () => orderPool.value.length > 0 && selectedOrderIds.value.length === orderPool.value.length,
)
const orderSelectIndeterminate = computed(
  () => selectedOrderIds.value.length > 0 && selectedOrderIds.value.length < orderPool.value.length,
)

const toggleSelectAllOrders = (checked) => {
  if (checked) {
    selectedOrderIds.value = orderPool.value.map((r) => r.id)
  } else {
    selectedOrderIds.value = []
  }
}

const supplierStateMap = (row) => {
  const states = Array.isArray(row?.supplier_option_states) ? row.supplier_option_states : []
  return new Map(states.map((s) => [Number(s.supplier_id), s]))
}

const supplierDisabled = (row, supplierId) => {
  const state = supplierStateMap(row).get(Number(supplierId))
  /** 无 supplier_option_states 的 id（历史误把全库厂家塞进下拉）一律不可选 */
  if (state == null) return true
  return Boolean(state.disabled)
}

const supplierOptionLabel = (row, supplier) => {
  if (!supplier) return ''
  const state = supplierStateMap(row).get(Number(supplier.id))
  if (state == null) return `${supplier.label}（不可选）`
  if (state.disabled) return `${supplier.label}（未报价）`
  if (state.quote_price != null) return `${supplier.label}（¥${Number(state.quote_price).toFixed(2)}）`
  return supplier.label
}

const supplierHoverText = (row) => {
  if (row?.is_designated_factory) return '指定厂家商品，供货商不可改'
  const sid = Number(row?.supplier_id || 0)
  if (!sid) return '请先选择供货商'
  const state = supplierStateMap(row).get(sid)
  if (!state || state.disabled) return '该供货商当前未报价'
  const price = Number(state.quote_price || 0).toFixed(2)
  return `当前供货商报价：¥${price}`
}

const runSmartSplitPreview = async () => {
  if (!selectedOrderIds.value.length) {
    ElMessage.warning('请先选择待分单订单')
    return
  }
  loading.value = true
  try {
    const res = await smartSplitPreviewApi({
      order_ids: selectedOrderIds.value,
      mode: mode.value,
      quota_window: quotaWindow.value,
    })
    modeMeta.value = {
      ...modeMeta.value,
      ...(res.mode_meta || {}),
      mode: (res.mode_meta && res.mode_meta.mode) || mode.value,
    }
    splitResults.value = (res.results || []).map((row) => ({
      ...row,
      quantity: Number(row.quantity || 0),
      unit_price: Number(row.unit_price || 0),
      supplier_id: Number(row.supplier_id || 0),
      has_quoted_suppliers: Boolean(row.has_quoted_suppliers),
    }))
    supplierViewFilterId.value = ''
    await nextTick()
    renderScoreBars()
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '生成建议失败'
    ElMessage.error(typeof msg === 'string' ? msg : '生成建议失败')
    splitResults.value = []
  } finally {
    loading.value = false
  }
}

const splitRow = (row) => {
  const index = splitResults.value.indexOf(row)
  if (index < 0) return
  if (row.is_designated_factory) {
    ElMessage.warning('指定厂家商品不支持拆分')
    return
  }
  const def = MODE_DEFS[mode.value] || MODE_DEFS.normal
  if (!def.allow_split) {
    ElMessage.warning('当前模式不允许拆行')
    return
  }
  if (!row.allow_split) {
    ElMessage.warning(`该行数量较小，低于拆分阈值 ${def.split_quantity_threshold}`)
    return
  }
  const qty = Number(row.quantity || 0)
  if (qty <= 1) {
    ElMessage.warning('当前行数量过小，无法再拆分')
    return
  }
  const left = Number((qty / 2).toFixed(3))
  const right = Number((qty - left).toFixed(3))
  row.quantity = left
  splitResults.value.splice(index + 1, 0, {
    ...row,
    quantity: right,
  })
}

const removeRow = (row) => {
  const index = splitResults.value.indexOf(row)
  if (index < 0) return
  if (splitResults.value[index]?.is_designated_factory) {
    ElMessage.warning('指定厂家商品不允许删除')
    return
  }
  splitResults.value.splice(index, 1)
}

const scoreRowKey = (row, idx = 0) =>
  `${row.order_id || 0}-${row.line_no || 0}-${row.product_id || 0}-${idx}`

const setScoreBarRef = (el, row, idx) => {
  const key = scoreRowKey(row, idx)
  if (!el) {
    const chart = scoreBarCharts.get(key)
    if (chart) chart.dispose()
    scoreBarCharts.delete(key)
    scoreBarRefs.delete(key)
    return
  }
  scoreBarRefs.set(key, el)
}

const renderScoreBars = () => {
  splitResults.value.forEach((row, globalIdx) => {
    const key = scoreRowKey(row, globalIdx)
    const el = scoreBarRefs.get(key)
    if (!el) return
    let chart = scoreBarCharts.get(key)
    if (!chart) {
      chart = echarts.init(el)
      scoreBarCharts.set(key, chart)
    }
    const b = row.score_breakdown || {}
    const p = Number(b.price_ratio || 0) * 100
    const q = Number(b.quota_ratio || 0) * 100
    const s = Number(b.stability_ratio || 0) * 100
    chart.setOption(
      {
        animation: false,
        grid: { left: 0, right: 0, top: 0, bottom: 0, containLabel: false },
        xAxis: { type: 'value', max: 100, show: false },
        yAxis: { type: 'category', data: [''], show: false },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          formatter: () =>
            `价格分占比：${p.toFixed(1)}%<br/>配额分占比：${q.toFixed(1)}%<br/>稳定性占比：${s.toFixed(1)}%`,
        },
        series: [
          { name: '价格', type: 'bar', stack: 'score', barWidth: 10, data: [p], itemStyle: { color: '#3b82f6' } },
          { name: '配额', type: 'bar', stack: 'score', barWidth: 10, data: [q], itemStyle: { color: '#22c55e' } },
          { name: '稳定性', type: 'bar', stack: 'score', barWidth: 10, data: [s], itemStyle: { color: '#f59e0b' } },
        ],
      },
      true,
    )
  })
}

const validateAllocations = () => {
  if (!splitResults.value.length) {
    ElMessage.warning('请先生成分单建议')
    return false
  }
  const sourceMap = new Map()
  const commitMap = new Map()
  for (const row of splitResults.value) {
    if (!row.has_quoted_suppliers) {
      ElMessage.warning(`订单${row.order_no} 第${row.line_no}行暂无供货商报价，请先报价后再分单`)
      return false
    }
    if (!row.supplier_id) {
      ElMessage.warning('每一行都必须选择供货商')
      return false
    }
    if (supplierDisabled(row, row.supplier_id)) {
      ElMessage.warning(`订单${row.order_no} 第${row.line_no}行所选供货商未报价，请重新选择`)
      return false
    }
    const key = `${row.order_id}-${row.line_no}`
    const sourceQty = Number(row.source_quantity ?? row.quantity ?? 0)
    if (!sourceMap.has(key)) sourceMap.set(key, sourceQty)
    const sum = Number(commitMap.get(key) || 0) + Number(row.quantity || 0)
    commitMap.set(key, Number(sum.toFixed(3)))
  }
  for (const [key, src] of sourceMap.entries()) {
    const committed = Number(commitMap.get(key) || 0)
    if (Number(committed.toFixed(3)) !== Number(Number(src).toFixed(3))) {
      ElMessage.warning(`行 ${key} 分配数量不平衡（原始${src}，当前${committed}）`)
      return false
    }
  }
  return true
}

const commitSmartSplit = async () => {
  if (!validateAllocations()) return
  committing.value = true
  try {
    const payload = {
      mode: mode.value,
      quota_window: quotaWindow.value,
      allocations: splitResults.value.map((row) => ({
        order_id: row.order_id,
        line_no: row.line_no,
        product_id: row.product_id,
        quantity: Number(row.quantity || 0),
        unit_price: Number(row.unit_price || 0),
        supplier_id: Number(row.supplier_id),
      })),
    }
    const res = await smartSplitCommitApi(payload)
    ElMessage.success(`分单提交成功，已生成 ${res.created || 0} 条`)
    splitResults.value = []
    selectedOrderIds.value = []
    await loadOrderPool()
  } finally {
    committing.value = false
  }
}

/** 上次「生成建议」返回的统计是否与当前界面上的模式+配额周期一致 */
const previewStatsSynced = computed(
  () =>
    (modeMeta.value?.mode || '') === mode.value &&
    (modeMeta.value?.quota_window || '') === quotaWindow.value,
)

const activeModeMeta = computed(() => {
  const def = MODE_DEFS[mode.value] || MODE_DEFS.normal
  const synced = previewStatsSynced.value
  return {
    mode: mode.value,
    mode_label: def.mode_label,
    allow_split: def.allow_split,
    max_suppliers_per_order: def.max_suppliers_per_order,
    split_quantity_threshold: def.split_quantity_threshold,
    quota_window: quotaWindow.value,
    weights: def.weights,
    quota_snapshot: synced ? modeMeta.value?.quota_snapshot : [],
    rating_data: synced ? modeMeta.value?.rating_data : undefined,
  }
})

const quotaTopText = computed(() => {
  if (!previewStatsSynced.value) {
    return '配额快照：已切换模式或配额周期，请点击「生成建议」后刷新（份额来自库表 order_item_allocations 聚合）'
  }
  const list = Array.isArray(activeModeMeta.value?.quota_snapshot) ? activeModeMeta.value.quota_snapshot : []
  if (!list.length) return '暂无历史配额统计（首次分单）'
  const sorted = [...list].sort((a, b) => Number(b.usage_ratio || 0) - Number(a.usage_ratio || 0))
  const top = sorted[0]
  const supplierName = top.supplier_name || `供货商${top.supplier_id}`
  return `当前最高份额供货商 ${supplierName}，占比约 ${(Number(top.usage_ratio || 0) * 100).toFixed(1)}%`
})

const ratingDataText = computed(() => {
  if (!previewStatsSynced.value) {
    return '供应商评分统计：切换模式或配额周期后请重新「生成建议」以与当前页同步'
  }
  const data = activeModeMeta.value?.rating_data || {}
  const rated = Number(data.rated_supplier_count || 0)
  const total = Number(data.total_supplier_count || 0)
  const coverage = Number(data.coverage || 0)
  if (!total || !rated) {
    return '供应商评分：暂未接入真实评分数据（当前不参与评分因子计算）'
  }
  return `供应商评分覆盖：${rated}/${total}（${(coverage * 100).toFixed(1)}%）`
})

const engineExplainTips = computed(() => {
  const modeLabel = activeModeMeta.value?.mode_label || '均衡协同'
  const maxSuppliers = Number(activeModeMeta.value?.max_suppliers_per_order || 0)
  const splitThreshold = Number(activeModeMeta.value?.split_quantity_threshold || 0)
  return [
    `当前模式：${modeLabel}`,
    '综合分计算：价格分×w1 + 配额分×w2 + 距离分×w3 + 评分分×w4 + 稳定性×w5。',
    '价格分：同商品候选供货商按报价相对位置归一化，报价越低分越高。',
    '配额分：基于近周/近月历史分配占比，份额越低越容易加分，用于抑制一家独大。',
    '距离分：按“配送商分拣场坐标 ↔ 供货商坐标”估算距离，越近分越高；无坐标时按未知距离处理。',
    '评分分：仅使用真实客户评价均分（1~5分）；未接入或无评分时该因子不参与打分。',
    '稳定性：用于减少同一订单内供货商频繁切换，已入选供货商在后续行项目获得稳定性加分，降低集货沟通成本。',
    `边界规则：单订单最多${maxSuppliers}家供货商；拆分阈值为${splitThreshold}，小于阈值默认不拆。`,
    '建议说明会显示本行主导因子（如成本优先/配额均衡/距离优先/评分优先），便于人工复核。',
  ].join('\n')
})

const riskBanner = computed(() => {
  if (!splitResults.value.length) {
    return { text: '请先生成建议', type: 'info' }
  }
  const splitRows = splitResults.value.filter((r) => Number(r.quantity) !== Number(r.source_quantity)).length
  const suppliers = new Set(splitResults.value.map((r) => Number(r.supplier_id)))
  if (splitRows > 0 || suppliers.size > 2) {
    return { text: '当前方案存在较高集货等待风险，请评估到场时效', type: 'danger' }
  }
  if (suppliers.size > 1) {
    return { text: '当前方案为多供货商协同，请关注到场时间', type: 'warning' }
  }
  return { text: '当前方案集货效率较高', type: 'success' }
})

const suggestPreview = (row) => {
  const t = String(row?.suggest_reason || '规则命中').trim()
  if (t.length <= 22) return t
  return `${t.slice(0, 22)}…`
}

const scoreDetailLines = (row) => {
  const b = row?.score_breakdown || {}
  const fmt = (n) => Number(n || 0).toFixed(4)
  const pct = (x) => `${(Number(x || 0) * 100).toFixed(1)}%`
  return [
    { k: '价格贡献（加权）', v: fmt(b.price), sub: `结构占比 ${pct(b.price_ratio)}` },
    { k: '配额贡献（加权）', v: fmt(b.quota), sub: `结构占比 ${pct(b.quota_ratio)}` },
    { k: '稳定性贡献（加权）', v: fmt(b.stability), sub: `结构占比 ${pct(b.stability_ratio)}` },
  ]
}

onMounted(loadOrderPool)

watch(
  () => splitResults.value,
  async () => {
    await nextTick()
    renderScoreBars()
  },
  { deep: true },
)

watch(supplierViewFilterId, async () => {
  await nextTick()
  renderScoreBars()
})

onBeforeUnmount(() => {
  scoreBarCharts.forEach((chart) => chart.dispose())
  scoreBarCharts.clear()
  scoreBarRefs.clear()
})
</script>

<template>
  <el-row :gutter="12">
    <el-col :span="8">
      <el-card>
        <template #header>待分单订单</template>
        <el-radio-group v-model="mode" class="mode-group">
          <el-radio-button v-for="m in modeOptions" :key="m.value" :label="m.value">
            {{ m.label }}
          </el-radio-button>
        </el-radio-group>
        <div class="mode-tip">{{ modeOptions.find((m) => m.value === mode)?.desc }}</div>
        <div v-if="orderPool.length" class="order-pool-toolbar">
          <el-checkbox
            :model-value="allOrdersSelected"
            :indeterminate="orderSelectIndeterminate"
            @change="toggleSelectAllOrders"
          >
            全选
          </el-checkbox>
          <span class="order-pool-count">已选 {{ selectedOrderIds.length }} / {{ orderPool.length }}</span>
        </div>
        <el-checkbox-group v-model="selectedOrderIds" class="w-full">
          <div
            v-for="row in orderPool"
            :key="row.id"
            class="mb-2 flex items-center justify-between rounded border p-2"
          >
            <el-checkbox :label="row.id">订单{{ row.order_no }}</el-checkbox>
            <span class="text-sm text-slate-500">{{ orderStatusLabel(row.status) }}</span>
          </div>
        </el-checkbox-group>
      </el-card>
      <el-card class="mt-2">
        <template #header>
          <div class="engine-header">
            <span>智能分单引擎说明</span>
            <el-tooltip
              :content="engineExplainTips"
              placement="top-start"
              effect="dark"
              popper-class="engine-help-tooltip"
            >
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
        </template>
        <div class="engine-panel">
          <div class="engine-row">
            <span>模式：</span>
            <el-tag size="small" type="success">{{ activeModeMeta.mode_label || '均衡协同' }}</el-tag>
          </div>
          <div class="engine-row engine-row--param">
            <span class="param-label">
              拆行开关
              <el-tooltip :content="PARAM_HELP.allow_split" placement="top" effect="dark" :show-after="200">
                <el-icon class="inline-help"><QuestionFilled /></el-icon>
              </el-tooltip>
              ：
            </span>
            <el-tag size="small" :type="activeModeMeta.allow_split ? 'warning' : 'info'">
              {{ activeModeMeta.allow_split ? '允许拆行' : '不允许拆行' }}
            </el-tag>
          </div>
          <div class="engine-row engine-row--param">
            <span class="param-label">
              最多供货商
              <el-tooltip :content="PARAM_HELP.max_suppliers" placement="top" effect="dark" :show-after="200">
                <el-icon class="inline-help"><QuestionFilled /></el-icon>
              </el-tooltip>
              ：
            </span>
            <span>{{ activeModeMeta.max_suppliers_per_order }} 家</span>
          </div>
          <div class="engine-row engine-row--param">
            <span class="param-label">
              拆分阈值
              <el-tooltip :content="PARAM_HELP.split_threshold" placement="top" effect="dark" :show-after="200">
                <el-icon class="inline-help"><QuestionFilled /></el-icon>
              </el-tooltip>
              ：
            </span>
            <span>{{ activeModeMeta.split_quantity_threshold }}（小于等于该值不自动拆行）</span>
          </div>
          <div class="engine-row engine-row--param engine-row--quota">
            <span class="param-label">
              配额统计周期
              <el-tooltip :content="PARAM_HELP.quota_window" placement="top" effect="dark" :show-after="200">
                <el-icon class="inline-help"><QuestionFilled /></el-icon>
              </el-tooltip>
              ：
            </span>
            <el-select v-model="quotaWindow" size="small" class="quota-select">
              <el-option value="week" label="近7天（周）" />
              <el-option value="month" label="近30天（月）" />
              <el-option value="quarter" label="近90天（季）" />
            </el-select>
          </div>
          <el-divider class="engine-divider" />
          <div class="engine-title-row">
            <span class="engine-title">权重因子</span>
            <el-tooltip placement="top" effect="dark" :show-after="200">
              <template #content>
                <div class="engine-inline-tip">
                  <div>{{ ratingDataText }}</div>
                  <div>软配额：超份额不拦截，仅做降权。</div>
                  <div>{{ quotaTopText }}</div>
                </div>
              </template>
              <el-icon class="engine-title-help"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
          <div class="engine-row">价格分权重：{{ Number(activeModeMeta.weights?.price || 0).toFixed(2) }}</div>
          <div class="engine-row">配额分权重：{{ Number(activeModeMeta.weights?.quota || 0).toFixed(2) }}</div>
          <div class="engine-row">距离分权重：{{ Number(activeModeMeta.weights?.distance || 0).toFixed(2) }}</div>
          <div class="engine-row">评分分权重：{{ Number(activeModeMeta.weights?.rating || 0).toFixed(2) }}</div>
          <div class="engine-row">稳定性权重：{{ Number(activeModeMeta.weights?.stability || 0).toFixed(2) }}</div>
          <div class="engine-formula">综合分 = 价格分×w1 + 配额分×w2 + 距离分×w3 + 评分分×w4 + 稳定性×w5</div>
        </div>
      </el-card>
    </el-col>
    <el-col :span="16">
      <el-card class="result-card">
        <template #header>
          <div class="result-card-header">
            <div class="result-card-header__left">
              <span class="result-card-title">分单结果</span>
              <span class="result-card-sub">行级可编辑 · 柱状图为结构占比</span>
            </div>
            <div class="result-card-header__right">
              <span class="supplier-filter-label">供货商</span>
              <el-select
                v-model="supplierViewFilterId"
                placeholder="全部供货商"
                clearable
                filterable
                size="small"
                class="supplier-view-filter"
                :disabled="!splitResults.length"
              >
                <el-option
                  v-for="opt in supplierFilterOptions"
                  :key="opt.value === '' ? '__all__' : opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
              <span v-if="supplierViewFilterId && splitResults.length" class="supplier-filter-count">
                {{ filteredSplitResults.length }} / {{ splitResults.length }} 行
              </span>
            </div>
          </div>
        </template>
        <div class="result-risk-strip">
          <el-tag :type="riskBanner.type" effect="plain" size="small" class="risk-tag">{{ riskBanner.text }}</el-tag>
        </div>
        <el-table
          :data="filteredSplitResults"
          class="split-result-table"
          size="small"
          stripe
          border
          empty-text="暂无数据，请勾选订单后生成建议"
        >
          <el-table-column prop="order_no" label="订单号" min-width="118" show-overflow-tooltip />
          <el-table-column prop="line_no" label="行" width="52" align="center" />
          <el-table-column prop="product_name" label="商品" min-width="160" show-overflow-tooltip />
          <el-table-column label="数量" width="112">
            <template #default="{ row }">
              <el-input-number
                v-model="row.quantity"
                :min="0.001"
                :precision="3"
                :step="1"
                :disabled="row.is_designated_factory"
                size="small"
                controls-position="right"
                class="qty-input"
              />
            </template>
          </el-table-column>
          <el-table-column label="供货商" min-width="158">
            <template #default="{ row }">
              <div class="supplier-cell">
                <el-tooltip :content="supplierHoverText(row)" placement="top" :show-after="160">
                  <el-select v-model="row.supplier_id" class="supplier-select" size="small" :disabled="row.is_designated_factory">
                    <el-option
                      v-for="s in row.supplier_options || []"
                      :key="s.id"
                      :value="s.id"
                      :label="supplierOptionLabel(row, s)"
                      :disabled="supplierDisabled(row, s.id)"
                    />
                  </el-select>
                </el-tooltip>
                <el-tooltip v-if="!row.has_quoted_suppliers" content="该商品暂无供货商报价，暂不可分配" placement="top">
                  <el-icon class="supplier-warn-icon" :size="16"><WarningFilled /></el-icon>
                </el-tooltip>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="建议说明" min-width="148">
            <template #default="{ row }">
              <el-popover placement="left" :width="340" trigger="click" popper-class="split-detail-popper">
                <template #reference>
                  <button type="button" class="cell-detail-trigger">
                    <span class="cell-detail-trigger__text">{{ suggestPreview(row) }}</span>
                    <el-icon class="cell-detail-trigger__icon"><ArrowRight /></el-icon>
                  </button>
                </template>
                <div class="detail-popover">
                  <div class="detail-popover__title">建议说明</div>
                  <p class="detail-popover__body">{{ row.suggest_reason || '规则命中' }}</p>
                </div>
              </el-popover>
            </template>
          </el-table-column>
          <el-table-column label="分值构成" min-width="176">
            <template #default="{ row }">
              <el-popover placement="left" :width="280" trigger="click" popper-class="split-detail-popper">
                <template #reference>
                  <div class="score-cell-trigger" role="button" tabindex="0">
                    <div
                      :ref="(el) => setScoreBarRef(el, row, globalRowIndex(row))"
                      class="score-bar score-bar--cell"
                    ></div>
                    <div class="score-cell-meta">
                      <span>
                        价 {{ Number((row.score_breakdown?.price_ratio || 0) * 100).toFixed(0) }}% · 配
                        {{ Number((row.score_breakdown?.quota_ratio || 0) * 100).toFixed(0) }}% · 稳
                        {{ Number((row.score_breakdown?.stability_ratio || 0) * 100).toFixed(0) }}%
                      </span>
                      <span class="score-cell-meta__hint">明细</span>
                    </div>
                  </div>
                </template>
                <div class="detail-popover">
                  <div class="detail-popover__title">加权得分明细</div>
                  <ul class="score-detail-list">
                    <li v-for="line in scoreDetailLines(row)" :key="line.k" class="score-detail-list__item">
                      <div class="score-detail-list__k">{{ line.k }}</div>
                      <div class="score-detail-list__v">{{ line.v }}</div>
                      <div class="score-detail-list__sub">{{ line.sub }}</div>
                    </li>
                  </ul>
                </div>
              </el-popover>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="108" align="center" fixed="right">
            <template #default="{ row }">
              <div class="row-actions">
                <el-button
                  size="small"
                  type="primary"
                  link
                  @click="splitRow(row)"
                  :disabled="row?.is_designated_factory"
                >
                  拆分
                </el-button>
                <el-button
                  size="small"
                  type="danger"
                  link
                  @click="removeRow(row)"
                  :disabled="row?.is_designated_factory"
                >
                  删除
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </el-col>
  </el-row>
  <el-card class="mt-3 sticky-actions">
    <el-button type="primary" :loading="loading" @click="runSmartSplitPreview">生成建议</el-button>
    <el-button
      type="success"
      class="confirm-btn"
      :loading="committing"
      :disabled="!splitResults.length"
      @click="commitSmartSplit"
    >
      确认分单
    </el-button>
    <span class="action-hint">
      {{ splitResults.length ? '可提交当前分单方案' : '请先生成建议后再确认分单' }}
    </span>
  </el-card>
  <el-card class="mt-2">
    <template #header>手动分单指引</template>
    <div class="manual-guide">
      1）先点“生成建议”；2）右上角「供货商」可筛选查看某家被分配了哪些行；3）在“分配数量”中直接改数；4）在“供货商”列切换供应商；
      5）需要一行分给两家时点“拆分”；6）误操作可点“删除”后重新生成建议。
      <br />
      注意：同一订单行的分配总量必须等于原始数量，否则“确认分单”无法提交。
    </div>
  </el-card>
</template>

<style scoped>
.mode-group {
  margin-bottom: 8px;
}

.mode-tip {
  margin-bottom: 10px;
  color: #909399;
  font-size: 12px;
}

.order-pool-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  padding: 6px 8px;
  background: #f8fafc;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.order-pool-count {
  font-size: 12px;
  color: #64748b;
}

.engine-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: #475569;
}

.engine-title {
  font-weight: 600;
  color: #1f2937;
}

.engine-row {
  line-height: 1.4;
}

.engine-formula {
  margin-top: 4px;
  color: #334155;
  font-weight: 600;
}

.engine-divider {
  margin: 12px 0;
}

.engine-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.engine-title-help {
  color: #94a3b8;
  cursor: help;
  font-size: 14px;
}

.engine-title-help:hover {
  color: #409eff;
}

.engine-inline-tip {
  max-width: 320px;
  line-height: 1.55;
  font-size: 12px;
}

.engine-inline-tip div + div {
  margin-top: 6px;
}

.engine-row--param {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.param-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.inline-help {
  color: #94a3b8;
  cursor: help;
  font-size: 14px;
}

.inline-help:hover {
  color: #409eff;
}

.quota-select {
  width: 168px;
}

.engine-header {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.help-icon {
  color: #409eff;
  cursor: pointer;
  font-size: 14px;
}

:deep(.engine-help-tooltip) {
  max-width: 420px;
  white-space: pre-line;
  line-height: 1.55;
}

.result-card :deep(.el-card__header) {
  padding: 12px 16px;
  border-bottom: 1px solid #f1f5f9;
}

.result-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.result-card-header__left {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.result-card-title {
  font-weight: 600;
  color: #0f172a;
}

.result-card-sub {
  font-size: 12px;
  font-weight: 400;
  color: #94a3b8;
}

.result-card-header__right {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  flex-shrink: 0;
}

.supplier-filter-label {
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
}

.supplier-view-filter {
  width: 200px;
  max-width: 56vw;
}

.supplier-filter-count {
  font-size: 12px;
  color: #94a3b8;
  white-space: nowrap;
}

.result-risk-strip {
  margin-bottom: 10px;
}

.risk-tag {
  border-radius: 6px;
}

.split-result-table {
  --el-table-border-color: #e8ecf1;
  border-radius: 8px;
  overflow: hidden;
}

.split-result-table :deep(.el-table__header-wrapper th) {
  background: #f8fafc !important;
  color: #475569;
  font-weight: 600;
  font-size: 12px;
}

.split-result-table :deep(.el-table__body tr:hover > td) {
  background-color: #fafbfc !important;
}

.split-result-table :deep(.el-table__cell) {
  padding: 8px 10px;
}

.cell-detail-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  padding: 4px 2px;
  margin: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  font: inherit;
  color: #334155;
  text-align: left;
  border-radius: 6px;
  transition: background 0.15s ease, color 0.15s ease;
}

.cell-detail-trigger:hover {
  background: #f1f5f9;
  color: #1d4ed8;
}

.cell-detail-trigger__text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.cell-detail-trigger__icon {
  flex-shrink: 0;
  font-size: 12px;
  color: #94a3b8;
}

.cell-detail-trigger:hover .cell-detail-trigger__icon {
  color: #3b82f6;
}

.score-cell-trigger {
  padding: 4px 6px;
  margin: -4px -6px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.score-cell-trigger:hover {
  background: #f8fafc;
}

.score-bar--cell {
  height: 14px;
}

.score-cell-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 4px;
  font-size: 11px;
  color: #64748b;
}

.score-cell-meta__hint {
  flex-shrink: 0;
  font-size: 11px;
  color: #94a3b8;
  letter-spacing: 0.02em;
}

.score-cell-trigger:hover .score-cell-meta__hint {
  color: #3b82f6;
}

.supplier-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.supplier-select {
  flex: 1;
  min-width: 0;
}

.supplier-warn-icon {
  flex-shrink: 0;
  color: #f56c6c;
  cursor: default;
}

.qty-input {
  width: 100%;
}

.qty-input :deep(.el-input__wrapper) {
  padding-left: 8px;
  padding-right: 28px;
}

.sticky-actions {
  position: sticky;
  bottom: 10px;
  z-index: 20;
  border: 1px solid #dbe2ef;
}

.action-hint {
  margin-left: 10px;
  color: #64748b;
  font-size: 12px;
}

.row-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.score-bar-wrap {
  width: 100%;
}

.score-bar {
  width: 100%;
  height: 20px;
}

.score-legend {
  margin-top: 2px;
  font-size: 11px;
  color: #64748b;
}

.manual-guide {
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
}

:deep(.confirm-btn.el-button--success) {
  color: #fff !important;
  background-color: #67c23a !important;
  border-color: #67c23a !important;
}

:deep(.confirm-btn.el-button--success.is-disabled) {
  color: #c0c4cc !important;
  background-color: #f5f7fa !important;
  border-color: #e4e7ed !important;
}
</style>

<style>
/* Popover 挂载在 body，需全局类名 */
.split-detail-popper.el-popover.el-popper {
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid #e8ecf1;
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.1);
}

.split-detail-popper .detail-popover__title {
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-bottom: 10px;
}

.split-detail-popper .detail-popover__body {
  margin: 0;
  font-size: 13px;
  line-height: 1.65;
  color: #1e293b;
}

.split-detail-popper .score-detail-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.split-detail-popper .score-detail-list__item {
  padding: 8px 0;
  border-bottom: 1px solid #f1f5f9;
}

.split-detail-popper .score-detail-list__item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.split-detail-popper .score-detail-list__k {
  font-size: 12px;
  color: #64748b;
}

.split-detail-popper .score-detail-list__v {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
  font-variant-numeric: tabular-nums;
  margin-top: 2px;
}

.split-detail-popper .score-detail-list__sub {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 2px;
}
</style>
