<template>
  <div class="right-card">
    <m-card title="今昨分时对比" :overlay-loading="chartRefreshing">
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
  todayYesterdayIso,
  aggregateIntradayTo3hBins,
  HOUR3_LABELS,
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
  tianshuSplitLineY,
  tianshuAxisLabelCategory,
  tianshuAxisLabelValue,
  tianshuTitleSubtextStyle,
  tianshuLegendTextStyle,
  TIANSHU_SERIES_COLORS,
} from "../tianshuEchartsTheme.js"

const API_BASE = "/api/insights/business"

const chartQueryDistrict = inject(TIANSHU_CHART_QUERY_DISTRICT_KEY, ref(null))
const chartRefreshing = ref(false)
let loadGen = 0

const SYMBOL_BLUE =
  "image://data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABQAAAAUCAYAAACNiR0NAAAAAXNSR0IArs4c6QAAAQ5JREFUOE+1la1OQ0EQRs8kCFIQdVCCxIBpCK1AInkDHC+B4QkwvASub4GsaE0NGCRpKhGFVDQZ+Mjem9vNbkphmWTMfjNnd3b2x0iYuxuwH7wNbIewBfAGzORm5nG6ElfM3QU6AXZSkzXG3oEnMxO8thWgux8DR2tAsfxiZs/VYA38Jazi1NBvYCizv+HK4vCRyrfQgIsf7Nm6+bSnjwIeAGeZaGnXQDfoE+ABmGbixwKeAoeJAMHuv3w30ubATQb6KqDKjZPEuAXOMysZAncJbS7gJbCVEAdAKwP8AK4S2vJfgMVLLt6UDtAreWx0W8od7OJXryq16OPwR2j6+WpAyz2wDagape7vARt9AZ+G3HmhiKS3xwAAAABJRU5ErkJggg=="
const SYMBOL_GREEN =
  "image://data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABQAAAAUCAYAAACNiR0NAAAAAXNSR0IArs4c6QAAAQ5JREFUOE+1la1OQ0EQRs8kCFIQdVCCxIBpCK1AInkDHC+B4QkwvASub4GsaE0NGCRpKhGFVDQZ+Mjem9vNbkphmWTMfjNnd3b2x0iYuxuwH7wNbIewBfAGzORm5nG6ElfM3QU6AXZSkzXG3oEnMxO8thWgux8DR2tAsfxiZs/VYA38Jazi1NBvYCizv+HK4vCRyrfQgIsf7Nm6+bSnjwIeAGeZaGnXQDfoE+ABmGbixwKeAoeJAMHuv3w30ubATQb6KqDKjZPEuAXOMysZAncJbS7gJbCVEAdAKwP8AK4S2vJfgMVLLt6UDtAreWx0W8od7OJXryq16OPwR2j6+WpAyz2wDagape7vARt9AZ+G3HmhiKS3xwAAAABJRU5ErkJggg=="

function lineSeries(name, z, withArea, symbol) {
  const base = {
    name,
    data: [0, 0, 0, 0, 0, 0, 0, 0],
    type: "line",
    smooth: true,
    symbol,
    symbolSize: 10,
    showSymbol: false,
    xAxisIndex: 0,
    z,
    emphasis: {
      focus: "none",
      itemStyle: { color: "white" },
    },
    label: {
      show: true,
      position: "top",
      distance: 10,
      color: "#ffffff",
      fontSize: 8,
    },
  }
  if (name === "今日") {
    return {
      ...base,
      lineStyle: {
        shadowColor: "rgba(115, 208, 255, 1)",
        shadowBlur: 20,
        shadowOffsetY: 0,
        width: 1,
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: TIANSHU_SERIES_COLORS[0] },
          { offset: 1, color: "rgba(18,60,98,1)" },
        ]),
      },
    }
  }
  const s = {
    ...base,
    lineStyle: {
      shadowColor: "rgba(129, 140, 248, 0.85)",
      shadowBlur: 20,
      shadowOffsetY: 0,
      width: 1,
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: TIANSHU_SERIES_COLORS[2] },
        { offset: 1, color: "rgba(40, 50, 95, 1)" },
      ]),
    },
  }
  if (withArea) {
    s.areaStyle = {
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: "rgba(129, 140, 248, 0.28)" },
        { color: "rgba(51, 153, 255, 0)", offset: 1 },
      ]),
    }
  }
  return s
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
  legend: {
    top: "4%",
    icon: "circle",
    itemWidth: 8,
    itemHeight: 8,
    textStyle: { ...tianshuLegendTextStyle },
    data: ["今日", "昨日"],
  },

  tooltip: { ...tianshuTooltipAxisShadow },
  color: [TIANSHU_SERIES_COLORS[0], TIANSHU_SERIES_COLORS[2]],
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
      data: [...HOUR3_LABELS],
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
  series: [lineSeries("今日", 3, false, SYMBOL_BLUE), lineSeries("昨日", 0, true, SYMBOL_GREEN)],
})

const vChart = ref(null)
useTianshuChartResize(vChart)

let stopPoll = null
let lastIntradayComparePollKey = undefined

function toYuan(arr) {
  return arr.map((x) => Math.round(Number(x) || 0))
}

async function load(opts = {}) {
  const silent = opts.silent === true
  const g = ++loadGen
  if (!silent) chartRefreshing.value = true
  try {
    const { yesterdayIso } = todayYesterdayIso()
    const todayQs = appendDistrictToQueryString("", chartQueryDistrict.value)
    const yestQs = appendDistrictToQueryString(
      `date=${encodeURIComponent(yesterdayIso)}`,
      chartQueryDistrict.value,
    )
    const todayUrl = todayQs
      ? `${API_BASE}/today-intraday-gmv?${todayQs}`
      : `${API_BASE}/today-intraday-gmv`
    const yestUrl = `${API_BASE}/today-intraday-gmv?${yestQs}`
    const [todayRes, yestRes] = await Promise.all([fetchJson(todayUrl), fetchJson(yestUrl)])
    if (g !== loadGen) return
    const t0Today = Number(todayRes.day_start_ts) || 0
    const t0Yest = Number(yestRes.day_start_ts) || 0
    const binsToday = aggregateIntradayTo3hBins(t0Today, todayRes.buckets)
    const binsYest = aggregateIntradayTo3hBins(t0Yest, yestRes.buckets)
    const d0 = toYuan(binsToday)
    const d1 = toYuan(binsYest)
    const dataKey = JSON.stringify({ t0Today, t0Yest, d0, d1 })
    if (dataKey === lastIntradayComparePollKey) return
    lastIntradayComparePollKey = dataKey
    const series0 = { ...option.value.series[0], data: d0 }
    const series1 = { ...option.value.series[1], data: d1 }
    option.value = {
      ...option.value,
      xAxis: [{ ...option.value.xAxis[0], data: [...HOUR3_LABELS] }, option.value.xAxis[1]],
      series: [series0, series1],
    }
  } catch (e) {
    if (g === loadGen) console.warn("[tianshu] 今昨分时对比", e)
  } finally {
    if (g === loadGen && !silent) chartRefreshing.value = false
  }
}

watch(chartQueryDistrict, debouncedDistrictReload(() => load()), { flush: "post" })

onMounted(() => {
  void load({ silent: true }).catch(() => {})
  stopPoll = startStaggeredPoll(
    TIANSHU_POLL_PERIOD_MS,
    TIANSHU_POLL_STAGGER.electricityUsage,
    () => void load({ silent: true }).catch(() => {}),
  )
})

onBeforeUnmount(() => {
  stopPoll?.()
})
</script>

<style lang="scss"></style>
