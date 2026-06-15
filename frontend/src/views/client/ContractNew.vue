<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createTenderApi, tenderMetaApi, tenderPeriodOverlapHintApi } from '../../api/contracts'
import { useIsMobile } from '../../composables/useIsMobile'

const router = useRouter()
const { isMobile } = useIsMobile()
const loading = ref(false)
const overlapLoading = ref(false)
const deliveryOptions = ref([])
const level1Categories = ref([])
const overlapHint = ref({ has_overlap: false, contracts: [], message: '' })
const form = reactive({
  delivery_ids: [],
  period_start: '',
  period_end: '',
})

let overlapTimer = null

const loadMeta = async () => {
  const meta = await tenderMetaApi()
  deliveryOptions.value = meta.deliveries || []
  level1Categories.value = meta.level1_categories || []
}

const refreshOverlapHint = async () => {
  if (!form.period_start || !form.period_end) {
    overlapHint.value = { has_overlap: false, contracts: [], message: '' }
    return
  }
  if (form.period_start > form.period_end) {
    overlapHint.value = { has_overlap: false, contracts: [], message: '' }
    return
  }
  overlapLoading.value = true
  try {
    const res = await tenderPeriodOverlapHintApi({
      period_start: form.period_start,
      period_end: form.period_end,
      delivery_ids: form.delivery_ids.length ? form.delivery_ids.join(',') : undefined,
    })
    overlapHint.value = {
      has_overlap: Boolean(res?.has_overlap),
      contracts: Array.isArray(res?.contracts) ? res.contracts : [],
      message: res?.message || '',
    }
  } catch {
    overlapHint.value = { has_overlap: false, contracts: [], message: '' }
  } finally {
    overlapLoading.value = false
  }
}

const scheduleOverlapHint = () => {
  clearTimeout(overlapTimer)
  overlapTimer = setTimeout(refreshOverlapHint, 300)
}

watch(
  () => [form.period_start, form.period_end, form.delivery_ids.join(',')],
  scheduleOverlapHint,
)

const submit = async () => {
  if (!form.delivery_ids.length) {
    ElMessage.warning('请至少选择一个配送单位')
    return
  }
  if (!form.period_start || !form.period_end) {
    ElMessage.warning('请选择招标周期')
    return
  }
  await refreshOverlapHint()
  if (overlapHint.value.has_overlap) {
    try {
      await ElMessageBox.confirm(
        `${overlapHint.value.message}\n\n仍可继续发布招标，但请知悉定标限制。是否继续提交？`,
        '招标周期与现有合约重叠',
        { type: 'warning', confirmButtonText: '继续发布', cancelButtonText: '返回修改' },
      )
    } catch {
      return
    }
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
  <!-- ── Mobile ── -->
  <div v-if="isMobile" v-loading="loading" class="m-page">
    <div class="m-card">
      <div class="m-card__title">配送单位</div>
      <el-select
        v-model="form.delivery_ids"
        multiple
        placeholder="选择配送单位（可多选）"
        style="width:100%"
        @change="scheduleOverlapHint"
      >
        <el-option
          v-for="item in deliveryOptions"
          :key="item.id"
          :value="item.id"
          :label="item.company_name || item.username"
        />
      </el-select>
    </div>

    <div class="m-card">
      <div class="m-card__title">招标周期</div>
      <div class="m-field-group">
        <div class="m-field-label">开始日期</div>
        <el-date-picker
          v-model="form.period_start"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择开始日期"
          style="width:100%"
          @change="scheduleOverlapHint"
        />
      </div>
      <div class="m-field-group">
        <div class="m-field-label">结束日期</div>
        <el-date-picker
          v-model="form.period_end"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择结束日期"
          style="width:100%"
          @change="scheduleOverlapHint"
        />
      </div>
      <div v-if="overlapHint.has_overlap || overlapLoading" class="m-overlap-alert" v-loading="overlapLoading">
        <span class="material-symbols-outlined" style="font-size:18px;flex:none">warning</span>
        <div>
          <div class="m-overlap-alert__title">与现有合约重叠</div>
          <div>{{ overlapHint.message }}</div>
          <div class="m-overlap-alert__sub">此为提示，不阻止招标，最终以定标时校验为准。</div>
        </div>
      </div>
    </div>

    <div class="m-card">
      <div class="m-card__title">采购品类范围</div>
      <div class="m-field-tip">本次招标默认覆盖全部一级分类，配送商需分别填写各品类浮动率，且不超过上限。</div>
      <div v-if="level1Categories.length" class="m-cat-list">
        <div v-for="c in level1Categories" :key="c.id" class="m-cat-row">
          <span class="m-cat-name">{{ c.name }}</span>
          <span class="m-cat-cap">上限 {{ Number(c.max_float_rate != null ? c.max_float_rate : 1).toFixed(4) }}</span>
        </div>
      </div>
      <div v-else class="m-field-tip">全部一级分类</div>
    </div>

    <div class="m-bottom-bar">
      <el-button style="flex:1" @click="router.back()">取消</el-button>
      <el-button type="primary" style="flex:2" :loading="loading" @click="submit">提交招标</el-button>
    </div>
  </div>

  <!-- ── PC ── -->
  <el-card v-else>
    <el-form label-width="100px" v-loading="loading">
      <el-form-item label="配送单位">
        <el-select
          v-model="form.delivery_ids"
          multiple
          placeholder="可多选配送单位"
          @change="scheduleOverlapHint"
        >
          <el-option
            v-for="item in deliveryOptions"
            :key="item.id"
            :value="item.id"
            :label="item.company_name || item.username"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="开始">
        <el-date-picker
          v-model="form.period_start"
          type="date"
          value-format="YYYY-MM-DD"
          @change="scheduleOverlapHint"
        />
      </el-form-item>
      <el-form-item label="结束">
        <el-date-picker
          v-model="form.period_end"
          type="date"
          value-format="YYYY-MM-DD"
          @change="scheduleOverlapHint"
        />
      </el-form-item>
      <el-form-item v-if="overlapHint.has_overlap || overlapLoading" label="周期提示">
        <el-alert
          v-loading="overlapLoading"
          type="warning"
          :closable="false"
          show-icon
          class="overlap-alert"
        >
          <template #title>与现有合约时段重叠</template>
          <p class="overlap-message">{{ overlapHint.message }}</p>
          <p class="overlap-sub">
            此为发布前提示，不阻止招标；最终能否定标给其他配送商，以定标时系统校验为准。
          </p>
        </el-alert>
      </el-form-item>
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

.overlap-alert {
  width: 100%;
}

.overlap-message {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.5;
}

.overlap-sub {
  margin: 6px 0 0;
  font-size: 12px;
  color: #909399;
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

/* ── Mobile styles ── */
.m-page {
  font-family: var(--m-font-body);
  padding: 12px 16px 88px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.m-card {
  background: var(--m-surface-container-lowest);
  border: 1px solid var(--m-outline-variant);
  border-radius: 12px;
  padding: 16px;
}
.m-card__title {
  font-family: var(--m-font-display);
  font-size: 15px;
  font-weight: 700;
  color: var(--m-on-surface);
  margin-bottom: 12px;
}
.m-field-group {
  margin-bottom: 12px;
}
.m-field-label {
  font-size: 13px;
  color: var(--m-on-surface-variant);
  margin-bottom: 6px;
}
.m-field-tip {
  font-size: 12px;
  color: var(--m-on-surface-variant);
  line-height: 1.6;
  margin-bottom: 10px;
}
.m-overlap-alert {
  margin-top: 12px;
  padding: 10px 12px;
  background: #fef9c3;
  border: 1px solid #f59e0b;
  border-radius: 10px;
  color: #854d0e;
  font-size: 12px;
  line-height: 1.5;
  display: flex;
  gap: 8px;
}
.m-overlap-alert__title {
  font-weight: 700;
  margin-bottom: 4px;
}
.m-overlap-alert__sub {
  color: #92400e;
  margin-top: 4px;
}
.m-cat-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.m-cat-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--m-outline-variant);
}
.m-cat-row:last-child { border-bottom: none; }
.m-cat-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--m-on-surface);
}
.m-cat-cap {
  font-size: 12px;
  color: var(--m-on-surface-variant);
}
.m-bottom-bar {
  position: fixed;
  bottom: calc(64px + env(safe-area-inset-bottom, 0px));
  left: 0;
  right: 0;
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  background: var(--m-surface-container-lowest);
  border-top: 1px solid var(--m-outline-variant);
  z-index: 20;
}
</style>
