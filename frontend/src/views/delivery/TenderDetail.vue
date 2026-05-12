<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { bidTenderApi, tenderDetailApi } from '../../api/contracts'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const tender = ref(null)
const form = reactive({ category_rates: [] })
const avgRate = computed(() =>
  form.category_rates.length
    ? form.category_rates.reduce((sum, row) => sum + Number(row.float_rate || 0), 0) / form.category_rates.length
    : 0,
)

const load = async () => {
  loading.value = true
  try {
    const detail = await tenderDetailApi(route.params.id)
    tender.value = detail
    const myRateMap = Object.fromEntries(
      (detail.my_category_rates || []).map((i) => [Number(i.category_id), Number(i.float_rate || 0)]),
    )
    form.category_rates = (detail.categories || []).map((item) => ({
      category_id: item.category_id,
      category_name: item.category_name,
      max_float_rate: item.max_float_rate != null ? Number(item.max_float_rate) : 1,
      float_rate: myRateMap[Number(item.category_id)] ?? 0,
    }))
  } finally {
    loading.value = false
  }
}

const submit = async () => {
  for (const row of form.category_rates) {
    const cap = row.max_float_rate ?? 1
    if (Number(row.float_rate) > cap) {
      ElMessage.error(`「${row.category_name}」上浮率不能超过运营设定上限 ${cap.toFixed(4)}`)
      return
    }
  }
  await bidTenderApi(route.params.id, {
    category_rates: form.category_rates.map((row) => ({
      category_id: row.category_id,
      float_rate: Number(row.float_rate),
    })),
  })
  ElMessage.success('报价提交成功')
  router.push('/delivery/tenders')
}
onMounted(load)
watch(() => route.fullPath, load)
</script>

<template>
  <el-card>
    <div class="tender-header" v-if="tender">
      <div class="header-item"><span class="label">招标编号：</span><span class="value">#{{ tender.id }}</span></div>
      <div class="header-item"><span class="label">客户单位：</span><span class="value">{{ tender.client_name || `客户#${tender.client_id}` }}</span></div>
      <div class="header-item"><span class="label">招标周期：</span><span class="value">{{ tender.period_start }} 至 {{ tender.period_end }}</span></div>
      <div class="header-item"><span class="label">当前状态：</span><span class="value">{{ tender.status }}</span></div>
    </div>
    <el-alert
      v-if="form.category_rates.length"
      type="info"
      :closable="false"
      show-icon
      class="rate-cap-alert"
      title="各一级分类的上浮率不得超过运营端为该分类设置的「运营上限」；系统已按上限限制输入框最大值。"
    />
    <el-table v-loading="loading" :data="form.category_rates" border>
      <el-table-column prop="category_name" label="一级分类" min-width="200" />
      <el-table-column label="运营上限" width="120" align="right">
        <template #default="{ row }">{{ (row.max_float_rate ?? 1).toFixed(4) }}</template>
      </el-table-column>
      <el-table-column label="上浮率" min-width="200">
        <template #default="{ row }">
          <el-input-number
            v-model="row.float_rate"
            :min="-0.5"
            :max="row.max_float_rate ?? 1"
            :step="0.01"
          />
        </template>
      </el-table-column>
    </el-table>
    <div class="actions">
      <span class="total">平均上浮率：{{ avgRate.toFixed(4) }}</span>
      <el-button type="primary" @click="submit">提交报价</el-button>
    </div>
  </el-card>
</template>

<style scoped>
.actions {
  margin-top: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.total {
  font-weight: 600;
}
.tender-header {
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid #dbeafe;
  border-radius: 10px;
  background: #f8fbff;
  display: grid;
  grid-template-columns: repeat(2, minmax(220px, 1fr));
  gap: 8px 14px;
}
.header-item .label {
  color: #64748b;
}
.header-item .value {
  color: #0f172a;
  font-weight: 600;
}
.rate-cap-alert {
  margin-bottom: 12px;
}
</style>
