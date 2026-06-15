<script setup>
/**
 * 天枢大屏「演示数据」浮窗按钮。
 *
 * - 默认隐藏：仅在 DEV 或 VITE_DEMO_MODE=true 时渲染，避免误带到正式环境（与 DemoConsole.vue 保留策略一致）
 * - 28×28 像素，绝对定位到大屏右上，z-index 高、半透明，开启状态加呼吸动画 + 「MOCK」红徽标
 * - 仅 toggle，不弹抽屉，不挤占大屏画面
 */
import { computed } from "vue"

const props = defineProps({
  running: { type: Boolean, required: true },
})
const emit = defineEmits(["toggle"])

const visible = computed(() => {
  const m = import.meta.env.VITE_DEMO_MODE
  return import.meta.env.DEV || m === "true" || m === true || m === "1"
})

const title = computed(() =>
  props.running ? "演示模式开启中（点击关闭，本地内存模拟）" : "开启模拟数据（仅本浏览器、关闭即净）"
)

function onClick() {
  emit("toggle")
}
</script>

<template>
  <div v-if="visible" class="mock-toggle-wrap" :class="{ running }">
    <button
      type="button"
      class="mock-toggle-btn"
      :title="title"
      :aria-pressed="running"
      @click="onClick"
    >
      <!-- 闪电图标：off=暗、on=金 -->
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
        <path
          d="M13 2L4 14h7l-1 8 9-12h-7l1-8z"
          :fill="running ? '#ffcc66' : '#7faab2'"
        />
      </svg>
    </button>
    <span v-if="running" class="mock-badge">MOCK</span>
  </div>
</template>

<style scoped>
.mock-toggle-wrap {
  position: absolute;
  top: 14px;
  right: 18px;
  z-index: 1200;
  display: flex;
  align-items: center;
  gap: 6px;
  pointer-events: auto;
}
.mock-toggle-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid rgba(120, 200, 220, 0.45);
  background: rgba(10, 22, 36, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0;
  transition: background 0.2s, border-color 0.2s, box-shadow 0.2s;
}
.mock-toggle-btn:hover {
  background: rgba(20, 40, 60, 0.7);
  border-color: rgba(180, 230, 240, 0.7);
}
.mock-toggle-wrap.running .mock-toggle-btn {
  border-color: #ffcc66;
  box-shadow: 0 0 10px rgba(255, 204, 102, 0.55);
  animation: mock-breath 1.6s ease-in-out infinite;
}
@keyframes mock-breath {
  0%, 100% { box-shadow: 0 0 6px rgba(255, 204, 102, 0.35); }
  50%      { box-shadow: 0 0 14px rgba(255, 204, 102, 0.85); }
}
.mock-badge {
  font-family: "Menlo", "Consolas", monospace;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #1a1208;
  background: #ffcc66;
  padding: 1px 6px;
  border-radius: 3px;
  line-height: 1.5;
}
</style>
