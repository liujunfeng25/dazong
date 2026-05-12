<template>
  <div class="left-card">
    <m-card title="单品分布" :overlay-loading="chartRefreshing">
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
  tianshuAxisLabelCategory,
  tianshuAxisLabelValue,
  tianshuTitleSubtextStyle,
  TIANSHU_SERIES_COLORS,
} from "../tianshuEchartsTheme.js"

const API_BASE = "/api/insights/business"

const chartQueryDistrict = inject(TIANSHU_CHART_QUERY_DISTRICT_KEY, ref(null))
const chartRefreshing = ref(false)
let loadGen = 0

const GRADIENTS = [
  new echarts.graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: TIANSHU_SERIES_COLORS[0] },
    { offset: 1, color: "rgba(56, 189, 248, 0.12)" },
  ]),
  new echarts.graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: TIANSHU_SERIES_COLORS[1] },
    { offset: 1, color: "rgba(129, 140, 248, 0.14)" },
  ]),
]

function barItem(value, i) {
  return {
    value,
    itemStyle: { color: GRADIENTS[i % GRADIENTS.length] },
  }
}

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
  color: [TIANSHU_SERIES_COLORS[0]],
  xAxis: [
    {
      type: "category",

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
    splitLine: {
      show: false,
    },
    axisLabel: { ...tianshuAxisLabelValue },
  },
  series: [
    {
      name: "",
      type: "pictorialBar",
      symbol: "path://M0,10 L10,10 C5.5,10 5.5,5 5,0 C4.5,5 4.5,10 0,10 z",
      label: {
        show: true,
        position: "top",
        distance: 10,
        color: "#ffffff",
        fontSize: 10,
      },

      data: [0, 0, 0, 0, 0].map((v, i) => barItem(v, i)),
    },
    {
      name: "",
      type: "custom",
      z: 3,
      xAxisIndex: 1,
      renderItem: (params, api) => {
        const categoryIndex = api.value(0)

        const categoryData = api.value(1)

        const basicsCoord = api.coord([categoryIndex, categoryData])

        const topBasicsYAxis = basicsCoord[1]

        const basicsXAxis = basicsCoord[0]
        return {
          type: "image",
          style: {
            x: basicsXAxis - 5,
            y: topBasicsYAxis - 5,
            width: 10,
            height: 10,
            image:
              "data:image/png;base64,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",
          },
        }
      },
      data: [0, 0, 0, 0, 0],
    },
  ],
})

const vChart = ref(null)
useTianshuChartResize(vChart)

let stopPoll = null
let lastGoodsTopPollKey = undefined

async function load(opts = {}) {
  const silent = opts.silent === true
  const g = ++loadGen
  if (!silent) chartRefreshing.value = true
  try {
    const baseQs = await todayRangeQueryString()
    const qs = appendDistrictToQueryString(baseQs, chartQueryDistrict.value)
    const data = await fetchJson(`${API_BASE}/goods-top?limit=5&${qs}`)
    if (g !== loadGen) return
    const rows = Array.isArray(data.rows) ? data.rows : []
    const labels = []
    const valuesYuan = []
    for (let i = 0; i < 5; i += 1) {
      const r = rows[i]
      if (r) {
        labels.push(truncateLabel(String(r.goods_name || "—"), 6))
        valuesYuan.push(Math.round(Number(r.total_amount) || 0))
      } else {
        labels.push("—")
        valuesYuan.push(0)
      }
    }
    const pictorial = valuesYuan.map((v, i) => barItem(v, i))
    const dataKey = JSON.stringify({ labels, valuesYuan })
    if (dataKey === lastGoodsTopPollKey) return
    lastGoodsTopPollKey = dataKey
    option.value = {
      ...option.value,
      xAxis: [{ ...option.value.xAxis[0], data: labels }, option.value.xAxis[1]],
      series: [{ ...option.value.series[0], data: pictorial }, { ...option.value.series[1], data: valuesYuan }],
    }
  } catch (e) {
    if (g === loadGen) console.warn("[tianshu] 单品分布", e)
  } finally {
    if (g === loadGen && !silent) chartRefreshing.value = false
  }
}

watch(chartQueryDistrict, debouncedDistrictReload(() => load()), { flush: "post" })

onMounted(() => {
  void load({ silent: true }).catch(() => {})
  stopPoll = startStaggeredPoll(
    TIANSHU_POLL_PERIOD_MS,
    TIANSHU_POLL_STAGGER.districtEconomic,
    () => void load({ silent: true }).catch(() => {}),
  )
})

onBeforeUnmount(() => {
  stopPoll?.()
})
</script>
<style lang="scss"></style>
