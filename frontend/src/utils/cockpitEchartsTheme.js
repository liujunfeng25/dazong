// 价格驾驶舱共享 ECharts 主题 —— 原生复刻「天枢」发光语言（cyan/sky/indigo/amber）
// 所有图表统一引用这里的色板与样式片段，保证全屏大屏观感一致。
import * as echarts from 'echarts'

export const COCKPIT_COLORS = {
  cyan: '#5cefff',
  cyanCore: '#00e5ff',
  sky: '#38bdf8',
  indigo: '#818cf8',
  amber: '#fbbf24',
  warn: '#ffd166',
  up: '#ff7a90', // 价格上行（偏贵 / 涨）
  down: '#5fe3a1', // 价格下行（便宜 / 跌）
  axis: '#7f9aa6',
  split: 'rgba(0,229,255,.08)',
}

// 玻璃感悬浮提示
export const glassTooltip = {
  backgroundColor: 'rgba(8,16,30,.94)',
  borderColor: 'rgba(92,239,255,.32)',
  borderWidth: 1,
  textStyle: { color: '#e8fbff', fontSize: 12 },
  extraCssText: 'box-shadow:0 12px 32px rgba(0,0,0,.45);backdrop-filter:blur(8px);border-radius:8px;',
}

export const catAxis = (data, extra = {}) => ({
  type: 'category',
  data,
  boundaryGap: false,
  axisLabel: { color: COCKPIT_COLORS.axis, fontSize: 10, ...(extra.axisLabel || {}) },
  axisLine: { lineStyle: { color: 'rgba(92,239,255,.22)' } },
  axisTick: { show: false },
  ...extra,
})

export const valAxis = (extra = {}) => ({
  type: 'value',
  scale: true,
  axisLabel: { color: COCKPIT_COLORS.axis, fontSize: 10 },
  axisLine: { show: false },
  splitLine: { lineStyle: { color: COCKPIT_COLORS.split, type: 'dashed' } },
  ...extra,
})

// 线下渐变填充
export const areaGradient = (hex, topAlpha = 0.28, bottomAlpha = 0.02) => {
  const rgba = (a) => {
    const h = hex.replace('#', '')
    const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16)
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
  }
  return new echarts.graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: rgba(topAlpha) },
    { offset: 1, color: rgba(bottomAlpha) },
  ])
}

// 发光折线样式
export const glowLine = (hex, width = 2.6) => ({
  color: hex,
  width,
  shadowColor: hex,
  shadowBlur: 12,
})
