<script setup>
import { reactive, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'
import networkBg from '../assets/login-bg-network.jpg'
import loginLogo from '../assets/login-logo.png'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)

// ── Canvas 粒子网络动效 ──────────────────────────────────────────
const canvasRef = ref(null)
let animId = null

function initCanvas(canvas) {
  const ctx = canvas.getContext('2d')
  const COUNT = 60
  const MAX_DIST = 140
  const COLOR = '180, 200, 210'

  const resize = () => {
    canvas.width = window.innerWidth
    canvas.height = window.innerHeight
  }
  resize()
  window.addEventListener('resize', resize)

  const particles = Array.from({ length: COUNT }, () => ({
    x: Math.random() * canvas.width,
    y: Math.random() * canvas.height,
    vx: (Math.random() - 0.5) * 0.6,
    vy: (Math.random() - 0.5) * 0.6,
    r: Math.random() * 1.5 + 0.8,
  }))

  const draw = () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    for (const p of particles) {
      p.x += p.vx
      p.y += p.vy
      if (p.x < 0 || p.x > canvas.width)  p.vx *= -1
      if (p.y < 0 || p.y > canvas.height) p.vy *= -1

      ctx.beginPath()
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${COLOR}, 0.5)`
      ctx.fill()
    }

    for (let i = 0; i < COUNT; i++) {
      for (let j = i + 1; j < COUNT; j++) {
        const dx = particles[i].x - particles[j].x
        const dy = particles[i].y - particles[j].y
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < MAX_DIST) {
          const alpha = (1 - dist / MAX_DIST) * 0.2
          ctx.beginPath()
          ctx.moveTo(particles[i].x, particles[i].y)
          ctx.lineTo(particles[j].x, particles[j].y)
          ctx.strokeStyle = `rgba(${COLOR}, ${alpha})`
          ctx.lineWidth = 0.8
          ctx.stroke()
        }
      }
    }

    animId = requestAnimationFrame(draw)
  }

  draw()
  return () => {
    window.removeEventListener('resize', resize)
    cancelAnimationFrame(animId)
  }
}

const activePanel = ref(null)
const openPanel = (name) => { activePanel.value = name }
const closePanel = () => { activePanel.value = null }
const onKeyDown = (e) => { if (e.key === 'Escape') closePanel() }

let cleanup = null
onMounted(() => {
  cleanup = initCanvas(canvasRef.value)
  window.addEventListener('keydown', onKeyDown)
})
onUnmounted(() => {
  cleanup?.()
  window.removeEventListener('keydown', onKeyDown)
})

const form = reactive({
  username: 'client001',
  password: 'demo123',
})

const nodes = [
  { key: 'operation', label: '运营端', icon: 'settings', username: 'operation001' },
  { key: 'monitor', label: '监管端', icon: 'visibility', username: 'monitor001' },
  { key: 'supplier', label: '供货商端', icon: 'inventory', username: 'supplier001' },
  { key: 'delivery', label: '配送商端', icon: 'truck', username: 'delivery001' },
  { key: 'factory', label: '工厂端', icon: 'factory', username: 'factory001' },
  { key: 'scale', label: '智能秤端', icon: 'scale', disabled: true },
  { key: 'client', label: '客户端', icon: 'person', username: 'client001' },
  { key: 'driver', label: '司机端', icon: 'shipping', disabled: true },
  { key: 'sorter', label: '分检端', icon: 'tree', disabled: true },
]

const selectedNode = ref('client')

const pickNode = (node) => {
  if (node.disabled) return
  selectedNode.value = node.key
  form.username = node.username
  form.password = 'demo123'
}

const submit = async () => {
  if (!form.username || !form.password) return
  loading.value = true
  try {
    const res = await userStore.login(form)
    if (res.role === 'client') {
      router.replace({ path: '/client/select-canteen', query: { redirect: '/client/contracts' } })
      return
    }
    router.replace(`/${res.role}`)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="ae-root">
    <div class="ae-bg-image" :style="{ backgroundImage: `url(${networkBg})` }" aria-hidden="true"></div>
    <canvas ref="canvasRef" class="ae-canvas" aria-hidden="true"></canvas>
    <div class="ae-bg-gradient" aria-hidden="true"></div>
    <div class="ae-particles" aria-hidden="true">
      <span class="p" style="width:4px;height:4px;top:20%;left:10%;animation-delay:0s"></span>
      <span class="p" style="width:2px;height:2px;top:60%;left:30%;animation-delay:-5s"></span>
      <span class="p" style="width:6px;height:6px;top:40%;left:70%;animation-delay:-10s"></span>
      <span class="p" style="width:3px;height:3px;top:80%;left:80%;animation-delay:-15s"></span>
      <span class="p" style="width:5px;height:5px;top:10%;left:50%;animation-delay:-2s"></span>
      <span class="p" style="width:2px;height:2px;top:90%;left:20%;animation-delay:-8s"></span>
    </div>

    <header class="ae-header">
      <div class="ae-brand">
        <img :src="loginLogo" class="ae-logo" alt="FoodLink Express Logo" />
        <span class="ae-brand-text">FoodLink Express</span>
      </div>
      <nav class="ae-nav">
        <a href="#" @click.prevent="openPanel('overview')">平台概览</a>
        <a href="#" @click.prevent="openPanel('security')">安全架构</a>
        <a href="#" @click.prevent="openPanel('support')">技术支持</a>
      </nav>
      <div class="ae-status">
        <span class="dot"></span>
        <span class="txt">SYSTEM STATUS 系统状态: ONLINE</span>
      </div>
    </header>

    <main class="ae-main">
      <section class="ae-hero">
        <h1 class="hero-title">FoodLink Express</h1>
        <h2 class="hero-sub">食迅易联・全域数据监管中台</h2>
        <p class="hero-desc">
          欢迎进入 Aetheris Command 系统。本终端作为新一代智能指挥中心的核心入口，
          集成多端协同能力，为您提供高实时、高安全性的全局数据监控与流程管理。
        </p>
      </section>

      <section class="ae-panel">
        <header class="panel-head">
          <h3>系统登录 <span class="en">System Login</span></h3>
          <p>请输入您的凭证以访问加密核心</p>
        </header>

        <form class="panel-form" @submit.prevent="submit">
          <label class="field">
            <span class="lbl">账户登录</span>
            <div class="input-wrap">
              <svg class="ico" viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="8" r="4" fill="none" stroke="currentColor" stroke-width="1.6"/>
                <path d="M4 21c1.5-4 5-6 8-6s6.5 2 8 6" fill="none" stroke="currentColor" stroke-width="1.6"/>
              </svg>
              <input v-model="form.username" type="text" placeholder="用户名 / 手机号 / ID" autocomplete="username" />
            </div>
          </label>

          <label class="field">
            <span class="lbl">登录密码</span>
            <div class="input-wrap">
              <svg class="ico" viewBox="0 0 24 24" aria-hidden="true">
                <rect x="5" y="10" width="14" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/>
                <path d="M8 10V7a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" stroke-width="1.6"/>
              </svg>
              <input v-model="form.password" type="password" placeholder="请输入登录密码" autocomplete="current-password" />
            </div>
          </label>

          <div class="row-between">
            <span class="hint">演示密码统一为 <code>demo123</code></span>
            <a class="link" href="#">忘记密码?</a>
          </div>

          <button class="btn-primary" :disabled="loading" type="submit">
            <span>{{ loading ? '登录中…' : '立即登录 LOGIN' }}</span>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M5 12h13M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
        </form>

        <div class="nodes">
          <div class="nodes-label">业务端节点选择</div>
          <div class="nodes-grid">
            <button
              v-for="node in nodes"
              :key="node.key"
              type="button"
              class="node"
              :class="{ active: selectedNode === node.key && !node.disabled, disabled: node.disabled }"
              :disabled="node.disabled"
              :title="node.disabled ? '尚未开放' : `填充 ${node.username} / demo123`"
              @click="pickNode(node)"
            >
              <svg class="node-ico" viewBox="0 0 24 24" aria-hidden="true">
                <template v-if="node.icon === 'settings'">
                  <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.6"/>
                  <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.9 2.9l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.9-2.9l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.9-2.9l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.9 2.9l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" fill="none" stroke="currentColor" stroke-width="1.4"/>
                </template>
                <template v-else-if="node.icon === 'visibility'">
                  <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" fill="none" stroke="currentColor" stroke-width="1.6"/>
                  <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.6"/>
                </template>
                <template v-else-if="node.icon === 'inventory'">
                  <rect x="3" y="7" width="18" height="13" rx="1" fill="none" stroke="currentColor" stroke-width="1.6"/>
                  <path d="M3 11h18M9 14h6" fill="none" stroke="currentColor" stroke-width="1.6"/>
                  <path d="M8 4h8l2 3H6z" fill="none" stroke="currentColor" stroke-width="1.6"/>
                </template>
                <template v-else-if="node.icon === 'truck'">
                  <path d="M3 7h11v9H3z" fill="none" stroke="currentColor" stroke-width="1.6"/>
                  <path d="M14 10h4l3 3v3h-7z" fill="none" stroke="currentColor" stroke-width="1.6"/>
                  <circle cx="7" cy="18" r="2" fill="none" stroke="currentColor" stroke-width="1.6"/>
                  <circle cx="17" cy="18" r="2" fill="none" stroke="currentColor" stroke-width="1.6"/>
                </template>
                <template v-else-if="node.icon === 'factory'">
                  <path d="M3 21V10l5 3V10l5 3V7l8 5v9z" fill="none" stroke="currentColor" stroke-width="1.6"/>
                  <path d="M7 17h2M11 17h2M15 17h2" stroke="currentColor" stroke-width="1.6"/>
                </template>
                <template v-else-if="node.icon === 'scale'">
                  <path d="M4 20h16M12 4v16" fill="none" stroke="currentColor" stroke-width="1.6"/>
                  <path d="M6 12 L4 7 L8 7 Z M18 12 L16 7 L20 7 Z" fill="none" stroke="currentColor" stroke-width="1.6"/>
                </template>
                <template v-else-if="node.icon === 'person'">
                  <circle cx="12" cy="8" r="4" fill="none" stroke="currentColor" stroke-width="1.6"/>
                  <path d="M4 21c1.5-4 5-6 8-6s6.5 2 8 6" fill="none" stroke="currentColor" stroke-width="1.6"/>
                </template>
                <template v-else-if="node.icon === 'shipping'">
                  <path d="M2 16V6h12v10M14 10h4l3 3v3h-7" fill="none" stroke="currentColor" stroke-width="1.6"/>
                  <circle cx="7" cy="18" r="1.8" fill="none" stroke="currentColor" stroke-width="1.6"/>
                  <circle cx="17" cy="18" r="1.8" fill="none" stroke="currentColor" stroke-width="1.6"/>
                </template>
                <template v-else-if="node.icon === 'tree'">
                  <path d="M12 3v18M12 8l-4-4M12 8l4-4M12 14l-5-5M12 14l5-5M12 20l-6-6M12 20l6-6" fill="none" stroke="currentColor" stroke-width="1.6"/>
                </template>
              </svg>
              <span class="node-label">{{ node.label }}</span>
            </button>
          </div>
        </div>
      </section>
    </main>

    <!-- ── Info Panels ───────────────────────────────────────── -->
    <Transition name="ip">
      <div v-if="activePanel" class="ip-overlay" @click.self="closePanel">
        <div class="ip-modal">

          <!-- HEAD -->
          <header class="ip-head">
            <div class="ip-head-left">
              <span class="ip-tag">{{ { overview: 'PLATFORM', security: 'SECURITY', support: 'SUPPORT' }[activePanel] }}</span>
              <h2 class="ip-title">{{ { overview: '平台概览', security: '安全架构', support: '技术支持' }[activePanel] }}</h2>
            </div>
            <button class="ip-close" @click="closePanel" aria-label="关闭">×</button>
          </header>

          <!-- BODY -->
          <div class="ip-body">

            <!-- ───── 平台概览 ───── -->
            <template v-if="activePanel === 'overview'">
              <p class="ip-lead">FoodLink Express 是面向学校食堂的 B2B2B2C 供应链全链路平台，覆盖采购招标、分单配货、物流配送、现场称重收货、账务清结全流程，形成多端协同闭环。</p>

              <div class="ov-stats">
                <div class="ov-stat"><span class="osn">6</span><span class="osl">协同角色</span></div>
                <div class="ov-stat"><span class="osn">7</span><span class="osl">订单流转状态</span></div>
                <div class="ov-stat"><span class="osn">37</span><span class="osl">核心数据模型</span></div>
                <div class="ov-stat"><span class="osn">50+</span><span class="osl">REST 接口</span></div>
                <div class="ov-stat"><span class="osn">3</span><span class="osl">账务清结层级</span></div>
              </div>

              <h3 class="ip-sec">全链路业务流</h3>
              <div class="flow-track">
                <div class="flow-node" v-for="(s, i) in [
                  { idx:'①', title:'合约招标', desc:'客户发起招标，配送商投标上浮率，系统自动中标、锁定定价', entity:'Contract · TenderBid', color:'#00e5ff' },
                  { idx:'②', title:'智能下单', desc:'OCR 图像识别、语音转文字或手动选品，快照冻结商品价格', entity:'Order · items_snapshot_json', color:'#51e7cb' },
                  { idx:'③', title:'分单配货', desc:'配送商智能分单（成本/均衡/多源三种模式）分派供货商，逐行追踪', entity:'OrderItemAllocation', color:'#a3f7e0' },
                  { idx:'④', title:'路线配送', desc:'高德地图路线规划，北斗实时定位，电子围栏与北京限行校验', entity:'Delivery · DeliveryGeofence', color:'#51e7cb' },
                  { idx:'⑤', title:'称重收货', desc:'智能秤 Pad 逐行扫码称重，少收填报原因，双方手写签名确认', entity:'OrderReceivingLine · Signatures', color:'#00e5ff' },
                  { idx:'⑥', title:'账务结算', desc:'自动生成三层账单（客户↔配送↔供货商），周期对账，状态追踪至结清', entity:'Bill · BillingStatement', color:'#9af7c8' },
                  { idx:'⑦', title:'全局监管', desc:'WebSocket 实时推送，告警预警，审计日志，物流地图大屏', entity:'Alert · AuditLog · Monitor', color:'#c3f5ff' },
                ]" :key="i">
                  <div class="fn-card" :style="{ borderColor: s.color + '30' }">
                    <div class="fn-idx" :style="{ color: s.color }">{{ s.idx }}</div>
                    <div class="fn-title">{{ s.title }}</div>
                    <div class="fn-desc">{{ s.desc }}</div>
                    <div class="fn-entity">{{ s.entity }}</div>
                  </div>
                  <div v-if="i < 6" class="fn-arrow">›</div>
                </div>
              </div>

              <h3 class="ip-sec">平台角色</h3>
              <div class="role-grid">
                <div class="role-card" v-for="r in [
                  { code:'client', name:'客户端（食堂）', desc:'学校采购方，多食堂管理，支持 OCR/语音下单', feats:['多食堂选择 & JWT 会话绑定','OCR 图片 / 语音 / 手动三种下单方式','智能秤 Pad 扫码称重收货','双签名签收 & 账单确认'] },
                  { code:'delivery', name:'配送商', desc:'统筹物流，投标合约，智能分单，路线规划', feats:['合约招标投标 & 价格报价','智能分单三种模式（成本/均衡/多源）','高德地图路线规划 & 北斗实时追踪','车队 & 设备 & 电子围栏管理'] },
                  { code:'supplier', name:'供货商', desc:'分包配货，打印标签，出库发货，上传质检', feats:['查看分配给自己的订单行','分拣位置分配 & 条码标签打印','逐行备货确认 & 出库发货','质检报告上传（PDF/图片）'] },
                  { code:'factory', name:'厂家', desc:'指定工厂出具质检报告，关联合规审计', feats:['查看指定商品的订单','上传质检报告 & 合格证','报告状态追踪（待审核/已通过）','与 supplier 质检报告互补'] },
                  { code:'operation', name:'运营端', desc:'平台管理，商品维护，工单处理，账期配置', feats:['商品分类 & 价格基准维护','账号管理 & 角色权限分配','工单审核（异常/售后/配送异常）','结算周期 & 对账单配置'] },
                  { code:'monitor', name:'监管驾驶舱', desc:'全链路实时监控，告警预警，审计报表', feats:['WebSocket 实时 KPI 仪表板','物流地图车辆位置 & 路线动画','告警中心（逾期/缺货/质量异常）','审计日志 & 数据报表导出'] },
                ]" :key="r.code">
                  <div class="rc-head">
                    <code class="rc-code">{{ r.code }}</code>
                    <span class="rc-name">{{ r.name }}</span>
                  </div>
                  <p class="rc-desc">{{ r.desc }}</p>
                  <ul class="rc-feats">
                    <li v-for="f in r.feats" :key="f">{{ f }}</li>
                  </ul>
                </div>
              </div>

              <h3 class="ip-sec">核心数据流转</h3>
              <div class="data-flow">
                <div class="df-row" v-for="r in [
                  { label:'合约定价',  val:'order.total_amount = Σ qty × reference_price × (1 + category_float_rate)' },
                  { label:'快照冻结',  val:'items_snapshot_json 下单瞬间固化商品名称、价格、规格，历史订单不受变更影响' },
                  { label:'分单账务',  val:'配送商对供货商账单 = Σ allocation.quantity × allocation.unit_price（独立于客户账单）' },
                  { label:'少收退差',  val:'收货 confirmed_kg < ordered_kg → 自动生成 OrderReturn & OrderReturnLine，关联工单' },
                  { label:'账单层级',  val:'客户 → 配送商（订单总额）; 配送商 → 供货商（分单金额）; 三层独立周期对账' },
                ]" :key="r.label">
                  <span class="df-label">{{ r.label }}</span>
                  <span class="df-val">{{ r.val }}</span>
                </div>
              </div>
            </template>

            <!-- ───── 安全架构 ───── -->
            <template v-else-if="activePanel === 'security'">
              <p class="ip-lead">平台采用纵深防御策略，从身份认证、权限隔离、数据完整性到操作审计与基础设施隔离，覆盖供应链数据安全的关键面。</p>

              <div class="sec-pillars">
                <div class="sec-pillar" v-for="p in [
                  {
                    tag:'AUTH', title:'身份认证与权限',
                    color:'#00e5ff',
                    items:[
                      'JWT Token 签名（HS256），服务端校验，无状态会话',
                      '6 角色 RBAC：client / delivery / supplier / factory / operation / monitor',
                      'dependencies.py 统一鉴权依赖，路由级角色断言',
                      'client 端二级会话：选食堂后 JWT 追加 canteen_id，跨食堂请求被拦截',
                      '登录失败不透露账号是否存在（统一 401 响应）',
                    ]
                  },
                  {
                    tag:'INTEGRITY', title:'数据完整性',
                    color:'#51e7cb',
                    items:[
                      'Order.version 乐观锁：并发修改时版本冲突抛 409，防止竞态覆写',
                      'IdempotencyKey 表：收货签字等关键接口幂等保护，重放请求返回原始结果',
                      'items_snapshot_json：下单时冻结商品快照，后续商品改价不影响历史订单',
                      'order_snapshot_json：账单生成时冻结订单数据，结算后数据不可被篡改',
                      '双签名（warehouse_signature + carrier_signature）：Base64/DataURL，服务端校验长度下限',
                    ]
                  },
                  {
                    tag:'AUDIT', title:'操作审计与追踪',
                    color:'#9af7c8',
                    items:[
                      'AuditLog 表记录全部关键操作：操作人、IP、时间戳、操作前后快照',
                      'WebSocket /ws/monitor 实时推送订单状态变更与告警事件',
                      'flow_logs_json：工单流转日志，记录每个节点处理人与时间',
                      'OrderReceivingLine.confirmed_at：确认时间戳不可逆，防篡改',
                      '告警（Alert）系统：逾期/缺货/质量异常自动触发，状态机驱动关闭',
                    ]
                  },
                  {
                    tag:'INFRA', title:'基础设施安全',
                    color:'#c3f5ff',
                    items:[
                      'Docker 容器隔离：backend / frontend / mysql 三服务独立网络命名空间',
                      '敏感配置通过 .env 注入，不进入代码仓库（JWT_SECRET, DB_PASSWORD 等）',
                      'CORS 严格配置：仅允许 CORS_ORIGINS 列表中的域名跨源请求',
                      'MySQL 独立数据卷（./mysql_data），容器删除不丢数据',
                      'DEMO_MODE 标志：演示重置接口仅在 DEMO_MODE=true 时激活，生产不暴露',
                    ]
                  },
                ]" :key="p.tag">
                  <div class="sp-head" :style="{ borderColor: p.color + '50' }">
                    <code class="sp-tag" :style="{ color: p.color }">{{ p.tag }}</code>
                    <span class="sp-title">{{ p.title }}</span>
                  </div>
                  <ul class="sp-list">
                    <li v-for="item in p.items" :key="item">{{ item }}</li>
                  </ul>
                </div>
              </div>

              <h3 class="ip-sec">数据保护矩阵</h3>
              <table class="ip-table">
                <thead><tr><th>场景</th><th>保护机制</th><th>实现字段 / 模块</th></tr></thead>
                <tbody>
                  <tr v-for="r in [
                    ['订单并发修改', '乐观锁', 'Order.version'],
                    ['重复收货签字', '幂等键', 'IdempotencyKey + Idempotency-Key Header'],
                    ['商品价格变更', '快照冻结', 'items_snapshot_json'],
                    ['账单数据篡改', '结算快照', 'order_snapshot_json'],
                    ['越权跨端操作', 'RBAC 断言', 'dependencies.py get_current_user(role=...)'],
                    ['跨食堂数据泄露', '会话隔离', 'JWT canteen_id 字段强校验'],
                    ['操作不可溯源', '审计日志', 'AuditLog + flow_logs_json'],
                  ]" :key="r[0]">
                    <td>{{ r[0] }}</td><td>{{ r[1] }}</td><td><code>{{ r[2] }}</code></td>
                  </tr>
                </tbody>
              </table>
            </template>

            <!-- ───── 技术支持 ───── -->
            <template v-else-if="activePanel === 'support'">
              <p class="ip-lead">以下资源可帮助您快速上手演示环境、了解技术架构，或在本地部署。所有演示数据可随时一键重置。</p>

              <h3 class="ip-sec">演示账号</h3>
              <p class="ip-note">所有账号统一密码 <code class="hl-code">demo123</code>，点击登录页「业务端节点」可自动填充。</p>
              <table class="ip-table">
                <thead><tr><th>角色</th><th>用户名</th><th>主要功能入口</th></tr></thead>
                <tbody>
                  <tr v-for="a in [
                    ['运营端', 'operation001', '商品 / 分类 / 账号管理，工单审核，合约确认'],
                    ['监管端', 'monitor001', '实时仪表板，物流地图，告警中心，审计日志'],
                    ['供货商端', 'supplier001', '待配货订单，标签打印，发货，质检报告'],
                    ['配送商端', 'delivery001', '招标投标，智能分单，路线规划，车队管理'],
                    ['工厂端', 'factory001', '质检报告上传与审核'],
                    ['客户端①', 'client001', 'OCR/语音下单，合约管理，收货，账单'],
                    ['客户端②~⑥', 'client002 ~ client006', '相同功能，分属不同学校账号'],
                  ]" :key="a[0]">
                    <td>{{ a[0] }}</td><td><code>{{ a[1] }}</code></td><td>{{ a[2] }}</td>
                  </tr>
                </tbody>
              </table>

              <h3 class="ip-sec">快速启动流程</h3>
              <div class="qs-steps">
                <div class="qs-step" v-for="(s, i) in [
                  { n:'01', title:'运营端初始化', desc:'用 operation001 登录，检查商品分类、价格基准、账号列表是否就绪' },
                  { n:'02', title:'客户发起招标', desc:'用 client001 进入「合约管理」→「发起招标」，选分类范围与配送商，等待投标' },
                  { n:'03', title:'配送商投标', desc:'用 delivery001 进入「合约」→「待投标」，为各分类填写上浮率后提交' },
                  { n:'04', title:'运营端中标', desc:'回到 operation001「合约管理」，确认中标方，合约状态变为「已中标」' },
                  { n:'05', title:'客户下单', desc:'client001 选食堂 → 上传采购单图片（OCR）或语音输入，加入购物车，提交订单' },
                  { n:'06', title:'配送商分单', desc:'delivery001「待分单」→「智能分单」，选模式，预览分配方案，确认提交' },
                  { n:'07', title:'供货商发货', desc:'supplier001 查看「待配货」，打印标签，逐行确认备货，点「发货」' },
                  { n:'08', title:'收货与签字', desc:'client001「订单详情」→「前往称重」，在智能秤 Pad 上逐行称重，双方签名确认' },
                  { n:'09', title:'账单结算', desc:'收货后自动生成账单，双方在各自的「账单」模块确认金额，点「结清」' },
                ]" :key="s.n">
                  <div class="qs-n">{{ s.n }}</div>
                  <div class="qs-content">
                    <div class="qs-title">{{ s.title }}</div>
                    <div class="qs-desc">{{ s.desc }}</div>
                  </div>
                </div>
              </div>

              <h3 class="ip-sec">演示数据重置</h3>
              <div class="reset-box">
                <div class="reset-info">
                  <code class="reset-cmd">POST /api/demo/reset</code>
                  <span class="reset-note">仅在 DEMO_MODE=true 时有效（本环境默认开启）。清空全部业务数据（订单、分单、账单、合约等），重新注入初始演示数据，账号密码不变。适合在演示流程走完后一键恢复初始状态。</span>
                </div>
              </div>

              <h3 class="ip-sec">技术栈</h3>
              <div class="tech-cols">
                <div class="tech-col">
                  <div class="tc-head">后端</div>
                  <div class="tc-item" v-for="t in ['Python 3.11 + FastAPI（异步 ASGI）','SQLAlchemy 2 + Alembic 迁移','MySQL 8.0 + Docker 容器','WebSocket 实时推送','JWT HS256 + RBAC 鉴权']" :key="t">{{ t }}</div>
                </div>
                <div class="tech-col">
                  <div class="tc-head">前端（PC Web）</div>
                  <div class="tc-item" v-for="t in ['Vue 3 + Vite + Element Plus','Pinia 状态管理','vue-router 多端路由隔离','ECharts 可视化图表','高德地图 JS API']" :key="t">{{ t }}</div>
                </div>
                <div class="tech-col">
                  <div class="tc-head">移动端（智能秤）</div>
                  <div class="tc-item" v-for="t in ['Uni-app Vue 3 + TypeScript','Android 原生 AAR 串口插件','UVC 摄像头（USB 留痕）','BLE 蓝牙秤配对','HBuilderX 云打包 APK/WGT']" :key="t">{{ t }}</div>
                </div>
              </div>
            </template>

          </div>
        </div>
      </div>
    </Transition>

    <footer class="ae-footer">
      <div class="copy">© 2026 AETHERIS 终端系统. 保留所有权利。</div>
      <div class="links">
        <a href="#">隐私政策</a>
        <a href="#">服务条款</a>
        <a href="#">接口文档 (API)</a>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.ae-root {
  position: fixed;
  inset: 0;
  background: #0f131f;
  color: #dfe2f3;
  font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif;
  overflow: hidden;
}

.ae-bg-image {
  position: absolute;
  inset: 0;
  background-size: cover;
  background-position: center;
  opacity: 0.2;
  filter: grayscale(1);
  mix-blend-mode: screen;
  pointer-events: none;
}

.ae-canvas {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 1;
}

.ae-bg-gradient {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(circle at 20% 30%, rgba(0, 229, 255, 0.08) 0%, transparent 50%),
    radial-gradient(circle at 80% 70%, rgba(154, 255, 232, 0.05) 0%, transparent 50%);
}

.ae-particles {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.ae-particles .p {
  position: absolute;
  background: #00e5ff;
  border-radius: 50%;
  filter: blur(1px);
  opacity: 0.3;
  animation: float 20s infinite linear;
}
@keyframes float {
  0%   { transform: translateY(0)     translateX(0)   scale(1);   opacity: 0.1; }
  50%  { transform: translateY(-100px) translateX(50px) scale(1.5); opacity: 0.4; }
  100% { transform: translateY(-200px) translateX(-20px) scale(1); opacity: 0.1; }
}

.ae-header {
  position: relative;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 40px;
  backdrop-filter: blur(12px);
  background: rgba(15, 19, 31, 0.35);
}
.ae-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #c3f5ff;
}
.ae-logo {
  height: 40px;
  width: auto;
  object-fit: contain;
}
.ae-brand-text {
  font-family: 'Space Grotesk', 'Inter', sans-serif;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: #c3f5ff;
}
.ae-nav {
  display: flex;
  gap: 28px;
}
.ae-nav a {
  font-family: 'JetBrains Mono', 'Menlo', monospace;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #bac9cc;
  text-decoration: none;
  transition: color .25s;
}
.ae-nav a:hover { color: #c3f5ff; }
.ae-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  letter-spacing: 0.08em;
  color: #bac9cc;
  text-transform: uppercase;
}
.ae-status .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #51e7cb;
  box-shadow: 0 0 8px rgba(81, 231, 203, 0.8);
  animation: pulse 1.6s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.ae-main {
  position: relative;
  z-index: 2;
  height: calc(100vh - 64px - 64px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 40px;
  gap: 40px;
}

.ae-hero {
  flex: 1 1 auto;
  max-width: 640px;
}
.hero-title {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 48px;
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #c3f5ff;
  margin: 0 0 16px;
}
.hero-sub {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 26px;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: rgba(195, 245, 255, 0.85);
  margin: 0 0 24px;
}
.hero-desc {
  font-size: 16px;
  line-height: 1.7;
  color: #bac9cc;
  max-width: 520px;
}

.ae-panel {
  width: 440px;
  flex-shrink: 0;
  padding: 32px;
  border-radius: 12px;
  background: rgba(22, 27, 34, 0.65);
  border: 1px solid rgba(0, 229, 255, 0.18);
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.8);
  backdrop-filter: blur(16px);
}
.panel-head h3 {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 26px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: #c3f5ff;
  margin: 0 0 8px;
}
.panel-head h3 .en {
  color: #bac9cc;
  font-weight: 300;
  font-size: 22px;
  letter-spacing: 0.04em;
}
.panel-head p {
  margin: 0 0 24px;
  font-size: 14px;
  color: #bac9cc;
}

.panel-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.field { display: block; }
.lbl {
  display: block;
  margin-bottom: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #bac9cc;
}
.input-wrap {
  position: relative;
}
.input-wrap .ico {
  position: absolute;
  left: 16px;
  top: 50%;
  width: 20px;
  height: 20px;
  transform: translateY(-50%);
  color: #849396;
}
.input-wrap input {
  width: 100%;
  box-sizing: border-box;
  height: 48px;
  padding: 0 16px 0 48px;
  background: #171b28;
  border: 1px solid #3b494c;
  border-radius: 8px;
  color: #dfe2f3;
  font-size: 14px;
  outline: none;
  transition: all .25s;
}
.input-wrap input::placeholder { color: #6b7780; }
.input-wrap input:focus {
  border-color: #00e5ff;
  box-shadow: 0 0 15px rgba(0, 229, 255, 0.2);
}

.row-between {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
}
.row-between .hint {
  color: #bac9cc;
}
.row-between code {
  color: #c3f5ff;
  background: rgba(0, 229, 255, 0.08);
  padding: 1px 6px;
  border-radius: 3px;
  letter-spacing: 0.04em;
}
.row-between .link {
  color: #00e5ff;
  text-decoration: none;
  letter-spacing: 0.08em;
}
.row-between .link:hover { color: #c3f5ff; }

.btn-primary {
  margin-top: 8px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: #00e5ff;
  color: #00626e;
  border: none;
  border-radius: 8px;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.18em;
  cursor: pointer;
  box-shadow: 0 0 20px rgba(0, 229, 255, 0.4);
  transition: all .3s;
}
.btn-primary svg { width: 22px; height: 22px; }
.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 0 35px rgba(0, 229, 255, 0.6);
}
.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.nodes {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid rgba(59, 73, 76, 0.5);
}
.nodes-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #bac9cc;
  margin-bottom: 16px;
}
.nodes-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 8px;
  background: #262a37;
  border: 1px solid rgba(59, 73, 76, 0.4);
  border-radius: 4px;
  color: #bac9cc;
  cursor: pointer;
  transition: all .25s;
}
.node:hover:not(.disabled) {
  background: #313442;
  border-color: rgba(0, 229, 255, 0.4);
  color: #c3f5ff;
}
.node.active {
  background: rgba(0, 229, 255, 0.12);
  border-color: #00e5ff;
  color: #c3f5ff;
  box-shadow: 0 0 12px rgba(0, 229, 255, 0.25) inset;
}
.node.disabled {
  background: #171b28;
  border-color: rgba(59, 73, 76, 0.2);
  opacity: 0.4;
  cursor: not-allowed;
  filter: grayscale(1);
}
.node-ico {
  width: 20px;
  height: 20px;
}
.node-label {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.02em;
}

.ae-footer {
  position: relative;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 40px;
  height: 64px;
  box-sizing: border-box;
}
.ae-footer .copy,
.ae-footer .links a {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #bac9cc;
}
.ae-footer .links {
  display: flex;
  gap: 24px;
}
.ae-footer .links a {
  text-decoration: none;
  transition: color .25s;
}
.ae-footer .links a:hover { color: #c3f5ff; }

/* ── Info Panel Overlay ─────────────────────────────────── */
.ip-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(5, 8, 18, 0.72);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
}
.ip-modal {
  width: 100%;
  max-width: 1040px;
  max-height: 88vh;
  background: rgba(12, 16, 28, 0.96);
  border: 1px solid rgba(0, 229, 255, 0.16);
  border-radius: 14px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.9), 0 0 0 1px rgba(0,229,255,0.06);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.ip-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 22px 32px;
  border-bottom: 1px solid rgba(0, 229, 255, 0.1);
  background: rgba(0, 229, 255, 0.04);
  flex-shrink: 0;
}
.ip-head-left { display: flex; align-items: center; gap: 16px; }
.ip-tag {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.2em;
  color: #00e5ff;
  background: rgba(0, 229, 255, 0.1);
  border: 1px solid rgba(0, 229, 255, 0.25);
  padding: 3px 10px;
  border-radius: 4px;
  text-transform: uppercase;
}
.ip-title {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #c3f5ff;
  margin: 0;
}
.ip-close {
  background: none;
  border: 1px solid rgba(0, 229, 255, 0.18);
  color: #bac9cc;
  width: 36px;
  height: 36px;
  border-radius: 6px;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all .2s;
}
.ip-close:hover { background: rgba(0, 229, 255, 0.1); color: #c3f5ff; }

.ip-body {
  overflow-y: auto;
  flex: 1;
  padding: 32px;
  scrollbar-width: thin;
  scrollbar-color: rgba(0,229,255,0.2) transparent;
}
.ip-lead {
  font-size: 15px;
  line-height: 1.75;
  color: #bac9cc;
  max-width: 800px;
  margin: 0 0 28px;
}
.ip-sec {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #00e5ff;
  margin: 32px 0 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(0, 229, 255, 0.12);
}
.ip-note {
  font-size: 13px;
  color: #bac9cc;
  margin: 0 0 14px;
  line-height: 1.6;
}
.hl-code {
  color: #c3f5ff;
  background: rgba(0, 229, 255, 0.1);
  padding: 1px 7px;
  border-radius: 3px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
}

/* Stats bar */
.ov-stats {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.ov-stat {
  flex: 1;
  min-width: 120px;
  background: rgba(0, 229, 255, 0.05);
  border: 1px solid rgba(0, 229, 255, 0.12);
  border-radius: 8px;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.osn {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 32px;
  font-weight: 700;
  color: #c3f5ff;
  line-height: 1;
}
.osl {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  letter-spacing: 0.06em;
  color: #849396;
  text-transform: uppercase;
}

/* Flow track */
.flow-track {
  display: flex;
  align-items: flex-start;
  gap: 0;
  overflow-x: auto;
  padding-bottom: 8px;
  scrollbar-width: thin;
  scrollbar-color: rgba(0,229,255,0.15) transparent;
}
.flow-node {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.fn-card {
  width: 146px;
  background: rgba(15, 19, 31, 0.8);
  border: 1px solid rgba(0, 229, 255, 0.15);
  border-radius: 8px;
  padding: 14px 14px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.fn-idx {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 20px;
  font-weight: 700;
  line-height: 1;
}
.fn-title {
  font-size: 13px;
  font-weight: 700;
  color: #c3f5ff;
  letter-spacing: 0.04em;
}
.fn-desc {
  font-size: 11px;
  line-height: 1.55;
  color: #849396;
}
.fn-entity {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: rgba(0, 229, 255, 0.5);
  letter-spacing: 0.04em;
  margin-top: 2px;
}
.fn-arrow {
  font-size: 20px;
  color: rgba(0, 229, 255, 0.3);
  padding: 0 6px;
  flex-shrink: 0;
  margin-top: -24px;
}

/* Role grid */
.role-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.role-card {
  background: rgba(15, 19, 31, 0.8);
  border: 1px solid rgba(0, 229, 255, 0.1);
  border-radius: 8px;
  padding: 16px;
}
.rc-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.rc-code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.08em;
  color: #00e5ff;
  background: rgba(0, 229, 255, 0.1);
  padding: 2px 7px;
  border-radius: 3px;
  flex-shrink: 0;
}
.rc-name {
  font-size: 13px;
  font-weight: 700;
  color: #c3f5ff;
}
.rc-desc {
  font-size: 12px;
  color: #849396;
  margin: 0 0 10px;
  line-height: 1.5;
}
.rc-feats {
  margin: 0;
  padding-left: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.rc-feats li {
  font-size: 11px;
  color: #bac9cc;
  line-height: 1.45;
}

/* Data flow */
.data-flow {
  display: flex;
  flex-direction: column;
  gap: 1px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(0, 229, 255, 0.1);
}
.df-row {
  display: flex;
  align-items: baseline;
  gap: 16px;
  padding: 12px 16px;
  background: rgba(15, 19, 31, 0.7);
}
.df-row:nth-child(even) { background: rgba(0, 229, 255, 0.03); }
.df-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  letter-spacing: 0.06em;
  color: #51e7cb;
  min-width: 88px;
  flex-shrink: 0;
}
.df-val {
  font-size: 12px;
  color: #bac9cc;
  line-height: 1.5;
}

/* Security pillars */
.sec-pillars {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.sec-pillar {
  background: rgba(15, 19, 31, 0.8);
  border-radius: 8px;
  padding: 18px;
  border: 1px solid rgba(0, 229, 255, 0.08);
}
.sp-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid;
  margin-bottom: 14px;
}
.sp-tag {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.14em;
  background: rgba(0,229,255,0.06);
  padding: 3px 9px;
  border-radius: 3px;
  flex-shrink: 0;
}
.sp-title {
  font-size: 13px;
  font-weight: 700;
  color: #c3f5ff;
}
.sp-list {
  margin: 0;
  padding-left: 16px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.sp-list li {
  font-size: 12px;
  color: #bac9cc;
  line-height: 1.5;
}

/* Table */
.ip-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.ip-table th {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #849396;
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid rgba(0, 229, 255, 0.12);
}
.ip-table td {
  padding: 10px 12px;
  color: #bac9cc;
  border-bottom: 1px solid rgba(0, 229, 255, 0.05);
  vertical-align: top;
  line-height: 1.5;
}
.ip-table tr:hover td { background: rgba(0, 229, 255, 0.03); }
.ip-table code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #51e7cb;
  background: rgba(81, 231, 203, 0.08);
  padding: 1px 6px;
  border-radius: 3px;
}

/* Quick start */
.qs-steps {
  display: flex;
  flex-direction: column;
  gap: 1px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(0, 229, 255, 0.1);
}
.qs-step {
  display: flex;
  align-items: flex-start;
  gap: 18px;
  padding: 12px 16px;
  background: rgba(15, 19, 31, 0.7);
}
.qs-step:nth-child(even) { background: rgba(0, 229, 255, 0.03); }
.qs-n {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  letter-spacing: 0.06em;
  color: #00e5ff;
  opacity: 0.6;
  min-width: 24px;
  flex-shrink: 0;
  padding-top: 2px;
}
.qs-title {
  font-size: 13px;
  font-weight: 700;
  color: #c3f5ff;
  margin-bottom: 3px;
}
.qs-desc { font-size: 12px; color: #849396; line-height: 1.5; }

/* Reset box */
.reset-box {
  background: rgba(0, 229, 255, 0.04);
  border: 1px solid rgba(0, 229, 255, 0.14);
  border-radius: 8px;
  padding: 18px 20px;
}
.reset-cmd {
  display: block;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  color: #c3f5ff;
  background: rgba(0, 229, 255, 0.1);
  padding: 6px 12px;
  border-radius: 4px;
  margin-bottom: 12px;
  width: fit-content;
}
.reset-note { font-size: 13px; color: #849396; line-height: 1.6; }

/* Tech cols */
.tech-cols {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}
.tech-col {
  background: rgba(15, 19, 31, 0.8);
  border: 1px solid rgba(0, 229, 255, 0.1);
  border-radius: 8px;
  padding: 16px;
}
.tc-head {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #00e5ff;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(0, 229, 255, 0.1);
}
.tc-item {
  font-size: 12px;
  color: #bac9cc;
  padding: 5px 0;
  border-bottom: 1px solid rgba(0, 229, 255, 0.04);
  line-height: 1.4;
}
.tc-item:last-child { border-bottom: none; }

/* Panel transition */
.ip-enter-active, .ip-leave-active { transition: opacity .22s, transform .22s; }
.ip-enter-from, .ip-leave-to { opacity: 0; transform: scale(0.97); }

@media (max-width: 1180px) {
  .ae-hero { display: none; }
  .ae-main { justify-content: center; }
}
@media (max-width: 860px) {
  .role-grid, .sec-pillars, .tech-cols { grid-template-columns: 1fr; }
  .ov-stats { gap: 8px; }
  .ov-stat { min-width: 100px; }
  .ip-body { padding: 20px; }
}
@media (max-width: 720px) {
  .ae-nav { display: none; }
  .ae-header,
  .ae-footer { padding-left: 16px; padding-right: 16px; }
  .ae-main { padding: 0 16px; }
  .ae-panel { width: 100%; padding: 24px; }
  .ip-overlay { padding: 12px; }
  .ip-head { padding: 16px 20px; }
  .ip-body { padding: 16px; }
  .role-grid { grid-template-columns: 1fr; }
}
</style>
