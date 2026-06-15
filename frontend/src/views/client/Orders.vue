<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listOrdersApi } from '../../api/orders'
import { formatChinaDateTime } from '../../utils/datetime'
import { MAIN_ORDER_STATUS_OPTIONS, orderStatusLabel, orderStatusTagColor } from '../../utils/orderStatus'
import { useIsMobile } from '../../composables/useIsMobile'

const router = useRouter()
const route = useRoute()
const { isMobile } = useIsMobile()
const status = ref('')
const orderNo = ref('')
const dateRange = ref([])
const list = ref([])
const loading = ref(false)
const differenceFilter = ref('')
// 从看板 KPI 下钻的视图过滤：'' | 'in_progress' | 'abnormal'
const viewFilter = ref('')
const CLIENT_ACTIVE_STATUSES = ['下单', '配货', '发货', '收货', '收货确认']
const filteredList = computed(() => {
  let rows = list.value
  if (viewFilter.value === 'in_progress') {
    rows = rows.filter((row) => CLIENT_ACTIVE_STATUSES.includes(row.status))
  } else if (viewFilter.value === 'abnormal') {
    rows = rows.filter((row) => row.has_abnormal)
  }
  if (differenceFilter.value === 'any') {
    rows = rows.filter((row) => row.receiving_difference?.has_receiving_difference)
  } else if (differenceFilter.value) {
    rows = rows.filter((row) => row.receiving_difference?.difference_type === differenceFilter.value)
  }
  return rows
})
// 看板下钻时顶部显示的上下文标签
const contextLabel = computed(() => {
  if (viewFilter.value === 'abnormal') return '异常订单'
  if (viewFilter.value === 'in_progress') return '进行中订单'
  if (status.value === '收货') return '待确认收货'
  return ''
})
// 'created' = 按下单时间筛选；'delivery' = 按配送时间筛选
const dateMode = ref('created')
// 移动端日期范围预设：today / 7d / 30d / custom
const datePreset = ref('today')
const toDateStr = (d) => {
  const dt = new Date(d)
  const m = String(dt.getMonth() + 1).padStart(2, '0')
  const day = String(dt.getDate()).padStart(2, '0')
  return `${dt.getFullYear()}-${m}-${day}`
}
const initToday = () => {
  const now = new Date()
  dateRange.value = [now, now]
}
const applyQuickFilter = (mode) => {
  dateMode.value = mode
  initToday()
  load()
}
// 移动端：切时间维度（按下单/按送达），保留当前范围
const setDateMode = (mode) => {
  if (dateMode.value === mode) return
  dateMode.value = mode
  load()
}
// 移动端：日期范围预设
const applyPreset = (preset) => {
  datePreset.value = preset
  if (preset === 'custom') return // 由 el-date-picker 触发 load
  const now = new Date()
  let start = new Date()
  if (preset === '7d') start.setDate(now.getDate() - 6)
  else if (preset === '30d') start.setDate(now.getDate() - 29)
  else if (preset === 'month') start = new Date(now.getFullYear(), now.getMonth(), 1)
  // 'today' → start = now
  dateRange.value = [start, now]
  load()
}
const datePresets = [
  { key: 'today', label: '今天' },
  { key: 'month', label: '本月' },
  { key: '7d', label: '近7天' },
  { key: '30d', label: '近30天' },
  { key: 'custom', label: '自定义' },
]
const receivingDifferenceText = (diff, type) => {
  if (!diff) return '—'
  if (type === 'shortage') return diff.shortage_text || diff.diff_label || `${diff.shortage_qty ?? diff.shortage_kg ?? 0} ${diff.measure_unit || 'kg'}`
  if (type === 'overage') return diff.overage_text || diff.diff_label || `${diff.overage_qty ?? diff.overage_kg ?? 0} ${diff.measure_unit || 'kg'}`
  return diff.diff_label || '—'
}
const goDetail = (row) => {
  if (row?.id != null) router.push(`/client/orders/${row.id}`)
}
// 卡片主标题：商品摘要（前 2 个商品名 + 等 N 项）；无快照回退订单号
const itemsSummary = (row) => {
  const snaps = Array.isArray(row?.items_snapshot_json) ? row.items_snapshot_json : []
  const names = snaps.map((s) => s?.product_name).filter(Boolean)
  const count = names.length || Number(row?.receiving_total_lines || 0)
  if (!names.length) return row?.order_no || '订单'
  const head = names.slice(0, 2).join('、')
  return count > 2 ? `${head} 等 ${count} 项` : head
}
// 送达日：expected_delivery_date(MM/DD) + slot
const deliveryText = (row) => {
  const raw = row?.expected_delivery_date
  const dateStr = raw != null && raw !== '' ? String(raw).slice(0, 10) : ''
  const md = dateStr ? dateStr.slice(5).replace('-', '/') : ''
  const slot = (row?.expected_delivery_slot || '').trim()
  if (md && slot) return `${md} ${slot}`
  return md || slot || ''
}
const load = async () => {
  loading.value = true
  try {
    const start = dateRange.value?.[0] ? toDateStr(dateRange.value[0]) : undefined
    const end = dateRange.value?.[1] ? toDateStr(dateRange.value[1]) : undefined
    const dateParams =
      dateMode.value === 'delivery'
        ? { expected_delivery_date_start: start, expected_delivery_date_end: end }
        : { created_date_start: start, created_date_end: end }
    list.value = await listOrdersApi({
      status: status.value || undefined,
      order_no: orderNo.value?.trim() || undefined,
      ...dateParams,
    })
  } finally {
    loading.value = false
  }
}
// 看板 KPI 下钻：从路由 query 初始化筛选（status / view / range）
const applyRouteQuery = () => {
  const q = route.query
  dateMode.value = 'created'
  status.value = q.status ? String(q.status) : ''
  viewFilter.value = q.view ? String(q.view) : ''
  const now = new Date()
  if (q.range === 'all') {
    // 全时段下钻：不高亮任何 chip、不展开自定义框，由上下文条说明「全部时间」
    datePreset.value = ''
    dateRange.value = [new Date(2000, 0, 1), now]
  } else if (q.range === 'month') {
    datePreset.value = 'month'
    dateRange.value = [new Date(now.getFullYear(), now.getMonth(), 1), now]
  } else {
    datePreset.value = 'today'
    initToday()
  }
}
// 清除看板下钻上下文，恢复默认（今天 / 全部状态）
const clearContext = () => {
  status.value = ''
  viewFilter.value = ''
  datePreset.value = 'today'
  initToday()
  load()
}
onMounted(() => {
  applyRouteQuery()
  load()
})
watch(() => route.fullPath, () => {
  applyRouteQuery()
  load()
})
</script>

<template>
  <!-- ── Mobile ── -->
  <div v-if="isMobile" class="m-page">
    <div class="m-filter-bar">
      <el-input v-model="orderNo" placeholder="搜索订单号" clearable class="m-search-input" @keyup.enter="load" />
      <div class="m-dim-seg">
        <button class="m-dim-seg__btn" :class="{ 'is-active': dateMode === 'created' }" @click="setDateMode('created')">按下单</button>
        <button class="m-dim-seg__btn" :class="{ 'is-active': dateMode === 'delivery' }" @click="setDateMode('delivery')">按送达</button>
      </div>
      <div class="m-quick-chips">
        <button
          v-for="p in datePresets"
          :key="p.key"
          class="m-date-chip"
          :class="{ 'is-active': datePreset === p.key }"
          @click="applyPreset(p.key)"
        >{{ p.label }}</button>
      </div>
      <el-date-picker
        v-if="datePreset === 'custom'"
        v-model="dateRange"
        type="daterange"
        start-placeholder="开始"
        end-placeholder="结束"
        size="small"
        class="m-date-picker"
        style="width: 100%"
        @change="load"
      />
      <div class="m-status-tabs">
        <button
          class="m-status-tab"
          :class="{ 'is-active': !status }"
          @click="status = ''; load()"
        >全部</button>
        <button
          v-for="o in MAIN_ORDER_STATUS_OPTIONS"
          :key="o.value"
          class="m-status-tab"
          :class="{ 'is-active': status === o.value }"
          @click="status = o.value; load()"
        >{{ o.label }}</button>
      </div>
    </div>

    <div v-if="contextLabel" class="m-context-bar">
      <span class="material-symbols-outlined m-context-bar__ic">filter_alt</span>
      <span class="m-context-bar__text">仅看 <b>{{ contextLabel }}</b> · 全部时间</span>
      <button class="m-context-bar__clear" @click="clearContext">
        清除<span class="material-symbols-outlined">close</span>
      </button>
    </div>

    <div v-if="loading" class="m-loading-hint">加载中...</div>
    <div v-else-if="!filteredList.length" class="m-empty">暂无订单</div>
    <div v-else class="m-order-list">
      <div
        v-for="row in filteredList"
        :key="row.id"
        class="m-order-card"
        :style="{ '--status-color': orderStatusTagColor(row.status) }"
        @click="goDetail(row)"
      >
        <div class="m-order-card__status-bar" />
        <div class="m-order-card__body">
          <div class="m-order-card__top">
            <span class="m-order-card__title">
              <span class="material-symbols-outlined m-order-card__leaf">nutrition</span>
              {{ itemsSummary(row) }}
            </span>
            <span class="m-order-card__tag" :style="{ background: orderStatusTagColor(row.status) }">
              {{ orderStatusLabel(row.status) }}
            </span>
          </div>
          <div class="m-order-card__amount">¥{{ Number(row.total_amount || 0).toLocaleString() }}</div>
          <div class="m-order-card__meta">
            <span v-if="deliveryText(row)" class="m-order-card__deliver">
              <span class="material-symbols-outlined m-order-card__meta-ic">local_shipping</span>送达 {{ deliveryText(row) }}
            </span>
            <span class="m-order-card__no">{{ row.order_no }}</span>
          </div>
          <div v-if="row.receiving_difference?.difference_type === 'shortage'" class="m-order-card__diff m-order-card__diff--shortage">
            少收 {{ receivingDifferenceText(row.receiving_difference, 'shortage') }}
          </div>
          <div v-else-if="row.receiving_difference?.difference_type === 'overage'" class="m-order-card__diff m-order-card__diff--overage">
            多收 {{ receivingDifferenceText(row.receiving_difference, 'overage') }}
          </div>
        </div>
        <span class="material-symbols-outlined m-order-card__arrow">chevron_right</span>
      </div>
    </div>

    <button class="m-fab-btn" type="button" @click="router.push('/client/orders/new')">
      <span class="material-symbols-outlined">add</span>
      新建订单
    </button>
  </div>

  <!-- ── PC ── -->
  <template v-else>
  <el-card class="mb-3">
    <template #header>
      <div class="flex items-center justify-between">
        <span class="font-semibold">订单筛选</span>
      </div>
    </template>
    <div class="quick-filter">
      <span class="quick-filter__label">快捷筛选</span>
      <div class="quick-filter__group">
        <button
          type="button"
          class="quick-chip"
          :class="{ 'is-active': dateMode === 'created' }"
          @click="applyQuickFilter('created')"
        >
          今日下单
        </button>
        <button
          type="button"
          class="quick-chip"
          :class="{ 'is-active': dateMode === 'delivery' }"
          @click="applyQuickFilter('delivery')"
        >
          今日配送
        </button>
      </div>
    </div>
    <div class="crud-toolbar">
      <el-input v-model="orderNo" placeholder="订单号" clearable style="width: 180px" />
      <el-select v-model="status" style="width: 180px">
        <el-option value="" label="全部状态" />
        <el-option v-for="o in MAIN_ORDER_STATUS_OPTIONS" :key="o.value" :value="o.value" :label="o.label" />
      </el-select>
      <el-select v-model="differenceFilter" placeholder="收货差异" clearable style="width: 150px">
        <el-option value="" label="全部" />
        <el-option value="any" label="有差异" />
        <el-option value="shortage" label="少收退货" />
        <el-option value="overage" label="多收留痕" />
      </el-select>
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        :start-placeholder="dateMode === 'delivery' ? '配送开始日期' : '下单开始日期'"
        :end-placeholder="dateMode === 'delivery' ? '配送结束日期' : '下单结束日期'"
      />
      <el-button @click="load">筛选</el-button>
    </div>
  </el-card>
  <el-card>
    <el-table v-loading="loading" :data="filteredList" border class="clickable-rows" @row-click="goDetail">
      <el-table-column prop="order_no" label="订单号" min-width="160" />
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :color="orderStatusTagColor(row.status)" effect="dark">{{ orderStatusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="total_amount" label="金额" width="130">
        <template #default="{ row }">¥{{ Number(row.total_amount || 0).toLocaleString() }}</template>
      </el-table-column>
      <el-table-column label="收货差异" width="150">
        <template #default="{ row }">
          <el-tag v-if="row.receiving_difference?.difference_type === 'shortage'" type="danger" effect="plain">
            少收 {{ receivingDifferenceText(row.receiving_difference, 'shortage') }}
          </el-tag>
          <el-tag v-else-if="row.receiving_difference?.difference_type === 'overage'" type="success" effect="plain">
            多收 {{ receivingDifferenceText(row.receiving_difference, 'overage') }}
          </el-tag>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" min-width="180">
        <template #default="{ row }">{{ formatChinaDateTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click.stop="goDetail(row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
  </template>
</template>

<style scoped>
.clickable-rows :deep(.el-table__row) {
  cursor: pointer;
}
.quick-filter {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.quick-filter__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}
.quick-filter__group {
  display: inline-flex;
  gap: 8px;
  padding: 4px;
  background: var(--el-fill-color-light);
  border-radius: 10px;
}
.quick-chip {
  padding: 6px 18px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--el-text-color-regular);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}
.quick-chip:hover {
  color: var(--el-color-primary);
}
.quick-chip.is-active {
  background: var(--el-color-primary);
  color: #fff;
  box-shadow: 0 2px 8px rgba(64, 128, 255, 0.28);
}
.crud-toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

/* ── Mobile styles ── */
.m-page {
  font-family: var(--m-font-body);
  padding-bottom: 16px;
  position: relative;
  min-height: 100%;
}
.m-filter-bar {
  padding: 12px 16px;
  background: var(--m-surface-container-lowest);
  border-bottom: 1px solid var(--m-outline-variant);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.m-search-input { width: 100%; }
.m-status-tabs {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  padding-bottom: 2px;
}
.m-status-tabs::-webkit-scrollbar { display: none; }
.m-status-tab {
  flex: none;
  padding: 5px 14px;
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
.m-dim-seg {
  display: inline-flex;
  align-self: flex-start;
  padding: 3px;
  border-radius: 11px;
  background: var(--m-surface-container);
  gap: 2px;
}
.m-dim-seg__btn {
  padding: 5px 16px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--m-on-surface-variant);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s;
}
.m-dim-seg__btn.is-active {
  background: var(--m-surface-container-lowest);
  color: var(--m-primary);
  box-shadow: 0 1px 4px rgba(35, 39, 31, 0.12);
}
.m-quick-chips {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}
.m-quick-chips::-webkit-scrollbar { display: none; }
.m-date-chip { flex: none; }
.m-date-chip {
  padding: 4px 14px;
  border-radius: 16px;
  border: 1.5px solid var(--m-outline-variant);
  background: transparent;
  color: var(--m-on-surface-variant);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.18s;
}
.m-date-chip.is-active {
  background: var(--m-secondary-fixed);
  border-color: var(--m-secondary);
  color: var(--m-primary);
  font-weight: 700;
}
.m-order-list {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.m-order-card {
  position: relative;
  background: var(--m-surface-container-lowest);
  border: 1px solid var(--m-outline-variant);
  border-radius: 16px;
  display: flex;
  align-items: stretch;
  overflow: hidden;
  cursor: pointer;
  box-shadow: 0 2px 12px rgba(35, 39, 31, 0.06);
  transition: transform 0.14s ease, box-shadow 0.14s ease;
}
.m-order-card:active {
  transform: translateY(1px);
  box-shadow: 0 1px 6px rgba(35, 39, 31, 0.10);
}
.m-order-card__status-bar {
  width: 5px;
  background: linear-gradient(180deg, var(--status-color, #94a3b8), color-mix(in srgb, var(--status-color, #94a3b8) 72%, #ffffff 28%));
  flex: none;
}
.m-order-card__body {
  flex: 1;
  padding: 13px 12px;
  min-width: 0;
}
.m-order-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.m-order-card__title {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--m-on-surface);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-order-card__leaf {
  font-size: 17px;
  color: var(--m-primary);
  flex: none;
}
.m-order-card__tag {
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  padding: 2px 8px;
  border-radius: 8px;
  white-space: nowrap;
  flex: none;
}
.m-order-card__amount {
  font-family: var(--m-font-accent);
  font-size: 23px;
  font-weight: 600;
  color: var(--m-primary);
  letter-spacing: 0.3px;
  margin-bottom: 2px;
}
.m-order-card__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--m-on-surface-variant);
  min-width: 0;
}
.m-order-card__deliver {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-weight: 600;
  color: var(--m-on-surface-variant);
  flex: none;
}
.m-order-card__meta-ic {
  font-size: 15px;
  color: var(--m-primary);
}
.m-order-card__no {
  color: var(--m-outline);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-order-card__diff {
  margin-top: 4px;
  font-size: 12px;
  font-weight: 600;
}
.m-order-card__diff--shortage { color: var(--m-error); }
.m-order-card__diff--overage { color: #15803d; }
.m-order-card__arrow {
  color: var(--m-outline-variant);
  align-self: center;
  padding-right: 8px;
  font-size: 20px;
}
.m-loading-hint,
.m-empty {
  text-align: center;
  color: var(--m-on-surface-variant);
  padding: 48px 16px;
  font-size: 14px;
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
  box-shadow: 0 4px 16px rgba(31, 122, 83, 0.36);
  cursor: pointer;
  font-family: var(--m-font-body);
  z-index: 40;
}
.m-fab-btn .material-symbols-outlined {
  font-size: 20px;
}
.m-context-bar {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 12px 16px 0;
  padding: 9px 12px;
  border-radius: 12px;
  background: var(--m-accent-soft);
  border: 1px solid color-mix(in srgb, var(--m-accent) 35%, #ffffff 65%);
  color: #8a5212;
  font-size: 13px;
}
.m-context-bar__ic {
  font-size: 17px;
  color: var(--m-accent);
  flex: none;
}
.m-context-bar__text {
  flex: 1;
  min-width: 0;
}
.m-context-bar__text b {
  font-weight: 700;
}
.m-context-bar__clear {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  border: none;
  background: transparent;
  color: #8a5212;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  flex: none;
}
.m-context-bar__clear .material-symbols-outlined {
  font-size: 15px;
}
</style>
