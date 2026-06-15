<template>
  <div class="right-card">
    <m-card title="订单排名" :overlay-loading="chartRefreshing">
      <TianshuNativeEchart ref="vChart" :option="option" />
    </m-card>
  </div>
</template>
<script setup>
import { ref, shallowRef, onMounted, onBeforeUnmount, inject, watch } from "vue"
import * as echarts from "echarts"
import mCard from "@/components/mCard/index.vue"
import TianshuNativeEchart from "./TianshuNativeEchart.vue"
import {
  fetchJson,
  isTianshuAuthMissingError,
  todayRangeQueryString,
  truncateLabel,
  appendDistrictToQueryString,
  TIANSHU_CHART_QUERY_DISTRICT_KEY,
  debouncedDistrictReload,
} from "@/api/tianshuInsights.js"
import { useTianshuChartResize } from "../composables/useTianshuChartResize.js"
import {
  startStaggeredPoll,
  TIANSHU_POLL_PERIOD_MS,
  TIANSHU_POLL_STAGGER,
} from "../composables/tianshuStaggeredPoll.js"
import {
  tianshuTooltipAxisShadow,
  tianshuLegendTextStyle,
  TIANSHU_SERIES_COLORS,
  TIANSHU_AMBER,
} from "../tianshuEchartsTheme.js"

const API_BASE = "/api/insights/business"

const chartQueryDistrict = inject(TIANSHU_CHART_QUERY_DISTRICT_KEY, ref(null))
const chartRefreshing = ref(false)
let loadGen = 0

const GRADIENTS = [
  new echarts.graphic.LinearGradient(0, 0, 1, 1, [
    { offset: 0, color: "rgba(12, 48, 72, 1)" },
    { offset: 1, color: "rgba(92, 239, 255, 0.95)" },
  ]),
  new echarts.graphic.LinearGradient(0, 0, 1, 1, [
    { offset: 0, color: "rgba(20, 60, 100, 1)" },
    { offset: 1, color: "rgba(56, 189, 248, 0.92)" },
  ]),
  new echarts.graphic.LinearGradient(0, 0, 1, 1, [
    { offset: 0, color: "rgba(30, 40, 90, 1)" },
    { offset: 1, color: "rgba(129, 140, 248, 0.95)" },
  ]),
  new echarts.graphic.LinearGradient(0, 0, 1, 1, [
    { offset: 0, color: "rgba(120, 70, 20, 1)" },
    { offset: 1, color: "rgba(251, 191, 36, 0.95)" },
  ]),
]

function barDataItem(value, i) {
  return {
    value,
    itemStyle: { color: GRADIENTS[i % GRADIENTS.length] },
  }
}

const option = shallowRef({
  grid: {
    left: "5%",
    top: "10%",
    width: "90%",
    height: "86%",
  },
  legend: {
    top: "8%",
    icon: "circle",
    itemWidth: 8,
    itemHeight: 8,
    textStyle: { ...tianshuLegendTextStyle },
  },

  tooltip: { ...tianshuTooltipAxisShadow },
  color: [...TIANSHU_SERIES_COLORS, TIANSHU_AMBER],
  xAxis: [
    {
      type: "value",
      interval: 0,

      axisLine: {
        show: false,
        lineStyle: {
          color: "#407A80",
        },
      },
      axisTick: {
        show: false,
      },
      splitLine: {
        show: false,
      },
      axisLabel: {
        color: "rgba(190, 225, 245, 0.9)",
        fontSize: 10,
        interval: 0,
      },
    },
  ],

  yAxis: [
    {
      type: "category",
      inverse: true,
      axisLabel: {
        color: "rgba(190, 225, 245, 0.9)",
        fontSize: 10,
        interval: 0,
        show: false,
        verticalAlign: "top",
      },
      axisLine: {
        show: false,
      },
      axisTick: {
        show: false,
      },
      splitLine: {
        show: false,
      },
      data: ["—", "—", "—", "—"],
    },
    {
      inverse: true,
      axisLine: {
        show: false,
        lineStyle: {
          color: "rgba(0,0,0,0)",
        },
      },
      data: [],
    },
  ],
  series: [
    {
      data: [0, 0, 0, 0].map((v, i) => barDataItem(v, i)),
      type: "bar",
      barWidth: 7,
      yAxisIndex: 0,
      showBackground: false,
      z: 2,
      label: {
        show: true,
        position: "middle",
        padding: [-18, 0, 0, 0],
        color: "#16C1A6",
        fontSize: 12,
        formatter: (p) => {
          const name = p.name || "—"
          const v = Math.round(Number(p.value) || 0)
          return `{title|${name}}                                                                              {value|${v}}  {unit|元}`
        },
        rich: {
          title: {
            color: "#FFFFFF",
            fontSize: 10,
          },
          value: {
            fontSize: 10,
          },
          unit: {
            color: "#717477",
            fontSize: 10,
          },
        },
      },
      itemStyle: {
        borderRadius: 0,
        borderWidth: 2,
        borderColor: "rgba(26, 57, 77,1)",
      },
    },
    {
      name: "背景",
      type: "bar",
      yAxisIndex: 1,
      barGap: "-100%",
      data: [1, 1, 1, 1],
      barWidth: 10,
      z: 0,
      itemStyle: {
        color: "none",
        borderColor: "rgba(172,191,188,0.4)",
        borderWidth: 1,
        borderRadius: 0,
      },
    },
  ],
})

const vChart = ref(null)
useTianshuChartResize(vChart)

let stopPoll = null
let lastTopMembersPollKey = undefined

async function load(opts = {}) {
  const silent = opts.silent === true
  const g = ++loadGen
  if (!silent) chartRefreshing.value = true
  try {
    const baseQs = await todayRangeQueryString()
    const qs = appendDistrictToQueryString(baseQs, chartQueryDistrict.value)
    const data = await fetchJson(`${API_BASE}/orders-top-members?limit=4&${qs}`)
    if (g !== loadGen) return
    const rows = Array.isArray(data.rows) ? data.rows : []
    const categories = []
    const valuesYuan = []
    for (let i = 0; i < 4; i += 1) {
      const r = rows[i]
      if (r) {
        categories.push(truncateLabel(String(r.member_name || "—"), 8))
        valuesYuan.push(Math.round(Number(r.gmv) || 0))
      } else {
        categories.push("—")
        valuesYuan.push(0)
      }
    }
    const maxV = Math.max(...valuesYuan, 1)
    const bg = Math.ceil(maxV * 1.2)
    const barSeries = valuesYuan.map((v, i) => barDataItem(v, i))
    const dataKey = JSON.stringify({ categories, valuesYuan, bg })
    if (dataKey === lastTopMembersPollKey) return
    lastTopMembersPollKey = dataKey
    option.value = {
      ...option.value,
      yAxis: [{ ...option.value.yAxis[0], data: categories }, option.value.yAxis[1]],
      series: [{ ...option.value.series[0], data: barSeries }, { ...option.value.series[1], data: [bg, bg, bg, bg] }],
    }
  } catch (e) {
    if (g === loadGen && !isTianshuAuthMissingError(e)) console.warn("[tianshu] 订单排名", e)
  } finally {
    if (g === loadGen && !silent) chartRefreshing.value = false
  }
}

watch(chartQueryDistrict, debouncedDistrictReload(() => load()), { flush: "post" })

onMounted(() => {
  void load({ silent: true }).catch(() => {})
  stopPoll = startStaggeredPoll(
    TIANSHU_POLL_PERIOD_MS,
    TIANSHU_POLL_STAGGER.purposeSpecialFunds,
    () => void load({ silent: true }).catch(() => {}),
  )
})

onBeforeUnmount(() => {
  stopPoll?.()
})
</script>

<style lang="scss"></style>
