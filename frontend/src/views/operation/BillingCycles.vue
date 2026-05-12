<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  clearBillingTestingApi,
  confirmBillingCycleApi,
  createBillingCycleApi,
  listBillingCyclesApi,
} from '../../api/bills'

const loading = ref(false)
const saving = ref(false)
const clearing = ref(false)
const list = ref([])
const form = ref({
  relation_type: 'client_delivery',
  cycle_type: 'monthly',
  close_day: 1,
  confirm_due_days: 3,
  payment_due_days: 7,
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

const selectedRelation = computed(() => relationOptions.find((item) => item.value === form.value.relation_type))
const cycleTypeLabel = (value) => ({ daily: '按天', weekly: '按周', monthly: '按月' }[value] || value)
const ruleRows = computed(() => {
  const order = new Map(relationOptions.map((item, index) => [item.value, index]))
  return [...list.value].sort((a, b) => (order.get(a.relation_type) ?? 99) - (order.get(b.relation_type) ?? 99))
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
    confirm_due_days: Number(row.confirm_due_days || 3),
    payment_due_days: Number(row.payment_due_days || 7),
  }
}

watch(
  () => form.value.relation_type,
  (value) => {
    const row = list.value.find((item) => item.relation_type === value)
    if (row) fillForm(row)
  },
)

const save = async () => {
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

onMounted(load)
</script>

<template>
  <div class="billing-config-page">
    <el-card shadow="never" class="hero-card">
      <div class="hero-row">
        <div>
          <div class="title">账期规则</div>
          <div class="subtitle">
            账期只按真实资金关系配置：客户（食堂）与配送商、配送商与供货商/厂家。
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

    <el-row :gutter="16">
      <el-col :xs="24" :md="10">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-title">编辑规则</div>
          </template>
          <el-form label-width="120px" :model="form">
            <el-form-item label="结算关系">
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
            <el-form-item label="周期类型">
              <el-select v-model="form.cycle_type" style="width: 100%">
                <el-option label="按天" value="daily" />
                <el-option label="按周" value="weekly" />
                <el-option label="按月" value="monthly" />
              </el-select>
            </el-form-item>
            <el-form-item label="出账日">
              <el-input-number v-model="form.close_day" :min="1" :max="31" style="width: 100%" />
            </el-form-item>
            <el-form-item label="确认天数">
              <el-input-number v-model="form.confirm_due_days" :min="1" :max="90" style="width: 100%" />
            </el-form-item>
            <el-form-item label="付款天数">
              <el-input-number v-model="form.payment_due_days" :min="1" :max="180" style="width: 100%" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="save">保存规则</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="14">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-title">规则列表</div>
          </template>
          <el-table v-loading="loading" :data="ruleRows" border>
            <el-table-column prop="display_title" label="规则名称" min-width="170" />
            <el-table-column prop="relation_description" label="适用关系" min-width="260" />
            <el-table-column label="周期" width="90">
              <template #default="{ row }">{{ cycleTypeLabel(row.cycle_type) }}</template>
            </el-table-column>
            <el-table-column prop="close_day" label="出账日" width="90" />
            <el-table-column prop="confirm_due_days" label="确认天数" width="100" />
            <el-table-column prop="payment_due_days" label="付款天数" width="100" />
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
      </el-col>
    </el-row>
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
}
.relation-note {
  margin: 0 0 18px;
}
@media (max-width: 900px) {
  .hero-row {
    flex-direction: column;
  }
}
</style>
