<template>
  <div class="left-card">
    <m-card title="客单价分布" :overlay-loading="chartRefreshing">
      <div class="pie-chat-wrap">
        <div class="pie-chat">
          <m-pie
            :key="pieKey"
            ref="pie"
            :data="state.pieData"
            :delay="3000"
            :colors="state.pieDataColor"
            :opacity="0.6"
            class="pieCanvas"
          >
            <template #default="slotProps">
              <div class="pieCanvas-content">
                <div class="pieCanvas-content-value">
                  <mCountTo
                    :startVal="0"
                    :endVal="getNumber(slotProps)"
                    :decimals="2"
                    :duration="1000"
                    :autoplay="true"
                  />
                  %
                </div>
                <div class="pieCanvas-content-name">
                  {{ slotProps.data.name }}
                </div>
              </div>
            </template>
          </m-pie>
        </div>

        <div class="pie-legend">
          <div class="pie-legend-item" v-for="(item, index) in state.pieData" :key="index">
            <div class="icon" :style="{ borderColor: state.pieDataColor[index] }"></div>
            <div class="name">{{ item.name }}</div>
            <div class="value">
              {{ item.value }}<span class="unit">单</span>
            </div>
          </div>
        </div>
      </div>
    </m-card>
  </div>
</template>
<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, inject, watch } from "vue"
import mCard from "@/components/mCard/index.vue"
import mPie from "@/components/mPie/index.vue"
import mCountTo from "@/components/mCountTo/index.js"
import {
  fetchJson,
  todayRangeQueryString,
  appendDistrictToQueryString,
  TIANSHU_CHART_QUERY_DISTRICT_KEY,
  debouncedDistrictReload,
} from "@/api/tianshuInsights.js"
import { TIANSHU_CYAN, TIANSHU_SKY, TIANSHU_INDIGO, TIANSHU_AMBER } from "../tianshuEchartsTheme.js"
import {
  startStaggeredPoll,
  TIANSHU_POLL_PERIOD_MS,
  TIANSHU_POLL_STAGGER,
} from "../composables/tianshuStaggeredPoll.js"

const API_BASE = "/api/insights/business"

const chartQueryDistrict = inject(TIANSHU_CHART_QUERY_DISTRICT_KEY, ref(null))
const chartRefreshing = ref(false)
let loadGen = 0

const pie = ref(null)
const pieKey = ref(0)
const state = reactive({
  pieDataColor: [TIANSHU_CYAN, TIANSHU_SKY, TIANSHU_INDIGO, TIANSHU_AMBER],
  pieData: [
    { name: "<500", value: 0 },
    { name: "500~2k", value: 0 },
    { name: "2k~5k", value: 0 },
    { name: ">5k", value: 0 },
  ],
})

function getNumber(slotProps) {
  const total = state.pieData.reduce((a, b) => a + Number(b.value || 0), 0)
  if (total <= 0) return 0
  return Number(((Number(slotProps.data.value || 0) / total) * 100).toFixed(2))
}

let stopPoll = null
let lastTicketBucketsPollKey = undefined

async function load(opts = {}) {
  const silent = opts.silent === true
  const g = ++loadGen
  if (!silent) chartRefreshing.value = true
  try {
    const baseQs = await todayRangeQueryString()
    const qs = appendDistrictToQueryString(baseQs, chartQueryDistrict.value)
    const data = await fetchJson(`${API_BASE}/cockpit-smart-side-insights?${qs}`)
    if (g !== loadGen) return
    const buckets = Array.isArray(data.ticket_buckets) ? data.ticket_buckets : []
    const order = ["lt500", "500_2k", "2k_5k", "gt5k"]
    const byKey = Object.fromEntries(buckets.map((b) => [b.key, b]))
    const nextPie = order.map((k) => {
      const b = byKey[k]
      return {
        name: b?.label || k,
        value: Number(b?.count) || 0,
      }
    })
    const dataKey = JSON.stringify(nextPie.map((x) => [x.name, x.value]))
    if (dataKey === lastTicketBucketsPollKey) return
    lastTicketBucketsPollKey = dataKey
    state.pieData = nextPie
    pieKey.value += 1
  } catch (e) {
    if (g === loadGen) console.warn("[tianshu] 客单价分布", e)
  } finally {
    if (g === loadGen && !silent) chartRefreshing.value = false
  }
}

watch(chartQueryDistrict, debouncedDistrictReload(() => load()), { flush: "post" })

onMounted(() => {
  void load({ silent: true }).catch(() => {})
  stopPoll = startStaggeredPoll(
    TIANSHU_POLL_PERIOD_MS,
    TIANSHU_POLL_STAGGER.yearlyEconomy,
    () => void load({ silent: true }).catch(() => {}),
  )
})

onBeforeUnmount(() => {
  stopPoll?.()
})
</script>
<style lang="scss">
.pie-chat-wrap {
  width: 100%;
  height: 100%;
  display: flex;
}
// 饼图
.pie-chat {
  pointer-events: all;
  position: relative;
  width: 236px;
  height: 100%;

  .pieCanvas {
    width: 100%;
    height: 100%;
    pointer-events: all;
  }
  .pieCanvas-content {
    width: 100%;
    height: 100%;
    margin-bottom: 30px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    color: #fff;
    font-size: 12px;
    &-value {
      font-size: 15px;
      font-weight: bold;
      text-shadow: 0 0 10px rgb(0 0 0);
    }
    &-name {
      width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: #fff;
      font-size: 12px;
      text-align: center;
    }
  }
}
// 饼图3d legend
.pie-legend {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  padding: 20px 0;
  &-item {
    display: flex;
    align-items: center;
    flex-wrap: nowrap;
    box-sizing: border-box;

    .icon {
      width: 10px;
      height: 10px;
      border-radius: 10px;
      border: 2px solid #17e6c3;
      box-sizing: border-box;
      margin-right: 10px;
    }
    .name {
      font-weight: 500;
      font-size: 12px;
      color: #ffffff;
    }
    .value {
      display: flex;
      flex-wrap: nowrap;
      align-items: flex-end;
      justify-content: flex-end;
      width: 80px;
      text-align: right;

      font-weight: bold;
      color: #ffffff;
      font-family: D-DIN;
      font-weight: bold;
      font-size: 16px;
      .unit {
        font-family: D-DIN;
        font-weight: 400;
        font-size: 10px;
        color: #ffffff;
        opacity: 0.5;
        padding-left: 10px;
      }
    }
  }
}
</style>
