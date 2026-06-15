<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { closeMonitorAlertApi, monitorAlertsApi } from '../../api/monitor'
import { formatChinaDateTime } from '../../utils/datetime'
import EventDetailView from '../../components/monitor/EventDetailView.vue'

const filterLevel = ref('')
const filterStatus = ref('')
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)
const closingId = ref(null)

const drawerVisible = ref(false)
const activeAlert = ref(null)

const levelLabel = (v) => ({ high: '高危', medium: '中危', low: '低危' }[v] || v)
const typeLabel = (v) => ({
  delivery_overdue: '配送超时',
  sensor: '传感器异常',
  quality_missing: '质检缺失',
  shortage: '短收异常',
  bill_discrepancy: '账单差异',
}[v] || v)

// —— 筛选选项（仅用于渲染分段控件，绑定关系与原 select 完全一致）——
const levelOptions = [
  { value: '', label: '全部' },
  { value: 'high', label: '高危' },
  { value: 'medium', label: '中危' },
  { value: 'low', label: '低危' },
]
const statusOptions = [
  { value: '', label: '全部' },
  { value: 'open', label: '待处理' },
  { value: 'closed', label: '已关闭' },
]
const setLevel = (v) => { filterLevel.value = v; onFilter() }
const setStatus = (v) => { filterStatus.value = v; onFilter() }

const load = async () => {
  loading.value = true
  try {
    const res = await monitorAlertsApi({
      level: filterLevel.value || undefined,
      status: filterStatus.value || undefined,
      page: page.value,
      page_size: pageSize,
    })
    list.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

const onFilter = () => { page.value = 1; load() }

const closeAlert = async (row) => {
  closingId.value = row.id
  try {
    await closeMonitorAlertApi(row.id)
    if (activeAlert.value?.id === row.id) activeAlert.value = { ...activeAlert.value, status: 'closed' }
    await load()
  } finally {
    closingId.value = null
  }
}

const openDetail = (row) => {
  activeAlert.value = row
  drawerVisible.value = true
}

// —— 富详情映射 ——
const toneByLevel = (lvl) => ({ high: 'danger', medium: 'warn', low: 'default' }[lvl] || 'default')

const detailHeader = computed(() => {
  const a = activeAlert.value || {}
  return {
    title: a.payload_json?.order_no || `预警 #${a.id}`,
    badge: a.type_label || typeLabel(a.type),
    badgeTone: toneByLevel(a.level),
    status: a.status_label || (a.status === 'closed' ? '已关闭' : '待处理'),
  }
})
const detailSubjects = computed(() => {
  const a = activeAlert.value || {}
  return [
    { label: '配送商', value: a.delivery_name },
    { label: '客户', value: a.client_name },
    { label: '食堂', value: a.canteen_name },
  ].filter((s) => s.value)
})
const detailMetrics = computed(() => {
  const a = activeAlert.value || {}
  const facts = Array.isArray(a.facts) ? a.facts.slice() : []
  facts.push({ label: '级别', value: a.level_label || levelLabel(a.level) })
  facts.push({ label: '发生时间', value: formatChinaDateTime(a.created_at) })
  return facts
})
const detailTexts = computed(() => {
  const a = activeAlert.value || {}
  return a.description ? [{ label: '描述', value: a.description }] : []
})

watch(page, load)
onMounted(load)
</script>

<template>
  <div class="alt-wrap">
    <header class="alt-header">
      <div class="alt-title-block">
        <p class="alt-eyebrow">MONITOR · ALERT MANAGEMENT</p>
        <h1>预警中心</h1>
        <span class="alt-live"><i class="alt-live-dot" />实时监控中</span>
      </div>
      <div class="alt-total">
        <span class="alt-total-num">{{ total }}</span>
        <span class="alt-total-label">条告警</span>
      </div>
    </header>

    <div class="alt-filter glass-card">
      <div class="alt-filter-group">
        <label>级别</label>
        <div class="seg">
          <button
            v-for="opt in levelOptions"
            :key="`lv-${opt.value}`"
            type="button"
            class="seg-btn"
            :class="[{ active: filterLevel === opt.value }, opt.value ? `seg-${opt.value}` : '']"
            @click="setLevel(opt.value)"
          >{{ opt.label }}</button>
        </div>
      </div>
      <div class="alt-filter-divider" />
      <div class="alt-filter-group">
        <label>状态</label>
        <div class="seg">
          <button
            v-for="opt in statusOptions"
            :key="`st-${opt.value}`"
            type="button"
            class="seg-btn"
            :class="{ active: filterStatus === opt.value }"
            @click="setStatus(opt.value)"
          >{{ opt.label }}</button>
        </div>
      </div>
      <button type="button" class="alt-refresh" :disabled="loading" @click="onFilter" title="刷新">
        <span class="alt-refresh-ico" :class="{ spin: loading }">⟳</span>
      </button>
    </div>

    <div class="alt-table-wrap glass-card" v-loading="loading" element-loading-background="rgba(5,10,20,.72)">
      <table class="alt-table">
        <thead>
          <tr>
            <th style="width:68px">编号</th>
            <th style="width:84px">级别</th>
            <th style="width:110px">类型</th>
            <th>描述</th>
            <th style="width:130px">配送商</th>
            <th style="width:140px">客户 / 食堂</th>
            <th style="width:90px">状态</th>
            <th style="width:104px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!loading && !list.length">
            <td colspan="8" class="empty-row">
              <span class="empty-ico">✓</span>
              <span class="empty-text">暂无告警 · 一切正常</span>
            </td>
          </tr>
          <tr
            v-for="(row, i) in list"
            :key="row.id"
            :class="`row-${row.level}`"
            class="data-row"
            :style="{ animationDelay: `${Math.min(i, 20) * 28}ms` }"
            @click="openDetail(row)"
          >
            <td class="mono">{{ row.id }}</td>
            <td>
              <span class="badge" :class="`badge-${row.level}`">
                <i class="badge-dot" />{{ levelLabel(row.level) }}
              </span>
            </td>
            <td class="type-cell">{{ row.type_label || typeLabel(row.type) }}</td>
            <td class="desc-cell">{{ row.description }}</td>
            <td class="dim-cell">{{ row.delivery_name || '—' }}</td>
            <td class="dim-cell">{{ row.client_name ? `${row.client_name}${row.canteen_name ? `(${row.canteen_name})` : ''}` : (row.canteen_name || '—') }}</td>
            <td>
              <span class="badge" :class="row.status === 'closed' ? 'badge-closed' : 'badge-open'">
                <i class="badge-dot" />{{ row.status === 'closed' ? '已关闭' : '待处理' }}
              </span>
            </td>
            <td @click.stop>
              <button
                v-if="row.status !== 'closed'"
                class="close-btn"
                :disabled="closingId === row.id"
                @click="closeAlert(row)"
              >{{ closingId === row.id ? '处理中…' : '关闭' }}</button>
              <span v-else class="done-text">已处置</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="alt-pagination" v-if="total > pageSize">
      <button type="button" :disabled="page <= 1" @click="page--">上一页</button>
      <span>第 {{ page }} 页 · 共 {{ Math.ceil(total / pageSize) }} 页</span>
      <button type="button" :disabled="page >= Math.ceil(total / pageSize)" @click="page++">下一页</button>
    </div>

    <!-- 详情抽屉 -->
    <div v-if="drawerVisible" class="drawer-mask" @click.self="drawerVisible = false">
      <aside class="drawer-panel glass-card" v-if="activeAlert">
        <header class="drawer-head">
          <div>
            <p class="alt-eyebrow">ALERT DETAIL</p>
            <h2>告警详情 #{{ activeAlert.id }}</h2>
          </div>
          <button class="drawer-close" @click="drawerVisible = false">✕</button>
        </header>

        <div class="drawer-body">
          <EventDetailView
            :header="detailHeader"
            :subjects="detailSubjects"
            :metrics="detailMetrics"
            :texts="detailTexts"
          >
            <button
              v-if="activeAlert.status !== 'closed'"
              class="close-btn-lg"
              :disabled="closingId === activeAlert.id"
              @click="closeAlert(activeAlert)"
            >
              {{ closingId === activeAlert.id ? '处理中…' : '关闭此告警' }}
            </button>
            <p v-else class="done-text-lg">此告警已处置</p>
          </EventDetailView>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.alt-wrap {
  color: #dfe2f3;
  font-family: "Space Grotesk", Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
}

.alt-eyebrow {
  font: 600 11px/1 "JetBrains Mono", monospace;
  letter-spacing: .12em;
  color: rgba(0, 229, 255, .55);
  margin: 0 0 8px;
  text-transform: uppercase;
}

.alt-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 22px;
}

.alt-title-block { position: relative; }

.alt-header h1 {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -.01em;
  color: #e8f0ff;
  margin: 0;
  display: inline-block;
  background: linear-gradient(120deg, #eaf6ff 0%, #8fe9ff 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.alt-live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: 14px;
  vertical-align: middle;
  padding: 3px 10px 3px 8px;
  border-radius: 999px;
  border: 1px solid rgba(104, 250, 221, .28);
  background: rgba(104, 250, 221, .07);
  font-size: 11px;
  font-weight: 600;
  color: #68fadd;
  transform: translateY(-3px);
}

.alt-live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #5ef0c8;
  box-shadow: 0 0 0 0 rgba(94, 240, 200, .6);
  animation: livePulse 1.8s ease-out infinite;
}

@keyframes livePulse {
  0% { box-shadow: 0 0 0 0 rgba(94, 240, 200, .55); }
  70% { box-shadow: 0 0 0 6px rgba(94, 240, 200, 0); }
  100% { box-shadow: 0 0 0 0 rgba(94, 240, 200, 0); }
}

.alt-total {
  display: flex;
  align-items: baseline;
  gap: 7px;
  padding: 8px 16px;
  border-radius: 12px;
  border: 1px solid rgba(0, 229, 255, .18);
  background: linear-gradient(135deg, rgba(0, 229, 255, .1), rgba(5, 14, 26, .4));
}
.alt-total-num {
  font: 800 24px/1 "Space Grotesk", monospace;
  color: #00e5ff;
  text-shadow: 0 0 16px rgba(0, 229, 255, .35);
}
.alt-total-label { color: #8090a0; font-size: 13px; }

/* —— 分段筛选器 —— */
.alt-filter {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 16px;
  padding: 12px 16px;
}

.alt-filter-group { display: flex; align-items: center; gap: 10px; }
.alt-filter-group > label {
  font: 600 11px/1 "JetBrains Mono", monospace;
  letter-spacing: .08em;
  color: rgba(186, 201, 204, .5);
  text-transform: uppercase;
}

.alt-filter-divider {
  width: 1px;
  height: 22px;
  background: rgba(0, 229, 255, .14);
}

.seg {
  display: inline-flex;
  padding: 3px;
  gap: 2px;
  border-radius: 9px;
  background: rgba(0, 0, 0, .28);
  border: 1px solid rgba(0, 229, 255, .1);
}

.seg-btn {
  height: 28px;
  padding: 0 13px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: rgba(186, 201, 204, .7);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all .16s ease;
  white-space: nowrap;
}
.seg-btn:hover { color: #dfe9f5; background: rgba(255, 255, 255, .05); }
.seg-btn.active {
  background: rgba(0, 229, 255, .16);
  color: #00e5ff;
  box-shadow: inset 0 0 0 1px rgba(0, 229, 255, .3);
}
.seg-btn.seg-high.active { background: rgba(255, 75, 95, .16); color: #ff7d8b; box-shadow: inset 0 0 0 1px rgba(255, 75, 95, .35); }
.seg-btn.seg-medium.active { background: rgba(255, 180, 0, .15); color: #ffcc44; box-shadow: inset 0 0 0 1px rgba(255, 180, 0, .32); }
.seg-btn.seg-low.active { background: rgba(100, 200, 255, .14); color: #8ad6f5; box-shadow: inset 0 0 0 1px rgba(100, 200, 255, .3); }

.alt-refresh {
  margin-left: auto;
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(0, 229, 255, .25);
  border-radius: 9px;
  background: rgba(0, 229, 255, .06);
  color: #00e5ff;
  cursor: pointer;
  transition: background .15s;
}
.alt-refresh:hover:not(:disabled) { background: rgba(0, 229, 255, .16); }
.alt-refresh:disabled { opacity: .6; cursor: progress; }
.alt-refresh-ico { font-size: 17px; line-height: 1; display: inline-block; }
.alt-refresh-ico.spin { animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.glass-card {
  border: 1px solid rgba(0, 229, 255, .14);
  border-radius: 12px;
  background: rgba(10, 14, 26, .72);
  backdrop-filter: blur(12px);
}

.alt-table-wrap {
  overflow-x: auto;
  box-shadow: 0 18px 50px -28px rgba(0, 0, 0, .8);
}

.alt-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.alt-table thead th {
  position: sticky;
  top: 0;
  z-index: 3;
}

.alt-table th {
  padding: 13px 14px;
  text-align: left;
  font: 600 11px/1 "JetBrains Mono", monospace;
  letter-spacing: .08em;
  color: rgba(186, 201, 204, .62);
  background:
    linear-gradient(rgba(8, 14, 26, .96), rgba(8, 14, 26, .96)),
    repeating-linear-gradient(90deg, rgba(0, 229, 255, .05) 0 1px, transparent 1px 7px);
  border-bottom: 1px solid rgba(0, 229, 255, .18);
  white-space: nowrap;
  text-transform: uppercase;
  backdrop-filter: blur(8px);
}
.alt-table th:first-child { border-top-left-radius: 12px; }
.alt-table th:last-child { border-top-right-radius: 12px; }

.alt-table td {
  padding: 12px 14px;
  border-bottom: 1px solid rgba(132, 147, 150, .07);
  vertical-align: middle;
  color: #bac9cc;
}

.data-row {
  cursor: pointer;
  transition: background .14s, box-shadow .14s;
  animation: rowIn .34s cubic-bezier(.22, .61, .36, 1) both;
}
@keyframes rowIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
.data-row:hover td { background: rgba(0, 229, 255, .05); }
.data-row:hover td:first-child { box-shadow: inset 3px 0 0 rgba(0, 229, 255, .5); }

/* 左侧严重度色条 */
.data-row td:first-child { position: relative; }
.data-row td:first-child::before {
  content: '';
  position: absolute;
  left: 0; top: 4px; bottom: 4px;
  width: 3px;
  border-radius: 0 3px 3px 0;
}
.row-high td:first-child::before { background: linear-gradient(rgba(255,75,95,.9), rgba(255,75,95,.4)); box-shadow: 0 0 10px rgba(255,75,95,.5); }
.row-medium td:first-child::before { background: linear-gradient(rgba(255,180,0,.85), rgba(255,180,0,.35)); }
.row-low td:first-child::before { background: rgba(100,200,255,.45); }

.desc-cell { max-width: 320px; line-height: 1.5; color: #d0d8e8; }
.type-cell { white-space: nowrap; }
.dim-cell { color: rgba(186, 201, 204, .65); font-size: 12px; }
.mono { font-family: "JetBrains Mono", monospace; color: rgba(186, 201, 204, .5); font-size: 12px; }

.badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.badge-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }

.badge-high { background: rgba(255, 75, 95, .16); color: #ff6b7a; border: 1px solid rgba(255, 75, 95, .35); }
.badge-medium { background: rgba(255, 180, 0, .13); color: #ffcc44; border: 1px solid rgba(255, 180, 0, .3); }
.badge-low { background: rgba(100, 200, 255, .12); color: #7dd0f0; border: 1px solid rgba(100, 200, 255, .25); }
.badge-open { background: rgba(255, 100, 80, .12); color: #ff8070; border: 1px solid rgba(255, 100, 80, .25); }
.badge-closed { background: rgba(104, 250, 221, .1); color: #68fadd; border: 1px solid rgba(104, 250, 221, .25); }

.close-btn {
  height: 28px;
  padding: 0 12px;
  border: 1px solid rgba(104, 250, 221, .35);
  border-radius: 7px;
  background: rgba(104, 250, 221, .08);
  color: #68fadd;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: all .15s;
}
.close-btn:hover:not(:disabled) { background: rgba(104, 250, 221, .2); box-shadow: 0 0 14px -2px rgba(104, 250, 221, .4); }
.close-btn:disabled { opacity: .5; cursor: not-allowed; }

.done-text { font-size: 12px; color: rgba(186, 201, 204, .35); }

.empty-row {
  text-align: center;
  padding: 56px 0;
  color: rgba(186, 201, 204, .4);
}
.empty-ico {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  margin: 0 auto 12px;
  border-radius: 50%;
  border: 1px solid rgba(104, 250, 221, .3);
  background: rgba(104, 250, 221, .07);
  color: #68fadd;
  font-size: 20px;
}
.empty-text { font-size: 13px; }

.alt-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 16px;
  color: #8090a0;
  font-size: 13px;
}

.alt-pagination button {
  height: 30px;
  padding: 0 14px;
  border: 1px solid rgba(0, 229, 255, .25);
  border-radius: 5px;
  background: rgba(0, 229, 255, .06);
  color: #9cf0ff;
  font-size: 12px;
  cursor: pointer;
}

.alt-pagination button:disabled { opacity: .35; cursor: not-allowed; }

/* 抽屉 */
.drawer-mask {
  position: fixed;
  inset: 0;
  background: rgba(2, 6, 14, .58);
  backdrop-filter: blur(3px);
  z-index: 2000;
  display: flex;
  justify-content: flex-end;
  animation: maskIn .2s ease both;
}
@keyframes maskIn { from { opacity: 0; } to { opacity: 1; } }

.drawer-panel {
  width: 440px;
  max-width: 92vw;
  height: 100%;
  overflow-y: auto;
  border-radius: 0;
  border-right: none;
  border-top: none;
  border-bottom: none;
  border-left: 1px solid rgba(0, 229, 255, .22);
  padding: 28px 24px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 0;
  box-shadow: -24px 0 60px -24px rgba(0, 0, 0, .9);
  animation: drawerIn .28s cubic-bezier(.22, .61, .36, 1) both;
}
@keyframes drawerIn {
  from { transform: translateX(28px); opacity: .4; }
  to { transform: translateX(0); opacity: 1; }
}

.drawer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 24px;
}

.drawer-head h2 {
  font-size: 18px;
  font-weight: 700;
  color: #e8f0ff;
  margin: 0;
}

.drawer-close {
  width: 30px;
  height: 30px;
  border: 1px solid rgba(0, 229, 255, .25);
  border-radius: 6px;
  background: transparent;
  color: #8090a0;
  font-size: 14px;
  cursor: pointer;
  line-height: 1;
}

.drawer-close:hover { color: #00e5ff; border-color: rgba(0, 229, 255, .5); }

.drawer-body { display: flex; flex-direction: column; gap: 0; }

.detail-row {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 8px;
  padding: 10px 0;
  align-items: start;
}

.detail-row label {
  font: 600 11px/1.6 "JetBrains Mono", monospace;
  letter-spacing: .06em;
  color: rgba(186, 201, 204, .5);
  text-transform: uppercase;
}

.detail-row span { font-size: 13px; color: #d0d8e8; line-height: 1.5; }

.desc-full { line-height: 1.6; }

.detail-divider {
  height: 1px;
  background: rgba(0, 229, 255, .1);
  margin: 10px 0;
}

.detail-section-label {
  font: 600 11px/1 "JetBrains Mono", monospace;
  letter-spacing: .08em;
  color: rgba(186, 201, 204, .4);
  text-transform: uppercase;
  margin: 0 0 10px;
}

.payload-grid {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 6px 12px;
  padding: 12px;
  border-radius: 8px;
  background: rgba(0, 0, 0, .3);
  border: 1px solid rgba(0, 229, 255, .08);
  font: 12px/1.5 "JetBrains Mono", monospace;
}

.payload-key { color: rgba(0, 229, 255, .6); }
.payload-val { color: #b0c0cc; word-break: break-all; }

.close-btn-lg {
  width: 100%;
  height: 40px;
  margin-top: 8px;
  border: 1px solid rgba(104, 250, 221, .4);
  border-radius: 8px;
  background: rgba(104, 250, 221, .1);
  color: #68fadd;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background .15s;
}

.close-btn-lg:hover:not(:disabled) { background: rgba(104, 250, 221, .2); }
.close-btn-lg:disabled { opacity: .5; cursor: not-allowed; }

.done-text-lg {
  text-align: center;
  padding: 14px 0;
  color: rgba(104, 250, 221, .5);
  font-size: 13px;
}
</style>
