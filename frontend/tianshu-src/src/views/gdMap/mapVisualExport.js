import { MAP_VISUAL_DEFAULTS } from "./mapVisualConfig.js"

const HEX_KEYS = new Set([
  "atmosphereColor",
  "ambientColor",
  "hemiSky",
  "hemiGround",
  "dirKeyColor",
  "dirFillColor",
  "dirRimColor",
  "extrudeTopTint",
  "extrudeSide1",
  "extrudeSide2",
  "mapTopGradient1",
  "mapTopGradient2",
  "mapHoverTint",
  "districtLineColor",
])

function fmtValue(key, val) {
  if (HEX_KEYS.has(key) && typeof val === "number" && val >= 0 && val <= 0xffffff) {
    return `0x${Math.floor(val).toString(16).padStart(6, "0")}`
  }
  if (typeof val === "string") return JSON.stringify(val)
  if (Array.isArray(val)) return `[${val.map((x) => Number(x).toFixed(4)).join(", ")}]`
  return JSON.stringify(val)
}

/**
 * 生成可粘贴到 mapVisualConfig.js 的 MAP_VISUAL_DEFAULTS 对象源码（保留字段顺序与注释提示）。
 */
export function formatMapVisualAsConfigModule(visual) {
  const keys = Object.keys(MAP_VISUAL_DEFAULTS)
  const body = keys
    .map((k) => `  ${k}: ${fmtValue(k, visual[k])},`)
    .join("\n")
  return `/**\n * 由 MapTuningPanel 导出——请整段替换 mapVisualConfig.js 中的 MAP_VISUAL_DEFAULTS\n */\nexport const MAP_VISUAL_DEFAULTS = {\n${body}\n}\n`
}
