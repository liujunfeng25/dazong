const LS_KEY = "tianshu_map_visual_v1"

function cloneRgb(arr) {
  if (!Array.isArray(arr) || arr.length < 3) return [0.22, 0.28, 0.34]
  return [Number(arr[0]), Number(arr[1]), Number(arr[2])]
}

/** 与 MAP_VISUAL_DEFAULTs 合并前的原始覆盖（仅 localStorage） */
export function loadMapVisualOverrides() {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return {}
    const o = JSON.parse(raw)
    if (!o || typeof o !== "object") return {}
    return o
  } catch {
    return {}
  }
}

export function saveMapVisualSnapshot(visual) {
  const payload = { ...visual }
  if (Array.isArray(visual.extrudeTopRgbBoost)) {
    payload.extrudeTopRgbBoost = cloneRgb(visual.extrudeTopRgbBoost)
  }
  if (Array.isArray(visual.extrudeSideRgbBoost)) {
    payload.extrudeSideRgbBoost = cloneRgb(visual.extrudeSideRgbBoost)
  }
  localStorage.setItem(LS_KEY, JSON.stringify(payload))
}

export function clearMapVisualStorage() {
  localStorage.removeItem(LS_KEY)
}

export function mergeMapVisual(baseDefaults, overrides) {
  const v = { ...baseDefaults, ...overrides }
  v.extrudeTopRgbBoost = cloneRgb(
    overrides.extrudeTopRgbBoost ?? baseDefaults.extrudeTopRgbBoost,
  )
  v.extrudeSideRgbBoost = cloneRgb(
    overrides.extrudeSideRgbBoost ?? baseDefaults.extrudeSideRgbBoost,
  )
  return v
}
