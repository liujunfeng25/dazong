<template>
  <div class="right-card">
    <m-card title="今日时段分布" :overlay-loading="chartRefreshing">
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
  aggregateIntradayTo6hBins,
  SIX_HOUR_LABELS,
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

const option = shallowRef({
  title: {
    text: "元 / 单",
    left: "5%",
    top: "8%",
    textStyle: { ...tianshuTitleSubtextStyle },
  },
  legend: {
    top: "4%",
    icon: "circle",
    itemWidth: 8,
    itemHeight: 8,
    textStyle: { ...tianshuLegendTextStyle },
    data: ["成交额", "订单数"],
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
      data: [...SIX_HOUR_LABELS],
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
  yAxis: [
    {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { ...tianshuSplitLineY },
      axisLabel: { ...tianshuAxisLabelValue },
    },
    {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { ...tianshuAxisLabelValue },
    },
  ],
  series: [
    {
      name: "成交额",
      yAxisIndex: 0,
      data: [0, 0, 0, 0],
      type: "bar",
      barWidth: 4,
      label: {
        show: false,
      },
      itemStyle: {
        borderRadius: 0,
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: TIANSHU_SERIES_COLORS[0] },
          { offset: 1, color: "rgba(12, 48, 72, 1)" },
        ]),
      },
    },
    {
      name: "订单数",
      yAxisIndex: 1,
      data: [0, 0, 0, 0],
      type: "bar",
      barWidth: 4,
      barGap: 2,
      label: {
        show: false,
      },
      itemStyle: {
        borderRadius: 0,
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: TIANSHU_SERIES_COLORS[1] },
          { offset: 1, color: "rgba(30, 58, 95, 1)" },
        ]),
      },
    },
  ],
})

const vChart = ref(null)
useTianshuChartResize(vChart)

let stopPoll = null
let lastIntraday6hPollKey = undefined

async function load(opts = {}) {
  const silent = opts.silent === true
  const g = ++loadGen
  if (!silent) chartRefreshing.value = true
  try {
    const qs = appendDistrictToQueryString("", chartQueryDistrict.value)
    const url = qs
      ? `${API_BASE}/today-intraday-gmv?${qs}`
      : `${API_BASE}/today-intraday-gmv`
    const res = await fetchJson(url)
    if (g !== loadGen) return
    const t0 = Number(res.day_start_ts) || 0
    const { gmv, orders } = aggregateIntradayTo6hBins(t0, res.buckets)
    const gmvYuan = gmv.map((x) => Math.round(Number(x) || 0))
    const dataKey = JSON.stringify({ t0, gmvYuan, orders })
    if (dataKey === lastIntraday6hPollKey) return
    lastIntraday6hPollKey = dataKey
    option.value = {
      ...option.value,
      xAxis: [{ ...option.value.xAxis[0], data: [...SIX_HOUR_LABELS] }, option.value.xAxis[1]],
      series: [
        { ...option.value.series[0], data: gmvYuan },
        { ...option.value.series[1], data: orders },
      ],
    }
  } catch (e) {
    if (g === loadGen) console.warn("[tianshu] 今日时段分布", e)
  } finally {
    if (g === loadGen && !silent) chartRefreshing.value = false
  }
}

watch(chartQueryDistrict, debouncedDistrictReload(() => load()), { flush: "post" })

onMounted(() => {
  void load({ silent: true }).catch(() => {})
  stopPoll = startStaggeredPoll(
    TIANSHU_POLL_PERIOD_MS,
    TIANSHU_POLL_STAGGER.quarterlyGrowth,
    () => void load({ silent: true }).catch(() => {}),
  )
})

onBeforeUnmount(() => {
  stopPoll?.()
})
</script>
<style lang="scss"></style>
