<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ys7SupportsPtz } from '../utils/ys7DeviceMeta'

const props = defineProps({
  device: { type: Object, default: null },
  ptzControl: { type: Function, required: true },
  compact: { type: Boolean, default: false },
  /** dark：监控深色底；light：弹窗浅色底 */
  theme: { type: String, default: 'dark' },
})

const activeDirection = ref(null)
const busy = ref(false)

const canPtz = computed(() => ys7SupportsPtz(props.device))

const send = async (action, direction) => {
  if (!props.device?.id || !canPtz.value) return
  await props.ptzControl(Number(props.device.id), {
    action,
    direction,
    speed: 1,
  })
}

const onPress = async (direction) => {
  if (!canPtz.value || busy.value) return
  activeDirection.value = direction
  busy.value = true
  try {
    await send('start', direction)
  } catch (err) {
    activeDirection.value = null
    ElMessage.error(err?.response?.data?.detail || '云台控制失败')
  } finally {
    busy.value = false
  }
}

const onRelease = async () => {
  const direction = activeDirection.value
  if (direction == null || !props.device?.id) return
  activeDirection.value = null
  try {
    await send('stop', direction)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '云台停止失败')
  }
}

const bindPress = (direction) => ({
  onMousedown: (e) => {
    e.preventDefault()
    onPress(direction)
  },
  onTouchstart: (e) => {
    e.preventDefault()
    onPress(direction)
  },
})

const isActive = (dir) => activeDirection.value === dir

onBeforeUnmount(() => {
  if (activeDirection.value != null) {
    send('stop', activeDirection.value).catch(() => {})
  }
})
</script>

<template>
  <div
    v-if="canPtz"
    class="ys7-ptz"
    :class="[
      `ys7-ptz--${theme}`,
      { 'ys7-ptz--compact': compact, 'ys7-ptz--active': activeDirection != null },
    ]"
  >
    <div class="ys7-ptz-head">
      <span class="ys7-ptz-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
        </svg>
      </span>
      <span class="ys7-ptz-title">云台</span>
    </div>

    <div class="ys7-ptz-body">
      <div class="ys7-ptz-ring">
        <button
          type="button"
          class="ys7-ptz-dir ys7-ptz-up"
          :class="{ 'is-active': isActive(0) }"
          aria-label="向上"
          v-bind="bindPress(0)"
          @mouseup="onRelease"
          @mouseleave="onRelease"
          @touchend.prevent="onRelease"
          @touchcancel.prevent="onRelease"
        >
          <span class="ys7-ptz-chevron">▲</span>
        </button>
        <button
          type="button"
          class="ys7-ptz-dir ys7-ptz-left"
          :class="{ 'is-active': isActive(2) }"
          aria-label="向左"
          v-bind="bindPress(2)"
          @mouseup="onRelease"
          @mouseleave="onRelease"
          @touchend.prevent="onRelease"
          @touchcancel.prevent="onRelease"
        >
          <span class="ys7-ptz-chevron">◀</span>
        </button>
        <div class="ys7-ptz-hub" />
        <button
          type="button"
          class="ys7-ptz-dir ys7-ptz-right"
          :class="{ 'is-active': isActive(3) }"
          aria-label="向右"
          v-bind="bindPress(3)"
          @mouseup="onRelease"
          @mouseleave="onRelease"
          @touchend.prevent="onRelease"
          @touchcancel.prevent="onRelease"
        >
          <span class="ys7-ptz-chevron">▶</span>
        </button>
        <button
          type="button"
          class="ys7-ptz-dir ys7-ptz-down"
          :class="{ 'is-active': isActive(1) }"
          aria-label="向下"
          v-bind="bindPress(1)"
          @mouseup="onRelease"
          @mouseleave="onRelease"
          @touchend.prevent="onRelease"
          @touchcancel.prevent="onRelease"
        >
          <span class="ys7-ptz-chevron">▼</span>
        </button>
      </div>
    </div>

    <p class="ys7-ptz-hint">按住转动 · 松开停止</p>
  </div>
</template>

<style scoped>
.ys7-ptz {
  width: 100%;
  max-width: 200px;
  padding: 14px 12px 12px;
  border-radius: 14px;
  user-select: none;
}

.ys7-ptz--dark {
  background: linear-gradient(165deg, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 0.98) 100%);
  border: 1px solid rgba(148, 163, 184, 0.22);
  box-shadow:
    0 8px 24px rgba(0, 0, 0, 0.35),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

.ys7-ptz--light {
  background: linear-gradient(165deg, #ffffff 0%, #f1f5f9 100%);
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.08);
}

.ys7-ptz--compact {
  max-width: 176px;
  padding: 10px 8px 8px;
}

.ys7-ptz--active.ys7-ptz--dark {
  border-color: rgba(56, 189, 248, 0.45);
  box-shadow:
    0 8px 28px rgba(14, 165, 233, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.ys7-ptz-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}

.ys7-ptz--compact .ys7-ptz-head {
  margin-bottom: 8px;
}

.ys7-ptz-icon {
  display: flex;
  color: #38bdf8;
}

.ys7-ptz--light .ys7-ptz-icon {
  color: #0284c7;
}

.ys7-ptz-title {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.ys7-ptz--dark .ys7-ptz-title {
  color: #e2e8f0;
}

.ys7-ptz--light .ys7-ptz-title {
  color: #334155;
}

.ys7-ptz-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.ys7-ptz-ring {
  position: relative;
  width: 132px;
  height: 132px;
  border-radius: 50%;
}

.ys7-ptz--compact .ys7-ptz-ring {
  width: 116px;
  height: 116px;
}

.ys7-ptz--dark .ys7-ptz-ring {
  background: radial-gradient(circle at 50% 45%, rgba(51, 65, 85, 0.9) 0%, rgba(15, 23, 42, 0.6) 70%);
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.15);
}

.ys7-ptz--light .ys7-ptz-ring {
  background: radial-gradient(circle at 50% 45%, #f8fafc 0%, #e2e8f0 75%);
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.35);
}

.ys7-ptz-hub {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 22px;
  height: 22px;
  margin: -11px 0 0 -11px;
  border-radius: 50%;
  background: rgba(56, 189, 248, 0.25);
  border: 2px solid rgba(56, 189, 248, 0.5);
  pointer-events: none;
}

.ys7-ptz--light .ys7-ptz-hub {
  background: rgba(2, 132, 199, 0.12);
  border-color: rgba(2, 132, 199, 0.35);
}

.ys7-ptz-dir {
  position: absolute;
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  touch-action: none;
  transition:
    transform 0.12s ease,
    background 0.12s ease,
    box-shadow 0.12s ease;
}

.ys7-ptz--compact .ys7-ptz-dir {
  width: 36px;
  height: 36px;
}

.ys7-ptz--dark .ys7-ptz-dir {
  background: rgba(30, 41, 59, 0.85);
  color: #cbd5e1;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
}

.ys7-ptz--light .ys7-ptz-dir {
  background: #fff;
  color: #475569;
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.1);
  border: 1px solid #e2e8f0;
}

.ys7-ptz-dir:hover {
  transform: scale(1.06);
}

.ys7-ptz-dir.is-active {
  transform: scale(1.08);
  background: linear-gradient(145deg, #0ea5e9, #0284c7);
  color: #fff;
  box-shadow: 0 0 16px rgba(14, 165, 233, 0.55);
}

.ys7-ptz-chevron {
  font-size: 11px;
  line-height: 1;
}

.ys7-ptz-up {
  left: 50%;
  top: 4px;
  margin-left: -20px;
}

.ys7-ptz--compact .ys7-ptz-up {
  margin-left: -18px;
}

.ys7-ptz-down {
  left: 50%;
  bottom: 4px;
  margin-left: -20px;
}

.ys7-ptz--compact .ys7-ptz-down {
  margin-left: -18px;
}

.ys7-ptz-left {
  left: 4px;
  top: 50%;
  margin-top: -20px;
}

.ys7-ptz--compact .ys7-ptz-left {
  margin-top: -18px;
}

.ys7-ptz-right {
  right: 4px;
  top: 50%;
  margin-top: -20px;
}

.ys7-ptz--compact .ys7-ptz-right {
  margin-top: -18px;
}

.ys7-ptz-hint {
  margin: 10px 0 0;
  font-size: 11px;
  text-align: center;
  line-height: 1.3;
}

.ys7-ptz--dark .ys7-ptz-hint {
  color: #64748b;
}

.ys7-ptz--light .ys7-ptz-hint {
  color: #94a3b8;
}
</style>
