<template>
  <span class="tianshu-df-digit" aria-hidden="true">
    <span class="tianshu-df-digit__window">
      <span
        class="tianshu-df-digit__reel"
        :style="reelStyle"
      >
        <span v-for="n in 10" :key="n" class="tianshu-df-digit__cell">{{ n - 1 }}</span>
      </span>
    </span>
  </span>
</template>

<script setup>
import { computed } from "vue"

/** easeOutCubic，与 DataV / 常见大屏动效一致 */
const DEFAULT_EASING = "cubic-bezier(0.33, 1, 0.68, 1)"

const props = defineProps({
  digit: {
    type: Number,
    required: true,
  },
  duration: {
    type: Number,
    default: 1000,
  },
  easing: {
    type: String,
    default: DEFAULT_EASING,
  },
})

const clamped = computed(() => {
  const d = Math.round(Number(props.digit))
  if (!Number.isFinite(d)) return 0
  return Math.max(0, Math.min(9, d))
})

const reelStyle = computed(() => ({
  transform: `translateY(-${clamped.value * 10}%)`,
  transition: `transform ${Math.min(1200, Math.max(800, props.duration))}ms ${props.easing}`,
}))
</script>

<style lang="scss" scoped>
.tianshu-df-digit {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  margin: 0 1px;
  &__window {
    display: inline-block;
    height: 1.05em;
    line-height: 1.05em;
    overflow: hidden;
    min-width: 0.68em;
    width: 0.68em;
    box-sizing: border-box;
    text-align: center;
    border-radius: 4px;
    background: linear-gradient(180deg, rgba(10, 22, 38, 0.92) 0%, rgba(6, 14, 26, 0.88) 100%);
    border: 1px solid rgba(103, 232, 249, 0.28);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.06),
      0 0 12px rgba(0, 0, 0, 0.35);
  }
  &__reel {
    display: flex;
    flex-direction: column;
    will-change: transform;
  }
  &__cell {
    flex: 0 0 1.05em;
    height: 1.05em;
    line-height: 1.05em;
  }
}

@media (prefers-reduced-motion: reduce) {
  .tianshu-df-digit__reel {
    transition: none !important;
  }
}
</style>
