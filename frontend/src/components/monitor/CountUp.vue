<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  value: { type: [Number, String], default: null },
  decimals: { type: Number, default: 0 },
  duration: { type: Number, default: 900 },
  prefix: { type: String, default: '' },
  suffix: { type: String, default: '' },
  placeholder: { type: String, default: '—' },
})

const display = ref('')
const pulsing = ref(false)
let raf = null
let pulseTimer = null
let current = 0

const isNum = (v) => v !== null && v !== '' && v !== undefined && !isNaN(Number(v))

function format(n) {
  const fixed = Number(n).toFixed(props.decimals)
  const [int, dec] = fixed.split('.')
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return dec ? `${grouped}.${dec}` : grouped
}

function tweenTo(target) {
  cancelAnimationFrame(raf)
  const from = current
  const start = performance.now()
  const dur = Math.max(120, props.duration)
  const step = (now) => {
    const t = Math.min(1, (now - start) / dur)
    const eased = 1 - Math.pow(1 - t, 3) // easeOutCubic
    current = from + (target - from) * eased
    display.value = format(current)
    if (t < 1) raf = requestAnimationFrame(step)
    else current = target
  }
  raf = requestAnimationFrame(step)
}

function triggerPulse() {
  pulsing.value = false
  // 强制重启动画
  requestAnimationFrame(() => { pulsing.value = true })
  clearTimeout(pulseTimer)
  pulseTimer = setTimeout(() => { pulsing.value = false }, 480)
}

watch(
  () => props.value,
  (v) => {
    if (!isNum(v)) { display.value = props.placeholder; current = 0; return }
    tweenTo(Number(v))
    triggerPulse()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  clearTimeout(pulseTimer)
})
</script>

<template>
  <span class="countup" :class="{ pulse: pulsing }">
    <span v-if="prefix" class="cu-fix">{{ prefix }}</span>{{ display }}<span v-if="suffix" class="cu-fix">{{ suffix }}</span>
  </span>
</template>

<style scoped>
.countup {
  font-variant-numeric: tabular-nums;
  display: inline-block;
}
.cu-fix { font-size: .56em; font-weight: 700; opacity: .7; margin: 0 .12em; }
.countup.pulse { animation: cuPulse .46s ease-out; }
@keyframes cuPulse {
  0% { filter: brightness(1.5); transform: scale(1.06); }
  100% { filter: brightness(1); transform: scale(1); }
}
</style>
