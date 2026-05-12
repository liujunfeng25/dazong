import { onMounted, onBeforeUnmount, unref } from "vue"
import emitter from "@/utils/emitter"

/** 监听全局 `tianshuChartsResize`（首屏入场结束后触发），并对 ECharts 实例 resize */
export function useTianshuChartResize(vChartRef) {
  function resizeChart() {
    const inst = unref(vChartRef.value?.chart)
    inst?.resize?.()
  }
  onMounted(() => {
    emitter.$on("tianshuChartsResize", resizeChart)
  })
  onBeforeUnmount(() => {
    emitter.$off("tianshuChartsResize", resizeChart)
  })
  return { resizeChart }
}
