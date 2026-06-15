<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { changePasswordApi } from '../../api/auth'
import {
  monitorNeuralMiningApi,
  monitorNeuralOverviewApi,
} from '../../api/monitor'
import { useMonitorStore } from '../../stores/monitor'
import { useUserStore } from '../../stores/user'
import DemoConsole from '../../components/monitor/DemoConsole.vue'
import AiChatWidget from '../../components/monitor/AiChatWidget.vue'
import { formatChinaClock } from '../../utils/datetime'
import TianshuBigScreen from './TianshuBigScreen.vue'
import MiningWorkbench from './MiningWorkbench.vue'
import CommandBroadcastCenter from './CommandBroadcastCenter.vue'
import AuditChainOverview from './AuditChainOverview.vue'
import ExecutiveOverview from './ExecutiveOverview.vue'
import Alerts from './Alerts.vue'
import BeijingAmapCockpit from './BeijingAmapCockpit.vue'
import FulfillmentMonitor from './FulfillmentMonitor.vue'

const STITCH_BASE = '/stitch/advanced-ai-neural-architecture'

const modules = [
  {
    key: 'overview',
    label: '监管总览',
    code: 'BI',
    source: '',
    note: '全域监管脉冲 BI 首页',
  },
  {
    key: 'audit',
    label: '审计态势',
    code: 'AUD',
    source: '',
    note: '全链路审计态势指挥舱',
  },
  {
    key: 'tianshu',
    label: '天枢大屏',
    code: 'TS',
    source: '',
    note: '保留原天枢大屏组件',
  },
  {
    key: 'broadcast',
    label: '指挥广播',
    code: 'CMD',
    source: `${STITCH_BASE}/_2/code.html`,
    note: '全域指挥广播中心',
  },
  {
    key: 'logistics',
    label: '履约监控',
    code: 'LOG',
    source: '',
    note: '今日履约、阻塞和在途监控',
  },
  {
    key: 'beijing-map',
    label: '北京全域',
    code: 'MAP',
    source: '',
    note: '高德地图物流监管驾驶舱',
  },
  {
    key: 'mining',
    label: '数据智能挖掘',
    code: 'MINE',
    source: `${STITCH_BASE}/_3/code.html`,
    note: '数据智能挖掘中心',
  },
  {
    key: 'alerts',
    label: '预警管理',
    code: 'ALT',
    source: '',
    note: '告警处置与监管闭环',
  },
]

const store = useMonitorStore()
const userStore = useUserStore()
const router = useRouter()
const route = useRoute()

const initialModule = modules.some((item) => item.key === route.query.module) ? String(route.query.module) : 'overview'
const activeModule = ref(initialModule)
const nowText = ref('')
const demoVisible = ref(false)
const passwordDialogVisible = ref(false)
const changingPassword = ref(false)
const loading = reactive({ overview: false, mining: false })
const passwordForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
const overviewData = ref({})
const miningData = ref({})
const stitchFrameRef = ref(null)
const tianshuScreenRef = ref(null)
const tianshuDirectorRunning = ref(false)

const activeItem = computed(() => modules.find((item) => item.key === activeModule.value) || modules[0])
const stitchFrameSrc = computed(() => activeItem.value.source)
const displayName = computed(() => userStore.userInfo?.username || userStore.userInfo?.company_name || '用户')
const avatarText = computed(() => String(displayName.value || 'U').slice(0, 1).toUpperCase())

let clockTimer = null
let refreshTimer = null

const refreshClock = () => {
  nowText.value = formatChinaClock()
}

const fmtNumber = (value, digits = 0) => {
  const n = Number(value || 0)
  return n.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

const fmtCompact = (value, digits = 1) => {
  const n = Number(value || 0)
  if (Math.abs(n) >= 10000) return `${fmtNumber(n / 10000, digits)}万`
  return fmtNumber(n, 0)
}

const fmtMoney = (value) => {
  const n = Number(value || 0)
  if (Math.abs(n) >= 10000) return `¥${fmtNumber(n / 10000, 1)}万`
  return `¥${fmtNumber(n, 0)}`
}

const replaceText = (doc, search, value, limit = 20) => {
  if (!doc || !search) return
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT)
  let count = 0
  let node = walker.nextNode()
  while (node && count < limit) {
    if (node.nodeValue?.includes(search)) {
      node.nodeValue = node.nodeValue.replaceAll(search, String(value))
      count += 1
    }
    node = walker.nextNode()
  }
}

const setWidthByClassToken = (doc, token, value) => {
  const width = `${Math.max(0, Math.min(Number(value || 0), 100))}%`
  Array.from(doc.querySelectorAll('*')).forEach((el) => {
    if (typeof el.className === 'string' && el.className.includes(token)) {
      el.style.width = width
    }
  })
}

const updateStitchOverview = (doc) => {
  if (!overviewData.value.generated_at) return
  const kpi = overviewData.value.kpi || {}
  const lifecycleTotal = (overviewData.value.lifecycle || []).reduce((sum, item) => sum + Number(item.count || 0), 0)
  replaceText(doc, '神经连接率', '履约完成率')
  replaceText(doc, '98.4', fmtNumber(kpi.fulfillment_rate, 1), 2)
  replaceText(doc, '1.2M+', `${fmtCompact(lifecycleTotal)}单`, 1)
  replaceText(doc, '活跃突触', '订单链路')
  replaceText(doc, '通信阈值稳定', `${fmtNumber(kpi.pending_alerts)} 条预警待处理`)
  replaceText(doc, '量子负载', '今日 GMV')
  replaceText(doc, '42.8', fmtMoney(kpi.today_gmv), 1)
  replaceText(doc, 'THz', '', 1)
  replaceText(doc, '自主决策数', '开放预警')
  replaceText(doc, '14,209', fmtNumber(kpi.pending_alerts), 1)
  setWidthByClassToken(doc, 'w-[98.4%]', kpi.fulfillment_rate)
}

const updateStitchBroadcast = (doc) => {
  if (!overviewData.value.generated_at) return
  const channels = overviewData.value.command_channels || []
  const alerts = overviewData.value.latest_alerts || []
  const kpi = overviewData.value.kpi || {}
  replaceText(doc, '9 节点活跃', `${fmtNumber(channels.length || 6)} 频道活跃`)
  replaceText(doc, '终端网格', '指挥频道')
  replaceText(doc, '同步: 100%', `预警: ${fmtNumber(kpi.pending_alerts)}`)
  replaceText(doc, 'AETHERIS 指挥流', '大宗供应链指挥流')
  replaceText(doc, '监管访问权限：ALPHA-1', alerts[0]?.description || '监管访问权限：ALPHA-1', 4)
  replaceText(doc, '执行广播', '发布指令')
}

const updateStitchMining = (doc) => {
  if (!miningData.value.generated_at) return
  const summary = miningData.value.summary || {}
  const spreads = miningData.value.price_spreads || []
  const topGoods = miningData.value.top_goods || []
  const topSpread = spreads[0]
  replaceText(doc, '98.42%', `${fmtNumber(Math.max(0, 100 - Number(summary.high_spread_products || 0) / Math.max(Number(summary.product_count || 1), 1) * 100), 2)}%`)
  replaceText(doc, '1.2 TB/s', `${fmtNumber(summary.quote_count)} 条报价`)
  replaceText(doc, '资产: QUANTUM-X 指数 | 24H 预测', topSpread ? `商品: ${topSpread.product_name} | 价差预测` : '商品价差预测')
  replaceText(doc, '$1,242.09', topSpread ? fmtMoney(topSpread.max_quote) : '¥0')
  replaceText(doc, '+4.2%', topSpread ? `${fmtNumber(topSpread.spread_rate, 1)}%` : '0%')
  replaceText(doc, '强力买入', topSpread ? '价差预警' : '稳定')
  replaceText(doc, '活跃摄取点: 14,209', `商品: ${fmtNumber(summary.product_count)} / 映射: ${fmtNumber(summary.mapped_products)}`)
  replaceText(doc, 'NODE_OMEGA_01', 'XINFADI_CRAWLER')
  replaceText(doc, '正在扫描全球交易所', '新发地行情与供应商报价同步')
  replaceText(doc, 'WHALE_TRACKER', 'SPREAD_WATCHER')
  replaceText(doc, '链上交易追踪', `${fmtNumber(summary.high_spread_products)} 个高价差商品`)
  if (topGoods[0]) replaceText(doc, '最佳切入时间', topGoods[0].name)
}

const updateStitchChat = (doc) => {
  if (!overviewData.value.generated_at) return
  const kpi = overviewData.value.kpi || {}
  const topGoods = miningData.value.top_goods || []
  replaceText(doc, 'NODE_ACTIVITY_STREAM', 'DAZONG_MONITOR_STREAM')
  replaceText(doc, 'AES-512-量子', '监管脱敏上下文')
  replaceText(doc, 'NODE_ID', '业务指标')
  replaceText(doc, '神经交互接口 - 活跃', 'AI 核心对话 - 活跃')
  replaceText(doc, '14,209', fmtNumber(kpi.pending_alerts), 2)
  if (topGoods[0]) replaceText(doc, 'Satellite 07', topGoods[0].name)
  installStitchChat(doc)
}

const installStitchChat = (doc) => {
  if (!doc?.body || doc.body.dataset.dazongChatInstalled === '1') return
  const input = doc.querySelector('input[placeholder*="指令"], input[type="text"]')
  const buttons = Array.from(doc.querySelectorAll('button'))
  const sendButton = buttons.find((btn) => btn.textContent?.includes('执行')) || buttons.at(-1)
  const history = doc.querySelector('.grid-pattern') || input?.closest('section')?.querySelector('.flex-1')
  if (!input || !sendButton || !history) return
  doc.body.dataset.dazongChatInstalled = '1'

  const appendMessage = (role, text, card) => {
    const row = doc.createElement('div')
    row.style.cssText = role === 'user'
      ? 'display:flex;justify-content:flex-end;margin:16px 0;'
      : 'display:flex;justify-content:flex-start;margin:16px 0;'
    const bubble = doc.createElement('div')
    bubble.style.cssText = role === 'user'
      ? 'max-width:72%;padding:14px 16px;border-radius:12px 12px 0 12px;background:#00e5ff;color:#00363d;font-weight:700;line-height:1.55;'
      : 'max-width:82%;padding:14px 16px;border-left:2px solid #00e5ff;border-radius:0 12px 12px 12px;background:linear-gradient(135deg,rgba(0,104,117,.24),rgba(15,19,31,.86));color:#dfe2f3;line-height:1.65;'
    bubble.textContent = text
    if (card?.rows?.length) {
      const table = doc.createElement('div')
      table.style.cssText = 'margin-top:12px;border:1px solid rgba(0,229,255,.22);border-radius:8px;overflow:hidden;font:12px/1.5 JetBrains Mono,monospace;'
      const title = doc.createElement('div')
      title.textContent = card.title || '数据卡片'
      title.style.cssText = 'padding:8px 10px;background:rgba(0,229,255,.10);color:#9cf0ff;font-weight:800;'
      table.appendChild(title)
      card.rows.slice(0, 6).forEach((item) => {
        const line = doc.createElement('div')
        line.style.cssText = 'display:flex;gap:10px;justify-content:space-between;padding:7px 10px;border-top:1px solid rgba(132,147,150,.16);'
        const values = Object.values(item).slice(0, 3).map((value) => String(value ?? ''))
        line.textContent = values.join('  |  ')
        table.appendChild(line)
      })
      bubble.appendChild(table)
    }
    row.appendChild(bubble)
    history.appendChild(row)
    history.scrollTop = history.scrollHeight
  }

  const ask = async () => {
    const text = input.value.trim()
    if (!text) return
    input.value = ''
    appendMessage('user', text)
    appendMessage('ai', '正在调用监管工具分析...')
    try {
      const token = doc.defaultView?.localStorage?.getItem('dz_token')
      const response = await doc.defaultView.fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message: text, messages: [{ role: 'user', content: text }] }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      const pending = Array.from(history.children).reverse().find((el) => el.textContent?.includes('正在调用监管工具分析'))
      pending?.remove()
      appendMessage('ai', data.reply || '已完成分析。', data.data_card)
    } catch (error) {
      const pending = Array.from(history.children).reverse().find((el) => el.textContent?.includes('正在调用监管工具分析'))
      pending?.remove()
      appendMessage('ai', `AI 调用失败：${error?.message || '未知错误'}`)
    }
  }

  sendButton.addEventListener('click', ask)
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') ask()
  })
}

const applyStitchData = () => {
  if (activeModule.value === 'tianshu') return
  const doc = stitchFrameRef.value?.contentDocument
  if (!doc?.body) return
  if (activeModule.value === 'overview') updateStitchOverview(doc)
  if (activeModule.value === 'broadcast') updateStitchBroadcast(doc)
}

const onStitchFrameLoad = () => {
  applyStitchData()
  window.setTimeout(applyStitchData, 500)
  window.setTimeout(applyStitchData, 1600)
}

const loadOverview = async () => {
  loading.overview = true
  try {
    const data = await monitorNeuralOverviewApi()
    overviewData.value = data || {}
    store.kpi = {
      today_orders: data?.kpi?.today_orders || 0,
      today_gmv: data?.kpi?.today_gmv || 0,
      active_vehicles: data?.kpi?.active_vehicles || 0,
      pending_alerts: data?.kpi?.pending_alerts || 0,
    }
    store.alerts = data?.latest_alerts || []
    store.latestOrders = data?.latest_orders || []
  } catch (error) {
    console.error('[monitor] overview load failed', error)
  } finally {
    loading.overview = false
  }
}

const loadMining = async () => {
  loading.mining = true
  try {
    miningData.value = (await monitorNeuralMiningApi()) || {}
  } catch (error) {
    console.error('[monitor] mining load failed', error)
  } finally {
    loading.mining = false
  }
}

/** 仅 Stitch 壳子页需要大块 /neural/*；挖掘中心等原生子组件自行请求，避免首屏 5 路重查询打满 DB 触发 10s 超时 */
function neuralPayloadTargets(moduleKey) {
  switch (moduleKey) {
    case 'broadcast':
      return ['overview']
    case 'chat':
      return ['overview', 'mining']
    default:
      return []
  }
}

async function refreshNeuralPayload() {
  const targets = neuralPayloadTargets(activeModule.value)
  if (!targets.length) return
  if (activeModule.value === 'chat') {
    await loadOverview().catch((error) => console.error('[monitor] chat bundle overview failed', error))
    await loadMining().catch((error) => console.error('[monitor] chat bundle mining failed', error))
    return
  }
  const tasks = []
  if (targets.includes('overview')) tasks.push(loadOverview())
  if (targets.includes('mining')) tasks.push(loadMining())
  await Promise.allSettled(tasks)
}

const selectModule = (key) => {
  activeModule.value = key
  router.replace({ path: '/monitor/dashboard', query: key === 'overview' ? {} : { module: key } }).catch(() => {})
}

const openTianshuStandalone = () => {
  router.push('/monitor/tianshu')
}

const toggleTianshuDirector = () => {
  if (tianshuDirectorRunning.value) {
    tianshuScreenRef.value?.stopDirector?.()
    tianshuDirectorRunning.value = false
    return
  }
  tianshuScreenRef.value?.startDirector?.()
  tianshuDirectorRunning.value = true
}

const onTianshuDirectorState = (payload = {}) => {
  tianshuDirectorRunning.value = Boolean(payload.running)
}

const resetPasswordForm = () => {
  passwordForm.old_password = ''
  passwordForm.new_password = ''
  passwordForm.confirm_password = ''
}

const openChangePassword = () => {
  resetPasswordForm()
  passwordDialogVisible.value = true
}

const submitChangePassword = async () => {
  if (!passwordForm.old_password.trim() || !passwordForm.new_password.trim() || !passwordForm.confirm_password.trim()) {
    ElMessage.warning('请完整填写密码信息')
    return
  }
  if (passwordForm.new_password.trim().length < 6) {
    ElMessage.warning('新密码长度不能少于6位')
    return
  }
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  changingPassword.value = true
  try {
    const res = await changePasswordApi({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password,
    })
    ElMessage.success(res?.message || '密码修改成功')
    passwordDialogVisible.value = false
    resetPasswordForm()
  } finally {
    changingPassword.value = false
  }
}

const logout = () => {
  userStore.logout()
  router.replace('/login')
}

const onUserCommand = (cmd) => {
  if (cmd === 'change-password') openChangePassword()
  if (cmd === 'logout') logout()
}

watch(activeModule, async () => {
  await refreshNeuralPayload()
  await nextTick()
  window.setTimeout(applyStitchData, 100)
})

watch([overviewData, miningData], () => {
  window.setTimeout(applyStitchData, 100)
}, { deep: true })

onMounted(async () => {
  document.body.style.overflow = 'hidden'
  refreshClock()
  clockTimer = setInterval(refreshClock, 1000)
  store.connectMonitor()
  await refreshNeuralPayload()
  refreshTimer = setInterval(refreshNeuralPayload, 60000)
})

onBeforeUnmount(() => {
  document.body.style.overflow = ''
  if (clockTimer) clearInterval(clockTimer)
  if (refreshTimer) clearInterval(refreshTimer)
  store.disconnectMonitor()
})
</script>

<template>
  <div class="stitch-host" :class="{ 'cockpit-scroll': activeModule === 'overview' || activeModule === 'beijing-map' || activeModule === 'logistics' }">
    <iframe
      v-if="activeModule !== 'overview' && activeModule !== 'audit' && activeModule !== 'tianshu' && activeModule !== 'logistics' && activeModule !== 'mining' && activeModule !== 'broadcast' && activeModule !== 'alerts' && activeModule !== 'beijing-map'"
      ref="stitchFrameRef"
      :key="activeModule"
      class="stitch-frame"
      :src="stitchFrameSrc"
      :title="activeItem.label"
      @load="onStitchFrameLoad"
    />

    <ExecutiveOverview v-else-if="activeModule === 'overview'" @navigate="selectModule" />
    <AuditChainOverview v-else-if="activeModule === 'audit'" />
    <FulfillmentMonitor v-else-if="activeModule === 'logistics'" />
    <MiningWorkbench v-else-if="activeModule === 'mining'" />
    <CommandBroadcastCenter v-else-if="activeModule === 'broadcast'" />
    <div v-else-if="activeModule === 'alerts'" class="alerts-stage"><Alerts /></div>
    <BeijingAmapCockpit v-else-if="activeModule === 'beijing-map'" />

    <section v-else class="tianshu-stage">
      <header class="tianshu-stage__bar">
        <div>
          <strong>NEURAL CORE / 天枢大屏</strong>
          <span>原生大屏组件承载，保留全屏通信</span>
        </div>
        <div class="tianshu-stage__director" :class="{ running: tianshuDirectorRunning }">
          <span>DEMO DIRECTOR</span>
          <button type="button" @click="toggleTianshuDirector">
            {{ tianshuDirectorRunning ? '停止巡航' : '演示巡航' }}
          </button>
        </div>
        <button type="button" @click="openTianshuStandalone">独立打开</button>
      </header>
      <div class="tianshu-stage__body">
        <TianshuBigScreen ref="tianshuScreenRef" embedded @director-state="onTianshuDirectorState" />
      </div>
    </section>

    <nav class="module-switcher" :class="{ 'is-tianshu': activeModule === 'tianshu' }" aria-label="监管模块切换">
      <button
        v-for="item in modules"
        :key="item.key"
        type="button"
        :class="{ active: activeModule === item.key }"
        :title="`${item.label} - ${item.note}`"
        @click="selectModule(item.key)"
      >
        <span>{{ item.code }}</span>
        <strong>{{ item.label }}</strong>
      </button>
    </nav>

    <div class="operator-panel">
      <span class="live-dot"></span>
      <span>{{ nowText }}</span>
      <button type="button" @click="demoVisible = true">演示</button>
      <el-dropdown trigger="click" @command="onUserCommand">
        <button class="operator-avatar" type="button">{{ avatarText }}</button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>{{ displayName }}</el-dropdown-item>
            <el-dropdown-item command="change-password">更换密码</el-dropdown-item>
            <el-dropdown-item command="logout">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <el-drawer v-model="demoVisible" title="演示控制台" direction="rtl" size="420px">
      <DemoConsole />
    </el-drawer>

    <AiChatWidget />

    <el-dialog v-model="passwordDialogVisible" title="更换密码" width="420px">
      <el-form label-width="92px">
        <el-form-item label="旧密码">
          <el-input v-model="passwordForm.old_password" type="password" show-password placeholder="请输入旧密码" />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="passwordForm.new_password" type="password" show-password placeholder="请输入新密码（至少6位）" />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="passwordForm.confirm_password" type="password" show-password placeholder="请再次输入新密码" @keyup.enter="submitChangePassword" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="changingPassword" @click="submitChangePassword">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.alerts-stage {
  position: absolute;
  inset: 0;
  overflow-y: auto;
  background: #0f131f;
  padding: 80px 32px 32px;
  box-sizing: border-box;
}

.stitch-host {
  width: 100vw;
  height: 100vh;
  position: relative;
  overflow: hidden;
  color: #dfe2f3;
  background:
    radial-gradient(circle at 50% 50%, rgba(0, 218, 243, 0.08), transparent 52%),
    radial-gradient(circle at 10% 20%, rgba(114, 17, 153, 0.12), transparent 40%),
    #0f131f;
  font-family: "Space Grotesk", Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
}

.stitch-host.cockpit-scroll {
  overflow-y: auto;
  overflow-x: hidden;
}

.stitch-frame {
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
  background: #0f131f;
}

.module-switcher,
.operator-panel,
.tianshu-stage__bar {
  border: 1px solid rgba(0, 218, 243, 0.18);
  background: rgba(10, 14, 26, 0.68);
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(14px);
}

.module-switcher {
  position: fixed;
  left: 0;
  top: 80px;
  bottom: 0;
  z-index: 30;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 18px;
  padding: 76px 0 18px;
  border: 0;
  border-right: 1px solid rgba(0, 229, 255, 0.1);
  border-radius: 0;
  background: rgba(10, 14, 26, 0.02);
  box-shadow: none;
  opacity: 1;
  overflow: visible;
  transition: width 180ms ease, background 180ms ease, border-color 180ms ease;
}

.module-switcher.is-tianshu {
  width: 8px;
  background: transparent;
  border-color: transparent;
}

.module-switcher:hover,
.module-switcher:focus-within {
  width: 104px;
  background: rgba(10, 14, 26, 0.58);
  border-color: rgba(0, 229, 255, 0.2);
}

.module-switcher button {
  width: 78px;
  min-height: 68px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px;
  border: 1px solid rgba(132, 147, 150, 0.24);
  border-radius: 8px;
  color: #bac9cc;
  background: rgba(22, 27, 34, 0.72);
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  transform: translateX(-26px);
  transition: opacity 180ms ease, transform 180ms ease, border-color 180ms ease, background 180ms ease;
}

.module-switcher:hover button,
.module-switcher:focus-within button {
  opacity: 1;
  pointer-events: auto;
  transform: translateX(0);
}

.module-switcher button span {
  width: 40px;
  height: 28px;
  display: grid;
  place-items: center;
  color: #00201a;
  font: 800 10px/1 "JetBrains Mono", monospace;
  background: #68fadd;
  border-radius: 5px;
}

.module-switcher button strong {
  width: 100%;
  min-width: 0;
  overflow: hidden;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
}

.module-switcher button.active {
  color: #dfe2f3;
  border-color: rgba(0, 229, 255, 0.62);
  background: rgba(0, 229, 255, 0.12);
  box-shadow: 0 0 18px rgba(0, 218, 243, 0.2);
}

.module-switcher button.active span {
  background: #00e5ff;
}

.operator-panel {
  position: fixed;
  right: 16px;
  top: 14px;
  z-index: 31;
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 40px;
  padding: 7px 8px 7px 12px;
  border-radius: 999px;
  color: #dffbff;
  font-size: 12px;
  opacity: 0.24;
  transition: opacity 180ms ease;
}

.operator-panel:hover,
.operator-panel:focus-within {
  opacity: 1;
}

.operator-panel > button,
.operator-avatar {
  height: 28px;
  border: 1px solid rgba(0, 229, 255, 0.38);
  color: #dffbff;
  background: rgba(0, 229, 255, 0.08);
  border-radius: 999px;
  cursor: pointer;
}

.operator-panel > button {
  padding: 0 10px;
}

.operator-avatar {
  width: 28px;
  padding: 0;
  font-weight: 800;
}

.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #68fadd;
  box-shadow: 0 0 12px rgba(104, 250, 221, 0.8);
}

.tianshu-stage {
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-rows: 80px minmax(0, 1fr);
  padding: 14px;
  background: #0f131f;
}

.tianshu-stage__bar {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 22px;
  margin-bottom: 14px;
  padding: 0 220px 0 18px;
  border-radius: 8px;
}

.tianshu-stage__bar strong {
  display: block;
  color: #9cf0ff;
  font-size: 24px;
  letter-spacing: 0.02em;
  text-shadow: 0 0 10px rgba(0, 218, 243, 0.5);
}

.tianshu-stage__bar span {
  display: block;
  margin-top: 2px;
  color: #bac9cc;
  font-size: 12px;
}

.tianshu-stage__director {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  height: 36px;
  padding: 0 10px;
  border: 1px solid rgba(0, 229, 255, 0.26);
  border-radius: 7px;
  background:
    radial-gradient(circle at 12% 50%, rgba(0, 229, 255, 0.15), transparent 40%),
    rgba(4, 18, 32, 0.68);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.03);
}

.tianshu-stage__director span {
  margin: 0;
  color: rgba(250, 204, 21, 0.82);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.14em;
}

.tianshu-stage__director button {
  height: 26px;
  padding: 0 10px;
  border-color: rgba(0, 229, 255, 0.42);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 800;
}

.tianshu-stage__director.running {
  border-color: rgba(250, 204, 21, 0.42);
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.04),
    0 0 18px rgba(0, 229, 255, 0.12);
}

.tianshu-stage__director.running button {
  border-color: rgba(251, 113, 133, 0.46);
  color: #ffe4e6;
  background: rgba(127, 29, 29, 0.22);
}

.tianshu-stage__bar > button {
  order: -1;
  flex: 0 0 auto;
  height: 36px;
  padding: 0 14px;
  border: 1px solid rgba(0, 229, 255, 0.45);
  color: #dffbff;
  background: rgba(0, 229, 255, 0.08);
  border-radius: 7px;
  cursor: pointer;
}

.tianshu-stage__body {
  min-height: 0;
  overflow: hidden;
  border: 1px solid rgba(0, 229, 255, 0.24);
  border-radius: 8px;
}

.tianshu-stage__body :deep(.tianshu-shell) {
  height: 100%;
}

:deep(.el-drawer) {
  background: #08111f;
  color: #e6f1ff;
}

@media (max-width: 900px) {
  .module-switcher {
    left: 0;
    right: 0;
    top: auto;
    bottom: 10px;
    width: auto;
    flex-direction: row;
    padding: 8px;
    overflow-x: auto;
    transform: none;
    background: rgba(10, 14, 26, 0.68);
    border: 1px solid rgba(0, 218, 243, 0.18);
    border-radius: 10px;
  }

  .module-switcher:hover,
  .module-switcher:focus-within {
    transform: translateY(-2px);
  }

  .module-switcher button {
    min-width: 96px;
    opacity: 1;
    pointer-events: auto;
    transform: none;
  }
}
</style>
