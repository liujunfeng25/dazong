<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import * as XLSX from 'xlsx'
import * as echarts from 'echarts'
import { streamChat, exportChatReport } from '../../api/chat'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const renderMd = (text) => DOMPurify.sanitize(md.render(String(text || '')))

const sessionId = `chat-${Date.now()}`
const input = ref('')
const questionMode = ref('auto')
const QUESTION_MODES = [
  { value: 'auto', label: '自动识别' },
  { value: 'national_price', label: '全国农产品价格' },
  { value: 'system_data', label: '业务系统数据' },
  { value: 'how_to', label: '操作手册' },
  { value: 'report', label: '监管报告' },
]
const sending = ref(false)
const listRef = ref(null)
const showDebug = ref(false)
const DEBUG_KEY = 'dz_ai_show_debug'

const EXAMPLE_CHIPS = [
  '生成今日监管日报',
  '生成昨日监管日报',
  '今天一级分类饼图',
  '稽核链路怎么查',
  '大白菜明天多少钱',
  '今天开放告警有几条',
  '演示账号是什么',
]

try {
  showDebug.value = localStorage.getItem(DEBUG_KEY) === '1'
} catch { /* ignore */ }

const onDebugKey = (e) => {
  if (e.altKey) {
    showDebug.value = !showDebug.value
    try { localStorage.setItem(DEBUG_KEY, showDebug.value ? '1' : '0') } catch { /* ignore */ }
  }
}
if (typeof window !== 'undefined') {
  window.addEventListener('keydown', onDebugKey)
}

// 每条消息：{ role, text(markdown), card, report, sql, debug, id }
const messages = ref([
  { role: 'ai', text: '你好，我是监管端 AI 分析助手。点击下方示例可快速提问；操作类问题会附带**参考来源**（操作手册）。', id: 'sys-0' },
])

const scrollBottom = () => nextTick(() => { const el = listRef.value; if (el) el.scrollTop = el.scrollHeight })

const cardColumns = (card) => {
  if (!card) return []
  if (card.columns?.length) return card.columns.map((c) => ({ key: c.key, label: c.label || c.key }))
  const first = card.rows?.[0]
  return first ? Object.keys(first).map((k) => ({ key: k, label: k })) : []
}

const buildCard = (data) => {
  const raw = data?.data_card
  if (!raw) return null
  if (raw.rows?.length || raw.report_content) return raw
  return null
}

const messageCitations = (m) => {
  if (m.card?.citations?.length) return m.card.citations
  const chunks = m.debug?.rag_chunks || []
  return chunks.map((c) => ({
    doc: c.doc || c.doc_title,
    section: c.section,
    path: c.path || c.source_path || '',
  }))
}

const citationPath = (c) => {
  const doc = c.doc || '操作手册'
  const sec = c.section ? ` · ${c.section}` : ''
  return c.path || `docs/操作手册/${doc}${sec}`
}

const copyCitation = async (c) => {
  const text = citationPath(c)
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制手册路径')
  } catch {
    ElMessage.info(text)
  }
}

const sendExample = (q) => {
  if (sending.value) return
  input.value = q
  send()
}

const finalizeAiMessage = (data) => ({
  role: 'ai',
  text: data.reply || '已完成分析。',
  card: buildCard(data),
  report: data.report_content || data.data_card?.report_content || '',
  reportOpen: !!(data.report_content || data.data_card?.report_content) && ((data.debug || {}).intent === 'report'),
  exportTitle: data.data_card?.title || '',
  sql: data.data_card?.sql || (data.debug?.tool_calls || []).map((t) => t.sql).filter(Boolean).slice(-1)[0] || '',
  debug: data.debug || {},
  pending: false,
})

const send = async () => {
  const text = input.value.trim()
  if (!text || sending.value) return
  input.value = ''
  messages.value.push({ role: 'user', text, id: `u-${Date.now()}` })
  const placeholder = {
    role: 'ai',
    text: '正在调用监管工具分析…',
    pending: true,
    trainingPct: null,
    id: `p-${Date.now()}`,
  }
  messages.value.push(placeholder)
  scrollBottom()
  sending.value = true
  let streamText = ''
  try {
    const history = messages.value
      .filter((m) => !m.pending && m.id !== 'sys-0')
      .map((m) => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.text }))
    let donePayload = null
    await streamChat(
      { message: text, messages: history, session_id: sessionId, question_mode: questionMode.value },
      {
        phase: (d) => {
          const idx = messages.value.indexOf(placeholder)
          if (idx >= 0) messages.value[idx].text = d.message || '正在分析…'
        },
        training_phase: (d) => {
          const idx = messages.value.indexOf(placeholder)
          if (idx < 0) return
          const pct = Number(d.progress_pct ?? 0)
          const label = d.phase_label || d.message || '正在训练全国价格预测…'
          messages.value[idx].trainingPct = Number.isFinite(pct) ? Math.max(0, Math.min(100, pct)) : null
          messages.value[idx].text = `${label}${messages.value[idx].trainingPct != null ? `（${messages.value[idx].trainingPct}%）` : ''}`
          scrollBottom()
        },
        delta: (d) => {
          streamText += d.text || ''
          const idx = messages.value.indexOf(placeholder)
          if (idx >= 0) messages.value[idx].text = streamText || '正在生成回答…'
          scrollBottom()
        },
        done: (d) => { donePayload = d },
      },
    )
    const idx = messages.value.indexOf(placeholder)
    const msg = { ...finalizeAiMessage(donePayload || { reply: streamText || '已完成分析。' }), id: `a-${Date.now()}` }
    if (idx >= 0) messages.value.splice(idx, 1, msg)
  } catch (e) {
    const idx = messages.value.indexOf(placeholder)
    const msg = { role: 'ai', text: `AI 调用失败：${e?.response?.data?.detail || e?.message || '未知错误'}`, id: `e-${Date.now()}` }
    if (idx >= 0) messages.value.splice(idx, 1, msg)
  } finally {
    sending.value = false
    scrollBottom()
    nextTick(() => renderCharts())
  }
}

const onKeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }

// ---- 图表：trend/rank/时序卡片自动出图 ----
const chartEls = ref({})
const setChartEl = (id, el) => { if (el) chartEls.value[id] = el }
const isChartable = (card) => {
  if (!card || !card.rows?.length) return false
  if (String(card.chart_type || '').toLowerCase() === 'pie') return card.rows.length >= 1
  return ['trend', 'rank', 'xinfadi_price', 'national_price'].includes(card.type) && card.rows.length >= 2
}
const CHART_VALUE_KEYS = ['price', 'yhat', 'avg_price', 'value', 'amount', 'gmv', 'total', 'qty', 'count']
const CHART_SKIP_KEYS = new Set(['rank', 'index', 'id', 'row', 'seq', 'no', 'trend', 'confidence', 'bar'])
const looksLikeDate = (v) => /^\d{4}-\d{2}-\d{2}/.test(String(v ?? '').trim())
const parseChartNumber = (v) => {
  if (v == null || v === '') return null
  if (typeof v === 'number' && Number.isFinite(v)) return v
  const s = String(v).trim()
  if (looksLikeDate(s)) return null
  const n = Number(s.replace(/[^\d.-]/g, ''))
  return Number.isFinite(n) ? n : null
}
const pickChartLabelCol = (cols, rows) => {
  const dateCol = cols.find((c) => ['date', 'name', 'day', 'label'].includes(c.key))
  if (dateCol) return dateCol
  return cols.find((c) => rows.every((r) => looksLikeDate(r[c.key]))) || cols[0]
}
const pickChartValueCol = (cols, rows) => {
  for (const key of CHART_VALUE_KEYS) {
    const col = cols.find((c) => c.key === key)
    if (col && rows.every((r) => parseChartNumber(r[col.key]) != null)) return col
  }
  return cols.find((c) => !CHART_SKIP_KEYS.has(c.key) && rows.every((r) => parseChartNumber(r[c.key]) != null))
}
const chartHasValues = (card) => {
  const cols = cardColumns(card)
  const labelCol = pickChartLabelCol(cols, card.rows)
  const valueCol = pickChartValueCol(cols, card.rows)
  return !!(labelCol?.key && valueCol?.key)
}
const PIE_COLORS = ['#00e5ff', '#4dd0e1', '#26a69a', '#80cbc4', '#b2dfdb', '#0097a7', '#006064']
const collapsePieSeries = (labels, values, topN = 5) => {
  const pairs = labels.map((name, i) => ({ name, value: values[i] ?? 0 }))
  if (pairs.length <= topN + 1) return pairs
  const sorted = [...pairs].sort((a, b) => b.value - a.value)
  const top = sorted.slice(0, topN)
  const otherVal = sorted.slice(topN).reduce((s, p) => s + p.value, 0)
  return [...top, { name: '其他', value: Math.round(otherVal * 100) / 100 }]
}
const resolveChartKind = (card) => {
  const hint = String(card?.chart_type || '').toLowerCase()
  if (hint === 'pie') return 'pie'
  if (hint === 'line') return 'line'
  if (card?.type === 'trend') return 'line'
  return 'bar'
}
const renderCharts = () => {
  messages.value.forEach((m) => {
    if (!m.card || !isChartable(m.card)) return
    const el = chartEls.value[m.id]
    if (!el) return
    const cols = cardColumns(m.card)
    const labelCol = pickChartLabelCol(cols, m.card.rows)
    const valueCol = pickChartValueCol(cols, m.card.rows)
    if (!labelCol?.key || !valueCol?.key) return
    const inst = echarts.getInstanceByDom(el) || echarts.init(el)
    const labels = m.card.rows.map((r) => String(r[labelCol.key]))
    const values = m.card.rows.map((r) => parseChartNumber(r[valueCol.key]) ?? 0)
    const kind = resolveChartKind(m.card)
    if (kind === 'pie') {
      const pieData = collapsePieSeries(labels, values)
      inst.setOption({
        color: PIE_COLORS,
        tooltip: { trigger: 'item', formatter: '{b}<br/>{c} ({d}%)' },
        legend: { type: 'scroll', bottom: 0, textStyle: { color: '#9cf0ff', fontSize: 10 } },
        series: [{
          type: 'pie',
          radius: ['36%', '62%'],
          center: ['50%', '46%'],
          data: pieData,
          label: { color: '#cfe7ee', fontSize: 10 },
          labelLine: { lineStyle: { color: 'rgba(156,240,255,.45)' } },
        }],
      })
    } else {
      inst.setOption({
        grid: { left: 48, right: 16, top: 24, bottom: 48 },
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: labels, axisLabel: { color: '#9cf0ff', rotate: labels.length > 6 ? 30 : 0, fontSize: 10 } },
        yAxis: { type: 'value', axisLabel: { color: '#9cf0ff', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(0,229,255,.12)' } } },
        series: [{ type: kind === 'line' ? 'line' : 'bar', data: values, itemStyle: { color: '#00e5ff' }, smooth: true }],
      })
    }
    inst.resize()
  })
}

// ---- 导出 ----
const downloadBlob = (blob, name) => {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = name; a.click()
  URL.revokeObjectURL(url)
}
const exportClient = (msg, type) => {
  const cols = cardColumns(msg.card)
  const aoa = [cols.map((c) => c.label), ...msg.card.rows.map((r) => cols.map((c) => r[c.key]))]
  const ws = XLSX.utils.aoa_to_sheet(aoa)
  const title = msg.card.title || '查询结果'
  if (type === 'csv') {
    downloadBlob(new Blob(['﻿' + XLSX.utils.sheet_to_csv(ws)], { type: 'text/csv;charset=utf-8;' }), `${title}.csv`)
  } else {
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, '数据')
    const out = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
    downloadBlob(new Blob([out], { type: 'application/octet-stream' }), `${title}.xlsx`)
  }
}
const reportTitleFromMarkdown = (md) => {
  const line = String(md || '').split('\n').find((l) => /^#\s+/.test(l.trim()))
  return line ? line.trim().replace(/^#+\s*/, '') : ''
}
const exportServer = async (msg, format) => {
  try {
    const title = msg.exportTitle || msg.card?.title || reportTitleFromMarkdown(msg.report) || '监管分析报告'
    const markdown = [msg.report, msg.text].filter(Boolean).join('\n\n') || '暂无报告内容。'
    const payload = { title, markdown, format, columns: msg.card?.columns || [], rows: msg.card?.rows || [] }
    const res = await exportChatReport(payload)
    downloadBlob(res, `${title}.${format}`)
  } catch (e) {
    ElMessage.error('导出失败：' + (e?.message || '未知错误'))
  }
}
const handleExport = (msg, cmd) => {
  if (cmd === 'csv' || cmd === 'xlsx') return exportClient(msg, cmd)
  return exportServer(msg, cmd)
}
const canExportTable = (msg) => !!msg.card?.rows?.length
const canExportDoc = (msg) => !!(msg.report && String(msg.report).trim())

onMounted(() => scrollBottom())
onBeforeUnmount(() => {
  if (typeof window !== 'undefined') window.removeEventListener('keydown', onDebugKey)
})
</script>

<template>
  <section class="ai-panel">
    <div v-if="messages.length <= 2" class="ai-mission">
      <div class="ai-mission__signal"><span></span><i></i><b></b></div>
      <div>
        <p>INTELLIGENCE MISSION CONTROL</p>
        <h2>今天需要分析什么？</h2>
        <span>连接监管数据、业务系统与操作手册，结果附带可追溯依据。</span>
      </div>
    </div>

    <div ref="listRef" class="ai-list">
      <div v-for="m in messages" :key="m.id" class="ai-row" :class="m.role === 'user' ? 'is-user' : 'is-ai'">
        <span class="ai-timeline-node" :class="{ pending: m.pending }">{{ m.role === 'user' ? 'CMD' : 'AI' }}</span>
        <div class="ai-bubble" :class="m.role === 'user' ? 'b-user' : 'b-ai'">
          <div v-if="m.pending" class="ai-pending">
            {{ m.text }}<span class="dots" />
            <div v-if="m.trainingPct != null" class="ai-train-bar">
              <div class="ai-train-bar__fill" :style="{ width: `${m.trainingPct}%` }" />
            </div>
          </div>
          <div v-else class="ai-md" v-html="renderMd(m.text)" />

          <!-- 数据卡片：全列表格 -->
          <div v-if="m.card && m.card.rows && m.card.rows.length" class="ai-card">
            <div class="ai-card__bar">
              <span>{{ m.card.title || '数据卡片' }}</span>
              <span class="ai-card__count" v-if="m.card.row_count != null">{{ m.card.row_count }} 行</span>
            </div>
            <div v-if="isChartable(m.card) && chartHasValues(m.card)" class="ai-chart" :ref="(el) => setChartEl(m.id, el)" />
            <div v-else-if="m.card?.chart_type === 'pie' || isChartable(m.card)" class="ai-chart-empty">暂无足够数据绘制图表</div>
            <details class="ai-data-details">
              <summary>查看明细数据 · {{ m.card.rows.length }} 行</summary>
              <div class="ai-table-wrap">
                <el-table :data="m.card.rows" size="small" max-height="320" class="ai-table">
                  <el-table-column v-for="c in cardColumns(m.card)" :key="c.key" :prop="c.key" :label="c.label" min-width="120" show-overflow-tooltip />
                </el-table>
              </div>
            </details>
          </div>

          <!-- 报表 markdown 全文渲染 -->
          <details v-if="m.report" class="ai-report" :open="m.reportOpen !== false">
            <summary>报表全文（点击展开）</summary>
            <div class="ai-md" v-html="renderMd(m.report)" />
          </details>

          <!-- 手册引用 -->
          <details v-if="messageCitations(m).length" class="ai-citations" open>
            <summary class="ai-citations__title">参考来源（{{ messageCitations(m).length }}）</summary>
            <div v-for="(c, ci) in messageCitations(m)" :key="ci" class="ai-cite-card">
              <div class="ai-cite-card__head">{{ c.doc }}<span v-if="c.section"> · {{ c.section }}</span></div>
              <button type="button" class="ai-cite-card__copy" @click="copyCitation(c)">复制路径</button>
            </div>
          </details>

          <!-- 调试信息（Alt 切换或曾开启） -->
          <details v-if="showDebug && m.debug && Object.keys(m.debug).length" class="ai-debug">
            <summary>调试信息</summary>
            <div v-if="m.debug.route" class="ai-debug__meta">route: {{ m.debug.route }} · synthesis: {{ m.debug.synthesis ? 'yes' : 'no' }}</div>
            <div v-if="m.debug.session_memory" class="ai-debug__meta">memory: {{ JSON.stringify(m.debug.session_memory) }}</div>
            <pre>{{ JSON.stringify(m.debug, null, 2) }}</pre>
          </details>

          <!-- SQL（开发可见） -->
          <details v-if="m.sql" class="ai-sql">
            <summary>查看 SQL</summary>
            <pre>{{ m.sql }}</pre>
          </details>

          <!-- 导出：不用 teleport，避免被 AI 浮窗全屏层挡住下拉菜单 -->
          <div v-if="m.role === 'ai' && !m.pending && (canExportTable(m) || canExportDoc(m))" class="ai-actions">
            <button v-if="canExportDoc(m)" type="button" class="ai-export" @click="handleExport(m, 'docx')">Word</button>
            <button v-if="canExportDoc(m)" type="button" class="ai-export" @click="handleExport(m, 'md')">Markdown</button>
            <button v-if="canExportTable(m)" type="button" class="ai-export" @click="handleExport(m, 'xlsx')">Excel</button>
            <button v-if="canExportTable(m)" type="button" class="ai-export" @click="handleExport(m, 'csv')">CSV</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="messages.length <= 2" class="ai-chips">
      <button
        v-for="q in EXAMPLE_CHIPS"
        :key="q"
        type="button"
        class="ai-chip"
        :disabled="sending"
        @click="sendExample(q)"
      ><span>{{ q.includes('日报') ? 'RPT' : q.includes('饼图') || q.includes('告警') ? 'DAT' : q.includes('怎么') || q.includes('账号') ? 'DOC' : 'AI' }}</span>{{ q }}<b>↗</b></button>
    </div>

    <footer class="ai-input">
      <div class="ai-mode">
        <label class="ai-mode__label" for="ai-question-mode">问题类型</label>
        <select id="ai-question-mode" v-model="questionMode" class="ai-mode__select" :disabled="sending">
          <option v-for="m in QUESTION_MODES" :key="m.value" :value="m.value">{{ m.label }}</option>
        </select>
      </div>
      <textarea v-model="input" rows="1" placeholder="输入指令或查询 …（按住 Alt 可切换技术信息）" @keydown="onKeydown" />
      <el-button type="primary" :loading="sending" class="ai-send" @click="send">执行 ▷</el-button>
    </footer>
  </section>
</template>

<style scoped>
.ai-panel {
  display: flex; flex-direction: column; height: 100%;
  background:
    linear-gradient(rgba(0,229,255,.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,229,255,.025) 1px, transparent 1px),
    radial-gradient(100% 80% at 100% 0, rgba(0,104,117,.18), rgba(5,14,25,.98) 62%);
  background-size: 42px 42px, 42px 42px, auto;
  color: #dfeaf0;
}
.ai-mission { display: grid; grid-template-columns: 62px 1fr; gap: 16px; align-items: center; margin: 18px 20px 4px; padding: 18px; border-bottom: 1px solid rgba(0,229,255,.12); }
.ai-mission p { margin: 0 0 6px; color: #4b97a7; font: 800 9px/1 'JetBrains Mono', monospace; letter-spacing: .17em; }
.ai-mission h2 { margin: 0; color: #e7fbff; font-size: 21px; }
.ai-mission > div:last-child > span { display: block; margin-top: 7px; color: #65818d; font-size: 11px; line-height: 1.5; }
.ai-mission__signal { position: relative; width: 54px; height: 54px; display: grid; place-items: center; }
.ai-mission__signal span, .ai-mission__signal i { position: absolute; border: 1px solid rgba(104,250,221,.34); border-radius: 50%; animation: missionOrbit 6s linear infinite; }
.ai-mission__signal span { width: 50px; height: 50px; border-style: dashed; }.ai-mission__signal i { width: 30px; height: 30px; animation-direction: reverse; }
.ai-mission__signal b { width: 7px; height: 7px; border-radius: 50%; background: #68fadd; box-shadow: 0 0 15px #68fadd; }
.ai-list { position: relative; flex: 1; overflow-y: auto; padding: 18px 26px 22px 30px; }
.ai-list::before { content: ''; position: absolute; left: 46px; top: 22px; bottom: 22px; width: 1px; background: linear-gradient(transparent, rgba(0,229,255,.2) 8%, rgba(0,229,255,.08) 92%, transparent); }
.ai-row { position: relative; display: flex; align-items: flex-start; gap: 14px; margin: 16px 0; padding-left: 0; }
.ai-row.is-user { justify-content: flex-start; }
.ai-timeline-node { position: relative; z-index: 2; flex: 0 0 34px; width: 34px; height: 24px; display: grid; place-items: center; margin-top: 4px; border: 1px solid rgba(0,229,255,.25); border-radius: 7px; color: #68fadd; background: #071522; font: 800 8px/1 'JetBrains Mono', monospace; }
.ai-row.is-user .ai-timeline-node { color: #001b1e; border-color: #00e5ff; background: #00e5ff; }
.ai-timeline-node.pending { animation: nodePulse 1.2s ease-in-out infinite; }
.ai-bubble { min-width: 0; max-width: calc(100% - 50px); padding: 14px 16px; line-height: 1.65; }
.b-user { padding: 10px 14px; background: rgba(0,229,255,.11); color: #c9f8ff; border: 1px solid rgba(0,229,255,.22); border-radius: 4px 12px 12px 12px; font-weight: 700; max-width: 72%; }
.b-ai { flex: 1; background: linear-gradient(135deg, rgba(0,104,117,.16), rgba(9,20,32,.78)); border: 1px solid rgba(0,229,255,.1); border-left: 2px solid #68fadd; border-radius: 4px 14px 14px 14px; }
.ai-md :deep(p) { margin: 4px 0; }
.ai-md :deep(table) { border-collapse: collapse; margin: 8px 0; width: 100%; }
.ai-md :deep(th), .ai-md :deep(td) { border: 1px solid rgba(0,229,255,.2); padding: 4px 8px; font-size: 13px; }
.ai-md :deep(code) { background: rgba(0,229,255,.12); padding: 1px 5px; border-radius: 4px; }
.ai-md :deep(h1), .ai-md :deep(h2), .ai-md :deep(h3) { color: #9cf0ff; margin: 10px 0 6px; }
.ai-pending { color: #9cf0ff; }
.ai-train-bar { margin-top: 10px; height: 6px; border-radius: 4px; background: rgba(0,229,255,.12); overflow: hidden; }
.ai-train-bar__fill { height: 100%; border-radius: 4px; background: linear-gradient(90deg, #00e5ff, #67e8f9); transition: width .35s ease; }
.dots::after { content: '…'; animation: blink 1.2s infinite; }
@keyframes blink { 50% { opacity: .3; } }
.ai-card { margin-top: 14px; border-top: 1px solid rgba(0,229,255,.18); overflow: hidden; }
.ai-card__bar { display: flex; justify-content: space-between; padding: 12px 2px 8px; color: #bff8ff; font-weight: 800; font-size: 13px; }
.ai-card__count { font: 11px/1.6 'JetBrains Mono', monospace; color: #6fb9c6; }
.ai-chart { height: 200px; padding: 8px; }
.ai-table-wrap { padding: 6px; }
.ai-data-details { margin-top: 8px; border-top: 1px solid rgba(0,229,255,.1); }
.ai-data-details summary { padding: 10px 2px; color: #6f9ba6; cursor: pointer; font-size: 11px; }
.ai-chips { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; padding: 8px 24px 16px 30px; }
.ai-chip { display: grid; grid-template-columns: 32px 1fr auto; gap: 9px; align-items: center; min-height: 46px; cursor: pointer; text-align: left; font-size: 11px; color: #bfeef4; border: 1px solid rgba(0,229,255,.16); background: rgba(0,229,255,.035); border-radius: 10px; padding: 7px 10px; }
.ai-chip > span { width: 28px; height: 28px; display: grid; place-items: center; border: 1px solid rgba(0,229,255,.24); border-radius: 7px; color: #00e5ff; font: 800 8px/1 'JetBrains Mono', monospace; }
.ai-chip b { color: #4f8994; font-size: 12px; }
.ai-chip:hover:not(:disabled) { border-color: rgba(104,250,221,.48); background: rgba(104,250,221,.08); transform: translateY(-1px); }
.ai-chip:disabled { opacity: .5; cursor: not-allowed; }
.ai-citations { margin-top: 10px; padding: 8px 10px; border: 1px dashed rgba(0,229,255,.28); border-radius: 6px; font-size: 12px; color: #9cf0ff; }
.ai-citations__title { font-weight: 800; cursor: pointer; }
.ai-cite-card { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-top: 6px; padding: 6px 8px; background: rgba(0,0,0,.2); border-radius: 6px; color: #cfe7ee; }
.ai-cite-card__head { flex: 1; font-size: 12px; }
.ai-cite-card__copy { cursor: pointer; font-size: 11px; color: #00e5ff; border: 1px solid rgba(0,229,255,.35); background: transparent; border-radius: 4px; padding: 2px 8px; }
.ai-chart-empty { margin-top: 8px; padding: 12px; text-align: center; color: #6fb9c6; font-size: 12px; border: 1px dashed rgba(0,229,255,.2); border-radius: 6px; }
.ai-debug { margin-top: 10px; font-size: 12px; }
.ai-debug summary { cursor: pointer; color: #6fb9c6; font-weight: 700; }
.ai-debug pre { background: rgba(0,0,0,.35); padding: 8px; border-radius: 6px; overflow-x: auto; font: 11px/1.45 'JetBrains Mono', monospace; color: #8ab4b8; max-height: 200px; }
.ai-report, .ai-sql { margin-top: 10px; font-size: 13px; }
.ai-report summary, .ai-sql summary { cursor: pointer; color: #9cf0ff; font-weight: 700; }
.ai-sql pre { background: rgba(0,0,0,.4); padding: 8px; border-radius: 6px; overflow-x: auto; font: 12px/1.5 'JetBrains Mono', monospace; color: #b6e8f0; }
.ai-actions {
  position: relative;
  z-index: 5;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.ai-export {
  cursor: pointer;
  color: #00e5ff;
  font: 12px/1 'JetBrains Mono', monospace;
  border: 1px solid rgba(0,229,255,.4);
  padding: 5px 10px;
  border-radius: 6px;
  background: rgba(0,229,255,.08);
}
.ai-export:hover { background: rgba(0,229,255,.18); }
.ai-input { position: relative; display: grid; grid-template-columns: 138px 1fr auto; align-items: end; gap: 10px; padding: 14px 18px 16px; border-top: 1px solid rgba(0,229,255,.18); background: rgba(4,13,23,.94); box-shadow: 0 -18px 40px rgba(0,0,0,.2); }
.ai-mode { display: flex; flex-direction: column; gap: 4px; min-width: 140px; }
.ai-mode__label { font-size: 11px; color: #6fb9c6; }
.ai-mode__select {
  background: rgba(8,11,20,.6);
  border: 1px solid rgba(0,229,255,.25);
  border-radius: 8px;
  color: #9cf0ff;
  padding: 8px 10px;
  font-size: 13px;
  outline: none;
}
.ai-mode__select:focus { border-color: #00e5ff; }
.ai-input__icon { font: 14px/1 'JetBrains Mono', monospace; color: #6fb9c6; }
.ai-input textarea { width: 100%; min-height: 42px; box-sizing: border-box; resize: none; background: rgba(8,22,34,.72); border: 1px solid rgba(0,229,255,.2); border-radius: 10px; color: #dfe2f3; padding: 11px 14px; font-size: 14px; outline: none; line-height: 1.4; }
.ai-input textarea:focus { border-color: #00e5ff; }
.ai-send { background: #00e5ff; border-color: #00e5ff; color: #00363d; font-weight: 800; }
:deep(.ai-table) { background: transparent; --el-table-border-color: rgba(0,229,255,.15); --el-table-bg-color: transparent; --el-table-tr-bg-color: transparent; --el-table-header-bg-color: rgba(0,229,255,.08); --el-table-text-color: #cfe7ee; --el-table-header-text-color: #9cf0ff; }
:deep(.ai-table .el-table__inner-wrapper::before) { display: none; }
@keyframes missionOrbit { to { transform: rotate(360deg); } }
@keyframes nodePulse { 50% { box-shadow: 0 0 18px rgba(104,250,221,.45); } }
@media (max-width: 720px) {
  .ai-mission { grid-template-columns: 48px 1fr; margin-left: 12px; margin-right: 12px; padding-left: 8px; padding-right: 8px; }
  .ai-list { padding-left: 14px; padding-right: 14px; }
  .ai-list::before { left: 30px; }
  .ai-chips { grid-template-columns: 1fr; padding-left: 14px; padding-right: 14px; }
  .ai-input { grid-template-columns: 1fr auto; }
  .ai-mode { grid-column: 1 / -1; }
}
@media (prefers-reduced-motion: reduce) {
  .ai-mission__signal span, .ai-mission__signal i, .ai-timeline-node.pending { animation: none; }
}
</style>
