<script setup>
import { computed } from 'vue'

const props = defineProps({
  phase: {
    type: String,
    default: '',
  },
})

const labels = ['客户提交', '派发配送商', '配送商处理', '运营审核', '处理完成']

/** 当前聚焦节点下标 0..4；售后单创建后即视为前两步已完成 */
const curIdx = computed(() => {
  const p = props.phase
  if (p === 'closed') return 4
  if (p === 'operation_review') return 3
  return 2
})

const stepClass = (idx) => {
  if (props.phase === 'closed') return 'done'
  const c = curIdx.value
  if (idx < c) return 'done'
  if (idx === c) return 'active'
  return 'todo'
}
</script>

<template>
  <div class="complaint-stepper-wrap">
    <div class="stepper">
      <div v-for="(label, idx) in labels" :key="idx" class="step" :class="stepClass(idx)">
        <div class="step-dot" />
        <div class="step-label">{{ label }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.complaint-stepper-wrap {
  padding: 8px 0;
}

.stepper {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 4px;
  flex-wrap: nowrap;
}

.step {
  flex: 1;
  text-align: center;
  position: relative;
  min-width: 0;
}

.step::after {
  content: '';
  position: absolute;
  top: 10px;
  left: 50%;
  width: 100%;
  height: 3px;
  background: #e2e8f0;
  z-index: 0;
}

.step:last-child::after {
  display: none;
}

.step-dot {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  margin: 0 auto 6px;
  position: relative;
  z-index: 1;
  border: 3px solid #e2e8f0;
  background: #fff;
}

.step.done .step-dot {
  background: #4f46e5;
  border-color: #4f46e5;
}

.step.done::after {
  background: linear-gradient(90deg, #4f46e5, #6366f1);
}

.step.active .step-dot {
  border-color: #6366f1;
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.25);
}

.step.active::after {
  background: linear-gradient(90deg, #6366f1 0%, #e2e8f0 100%);
}

.step.todo .step-dot {
  background: #f1f5f9;
}

.step-label {
  font-size: 11px;
  color: #475569;
  line-height: 1.2;
  padding: 0 2px;
}

.step.done .step-label {
  color: #312e81;
  font-weight: 600;
}

.step.active .step-label {
  color: #4f46e5;
  font-weight: 700;
}
</style>
