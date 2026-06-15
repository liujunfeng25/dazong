<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { receiveOrderApi, reviewOrderApi, settleOrderApi } from '../../api/orders'
import { useIsMobile } from '../../composables/useIsMobile'

const route = useRoute()
const router = useRouter()
const { isMobile } = useIsMobile()
const form = reactive({ rating: 5, comment: '' })
const loading = ref(false)
const received = ref(false)
const reviewed = ref(false)
const settled = ref(false)

const receive = async () => {
  loading.value = true
  try {
    await receiveOrderApi(route.params.id)
    received.value = true
    ElMessage.success('收货完成')
  } finally {
    loading.value = false
  }
}
const review = async () => {
  loading.value = true
  try {
    await reviewOrderApi(route.params.id, form)
    reviewed.value = true
    ElMessage.success('评价已提交')
  } finally {
    loading.value = false
  }
}
const settle = async () => {
  loading.value = true
  try {
    await settleOrderApi(route.params.id)
    settled.value = true
    ElMessage.success('已完成结算')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <!-- ── Mobile ── -->
  <div v-if="isMobile" v-loading="loading" class="m-page">
    <div class="m-steps">
      <div class="m-step" :class="{ done: received || reviewed || settled, active: !received }">
        <div class="m-step__dot"><span v-if="received" class="material-symbols-outlined" style="font-size:14px">check</span><span v-else>1</span></div>
        <div class="m-step__label">确认收货</div>
      </div>
      <div class="m-step-line" />
      <div class="m-step" :class="{ done: reviewed || settled, active: received && !reviewed }">
        <div class="m-step__dot"><span v-if="reviewed" class="material-symbols-outlined" style="font-size:14px">check</span><span v-else>2</span></div>
        <div class="m-step__label">提交评价</div>
      </div>
      <div class="m-step-line" />
      <div class="m-step" :class="{ done: settled, active: reviewed && !settled }">
        <div class="m-step__dot"><span v-if="settled" class="material-symbols-outlined" style="font-size:14px">check</span><span v-else>3</span></div>
        <div class="m-step__label">确认结算</div>
      </div>
    </div>

    <div v-if="!received" class="m-step-card">
      <div class="m-step-card__title">步骤 1：确认收货</div>
      <div class="m-step-card__desc">确认货物已实物接收完毕，请核对清单后操作。</div>
      <el-button type="primary" style="width:100%;margin-top:16px" @click="receive">确认收货</el-button>
    </div>

    <div v-else-if="!reviewed" class="m-step-card">
      <div class="m-step-card__title">步骤 2：提交评价</div>
      <div class="m-field-label">配送评分（1-5 分）</div>
      <el-rate v-model="form.rating" style="margin-bottom:12px" />
      <div class="m-field-label">评价内容（可选）</div>
      <el-input v-model="form.comment" type="textarea" :rows="4" placeholder="请填写评价内容..." />
      <el-button type="primary" style="width:100%;margin-top:16px" @click="review">提交评价</el-button>
    </div>

    <div v-else-if="!settled" class="m-step-card">
      <div class="m-step-card__title">步骤 3：确认结算</div>
      <div class="m-step-card__desc">评价已提交。确认完成本订单结算后，账单将被关账。</div>
      <el-button type="success" style="width:100%;margin-top:16px" @click="settle">确认结算</el-button>
    </div>

    <div v-else class="m-step-card m-step-card--done">
      <span class="material-symbols-outlined" style="font-size:40px;color:#15803d">check_circle</span>
      <div class="m-step-card__title" style="color:#15803d">全部完成</div>
      <div class="m-step-card__desc">收货、评价与结算均已完成。</div>
      <el-button style="width:100%;margin-top:16px" @click="router.push('/client/orders')">返回订单列表</el-button>
    </div>
  </div>

  <!-- ── PC ── -->
  <el-card v-else v-loading="loading">
    <template #header>
      <span class="font-semibold">收货与结算</span>
    </template>
    <div class="mb-3">
      <el-button type="primary" :disabled="received" @click="receive">确认收货</el-button>
      <el-tag v-if="received" type="success" class="ml-2">已收货</el-tag>
    </div>
    <el-divider />
    <el-form label-width="80px">
      <el-form-item label="评分"><el-input-number v-model="form.rating" :min="1" :max="5" /></el-form-item>
      <el-form-item label="评价"><el-input v-model="form.comment" type="textarea" /></el-form-item>
      <el-button :disabled="reviewed" @click="review">提交评价</el-button>
      <el-button type="success" :disabled="settled || !received" @click="settle">结算</el-button>
      <el-tag v-if="settled" type="success" class="ml-2">已结算</el-tag>
    </el-form>
  </el-card>
</template>

<style scoped>
/* ── Mobile styles ── */
.m-page {
  font-family: var(--m-font-body);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.m-steps {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  padding: 8px 0;
}
.m-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.m-step__dot {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--m-surface-container-high);
  color: var(--m-on-surface-variant);
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 700;
  transition: all 0.2s;
}
.m-step.active .m-step__dot {
  background: var(--m-primary);
  color: var(--m-on-primary);
  box-shadow: 0 0 0 4px rgba(0,50,134,0.15);
}
.m-step.done .m-step__dot {
  background: #15803d;
  color: #fff;
}
.m-step__label {
  font-size: 11px;
  color: var(--m-on-surface-variant);
  font-weight: 500;
}
.m-step.active .m-step__label { color: var(--m-primary); font-weight: 700; }
.m-step.done .m-step__label { color: #15803d; }
.m-step-line {
  flex: 1;
  height: 2px;
  background: var(--m-outline-variant);
  margin: 0 6px;
  margin-bottom: 16px;
}
.m-step-card {
  background: var(--m-surface-container-lowest);
  border: 1px solid var(--m-outline-variant);
  border-radius: 14px;
  padding: 20px 16px;
}
.m-step-card--done {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 8px;
}
.m-step-card__title {
  font-family: var(--m-font-display);
  font-size: 16px;
  font-weight: 700;
  color: var(--m-on-surface);
  margin-bottom: 8px;
}
.m-step-card__desc {
  font-size: 13px;
  color: var(--m-on-surface-variant);
  line-height: 1.6;
}
.m-field-label {
  font-size: 13px;
  color: var(--m-on-surface-variant);
  margin-bottom: 6px;
}
</style>
