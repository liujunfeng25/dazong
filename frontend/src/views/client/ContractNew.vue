<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createTenderApi, tenderMetaApi } from '../../api/contracts'

const router = useRouter()
const loading = ref(false)
const deliveryOptions = ref([])
const level1Categories = ref([])
const form = reactive({
  delivery_ids: [],
  period_start: '',
  period_end: '',
})

const loadMeta = async () => {
  const meta = await tenderMetaApi()
  deliveryOptions.value = meta.deliveries || []
  level1Categories.value = meta.level1_categories || []
}

const submit = async () => {
  if (!form.delivery_ids.length) {
    ElMessage.warning('请至少选择一个配送单位')
    return
  }
  if (!form.period_start || !form.period_end) {
    ElMessage.warning('请选择招标周期')
    return
  }
  loading.value = true
  try {
    await createTenderApi({
      delivery_ids: form.delivery_ids,
      period_start: form.period_start,
      period_end: form.period_end,
    })
    ElMessage.success('招标已发布')
    router.push('/client/tenders')
  } finally {
    loading.value = false
  }
}

onMounted(loadMeta)
</script>

<template>
  <el-card>
    <el-form label-width="100px" v-loading="loading">
      <el-form-item label="配送单位">
        <el-select v-model="form.delivery_ids" multiple placeholder="可多选配送单位">
          <el-option
            v-for="item in deliveryOptions"
            :key="item.id"
            :value="item.id"
            :label="item.company_name || item.username"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="开始"><el-date-picker v-model="form.period_start" type="date" value-format="YYYY-MM-DD" /></el-form-item>
      <el-form-item label="结束"><el-date-picker v-model="form.period_end" type="date" value-format="YYYY-MM-DD" /></el-form-item>
      <el-form-item>
        <div class="field-tip">
          本次招标默认覆盖全部一级分类，配送商需对每个一级分类分别填写上浮率，且不得超过运营端为各分类设置的上浮率上限。
        </div>
      </el-form-item>
      <el-form-item label="分类范围">
        <div v-if="level1Categories.length" class="category-list">
          <div v-for="c in level1Categories" :key="c.id" class="category-line">
            <span class="category-text">{{ c.name }}</span>
            <span class="category-cap">（上浮率上限 {{ Number(c.max_float_rate != null ? c.max_float_rate : 1).toFixed(4) }}）</span>
          </div>
        </div>
        <div v-else class="category-text">全部一级分类</div>
      </el-form-item>
      <el-button type="primary" @click="submit">提交招标</el-button>
    </el-form>
  </el-card>
</template>

<style scoped>
.field-tip {
  color: #909399;
  font-size: 12px;
}

.category-text {
  color: #303133;
  font-weight: 600;
}

.category-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.category-line {
  line-height: 1.5;
}

.category-cap {
  color: #909399;
  font-size: 12px;
  font-weight: 500;
}
</style>
