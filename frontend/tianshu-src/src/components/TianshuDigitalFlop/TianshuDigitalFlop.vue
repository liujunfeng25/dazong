<template>
  <span class="tianshu-digital-flop" role="img" :aria-label="ariaLabel">
    <span class="tianshu-digital-flop__visual" aria-hidden="true">
      <template v-for="(seg, i) in segments" :key="i">
        <TianshuDigitalFlopDigit
          v-if="seg.kind === 'digit'"
          :digit="seg.value"
          :duration="duration"
          :easing="easing"
        />
        <span
          v-else
          class="tianshu-digital-flop__sep"
          :class="{ 'tianshu-digital-flop__sep--dot': seg.char === '.' }"
        >{{ seg.char }}</span>
      </template>
    </span>
  </span>
</template>

<script setup>
import { computed } from "vue"
import TianshuDigitalFlopDigit from "./TianshuDigitalFlopDigit.vue"

const props = defineProps({
  /** 原始数值（整数或小数） */
  value: {
    type: Number,
    default: 0,
  },
  decimals: {
    type: Number,
    default: 0,
  },
  /** 800–1200ms 推荐区间，超出会被夹取 */
  duration: {
    type: Number,
    default: 1000,
  },
  easing: {
    type: String,
    default: "cubic-bezier(0.33, 1, 0.68, 1)",
  },
})

/** 千分位 + 固定小数位，与 toFixed 一致 */
function formatFlopString(num, dec) {
  const n = Number(num)
  if (!Number.isFinite(n)) return dec > 0 ? "0." + "0".repeat(dec) : "0"
  const fixed = n.toFixed(Math.max(0, Math.min(20, dec)))
  const [intRaw, frac] = fixed.split(".")
  const intPart = intRaw.replace(/\B(?=(\d{3})+(?!\d))/g, ",")
  return frac !== undefined ? `${intPart}.${frac}` : intPart
}

const displayStr = computed(() => formatFlopString(props.value, props.decimals))

const segments = computed(() => {
  const s = displayStr.value
  const out = []
  for (let i = 0; i < s.length; i += 1) {
    const c = s[i]
    if (c >= "0" && c <= "9") {
      out.push({ kind: "digit", value: c.charCodeAt(0) - 48 })
    } else {
      out.push({ kind: "sep", char: c })
    }
  }
  return out
})

const ariaLabel = computed(() => displayStr.value)
</script>

<style lang="scss" scoped>
.tianshu-digital-flop {
  display: inline-flex;
  align-items: center;
  flex-wrap: nowrap;
  letter-spacing: 0;
  /* 与父级 .value 的 letter-spacing 解耦，避免逗号/小数点被挤进数字槽 */
  &__visual {
    display: inline-flex;
    align-items: center;
    flex-wrap: nowrap;
    gap: 0;
    letter-spacing: 0;
  }
  font-family: D-DIN, ui-monospace, monospace;
  font-weight: bold;
  font-size: inherit;
  font-variant-numeric: tabular-nums;
  color: #ffffff;
  text-shadow:
    0 0 12px rgba(186, 245, 255, 0.45),
    0 0 22px rgba(56, 189, 248, 0.35),
    0 1px 0 rgba(8, 24, 42, 0.9);
  &__sep {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 0.5em;
    height: 1em;
    line-height: 1;
    margin: 0 0.04em;
    padding: 0 0.02em;
    box-sizing: border-box;
    text-align: center;
    font-weight: 700;
    font-size: 0.82em;
    color: rgba(200, 245, 255, 0.95);
    /* 分隔符单独发光易与数字槽边缘糊成「白边」，改轻量描边 */
    text-shadow: 0 0 6px rgba(56, 189, 248, 0.35);
    z-index: 2;
    position: relative;
    &--dot {
      min-width: 0.35em;
      font-size: 1.05em;
      font-weight: 900;
      margin: 0 0.02em;
      /* 小数点略下沉，避免与千分位逗号视觉混淆 */
      transform: translateY(0.12em);
    }
  }
}
</style>
