<template>
  <div ref="host" class="tianshu-native-echart" />
</template>
<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from "vue"
import * as echarts from "echarts"

const props = defineProps({
  option: { type: Object, required: true },
})

const host = ref(null)
let chart = null

function apply(opt) {
  if (!chart || !opt) return
  chart.setOption(opt, { notMerge: true, lazyUpdate: true })
}

onMounted(() => {
  if (!host.value) return
  chart = echarts.init(host.value)
  apply(props.option)
})

watch(
  () => props.option,
  (o) => apply(o),
  { flush: "post" },
)

onBeforeUnmount(() => {
  if (chart) {
    chart.dispose()
    chart = null
  }
})

defineExpose({
  get chart() {
    return chart
  },
  resize() {
    chart?.resize?.()
  },
})
</script>
<style scoped>
.tianshu-native-echart {
  width: 100%;
  height: 100%;
  min-height: 120px;
}
</style>
