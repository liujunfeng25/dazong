<template>
  <div class="right-card">
    <m-card
      title="补单 · 退单 · 订单"
      :title-hint="orderMixHint"
      :overlay-loading="chartRefreshing"
    >
      <div class="population-proportion">
        <div class="population-proportion-chart">
          <TianshuNativeEchart ref="vChart" :option="option" />
          <div class="label-name">订单占比</div>
        </div>
        <div class="pie-legend">
          <div class="pie-legend-item" v-for="(item, index) in state.pieData" :key="index">
            <div class="icon" :style="{ borderColor: state.pieDataColor[index] }"></div>
            <div class="name">{{ item.name }}</div>
            <div class="value">{{ item.value }}<span class="unit">%</span></div>
          </div>
        </div>
      </div>
    </m-card>
  </div>
</template>
<script setup>
import { ref, reactive, shallowRef, onMounted, onBeforeUnmount } from "vue"
import * as echarts from "echarts"
import mCard from "@/components/mCard/index.vue"
import TianshuNativeEchart from "./TianshuNativeEchart.vue"
import { fetchJson } from "@/api/tianshuInsights.js"
import { useTianshuChartResize } from "../composables/useTianshuChartResize.js"
import {
  startStaggeredPoll,
  TIANSHU_POLL_PERIOD_MS,
  TIANSHU_POLL_STAGGER,
} from "../composables/tianshuStaggeredPoll.js"
import {
  tianshuTooltipItem,
  TIANSHU_CYAN,
  TIANSHU_SKY,
  TIANSHU_AMBER,
} from "../tianshuEchartsTheme.js"

const API_BASE = "/api/insights/business"

const chartRefreshing = ref(false)
/** 与后端 today_order_mix.note 同步；旧接口无 note 时用本地兜底文案 */
const orderMixHint = ref(
  "今日范围：仅按下单时间 add_time 当日，与顶部「今日下单数」同为全市口径（本图不受地图区县筛选影响）。" +
    "三色（互斥、依次判定）：订单曾在 backorder 出现 → 退单；否则有补单号 disorder_id>0 → 补单；否则正常。",
)
let loadGen = 0

const vChart = ref(null)
useTianshuChartResize(vChart)

/** 与后端 today_order_mix 一致：退单 → 补单 → 正常（互斥） */
const SLICE_STYLES = [
  new echarts.graphic.LinearGradient(0, 0, 1, 1, [
    { offset: 0, color: "rgba(120, 70, 20, 1)" },
    { offset: 1, color: "rgba(251, 191, 36, 0.95)" },
  ]),
  new echarts.graphic.LinearGradient(0, 0, 1, 1, [
    { offset: 0, color: "rgba(20, 60, 100, 1)" },
    { offset: 1, color: "rgba(56, 189, 248, 0.92)" },
  ]),
  new echarts.graphic.LinearGradient(0, 0, 1, 1, [
    { offset: 0, color: "rgba(12, 48, 72, 1)" },
    { offset: 1, color: "rgba(92, 239, 255, 0.95)" },
  ]),
]

const NAMES = ["退单", "补单", "正常"]

const state = reactive({
  pieDataColor: [TIANSHU_AMBER, TIANSHU_SKY, TIANSHU_CYAN],
  pieData: NAMES.map((name, i) => ({ name, value: i === 2 ? 100 : 0 })),
})

const option = shallowRef({
  tooltip: { ...tianshuTooltipItem },

  series: [
    {
      name: "",
      type: "pie",
      itemStyle: {
        borderWidth: 5,
        borderColor: "rgba(26, 57, 77,1)",
      },
      label: { show: false },
      radius: ["55%", "70%"],
      color: [TIANSHU_AMBER, TIANSHU_SKY, TIANSHU_CYAN],

      data: NAMES.map((name, i) => ({
        value: i === 2 ? 1 : 0,
        name,
        itemStyle: { color: SLICE_STYLES[i] },
      })),
    },
  ],
})

let stopPoll = null
let lastOrderMixPollKey = undefined

function pct(num, den) {
  if (!den || den <= 0) return 0
  return Math.round((1000 * num) / den) / 10
}

async function load(opts = {}) {
  const silent = opts.silent === true
  const g = ++loadGen
  if (!silent) chartRefreshing.value = true
  try {
    // 与顶部 kpi-summary?scope=today 一致：全市、add_time 当日，不带收货区县筛选（避免与「今日下单数」总单数对不上）
    const ops = await fetchJson(`${API_BASE}/ops-alerts?limit=12`)
    if (g !== loadGen) return
    const mix = ops?.today_order_mix
    const hint = mix?.note
    const total = Number(mix?.total) || 0
    const ret = Number(mix?.n_return) || 0
    const sup = Number(mix?.n_supplement) || 0
    const norm = Number(mix?.n_normal) || 0
    const noteKey = typeof hint === "string" && hint.trim() ? hint.trim() : ""
    const dataKey = JSON.stringify([total, ret, sup, norm, noteKey])
    if (dataKey === lastOrderMixPollKey) return
    lastOrderMixPollKey = dataKey
    if (noteKey) orderMixHint.value = noteKey
    const counts = [ret, sup, norm]
    const p0 = pct(ret, total)
    const p1 = pct(sup, total)
    const p2 = pct(norm, total)
    const piePerc = [p0, p1, p2]
    for (let i = 0; i < 3; i += 1) {
      state.pieData[i].name = NAMES[i]
      state.pieData[i].value = total > 0 ? piePerc[i] : 0
    }

    option.value = {
      ...option.value,
      series: [
        {
          ...option.value.series[0],
          data: NAMES.map((name, i) => ({
            value: Math.max(0, counts[i]),
            name,
            itemStyle: { color: SLICE_STYLES[i] },
          })),
        },
      ],
    }
  } catch (e) {
    if (g === loadGen) console.warn("[tianshu] 补单 · 退单 · 订单", e)
  } finally {
    if (g === loadGen && !silent) chartRefreshing.value = false
  }
}

onMounted(() => {
  void load({ silent: true }).catch(() => {})
  stopPoll = startStaggeredPoll(
    TIANSHU_POLL_PERIOD_MS,
    TIANSHU_POLL_STAGGER.proportionPopulation,
    () => void load({ silent: true }).catch(() => {}),
  )
})

onBeforeUnmount(() => {
  stopPoll?.()
})
</script>
<style lang="scss">
.population-proportion {
  display: flex;
  height: 100%;
  &-chart {
    position: relative;
    width: 180px;
    height: 100%;
    margin-left: 15px;
    background: url("~@/assets/images/pie/pie-zs-bg.png") no-repeat;
    background-size: cover;
    .label-name {
      position: absolute;
      left: 50%;
      top: 50%;
      width: 72px;
      height: 72px;
      margin-left: -36px;
      margin-top: -36px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      color: #c4e3fd;
    }
    &:after {
      position: absolute;
      left: 50%;
      top: 50%;
      z-index: -1;
      margin-left: -36px;
      margin-top: -36px;
      content: "";
      width: 72px;
      height: 72px;
      background: url("~@/assets/images/pie/pie-mid-circle.png") no-repeat;
      background-size: cover;
      animation: rotate360Animate 2s linear infinite;
    }
  }
  .pie-legend {
    padding-left: 30px;
  }
}
</style>
