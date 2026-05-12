/** 天枢大屏 HTTP 轮询：统一周期 + 错开首次触发，避免同一帧内集体 setOption / 主线程尖峰 */

export const TIANSHU_POLL_PERIOD_MS = 60_000

/** 相对整分钟周期的偏移（毫秒），与 {@link TIANSHU_POLL_PERIOD_MS} 相加为首次执行延迟 */
export const TIANSHU_POLL_STAGGER = {
  dashboardKpi: 0,
  dashboardPillars: 8_000,
  economicTrend: 3_500,
  bulkCommodity: 7_000,
  purposeSpecialFunds: 10_500,
  quarterlyGrowth: 14_000,
  electricityUsage: 17_500,
  districtEconomic: 21_000,
  proportionPopulation: 24_500,
  yearlyEconomy: 28_000,
}

/**
 * 首次在 periodMs + staggerMs 时执行 fn，之后每 periodMs 重复（以上一次 fn  settled 为起点）。
 * @param {number} periodMs
 * @param {number} staggerMs
 * @param {() => void | Promise<void>} fn
 * @returns {() => void} 取消后续调度
 */
export function startStaggeredPoll(periodMs, staggerMs, fn) {
  let id = null
  let cancelled = false
  function clear() {
    cancelled = true
    if (id != null) {
      clearTimeout(id)
      id = null
    }
  }
  function tick() {
    if (cancelled) return
    void Promise.resolve(fn()).finally(() => {
      if (cancelled) return
      id = setTimeout(tick, periodMs)
    })
  }
  id = setTimeout(tick, periodMs + staggerMs)
  return clear
}
