<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { QuestionFilled, Calendar, Promotion, Wallet } from '@element-plus/icons-vue'
import {
  clearBillingTestingApi,
  confirmBillingCycleApi,
  createBillingCycleApi,
  createTargetedCycleApi,
  followGlobalTargetedCycleApi,
  listBillingCyclesApi,
  listTargetedCyclesApi,
  previewBillingCycleApi,
  updateTargetedCycleApi,
} from '../../api/bills'
import { listAccountsApi, listOperationClientCanteensApi } from '../../api/operation'

const loading = ref(false)
const saving = ref(false)
const clearing = ref(false)
const list = ref([])
const previewLoading = ref(false)
const preview = ref(null)
const fieldsTouched = ref(new Set()) // 用于决定是否覆盖默认值

const form = ref({
  relation_type: 'client_delivery',
  cycle_type: 'monthly',
  close_day: 1,
  confirm_due_days: 3,
  payment_due_days: 15,
})

const relationOptions = [
  {
    value: 'client_delivery',
    label: '客户（食堂）对配送商结算',
    description: '只适用于已中标且在有效期内的客户-配送商合约；客户（食堂）只向配送商付款。',
    flow: '客户（食堂）应付配送商；配送商应收客户（食堂）',
  },
  {
    value: 'delivery_supplier',
    label: '配送商对供货商/厂家结算',
    description: '只适用于配送商绑定的供货商，以及指定厂家商品实际分单到的厂家。',
    flow: '配送商应付供货商/厂家；供货商/厂家应收配送商',
  },
]

const cycleCards = [
  {
    value: 'daily',
    icon: Promotion,
    title: '按天',
    subtitle: '每天 24:00 都自动关账',
    hint: '资金流转极快、新合作或信用要求高时用',
  },
  {
    value: 'weekly',
    icon: Calendar,
    title: '按周',
    subtitle: '每周固定一天关账',
    hint: '中小客户、稳定合作',
  },
  {
    value: 'monthly',
    icon: Wallet,
    title: '按月',
    subtitle: '每月固定一号关账（最常见）',
    hint: '大客户、传统月结',
  },
]

const weekdayOptions = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 7, label: '周日' },
]

const DEFAULTS_BY_CYCLE = {
  daily: { close_day: 1, confirm_due_days: 1, payment_due_days: 7 },
  weekly: { close_day: 5, confirm_due_days: 3, payment_due_days: 7 },
  monthly: { close_day: 1, confirm_due_days: 5, payment_due_days: 15 },
}

const selectedRelation = computed(() => relationOptions.find((item) => item.value === form.value.relation_type))

const ruleRows = computed(() => {
  const order = new Map(relationOptions.map((item, index) => [item.value, index]))
  return [...list.value].sort((a, b) => (order.get(a.relation_type) ?? 99) - (order.get(b.relation_type) ?? 99))
})

const naturalLanguageFor = (cycle_type, close_day, confirm, payment) => {
  let head
  if (cycle_type === 'daily') head = '每天 24:00 关账'
  else if (cycle_type === 'weekly') {
    const cd = Math.max(1, Math.min(7, Number(close_day) || 1))
    head = `每${weekdayOptions[cd - 1].label} 24:00 关账`
  } else {
    const cd = Math.max(1, Math.min(28, Number(close_day) || 1))
    head = `每月 ${cd} 号 24:00 关账`
  }
  return `${head} · 对方需在 ${confirm} 天内确认 / ${payment} 天内付清`
}

const cycleLongSummary = (row) =>
  naturalLanguageFor(row.cycle_type, row.close_day, row.confirm_due_days, row.payment_due_days)

const dayValidationError = computed(() => {
  if (Number(form.value.payment_due_days) < Number(form.value.confirm_due_days)) {
    return '付款期限应不少于确认期限'
  }
  return ''
})

const canSave = computed(() => {
  if (dayValidationError.value) return false
  if (form.value.cycle_type === 'weekly' && !(form.value.close_day >= 1 && form.value.close_day <= 7)) return false
  if (form.value.cycle_type === 'monthly' && !(form.value.close_day >= 1 && form.value.close_day <= 28)) return false
  if (!(form.value.confirm_due_days >= 0) || !(form.value.payment_due_days >= 0)) return false
  return true
})

const load = async () => {
  loading.value = true
  try {
    list.value = await listBillingCyclesApi()
    const current = list.value.find((item) => item.relation_type === form.value.relation_type)
    if (current) fillForm(current)
  } finally {
    loading.value = false
  }
}

const fillForm = (row) => {
  form.value = {
    relation_type: row.relation_type || form.value.relation_type,
    cycle_type: row.cycle_type || 'monthly',
    close_day: Number(row.close_day || 1),
    confirm_due_days: Number(row.confirm_due_days ?? 3),
    payment_due_days: Number(row.payment_due_days ?? 15),
  }
  fieldsTouched.value = new Set(['close_day', 'confirm_due_days', 'payment_due_days'])
}

watch(
  () => form.value.relation_type,
  (value) => {
    const row = list.value.find((item) => item.relation_type === value)
    if (row) fillForm(row)
  },
)

const pickCycleType = (val) => {
  if (form.value.cycle_type === val) return
  form.value.cycle_type = val
  const def = DEFAULTS_BY_CYCLE[val]
  if (!def) return
  // 仅对用户未明确编辑过的字段套默认
  if (!fieldsTouched.value.has('close_day')) form.value.close_day = def.close_day
  else if (val === 'weekly' && !(form.value.close_day >= 1 && form.value.close_day <= 7)) form.value.close_day = def.close_day
  else if (val === 'monthly' && !(form.value.close_day >= 1 && form.value.close_day <= 28)) form.value.close_day = def.close_day
  if (!fieldsTouched.value.has('confirm_due_days')) form.value.confirm_due_days = def.confirm_due_days
  if (!fieldsTouched.value.has('payment_due_days')) form.value.payment_due_days = def.payment_due_days
}

const markTouched = (field) => fieldsTouched.value.add(field)

let previewTimer = null
const debouncePreview = () => {
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(loadPreview, 220)
}

const loadPreview = async () => {
  if (!canSave.value) {
    preview.value = null
    return
  }
  previewLoading.value = true
  try {
    preview.value = await previewBillingCycleApi({
      cycle_type: form.value.cycle_type,
      close_day: form.value.close_day,
      confirm_due_days: form.value.confirm_due_days,
      payment_due_days: form.value.payment_due_days,
    })
  } catch {
    preview.value = null
  } finally {
    previewLoading.value = false
  }
}

watch(
  () => [form.value.cycle_type, form.value.close_day, form.value.confirm_due_days, form.value.payment_due_days],
  debouncePreview,
  { deep: false },
)

const save = async () => {
  if (!canSave.value) {
    ElMessage.warning(dayValidationError.value || '请检查参数')
    return
  }
  saving.value = true
  try {
    await createBillingCycleApi({ ...form.value })
    await load()
    ElMessage.success('账期规则已保存')
  } finally {
    saving.value = false
  }
}

const confirmCycle = async (row) => {
  saving.value = true
  try {
    await confirmBillingCycleApi(row.id)
    await load()
    ElMessage.success('规则已确认启用')
  } finally {
    saving.value = false
  }
}

const clearInvalid = async () => {
  await ElMessageBox.confirm('将删除错误关系产生的账期和关联演示账单，例如客户（食堂）直接对供货商/厂家。有效业务账单不会被清除。', '清理无效账期', {
    confirmButtonText: '确认清理',
    cancelButtonText: '取消',
    type: 'warning',
  })
  clearing.value = true
  try {
    const res = await clearBillingTestingApi()
    await load()
    ElMessage.success(res?.message || '无效账期已清理')
  } finally {
    clearing.value = false
  }
}

// ===== 定向账期规则（按 学校×食堂×配送商 / 配送商×供货商）=====
const targetedLoading = ref(false)
const targetedRows = ref([])
const targetedFilter = ref({ relation_type: '', keyword: '' })

const loadTargeted = async () => {
  targetedLoading.value = true
  try {
    targetedRows.value = await listTargetedCyclesApi({
      relation_type: targetedFilter.value.relation_type || undefined,
      keyword: targetedFilter.value.keyword?.trim() || undefined,
    })
  } finally {
    targetedLoading.value = false
  }
}

const targetedPartyText = (row) =>
  row.relation_type === 'client_delivery'
    ? `${row.owner_name} · ${row.canteen_name || '未指定食堂'} × ${row.counterparty_name}`
    : `${row.owner_name} × ${row.counterparty_name}`

// 编辑/新增对话框
const targetedDialog = ref(false)
const targetedSaving = ref(false)
const targetedEditing = ref(null) // null=新增；否则为被编辑行
const targetedForm = ref({
  relation_type: 'client_delivery',
  owner_user_id: null,
  canteen_id: null,
  counterparty_user_id: null,
  cycle_type: 'monthly',
  close_day: 1,
  confirm_due_days: 3,
  payment_due_days: 15,
})

const clientOptions = ref([])
const deliveryOptions = ref([])
const upstreamOptions = ref([]) // 供货商+厂家
const canteenOptions = ref([])

const accountLabel = (a) => a.company_name || a.username

const loadPartyOptions = async () => {
  if (clientOptions.value.length) return
  const [clients, deliveries, suppliers, factories] = await Promise.all([
    listAccountsApi({ role: 'client' }),
    listAccountsApi({ role: 'delivery' }),
    listAccountsApi({ role: 'supplier' }),
    listAccountsApi({ role: 'factory' }),
  ])
  clientOptions.value = clients || []
  deliveryOptions.value = deliveries || []
  upstreamOptions.value = [...(suppliers || []), ...(factories || [])]
}

const loadCanteenOptions = async (schoolId) => {
  canteenOptions.value = schoolId
    ? await listOperationClientCanteensApi({ school_client_id: schoolId })
    : []
}

watch(
  () => targetedForm.value.owner_user_id,
  async (val) => {
    if (targetedEditing.value || targetedForm.value.relation_type !== 'client_delivery') return
    targetedForm.value.canteen_id = null
    await loadCanteenOptions(val)
  },
)

const openTargetedCreate = async () => {
  targetedEditing.value = null
  targetedForm.value = {
    relation_type: 'client_delivery',
    owner_user_id: null,
    canteen_id: null,
    counterparty_user_id: null,
    cycle_type: 'monthly',
    close_day: 1,
    confirm_due_days: 3,
    payment_due_days: 15,
  }
  targetedDialog.value = true
  await loadPartyOptions()
}

const openTargetedEdit = (row) => {
  targetedEditing.value = row
  targetedForm.value = {
    relation_type: row.relation_type,
    owner_user_id: row.owner_user_id,
    canteen_id: row.canteen_id,
    counterparty_user_id: row.counterparty_user_id,
    cycle_type: row.cycle_type,
    close_day: Number(row.close_day || 1),
    confirm_due_days: Number(row.confirm_due_days ?? 3),
    payment_due_days: Number(row.payment_due_days ?? 15),
  }
  targetedDialog.value = true
}

const targetedCanSave = computed(() => {
  const f = targetedForm.value
  if (Number(f.payment_due_days) < Number(f.confirm_due_days)) return false
  if (targetedEditing.value) return true
  if (!f.owner_user_id || !f.counterparty_user_id) return false
  if (f.relation_type === 'client_delivery' && !f.canteen_id) return false
  return true
})

const saveTargeted = async () => {
  targetedSaving.value = true
  try {
    const f = targetedForm.value
    const params = {
      cycle_type: f.cycle_type,
      close_day: f.close_day,
      confirm_due_days: f.confirm_due_days,
      payment_due_days: f.payment_due_days,
    }
    if (targetedEditing.value) {
      await updateTargetedCycleApi(targetedEditing.value.id, params)
      ElMessage.success('定向规则已更新（已标记为定制，不再跟随全局）')
    } else {
      await createTargetedCycleApi({
        relation_type: f.relation_type,
        owner_user_id: f.owner_user_id,
        counterparty_user_id: f.counterparty_user_id,
        canteen_id: f.relation_type === 'client_delivery' ? f.canteen_id : undefined,
        ...params,
      })
      ElMessage.success('定向规则已创建')
    }
    targetedDialog.value = false
    await loadTargeted()
  } finally {
    targetedSaving.value = false
  }
}

const followGlobal = async (row) => {
  await ElMessageBox.confirm(
    `「${targetedPartyText(row)}」将恢复跟随全局规则，参数立即同步为全局当前值，之后全局调整也会自动生效。`,
    '恢复跟随全局',
    { confirmButtonText: '恢复跟随', cancelButtonText: '取消', type: 'warning' },
  )
  await followGlobalTargetedCycleApi(row.id)
  ElMessage.success('已恢复跟随全局')
  await loadTargeted()
}

onMounted(async () => {
  await load()
  await loadPreview()
  await loadTargeted()
})
</script>

<template>
  <div class="billing-config-page">
    <el-card shadow="never" class="hero-card">
      <div class="hero-row">
        <div>
          <div class="title">账期规则</div>
          <div class="subtitle">
            按"给谁、多久、多急"三步配置即可；右侧实时预览帮你看清下一个关账日与催收时间线。
          </div>
        </div>
        <div class="actions">
          <el-button :loading="loading" @click="load">刷新</el-button>
          <el-button type="danger" plain :loading="clearing" @click="clearInvalid">清理无效账期</el-button>
        </div>
      </div>
    </el-card>

    <el-alert
      title="账单只能从真实订单收货确认后生成"
      type="info"
      show-icon
      :closable="false"
      description="客户（食堂）只向配送商付款，不直接接触供货商或厂家。配送商再按分单向供货商/厂家付款。"
    />
    <el-alert
      title="账期不是出账触发器"
      type="warning"
      show-icon
      :closable="false"
    >
      <template #default>
        <div class="explain-block">
          账单仍按每次收货实时生成，方便随单核对。此处账期配置只用来：
          ① 决定每张账单归到哪个账期（如「2026-05」）；
          ② 算出每张账单的「确认到期日」「付款到期日」；
          ③ 超过上述到期日的账单会出现在「账单总览」的异常清单里；
          ④ 在「账单总览 → 按账期汇总」视图按账期+方向聚合，可单组导出 CSV 作为对账单。
        </div>
        <div class="explain-block explain-glossary">
          📚 名词解释 ——
          <strong>关账</strong>：账期截止、本期账单冻结进入催收的时刻；
          <strong>出账日</strong>：本周期最后一天，也是关账日；
          <strong>账期归属</strong>：账单按其创建时间归入最近的一个未关账周期。
        </div>
      </template>
    </el-alert>

    <el-row :gutter="16">
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-title">编辑规则</div>
          </template>
          <el-alert
            class="scope-banner"
            type="info"
            :closable="false"
            show-icon
          >
            <template #default>
              <strong>这是全局默认规则。</strong>
              <span class="scope-relation">{{ selectedRelation?.label || '该关系链' }}</span>
              下<strong>未定制的结算对子</strong>都按此账期算；修改后会在下次出账时自动同步给它们。
              <span class="scope-hint">⚠️ 已定制的对子不受全局修改影响；已生成的历史对账单不会改变（账单按生成时的账期冻结）。</span>
              <span class="scope-hint">需要给某个食堂 / 供货商单独配账期？用下方「定向账期规则」。</span>
            </template>
          </el-alert>
          <el-form label-position="top" :model="form">
            <!-- Step 1 -->
            <div class="step">
              <div class="step-title">
                <span class="step-no">①</span>
                给哪条结算关系配规则
                <el-tooltip content="账期只在「资金真的会流动」的两条链上配置：客户→配送商、配送商→上游。" placement="top">
                  <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <el-form-item>
                <el-select v-model="form.relation_type" style="width: 100%">
                  <el-option
                    v-for="item in relationOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
              </el-form-item>
              <el-alert
                class="relation-note"
                type="success"
                :closable="false"
                :title="selectedRelation?.flow"
                :description="selectedRelation?.description"
              />
            </div>

            <!-- Step 2 -->
            <div class="step">
              <div class="step-title">
                <span class="step-no">②</span>
                多久关账一次、几点关
                <el-tooltip content="决定多久结一次账。关账后这一批账单进入催收阶段。" placement="top">
                  <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <div class="cycle-cards">
                <div
                  v-for="opt in cycleCards"
                  :key="opt.value"
                  class="cycle-card"
                  :class="{ active: form.cycle_type === opt.value }"
                  @click="pickCycleType(opt.value)"
                >
                  <div class="cycle-card-head">
                    <el-icon :size="18"><component :is="opt.icon" /></el-icon>
                    <strong>{{ opt.title }}</strong>
                  </div>
                  <div class="cycle-card-sub">{{ opt.subtitle }}</div>
                  <div class="cycle-card-hint">{{ opt.hint }}</div>
                </div>
              </div>

              <el-form-item v-if="form.cycle_type === 'monthly'" label="每月几号关账">
                <el-input-number
                  v-model="form.close_day"
                  :min="1"
                  :max="28"
                  style="width: 100%"
                  @change="markTouched('close_day')"
                />
                <div class="form-hint">选 1-28；选 28 是为了兼容 2 月（最长 28 天）。</div>
              </el-form-item>
              <el-form-item v-else-if="form.cycle_type === 'weekly'" label="每周几关账">
                <el-select
                  v-model="form.close_day"
                  style="width: 100%"
                  @change="markTouched('close_day')"
                >
                  <el-option
                    v-for="w in weekdayOptions"
                    :key="w.value"
                    :label="w.label"
                    :value="w.value"
                  />
                </el-select>
              </el-form-item>
              <el-alert
                v-else
                type="info"
                :closable="false"
                class="daily-note"
                title="按天关账：每天 24:00 都是关账日，无需指定具体哪天"
              />
            </div>

            <!-- Step 3 -->
            <div class="step">
              <div class="step-title">
                <span class="step-no">③</span>
                关账后多久要做什么
                <el-tooltip content="账单关账后，对方需要在多少天内完成核对、多少天内付清。" placement="top">
                  <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <el-form-item label="对方需在几天内核对账单">
                <el-input-number
                  v-model="form.confirm_due_days"
                  :min="0"
                  :max="90"
                  style="width: 100%"
                  @change="markTouched('confirm_due_days')"
                />
                <div class="form-hint">超期会被列入「账单总览 → 超期未确认」清单。</div>
              </el-form-item>
              <el-form-item label="对方需在几天内付清欠款">
                <el-input-number
                  v-model="form.payment_due_days"
                  :min="0"
                  :max="180"
                  style="width: 100%"
                  @change="markTouched('payment_due_days')"
                />
                <div class="form-hint">超期会被列入「账单总览 → 超期未付款」清单。</div>
              </el-form-item>
              <div v-if="dayValidationError" class="validation-error">⚠ {{ dayValidationError }}</div>
            </div>

            <div class="save-bar">
              <el-button
                type="primary"
                :loading="saving"
                :disabled="!canSave"
                @click="save"
              >
                保存规则
              </el-button>
              <span class="save-hint">保存后该关系链下新生成的账单立刻按新规则计算到期日</span>
            </div>
          </el-form>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="panel-card preview-card">
          <template #header>
            <div class="panel-title">
              当前编辑的规则预览
              <el-tooltip content="实时根据左侧编辑器的数值计算下一个关账日与到期日，不保存也不影响线上数据。" placement="top">
                <el-icon class="tip-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
          <div v-loading="previewLoading">
            <div class="preview-natural">
              <span class="preview-emoji">📋</span>
              <span>{{ preview?.natural_language || naturalLanguageFor(form.cycle_type, form.close_day, form.confirm_due_days, form.payment_due_days) }}</span>
            </div>
            <div v-if="preview" class="preview-timeline">
              <div class="preview-timeline-head">
                🕒 以今天（{{ preview.today }}）为基准：
              </div>
              <ul class="preview-step-list">
                <li>
                  <strong>下一次关账日</strong>
                  <span>{{ preview.next_close_at }}</span>
                  <em v-if="preview.days_to_close === 0">（今天关账）</em>
                  <em v-else>（还有 {{ preview.days_to_close }} 天）</em>
                </li>
                <li>
                  <strong>对方需在</strong>
                  <span>{{ preview.next_confirm_due }} 23:59</span>
                  <em>前完成「确认账单」，否则进入「超期未确认」</em>
                </li>
                <li>
                  <strong>对方需在</strong>
                  <span>{{ preview.next_payment_due }} 23:59</span>
                  <em>前完成「付清欠款」，否则进入「超期未付款」</em>
                </li>
              </ul>
              <div class="preview-period">本张账单归属账期：<strong>{{ preview.period_label }}</strong>（{{ preview.period_start }} 至 {{ preview.period_end }}）</div>
            </div>
            <el-empty v-else description="参数不合法时不展示预览" :image-size="60" />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="panel-card">
      <template #header>
        <div class="panel-title">规则列表</div>
      </template>
      <el-table v-loading="loading" :data="ruleRows" border>
        <el-table-column prop="display_title" label="规则名称" min-width="170" />
        <el-table-column prop="relation_description" label="适用关系" min-width="260" />
        <el-table-column label="关账与催收" min-width="320">
          <template #default="{ row }">
            <span class="rule-summary">{{ cycleLongSummary(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="is_confirmed" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.is_confirmed ? 'success' : 'warning'">
              {{ row.is_confirmed ? '已确认' : '待确认' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button v-if="!row.is_confirmed" size="small" @click="confirmCycle(row)">确认启用</el-button>
            <el-button v-else size="small" @click="fillForm(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="panel-card">
      <template #header>
        <div class="targeted-head">
          <div class="panel-title">
            定向账期规则
            <el-tooltip content="给具体的「学校·食堂 × 配送商」或「配送商 × 供货商/厂家」配差异化账期。首次出账会自动生成跟随全局的规则；编辑后即为定制，不再跟随全局。" placement="top">
              <el-icon class="tip-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
          <div class="targeted-tools">
            <el-select v-model="targetedFilter.relation_type" placeholder="全部关系" clearable style="width: 200px" @change="loadTargeted">
              <el-option v-for="item in relationOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-input
              v-model="targetedFilter.keyword"
              placeholder="搜索 学校/食堂/对手方"
              clearable
              style="width: 200px"
              @keyup.enter="loadTargeted"
              @clear="loadTargeted"
            />
            <el-button :loading="targetedLoading" @click="loadTargeted">查询</el-button>
            <el-button type="primary" @click="openTargetedCreate">新增定向规则</el-button>
          </div>
        </div>
      </template>
      <el-table v-loading="targetedLoading" :data="targetedRows" border>
        <el-table-column prop="relation_title" label="结算关系" min-width="170" />
        <el-table-column label="结算主体" min-width="240">
          <template #default="{ row }">
            <span class="rule-summary">{{ targetedPartyText(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关账与催收" min-width="300">
          <template #default="{ row }">
            <span class="rule-summary">{{ cycleLongSummary(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.is_customized ? 'warning' : 'info'">{{ row.follow_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="190">
          <template #default="{ row }">
            <el-button size="small" @click="openTargetedEdit(row)">编辑</el-button>
            <el-button v-if="row.is_customized" size="small" plain @click="followGlobal(row)">恢复跟随全局</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!targetedLoading && !targetedRows.length"
        description="暂无定向规则：结算对子首次出账时会自动生成（跟随全局），也可点「新增定向规则」提前配置"
        :image-size="70"
      />
    </el-card>

    <el-dialog
      v-model="targetedDialog"
      :title="targetedEditing ? '编辑定向规则' : '新增定向规则'"
      width="520px"
    >
      <el-form label-position="top" :model="targetedForm">
        <template v-if="!targetedEditing">
          <el-form-item label="结算关系">
            <el-select v-model="targetedForm.relation_type" style="width: 100%">
              <el-option v-for="item in relationOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <template v-if="targetedForm.relation_type === 'client_delivery'">
            <el-form-item label="客户（学校）">
              <el-select v-model="targetedForm.owner_user_id" filterable style="width: 100%" placeholder="选择客户">
                <el-option v-for="a in clientOptions" :key="a.id" :label="accountLabel(a)" :value="a.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="食堂">
              <el-select v-model="targetedForm.canteen_id" style="width: 100%" placeholder="先选客户再选食堂">
                <el-option v-for="c in canteenOptions" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="配送商">
              <el-select v-model="targetedForm.counterparty_user_id" filterable style="width: 100%" placeholder="选择配送商">
                <el-option v-for="a in deliveryOptions" :key="a.id" :label="accountLabel(a)" :value="a.id" />
              </el-select>
            </el-form-item>
          </template>
          <template v-else>
            <el-form-item label="配送商">
              <el-select v-model="targetedForm.owner_user_id" filterable style="width: 100%" placeholder="选择配送商">
                <el-option v-for="a in deliveryOptions" :key="a.id" :label="accountLabel(a)" :value="a.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="供货商 / 厂家">
              <el-select v-model="targetedForm.counterparty_user_id" filterable style="width: 100%" placeholder="选择供货商或厂家">
                <el-option v-for="a in upstreamOptions" :key="a.id" :label="accountLabel(a)" :value="a.id" />
              </el-select>
            </el-form-item>
          </template>
        </template>
        <el-form-item v-else label="结算主体">
          <span class="rule-summary">{{ targetedPartyText(targetedEditing) }}</span>
        </el-form-item>

        <el-form-item label="结算周期">
          <el-select v-model="targetedForm.cycle_type" style="width: 100%">
            <el-option label="按天" value="daily" />
            <el-option label="按周" value="weekly" />
            <el-option label="按月" value="monthly" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="targetedForm.cycle_type === 'monthly'" label="每月几号关账">
          <el-input-number v-model="targetedForm.close_day" :min="1" :max="28" style="width: 100%" />
        </el-form-item>
        <el-form-item v-else-if="targetedForm.cycle_type === 'weekly'" label="每周几关账">
          <el-select v-model="targetedForm.close_day" style="width: 100%">
            <el-option v-for="w in weekdayOptions" :key="w.value" :label="w.label" :value="w.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="确认期限（天）">
          <el-input-number v-model="targetedForm.confirm_due_days" :min="0" :max="90" style="width: 100%" />
        </el-form-item>
        <el-form-item label="付款期限（天）">
          <el-input-number v-model="targetedForm.payment_due_days" :min="0" :max="180" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="targetedDialog = false">取消</el-button>
        <el-button type="primary" :loading="targetedSaving" :disabled="!targetedCanSave" @click="saveTargeted">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.billing-config-page {
  display: grid;
  gap: 16px;
}
.hero-card,
.panel-card {
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
.panel-title {
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.tip-icon {
  color: #94a3b8;
  cursor: help;
}

.explain-block {
  line-height: 1.7;
}
.explain-glossary {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed rgba(0, 0, 0, 0.08);
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.explain-glossary strong {
  color: #0f172a;
}

.step {
  padding: 12px 0;
  border-bottom: 1px dashed #e2e8f0;
}
.step:last-of-type {
  border-bottom: none;
}
.step-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.step-no {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #e0e7ff;
  color: #4338ca;
  font-size: 12px;
  font-weight: 700;
}

.relation-note {
  margin: 0;
}

.scope-banner {
  margin-bottom: 14px;
  line-height: 1.7;
}
.scope-banner strong {
  color: #0f172a;
}
.scope-relation {
  color: #4338ca;
  font-weight: 600;
  margin: 0 2px;
}
.scope-hint {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.cycle-cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.cycle-card {
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  transition: border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
}
.cycle-card:hover {
  border-color: var(--el-color-primary-light-3);
}
.cycle-card.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 6px 16px rgba(64, 96, 220, 0.12);
}
.cycle-card-head {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #0f172a;
  font-size: 15px;
}
.cycle-card-head strong {
  font-weight: 700;
}
.cycle-card-sub {
  margin-top: 6px;
  font-size: 12px;
  color: #475569;
}
.cycle-card-hint {
  margin-top: 4px;
  font-size: 11px;
  color: #94a3b8;
}

.form-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.daily-note {
  margin-bottom: 14px;
}
.validation-error {
  color: #dc2626;
  font-size: 12px;
  margin-top: 4px;
}

.save-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
}
.save-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.preview-natural {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px;
  border-radius: 8px;
  background: #f8fafc;
  color: #0f172a;
  font-size: 14px;
  line-height: 1.6;
}
.preview-emoji {
  font-size: 18px;
}
.preview-timeline {
  margin-top: 12px;
}
.preview-timeline-head {
  font-size: 13px;
  color: #475569;
  margin-bottom: 6px;
}
.preview-step-list {
  margin: 0;
  padding-left: 16px;
  display: grid;
  gap: 6px;
  font-size: 13px;
  color: #334155;
}
.preview-step-list li strong {
  color: #0f172a;
  margin-right: 6px;
}
.preview-step-list li em {
  margin-left: 4px;
  color: #64748b;
  font-style: normal;
  font-size: 12px;
}
.preview-period {
  margin-top: 10px;
  font-size: 12px;
  color: #64748b;
}
.preview-period strong {
  color: #0f172a;
}

.rule-summary {
  color: #0f172a;
  line-height: 1.5;
}

.targeted-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.targeted-tools {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 900px) {
  .hero-row {
    flex-direction: column;
  }
  .cycle-cards {
    grid-template-columns: 1fr;
  }
}
</style>
