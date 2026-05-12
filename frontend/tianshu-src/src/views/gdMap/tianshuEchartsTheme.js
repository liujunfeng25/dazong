/** 天枢大屏 ECharts 统一基线：冷色主序列 + 弱网格 + 玻璃风 tooltip（琥珀仅作语义色，在业务里单独指定） */

export const TIANSHU_CYAN = "#5cefff"
export const TIANSHU_SKY = "#38bdf8"
export const TIANSHU_INDIGO = "#818cf8"
export const TIANSHU_AMBER = "#fbbf24"

/** 折线/柱状主色序列（2～3 冷色） */
export const TIANSHU_SERIES_COLORS = [TIANSHU_CYAN, TIANSHU_SKY, TIANSHU_INDIGO]

export const tianshuTooltipAxisShadow = {
  trigger: "axis",
  backgroundColor: "rgba(10, 22, 40, 0.92)",
  borderWidth: 1,
  borderColor: "rgba(103, 232, 249, 0.32)",
  padding: [8, 10],
  extraCssText:
    "box-shadow:0 12px 32px rgba(0,0,0,0.42);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);",
  textStyle: {
    color: "#e8f8ff",
    fontSize: 11,
  },
  axisPointer: {
    type: "shadow",
    shadowStyle: {
      color: "rgba(56, 189, 248, 0.07)",
    },
  },
}

export const tianshuTooltipItem = {
  trigger: "item",
  backgroundColor: "rgba(10, 22, 40, 0.92)",
  borderWidth: 1,
  borderColor: "rgba(103, 232, 249, 0.32)",
  padding: [8, 10],
  extraCssText:
    "box-shadow:0 12px 32px rgba(0,0,0,0.42);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);",
  textStyle: {
    color: "#e8f8ff",
    fontSize: 11,
  },
}

/** 弱化 Y 轴参考网格 */
export const tianshuSplitLineY = {
  show: true,
  lineStyle: {
    type: [4, 6],
    color: "rgba(103, 232, 249, 0.1)",
    width: 1,
  },
}

export const tianshuAxisLabelCategory = {
  color: "rgba(190, 225, 245, 0.92)",
  fontSize: 10,
}

export const tianshuAxisLabelValue = {
  color: "rgba(148, 190, 215, 0.72)",
  fontSize: 9,
}

export const tianshuTitleSubtextStyle = {
  color: "rgba(186, 232, 245, 0.78)",
  fontSize: 8,
}

export const tianshuLegendTextStyle = {
  color: "rgba(176, 214, 232, 0.82)",
  fontSize: 12,
  lineHeight: 20,
}
