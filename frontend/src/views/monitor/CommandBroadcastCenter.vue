<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import EventDetailView from '../../components/monitor/EventDetailView.vue'
import {
  createMonitorBroadcastApi,
  listMonitorBroadcastRecipientsApi,
  listMonitorBroadcastsApi,
  monitorBroadcastOverviewApi,
  monitorBroadcastTargetsApi,
} from '../../api/monitorBroadcast'
import { formatChinaDateTime } from '../../utils/datetime'

const roleOptions = [
  { value: 'client', label: '采购端' },
  { value: 'delivery', label: '配送端' },
  { value: 'supplier', label: '供应端' },
  { value: 'factory', label: '工厂端' },
  { value: 'operation', label: '运营端' },
]

const overview = ref({})
const broadcasts = ref([])
const targets = ref([])
const recipients = ref([])
const selectedBroadcast = ref(null)
const detailDrawerVisible = ref(false)
const detailState = ref({ title: '', subtitle: '', rows: [], columns: [], detail: null, route: '' })
const loading = ref(false)
const sending = ref(false)
const targetLoading = ref(false)
const drawerVisible = ref(false)
const contentInputRef = ref(null)

const form = reactive({
  title: '',
  content: '',
  priority: 'normal',
  target_type: 'all',
  roles: [],
  user_ids: [],
})

const kpi = computed(() => overview.value.kpi || {})
const channels = computed(() => overview.value.channels || [])
const eventFlow = computed(() => overview.value.event_flow || [])
const kpiDetails = computed(() => overview.value.kpi_details || {})

const readRateText = (row) => `${row.read_count || 0}/${row.total || row.recipient_count || 0}`

const detailColumns = {
  today_commands: [
    ['title', '标题'], ['priority_label', '级别'], ['target_summary', '目标'], ['recipient_count', '人数'], ['read_rate', '已读率'], ['sender', '发送人'], ['sent_at', '发送时间'],
  ],
  pending_alerts: [
    ['alert_level', '等级'], ['alert_type', '问题'], ['order_no', '订单号'], ['client', '客户'], ['canteen', '食堂'], ['delivery', '配送商'], ['expected_delivery', '约定送达'], ['issue', '说明'], ['created_at', '发生时间'],
  ],
  unread_receipts: [
    ['title', '指令'], ['target_summary', '目标'], ['role', '端'], ['company_name', '公司'], ['username', '账号'], ['sent_at', '发送时间'],
  ],
  active_terminals: [
    ['role', '目标端'], ['count', '启用账号'], ['recent_targets', '最近账号'],
  ],
  orders: [
    ['order_no', '订单号'], ['status', '状态'], ['amount', '金额'], ['client', '客户'], ['canteen', '食堂'], ['delivery', '配送商'], ['updated_at', '更新时间'],
  ],
  risk: [
    ['alert_level', '等级'], ['alert_type', '问题'], ['order_no', '订单号'], ['client', '客户'], ['canteen', '食堂'], ['delivery', '配送商'], ['expected_delivery', '约定送达'], ['issue', '说明'], ['created_at', '发生时间'],
  ],
  quality: [
    ['report_no', '报告号'], ['order_no', '订单号'], ['supplier', '供应商'], ['product', '商品'], ['client', '客户'], ['canteen', '食堂'], ['report_status', '状态'], ['created_at', '提交时间'],
  ],
  finance: [
    ['role', '角色'], ['bill_type', '类型'], ['bill_status', '状态'], ['amount', '金额'], ['order_no', '订单'], ['client', '客户'], ['created_at', '创建时间'],
  ],
  delivery: [
    ['order_no', '订单'], ['driver', '司机'], ['vehicle_no', '车牌'], ['status', '状态'], ['departed_at', '发车时间'], ['arrived_at', '到达时间'],
  ],
}

const detailLabelMap = {
  alert_no: '预警编号',
  alert_level: '预警等级',
  alert_type: '问题类型',
  ticket_no: '工单编号',
  subtype: '问题子类',
  assigned_delivery_name: '承接配送商',
  order_no: '订单号',
  status: '订单状态',
  order_status: '订单状态',
  process_status: '处理状态',
  report_status: '质检状态',
  bill_status: '结算状态',
  amount: '订单金额',
  client: '客户',
  canteen: '食堂',
  delivery: '配送商',
  driver: '司机',
  vehicle_no: '车牌号',
  expected_delivery: '约定送达时间',
  issue: '问题说明',
  location: '配送区域',
  supplier: '供应商',
  product: '商品',
  report_no: '质检报告号',
  bill_type: '账单类型',
  role: '结算对象',
  description: '说明',
  type: '类型',
  created_at: '发生时间',
  updated_at: '更新时间',
  departed_at: '发车时间',
  arrived_at: '送达时间',
}

const hiddenDetailKeys = new Set(['id', 'route', 'object_type', 'object_id', 'order_id'])

const displayValue = (value, key = '') => {
  if (value === null || value === undefined || value === '') return '-'
  if (key.endsWith('_at') || key === 'sent_at' || key === 'updated_at' || key === 'created_at') {
    return formatChinaDateTime(value)
  }
  if (key === 'read_rate') return `${value}%`
  if (key === 'amount') return `￥${Number(value || 0).toLocaleString()}`
  return value
}

const openKpiDetail = (key, title) => {
  const group = kpiDetails.value[key] || {}
  detailState.value = {
    title,
    subtitle: group.title || '指标明细',
    rows: group.items || [],
    columns: detailColumns[key] || [],
    detail: null,
    route: '',
  }
  detailDrawerVisible.value = true
}

const openChannelDetail = (item) => {
  detailState.value = {
    title: item.title,
    subtitle: item.description,
    rows: item.items || [],
    columns: detailColumns[item.key] || [],
    detail: null,
    route: '',
  }
  detailDrawerVisible.value = true
}

const openEventDetail = (item) => {
  detailState.value = {
    title: item.title,
    subtitle: `${item.kind} · ${formatChinaDateTime(item.created_at)}`,
    rows: [],
    columns: [],
    detail: item.detail || {},
    objectType: item.object_type || '',
    kind: item.kind || '',
    route: item.route || '',
  }
  detailDrawerVisible.value = true
}

// —— 事件详情富布局：按字段分组呈现，替代平铺键值 ——
const SUBJECT_FIELDS = ['client', 'canteen', 'delivery', 'supplier']
const METRIC_FIELDS = [
  'amount', 'location', 'expected_delivery', 'order_status', 'process_status',
  'report_status', 'bill_status', 'bill_type', 'role', 'product',
]
const TIME_FIELDS = ['created_at', 'updated_at', 'departed_at', 'arrived_at', 'sent_at']
const TEXT_FIELDS = ['issue', 'description', 'reason']
// 已被专属区块/头部消费、不进通用磁贴的键
const CONSUMED_KEYS = new Set([
  ...SUBJECT_FIELDS, ...METRIC_FIELDS, ...TIME_FIELDS, ...TEXT_FIELDS,
  'driver', 'vehicle_no', 'ticket_no', 'order_no', 'alert_no', 'report_no',
  'statement_no', 'type', 'subtype', 'status', 'complaint', 'billing',
])

const eventDetail = computed(() => detailState.value.detail || {})

// 仅工单详情显示「去督促」：选中运营端、预填标题、关抽屉并聚焦内容输入框
const isTicket = computed(() => !!eventDetail.value.ticket_no)
const goUrge = () => {
  form.target_type = 'roles'
  form.roles = ['operation']
  const tag = headerBadge.value
  form.title = `督促处理：工单 ${headerTitle.value}${tag ? `（${tag}）` : ''}`
  detailDrawerVisible.value = false
  nextTick(() => contentInputRef.value?.focus())
}

const pickEntries = (keys) =>
  keys
    .filter((k) => {
      const v = eventDetail.value[k]
      return v !== null && v !== undefined && v !== '' && v !== '-'
    })
    .map((k) => ({ key: k, label: detailLabelMap[k] || k, value: displayValue(eventDetail.value[k], k) }))

const headerTitle = computed(() => {
  const d = eventDetail.value
  return d.ticket_no || d.order_no || d.alert_no || d.report_no || d.statement_no || detailState.value.title || ''
})
const headerBadge = computed(() => {
  const d = eventDetail.value
  return d.subtype || d.type || d.alert_type || d.bill_type || detailState.value.kind || ''
})
const headerStatus = computed(() => {
  const d = eventDetail.value
  return d.process_status || d.order_status || d.report_status || d.bill_status || d.status || ''
})
const subjectCards = computed(() => {
  const cards = pickEntries(SUBJECT_FIELDS)
  const d = eventDetail.value
  const carrier = [d.driver, d.vehicle_no].filter((x) => x && x !== '-' && x !== '待填写').join(' · ')
  return cards.map((c) =>
    c.key === 'delivery' && carrier ? { ...c, sub: carrier } : c,
  )
})
const metricTiles = computed(() => pickEntries(METRIC_FIELDS))
const timeTiles = computed(() => pickEntries(TIME_FIELDS))
const textBlocks = computed(() => pickEntries(TEXT_FIELDS))
const complaint = computed(() => eventDetail.value.complaint || null)
const billing = computed(() => eventDetail.value.billing || null)
const extraTiles = computed(() =>
  Object.keys(eventDetail.value)
    .filter((k) => !hiddenDetailKeys.has(k) && !CONSUMED_KEYS.has(k))
    .filter((k) => {
      const v = eventDetail.value[k]
      return v !== null && v !== undefined && v !== '' && typeof v !== 'object'
    })
    .map((k) => ({ key: k, label: detailLabelMap[k] || k, value: displayValue(eventDetail.value[k], k) })),
)
const headerTone = computed(() => {
  const b = headerBadge.value
  if (['配送异常', '配送超时', '预警'].includes(b)) return 'warn'
  if (['售后投诉'].includes(b)) return 'info'
  if (['异常订单', '质检缺失', '账务异常'].includes(b)) return 'danger'
  return 'default'
})
const eventMetrics = computed(() => [...metricTiles.value, ...extraTiles.value, ...timeTiles.value])
const eventTimeline = computed(() =>
  (complaint.value?.flow || []).map((f) => ({
    title: f.action_label,
    meta: f.actor_name ? `${f.role_label} · ${f.actor_name}` : f.role_label,
    note: f.note,
    at: f.at,
  })),
)

const loadAll = async () => {
  loading.value = true
  try {
    const [overviewData, listData] = await Promise.all([
      monitorBroadcastOverviewApi(),
      listMonitorBroadcastsApi({ limit: 30 }),
    ])
    overview.value = overviewData || {}
    broadcasts.value = listData || []
  } finally {
    loading.value = false
  }
}

const searchTargets = async (query = '') => {
  targetLoading.value = true
  try {
    targets.value = await monitorBroadcastTargetsApi({ q: query }) || []
  } finally {
    targetLoading.value = false
  }
}

const validateForm = () => {
  if (!form.content.trim()) {
    ElMessage.warning('请输入指令内容')
    return false
  }
  if (form.target_type === 'roles' && !form.roles.length) {
    ElMessage.warning('请选择至少一个目标端')
    return false
  }
  if (form.target_type === 'users' && !form.user_ids.length) {
    ElMessage.warning('请选择至少一个接收用户')
    return false
  }
  return true
}

const sendBroadcast = async () => {
  if (!validateForm()) return
  sending.value = true
  try {
    await createMonitorBroadcastApi({
      title: form.title,
      content: form.content,
      priority: form.priority,
      target_type: form.target_type,
      roles: form.roles,
      user_ids: form.user_ids,
    })
    ElMessage.success('监管指令已发送')
    form.title = ''
    form.content = ''
    await loadAll()
  } finally {
    sending.value = false
  }
}

const openRecipients = async (row) => {
  selectedBroadcast.value = row
  drawerVisible.value = true
  const data = await listMonitorBroadcastRecipientsApi(row.id)
  recipients.value = data?.recipients || []
}

onMounted(async () => {
  await Promise.all([loadAll(), searchTargets()])
})
</script>

<template>
  <section class="command-center" v-loading="loading">
    <div class="ambient-field" aria-hidden="true">
      <i class="ambient-field__orb ambient-field__orb--one"></i>
      <i class="ambient-field__orb ambient-field__orb--two"></i>
      <i class="ambient-field__mesh"></i>
    </div>

    <header class="command-header">
      <div class="command-heading">
        <div class="command-heading__signal"><i></i><span>COMMAND INTELLIGENCE / ONLINE</span></div>
        <h1>指挥广播</h1>
        <p>监管意图经智能编排后，实时触达全域业务节点</p>
      </div>
      <div class="hero-kpis">
        <article class="kpi-item clickable-card" role="button" tabindex="0" aria-label="查看今日指令详情" @click="openKpiDetail('today_commands', '今日指令')" @keydown.enter="openKpiDetail('today_commands', '今日指令')">
          <span class="kpi-item__code">TX</span>
          <strong>{{ kpi.today_commands || 0 }}</strong>
          <span>今日指令</span>
        </article>
        <article class="kpi-item clickable-card is-alert" role="button" tabindex="0" aria-label="查看待处理预警详情" @click="openKpiDetail('pending_alerts', '待处理预警')" @keydown.enter="openKpiDetail('pending_alerts', '待处理预警')">
          <span class="kpi-item__code">AL</span>
          <strong>{{ kpi.pending_alerts || 0 }}</strong>
          <span>待处理预警</span>
        </article>
        <article class="kpi-item clickable-card" role="button" tabindex="0" aria-label="查看未读回执详情" @click="openKpiDetail('unread_receipts', '未读回执')" @keydown.enter="openKpiDetail('unread_receipts', '未读回执')">
          <span class="kpi-item__code">ACK</span>
          <strong>{{ kpi.unread_receipts || 0 }}</strong>
          <span>未读回执</span>
        </article>
        <article class="kpi-item clickable-card" role="button" tabindex="0" aria-label="查看可达账号详情" @click="openKpiDetail('active_terminals', '可达账号')" @keydown.enter="openKpiDetail('active_terminals', '可达账号')">
          <span class="kpi-item__code">NODE</span>
          <strong>{{ kpi.active_terminals || 0 }}</strong>
          <span>可达账号</span>
        </article>
      </div>
    </header>

    <main class="command-grid">
      <section class="compose-panel">
        <div class="agent-stage" aria-hidden="true">
          <div class="agent-orbit agent-orbit--outer"></div>
          <div class="agent-orbit agent-orbit--inner"></div>
          <div class="agent-core">
            <i class="agent-core__liquid agent-core__liquid--cyan"></i>
            <i class="agent-core__liquid agent-core__liquid--violet"></i>
            <i class="agent-core__shine"></i>
          </div>
          <span class="agent-node agent-node--one"></span>
          <span class="agent-node agent-node--two"></span>
          <span class="agent-node agent-node--three"></span>
        </div>

        <div class="compose-shell">
          <div class="panel-title compose-title">
            <div>
              <small>AI COMMAND COMPOSER</small>
              <span>协同指令舱</span>
            </div>
            <div class="agent-state"><i></i>智能链路已就绪</div>
          </div>
          <p class="compose-intro">输入监管意图，系统将按优先级与目标范围完成安全分发。</p>
          <el-form label-position="top">
            <el-form-item label="指令标题">
              <el-input v-model="form.title" placeholder="监管指令（选填）" maxlength="60" />
            </el-form-item>
            <el-form-item label="指令内容">
              <el-input
                ref="contentInputRef"
                v-model="form.content"
                type="textarea"
                :rows="5"
                maxlength="800"
                show-word-limit
                placeholder="描述风险、处置要求或需要各业务端执行的监管动作..."
              />
            </el-form-item>
            <div class="form-row">
              <el-form-item label="信号优先级">
                <el-segmented
                  v-model="form.priority"
                  :options="[
                    { label: '常规', value: 'normal' },
                    { label: '重要', value: 'important' },
                    { label: '紧急', value: 'urgent' },
                  ]"
                />
              </el-form-item>
              <el-form-item label="触达范围">
                <el-segmented
                  v-model="form.target_type"
                  :options="[
                    { label: '业务全域', value: 'all' },
                    { label: '按端角色', value: 'roles' },
                    { label: '指定用户', value: 'users' },
                  ]"
                />
              </el-form-item>
            </div>
            <el-form-item v-if="form.target_type === 'roles'" label="目标端">
              <el-checkbox-group v-model="form.roles" class="role-pills">
                <el-checkbox-button v-for="role in roleOptions" :key="role.value" :label="role.value">
                  {{ role.label }}
                </el-checkbox-button>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item v-if="form.target_type === 'users'" label="指定接收账号">
              <el-select
                v-model="form.user_ids"
                multiple
                filterable
                remote
                reserve-keyword
                collapse-tags
                :remote-method="searchTargets"
                :loading="targetLoading"
                placeholder="搜索公司、账号或手机号"
                class="target-select"
              >
                <el-option
                  v-for="item in targets"
                  :key="item.id"
                  :label="item.label"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <div class="send-zone">
              <div class="send-zone__meta">
                <span>SECURE BROADCAST</span>
                <small>消息中心 + WebSocket 双通道触达</small>
              </div>
              <button class="send-button" :class="`is-${form.priority}`" type="button" :disabled="sending" @click="sendBroadcast">
                <span>{{ sending ? '正在建立链路' : '发布指令' }}</span>
                <i>↗</i>
              </button>
            </div>
          </el-form>
        </div>
      </section>

      <aside class="signal-rail">
      <section class="channels-panel">
        <div class="panel-title">
          <div>
            <small>LIVE CHANNELS</small>
            <span>业务信号</span>
          </div>
          <b>{{ channels.length }} ACTIVE</b>
        </div>
        <div class="channel-list">
          <article
            v-for="item in channels"
            :key="item.key"
            :class="['channel-card', 'clickable-card', item.status]"
            role="button"
            tabindex="0"
            :aria-label="`查看${item.title}详情`"
            @click="openChannelDetail(item)"
            @keydown.enter="openChannelDetail(item)"
          >
            <i class="channel-card__pulse"></i>
            <div>
              <span>{{ item.title }}</span>
              <small>{{ item.description }}</small>
            </div>
            <strong>{{ item.count }}</strong>
          </article>
        </div>
      </section>

      <section class="event-panel">
        <div class="panel-title">
          <div>
            <small>REAL-TIME SIGNALS</small>
            <span>事件脉冲</span>
          </div>
          <b>LIVE</b>
        </div>
        <div class="event-list">
          <article
            v-for="item in eventFlow"
            :key="item.id"
            :class="['event-row', 'clickable-row', item.level]"
            role="button"
            tabindex="0"
            :aria-label="`查看${item.title}详情`"
            @click="openEventDetail(item)"
            @keydown.enter="openEventDetail(item)"
          >
            <i class="event-row__node"></i>
            <div>
              <div class="event-row__head"><b>{{ item.kind }}</b><time>{{ formatChinaDateTime(item.created_at) }}</time></div>
              <strong>{{ item.title }}</strong>
              <span>{{ item.description }}</span>
            </div>
          </article>
          <el-empty v-if="!eventFlow.length" description="暂无事件" />
        </div>
      </section>
      </aside>

      <section class="records-panel">
        <div class="panel-title">
          <div>
            <small>TRANSMISSION LEDGER</small>
            <span>广播记录与回执</span>
          </div>
          <b>点击记录查看接收明细</b>
        </div>
        <el-table :data="broadcasts" height="100%" class="dark-table" @row-click="openRecipients">
          <el-table-column prop="priority_label" label="级别" width="72" />
          <el-table-column prop="title" label="标题" min-width="160" show-overflow-tooltip />
          <el-table-column prop="target_summary" label="目标" min-width="130" show-overflow-tooltip />
          <el-table-column label="已读/总数" width="110">
            <template #default="{ row }">{{ readRateText(row) }}</template>
          </el-table-column>
          <el-table-column label="已读率" width="92">
            <template #default="{ row }">{{ row.read_rate || 0 }}%</template>
          </el-table-column>
          <el-table-column label="发送时间" min-width="150">
            <template #default="{ row }">{{ formatChinaDateTime(row.sent_at) }}</template>
          </el-table-column>
        </el-table>
      </section>
    </main>

    <el-drawer v-model="drawerVisible" title="广播回执明细" direction="rtl" size="620px">
      <div class="drawer-summary" v-if="selectedBroadcast">
        <strong>{{ selectedBroadcast.title }}</strong>
        <span>{{ selectedBroadcast.target_summary }} · {{ readRateText(selectedBroadcast) }} 已读</span>
      </div>
      <el-table :data="recipients" height="calc(100vh - 190px)" class="dark-table">
        <el-table-column prop="role_label" label="端" width="84" />
        <el-table-column prop="company_name" label="公司/组织" min-width="150" show-overflow-tooltip />
        <el-table-column prop="username" label="账号" width="110" />
        <el-table-column label="状态" width="82">
          <template #default="{ row }">
            <span :class="row.is_read ? 'read-ok' : 'read-wait'">{{ row.is_read ? '已读' : '未读' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="已读时间" min-width="150">
          <template #default="{ row }">{{ row.read_at ? formatChinaDateTime(row.read_at) : '-' }}</template>
        </el-table-column>
      </el-table>
    </el-drawer>

    <el-drawer v-model="detailDrawerVisible" :title="detailState.title" direction="rtl" size="720px">
      <div class="drawer-summary">
        <strong>{{ detailState.title }}</strong>
        <span>{{ detailState.subtitle }}</span>
      </div>
      <el-table
        v-if="detailState.rows?.length"
        :data="detailState.rows"
        height="calc(100vh - 180px)"
        class="dark-table"
      >
        <el-table-column
          v-for="col in detailState.columns"
          :key="col[0]"
          :label="col[1]"
          :min-width="['description', 'recent_targets', 'issue'].includes(col[0]) ? 260 : 128"
          show-overflow-tooltip
        >
          <template #default="{ row }">{{ displayValue(row[col[0]], col[0]) }}</template>
        </el-table-column>
      </el-table>
      <EventDetailView
        v-else-if="detailState.detail && Object.keys(detailState.detail).length"
        :header="{ title: headerTitle, badge: headerBadge, badgeTone: headerTone, status: headerStatus }"
        :subjects="subjectCards"
        :metrics="eventMetrics"
        :texts="textBlocks"
        :images="complaint?.images || []"
        :timeline="eventTimeline"
        images-title="客户上传凭证"
      >
        <template v-if="isTicket" #header-action>
          <el-button type="primary" size="small" round @click="goUrge">去督促</el-button>
        </template>

        <!-- 售后投诉专属：反馈 / 结案 -->
        <div v-if="complaint" class="resolve-cards">
          <article class="resolve-card" :class="{ filled: complaint.delivery_response }">
            <span>配送商反馈<template v-if="complaint.assigned_delivery_name"> · {{ complaint.assigned_delivery_name }}</template></span>
            <p v-if="complaint.delivery_response">{{ complaint.delivery_response }}</p>
            <p v-else class="pending">待配送商反馈</p>
            <time v-if="complaint.delivery_responded_at">{{ formatChinaDateTime(complaint.delivery_responded_at) }}</time>
          </article>
          <article class="resolve-card" :class="{ filled: complaint.operation_resolution }">
            <span>运营结案</span>
            <p v-if="complaint.operation_resolution">{{ complaint.operation_resolution }}</p>
            <p v-else class="pending">待运营结案</p>
            <time v-if="complaint.operation_resolved_at">{{ formatChinaDateTime(complaint.operation_resolved_at) }}</time>
          </article>
        </div>

        <!-- 账务异常专属 -->
        <section v-if="billing" class="billing-block">
          <h4>结算单信息</h4>
          <div class="billing-grid">
            <article class="billing-tile"><span>结算单号</span><strong>{{ billing.statement_no }}</strong></article>
            <article class="billing-tile"><span>方向</span><strong>{{ billing.direction || '-' }}</strong></article>
            <article class="billing-tile"><span>金额</span><strong>{{ displayValue(billing.amount, 'amount') }}</strong></article>
            <article class="billing-tile"><span>状态</span><strong>{{ billing.status || '-' }}</strong></article>
            <article class="billing-tile"><span>结算对方</span><strong>{{ billing.counterparty || '-' }}</strong></article>
          </div>
        </section>
      </EventDetailView>
      <el-empty v-else description="暂无明细" />
    </el-drawer>
  </section>
</template>

<style scoped>
.command-center {
  width: 100%;
  height: 100%;
  overflow: auto;
  padding: 26px 28px 42px;
  color: #dfe8f2;
  background:
    linear-gradient(rgba(18, 24, 36, 0.84), rgba(9, 12, 20, 0.94)),
    radial-gradient(circle at 50% 20%, rgba(0, 229, 255, 0.18), transparent 34%),
    #090d16;
}

.hero-panel,
.panel {
  border: 1px solid rgba(0, 229, 255, 0.18);
  border-radius: 8px;
  background: rgba(13, 18, 31, 0.78);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04), 0 22px 50px rgba(0, 0, 0, 0.28);
  backdrop-filter: blur(16px);
}

.hero-panel {
  min-height: 136px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 28px 34px;
}

.hero-panel p {
  margin: 0 0 6px;
  color: rgba(103, 255, 219, 0.62);
  font: 700 12px/1 "JetBrains Mono", monospace;
  letter-spacing: 3px;
}

.hero-panel h1 {
  margin: 0;
  color: #c8fbff;
  font-size: 42px;
  text-shadow: 0 0 18px rgba(0, 229, 255, 0.45);
}

.hero-panel span,
.panel-title small {
  color: rgba(215, 235, 242, 0.58);
}

.hero-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(112px, 1fr));
  gap: 12px;
}

.hero-kpis article {
  min-width: 112px;
  padding: 14px 18px;
  border: 1px solid rgba(0, 229, 255, 0.15);
  border-radius: 8px;
  background: rgba(2, 12, 24, 0.55);
}

.clickable-card,
.clickable-row {
  cursor: pointer;
  transition: border-color 160ms ease, background 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

.clickable-card:hover,
.clickable-card:focus-visible,
.clickable-row:hover,
.clickable-row:focus-visible {
  border-color: rgba(0, 229, 255, 0.58);
  background: rgba(0, 229, 255, 0.09);
  box-shadow: 0 0 22px rgba(0, 229, 255, 0.16);
  outline: none;
}

.clickable-card:hover,
.clickable-card:focus-visible {
  transform: translateY(-1px);
}

.hero-kpis strong {
  display: block;
  color: #8ff8ff;
  font-size: 30px;
}

.command-grid {
  display: grid;
  grid-template-columns: minmax(360px, 0.85fr) minmax(500px, 1.15fr);
  grid-auto-rows: minmax(220px, auto);
  gap: 18px;
  margin-top: 18px;
}

.panel {
  padding: 20px;
  min-height: 0;
}

.panel-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.panel-title span {
  color: #e8faff;
  font-size: 22px;
  font-weight: 800;
}

.compose-panel {
  grid-row: span 2;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1.4fr;
  gap: 14px;
}

.target-select {
  width: 100%;
}

.send-button {
  width: 100%;
  height: 48px;
  border: 1px solid rgba(0, 229, 255, 0.65);
  border-radius: 8px;
  color: #03161b;
  background: linear-gradient(135deg, #7fffee, #00d5ff);
  font-weight: 900;
  cursor: pointer;
}

.send-button:disabled {
  opacity: 0.55;
  cursor: progress;
}

.channel-list {
  display: grid;
  grid-template-columns: repeat(5, minmax(110px, 1fr));
  gap: 12px;
}

.channel-card {
  min-height: 128px;
  padding: 16px;
  border: 1px solid rgba(0, 229, 255, 0.16);
  border-radius: 8px;
  background: rgba(4, 12, 23, 0.56);
}

.channel-card.warn {
  border-color: rgba(255, 128, 128, 0.42);
}

.channel-card span,
.event-row b {
  color: #72ffe2;
  font-weight: 800;
}

.channel-card strong {
  display: block;
  margin: 10px 0 8px;
  color: #eef3ff;
  font-size: 32px;
}

.channel-card small,
.event-row span,
.event-row time {
  color: rgba(221, 232, 241, 0.58);
}

.event-panel,
.records-panel {
  min-height: 360px;
}

.event-list {
  max-height: 330px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.event-row {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) 150px;
  gap: 12px;
  align-items: center;
  padding: 12px;
  border-left: 3px solid rgba(0, 229, 255, 0.65);
  background: rgba(255, 255, 255, 0.035);
}

.event-row.high {
  border-left-color: #ff7a86;
}

.event-row.medium {
  border-left-color: #eaa1ff;
}

.event-row strong {
  display: block;
  color: #eef3ff;
}

.records-panel {
  grid-column: 1 / -1;
  height: 390px;
}

.drawer-summary {
  display: grid;
  gap: 6px;
  margin-bottom: 16px;
}

.drawer-summary strong {
  color: #c8fbff;
  font-size: 20px;
}

.drawer-summary span {
  color: rgba(223, 248, 255, 0.62);
}

.detail-card {
  padding: 18px;
  border: 1px solid rgba(0, 229, 255, 0.16);
  border-radius: 8px;
  background: rgba(5, 14, 26, 0.72);
}

.detail-card dl {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 12px 16px;
  margin: 0;
}

.detail-card dt {
  color: rgba(130, 255, 231, 0.72);
  font-weight: 800;
}

.detail-card dd {
  min-width: 0;
  margin: 0;
  color: #eaf8ff;
  overflow-wrap: anywhere;
}

.read-ok {
  color: #70ffd7;
}

.read-wait {
  color: #ff9faa;
}

.resolve-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.resolve-card {
  padding: 14px 16px;
  border: 1px dashed rgba(0, 229, 255, 0.24);
  border-radius: 10px;
  background: rgba(2, 10, 20, 0.5);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.resolve-card.filled {
  border-style: solid;
  border-color: rgba(0, 229, 255, 0.45);
}

.resolve-card > span {
  color: rgba(130, 255, 231, 0.72);
  font-size: 12px;
  font-weight: 700;
}

.resolve-card p {
  margin: 0;
  color: #eaf8ff;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.resolve-card p.pending {
  color: rgba(221, 232, 241, 0.42);
  font-style: italic;
}

.resolve-card time {
  color: rgba(221, 232, 241, 0.5);
  font-size: 12px;
}

.billing-block h4 {
  margin: 0 0 10px;
  color: #bffcff;
  font-size: 15px;
}

.billing-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}

.billing-tile {
  padding: 12px 14px;
  border: 1px solid rgba(0, 229, 255, 0.12);
  border-radius: 8px;
  background: rgba(2, 10, 20, 0.5);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.billing-tile span {
  color: rgba(215, 235, 242, 0.55);
  font-size: 12px;
}

.billing-tile strong {
  color: #d8f3ff;
  font-size: 16px;
  overflow-wrap: anywhere;
}

:deep(.el-form-item__label),
:deep(.el-radio-button__inner),
:deep(.el-checkbox-button__inner) {
  color: rgba(226, 241, 248, 0.72);
}

:deep(.role-pills .el-checkbox-button__inner) {
  min-width: 86px;
  border-color: rgba(0, 229, 255, 0.28);
  color: #dffbff;
  background: rgba(2, 10, 20, 0.88);
  font-weight: 800;
}

:deep(.role-pills .el-checkbox-button:first-child .el-checkbox-button__inner) {
  border-left-color: rgba(0, 229, 255, 0.28);
}

:deep(.role-pills .el-checkbox-button.is-checked .el-checkbox-button__inner) {
  border-color: rgba(0, 229, 255, 0.82);
  color: #02161b;
  background: linear-gradient(135deg, #7fffee, #00d5ff);
  box-shadow: 0 0 16px rgba(0, 229, 255, 0.28);
}

:deep(.role-pills .el-checkbox-button__inner:hover) {
  color: #ffffff;
  border-color: rgba(0, 229, 255, 0.72);
}

:deep(.el-input__wrapper),
:deep(.el-textarea__inner),
:deep(.el-select__wrapper) {
  background: rgba(2, 10, 20, 0.72);
  border: 1px solid rgba(0, 229, 255, 0.18);
  box-shadow: none;
}

:deep(.el-input__inner),
:deep(.el-textarea__inner) {
  color: #eaf8ff;
}

:deep(.el-segmented) {
  --el-segmented-bg-color: rgba(5, 14, 26, 0.92);
  --el-segmented-item-selected-bg-color: rgba(0, 229, 255, 0.18);
  --el-segmented-item-selected-color: #bffcff;
  --el-segmented-item-hover-color: #bffcff;
  --el-border-radius-base: 8px;
}

:deep(.dark-table),
:deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(6, 16, 30, 0.96);
  --el-table-header-text-color: #bffcff;
  --el-table-text-color: #dfe8f2;
  --el-table-border-color: rgba(0, 229, 255, 0.12);
  --el-table-row-hover-bg-color: rgba(0, 229, 255, 0.08);
  background: transparent;
}

@media (max-width: 1360px) {
  .command-center {
    padding-left: 18px;
  }
  .command-grid,
  .hero-panel {
    grid-template-columns: 1fr;
  }
  .hero-panel {
    display: block;
  }
  .hero-kpis,
  .channel-list {
    grid-template-columns: repeat(2, 1fr);
    margin-top: 18px;
  }
}
</style>

<style scoped>
.command-center {
  --ink: #f2f5ff;
  --muted: rgba(205, 215, 238, 0.56);
  --cyan: #00e5ff;
  --mint: #68fadd;
  --blue: #38bdf8;
  --signal: #ff6b4a;
  position: relative;
  isolation: isolate;
  width: 100%;
  height: 100%;
  padding: 22px 28px 42px 42px;
  overflow: auto;
  color: var(--ink);
  background:
    linear-gradient(115deg, rgba(5, 9, 18, 0.98), rgba(8, 14, 26, 0.96) 48%, rgba(7, 15, 25, 0.97)),
    #08111f;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
}

.command-center::before {
  content: "";
  position: fixed;
  inset: 0;
  z-index: -3;
  opacity: 0.28;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(132, 149, 255, 0.055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(132, 149, 255, 0.055) 1px, transparent 1px);
  background-size: 64px 64px;
  mask-image: linear-gradient(to bottom, black, transparent 78%);
}

.ambient-field,
.ambient-field i {
  position: fixed;
  pointer-events: none;
}

.ambient-field {
  inset: 0;
  z-index: -2;
  overflow: hidden;
}

.ambient-field__orb {
  border-radius: 50%;
  filter: blur(90px);
  opacity: 0.22;
  animation: ambient-drift 14s ease-in-out infinite alternate;
}

.ambient-field__orb--one {
  top: -18%;
  right: 8%;
  width: 44vw;
  height: 44vw;
  background: #0ea5e9;
  opacity: 0.1;
}

.ambient-field__orb--two {
  top: 36%;
  left: 18%;
  width: 34vw;
  height: 34vw;
  background: #00d9ff;
  opacity: 0.1;
  animation-delay: -6s;
}

.ambient-field__mesh {
  inset: 0;
  background:
    radial-gradient(circle at 72% 24%, rgba(0, 229, 255, 0.1), transparent 24%),
    radial-gradient(circle at 34% 44%, rgba(53, 223, 255, 0.1), transparent 24%);
}

.command-header {
  position: relative;
  z-index: 2;
  display: grid;
  grid-template-columns: minmax(300px, 1fr) minmax(650px, 1.55fr);
  align-items: end;
  gap: 32px;
  min-height: 96px;
  padding: 0 8px 18px;
  border-bottom: 1px solid rgba(143, 153, 205, 0.13);
}

.command-heading__signal {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 8px;
  color: rgba(157, 237, 255, 0.68);
  font: 700 10px/1.2 "JetBrains Mono", monospace;
  letter-spacing: 0.18em;
}

.command-heading__signal i,
.agent-state i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cyan);
  box-shadow: 0 0 14px var(--cyan);
  animation: signal-pulse 1.8s ease-in-out infinite;
}

.command-heading h1 {
  margin: 0;
  font-size: clamp(30px, 2.6vw, 44px);
  font-weight: 640;
  letter-spacing: -0.06em;
}

.command-heading p {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 13px;
}

.hero-kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  margin: 0;
}

.hero-kpis .kpi-item {
  position: relative;
  min-width: 0;
  padding: 7px 18px 6px;
  border: 0;
  border-left: 1px solid rgba(151, 162, 213, 0.13);
  border-radius: 0;
  background: transparent;
}

.kpi-item__code {
  position: absolute;
  top: 9px;
  right: 16px;
  color: rgba(134, 236, 255, 0.3);
  font: 700 9px/1 "JetBrains Mono", monospace;
  letter-spacing: 0.12em;
}

.hero-kpis .kpi-item strong {
  display: block;
  margin-bottom: 3px;
  color: #f5f7ff;
  font: 500 31px/1 "JetBrains Mono", "DIN Alternate", monospace;
  letter-spacing: -0.07em;
}

.hero-kpis .kpi-item > span:last-child {
  color: rgba(206, 215, 237, 0.52);
  font-size: 12px;
}

.hero-kpis .kpi-item.is-alert strong {
  color: #ff876e;
  text-shadow: 0 0 22px rgba(255, 85, 58, 0.32);
}

.clickable-card:hover,
.clickable-card:focus-visible,
.clickable-row:hover,
.clickable-row:focus-visible {
  border-color: rgba(116, 247, 255, 0.36);
  background: linear-gradient(90deg, rgba(116, 247, 255, 0.045), transparent);
  box-shadow: none;
  outline: none;
}

.clickable-card:hover,
.clickable-card:focus-visible {
  transform: none;
}

.command-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(640px, 1.55fr) minmax(390px, 0.82fr);
  grid-template-rows: minmax(560px, calc(100vh - 400px)) 390px;
  gap: 18px 24px;
  margin-top: 18px;
}

.compose-panel {
  position: relative;
  grid-row: auto;
  display: flex;
  align-items: flex-start;
  min-height: 560px;
  padding: clamp(48px, 6vh, 72px) 20px 24px clamp(230px, 25vw, 390px);
  overflow: hidden;
  border: 1px solid rgba(145, 157, 212, 0.12);
  border-radius: 28px 8px 28px 8px;
  background:
    linear-gradient(120deg, rgba(10, 22, 36, 0.42), rgba(8, 16, 29, 0.82) 58%, rgba(7, 14, 25, 0.94)),
    rgba(8, 17, 31, 0.76);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.055),
    0 30px 90px rgba(0, 0, 0, 0.24);
  backdrop-filter: blur(24px);
}

.compose-panel::after {
  content: "";
  position: absolute;
  inset: auto 5% 0 35%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0, 229, 255, 0.62), rgba(104, 250, 221, 0.38), transparent);
  box-shadow: 0 0 20px rgba(102, 220, 255, 0.45);
}

.agent-stage {
  position: absolute;
  left: clamp(18px, 2.2vw, 36px);
  top: 50%;
  width: clamp(300px, 21vw, 380px);
  aspect-ratio: 1;
  transform: translateY(-50%);
  filter: drop-shadow(0 28px 55px rgba(0, 128, 170, 0.22));
}

.agent-stage::before {
  content: "";
  position: absolute;
  inset: 16%;
  border-radius: 50%;
  background: rgba(0, 229, 255, 0.13);
  filter: blur(38px);
  animation: core-breathe 4.8s ease-in-out infinite;
}

.agent-orbit {
  position: absolute;
  border: 1px solid rgba(127, 218, 255, 0.13);
  border-radius: 50%;
}

.agent-orbit::after {
  content: "";
  position: absolute;
  top: 50%;
  left: -3px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #d8fbff;
  box-shadow: 0 0 16px 4px rgba(111, 237, 255, 0.8);
}

.agent-orbit--outer {
  inset: 1%;
  animation: orbit-spin 18s linear infinite;
}

.agent-orbit--inner {
  inset: 10%;
  border-color: rgba(104, 250, 221, 0.18);
  transform: rotate(62deg);
  animation: orbit-spin-reverse 12s linear infinite;
}

.agent-core {
  position: absolute;
  inset: 19%;
  overflow: hidden;
  border: 1px solid rgba(221, 234, 255, 0.28);
  border-radius: 46% 54% 63% 37% / 42% 38% 62% 58%;
  background:
    radial-gradient(circle at 42% 35%, rgba(255, 255, 255, 0.95), rgba(151, 241, 255, 0.32) 9%, transparent 24%),
    radial-gradient(circle at 61% 65%, rgba(104, 250, 221, 0.74), transparent 40%),
    linear-gradient(145deg, rgba(28, 235, 255, 0.78), rgba(14, 165, 233, 0.7) 48%, rgba(45, 212, 191, 0.72));
  box-shadow:
    inset -18px -24px 50px rgba(3, 68, 93, 0.7),
    inset 16px 16px 35px rgba(185, 252, 255, 0.3),
    0 0 50px rgba(62, 210, 255, 0.2),
    0 0 90px rgba(34, 211, 238, 0.14);
  animation: liquid-morph 8s ease-in-out infinite alternate;
}

.agent-core__liquid {
  position: absolute;
  border-radius: 42% 58% 52% 48%;
  filter: blur(7px);
  mix-blend-mode: screen;
}

.agent-core__liquid--cyan {
  inset: -20% 30% 20% -25%;
  background: rgba(38, 247, 255, 0.85);
  animation: liquid-flow 7s ease-in-out infinite;
}

.agent-core__liquid--violet {
  inset: 22% -18% -25% 28%;
  background: rgba(45, 212, 191, 0.86);
  animation: liquid-flow 6s ease-in-out -2s infinite reverse;
}

.agent-core__shine {
  position: absolute;
  inset: 7% 46% 55% 13%;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.72);
  filter: blur(10px);
  transform: rotate(-24deg);
}

.agent-node {
  position: absolute;
  width: 7px;
  height: 7px;
  border: 1px solid rgba(219, 248, 255, 0.9);
  border-radius: 50%;
  background: rgba(86, 238, 255, 0.8);
  box-shadow: 0 0 15px rgba(94, 236, 255, 0.9);
}

.agent-node--one { top: 18%; right: 13%; }
.agent-node--two { bottom: 21%; right: 4%; }
.agent-node--three { bottom: 8%; left: 28%; }

.compose-shell {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 720px;
  margin-left: auto;
}

.panel-title {
  margin-bottom: 14px;
}

.panel-title > div > small,
.compose-title > div > small {
  display: block;
  margin-bottom: 5px;
  color: rgba(126, 233, 255, 0.48);
  font: 700 9px/1.2 "JetBrains Mono", monospace;
  letter-spacing: 0.2em;
}

.panel-title > div > span,
.compose-title > div > span {
  color: #f3f5ff;
  font-size: 19px;
  font-weight: 650;
  letter-spacing: -0.02em;
}

.compose-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.agent-state {
  display: flex;
  align-items: center;
  gap: 8px;
  color: rgba(205, 235, 245, 0.58);
  font-size: 11px;
}

.compose-intro {
  margin: -4px 0 16px;
  color: rgba(207, 215, 237, 0.45);
  font-size: 12px;
}

.form-row {
  grid-template-columns: 0.82fr 1.18fr;
  gap: 12px;
}

.target-select {
  width: 100%;
}

.send-zone {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-top: 6px;
  padding-top: 14px;
  border-top: 1px solid rgba(149, 161, 212, 0.1);
}

.send-zone__meta {
  display: grid;
  gap: 4px;
}

.send-zone__meta span {
  color: rgba(132, 232, 255, 0.62);
  font: 700 9px/1 "JetBrains Mono", monospace;
  letter-spacing: 0.16em;
}

.send-zone__meta small {
  color: rgba(204, 214, 237, 0.42);
  font-size: 11px;
}

.send-button {
  width: auto;
  min-width: 174px;
  height: 48px;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 0 10px 0 20px;
  border: 1px solid rgba(137, 241, 255, 0.45);
  border-radius: 999px;
  color: #06151c;
  background: linear-gradient(105deg, #dffbff, #67e8f9 55%, #68fadd);
  box-shadow: 0 8px 28px rgba(73, 218, 255, 0.16);
  font-weight: 800;
  cursor: pointer;
  transition: transform 180ms ease, box-shadow 180ms ease, filter 180ms ease;
}

.send-button i {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: white;
  background: rgba(6, 32, 43, 0.9);
  font-style: normal;
  font-size: 17px;
}

.send-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 34px rgba(73, 218, 255, 0.26);
  filter: saturate(1.15);
}

.send-button.is-urgent {
  border-color: rgba(255, 123, 90, 0.64);
  background: linear-gradient(105deg, #ffe0d8, #ff8569 58%, #ff4e75);
  box-shadow: 0 8px 30px rgba(255, 79, 51, 0.22);
}

.send-button:disabled {
  opacity: 0.52;
  cursor: progress;
  transform: none;
}

.signal-rail {
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 24px;
  padding: 6px 0;
}

.channels-panel,
.event-panel {
  min-height: 0;
  padding-left: 22px;
  border-left: 1px solid rgba(144, 156, 209, 0.14);
}

.channels-panel .panel-title,
.event-panel .panel-title,
.records-panel .panel-title {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.panel-title > b {
  color: rgba(159, 228, 255, 0.4);
  font: 700 9px/1 "JetBrains Mono", monospace;
  letter-spacing: 0.14em;
}

.channel-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px 18px;
}

.channel-card {
  min-height: 64px;
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 9px 4px;
  border: 0;
  border-bottom: 1px solid rgba(147, 158, 210, 0.1);
  border-radius: 0;
  background: transparent;
}

.channel-card__pulse {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #74efff;
  box-shadow: 0 0 10px rgba(116, 239, 255, 0.72);
}

.channel-card.warn .channel-card__pulse {
  background: #ff765b;
  box-shadow: 0 0 12px rgba(255, 86, 52, 0.8);
}

.channel-card span {
  color: rgba(231, 238, 255, 0.86);
  font-size: 12px;
}

.channel-card small {
  display: block;
  max-width: 150px;
  margin-top: 3px;
  overflow: hidden;
  color: rgba(198, 208, 232, 0.38);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.channel-card strong {
  margin: 0;
  color: #e8edff;
  font: 500 23px/1 "JetBrains Mono", monospace;
}

.event-panel {
  display: flex;
  flex-direction: column;
}

.event-panel .panel-title > b {
  color: #88f5d2;
}

.event-list {
  position: relative;
  flex: 1;
  max-height: none;
  gap: 0;
  padding-left: 1px;
}

.event-list :deep(.el-empty) {
  padding: 24px 0 0;
}

.event-list :deep(.el-empty__image) {
  width: 72px;
  opacity: 0.32;
}

.event-list :deep(.el-empty__description) {
  margin-top: 8px;
}

.event-list :deep(.el-empty__description p) {
  color: rgba(198, 207, 230, 0.34);
  font-size: 11px;
}

.event-list::before {
  content: "";
  position: absolute;
  left: 4px;
  top: 8px;
  bottom: 12px;
  width: 1px;
  background: linear-gradient(to bottom, rgba(110, 236, 255, 0.46), rgba(104, 250, 221, 0.06));
}

.event-row {
  position: relative;
  display: grid;
  grid-template-columns: 9px minmax(0, 1fr);
  gap: 13px;
  align-items: start;
  padding: 9px 4px 10px 0;
  border: 0;
  border-left: 0;
  background: transparent;
}

.event-row__node {
  position: relative;
  z-index: 1;
  width: 9px;
  height: 9px;
  margin-top: 4px;
  border: 2px solid #12162c;
  border-radius: 50%;
  background: #75efff;
  box-shadow: 0 0 9px rgba(98, 231, 255, 0.66);
}

.event-row.high .event-row__node {
  background: #ff674c;
  box-shadow: 0 0 11px rgba(255, 82, 53, 0.78);
}

.event-row.medium .event-row__node {
  background: #c674ff;
}

.event-row__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 4px;
}

.event-row__head b {
  color: rgba(128, 239, 255, 0.6);
  font-size: 10px;
}

.event-row__head time {
  color: rgba(196, 206, 231, 0.3);
  font: 500 9px/1 "JetBrains Mono", monospace;
}

.event-row strong {
  color: rgba(238, 242, 255, 0.88);
  font-size: 12px;
}

.event-row span {
  display: block;
  margin-top: 2px;
  overflow: hidden;
  color: rgba(198, 207, 230, 0.42);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.records-panel {
  grid-column: 1 / -1;
  height: 390px;
  min-height: 0;
  padding: 20px 22px 22px;
  border: 1px solid rgba(145, 157, 212, 0.11);
  border-radius: 8px 24px 8px 24px;
  background: linear-gradient(110deg, rgba(14, 17, 39, 0.76), rgba(9, 10, 26, 0.5));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
  backdrop-filter: blur(18px);
}

.records-panel .panel-title > b {
  color: rgba(200, 211, 235, 0.38);
  font: 500 10px/1 "PingFang SC", sans-serif;
  letter-spacing: 0;
}

:deep(.el-form-item) {
  margin-bottom: 13px;
}

:deep(.el-form-item__label) {
  height: auto;
  margin-bottom: 6px;
  padding: 0;
  color: rgba(212, 220, 240, 0.58);
  font-size: 11px;
  line-height: 1.2;
}

:deep(.el-input__wrapper),
:deep(.el-textarea__inner),
:deep(.el-select__wrapper) {
  border: 1px solid rgba(148, 161, 215, 0.13);
  border-radius: 9px;
  background: rgba(5, 8, 23, 0.58);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.025);
  transition: border-color 180ms ease, box-shadow 180ms ease, background 180ms ease;
}

:deep(.el-input__wrapper:hover),
:deep(.el-textarea__inner:hover),
:deep(.el-select__wrapper:hover),
:deep(.el-input__wrapper.is-focus),
:deep(.el-textarea__inner:focus),
:deep(.el-select__wrapper.is-focused) {
  border-color: rgba(115, 235, 255, 0.38);
  background: rgba(8, 12, 32, 0.76);
  box-shadow: 0 0 0 3px rgba(92, 220, 255, 0.045);
}

:deep(.el-input__inner),
:deep(.el-textarea__inner) {
  color: #edf2ff;
}

:deep(.el-input__wrapper) {
  min-height: 38px;
}

:deep(.el-textarea__inner) {
  min-height: 116px !important;
  padding: 12px 14px;
  line-height: 1.65;
}

:deep(.el-input__count) {
  color: rgba(195, 204, 227, 0.3);
  background: transparent;
}

:deep(.el-segmented) {
  width: 100%;
  padding: 3px;
  --el-segmented-bg-color: rgba(5, 8, 22, 0.65);
  --el-segmented-item-selected-bg-color: rgba(0, 229, 255, 0.16);
  --el-segmented-item-selected-color: #dffbff;
  --el-segmented-item-hover-color: #dffbff;
  --el-border-radius-base: 7px;
  border: 1px solid rgba(148, 161, 215, 0.1);
}

:deep(.el-segmented__item) {
  min-width: 0;
  font-size: 11px;
}

:deep(.role-pills .el-checkbox-button__inner) {
  min-width: 72px;
  border-color: rgba(139, 151, 205, 0.14);
  color: rgba(221, 228, 246, 0.7);
  background: rgba(6, 9, 24, 0.68);
  font-size: 11px;
  font-weight: 600;
}

:deep(.role-pills .el-checkbox-button.is-checked .el-checkbox-button__inner) {
  border-color: rgba(105, 229, 255, 0.48);
  color: #effdff;
  background: linear-gradient(120deg, rgba(0, 229, 255, 0.24), rgba(104, 250, 221, 0.2));
  box-shadow: inset 0 0 18px rgba(108, 219, 255, 0.08);
}

:deep(.dark-table),
:deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(15, 18, 40, 0.86);
  --el-table-header-text-color: rgba(176, 218, 242, 0.62);
  --el-table-text-color: rgba(226, 232, 248, 0.78);
  --el-table-border-color: rgba(139, 151, 201, 0.08);
  --el-table-row-hover-bg-color: rgba(107, 122, 255, 0.08);
  background: transparent;
  font-size: 12px;
}

:deep(.el-table th.el-table__cell) {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
}

:deep(.el-table td.el-table__cell) {
  border-bottom-color: rgba(139, 151, 201, 0.075);
}

:deep(.el-table__inner-wrapper::before) {
  display: none;
}

.drawer-summary strong {
  color: #dffbff;
}

.read-ok { color: #7fffd7; }
.read-wait { color: #ff8b72; }

@keyframes liquid-morph {
  0% { border-radius: 46% 54% 63% 37% / 42% 38% 62% 58%; transform: rotate(-4deg) scale(0.98); }
  35% { border-radius: 58% 42% 45% 55% / 56% 61% 39% 44%; transform: rotate(3deg) scale(1.025); }
  70% { border-radius: 39% 61% 55% 45% / 48% 37% 63% 52%; transform: rotate(-2deg) scale(1); }
  100% { border-radius: 55% 45% 39% 61% / 36% 58% 42% 64%; transform: rotate(5deg) scale(1.035); }
}

@keyframes liquid-flow {
  0%, 100% { transform: translate(-5%, -4%) rotate(0deg) scale(1); }
  50% { transform: translate(16%, 14%) rotate(42deg) scale(1.18); }
}

@keyframes orbit-spin { to { transform: rotate(360deg); } }
@keyframes orbit-spin-reverse { from { transform: rotate(62deg); } to { transform: rotate(-298deg); } }
@keyframes core-breathe { 50% { transform: scale(1.18); opacity: 0.74; } }
@keyframes signal-pulse { 50% { opacity: 0.35; transform: scale(0.72); } }
@keyframes ambient-drift { to { transform: translate(7vw, 5vh) scale(1.12); } }

@media (prefers-reduced-motion: reduce) {
  .command-center *,
  .command-center *::before,
  .command-center *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
  }
}

@media (max-width: 1420px) {
  .command-center {
    padding-left: 30px;
  }

  .command-header {
    grid-template-columns: minmax(280px, 0.8fr) minmax(600px, 1.5fr);
  }

  .command-grid {
    grid-template-columns: minmax(570px, 1.45fr) minmax(350px, 0.8fr);
  }

  .compose-panel {
    padding-left: 285px;
  }

  .agent-stage {
    left: 18px;
    width: 330px;
  }
}

@media (max-width: 1120px) {
  .command-header {
    grid-template-columns: 1fr;
    gap: 18px;
  }

  .command-grid {
    grid-template-columns: 1fr;
    grid-template-rows: auto auto 390px;
  }

  .signal-rail {
    grid-template-columns: 0.8fr 1.2fr;
    grid-template-rows: minmax(300px, auto);
  }

  .records-panel {
    grid-column: 1;
  }
}

@media (max-width: 820px) {
  .command-center {
    padding: 18px 16px 110px;
  }

  .hero-kpis {
    grid-template-columns: repeat(2, 1fr);
  }

  .hero-kpis .kpi-item {
    border-bottom: 1px solid rgba(151, 162, 213, 0.1);
  }

  .compose-panel {
    display: block;
    min-height: 0;
    padding: 250px 16px 20px;
  }

  .agent-stage {
    top: -36px;
    left: 50%;
    width: 280px;
    transform: translateX(-50%);
  }

  .form-row,
  .signal-rail {
    grid-template-columns: 1fr;
  }

  .signal-rail {
    grid-template-rows: auto auto;
  }

  .send-zone {
    align-items: stretch;
    flex-direction: column;
  }

  .send-button {
    width: 100%;
  }
}
</style>
