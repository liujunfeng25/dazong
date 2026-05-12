<template>
  <div class="left-card">
    <m-card title="近日 GMV" :overlay-loading="chartRefreshing">
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
  resolveRangeQueryString,
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
  TIANSHU_SERIES_COLORS,
} from "../tianshuEchartsTheme.js"

const API_BASE = "/api/insights/business"

const chartQueryDistrict = inject(TIANSHU_CHART_QUERY_DISTRICT_KEY, ref(null))
const chartRefreshing = ref(false)
let loadGen = 0
let lastOrdersDailyPollKey = undefined

const option = shallowRef({
  title: {
    text: "元",
    subtext: "",
    left: "auto",
    right: "6%",
    top: "7%",
    textAlign: "right",
    textStyle: { ...tianshuTitleSubtextStyle },
    subtextStyle: {
      color: "rgba(186, 232, 245, 0.62)",
      fontSize: 7,
    },
  },
  grid: {
    left: "12%",
    top: "22%",
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
      data: [],
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
      data: [],
      type: "line",
      smooth: true,
      symbol:
        "image://data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABQAAAAUCAYAAACNiR0NAAAAAXNSR0IArs4c6QAAAQ5JREFUOE+1la1OQ0EQRs8kCFIQdVCCxIBpCK1AInkDHC+B4QkwvASub4GsaE0NGCRpKhGFVDQZ+Mjem9vNbkphmWTMfjNnd3b2x0iYuxuwH7wNbIewBfAGzORm5nG6ElfM3QU6AXZSkzXG3oEnMxO8thWgux8DR2tAsfxiZs/VYA38Jazi1NBvYCizv+HK4vCRyrfQgIsf7Nm6+bSnjwIeAGeZaGnXQDfoE+ABmGbixwKeAoeJAMHuv3w30ubATQb6KqDKjZPEuAXOMysZAncJbS7gJbCVEAdAKwP8AK4S2vJfgMVLLt6UDtAreWx0W8od7OJXryq16OPwR2j6+WpAyz2wDagape7vARt9AZ+G3HmhiKS3xwAAAABJRU5ErkJggg==",
      symbolSize: 10,
      showSymbol: false,
      yAxisIndex: 0,
      z: 0,
      emphasis: {
        focus: "none",
        itemStyle: { color: "white" },
      },
      label: {
        show: true,
        position: "top",
        distance: 10,
        color: "#ffffff",
        fontSize: 10,
      },
      lineStyle: {
        shadowColor: "rgba(0, 0, 0, 0.4)",
        shadowBlur: 3,
        shadowOffsetY: 10,
        width: 3,
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: TIANSHU_SERIES_COLORS[0] },
          { offset: 1, color: "rgba(18,60,98,1)" },
        ]),
      },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: "rgba(25, 255, 236, 0.4)" },
          { color: "rgba(51, 153, 255, 0)", offset: 1 },
        ]),
      },
    },
  ],
})

const vChart = ref(null)
useTianshuChartResize(vChart)

let stopPoll = null

function formatDayLabel(dayStr) {
  if (!dayStr || typeof dayStr !== "string") return "—"
  const p = dayStr.slice(5).replace("-", "/")
  return p || "—"
}

function formatRangeSubtext(startIso, endIso) {
  const a = formatDayLabel(String(startIso || ""))
  const b = formatDayLabel(String(endIso || ""))
  if (a === "—" && b === "—") return ""
  if (a === b) return a
  return `${a}～${b}`
}

async function load(opts = {}) {
  const silent = opts.silent === true
  const g = ++loadGen
  if (!silent) chartRefreshing.value = true
  try {
    const baseQs = await resolveRangeQueryString()
    const qs = appendDistrictToQueryString(baseQs, chartQueryDistrict.value)
    const data = await fetchJson(`${API_BASE}/orders-daily?${qs}`)
    if (g !== loadGen) return
    const series = Array.isArray(data.series) ? [...data.series] : []
    series.sort((a, b) => String(a.day).localeCompare(String(b.day)))
    /** 仅展示接口返回区间内的真实日序，不再左侧补「—」占位（避免误认为前面缺数） */
    const last12 = series.slice(-12)
    const labels = []
    const valuesYuan = []
    if (last12.length === 0) {
      labels.push("—")
      valuesYuan.push(0)
    } else {
      for (const row of last12) {
        labels.push(formatDayLabel(row.day))
        valuesYuan.push(Math.round(Number(row.gmv) || 0))
      }
    }
    const subtext = formatRangeSubtext(data.start_date, data.end_date)
    const dataKey = JSON.stringify({ labels, v: valuesYuan, subtext })
    if (dataKey === lastOrdersDailyPollKey) return
    lastOrdersDailyPollKey = dataKey
    option.value = {
      ...option.value,
      title: {
        ...option.value.title,
        subtext,
      },
      xAxis: [{ ...option.value.xAxis[0], data: labels }, option.value.xAxis[1]],
      series: [{ ...option.value.series[0], data: valuesYuan }],
    }
  } catch (e) {
    if (g === loadGen) console.warn("[tianshu] 近日 GMV", e)
  } finally {
    if (g === loadGen && !silent) chartRefreshing.value = false
  }
}

watch(chartQueryDistrict, debouncedDistrictReload(() => load()), { flush: "post" })

onMounted(() => {
  void load({ silent: true }).catch(() => {})
  stopPoll = startStaggeredPoll(
    TIANSHU_POLL_PERIOD_MS,
    TIANSHU_POLL_STAGGER.economicTrend,
    () => void load({ silent: true }).catch(() => {}),
  )
})

onBeforeUnmount(() => {
  stopPoll?.()
})
</script>
<style lang="scss"></style>
