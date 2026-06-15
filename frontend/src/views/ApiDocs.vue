<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { ENDPOINT_DETAIL, CORE_RESPONSES } from './apiDocsData'

const METHOD_COLOR = { GET: '#00e5ff', POST: '#51e7cb', PUT: '#ffd166', DELETE: '#ff7a90', PATCH: '#c4b5fd' }

// 端点展开详情
const expanded = ref(new Set())
const keyOf = (e) => `${e.m} ${e.p}`
const isOpen = (e) => expanded.value.has(keyOf(e))
const toggle = (e) => {
  const k = keyOf(e); const s = new Set(expanded.value)
  s.has(k) ? s.delete(k) : s.add(k); expanded.value = s
}
const detailOf = (e) => ENDPOINT_DETAIL[keyOf(e)] || { auth: true, params: [], resNote: '返回业务数据' }
const resOf = (e) => CORE_RESPONSES[keyOf(e)] || null
const PARAM_IN = { body: 'Body', query: 'Query', path: 'Path', header: 'Header' }

// 字段名 → 中文说明（跨端点复用，一张表覆盖大多数参数）
const FIELD_LABELS = {
  page: '页码', page_size: '每页条数', keyword: '关键词搜索', status: '状态', limit_price: '限价',
  name: '名称', remark: '备注', notes: '备注', title: '标题', content: '内容', message: '消息内容',
  type: '类型', mode: '分单策略 eco/normal/sport', force: '强制（忽略异常校验）', date: '日期', source: '来源',
  username: '登录账号', password: '登录密码', old_password: '旧密码', new_password: '新密码',
  roles: '角色', user_ids: '用户 id 列表', session_id: '会话 id',
  order_id: '订单 id', order_ids: '订单 id 列表', order_no: '订单号',
  delivery_id: '配送商 id', delivery_ids: '配送商 id 列表', supplier_id: '供货商 id',
  supplier_name: '供货商名称', supplier_username: '供货商登录名',
  canteen_id: '食堂 id', school_client_id: '所属学校客户 id',
  items: '订单行（商品 / 数量 / 单价）', allocations: '分单行明细', allocation_ids: '分单行 id 列表',
  product_id: '商品 id', product: '商品名', product_name: '商品名称', goods_sn: '商品编码',
  quantity: '数量', unit: '单位', unit_price: '单价', amount: '金额', reference_price: '参考价',
  spec: '规格', standard_type: '标品 / 非标', brand: '品牌', origin: '产地',
  delivery_address: '收货地址', delivery_lng: '收货经度', delivery_lat: '收货纬度',
  expected_delivery_date: '期望配送日', expected_delivery_slot: '期望配送时段',
  expected_delivery_date_start: '配送日（起）', expected_delivery_date_end: '配送日（止）',
  created_date_start: '下单日（起）', created_date_end: '下单日（止）', delivery_date: '配送日',
  service_duration_min: '服务时长（分钟）', is_designated_factory: '是否指定厂家',
  designated_factory_id: '指定厂家 id', contract_categories_only: '仅合约内分类',
  quota_window: '配额窗口 week/month/quarter', allow_split: '是否允许拆分',
  geofence_policy: '电子围栏策略 normal/strict',
  tender_id: '招标 id', period_start: '合约期（起）', period_end: '合约期（止）', period_label: '账期标签',
  float_rate_min: '上浮率下限', float_rate_max: '上浮率上限', discount_rate: '折扣点',
  finance_rate: '财务费率', finance_code: '财务类别码', category_rates: '分类上浮率',
  statement_id: '对账单 id', direction: '方向（应收 / 应付）', counterparty_keyword: '对手方关键词',
  statement_scope: '对账范围', scope: '范围',
  category: '分类', category_ids: '分类 id 列表', category1_id: '一级分类 id', category2_id: '二级分类 id',
  sort_order: '排序号', unit_weight_kg: '单位重量（kg）', weight: '重量', volume_adjust_factor: '体积系数',
  length_cm: '长（cm）', width_cm: '宽（cm）', height_cm: '高（cm）',
  image_list_json: '图片列表', detail_images_json: '详情图列表', logo: '图标', slogo: '副标识',
  manufacturer: '生产厂家', external_url: '外链',
  ticket_id: '工单 id', alert_id: '告警 id', level: '级别', priority: '优先级', resolution: '处理结论',
  overdue: '是否逾期', target_type: '目标类型', reported_at: '上报时间',
  vehicle_id: '车辆 id', vehicle_no: '车牌号', device_code: '设备编码', device_name: '设备名',
  driver_id: '司机 id', trip_id: '车次 id', stop_id: '站点 id', speed: '速度',
  lng: '经度', lat: '纬度', address: '地址', departure_time: '发车时间',
  planning_date: '排线日期', plan_date: '计划日期', user_disabled_vehicle_nos: '禁用车牌',
  barcode_value: '条码值', stream: '是否流式返回', messages: '对话消息', text: '文本',
  model: '模型', epochs: '训练轮数', batch_size: '批大小', min_samples_per_class: '每类最少样本',
  quality_report_mode: '质检报告模式', object_name: '对象路径', limit: '数量上限', number: '编号',
}
// 参数中文说明：优先字典 → 其次规范里有意义的描述 → 否则空
const fieldLabel = (pm) => {
  if (FIELD_LABELS[pm.name]) return FIELD_LABELS[pm.name]
  const d = (pm.desc || '').toLowerCase().replace(/\s+/g, '')
  const n = pm.name.toLowerCase().replace(/_/g, '')
  return d && d !== n ? pm.desc : ''
}

// 文档分区（手写说明）
const docNav = [
  { id: 'start', label: '快速上手' },
  { id: 'conventions', label: '通用约定' },
  { id: 'example', label: '流程示例' },
]

// 端点参考（精选，逐个对照 backend/routers/*.py 真实存在）
const apiGroups = [
  { id: 'g-auth', label: '认证 / 会话', tag: 'AUTH', color: '#00e5ff', eps: [
    { m: 'POST', p: '/api/auth/login', d: '账号密码登录，返回 JWT token 与角色 role' },
    { m: 'GET', p: '/api/auth/me', d: '获取当前登录用户信息' },
    { m: 'POST', p: '/api/auth/change-password', d: '修改登录密码' },
    { m: 'POST', p: '/api/client/canteen-session', d: '客户选食堂，换发携带 canteen_id 的会话' },
  ] },
  { id: 'g-client', label: '客户端 · 食堂', tag: 'CLIENT', color: '#00e5ff', eps: [
    { m: 'GET', p: '/api/client/dashboard', d: '食堂采购看板（趋势 / 品类 / 常购）' },
    { m: 'GET', p: '/api/client/canteens', d: '当前账号下的履约食堂列表' },
    { m: 'GET', p: '/api/orders/products/search', d: '按已中标合约检索可下单商品' },
    { m: 'POST', p: '/api/ocr/parse-order', d: '采购单拍照 OCR → 结构化订单行' },
    { m: 'POST', p: '/api/voice/parse-order', d: '语音 / 文本转单 → 商品与数量' },
    { m: 'GET', p: '/api/client/bills', d: '客户账单列表' },
  ] },
  { id: 'g-order', label: '订单生命周期', tag: 'ORDER', color: '#51e7cb', eps: [
    { m: 'POST', p: '/api/orders', d: '下单（快照冻结商品与价格）→ 状态「下单」' },
    { m: 'GET', p: '/api/orders/{id}', d: '订单详情' },
    { m: 'POST', p: '/api/orders/{id}/print-allocation-labels', d: '供货商行级标签云打印' },
    { m: 'POST', p: '/api/orders/{id}/ship', d: '供货商发货：本户分单行 →「已出库」' },
    { m: 'POST', p: '/api/orders/{id}/pickup', d: '配送商取货 → 状态「发货」' },
    { m: 'POST', p: '/api/orders/{id}/deliver', d: '送达 → 状态「收货」' },
    { m: 'POST', p: '/api/orders/{id}/receive', d: '称重双签收货确认 → 自动生成账单' },
    { m: 'POST', p: '/api/orders/{id}/settle', d: '结算 → 状态「已结算」' },
    { m: 'PUT', p: '/api/orders/{id}/cancel', d: '取消订单' },
    { m: 'GET', p: '/api/orders/{id}/logistics-tracking', d: '订单物流追踪' },
  ] },
  { id: 'g-delivery', label: '配送商 · 枢纽', tag: 'DELIVERY', color: '#51e7cb', eps: [
    { m: 'POST', p: '/api/delivery/smart-split/preview', d: '智能分单预览（5 因子 × 3 策略）' },
    { m: 'POST', p: '/api/delivery/smart-split/commit', d: '确认提交分单方案' },
    { m: 'POST', p: '/api/delivery/route-plan', d: '高德多途经点路线规划' },
    { m: 'GET', p: '/api/delivery/vehicles/restriction/beijing', d: '北京车辆限行查询' },
    { m: 'POST', p: '/api/delivery/vehicles/{id}/beidou-location', d: '北斗车辆实时定位' },
    { m: 'GET', p: '/api/delivery/geofences', d: '电子围栏列表' },
    { m: 'GET', p: '/api/delivery/warehouses/{id}/elitech/realtime', d: '冷库温湿度实时' },
    { m: 'GET', p: '/api/delivery/workbench', d: '配送商工作台汇总' },
  ] },
  { id: 'g-supply', label: '供货商 / 厂家 / 质检', tag: 'SUPPLY', color: '#ea9a51', eps: [
    { m: 'GET', p: '/api/supplier/home', d: '供货商今日待办（待发货 / 应收）' },
    { m: 'GET', p: '/api/supplier/orders', d: '配送分包订单列表' },
    { m: 'PUT', p: '/api/supplier/product-quotes', d: '维护商品报价' },
    { m: 'GET', p: '/api/factory/orders', d: '厂家：指定商品订单' },
    { m: 'POST', p: '/api/quality-reports/by-allocation', d: '按分单上传质检报告' },
    { m: 'GET', p: '/api/quality-reports/by-order/{id}', d: '订单质检报告' },
  ] },
  { id: 'g-contract', label: '合约 · 招投标', tag: 'TENDER', color: '#00e5ff', eps: [
    { m: 'POST', p: '/api/contracts/tender', d: '客户发起招标' },
    { m: 'POST', p: '/api/contracts/tender/{id}/bid', d: '配送商投标（上浮率报价）' },
    { m: 'POST', p: '/api/contracts/tender/{id}/award', d: '定标，合约置「已中标」' },
    { m: 'GET', p: '/api/contracts/list', d: '合约列表' },
  ] },
  { id: 'g-bills', label: '账务清结', tag: 'BILLING', color: '#9af7c8', eps: [
    { m: 'GET', p: '/api/bills/statements', d: '账期对账单（应收 / 应付）' },
    { m: 'POST', p: '/api/bills/statements/{id}/confirm', d: '确认对账单' },
    { m: 'POST', p: '/api/bills/statements/{id}/settle', d: '结清对账单' },
    { m: 'GET', p: '/api/bills/cycles', d: '账期周期配置' },
    { m: 'GET', p: '/api/bills/overview', d: '账务总览' },
  ] },
  { id: 'g-operation', label: '运营端', tag: 'OPS', color: '#00e5ff', eps: [
    { m: 'GET', p: '/api/operation/dashboard', d: '运营看板' },
    { m: 'POST', p: '/api/operation/products', d: '新增商品' },
    { m: 'POST', p: '/api/operation/client-canteens', d: '客户食堂建档' },
    { m: 'GET', p: '/api/operation/tickets', d: '工单列表' },
    { m: 'POST', p: '/api/operation/tickets/{id}/resolve', d: '处理 / 关闭工单' },
  ] },
  { id: 'g-monitor', label: '监管端', tag: 'MONITOR', color: '#00e5ff', eps: [
    { m: 'GET', p: '/api/monitor/neural/overview', d: '核心态势驾驶舱' },
    { m: 'GET', p: '/api/monitor/neural/audit-chain', d: '全链路审计链' },
    { m: 'GET', p: '/api/monitor/neural/mining', d: '数据智能挖掘' },
    { m: 'GET', p: '/api/monitor/alerts', d: '告警中心' },
    { m: 'PUT', p: '/api/monitor/alerts/{id}/close', d: '关闭告警' },
    { m: 'GET', p: '/api/monitor/audit-logs', d: '审计日志' },
    { m: 'POST', p: '/api/monitor/broadcasts', d: '指挥广播下发' },
  ] },
  { id: 'g-ai', label: '数据智能内核', tag: 'AI', color: '#a78bfa', dim: true, eps: [
    { m: 'POST', p: '/api/chat/stream', d: 'AI 流式对话（qwen · 意图路由）' },
    { m: 'POST', p: '/api/zgncpjgw/analytics/briefing', d: 'AI 行情日报（研报式结构）' },
    { m: 'GET', p: '/api/zgncpjgw/analytics/forecast/status', d: '价格集成预测状态' },
    { m: 'POST', p: '/api/xinfadi/crawl', d: '新发地行情抓取' },
    { m: 'POST', p: '/api/xinfadi/predict/retrain', d: '价格预测模型重训' },
    { m: 'POST', p: '/api/smart-scale-recognition/recognize', d: '智能秤图像识别商品' },
    { m: 'POST', p: '/api/smart-scale-recognition/train', d: '识别模型训练' },
  ] },
  { id: 'g-hardware', label: '硬件端 · 分拣 / 司机 / 秤', tag: 'DEVICE', color: '#a78bfa', dim: true, eps: [
    { m: 'GET', p: '/api/delivery-sort/today', d: '分拣 PDA：今日分拣任务' },
    { m: 'POST', p: '/api/delivery-sort/scan', d: '分拣 PDA：扫码收货分拣' },
    { m: 'POST', p: '/api/driver/login', d: '司机端登录' },
    { m: 'GET', p: '/api/driver/trips/today', d: '司机端：今日车次' },
    { m: 'POST', p: '/api/driver/trips/{id}/start', d: '司机端：发车' },
    { m: 'POST', p: '/api/driver/stops/{id}/deliver', d: '司机端：到点送达' },
  ] },
  { id: 'g-system', label: '系统 / 通用', tag: 'SYSTEM', color: '#7f93a0', eps: [
    { m: 'GET', p: '/api/system/healthz', d: '存活健康检查' },
    { m: 'GET', p: '/api/system/readyz', d: '就绪检查（依赖可用）' },
    { m: 'GET', p: '/api/system/downloads/manifest', d: 'APK 下载动态清单' },
    { m: 'GET', p: '/api/system/files/minio/{name}', d: 'MinIO 图片统一代理' },
  ] },
]

const navItems = computed(() => [
  ...docNav.map(d => ({ id: d.id, label: d.label, doc: true })),
  ...apiGroups.map(g => ({ id: g.id, label: g.label, color: g.color, count: g.eps.length })),
])

const activeId = ref('start')
let observer = null
const scrollTo = (id) => {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const loginExample = `POST /api/auth/login
Content-Type: application/json

{ "username": "client001", "password": "demo123" }

# 200 OK
{ "token": "eyJhbGciOiJIUzI1NiI...", "role": "client" }

# 后续所有请求携带:
Authorization: Bearer <token>`

const orderExample = `POST /api/orders        # Authorization: Bearer <client token>

{
  "delivery_id": 3,
  "expected_delivery_date": "2026-06-04",
  "expected_delivery_slot": "09:00-10:00",
  "delivery_address": "北京市海淀区 XX 学校",
  "items": [
    { "product_id": 2041, "quantity": 20, "unit_price": 6.80 }
  ]
}

# 200 OK
{ "id": 2536, "order_no": "OD0304...", "status": "下单",
  "total_amount": 136.00, "version": 1 }`

const errorExample = `# 业务错误 (4xx)
{ "detail": "配送时段须距当前时间至少 2 小时" }

# 参数校验失败 (422)
{ "detail": [
    { "loc": ["body", "items"], "msg": "field required", "type": "value_error.missing" }
] }`

const statusCodes = [
  ['200', '成功', '请求正常返回'],
  ['400', '业务错误', '参数非法 / 状态机不允许的操作'],
  ['401', '未认证', 'token 缺失 / 失效，需重新登录'],
  ['403', '无权限', '角色或归属校验未通过（越权）'],
  ['404', '不存在', '资源未找到'],
  ['409', '版本冲突', '乐观锁 version 冲突，需重新加载后重试'],
  ['422', '校验失败', '请求体字段校验未通过（数组明细）'],
]

onMounted(() => {
  observer = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting) activeId.value = e.target.id
    }
  }, { rootMargin: '-15% 0px -75% 0px', threshold: 0 })
  document.querySelectorAll('[data-doc-section]').forEach(el => observer.observe(el))
})
onUnmounted(() => observer?.disconnect())
</script>

<template>
  <div class="docs-root">
    <div class="docs-bg" aria-hidden="true"></div>

    <!-- 顶栏 -->
    <header class="docs-top">
      <div class="brand">
        <span class="brand-mark">FE</span>
        <div class="brand-txt">
          <strong>FoodLink Express</strong>
          <span class="brand-sub">API REFERENCE · 接口文档</span>
        </div>
      </div>
      <div class="top-right">
        <span class="base-chip">BASE · <code>/api</code></span>
        <a class="back-login" href="/login">← 返回登录</a>
      </div>
    </header>

    <div class="docs-shell">
      <!-- 左侧导航 -->
      <aside class="docs-side">
        <div class="side-inner">
          <p class="side-cap">指南</p>
          <a v-for="n in navItems.filter(x => x.doc)" :key="n.id"
             class="side-link" :class="{ active: activeId === n.id }"
             @click.prevent="scrollTo(n.id)" href="#">{{ n.label }}</a>
          <p class="side-cap">端点参考</p>
          <a v-for="n in navItems.filter(x => !x.doc)" :key="n.id"
             class="side-link grp" :class="{ active: activeId === n.id }"
             @click.prevent="scrollTo(n.id)" href="#">
            <i class="dot" :style="{ background: n.color }"></i>{{ n.label }}<span class="ct">{{ n.count }}</span>
          </a>
        </div>
      </aside>

      <!-- 主内容 -->
      <main class="docs-main">
        <!-- Hero -->
        <section class="hero">
          <p class="eyebrow">FOODLINK EXPRESS · 全域供应链开放接口</p>
          <h1>接口文档 <span>API Reference</span></h1>
          <p class="hero-lead">面向 9 端协同供应链平台的 REST / JSON 接口。统一基址 <code>/api</code>，JWT Bearer 鉴权，覆盖招标定价、智能分单、北斗配送、称重收货、多方清结与数据智能全链路。</p>
          <div class="hero-stats">
            <div class="hs"><b>335</b><span>API 路径</span></div>
            <div class="hs"><b>27</b><span>业务模块</span></div>
            <div class="hs"><b>103</b><span>数据模型</span></div>
            <div class="hs"><b>JWT</b><span>Bearer 鉴权</span></div>
            <div class="hs"><b>JSON</b><span>RESTful</span></div>
          </div>
        </section>

        <!-- 快速上手 -->
        <section id="start" data-doc-section class="doc-block">
          <h2 class="block-h">快速上手</h2>
          <p class="block-p">所有业务接口需先登录拿到 JWT。登录后把 token 放进 <code>Authorization</code> 头即可访问。客户端登录后还需选择履约食堂，换发携带 <code>canteen_id</code> 的会话——订单 / 账单按所选食堂隔离。</p>
          <pre class="code">{{ loginExample }}</pre>
          <div class="note">
            <span class="note-tag">演示</span>所有演示账号统一密码 <code class="hl">demo123</code>（client001 / delivery001 / supplier001 / factory001 / operation001 / monitor001 …）。
          </div>
        </section>

        <!-- 通用约定 -->
        <section id="conventions" data-doc-section class="doc-block">
          <h2 class="block-h">通用约定</h2>
          <div class="conv-grid">
            <div class="conv"><code>BASE</code><b>统一基址</b><p>全部接口前缀 <code>/api</code>，请求 / 响应均为 JSON（UTF-8）。</p></div>
            <div class="conv"><code>AUTH</code><b>鉴权</b><p><code>Authorization: Bearer &lt;token&gt;</code>；客户端二级会话携带 <code>canteen_id</code>。</p></div>
            <div class="conv"><code>PAGE</code><b>分页</b><p>列表类接口用 <code>page</code> / <code>page_size</code> 查询参数翻页。</p></div>
            <div class="conv"><code>IDEM</code><b>幂等</b><p>收货 / 结算等关键写接口支持 <code>Idempotency-Key</code> 头，重放返回原结果。</p></div>
            <div class="conv"><code>LOCK</code><b>乐观锁</b><p>订单携带 <code>version</code>，并发修改冲突返回 <code>409</code>。</p></div>
            <div class="conv"><code>ERR</code><b>错误体</b><p>统一 <code>{ "detail": ... }</code>；参数校验失败为 <code>422</code> 明细数组。</p></div>
          </div>
          <pre class="code">{{ errorExample }}</pre>
          <table class="st-table">
            <thead><tr><th>状态码</th><th>含义</th><th>说明</th></tr></thead>
            <tbody>
              <tr v-for="s in statusCodes" :key="s[0]">
                <td><code class="st-code" :class="{ ok: s[0]==='200', warn: ['400','409','422'].includes(s[0]), bad: ['401','403','404'].includes(s[0]) }">{{ s[0] }}</code></td>
                <td>{{ s[1] }}</td><td>{{ s[2] }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <!-- 流程示例 -->
        <section id="example" data-doc-section class="doc-block">
          <h2 class="block-h">流程示例 · 下单</h2>
          <p class="block-p">客户在已中标合约范围内选品下单，服务端按合约口径重算金额并冻结商品快照，返回订单号与初始状态「下单」。</p>
          <pre class="code">{{ orderExample }}</pre>
        </section>

        <!-- 端点参考分组 -->
        <section v-for="g in apiGroups" :key="g.id" :id="g.id" data-doc-section class="api-group" :class="{ dim: g.dim }">
          <div class="grp-head">
            <span class="grp-tag" :style="{ color: g.color, borderColor: g.color + '55' }">{{ g.tag }}</span>
            <h2 class="grp-title">{{ g.label }}</h2>
            <span class="grp-count">{{ g.eps.length }} 接口</span>
          </div>
          <div class="ep-list">
            <div class="ep-item" v-for="(e, i) in g.eps" :key="i" :class="{ open: isOpen(e) }">
              <button type="button" class="ep" @click="toggle(e)">
                <span class="ep-method" :style="{ color: METHOD_COLOR[e.m], borderColor: METHOD_COLOR[e.m] + '55', background: METHOD_COLOR[e.m] + '12' }">{{ e.m }}</span>
                <code class="ep-path">{{ e.p }}</code>
                <span class="ep-desc">{{ e.d }}</span>
                <span class="ep-caret">▸</span>
              </button>
              <div v-if="isOpen(e)" class="ep-detail">
                <div class="det-meta">
                  <span class="det-auth" :class="{ pub: !detailOf(e).auth }">{{ detailOf(e).auth ? '🔒 需 Bearer 鉴权' : '◎ 公开访问' }}</span>
                  <span v-if="detailOf(e).summary" class="det-sum">{{ detailOf(e).summary }}</span>
                </div>

                <template v-if="detailOf(e).params && detailOf(e).params.length">
                  <p class="det-h">请求参数</p>
                  <table class="det-table">
                    <thead><tr><th>参数</th><th>位置</th><th>必填</th><th>类型</th><th>说明</th></tr></thead>
                    <tbody>
                      <tr v-for="pm in detailOf(e).params" :key="pm.name">
                        <td><code class="pm-name">{{ pm.name }}</code></td>
                        <td><span class="pm-in">{{ PARAM_IN[pm.in] || pm.in }}</span></td>
                        <td><span :class="pm.required ? 'pm-req' : 'pm-opt'">{{ pm.required ? '必填' : '可选' }}</span></td>
                        <td class="pm-type">{{ pm.type }}</td>
                        <td class="pm-label">{{ fieldLabel(pm) || '—' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </template>
                <p v-else class="det-note">无请求参数。</p>

                <template v-if="detailOf(e).reqExample">
                  <p class="det-h">请求示例</p>
                  <pre class="code sm">{{ detailOf(e).reqExample }}</pre>
                </template>

                <p class="det-h">响应{{ resOf(e) ? '示例' : '说明' }}</p>
                <pre v-if="resOf(e)" class="code sm">{{ resOf(e) }}</pre>
                <p v-else class="det-note">{{ detailOf(e).resNote }}（成功 <code>200</code>；错误见<a href="#conventions" @click.prevent="scrollTo('conventions')">通用约定</a>）。</p>
              </div>
            </div>
          </div>
        </section>

        <footer class="docs-foot">
          <span>© 2026 FoodLink Express · 食迅易联</span>
          <span class="foot-note">本文档为精选接口参考；端点与参数对照真实代码维护。</span>
        </footer>
      </main>
    </div>
  </div>
</template>

<style scoped>
.docs-root {
  position: relative;
  min-height: 100vh;
  background: #070b14;
  color: #d9e6ea;
  font-family: 'Space Grotesk', 'Plus Jakarta Sans', -apple-system, system-ui, sans-serif;
}
.docs-bg {
  position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background:
    radial-gradient(circle at 78% -10%, rgba(0, 229, 255, 0.10), transparent 42%),
    radial-gradient(circle at 12% 108%, rgba(129, 140, 248, 0.09), transparent 40%),
    linear-gradient(180deg, #070b14 0%, #0a1120 60%, #070d18 100%);
}
.docs-bg::after {
  content: ''; position: absolute; inset: 0;
  background-image: linear-gradient(rgba(0,229,255,.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,229,255,.03) 1px, transparent 1px);
  background-size: 46px 46px;
  -webkit-mask-image: radial-gradient(ellipse 80% 60% at 60% 0%, #000, transparent 75%);
  mask-image: radial-gradient(ellipse 80% 60% at 60% 0%, #000, transparent 75%);
}

/* 顶栏 */
.docs-top {
  position: sticky; top: 0; z-index: 20;
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 30px;
  background: rgba(7, 12, 22, 0.82); backdrop-filter: blur(14px);
  border-bottom: 1px solid rgba(0, 229, 255, 0.12);
}
.brand { display: flex; align-items: center; gap: 12px; }
.brand-mark {
  width: 36px; height: 36px; border-radius: 8px; display: grid; place-items: center;
  font-weight: 800; font-size: 14px; letter-spacing: .02em; color: #04141a;
  background: linear-gradient(135deg, #00e5ff, #51e7cb);
}
.brand-txt { display: flex; flex-direction: column; line-height: 1.2; }
.brand-txt strong { font-size: 15px; color: #eaf6fa; letter-spacing: .03em; }
.brand-sub { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: .18em; color: #6f8a92; }
.top-right { display: flex; align-items: center; gap: 16px; }
.base-chip { font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: .1em; color: #8fb6bf; }
.base-chip code { color: #00e5ff; }
.back-login {
  font-size: 13px; color: #cdeef5; text-decoration: none;
  border: 1px solid rgba(0, 229, 255, 0.3); border-radius: 8px; padding: 7px 14px;
  transition: all .15s;
}
.back-login:hover { background: rgba(0, 229, 255, 0.12); }

/* 布局 */
.docs-shell { position: relative; z-index: 1; display: flex; max-width: 1320px; margin: 0 auto; }
.docs-side { width: 248px; flex-shrink: 0; }
.side-inner {
  position: sticky; top: 64px; max-height: calc(100vh - 64px); overflow-y: auto;
  padding: 26px 14px 40px 26px;
  scrollbar-width: thin; scrollbar-color: rgba(0,229,255,.2) transparent;
}
.side-cap {
  font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: .2em;
  text-transform: uppercase; color: #5f7984; margin: 18px 0 8px;
}
.side-cap:first-child { margin-top: 0; }
.side-link {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; color: #a7c0c7; text-decoration: none;
  padding: 7px 12px; border-radius: 7px; border-left: 2px solid transparent;
  transition: all .14s; cursor: pointer;
}
.side-link:hover { color: #eaf6fa; background: rgba(0, 229, 255, 0.05); }
.side-link.active {
  color: #eaf6fa; background: rgba(0, 229, 255, 0.1);
  border-left-color: #00e5ff;
}
.side-link .dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.side-link .ct {
  margin-left: auto; font-family: 'JetBrains Mono', monospace; font-size: 10px;
  color: #62808a; background: rgba(255,255,255,.04); border-radius: 20px; padding: 1px 7px;
}

/* 主内容 */
.docs-main { flex: 1; min-width: 0; padding: 30px 40px 80px; }

.hero { padding: 24px 0 8px; }
.eyebrow { font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: .18em; color: rgba(0,229,255,.75); margin: 0 0 12px; }
.hero h1 {
  margin: 0; font-size: clamp(30px, 4vw, 44px); font-weight: 800; letter-spacing: .01em;
  background: linear-gradient(110deg, #eafcff, #7fe9ff 55%, #818cf8 120%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.hero h1 span { font-size: .5em; font-weight: 600; -webkit-text-fill-color: #6f8a92; margin-left: 10px; letter-spacing: .12em; }
.hero-lead { max-width: 760px; font-size: 14.5px; line-height: 1.8; color: #b9d2d9; margin: 16px 0 22px; }
.hero-lead code, code { font-family: 'JetBrains Mono', monospace; color: #7df0db; background: rgba(0,229,255,.08); padding: 1px 6px; border-radius: 4px; font-size: .86em; }
.hero-stats { display: flex; flex-wrap: wrap; gap: 10px; }
.hs {
  display: flex; flex-direction: column; gap: 3px; padding: 12px 20px;
  border: 1px solid rgba(0, 229, 255, 0.16); border-radius: 10px; background: rgba(0, 229, 255, 0.04);
}
.hs b { font-size: 24px; font-weight: 800; color: #c3f5ff; line-height: 1; }
.hs span { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: .05em; color: #8aa6ae; }

/* 文档块 */
.doc-block { padding: 30px 0; border-top: 1px solid rgba(0, 229, 255, 0.08); margin-top: 14px; }
.block-h { font-size: 22px; font-weight: 700; color: #eaf6fa; margin: 0 0 12px; letter-spacing: .02em; }
.block-p { font-size: 14px; line-height: 1.8; color: #b9d2d9; max-width: 800px; margin: 0 0 16px; }
.code {
  font-family: 'JetBrains Mono', monospace; font-size: 12.5px; line-height: 1.7;
  color: #cfeede; background: rgba(3, 9, 18, 0.85); border: 1px solid rgba(0, 229, 255, 0.14);
  border-left: 3px solid rgba(0, 229, 255, 0.5); border-radius: 8px;
  padding: 16px 18px; overflow-x: auto; margin: 4px 0 0; white-space: pre;
}
.note {
  margin-top: 14px; font-size: 13px; color: #cfe6eb; line-height: 1.6;
  background: rgba(0, 229, 255, 0.05); border: 1px solid rgba(0, 229, 255, 0.14);
  border-radius: 8px; padding: 12px 16px;
}
.note-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: .1em; color: #04141a; background: #00e5ff; border-radius: 4px; padding: 2px 8px; margin-right: 10px; }
.hl { color: #7df0db; }

.conv-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 18px; }
.conv { background: rgba(24, 34, 58, 0.7); border: 1px solid rgba(0, 229, 255, 0.14); border-radius: 10px; padding: 14px 16px; }
.conv > code { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: .14em; color: #00e5ff; background: none; padding: 0; }
.conv b { display: block; font-size: 14px; color: #eaf6fa; margin: 4px 0 6px; }
.conv p { margin: 0; font-size: 12.5px; line-height: 1.6; color: #aac6cd; }

.st-table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }
.st-table th { text-align: left; font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: #6f8a92; padding: 10px 14px; border-bottom: 1px solid rgba(0, 229, 255, 0.14); }
.st-table td { padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,.04); color: #c4dce2; }
.st-code { font-family: 'JetBrains Mono', monospace; font-weight: 700; }
.st-code.ok { color: #5fe3a1; } .st-code.warn { color: #ffd166; } .st-code.bad { color: #ff7a90; }

/* 端点分组 */
.api-group { padding: 28px 0; border-top: 1px solid rgba(0, 229, 255, 0.08); margin-top: 14px; }
.grp-head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.grp-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: .14em; border: 1px solid; border-radius: 4px; padding: 3px 9px; }
.grp-title { font-size: 18px; font-weight: 700; color: #eaf6fa; margin: 0; }
.grp-count { margin-left: auto; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #62808a; }
.ep-list { display: flex; flex-direction: column; border: 1px solid rgba(0, 229, 255, 0.1); border-radius: 10px; overflow: hidden; }
.ep-item { border-bottom: 1px solid rgba(255,255,255,.04); }
.ep-item:last-child { border-bottom: none; }
.ep {
  width: 100%; display: flex; align-items: center; gap: 14px; padding: 11px 16px;
  background: rgba(22, 31, 52, 0.55); border: none; cursor: pointer; text-align: left;
  transition: background .12s; font: inherit; color: inherit;
}
.ep:hover { background: rgba(0, 229, 255, 0.06); }
.ep-item.open > .ep { background: rgba(0, 229, 255, 0.08); }
.ep-method { font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700; letter-spacing: .04em; border: 1px solid; border-radius: 5px; padding: 3px 9px; min-width: 58px; text-align: center; flex-shrink: 0; }
.ep-path { font-family: 'JetBrains Mono', monospace; font-size: 13px; color: #d6eef4; background: none; padding: 0; flex-shrink: 0; }
.ep-desc { font-size: 12.5px; color: #93b0b8; margin-left: auto; text-align: right; }
.ep-caret { flex-shrink: 0; color: #5f7984; font-size: 12px; transition: transform .18s ease; }
.ep-item.open .ep-caret { transform: rotate(90deg); color: #00e5ff; }

/* 展开详情 */
.ep-detail { padding: 4px 18px 20px; background: rgba(7, 12, 22, 0.55); animation: epFade .18s ease; }
@keyframes epFade { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }
.det-meta { display: flex; align-items: center; gap: 12px; padding: 10px 0 4px; flex-wrap: wrap; }
.det-auth { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: .06em; color: #ffd166; background: rgba(255,209,102,.1); border: 1px solid rgba(255,209,102,.3); border-radius: 5px; padding: 3px 9px; }
.det-auth.pub { color: #5fe3a1; background: rgba(95,227,161,.1); border-color: rgba(95,227,161,.3); }
.det-sum { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #6f8a92; }
.det-h { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: .14em; text-transform: uppercase; color: rgba(0,229,255,.7); margin: 16px 0 8px; }
.det-note { font-size: 12.5px; color: #93b0b8; margin: 6px 0 0; }
.det-note a { color: #00e5ff; text-decoration: none; }
.det-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.det-table th { text-align: left; font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: .1em; text-transform: uppercase; color: #5f7984; padding: 6px 12px; border-bottom: 1px solid rgba(0,229,255,.12); }
.det-table td { padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,.03); vertical-align: top; }
.pm-name { font-family: 'JetBrains Mono', monospace; color: #aef6ff; background: none; padding: 0; font-size: 12.5px; }
.pm-desc { display: block; font-size: 11px; color: #7e9aa2; margin-top: 2px; }
.pm-in { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #8aa6ae; border: 1px solid rgba(255,255,255,.1); border-radius: 4px; padding: 1px 7px; }
.pm-req { color: #ff9db0; font-weight: 600; } .pm-opt { color: #6f8a92; }
.pm-type { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #c4b5fd; white-space: nowrap; }
.pm-label { font-size: 12.5px; color: #aac6cd; }
.code.sm { font-size: 12px; padding: 12px 14px; margin-top: 0; }

.api-group.dim .ep-list { border-color: rgba(129, 140, 248, 0.18); }
.api-group.dim .ep:hover { background: rgba(129, 140, 248, 0.08); }
.api-group.dim .ep-item.open > .ep { background: rgba(129, 140, 248, 0.1); }
.api-group.dim .ep-path { color: #ddd6fe; }

.docs-foot { margin-top: 40px; padding-top: 20px; border-top: 1px solid rgba(0,229,255,.08); display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: 12px; color: #62808a; }

@media (max-width: 900px) {
  .docs-side { display: none; }
  .conv-grid { grid-template-columns: 1fr; }
  .ep { flex-wrap: wrap; }
  .ep-desc { margin-left: 72px; text-align: left; width: 100%; }
}
</style>
