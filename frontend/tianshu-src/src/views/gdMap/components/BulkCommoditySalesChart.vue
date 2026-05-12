<template>
  <div class="left-card">
    <m-card title="区域分布">
      <TianshuNativeEchart ref="vChart" :option="option" />
    </m-card>
  </div>
</template>
<script setup>
import { ref, shallowRef, onMounted, onBeforeUnmount, nextTick, unref } from "vue"
import * as echarts from "echarts"
import mCard from "@/components/mCard/index.vue"
import TianshuNativeEchart from "./TianshuNativeEchart.vue"
import emitter from "@/utils/emitter"
import {
  fetchJson,
  todayRangeQueryString,
  truncateLabel,
} from "@/api/tianshuInsights.js"
import { useTianshuChartResize } from "../composables/useTianshuChartResize.js"
import {
  startStaggeredPoll,
  TIANSHU_POLL_PERIOD_MS,
  TIANSHU_POLL_STAGGER,
} from "../composables/tianshuStaggeredPoll.js"
import {
  tianshuTooltipAxisShadow,
  tianshuSplitLineY,
  tianshuAxisLabelCategory,
  tianshuAxisLabelValue,
  tianshuTitleSubtextStyle,
  TIANSHU_SERIES_COLORS,
} from "../tianshuEchartsTheme.js"

const API_BASE = "/api/insights/business"

const option = shallowRef({
  title: {
    text: "元",
    left: "5%",
    top: "8%",
    textStyle: { ...tianshuTitleSubtextStyle },
  },
  grid: {
    left: "12%",
    top: "25%",
    width: "82%",
    height: "55%",
  },
  tooltip: { ...tianshuTooltipAxisShadow },
  xAxis: [
    {
      type: "category",
      interval: 0,
      axisLine: {
        show: false,
        lineStyle: {
          color: "#435459",
        },
      },
      axisTick: {
        show: false,
      },
      splitLine: {
        show: false,
      },
      axisLabel: {
        ...tianshuAxisLabelCategory,
        interval: 0,
        padding: [0, 0, 0, 0],
      },
      data: ["—", "—", "—", "—", "—"],
    },
    {
      axisLine: {
        show: false,
        lineStyle: {
          color: "rgba(0,0,0,0)",
        },
      },
      data: [],
    },
  ],
  yAxis: {
    type: "value",
    axisLine: {
      show: false,
    },
    axisTick: {
      show: false,
    },
    splitLine: { ...tianshuSplitLineY },
    axisLabel: { ...tianshuAxisLabelValue },
  },
  series: [
    {
      name: "",
      data: [0, 0, 0, 0, 0],
      type: "bar",
      barWidth: 4,
      stack: "b",
      z: 3,
      yAxisIndex: 0,
      showBackground: false,
      backgroundStyle: {
        color: "rgba(180, 180, 180, 0.2)",
      },
      label: {
        show: true,
        position: "top",
        distance: 15,
        color: "#ffffff",
        fontSize: 10,
      },
      itemStyle: {
        borderRadius: 2,
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: TIANSHU_SERIES_COLORS[0] },
          { offset: 1, color: TIANSHU_SERIES_COLORS[1] },
        ]),
      },
    },
    {
      type: "custom",
      /** 不抢点击，让事件落到主柱 series（与地图下钻一致） */
      silent: true,
      renderItem: (params, api) => {
        const categoryIndex = api.value(0)
        const categoryData = api.value(1)
        const basicsCoord = api.coord([categoryIndex, categoryData])
        const topBasicsYAxis = basicsCoord[1]
        const basicsXAxis = basicsCoord[0]
        return {
          type: "image",
          style: {
            x: basicsXAxis - 4.5,
            y: topBasicsYAxis - 9,
            width: 10,
            height: 10,
            image:
              "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA4AAAAOCAYAAAAfSC3RAAAAAXNSR0IArs4c6QAAAL1JREFUOE9j/P///38GMgAjSKOMdxRJWp9sXcYA18giJMLw99MHhv9//mA1hJGZhYGZX4Dhz7s3DCgaGVlYGDjVtBi+37rO8P/PbxTNjCysDJyqWgzfb18Dy6FoBKmEKfh17wZcM0iMTUkDrgmkDkMjSJCFnZ3hwbr5KDYqBCUy/Pn5Ey6GVSMzMxPDw01LUDTK+8Uw/P37j0YayXIqWYGDHuTInsQbHeAE8PEDw/+/JCYAUtIcPDpI0QRTCwDhurXXJ/EmUwAAAABJRU5ErkJggg==",
          },
        }
      },
      xAxisIndex: 1,
      data: [0, 0, 0, 0, 0],
    },
    {
      type: "bar",
      barWidth: 32,
      xAxisIndex: 1,
      barGap: "-220%",
      data: [1, 1, 1, 1, 1],
      silent: true,
      emphasis: {
        focus: "none",
        itemStyle: { color: "rgba(255,255,255,0.8)" },
      },
      itemStyle: {
        color: "rgba(122,140,153,0.6)",
        opacity: 0.1,
      },
      z: 0,
    },
  ],
})

const vChart = ref(null)
const { resizeChart } = useTianshuChartResize(vChart)
/** 与柱顺序一致的全名，供点击下钻（图表数据始终全市，不带 district_name） */
const fullDistrictNames = ref([])

let stopPoll = null
let chartClickBound = false
let lastBulkDistrictPollKey = undefined

function scheduleResizeAfterData() {
  return new Promise((resolve) => {
    nextTick(() => {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          resizeChart()
          resolve()
        })
      })
    })
  })
}

function onDistrictBarClick(params) {
  if (params?.componentType !== "series" || params?.seriesType !== "bar") return
  const si = params.seriesIndex
  /** 主柱 series 0；若仍点到背景柱 2，用同一 dataIndex 下钻 */
  if (si !== 0 && si !== 2) return
  const idx = params.dataIndex
  if (idx == null || idx < 0) return
  const name = fullDistrictNames.value[idx]
  if (!name) return
  emitter.$emit("tianshuChartDistrictClick", { name })
}

function tryBindChartClick() {
  if (chartClickBound) return
  const inst = unref(vChart.value?.chart)
  if (!inst) return
  chartClickBound = true
  inst.on("click", onDistrictBarClick)
}

async function load() {
  const qs = await todayRangeQueryString()
  const data = await fetchJson(`${API_BASE}/cockpit-smart-side-insights?${qs}`)
  const raw = Array.isArray(data.key_districts) ? data.key_districts : []
  const top = raw.slice(0, 5)
  const labels = []
  const valuesYuan = []
  const names = []
  for (let i = 0; i < 5; i += 1) {
    const r = top[i]
    if (r) {
      labels.push(truncateLabel(r.district_name, 5))
      valuesYuan.push(Math.round(Number(r.gmv) || 0))
      names.push(String(r.district_name || "").trim())
    } else {
      labels.push("—")
      valuesYuan.push(0)
      names.push("")
    }
  }
  const dataKey = JSON.stringify([labels, valuesYuan, names])
  if (dataKey === lastBulkDistrictPollKey) return
  lastBulkDistrictPollKey = dataKey
  fullDistrictNames.value = names
  const maxBg = Math.max(1, ...valuesYuan.map((v) => v * 1.35))
  const bgRow = valuesYuan.map(() => maxBg)
  option.value = {
    ...option.value,
    xAxis: [
      { ...option.value.xAxis[0], data: labels },
      option.value.xAxis[1],
    ],
    series: [
      { ...option.value.series[0], data: valuesYuan },
      { ...option.value.series[1], data: valuesYuan, silent: true },
      { ...option.value.series[2], data: bgRow, silent: true },
    ],
  }
  await scheduleResizeAfterData()
  nextTick(() => {
    tryBindChartClick()
  })
}

onMounted(() => {
  void load().catch((e) => console.warn("[tianshu] 区域分布", e))
  stopPoll = startStaggeredPoll(
    TIANSHU_POLL_PERIOD_MS,
    TIANSHU_POLL_STAGGER.bulkCommodity,
    () => void load().catch((e) => console.warn("[tianshu] 区域分布 poll", e)),
  )
  nextTick(tryBindChartClick)
  setTimeout(tryBindChartClick, 400)
})

onBeforeUnmount(() => {
  stopPoll?.()
  const inst = unref(vChart.value?.chart)
  if (inst && chartClickBound) {
    inst.off("click", onDistrictBarClick)
    chartClickBound = false
  }
})
</script>
<style lang="scss"></style>
