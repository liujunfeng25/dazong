<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Cpu,
  FullScreen,
  Histogram,
  MapLocation,
  Odometer,
  QuestionFilled,
  Timer,
  Van,
} from '@element-plus/icons-vue'
import {
  commitRoutePlanApi,
  deliveryOrderPoolApi,
  dispatchPlanningSummaryApi,
  listDeliveryGeofencesApi,
  listDeliveryVehiclesApi,
  routePlanApi,
} from '../../api/delivery'
import { limitStatusDisplay } from '../../utils/beijingVehicleLimit'
import { createEmptyRoutePlan, hasGeneratedRoutePlan } from '../../utils/routePlanState'
import { useUserStore } from '../../stores/user'
import { useRouter, useRoute } from 'vue-router'

const chartRef = ref(null)
const amapIns = ref(null)
const amapReady = ref(false)
const amapOverlays = ref([])
/** 地图容器从 0 尺寸变为可见（懒加载 Tab、侧栏布局）时需 resize，否则底图瓦片错位呈「网格+怪多边形」 */
let mapResizeObserver = null
let mapResizeDebounceTimer = null
/** 禁行区域（电子围栏 Tab 维护），仅在路线规划地图展示；不参与分检/收货区 */
const noGoFences = ref([])
const loading = ref(false)
const commitLoading = ref(false)
const orderPool = ref([])
const planningSummary = ref(null)
const planWarnings = ref([])
const selectedOrderIds = ref([])
const userStore = useUserStore()
const router = useRouter()
const route = useRoute()
const currentDeliveryId = computed(() => Number(userStore.userInfo?.id || 0))

const planningDate = ref(
  (() => {
    const d = new Date()
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  })(),
)
const departureTime = ref('06:00')
/** 禁行围栏：normal 与现网一致（避让失败可降级无避让）；strict 禁止降级，失败整单报错 */
const geofencePolicy = ref('normal')
/** 车牌 -> HH:mm，仅保存与上方「默认发车」不同的按车覆盖 */
const vehicleDepartureOverrides = ref({})
const showVehicleDepartureTable = ref(false)
const deliveryVehicles = ref([])
const serviceMinutesDefault = ref(30)
const serviceByOrder = ref({})
const selectedVehicleKey = ref('all')
const manualDialogVisible = ref(false)
const manualSubmitting = ref(false)
const manualVehicleId = ref(null)
const manualDepartureTime = ref('06:00')
const manualOrderIds = ref([])
/** 总览区「限行与车辆」下拉筛选，空字符串表示显示全部 */
const limitPlateFilter = ref('')
/** 用户手动「停用排线」的车牌：仅内存保留，在下次点击「生成智能路线」时随请求提交；排线成功后自动清空 */
const userDisabledVehicleNos = ref([])
const userDisabledSet = computed(() => new Set(userDisabledVehicleNos.value.map((x) => String(x || '').trim()).filter(Boolean)))

const showServiceTable = ref(false)
/** 停靠序列表格：关键词筛选（订单号 / 客户 / 车牌 / 约定窗） */
const stopsTableKeyword = ref('')

/** 路线规划结果（须早于依赖 plan 的 computed / watch，避免 TDZ） */
const plan = ref(createEmptyRoutePlan())

const invalidateGeneratedPlan = () => {
  if (!hasGeneratedRoutePlan(plan.value)) return
  plan.value = createEmptyRoutePlan()
  planWarnings.value = []
  selectedVehicleKey.value = 'all'
  limitPlateFilter.value = ''
  nextTick(() => renderRoute())
}

/** 优化收益对比：动效展示用 */
const animBaselineKm = ref(0)
const animOptimizedKm = ref(0)
const animSavedKm = ref(0)
const animBaselineMin = ref(0)
const animOptimizedMin = ref(0)
const animSavedMin = ref(0)
let compareAnimRaf = null

const customerDemoVisible = ref(false)
const customerDemoStep = ref(0)
const compareCollapseActive = ref([])

const CAPABILITY_BADGE_TIPS = {
  北斗定位接入: '与北斗能力对接展示位（当前为演示徽章）。',
  '高德驾车路径与ETA': '路段距离与耗时优先请求高德驾车；失败时降级为直线距离与经验车速。',
  载重容积约束: '按车辆核定载重与容积约束参与分配与预警。',
  顺路策略: '在同车多站间优先减少折返与空驶的分配倾向。',
  '时窗策略（演示）': '以客户下单配送日及 1 小时时段截止为硬约束参与排序与 ETA。',
  '禁行区避让（高德+分配惩罚）': '禁行围栏参与高德避让参数与分配侧惩罚，降低驶入风险。',
}

const badgeTip = (label) => CAPABILITY_BADGE_TIPS[label] || '路线规划能力组件，详见停靠序列表与风险提示。'

const optCompare = computed(() => plan.value?.optimization_compare || {})

const routingModeLabel = computed(() => {
  const r = plan.value?.data_quality?.routing
  if (r === 'amap_driving') return '高德驾车（全段命中）'
  if (r === 'mixed') return '混合（部分高德 + 部分降级）'
  if (r === 'fallback') return '降级估算（直线+经验车速）'
  return '—'
})

/** 从停靠点累加里程/时长（与后端 total 口径一致，作展示回退） */
const sumDistanceKmFromStops = () => {
  const stops = plan.value?.stops || []
  return Math.round(stops.reduce((s, x) => s + Number(x.distance_from_prev_km || 0), 0) * 100) / 100
}

const sumDurationMinFromStops = () => {
  const stops = plan.value?.stops || []
  return stops.reduce((s, x) => s + Number(x.travel_minutes || 0) + Number(x.service_minutes || 0), 0)
}

/**
 * 解析对比卡片用的目标数值：优先 optimization_compare；
 * 缺字段或后端给 0 但停靠点有路段累计时，回退 total_distance_km / estimated_duration_minutes 或停靠点求和。
 */
const resolveCompareTargets = () => {
  const stops = plan.value?.stops || []
  if (!stops.length) return null
  const oc = plan.value?.optimization_compare || {}
  const sumKm = sumDistanceKmFromStops()
  const sumMin = sumDurationMinFromStops()
  const rootKm = Number(plan.value?.total_distance_km)
  const rootMin = Number(plan.value?.estimated_duration_minutes)

  let oKm = Number(oc.optimized_distance_km)
  if (!Number.isFinite(oKm) || oKm < 0) {
    oKm = Number.isFinite(rootKm) && rootKm >= 0 ? rootKm : sumKm
  } else if (oKm === 0 && sumKm > 0) {
    oKm = sumKm
  }

  let oMin = Number(oc.optimized_duration_minutes)
  if (!Number.isFinite(oMin) || oMin < 0) {
    oMin = Number.isFinite(rootMin) && rootMin >= 0 ? rootMin : sumMin
  } else if (oMin === 0 && sumMin > 0) {
    oMin = sumMin
  }

  const upliftKm = Number(oc.baseline_distance_uplift_ratio ?? 0.12)
  const upliftMin = Number(oc.baseline_duration_uplift_ratio ?? 0.14)
  let bKm = Number(oc.baseline_distance_km)
  if (!Number.isFinite(bKm) || bKm <= 0) {
    bKm = Math.round(oKm * (1 + (Number.isFinite(upliftKm) ? upliftKm : 0.12)) * 100) / 100
  }
  let bMin = Number(oc.baseline_duration_minutes)
  if (!Number.isFinite(bMin) || bMin <= 0) {
    bMin = Math.round(oMin * (1 + (Number.isFinite(upliftMin) ? upliftMin : 0.14)))
  }

  let sKm = Number(oc.distance_saved_km)
  if (!Number.isFinite(sKm)) sKm = Math.round(Math.max(0, bKm - oKm) * 100) / 100
  let sMin = Number(oc.duration_saved_minutes)
  if (!Number.isFinite(sMin)) sMin = Math.max(0, bMin - oMin)

  return { bKm, oKm, sKm, bMin, oMin, sMin }
}

/** 计算简报弹窗与动效共用一套解析结果 */
const briefCompareSnapshot = computed(() => resolveCompareTargets())

const kmOptimizedBarPct = computed(() => {
  const b = Number(animBaselineKm.value) || 0
  const o = Number(animOptimizedKm.value) || 0
  if (b <= 0) return 0
  return Math.min(100, (o / b) * 100)
})

const minOptimizedBarPct = computed(() => {
  const b = Number(animBaselineMin.value) || 0
  const o = Number(animOptimizedMin.value) || 0
  if (b <= 0) return 0
  return Math.min(100, (o / b) * 100)
})

const startCompareAnim = () => {
  if (compareAnimRaf) cancelAnimationFrame(compareAnimRaf)
  compareAnimRaf = null
  const t = resolveCompareTargets()
  if (!t) {
    animBaselineKm.value = 0
    animOptimizedKm.value = 0
    animSavedKm.value = 0
    animBaselineMin.value = 0
    animOptimizedMin.value = 0
    animSavedMin.value = 0
    return
  }
  const dur = 780
  const t0 = performance.now()
  const ease = (x) => 1 - (1 - x) * (1 - x)
  const tick = (now) => {
    const u = Math.min(1, (now - t0) / dur)
    const k = ease(u)
    animBaselineKm.value = Math.round(t.bKm * k * 100) / 100
    animOptimizedKm.value = Math.round(t.oKm * k * 100) / 100
    animSavedKm.value = Math.round(t.sKm * k * 100) / 100
    animBaselineMin.value = Math.round(t.bMin * k)
    animOptimizedMin.value = Math.round(t.oMin * k)
    animSavedMin.value = Math.round(t.sMin * k)
    if (u < 1) {
      compareAnimRaf = requestAnimationFrame(tick)
    } else {
      animBaselineKm.value = t.bKm
      animOptimizedKm.value = t.oKm
      animSavedKm.value = t.sKm
      animBaselineMin.value = t.bMin
      animOptimizedMin.value = t.oMin
      animSavedMin.value = t.sMin
      compareAnimRaf = null
    }
  }
  compareAnimRaf = requestAnimationFrame(tick)
}

/**
 * 须与「计算简报」同源：原先 watch 只依赖 stops 数组引用，未在 getter 内读取各站
 * distance_from_prev_km / travel_minutes 等，异步回填路段后不会触发，导致主卡片 anim* 卡在 0
 * 而 briefCompareSnapshot 会随这些字段更新。
 */
watch(
  briefCompareSnapshot,
  () => {
    nextTick(() => startCompareAnim())
  },
  { immediate: true },
)

const openBriefDialog = () => {
  if (!(plan.value?.stops || []).length) {
    ElMessage.warning('请先生成智能路线后再打开计算简报')
    return
  }
  customerDemoStep.value = 0
  customerDemoVisible.value = true
}

const toYmd = (d) => {
  if (typeof d === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(d)) return d
  const dt = d instanceof Date ? d : new Date(d)
  const y = dt.getFullYear()
  const m = String(dt.getMonth() + 1).padStart(2, '0')
  const day = String(dt.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const animRaf = ref(null)
const animMarker = ref(null)
const animInfo = ref(null)
const isPlaying = ref(false)

/** 本次返回结果中未纳入排线的车辆（含尾号限行、外地牌、用户停用等） */
const excludedFromPlanMap = computed(() => {
  const m = new Map()
  for (const x of plan.value?.vehicles_excluded_from_planning || []) {
    const k = String(x?.vehicle_no || '').trim()
    if (k) m.set(k, x)
  }
  return m
})

const isPendingUserDisable = (row) => userDisabledSet.value.has(String(row?.vehicle_no || '').trim())

const isExcludedFromThisPlan = (row) =>
  excludedFromPlanMap.value.has(String(row?.vehicle_no || '').trim())

/** 车牌条弱化：待提交的停用，或本次排线结果已剔除 */
const isLimitChipDimmed = (row) => isPendingUserDisable(row) || isExcludedFromThisPlan(row)

const setVehicleUserDisabled = (vehicleNo, disabled) => {
  const key = String(vehicleNo || '').trim()
  if (!key) return
  const s = new Set(userDisabledVehicleNos.value)
  if (disabled) s.add(key)
  else s.delete(key)
  userDisabledVehicleNos.value = [...s]
  invalidateGeneratedPlan()
}

const limitChipTooltip = (v) => {
  const parts = []
  if (v?.reason) parts.push(String(v.reason))
  const no = String(v?.vehicle_no || '').trim()
  const ex = excludedFromPlanMap.value.get(no)
  if (ex) {
    const r = ex.reason != null ? String(ex.reason) : ''
    const st = ex.limit_status != null ? String(ex.limit_status) : ''
    if (r) parts.push(`本次排线未纳入：${r}`)
    else if (st) parts.push(`本次排线未纳入（${st}）。`)
    else parts.push('本次智能排线未纳入该车。')
  }
  if (isPendingUserDisable(v)) {
    parts.push('已勾选「停用排线」：仅在您下次点击「生成智能路线」时随请求排除，不写入浏览器。')
  }
  return parts.join('\n\n') || '—'
}

const routingHint = computed(() => {
  const dq = plan.value?.data_quality || {}
  const total = Number(dq.amap_legs_total || 0)
  const ok = Number(dq.amap_legs_ok || 0)
  const r = dq.routing
  if (total <= 0) return ''
  if (r === 'amap_driving') return `路段 ETA：高德驾车 ${ok}/${total} 段全部命中。`
  if (r === 'mixed') return `路段 ETA：高德驾车 ${ok}/${total} 段，其余已直线+经验车速降级。`
  return '路段 ETA：未取到高德驾车结果，当前为直线距离与经验车速估算。'
})

const limitSummaryText = computed(() => {
  const v = plan.value?.vehicle_limit_today
  if (!v) return ''
  const day = v.date ? `${v.date} ` : ''
  if (!v.available) return v.message || '限行接口不可用，以下为规则内推断'
  if (!(v.digits || []).length) return `${v.city || '北京'}${day}尾号：接口显示不限行`
  return `${v.city || '北京'}${day}限行尾号：${(v.digits || []).join('、')}${v.raw_text ? `（${v.raw_text}）` : ''}`
})

const filteredStops = computed(() => {
  let list = plan.value.stops || []
  if (selectedVehicleKey.value !== 'all') {
    list = list.filter((s) => String(s.vehicle_no) === String(selectedVehicleKey.value))
  }
  const kw = String(stopsTableKeyword.value || '').trim().toLowerCase()
  if (kw) {
    list = list.filter((s) => {
      const blob = [
        String(s.order_no || ''),
        String(s.client_name || ''),
        String(s.vehicle_no || ''),
        String(s.client_delivery_window || s.time_window || ''),
      ]
        .join('\u0000')
        .toLowerCase()
      return blob.includes(kw)
    })
  }
  return list
})

const limitVehicleRows = computed(() => plan.value?.vehicle_limit_today?.vehicles || [])

const limitChipsFiltered = computed(() => {
  const list = limitVehicleRows.value
  const f = String(limitPlateFilter.value || '').trim()
  const rows = f ? list.filter((v) => String(v.vehicle_no) === f) : [...list]
  rows.sort((a, b) => {
    const ad = isLimitChipDimmed(a) ? 1 : 0
    const bd = isLimitChipDimmed(b) ? 1 : 0
    return bd - ad
  })
  return rows
})

const selectedOrdersForPlan = computed(() =>
  (orderPool.value || []).filter((row) => selectedOrderIds.value.includes(Number(row.id))),
)

const orderDispatchLabel = (row) => {
  if (row?.dispatch_readiness) return row.dispatch_readiness
  if (String(row?.status || '') === '下单' || Number(row?.allocation_total || 0) <= 0) return '未分单仅预估'
  if (!row?.all_allocations_shipped) return '待供货商出库'
  if (!row?.delivery_sort_all_done) return '待分检'
  return '待取货'
}

const orderDispatchTagType = (row) => {
  const label = orderDispatchLabel(row)
  if (label === '未分单仅预估') return 'info'
  if (label === '待取货') return 'success'
  return 'warning'
}

const canOrderSaveDispatch = (row) => {
  if (row?.dispatch_save_ready !== undefined) return Boolean(row.dispatch_save_ready)
  return String(row?.status || '') === '配货' && Number(row?.allocation_total || 0) > 0
}

const dispatchSaveBlockers = computed(() => selectedOrdersForPlan.value.filter((row) => !canOrderSaveDispatch(row)))

const plannedRouteOrderIds = computed(() => {
  const ids = new Set()
  const routes = Array.isArray(plan.value?.vehicle_routes) ? plan.value.vehicle_routes : []
  for (const route of routes) {
    for (const stop of route?.stops || []) {
      if (stop?.order_id != null) ids.add(Number(stop.order_id))
    }
  }
  if (!ids.size) {
    for (const stop of plan.value?.stops || []) {
      if (stop?.order_id != null) ids.add(Number(stop.order_id))
    }
  }
  return ids
})

const plannedOrdersForSave = computed(() =>
  (orderPool.value || []).filter((row) => plannedRouteOrderIds.value.has(Number(row.id))),
)

const planDispatchSaveBlockers = computed(() => plannedOrdersForSave.value.filter((row) => !canOrderSaveDispatch(row)))

const canSaveGeneratedPlan = computed(() => {
  const routes = Array.isArray(plan.value?.vehicle_routes) ? plan.value.vehicle_routes : []
  return routes.length > 0 && planDispatchSaveBlockers.value.length === 0
})

const buildDispatchBlockerText = (rows) => {
  if (!rows.length) return ''
  const sample = rows
    .slice(0, 3)
    .map((row) => row.order_no || `#${row.id}`)
    .join('、')
  const more = rows.length > 3 ? ` 等 ${rows.length} 单` : ''
  return `${sample}${more} 尚未完成智能分单，只能参与预排线，不能保存为发车计划。`
}

const dispatchSaveBlockerText = computed(() => buildDispatchBlockerText(dispatchSaveBlockers.value))
const planDispatchSaveBlockerText = computed(() => buildDispatchBlockerText(planDispatchSaveBlockers.value))

const manualDispatchableOrders = computed(() => (orderPool.value || []).filter(canOrderSaveDispatch))
const manualDispatchableOrderMap = computed(
  () => new Map(manualDispatchableOrders.value.map((row) => [Number(row.id), row])),
)
const manualSelectedOrders = computed(() =>
  manualOrderIds.value.map((id) => manualDispatchableOrderMap.value.get(Number(id))).filter(Boolean),
)

const activeVehicleRoute = computed(() => {
  const routes = plan.value.vehicle_routes || []
  if (selectedVehicleKey.value === 'all') return null
  return routes.find((r) => String(r.vehicle_no) === String(selectedVehicleKey.value)) || null
})

watch(
  selectedOrderIds,
  (ids) => {
    invalidateGeneratedPlan()
    const next = { ...serviceByOrder.value }
    ids.forEach((id) => {
      if (next[id] === undefined) next[id] = Number(serviceMinutesDefault.value) || 30
    })
    Object.keys(next).forEach((k) => {
      if (!ids.includes(Number(k))) delete next[k]
    })
    serviceByOrder.value = next
  },
  { deep: true },
)

watch(serviceMinutesDefault, (v) => {
  invalidateGeneratedPlan()
  const n = Number(v) || 30
  selectedOrderIds.value.forEach((id) => {
    if (serviceByOrder.value[id] === undefined) serviceByOrder.value[id] = n
  })
})

watch(serviceByOrder, invalidateGeneratedPlan, { deep: true })
watch([departureTime, geofencePolicy], invalidateGeneratedPlan)
watch(deliveryVehicles, invalidateGeneratedPlan, { deep: true })

const loadPool = async () => {
  orderPool.value = await deliveryOrderPoolApi(120, toYmd(planningDate.value), {
    statuses: ['下单', '配货'],
    excludeActiveDispatch: true,
    includeDispatchReadiness: true,
  })
}

const loadPlanningSummary = async () => {
  try {
    planningSummary.value = await dispatchPlanningSummaryApi(toYmd(planningDate.value))
  } catch {
    planningSummary.value = null
  }
}

const unplannedOrderCount = computed(() => Number(planningSummary.value?.unplanned_order_count ?? 0))
const availableVehicleCount = computed(() => Number(planningSummary.value?.vehicles_available_count ?? 0))
const newUnplannedOrders = computed(() => (orderPool.value || []).filter((row) => row.is_new_unplanned))
const noVehicleGuidanceText = computed(() => {
  if (availableVehicleCount.value > 0) return ''
  const occupied = Number(planningSummary.value?.vehicles_occupied_count ?? 0)
  if (occupied <= 0) return ''
  return (
    `计划日 ${planningDate.value} 的 ${occupied} 辆车已被同日未完成车次占用。` +
    '可到「发车计划」取消或完结旧车次释放车辆，或使用未占用的其他车辆手动建第二趟。'
  )
})

const loadNoGoFences = async () => {
  try {
    const list = await listDeliveryGeofencesApi()
    noGoFences.value = (list || []).filter((f) => f.fence_type === 'no_go' && f.is_active)
  } catch {
    noGoFences.value = []
  }
}

const loadDeliveryFleet = async () => {
  try {
    const rows = await listDeliveryVehiclesApi()
    deliveryVehicles.value = (rows || []).filter((v) => String(v.status || '') === 'active')
  } catch {
    deliveryVehicles.value = []
  }
}

const setVehicleDepartureOverride = (vehicleNo, val) => {
  const no = String(vehicleNo || '').trim()
  if (!no) return
  const g = departureTime.value || '06:00'
  const next = { ...vehicleDepartureOverrides.value }
  if (!val || String(val).trim() === g) delete next[no]
  else next[no] = String(val).trim()
  vehicleDepartureOverrides.value = next
  invalidateGeneratedPlan()
}

watch(planningDate, async () => {
  invalidateGeneratedPlan()
  selectedOrderIds.value = []
  manualOrderIds.value = []
  planWarnings.value = []
  await loadPool()
  await loadPlanningSummary()
})

watch(
  () => plan.value?.vehicle_routes,
  (routes) => {
    const list = routes || []
    const keys = new Set(list.map((r) => String(r.vehicle_no)))
    if (selectedVehicleKey.value !== 'all' && !keys.has(String(selectedVehicleKey.value))) {
      selectedVehicleKey.value = 'all'
    }
  },
  { deep: true },
)

watch(
  () => plan.value?.vehicle_limit_today?.date,
  () => {
    limitPlateFilter.value = ''
  },
)

/** 等待布局完成，避免懒加载 Tab 下容器宽高为 0 时初始化高德导致底图异常 */
const waitForMapContainerSize = async (el, maxMs = 3000) => {
  const t0 = performance.now()
  while (el && (el.offsetWidth < 4 || el.offsetHeight < 4)) {
    if (performance.now() - t0 > maxMs) break
    await new Promise((r) => requestAnimationFrame(r))
  }
}

/** GeoJSON 应为 [lng,lat]；若误存为国内常见的 [lat,lng]，用粗略范围纠正 */
const normalizeFenceLngLat = (a, b) => {
  const x = Number(a)
  const y = Number(b)
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null
  const asLngLat = x >= 70 && x <= 140 && y >= 15 && y <= 55
  const asLatLng = y >= 70 && y <= 140 && x >= 15 && x <= 55
  if (asLatLng && !asLngLat) return [y, x]
  return [x, y]
}

const resizeMapIfNeeded = () => {
  if (!amapIns.value || !chartRef.value) return
  const w = chartRef.value.offsetWidth
  const h = chartRef.value.offsetHeight
  if (w < 4 || h < 4) return
  try {
    amapIns.value.resize()
  } catch (_) {
    /* ignore */
  }
}

const scheduleMapResize = () => {
  if (mapResizeDebounceTimer) clearTimeout(mapResizeDebounceTimer)
  mapResizeDebounceTimer = setTimeout(() => {
    mapResizeDebounceTimer = null
    resizeMapIfNeeded()
  }, 80)
}

const bindMapResizeObserver = () => {
  if (mapResizeObserver || !chartRef.value) return
  mapResizeObserver = new ResizeObserver(() => {
    scheduleMapResize()
  })
  mapResizeObserver.observe(chartRef.value)
}

const initMap = async () => {
  const key = import.meta.env.VITE_AMAP_KEY
  if (!key || !chartRef.value) {
    ElMessage.warning('未配置高德 Key，无法加载地图底图')
    return
  }
  await waitForMapContainerSize(chartRef.value)
  await AMapLoader.load({ key, version: '2.0' })
  amapIns.value = new window.AMap.Map(chartRef.value, {
    zoom: 11,
    center: [116.397428, 39.90923],
    viewMode: '2D',
  })
  amapReady.value = true
  bindMapResizeObserver()
  await nextTick()
  resizeMapIfNeeded()
}

const stopAnimation = () => {
  if (animRaf.value != null) {
    cancelAnimationFrame(animRaf.value)
    animRaf.value = null
  }
  if (animMarker.value && amapIns.value) {
    if (typeof animMarker.value.stopMove === 'function') {
      try {
        animMarker.value.stopMove()
      } catch (_) {
        /* ignore */
      }
    }
    animMarker.value.setMap(null)
    animMarker.value = null
  }
  if (animInfo.value) {
    animInfo.value.close()
    animInfo.value = null
  }
  isPlaying.value = false
}

/** 沿折线顶点比例 t∈[0,1] 插值 */
const interpolatePath = (coords, t) => {
  if (!coords?.length) return null
  if (coords.length === 1) return coords[0]
  const n = coords.length - 1
  const f = Math.min(1, Math.max(0, t)) * n
  const i = Math.min(n - 1, Math.floor(f))
  const u = f - i
  const a = coords[i]
  const b = coords[i + 1]
  return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u]
}

/** 地图 HTML 片段转义（车牌等来自接口） */
const escapeHtmlForMap = (s) =>
  String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')

/** 归一化路径点并去掉连续重复点，减轻插值与主线程压力 */
const normalizeRouteAnimPath = (raw) => {
  const out = []
  if (!Array.isArray(raw)) return out
  for (const p of raw) {
    let lng
    let lat
    if (Array.isArray(p) && p.length >= 2) {
      lng = Number(p[0])
      lat = Number(p[1])
    } else if (p && typeof p === 'object' && Number.isFinite(p.lng) && Number.isFinite(p.lat)) {
      lng = Number(p.lng)
      lat = Number(p.lat)
    } else continue
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue
    const prev = out[out.length - 1]
    if (!prev || Math.abs(prev[0] - lng) > 1e-7 || Math.abs(prev[1] - lat) > 1e-7) out.push([lng, lat])
  }
  return out
}

const playActiveRoute = () => {
  const route = activeVehicleRoute.value
  if (!route || !amapIns.value) {
    ElMessage.info('请先选择一辆具体车辆')
    return
  }
  const rawPath = Array.isArray(route.route_path) ? route.route_path : []
  const playPath = normalizeRouteAnimPath(rawPath)
  if (playPath.length < 2) {
    ElMessage.warning('该车辆路线点过少或坐标无效，无法播放')
    return
  }
  stopAnimation()
  isPlaying.value = true
  const stops = route.stops || []
  const totalTravel = stops.reduce((s, x) => s + Number(x.travel_minutes || 0), 0) || 1

  const vn = route.vehicle_no || ''
  /** 不传 icon/content，使用高德 JSAPI 2.0 默认点标 */
  animMarker.value = new window.AMap.Marker({
    position: playPath[0],
    title: `模拟在途 · ${vn}`,
    zIndex: 400,
  })
  animMarker.value.setMap(amapIns.value)

  animInfo.value = new window.AMap.InfoWindow({
    isCustom: true,
    offset: new window.AMap.Pixel(0, -42),
  })

  /** 上限缩短：路径点很多时仍能在数十秒内跑完，便于肉眼确认「在动」 */
  const durationMs = Math.min(36000, Math.max(9000, 45 * playPath.length))
  const t0 = performance.now()

  const buildAnimPopHtml = (raw, tForLeg) => {
    let cum = 0
    let legIdx = 0
    for (let i = 0; i < stops.length; i++) {
      const leg = Number(stops[i].travel_minutes || 0) / totalTravel
      if (tForLeg <= cum + leg || i === stops.length - 1) {
        legIdx = i
        break
      }
      cum += leg
    }
    const st = stops[legIdx] || {}
    return `<div class="route-map-pop route-map-pop-anim">
        <div class="route-map-pop-hd">${route.vehicle_no || '车辆'} · 模拟 ${(Math.min(1, Math.max(0, raw)) * 100).toFixed(0)}%</div>
        <div class="route-map-pop-bd">
          <div class="route-map-pop-line"><span class="route-map-pop-k">停靠</span>本车第 <b>${st.sequence ?? '-'}</b> 站 / 全序 <b>${st.sequence_global ?? '-'}</b></div>
          <div class="route-map-pop-line">${st.client_name || ''}</div>
          <div class="route-map-pop-line"><span class="route-map-pop-k">订单</span>${st.order_no || '-'}</div>
          <div class="route-map-pop-line"><span class="route-map-pop-k">到达</span><b>${st.planned_arrive_datetime || '-'}</b></div>
          <div class="route-map-pop-line muted">本段 ${st.travel_minutes ?? '-'} 分 · 服务 ${st.service_minutes ?? '-'} 分</div>
        </div>
      </div>`
  }

  const openAnimInfoAtMarker = (raw, tForLeg) => {
    const pos = animMarker.value?.getPosition?.()
    if (!pos || !animInfo.value) return
    animInfo.value.setContent(buildAnimPopHtml(raw, tForLeg))
    animInfo.value.open(amapIns.value, pos)
  }

  const finishAnimAtEnd = () => {
    const end = playPath[playPath.length - 1]
    const last = stops[stops.length - 1]
    animInfo.value.setContent(
      `<div class="route-map-pop route-map-pop-anim"><div class="route-map-pop-hd">模拟完成</div><div class="route-map-pop-bd">${last?.order_no || ''}<br/>${last?.planned_arrive_datetime || ''}</div></div>`,
    )
    animInfo.value.open(amapIns.value, end)
    isPlaying.value = false
  }

  const startRouteAnimRafFallback = () => {
    let lastPop = 0
    const POP_MS = 140
    const tick = (nowMs) => {
      const raw = (nowMs - t0) / durationMs
      if (raw >= 1) {
        const end = playPath[playPath.length - 1]
        animMarker.value.setPosition(end)
        finishAnimAtEnd()
        animRaf.value = null
        return
      }
      /** 线性沿折线比例前进；easeInOut 在 raw 很小时几乎不动，易被误认为「卡住」 */
      const t = raw
      const pos = interpolatePath(playPath, t)
      animMarker.value.setPosition(pos)
      if (nowMs - lastPop >= POP_MS || raw >= 0.998) {
        lastPop = nowMs
        openAnimInfoAtMarker(raw, t)
      }
      animRaf.value = requestAnimationFrame(tick)
    }
    animRaf.value = requestAnimationFrame(tick)
  }

  /** 经实机验证：moveAlong 对自定义车标不可靠；用 RAF + setPosition 沿路径移动，不模拟车头转角。 */
  startRouteAnimRafFallback()
}

const limitTagType = (status) => {
  if (status === '限行') return 'danger'
  if (status === '不限行') return 'success'
  if (status === '纯电不限') return 'info'
  if (status === '外地限行') return 'warning'
  if (status === '用户禁用') return 'info'
  return 'info'
}

const renderRoute = async () => {
  await nextTick()
  stopAnimation()
  if (!amapReady.value || !amapIns.value) return
  const vehicleRoutes = Array.isArray(plan.value.vehicle_routes) ? plan.value.vehicle_routes : []
  const coords = Array.isArray(plan.value.route_path) ? plan.value.route_path : []
  amapIns.value.clearMap()
  amapOverlays.value = []
  for (const f of noGoFences.value || []) {
    if (f.geometry_json?.type === 'Polygon' && Array.isArray(f.geometry_json.coordinates?.[0])) {
      const ring = []
      for (const pair of f.geometry_json.coordinates[0]) {
        if (!Array.isArray(pair) || pair.length < 2) continue
        const ll = normalizeFenceLngLat(pair[0], pair[1])
        if (ll) ring.push(ll)
      }
      if (ring.length < 3) continue
      const poly = new window.AMap.Polygon({
        path: ring,
        strokeColor: '#b91c1c',
        strokeWeight: 2,
        fillColor: '#fecaca',
        fillOpacity: 0.22,
        zIndex: 30,
      })
      amapIns.value.add(poly)
      amapOverlays.value.push(poly)
    }
  }
  if (!coords.length && !vehicleRoutes.length) {
    if (!amapOverlays.value.length) return
    resizeMapIfNeeded()
    amapIns.value.setFitView(amapOverlays.value, false, [40, 40, 40, 40], 14)
    return
  }
  const palette = ['#2E8BFF', '#22C55E', '#F59E0B', '#EF4444', '#A855F7', '#06B6D4']
  const key = selectedVehicleKey.value

  if (vehicleRoutes.length) {
    vehicleRoutes.forEach((route, routeIdx) => {
      const routeCoords = Array.isArray(route.route_path) ? route.route_path : []
      if (!routeCoords.length) return
      const isFocus = key === 'all' || String(route.vehicle_no) === String(key)
      const polyline = new window.AMap.Polyline({
        path: routeCoords,
        strokeColor: palette[routeIdx % palette.length],
        strokeWeight: isFocus ? 7 : 4,
        strokeOpacity: isFocus ? 0.92 : 0.22,
        lineJoin: 'round',
        lineCap: 'round',
        zIndex: 80,
      })
      amapIns.value.add(polyline)
      amapOverlays.value.push(polyline)
      if (isFocus) {
        const dep = document.createElement('div')
        dep.className = 'route-depot-chip'
        dep.textContent = `${route.vehicle_no || '车'}·起点`
        const startMarker = new window.AMap.Marker({
          position: routeCoords[0],
          title: `${route.vehicle_no || '车辆'}线路起点`,
          content: dep,
          offset: new window.AMap.Pixel(-40, -28),
          zIndex: 110,
        })
        amapIns.value.add(startMarker)
        amapOverlays.value.push(startMarker)
      }
    })
  } else {
    const polyline = new window.AMap.Polyline({
      path: coords,
      strokeColor: '#2E8BFF',
      strokeWeight: 6,
      strokeOpacity: 0.9,
      lineJoin: 'round',
      lineCap: 'round',
      zIndex: 80,
    })
    amapIns.value.add(polyline)
    amapOverlays.value.push(polyline)
  }

  const esc = escapeHtmlForMap
  const stopsAll = plan.value.stops || []
  stopsAll.forEach((stop) => {
    if (key !== 'all' && String(stop.vehicle_no) !== String(key)) return
    const lng = Number(stop.lng)
    const lat = Number(stop.lat)
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return
    const gDisp = stop.sequence_global != null ? String(stop.sequence_global) : '—'
    const svDisp = stop.sequence != null ? String(stop.sequence) : '—'
    const wrap = document.createElement('div')
    wrap.className = 'route-stop-marker'
    wrap.innerHTML = `<div class="route-stop-marker-inner">
      <span class="route-stop-marker-g">${esc(gDisp)}</span>
      <span class="route-stop-marker-meta">${esc(String(stop.vehicle_no || ''))}<span class="route-stop-marker-dot">·</span>第${esc(svDisp)}站</span>
    </div>`
    const marker = new window.AMap.Marker({
      position: [lng, lat],
      title: `${stop.order_no || '订单'} · 全序${gDisp} · 本车第${svDisp}站`,
      content: wrap,
      offset: new window.AMap.Pixel(-36, -44),
      zIndex: 120,
    })
    marker.on('click', () => {
      const info = new window.AMap.InfoWindow({
        isCustom: true,
        offset: new window.AMap.Pixel(0, -36),
        content: `<div class="route-map-pop">
          <div class="route-map-pop-hd">${esc(String(stop.order_no || '-'))}</div>
          <div class="route-map-pop-bd">
            <div class="route-map-pop-line"><span class="route-map-pop-k">全序</span>${esc(String(stop.sequence_global ?? '-'))} · <span class="route-map-pop-k">本车</span>第 ${esc(String(stop.sequence ?? '-'))} 站</div>
            <div class="route-map-pop-line">${esc(String(stop.client_name || '-'))}</div>
            <div class="route-map-pop-line muted">${esc(String(stop.address || '-'))}</div>
            <div class="route-map-pop-line"><span class="route-map-pop-k">时窗</span>${esc(String(stop.client_delivery_window || stop.time_window || '-'))}</div>
            <div class="route-map-pop-line"><span class="route-map-pop-k">到达</span><b>${esc(String(stop.planned_arrive_datetime || stop.planned_arrive_time || '-'))}</b></div>
            <div class="route-map-pop-line"><span class="route-map-pop-k">离开</span><b>${esc(String(stop.planned_leave_datetime || stop.planned_leave_time || '-'))}</b></div>
            <div class="route-map-pop-line muted">本段 ${esc(String(stop.travel_minutes ?? '-'))} 分 · ${esc(String(stop.distance_from_prev_km ?? '-'))} km · 累计 ${esc(String(stop.cumulative_drive_minutes ?? '-'))} 分</div>
            <div class="route-map-pop-line"><span class="route-map-pop-k">车辆</span>${esc(String(stop.vehicle_no || '-'))} · ${stop.routing_source === 'amap' ? '高德' : '降级'}</div>
          </div>
        </div>`,
      })
      info.open(amapIns.value, [lng, lat])
    })
    amapIns.value.add(marker)
    amapOverlays.value.push(marker)
  })
  resizeMapIfNeeded()
  amapIns.value.setFitView(amapOverlays.value, false, [40, 40, 40, 40], 16)
}

watch(selectedVehicleKey, async () => {
  await renderRoute()
})

const selectAllOrders = () => {
  selectedOrderIds.value = (orderPool.value || []).map((i) => i.id)
}

const clearOrders = () => {
  selectedOrderIds.value = []
}

const openManualDispatch = () => {
  manualDepartureTime.value = departureTime.value || '06:00'
  manualVehicleId.value = deliveryVehicles.value[0]?.id ?? null
  const preselected = selectedOrdersForPlan.value.filter(canOrderSaveDispatch).map((row) => Number(row.id))
  manualOrderIds.value = preselected.length ? preselected : []
  manualDialogVisible.value = true
}

const moveManualOrder = (idx, dir) => {
  const nextIdx = idx + dir
  if (nextIdx < 0 || nextIdx >= manualOrderIds.value.length) return
  const arr = [...manualOrderIds.value]
  const current = arr[idx]
  arr[idx] = arr[nextIdx]
  arr[nextIdx] = current
  manualOrderIds.value = arr
}

const submitManualDispatch = async () => {
  const vehicle = (deliveryVehicles.value || []).find((v) => Number(v.id) === Number(manualVehicleId.value))
  if (!vehicle) {
    ElMessage.warning('请选择车辆')
    return
  }
  const orders = manualSelectedOrders.value
  if (!orders.length) {
    ElMessage.warning('请选择至少一个可保存的配货订单')
    return
  }
  manualSubmitting.value = true
  try {
    const stops = orders.map((order, idx) => ({
      order_id: Number(order.id),
      order_no: order.order_no,
      sequence: idx + 1,
      client_name: order.client_name || '',
      address: order.delivery_address || '',
      planned_arrive_time: '',
      planned_leave_time: '',
    }))
    const res = await commitRoutePlanApi({
      planning_date: toYmd(planningDate.value),
      source: 'manual',
      vehicle_routes: [
        {
          vehicle_id: Number(vehicle.id),
          vehicle_no: vehicle.vehicle_no,
          driver_name: vehicle.driver_name || '',
          stops,
          route_path: [],
        },
      ],
      risk_alerts: ['手动调度车次：未经过智能排线优化，请调度员自行确认站点顺序、时窗与车辆占用。'],
      planning_inputs_echo: {
        planning_date: toYmd(planningDate.value),
        departure_time_local: manualDepartureTime.value || departureTime.value || '06:00',
        manual_dispatch: true,
      },
      note: 'manual_dispatch',
    })
    const trips = Array.isArray(res?.trips) ? res.trips : []
    ElMessage.success(trips.length ? `已手动创建 ${trips.length} 个车次` : '已手动创建发车计划')
    if (Array.isArray(res?.warnings) && res.warnings.length) {
      ElMessage.warning(res.warnings.join(' '))
    }
    manualDialogVisible.value = false
    await loadPool()
    await loadPlanningSummary()
    router.push({ path: '/delivery/smart-routing', query: { tab: 'dispatch', date: toYmd(planningDate.value) } })
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '手动建车次失败'
    ElMessage.error(typeof msg === 'string' ? msg : '手动建车次失败')
  } finally {
    manualSubmitting.value = false
  }
}

const runPlan = async () => {
  const orderIds = [...selectedOrderIds.value]
  if (!orderIds.length) {
    ElMessage.warning('请至少选择一个订单')
    return
  }
  const did = currentDeliveryId.value
  if (!did) {
    ElMessage.warning('未获取到当前配送商账号，请重新登录后再试')
    return
  }
  loading.value = true
  try {
    const svcPayload = {}
    Object.entries(serviceByOrder.value).forEach(([k, v]) => {
      const n = Math.max(5, Math.min(240, Number(v) || 30))
      svcPayload[String(k)] = n
    })
    const departGlobal = departureTime.value || '06:00'
    const departByVehicle = {}
    for (const row of deliveryVehicles.value || []) {
      const vno = String(row.vehicle_no || '').trim()
      if (!vno) continue
      const t = vehicleDepartureOverrides.value[vno]
      if (t && String(t).trim() && String(t).trim() !== departGlobal) departByVehicle[vno] = String(t).trim()
    }
    const res = await routePlanApi({
      driver_id: did,
      order_ids: orderIds,
      planning_date: toYmd(planningDate.value),
      departure_time: departGlobal,
      departure_time_by_vehicle_no: Object.keys(departByVehicle).length ? departByVehicle : undefined,
      service_minutes_default: Math.max(5, Math.min(240, Number(serviceMinutesDefault.value) || 30)),
      service_minutes_by_order: Object.keys(svcPayload).length ? svcPayload : undefined,
      user_disabled_vehicle_nos: userDisabledVehicleNos.value.length ? [...userDisabledVehicleNos.value] : undefined,
      geofence_policy: geofencePolicy.value === 'strict' ? 'strict' : 'normal',
    })
    plan.value = res
    planWarnings.value = Array.isArray(res?.warnings) ? res.warnings : []
    if (planWarnings.value.length) {
      ElMessage.warning(planWarnings.value[0])
    }
    userDisabledVehicleNos.value = []
    selectedVehicleKey.value = 'all'
    limitPlateFilter.value = ''
    await renderRoute()
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '路线规划失败'
    ElMessage.error(typeof msg === 'string' ? msg : '路线规划失败')
  } finally {
    loading.value = false
  }
}

const goMonitorReport = () => {
  router.push('/monitor/route-planning')
}

const saveDispatchPlan = async () => {
  const routes = Array.isArray(plan.value?.vehicle_routes) ? plan.value.vehicle_routes : []
  if (!routes.length) {
    ElMessage.warning('请先生成智能路线')
    return
  }
  if (planDispatchSaveBlockers.value.length) {
    ElMessage.warning(planDispatchSaveBlockerText.value || '存在不能保存为发车计划的订单')
    return
  }
  const missingVehicleRoutes = routes.filter((r) => !String(r?.vehicle_no || '').trim())
  if (missingVehicleRoutes.length) {
    ElMessage.warning('当前路线存在未绑定车辆的车次，请先在车辆管理中维护车辆后重新生成路线')
    return
  }
  commitLoading.value = true
  try {
    const res = await commitRoutePlanApi({
      planning_date: toYmd(planningDate.value),
      source: 'smart_route',
      vehicle_routes: routes,
      risk_alerts: Array.isArray(plan.value?.risk_alerts) ? plan.value.risk_alerts : [],
      planning_inputs_echo: plan.value?.planning_inputs_echo || {},
    })
    const trips = Array.isArray(res?.trips) ? res.trips : []
    ElMessage.success(trips.length ? `已保存 ${trips.length} 个发车车次` : '已保存发车计划')
    if (Array.isArray(res?.warnings) && res.warnings.length) {
      ElMessage.warning(res.warnings.join(' '))
    }
    await loadPool()
    await loadPlanningSummary()
    try {
      await ElMessageBox.confirm(
        '发车计划已生成。是否现在进入发车计划处理装车、发车和异常发车？',
        '保存成功',
        {
          type: 'success',
          confirmButtonText: '查看发车计划',
          cancelButtonText: '继续看路线',
          customClass: 'dispatch-confirm-dialog',
          confirmButtonClass: 'dispatch-confirm-btn',
          cancelButtonClass: 'dispatch-cancel-btn',
        },
      )
      router.push({ path: '/delivery/smart-routing', query: { tab: 'dispatch', date: toYmd(planningDate.value) } })
    } catch (err) {
      if (err !== 'cancel' && err !== 'close') {
        console.warn('open dispatch plan cancelled', err)
      }
    }
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '保存发车计划失败'
    ElMessage.error(typeof msg === 'string' ? msg : '保存发车计划失败')
  } finally {
    commitLoading.value = false
  }
}

/** 是否有已生成的停靠数据（用于打印配送单） */
const hasPrintableStops = computed(() => (plan.value.stops || []).length > 0)

/** 按司机分组（司机未登记时按车牌单独成组，便于现场指派） */
const deliveryPrintSections = computed(() => {
  const list = [...(plan.value.stops || [])].filter((r) => r && (r.order_id != null || r.order_no))
  list.sort((a, b) => (Number(a.sequence_global) || 0) - (Number(b.sequence_global) || 0))
  const map = new Map()
  for (const row of list) {
    const driver = String(row.driver_name || '').trim()
    const vehicle = String(row.vehicle_no || '').trim()
    const groupKey = driver ? `d:${driver}` : `v:${vehicle || '?'}`
    if (!map.has(groupKey)) {
      map.set(groupKey, { groupKey, driverName: driver, vehicles: new Set(), rows: [] })
    }
    const g = map.get(groupKey)
    if (vehicle) g.vehicles.add(vehicle)
    g.rows.push(row)
  }
  return [...map.values()].map((g) => {
    const vehicles = [...g.vehicles].sort()
    const driverLabel = g.driverName || '（未登记司机）'
    const subtitle =
      vehicles.length > 1
        ? `涉及车辆：${vehicles.join('、')}（同一司机多车合并展示，请按「本车序」执行）`
        : `车辆：${vehicles[0] || '—'}`
    const rows = [...g.rows].sort((a, b) => (Number(a.sequence) || 0) - (Number(b.sequence) || 0))
    return { ...g, vehicles, driverLabel, subtitle, rows }
  })
})

const printDeliveryMeta = computed(() => {
  const e = plan.value?.planning_inputs_echo
  return {
    org: plan.value?.driver || '—',
    date: e?.planning_date || '',
    depart: e?.departure_time_local || '',
    totalKm: plan.value?.total_distance || '—',
    estMin: plan.value?.estimated_time || '—',
  }
})

const printDeliverySlips = () => {
  if (!hasPrintableStops.value) {
    ElMessage.warning('请先生成智能路线后再打印配送单')
    return
  }
  if (!deliveryPrintSections.value.length) {
    ElMessage.warning('当前没有可打印的停靠任务')
    return
  }
  window.print()
}

/** 打印用收货地址：去掉历史演示里的「（明日N）」并改为司机可读说明 */
const formatPrintAddress = (row) => {
  let addr = String(row?.address || '').trim()
  if (!addr) return '—'
  const win = String(row?.client_delivery_window || row?.time_window || '').trim()
  const m = addr.match(/（明日\d+）\s*$/)
  if (m) {
    addr = addr.slice(0, addr.length - m[0].length).trim()
    if (win) {
      return `${addr}（配送约定：${win}）`
    }
    return `${addr}（配送日及时段以右侧「客户约定送达」为准）`
  }
  return addr
}

const onTimeRateText = computed(() => {
  const rate = Number(plan.value?.optimization_compare?.estimated_on_time_rate || 0)
  if (!rate) return '-'
  return `${(rate * 100).toFixed(1)}%`
})

/** 准点率示意指标说明（一期/二期口径，与后端 optimization_compare.estimated_on_time_rate_note 一致） */
const onTimeRateNote = computed(
  () =>
    plan.value?.optimization_compare?.estimated_on_time_rate_note ||
    '【一期】规划期示意值：由坐标覆盖率等规则合成，非基于历史送达的预测模型，便于汇报演示占位。【二期】接入签收与实际到达时间，按客户约定窗统计真实准点率，或再建设准点概率预测模型。',
)

/** 左侧禁行策略与当前已生成 plan 是否不一致（须重新点「生成智能路线」地图才会对齐） */
const geofencePolicyStale = computed(() => {
  if (!(plan.value?.stops || []).length) return false
  const ui = geofencePolicy.value === 'strict' ? 'strict' : 'normal'
  const echo = plan.value?.planning_inputs_echo?.geofence_policy
  if (echo == null || echo === undefined) return ui === 'strict'
  return echo !== ui
})

/** 本次结果实际采用的禁行策略（来自后端回显） */
const appliedGeofencePolicyLabel = computed(() => {
  const echo = plan.value?.planning_inputs_echo?.geofence_policy
  if (echo === 'strict') return '严格'
  if (echo === 'normal') return '正常'
  return null
})

/** 规划总览：发车列表默认一行，悬浮「全部发车」看完整 */
const echoDepartureMeta = computed(() => {
  const e = plan.value?.planning_inputs_echo
  if (!e) return null
  const eff = e.departure_time_by_vehicle_no_effective || {}
  const pairs = Object.keys(eff).length
    ? Object.entries(eff).map(([k, t]) => `${k} ${t}`)
    : [`默认 ${e.departure_time_local || '06:00'}`]
  const head = `计划日期 ${e.planning_date}（北京）`
  const foot = '下方「计划到达/离开」均为北京时间，与高德路段累计一致。'
  const preview =
    pairs.length === 1 ? `${head} · ${pairs[0]}` : `${head} · ${pairs[0]} 等 ${pairs.length} 条发车`
  const fullLines = [`各车计划发车：`, ...pairs.map((p) => `· ${p}`), '', foot]
  return { preview, fullLines: fullLines.join('\n'), showMore: pairs.length > 1 }
})

/** 表头说明（悬停问号） */
const clientWindowHeaderTip =
  '客户在下单页选择的「配送日期」与「配送时段」：须为整点起止且恰好 1 小时（如 06:00-07:00）。算法用时段结束时刻作为到站截止；应与左侧「计划日期」对齐，否则会误判延误。'

const overtimeHeaderTip =
  '「超窗」= 计划到达晚于上述时段截止时刻的分钟数。红色数字越大延误越久；「—」表示未超窗。\n若计划发车日在订单配送日之后（例如订单要求 5 日送达却选 6 日发车），分钟数会很大，请先对齐日期。'

const overtimeCellTooltip = (row) => {
  const m = Number(row?.window_violation_minutes)
  const deadline = row?.window_deadline_sh ? String(row.window_deadline_sh) : '客户约定时段截止时刻'
  if (!(m > 0)) {
    return '未超窗：当前 ETA 未晚于约定截止时刻（截止时刻见「客户约定送达」列）。'
  }
  const h = (m / 60).toFixed(1)
  return `计划到达比约定截止（${deadline}）晚了约 ${m} 分钟（约 ${h} 小时）。建议核对计划日期与订单配送日是否一致，或提前发车、增加车辆。`
}

const vehicleStatsLine = computed(() => {
  const used = Number(plan.value?.vehicles_used_in_plan ?? 0)
  const eligible = Number(plan.value?.vehicles_available_today ?? 0)
  const active = Number(plan.value?.vehicles_active_total ?? eligible)
  const excluded = Array.isArray(plan.value?.vehicles_excluded_from_planning)
    ? plan.value.vehicles_excluded_from_planning.length
    : 0
  if (!used && !eligible && !active) return ''
  let s = `本方案实际出车 ${used} 辆。所选计划日可参与智能排线的车辆 ${eligible} 辆（运营中且发车在限行窗口内时已剔除尾号限行与外地牌默认限行）。`
  if (active > 0) {
    s += ` 车队运营中登记共 ${active} 辆。`
  }
  if (excluded > 0) {
    s += ` 另有 ${excluded} 辆未纳入本次排线。`
  }
  return s
})

onMounted(async () => {
  const qDate = route.query.date || route.query.planning_date
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(qDate || ''))) {
    planningDate.value = String(qDate)
  }
  if (!userStore.userInfo) {
    try {
      await userStore.fetchMe()
    } catch {
      // ignore
    }
  }
  await nextTick()
  await initMap()
  await loadNoGoFences()
  await loadDeliveryFleet()
  await loadPool()
  await loadPlanningSummary()
  await renderRoute()
})

onUnmounted(() => {
  stopAnimation()
  if (compareAnimRaf) cancelAnimationFrame(compareAnimRaf)
  if (mapResizeDebounceTimer) {
    clearTimeout(mapResizeDebounceTimer)
    mapResizeDebounceTimer = null
  }
  if (mapResizeObserver) {
    try {
      mapResizeObserver.disconnect()
    } catch (_) {
      /* ignore */
    }
    mapResizeObserver = null
  }
  if (amapIns.value) {
    amapIns.value.destroy()
    amapIns.value = null
  }
})
</script>

<template>
  <el-row :gutter="12" class="route-plan-row">
    <el-col :span="8">
      <el-alert
        :closable="false"
        type="info"
        class="mb-3 route-plan-occupancy-alert"
        title="占用与释放规则"
      >
        <template #default>
          <ul class="occupancy-help-list">
            <li>占用按<strong>计划日期</strong>隔离：排明天不受今天旧车次影响；同一计划日同一车辆/订单不可重复排线。</li>
            <li>释放条件：车次<strong>全部站点送达</strong>（已完成）或调度<strong>取消车次</strong>；无需等客户确认收货，也不跟踪车辆回场。</li>
            <li>临时加单：订单池内为未排入车次订单；有空车可手动建第二趟，或在发车计划中对未发车车次「追加站点」。</li>
          </ul>
        </template>
      </el-alert>
      <el-alert
        :closable="false"
        type="success"
        class="mb-3 route-plan-top-alert"
        title="智能路线引擎：按高德驾车路径计算路段距离与 ETA；默认发车时间可按车覆盖，与服务时长一并参与到达/离开推算。分配车辆时优先满足客户「配送日期 + 时段」截止时刻（仍超窗时会提示风险）。"
      />
      <el-card>
        <template #header>智能规划参数</template>
        <el-form label-width="100px">
          <el-form-item label="计划日期">
            <el-date-picker v-model="planningDate" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" class="w-full" />
          </el-form-item>
          <el-alert
            v-if="noVehicleGuidanceText"
            type="warning"
            :closable="false"
            show-icon
            class="mb-2"
            :title="noVehicleGuidanceText"
          />
          <el-alert
            v-if="unplannedOrderCount > 0"
            type="info"
            :closable="false"
            show-icon
            class="mb-2"
          >
            <template #title>
              计划日 {{ planningDate }} 尚有 {{ unplannedOrderCount }} 单未排入车次
              <span v-if="newUnplannedOrders.length">（其中 {{ newUnplannedOrders.length }} 单为保存计划后新增）</span>
            </template>
          </el-alert>
          <el-form-item label="默认发车">
            <el-time-select
              v-model="departureTime"
              start="04:00"
              step="00:15"
              end="23:45"
              placeholder="选择时间"
              class="w-full"
            />
            <span class="inline-hint">未单独设置的车辆用此时间（北京时间）</span>
          </el-form-item>
          <el-form-item>
            <template #label>
              <span class="inline-flex items-center gap-1">
                禁行围栏
                <el-tooltip
                  placement="top"
                  effect="dark"
                  content="正常：避让失败时自动改为无避让路径（与现网一致）。严格：禁止无避让重试；收货点在围栏内时该围栏本段可穿行；否则任一路段失败则整单报错。另：高德避让与后端多边形抽稀（每区最多 16 顶点）属尽力而为，轨迹可能与地图上完整红线略有偏差。"
                >
                  <el-icon class="cursor-help text-slate-400"><QuestionFilled /></el-icon>
                </el-tooltip>
              </span>
            </template>
            <el-radio-group v-model="geofencePolicy" size="small">
              <el-radio-button label="normal">正常</el-radio-button>
              <el-radio-button label="strict">严格</el-radio-button>
            </el-radio-group>
            <el-alert
              v-if="geofencePolicyStale"
              type="warning"
              :closable="false"
              show-icon
              class="mt-2 max-w-full"
            >
              当前路线与地图仍是<strong>上次生成</strong>的结果；切换「禁行围栏」后必须再点「生成智能路线」才会按新模式重算。
              <template v-if="appliedGeofencePolicyLabel">
                本次已展示的数据实际为「<strong>{{ appliedGeofencePolicyLabel }}</strong>」模式。
              </template>
            </el-alert>
          </el-form-item>
          <el-form-item v-if="deliveryVehicles.length" label="按车发车">
            <div class="quick-select-row">
              <el-button link type="primary" @click="showVehicleDepartureTable = !showVehicleDepartureTable">
                {{ showVehicleDepartureTable ? '收起' : '展开' }}按车发车时间
              </el-button>
            </div>
            <el-table v-if="showVehicleDepartureTable" :data="deliveryVehicles" size="small" border max-height="220" class="mt-2">
              <el-table-column prop="vehicle_no" label="车牌" width="120" />
              <el-table-column label="发车(北京)" min-width="140">
                <template #default="{ row }">
                  <el-time-select
                    :model-value="vehicleDepartureOverrides[row.vehicle_no] ?? departureTime"
                    start="04:00"
                    step="00:15"
                    end="23:45"
                    placeholder="同默认"
                    class="w-full"
                    @update:model-value="(v) => setVehicleDepartureOverride(row.vehicle_no, v)"
                  />
                </template>
              </el-table-column>
            </el-table>
            <p v-if="showVehicleDepartureTable" class="field-tip">
              与默认相同时不提交覆盖；生成路线时参与尾号限行窗口判断，并按各车发车时刻累加行驶与到站。
            </p>
          </el-form-item>
          <el-form-item label="默认服务">
            <el-input-number v-model="serviceMinutesDefault" :min="5" :max="240" class="w-full" />
            <span class="inline-hint">分钟/站（未单独设置的订单用此值）</span>
          </el-form-item>
          <el-form-item label="订单选择">
            <el-select
              v-model="selectedOrderIds"
              multiple
              collapse-tags
              collapse-tags-tooltip
              :max-collapse-tags="4"
              class="w-full"
              filterable
            >
              <el-option
                v-for="row in orderPool"
                :key="row.id"
                :label="`${row.order_no} · ${orderDispatchLabel(row)}`"
                :value="row.id"
              >
                <div class="order-option-row">
                  <span>{{ row.order_no }}</span>
                  <span class="order-option-tags">
                    <el-tag v-if="row.is_new_unplanned" size="small" type="danger" effect="plain">新单</el-tag>
                    <el-tag size="small" type="info" effect="plain">未排入车次</el-tag>
                    <el-tag size="small" :type="orderDispatchTagType(row)" effect="plain">{{ orderDispatchLabel(row) }}</el-tag>
                  </span>
                </div>
              </el-option>
            </el-select>
            <div class="quick-select-row">
              <el-button link type="primary" @click="selectAllOrders">全选</el-button>
              <el-button link @click="clearOrders">清空</el-button>
              <el-button link type="primary" @click="showServiceTable = !showServiceTable">
                {{ showServiceTable ? '收起' : '展开' }}按单服务时长
              </el-button>
              <span class="quick-select-text">已选 {{ selectedOrderIds.length }} / {{ orderPool.length }}</span>
            </div>
            <p class="field-tip">
              仅展示归属当前配送商、主单为「待履约」或「配货中」、且<strong>客户配送日</strong>等于左侧「计划日期」的订单（配货中表示已完成智能分单，仍可纳入排线）。计划日期与发车时间为<strong>北京时间</strong>。
              若改计划日期，列表会切换为对应配送日的订单；选单后请再点「生成智能路线」。
            </p>
            <el-alert
              v-if="dispatchSaveBlockerText"
              type="info"
              :closable="false"
              show-icon
              class="mt-2"
              :title="dispatchSaveBlockerText"
            />
          </el-form-item>
          <el-form-item v-if="showServiceTable && selectedOrderIds.length" label="按单服务">
            <el-table :data="orderPool.filter((r) => selectedOrderIds.includes(r.id))" size="small" border max-height="220">
              <el-table-column prop="order_no" label="订单号" min-width="120" />
              <el-table-column label="调度状态" width="130">
                <template #default="{ row }">
                  <el-tag size="small" :type="orderDispatchTagType(row)" effect="plain">{{ orderDispatchLabel(row) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="服务(分钟)" width="120">
                <template #default="{ row }">
                  <el-input-number v-model="serviceByOrder[row.id]" :min="5" :max="240" size="small" />
                </template>
              </el-table-column>
            </el-table>
          </el-form-item>
          <div class="action-row">
            <div class="action-row__btns">
              <el-button type="primary" :loading="loading" @click="runPlan">生成智能路线</el-button>
              <el-button type="success" plain :loading="commitLoading" :disabled="!canSaveGeneratedPlan" @click="saveDispatchPlan">
                保存为发车计划
              </el-button>
              <el-button plain @click="openManualDispatch">手动建车次</el-button>
              <el-button plain @click="goMonitorReport">打开监管路线汇报</el-button>
              <el-button plain :disabled="!hasPrintableStops" @click="printDeliverySlips">打印配送单</el-button>
            </div>
            <el-popover placement="top-end" :width="440" trigger="click" popper-class="route-plan-phase2-popper">
              <template #reference>
                <button type="button" class="phase2-kb-btn" title="能力边界与二期方向（内部备忘）" aria-label="能力边界与二期方向">
                  <el-icon class="phase2-kb-ico"><QuestionFilled /></el-icon>
                </button>
              </template>
              <div class="phase2-kb">
                <p class="phase2-kb-title">智能排线 · 一期边界与二期储备</p>
                <p class="phase2-kb-section">【一期 · 当前实现】</p>
                <ul class="phase2-kb-list">
                  <li>排线以订单坐标、时窗、车辆载重容积、禁行策略等规则 + 高德驾车路径为主；未使用历史单训练专属路径模型。</li>
                  <li>路段 ETA 来自高德 A→B 驾车接口返回的时长；请求时刻<strong>未传</strong>「每段计划出发时间」，路况更接近<strong>规划请求当时</strong>的快照。</li>
                  <li>「准点率示意（一期）」为规则合成占位，非历史送达预测模型；真实准点需二期接签收/到达数据与口径。</li>
                  <li>禁行「严格」模式禁止无避让降级，但高德避让 + 多边形抽稀仍为尽力而为，与地图红线非逐米一致。</li>
                </ul>
                <p class="phase2-kb-section">【二期 · 可升级方向】</p>
                <ul class="phase2-kb-list">
                  <li><strong>实时 ETA</strong>：车辆上报位置后，定时/事件触发用「当前位置→下一站」重算驾车时长，限流与配额需设计。</li>
                  <li><strong>分时刻规划</strong>：评估高德企业能力（如按出发时间/未来路况的接口），使每 leg 与计划发车链对齐。</li>
                  <li><strong>准点闭环</strong>：沉淀计划 vs 实际到达，统计真实准点率或建设概率预测。</li>
                  <li><strong>可选增强</strong>：历史路段耗时系数、拥堵补偿、与监管大屏 WebSocket 联动展示。</li>
                </ul>
                <p class="phase2-kb-foot">仅供对内汇报与需求备忘；产品对外口径以合同与交付说明为准。</p>
              </div>
            </el-popover>
          </div>
        </el-form>
      </el-card>

      <el-card class="mt-3 overview-card">
        <template #header>规划总览</template>
        <p>调度主体：{{ plan.driver || '-' }}</p>
        <p v-if="plan.planning_inputs_echo?.geofence_policy" class="text-slate-600 text-sm">
          禁行围栏：<strong>{{ plan.planning_inputs_echo.geofence_policy === 'strict' ? '严格' : '正常' }}</strong>
        </p>
        <div v-if="vehicleStatsLine" class="vehicle-stats-block">
          <p class="vehicle-stats-main">{{ vehicleStatsLine }}</p>
          <p class="vehicle-stats-sub text-xs text-slate-500">
            占用仅看<strong>同一计划日</strong>的未完成车次；车次全部送达或取消后释放，不等客户确认收货。
            发车在北京时间当日 20:00 及以前时：尾号限行、外地牌（默认限行）车辆不参与排线；晚于 20:00 发车则不因此而剔除。
            您在下方手动「停用排线」的车辆亦<strong>绝不进入</strong>当次「生成智能路线」的后端计算（仅本次请求有效，不保存）。
          </p>
        </div>
        <el-alert
          v-for="(w, wi) in planWarnings"
          :key="`pw-${wi}`"
          class="mt-2"
          type="warning"
          :closable="false"
          :title="w"
        />
        <p v-if="!vehicleStatsLine" class="text-slate-500">生成路线后将显示本方案出车数与车队可用车辆数。</p>
        <p>总距离：{{ plan.total_distance || '-' }}</p>
        <p>预计时长：{{ plan.estimated_time || '-' }}</p>
        <div class="on-time-rate-block">
          <p class="flex items-center gap-1 flex-wrap">
            <span>准点率示意（一期）：<strong>{{ onTimeRateText }}</strong></span>
            <el-tooltip placement="top" effect="dark" :content="onTimeRateNote" :max-width="420">
              <el-icon class="cursor-help text-slate-400"><QuestionFilled /></el-icon>
            </el-tooltip>
          </p>
          <p class="text-xs text-slate-500 mt-1 leading-relaxed">{{ onTimeRateNote }}</p>
        </div>
        <div v-if="echoDepartureMeta" class="echo-compact">
          <div class="echo-compact__row">
            <el-tooltip v-if="!echoDepartureMeta.showMore" placement="top-start" :show-after="220" :max-width="400">
              <template #content>
                <pre class="echo-tip-pre">{{ echoDepartureMeta.fullLines }}</pre>
              </template>
              <span class="echo-compact__main">{{ echoDepartureMeta.preview }}</span>
            </el-tooltip>
            <template v-else>
              <span class="echo-compact__main">{{ echoDepartureMeta.preview }}</span>
              <el-popover placement="top-start" :width="400" trigger="hover" :show-after="180" popper-class="route-echo-popper">
                <template #reference>
                  <button type="button" class="echo-more-link">全部发车</button>
                </template>
                <pre class="echo-popover-pre">{{ echoDepartureMeta.fullLines }}</pre>
              </el-popover>
            </template>
          </div>
        </div>
        <el-alert v-if="routingHint" class="mt-2" type="info" :closable="false" :title="routingHint" />

        <div v-if="plan.vehicle_limit_today" class="limit-block">
          <div class="limit-title">{{ plan.vehicle_limit_today.date || '—' }} 限行与车辆</div>
          <p class="limit-desc">{{ limitSummaryText }}</p>
          <p class="limit-hint">
            右侧开关为「参与 / 停用排线」：勾选<strong>停用</strong>后，仅在下一次点击「生成智能路线」时传参排除，不写入浏览器。生成成功后开关会复位；若该车因限行等原因<strong>本次结果已未纳入排线</strong>，车牌同样会以灰色删除线显示，并带「未参与本次排线」标签，避免误以为仍在计算中。
          </p>
          <div v-if="limitVehicleRows.length" class="limit-select-row">
            <span class="limit-select-label">筛选车牌</span>
            <el-select
              v-model="limitPlateFilter"
              clearable
              filterable
              placeholder="全部显示"
              size="small"
              class="limit-plate-select"
            >
              <el-option
                v-for="v in limitVehicleRows"
                :key="v.vehicle_no"
                :label="v.vehicle_no"
                :value="String(v.vehicle_no)"
              />
            </el-select>
          </div>
          <div class="limit-chips limit-chips-scroll">
            <div
              v-for="v in limitChipsFiltered"
              :key="v.vehicle_no"
              class="limit-chip"
              :class="{ 'limit-chip--disabled': isLimitChipDimmed(v) }"
            >
              <span class="plate">{{ v.vehicle_no }}</span>
              <template v-if="isPendingUserDisable(v)">
                <el-tag type="info" size="small">停用排线</el-tag>
              </template>
              <template v-else-if="isExcludedFromThisPlan(v)">
                <el-tag type="warning" size="small" effect="plain">未参与本次排线</el-tag>
                <el-tag size="small" :type="limitTagType(v.limit_status)">{{
                  limitStatusDisplay(v.limit_status)
                }}</el-tag>
              </template>
              <el-tag v-else size="small" :type="limitTagType(v.limit_status)">{{
                limitStatusDisplay(v.limit_status)
              }}</el-tag>
              <el-switch
                class="limit-chip-switch"
                :model-value="isPendingUserDisable(v)"
                size="small"
                inline-prompt
                active-text="停用"
                inactive-text="参与"
                @change="(on) => setVehicleUserDisabled(v.vehicle_no, Boolean(on))"
              />
              <el-tooltip :content="limitChipTooltip(v)" placement="top">
                <span class="limit-reason-hint">?</span>
              </el-tooltip>
            </div>
          </div>
        </div>
      </el-card>

      <el-card v-if="(plan.stops || []).length" class="mt-3 compare-card">
        <template #header>
          <div class="compare-card-hd">
            <span class="compare-card-title">相对粗放对标的演示收益</span>
            <div class="compare-card-hd-actions">
              <el-button type="primary" link @click="openBriefDialog">
                <el-icon class="btn-ico"><FullScreen /></el-icon>
                计算简报
              </el-button>
              <el-tag size="small" effect="plain" type="info">本方案为真实累计</el-tag>
            </div>
          </div>
        </template>
        <div class="compare-body">
          <div class="compare-metric compare-metric--highlight">
            <span class="compare-metric-k">节省里程</span>
            <span class="compare-metric-v">{{ animSavedKm.toFixed(2) }} <small>km</small></span>
          </div>
          <div class="compare-metric compare-metric--highlight">
            <span class="compare-metric-k">节省总时长</span>
            <span class="compare-metric-v">{{ animSavedMin }} <small>分钟</small></span>
            <span class="compare-metric-hint">行驶 + 到站服务累计</span>
          </div>
          <div class="compare-bars">
            <div class="compare-bar-block">
              <div class="compare-bar-title">
                <Odometer class="compare-bar-ico" />
                里程 (km)
              </div>
              <div class="compare-bar-row">
                <span class="compare-bar-label">粗放对标</span>
                <div class="compare-bar-track">
                  <div class="compare-bar-fill compare-bar-fill--baseline" style="width: 100%" />
                </div>
                <span class="compare-bar-num">{{ animBaselineKm.toFixed(2) }}</span>
              </div>
              <div class="compare-bar-row">
                <span class="compare-bar-label">本方案</span>
                <div class="compare-bar-track">
                  <div class="compare-bar-fill compare-bar-fill--opt" :style="{ width: `${kmOptimizedBarPct}%` }" />
                </div>
                <span class="compare-bar-num">{{ animOptimizedKm.toFixed(2) }}</span>
              </div>
            </div>
            <div class="compare-bar-block">
              <div class="compare-bar-title">
                <Timer class="compare-bar-ico" />
                总时长 (分钟)
              </div>
              <div class="compare-bar-row">
                <span class="compare-bar-label">粗放对标</span>
                <div class="compare-bar-track">
                  <div class="compare-bar-fill compare-bar-fill--baseline" style="width: 100%" />
                </div>
                <span class="compare-bar-num">{{ animBaselineMin }}</span>
              </div>
              <div class="compare-bar-row">
                <span class="compare-bar-label">本方案</span>
                <div class="compare-bar-track">
                  <div class="compare-bar-fill compare-bar-fill--opt" :style="{ width: `${minOptimizedBarPct}%` }" />
                </div>
                <span class="compare-bar-num">{{ animOptimizedMin }}</span>
              </div>
            </div>
          </div>
          <el-collapse v-model="compareCollapseActive" class="compare-collapse">
            <el-collapse-item name="method">
              <template #title>
                <span class="compare-collapse-title">
                  <Cpu class="compare-collapse-ico" />
                  计算口径与方法说明
                </span>
              </template>
              <p class="compare-method-p">
                {{
                  optCompare.baseline_description ||
                  '「对标里程/时长」并非第二套真实路径回放：在「本方案」路段累计之上按行业粗放冗余系数估算，用于演示量级；节省量 = 对标值 − 本方案累计。'
                }}
              </p>
              <p class="compare-method-meta">
                模型标识：<code>{{ optCompare.baseline_model || 'synthetic_uplift' }}</code>
                · 里程冗余系数 {{ (Number(optCompare.baseline_distance_uplift_ratio ?? 0.12) * 100).toFixed(0) }}% · 时长冗余系数
                {{ (Number(optCompare.baseline_duration_uplift_ratio ?? 0.14) * 100).toFixed(0) }}%
              </p>
            </el-collapse-item>
          </el-collapse>
        </div>
      </el-card>

      <el-card class="mt-3">
        <template #header>算法解释</template>
        <el-alert
          type="info"
          :closable="false"
          title="停靠顺序按客户约定送达截止时刻优先、再按车辆增量成本分配；路段耗时优先高德驾车；到达=发车+累计行驶，离开=到达+服务时长。"
        />
        <div class="capability-badge-row">
          <el-tooltip v-for="item in plan.capability_badges || []" :key="item" :content="badgeTip(item)" placement="top" :show-after="300">
            <el-tag size="small" effect="plain" type="primary" class="capability-badge">{{ item }}</el-tag>
          </el-tooltip>
        </div>
        <div class="mt-2 text-xs text-slate-500">
          坐标模式：{{ plan.data_quality?.mode || '-' }}，坐标覆盖率：{{ Number(plan.data_quality?.geo_coverage || 0) * 100 }}%
        </div>
      </el-card>
    </el-col>

    <el-col :span="16" class="route-plan-main-col">
      <el-card>
        <template #header>
          <div class="map-header">
            <span>路线可视化</span>
            <div class="map-toolbar map-toolbar-row">
              <el-select
                v-model="selectedVehicleKey"
                filterable
                placeholder="选择要查看的车辆"
                size="small"
                class="vehicle-route-select"
              >
                <el-option label="全部车辆" value="all" />
                <el-option
                  v-for="vr in plan.vehicle_routes || []"
                  :key="vr.vehicle_no"
                  :label="vr.vehicle_no"
                  :value="String(vr.vehicle_no)"
                />
              </el-select>
              <div class="map-actions-inline">
                <el-button size="small" type="primary" plain :disabled="selectedVehicleKey === 'all' || isPlaying" @click="playActiveRoute">
                  播放轨迹
                </el-button>
                <el-button size="small" :disabled="!isPlaying" @click="stopAnimation">停止</el-button>
              </div>
            </div>
          </div>
        </template>
        <div ref="chartRef" class="h-[360px] map-panel" />
        <div v-if="(plan.stops || []).length" class="engine-credibility-strip">
          <div class="ecs-cell">
            <el-icon class="ecs-ico ecs-ico--ok"><Histogram /></el-icon>
            <div class="ecs-text">
              <div class="ecs-title">{{ routingModeLabel }}</div>
              <div class="ecs-sub">
                高德路段 {{ plan.data_quality?.amap_legs_ok ?? 0 }}/{{ plan.data_quality?.amap_legs_total ?? 0 }}
              </div>
            </div>
          </div>
          <div class="ecs-cell">
            <el-icon class="ecs-ico"><MapLocation /></el-icon>
            <div class="ecs-text">
              <div class="ecs-title">坐标覆盖 {{ (Number(plan.data_quality?.geo_coverage || 0) * 100).toFixed(1) }}%</div>
              <div class="ecs-sub">{{ plan.data_quality?.mode === 'real_geo' ? '全量真实坐标' : '含估算坐标' }}</div>
            </div>
          </div>
          <div class="ecs-cell">
            <el-icon class="ecs-ico"><Van /></el-icon>
            <div class="ecs-text">
              <div class="ecs-title">
                本方案 {{ plan.vehicles_used_in_plan ?? 0 }} 车 · {{ (plan.stops || []).length }} 停靠
              </div>
              <div class="ecs-sub">
                <el-tooltip placement="top" effect="dark" :content="onTimeRateNote" :max-width="420">
                  <span class="cursor-help underline decoration-dotted decoration-slate-400 underline-offset-2">准点率示意（一期）</span>
                </el-tooltip>
                {{ ((Number(optCompare.estimated_on_time_rate || 0)) * 100).toFixed(1) }}%
              </div>
            </div>
          </div>
        </div>
      </el-card>

      <el-card class="mt-3 stops-card">
        <template #header>
          <div class="stops-card-header">
            <span>停靠序列与约束命中（含 ETA）</span>
            <span class="stops-card-sub">主表保留关键列，展开查看路段与约束</span>
          </div>
        </template>
        <div class="stops-toolbar">
          <el-input
            v-model="stopsTableKeyword"
            clearable
            size="small"
            placeholder="筛选订单号、客户、车牌或约定窗…"
            class="stops-search"
          />
          <span class="stops-count">共 <strong>{{ filteredStops.length }}</strong> 条</span>
        </div>
        <div class="route-stops-table-scroll">
          <el-table
            :data="filteredStops"
            class="stops-elegant-table"
            border
            stripe
            size="small"
            :row-key="(row) => `${row.order_id ?? ''}-${row.vehicle_no ?? ''}-${row.sequence_global ?? row.sequence ?? ''}`"
          >
          <el-table-column type="expand" width="44">
            <template #default="{ row }">
              <div class="stop-expand">
                <div class="stop-expand-grid">
                  <div class="stop-expand-item">
                    <span class="stop-expand-k">计划离开</span>
                    <span class="stop-expand-v">{{ row.planned_leave_datetime || row.planned_leave_time || '—' }}</span>
                  </div>
                  <div class="stop-expand-item">
                    <span class="stop-expand-k">本段行驶</span>
                    <span class="stop-expand-v">{{ row.travel_minutes != null ? `${row.travel_minutes} 分` : '—' }}</span>
                  </div>
                  <div class="stop-expand-item">
                    <span class="stop-expand-k">服务时长</span>
                    <span class="stop-expand-v">{{ row.service_minutes != null ? `${row.service_minutes} 分` : '—' }}</span>
                  </div>
                  <div class="stop-expand-item">
                    <span class="stop-expand-k">累计行驶</span>
                    <span class="stop-expand-v">{{ row.cumulative_drive_minutes != null ? `${row.cumulative_drive_minutes} 分` : '—' }}</span>
                  </div>
                  <div class="stop-expand-item">
                    <span class="stop-expand-k">前序路段</span>
                    <span class="stop-expand-v">{{ row.distance_from_prev_km != null ? `${row.distance_from_prev_km} km` : '—' }}</span>
                  </div>
                  <div class="stop-expand-item">
                    <span class="stop-expand-k">路段来源</span>
                    <span class="stop-expand-v">
                      <el-tag size="small" :type="row.routing_source === 'amap' ? 'success' : 'info'">
                        {{ row.routing_source === 'amap' ? '高德驾车' : '降级估算' }}
                      </el-tag>
                    </span>
                  </div>
                  <div class="stop-expand-item">
                    <span class="stop-expand-k">货重 / 体积</span>
                    <span class="stop-expand-v">
                      {{ row.load_weight_kg != null ? `${row.load_weight_kg} kg` : '—' }}
                      <span class="stop-expand-sep">·</span>
                      {{ row.load_volume_m3 != null ? `${row.load_volume_m3} m³` : '—' }}
                    </span>
                  </div>
                </div>
                <div v-if="(row.constraints_hit || []).length" class="stop-expand-constraints">
                  <span class="stop-expand-k">约束命中</span>
                  <div class="stop-expand-tags">
                    <el-tag v-for="tag in row.constraints_hit" :key="tag" size="small" effect="plain" class="stop-constraint-tag">
                      {{ tag }}
                    </el-tag>
                  </div>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="sequence_global" width="56" align="center">
            <template #header>
              <span>全序</span>
              <el-tooltip
                content="本方案全部订单里的顺序号（算法排序后 1…N），便于总览；与「本车序」不同。"
                placement="top"
                :show-after="200"
                max-width="280"
              >
                <el-icon class="col-help-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="sequence" width="64" align="center">
            <template #header>
              <span>本车序</span>
              <el-tooltip content="该车在本条行驶线路上第几站（每辆车各自从 1 递增）。" placement="top" :show-after="200" max-width="260">
                <el-icon class="col-help-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="order_no" label="订单号" min-width="128" show-overflow-tooltip />
          <el-table-column prop="vehicle_no" label="车辆" min-width="92" show-overflow-tooltip />
          <el-table-column prop="client_name" label="客户" min-width="108" show-overflow-tooltip />
          <el-table-column prop="client_delivery_window" min-width="156" show-overflow-tooltip>
            <template #header>
              <span>客户约定送达</span>
              <el-tooltip :content="clientWindowHeaderTip" placement="top" :show-after="200" max-width="340">
                <el-icon class="col-help-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column width="100" align="right">
            <template #header>
              <span>窗内等待(分)</span>
              <el-tooltip
                content="车辆若早于客户约定窗口起点驶达，按「就地等待至窗内再开工」推算；为 0 或 — 表示无需等待（到达已在窗口内或之后）。"
                placement="top"
                :show-after="200"
                max-width="320"
              >
                <el-icon class="col-help-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              {{ Number(row.window_early_wait_minutes) > 0 ? row.window_early_wait_minutes : '—' }}
            </template>
          </el-table-column>
          <el-table-column width="104" align="right">
            <template #header>
              <span>超窗(分)</span>
              <el-tooltip :content="overtimeHeaderTip" placement="top" :show-after="200" max-width="340">
                <el-icon class="col-help-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-tooltip :content="overtimeCellTooltip(row)" placement="top" :show-after="300" max-width="360">
                <span
                  :class="[
                    'cursor-help border-b border-dotted border-transparent',
                    Number(row.window_violation_minutes) > 0 ? 'text-red-600 font-semibold border-red-300' : '',
                  ]"
                >
                  {{ Number(row.window_violation_minutes) > 0 ? row.window_violation_minutes : '—' }}
                </span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="planned_arrive_datetime" label="计划到达" min-width="136" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.planned_arrive_datetime || row.planned_arrive_time || '—' }}
            </template>
          </el-table-column>
        </el-table>
        </div>
      </el-card>

      <el-card class="mt-3">
        <template #header>风险提示</template>
        <el-alert
          v-for="(item, idx) in plan.risk_alerts || []"
          :key="`${item}-${idx}`"
          class="mb-2"
          type="warning"
          :closable="false"
          :title="item"
        />
        <el-empty v-if="!(plan.risk_alerts || []).length" description="当前无明显风险" />
      </el-card>
    </el-col>
  </el-row>

  <el-dialog
    v-model="customerDemoVisible"
    title="计算简报"
    width="680px"
    destroy-on-close
    class="customer-demo-dlg"
    align-center
  >
    <el-steps :active="customerDemoStep" align-center finish-status="success" class="customer-demo-steps">
      <el-step title="输入与规模" />
      <el-step title="引擎可信指标" />
      <el-step title="收益与口径" />
    </el-steps>
    <div class="customer-demo-pane">
      <div v-show="customerDemoStep === 0" class="customer-demo-step">
        <p class="customer-demo-lead">本次演示基于当前配送商在选定计划日下的真实订单与参数。</p>
        <ul class="customer-demo-list">
          <li><strong>计划日期</strong>：{{ plan.planning_inputs_echo?.planning_date || planningDate }}</li>
          <li>
            <strong>参与订单</strong>：{{ [...new Set((plan.stops || []).map((s) => s.order_id ?? s.order_no))].length }} 单（{{
              (plan.stops || []).length
            }}
            个停靠点）
          </li>
          <li><strong>出车规模</strong>：{{ plan.vehicles_used_in_plan ?? 0 }} 辆（本方案实际派车）</li>
          <li><strong>默认服务时长</strong>：{{ plan.planning_inputs_echo?.service_minutes_default ?? serviceMinutesDefault }} 分钟/站</li>
        </ul>
      </div>
      <div v-show="customerDemoStep === 1" class="customer-demo-step">
        <p class="customer-demo-lead">引擎侧可验证信号（来自本次规划返回值，非文案包装）。</p>
        <div class="engine-credibility-strip engine-credibility-strip--dialog">
          <div class="ecs-cell">
            <el-icon class="ecs-ico ecs-ico--ok"><Histogram /></el-icon>
            <div class="ecs-text">
              <div class="ecs-title">{{ routingModeLabel }}</div>
              <div class="ecs-sub">高德路段 {{ plan.data_quality?.amap_legs_ok ?? 0 }}/{{ plan.data_quality?.amap_legs_total ?? 0 }}</div>
            </div>
          </div>
          <div class="ecs-cell">
            <el-icon class="ecs-ico"><MapLocation /></el-icon>
            <div class="ecs-text">
              <div class="ecs-title">坐标覆盖 {{ (Number(plan.data_quality?.geo_coverage || 0) * 100).toFixed(1) }}%</div>
              <div class="ecs-sub">{{ plan.data_quality?.mode === 'real_geo' ? '全量真实坐标' : '含估算坐标' }}</div>
            </div>
          </div>
        </div>
        <div class="capability-badge-row capability-badge-row--dialog">
          <el-tooltip v-for="item in plan.capability_badges || []" :key="'d-' + item" :content="badgeTip(item)" placement="top">
            <el-tag size="small" effect="plain" type="primary" class="capability-badge">{{ item }}</el-tag>
          </el-tooltip>
        </div>
      </div>
      <div v-show="customerDemoStep === 2" class="customer-demo-step">
        <p class="customer-demo-lead">收益数字由「本方案真实累计」与「行业粗放对标假设」相减得到，便于对外说明量级。</p>
        <div class="customer-demo-kpi">
          <div class="customer-demo-kpi-item">
            <span class="k">节省里程</span>
            <span class="v">{{ Number(briefCompareSnapshot?.sKm ?? optCompare.distance_saved_km ?? 0).toFixed(2) }} km</span>
          </div>
          <div class="customer-demo-kpi-item">
            <span class="k">节省总时长</span>
            <span class="v">{{ briefCompareSnapshot?.sMin ?? optCompare.duration_saved_minutes ?? '—' }} 分钟</span>
          </div>
        </div>
        <p class="compare-method-p customer-demo-foot">
          {{
            optCompare.baseline_description ||
            '对标值为在本方案累计之上按行业粗放冗余系数估算，非第二套路径仿真；节省量为二者之差。'
          }}
        </p>
      </div>
    </div>
    <template #footer>
      <el-button @click="customerDemoVisible = false">关闭</el-button>
      <el-button v-if="customerDemoStep > 0" @click="customerDemoStep -= 1">上一步</el-button>
      <el-button v-if="customerDemoStep < 2" type="primary" @click="customerDemoStep += 1">下一步</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="manualDialogVisible" title="手动建车次" width="760px" destroy-on-close class="manual-dispatch-dialog">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="mb-3"
      title="手动调度用于兜底，不经过智能排线优化；保存后仍走装车、发车、异常发车和司机端流程。"
    />
    <el-form label-width="96px">
      <el-form-item label="配送日期">
        <el-date-picker v-model="planningDate" type="date" value-format="YYYY-MM-DD" class="w-full" />
      </el-form-item>
      <el-form-item label="车辆">
        <el-select v-model="manualVehicleId" filterable class="w-full" placeholder="选择车辆">
          <el-option
            v-for="v in deliveryVehicles"
            :key="v.id"
            :label="`${v.vehicle_no} ${v.driver_name ? '· ' + v.driver_name : ''}`"
            :value="v.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="发车时间">
        <el-time-select v-model="manualDepartureTime" start="04:00" step="00:15" end="23:45" class="w-full" />
      </el-form-item>
      <el-form-item label="订单">
        <el-select
          v-model="manualOrderIds"
          multiple
          filterable
          collapse-tags
          collapse-tags-tooltip
          class="w-full"
          placeholder="选择已分单订单"
        >
          <el-option
            v-for="row in manualDispatchableOrders"
            :key="row.id"
            :label="`${row.order_no} · ${orderDispatchLabel(row)}`"
            :value="row.id"
          />
        </el-select>
        <p class="field-tip">这里只能选择已完成智能分单的订单；未分单订单可预排线，但不能手动建车次。</p>
      </el-form-item>
    </el-form>
    <el-table :data="manualSelectedOrders" border size="small" max-height="260" empty-text="请选择订单">
      <el-table-column label="顺序" width="92">
        <template #default="{ $index }">
          <div class="manual-seq-actions">
            <span>{{ $index + 1 }}</span>
            <el-button link size="small" :disabled="$index === 0" @click="moveManualOrder($index, -1)">上移</el-button>
            <el-button
              link
              size="small"
              :disabled="$index === manualSelectedOrders.length - 1"
              @click="moveManualOrder($index, 1)"
            >
              下移
            </el-button>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="order_no" label="订单号" min-width="150" />
      <el-table-column prop="client_name" label="客户" min-width="150" show-overflow-tooltip />
      <el-table-column label="窗口" min-width="150">
        <template #default="{ row }">{{ row.expected_delivery_date || planningDate }} {{ row.expected_delivery_slot || '—' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="130">
        <template #default="{ row }">
          <el-tag size="small" :type="orderDispatchTagType(row)" effect="plain">{{ orderDispatchLabel(row) }}</el-tag>
        </template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button @click="manualDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="manualSubmitting" @click="submitManualDispatch">保存手动车次</el-button>
    </template>
  </el-dialog>

  <Teleport to="body">
    <div class="route-plan-print-export" aria-hidden="true">
      <div class="rpp-inner">
        <header class="rpp-hd">
          <h1 class="rpp-title">配送任务单（按司机）</h1>
          <p class="rpp-sub">管理人员下发 · 司机随车核对 · 以客户约定时段为准</p>
        </header>
        <section class="rpp-meta">
          <div class="rpp-meta-grid">
            <span><strong>调度主体</strong> {{ printDeliveryMeta.org }}</span>
            <span v-if="printDeliveryMeta.date"><strong>计划配送日</strong> {{ printDeliveryMeta.date }}</span>
            <span v-if="printDeliveryMeta.depart"><strong>计划发车</strong> {{ printDeliveryMeta.depart }}（北京）</span>
            <span><strong>方案里程</strong> {{ printDeliveryMeta.totalKm }}</span>
            <span><strong>方案时长</strong> {{ printDeliveryMeta.estMin }}</span>
            <span
              ><strong>打印时间</strong>
              {{ new Date().toLocaleString('zh-CN', { hour12: false }) }}</span
            >
          </div>
        </section>

        <section
          v-for="(sec, sidx) in deliveryPrintSections"
          :key="sec.groupKey"
          class="rpp-driver"
          :class="{ 'rpp-driver--break': sidx > 0 }"
        >
          <h2 class="rpp-driver-title">
            <span class="rpp-driver-label">司机</span>
            <span class="rpp-driver-name">{{ sec.driverLabel }}</span>
          </h2>
          <p class="rpp-driver-sub">{{ sec.subtitle }}</p>
          <table class="rpp-table">
            <thead>
              <tr>
                <th class="c-seq">本车序</th>
                <th class="c-vno">车牌</th>
                <th class="c-ord">订单号</th>
                <th class="c-cli">客户</th>
                <th class="c-addr">收货地址</th>
                <th class="c-win">客户约定送达</th>
                <th class="c-time">计划到达</th>
                <th class="c-time">计划离开</th>
                <th class="c-num">货重(kg)</th>
                <th class="c-num">体积(m³)</th>
                <th class="c-ot">超窗(分)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in sec.rows" :key="`${row.order_id}-${row.vehicle_no}-${row.sequence_global ?? row.sequence}`">
                <td class="c-seq">{{ row.sequence ?? '—' }}</td>
                <td class="c-vno">{{ row.vehicle_no || '—' }}</td>
                <td class="c-ord">{{ row.order_no || '—' }}</td>
                <td class="c-cli">{{ row.client_name || '—' }}</td>
                <td class="c-addr">{{ formatPrintAddress(row) }}</td>
                <td class="c-win">{{ row.client_delivery_window || row.time_window || '—' }}</td>
                <td class="c-time">{{ row.planned_arrive_datetime || row.planned_arrive_time || '—' }}</td>
                <td class="c-time">{{ row.planned_leave_datetime || row.planned_leave_time || '—' }}</td>
                <td class="c-num">{{ row.load_weight_kg ?? '—' }}</td>
                <td class="c-num">{{ row.load_volume_m3 ?? '—' }}</td>
                <td class="c-ot">{{ Number(row.window_violation_minutes) > 0 ? row.window_violation_minutes : '—' }}</td>
              </tr>
            </tbody>
          </table>
          <div class="rpp-sign">
            <span>司机签收：____________</span>
            <span>调度确认：____________</span>
            <span>日期：____年____月____日</span>
          </div>
        </section>

        <footer class="rpp-foot">
          本单由「智能路线规划」根据当前参数生成；若与客户约定或现场路况不符，请以管理人员书面变更及客户沟通结果为准。
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}
.action-row__btns {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.order-option-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.order-option-tags {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: flex-end;
}
.occupancy-help-list {
  margin: 0;
  padding-left: 1.1rem;
  line-height: 1.55;
  font-size: 13px;
}
.occupancy-help-list li + li {
  margin-top: 4px;
}
.manual-seq-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.manual-dispatch-dialog :deep(.el-dialog__body) {
  padding-top: 10px;
}
.phase2-kb-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  color: #64748b;
  cursor: pointer;
  flex-shrink: 0;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}
.phase2-kb-btn:hover {
  color: #0f172a;
  border-color: #cbd5e1;
  background: #f1f5f9;
}
.phase2-kb-ico {
  font-size: 18px;
}
.phase2-kb {
  font-size: 13px;
  line-height: 1.55;
  color: #334155;
}
.phase2-kb-title {
  margin: 0 0 10px;
  font-weight: 600;
  color: #0f172a;
  font-size: 14px;
}
.phase2-kb-section {
  margin: 10px 0 6px;
  font-weight: 600;
  color: #0f172a;
  font-size: 12px;
}
.phase2-kb-section:first-of-type {
  margin-top: 0;
}
.phase2-kb-list {
  margin: 0;
  padding-left: 1.15em;
}
.phase2-kb-list li {
  margin-bottom: 6px;
}
.phase2-kb-list li:last-child {
  margin-bottom: 0;
}
.phase2-kb-foot {
  margin: 12px 0 0;
  padding-top: 8px;
  border-top: 1px solid #e2e8f0;
  font-size: 11px;
  color: #94a3b8;
}

.btn-ico {
  margin-right: 4px;
  vertical-align: -0.12em;
}

.compare-card-hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  width: 100%;
}

.compare-card-title {
  font-weight: 600;
  color: #0f172a;
}

.compare-card-hd-actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.compare-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.compare-metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  border-radius: 10px;
  background: linear-gradient(135deg, #f0fdf4 0%, #eff6ff 100%);
  border: 1px solid #d1fae5;
}

.compare-metric--highlight .compare-metric-k {
  font-size: 12px;
  color: #64748b;
  font-weight: 500;
}

.compare-metric--highlight .compare-metric-v {
  font-size: 22px;
  font-weight: 700;
  color: #0f172a;
  font-variant-numeric: tabular-nums;
}

.compare-metric--highlight .compare-metric-v small {
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
}

.compare-metric-hint {
  font-size: 11px;
  color: #94a3b8;
}

.compare-bars {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.compare-bar-block {
  padding: 12px;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid #e8ecf1;
}

.compare-bar-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 10px;
}

.compare-bar-ico {
  width: 16px;
  height: 16px;
  color: #3b82f6;
}

.compare-bar-row {
  display: grid;
  grid-template-columns: 72px 1fr 56px;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.compare-bar-row:last-child {
  margin-bottom: 0;
}

.compare-bar-label {
  font-size: 11px;
  color: #94a3b8;
}

.compare-bar-track {
  height: 10px;
  border-radius: 999px;
  background: #e2e8f0;
  overflow: hidden;
}

.compare-bar-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.35s ease;
}

.compare-bar-fill--baseline {
  background: linear-gradient(90deg, #cbd5e1, #94a3b8);
}

.compare-bar-fill--opt {
  background: linear-gradient(90deg, #3b82f6, #2563eb);
  box-shadow: 0 0 12px rgba(37, 99, 235, 0.25);
}

.compare-bar-num {
  font-size: 12px;
  font-weight: 600;
  color: #334155;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.compare-collapse {
  border: none;
  --el-collapse-header-bg-color: transparent;
}

.compare-collapse :deep(.el-collapse-item__header) {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  padding-left: 0;
}

.compare-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

.compare-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 4px;
}

.compare-collapse-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.compare-collapse-ico {
  width: 16px;
  height: 16px;
  color: #64748b;
}

.compare-method-p {
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
  color: #475569;
}

.compare-method-meta {
  margin: 10px 0 0;
  font-size: 11px;
  color: #94a3b8;
}

.compare-method-meta code {
  font-size: 11px;
  background: #f1f5f9;
  padding: 1px 6px;
  border-radius: 4px;
}

.engine-credibility-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  background: linear-gradient(180deg, #fafbfc 0%, #f1f5f9 100%);
  border: 1px solid #e8ecf1;
}

.engine-credibility-strip--dialog {
  margin-top: 0;
}

.ecs-cell {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 160px;
  flex: 1;
}

.ecs-ico {
  font-size: 22px;
  color: #64748b;
  flex-shrink: 0;
  margin-top: 2px;
}

.ecs-ico--ok {
  color: #16a34a;
}

.ecs-title {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.35;
}

.ecs-sub {
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
}

.capability-badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.capability-badge-row--dialog {
  margin-top: 14px;
}

.capability-badge {
  cursor: default;
  border-radius: 8px;
}

.customer-demo-steps {
  margin-bottom: 20px;
}

.customer-demo-pane {
  min-height: 200px;
  padding: 8px 0 4px;
}

.customer-demo-lead {
  margin: 0 0 12px;
  font-size: 13px;
  color: #475569;
  line-height: 1.55;
}

.customer-demo-list {
  margin: 0;
  padding-left: 18px;
  color: #334155;
  font-size: 13px;
  line-height: 1.8;
}

.customer-demo-kpi {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 14px;
}

.customer-demo-kpi-item {
  flex: 1;
  min-width: 140px;
  padding: 12px 14px;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid #e8ecf1;
}

.customer-demo-kpi-item .k {
  display: block;
  font-size: 12px;
  color: #64748b;
  margin-bottom: 4px;
}

.customer-demo-kpi-item .v {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
  font-variant-numeric: tabular-nums;
}

.customer-demo-foot {
  margin-top: 8px;
}

.quick-select-row {
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.quick-select-text {
  color: #64748b;
  font-size: 12px;
}
.field-tip {
  margin: 6px 0 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}
.inline-hint {
  margin-left: 8px;
  font-size: 12px;
  color: #64748b;
}
.echo-compact {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #e8ecf1;
}

.echo-compact__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
}

.echo-compact__main {
  font-size: 12px;
  color: #0f172a;
  line-height: 1.45;
  min-width: 0;
}

.echo-more-link {
  flex-shrink: 0;
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  color: #2563eb;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.echo-more-link:hover {
  color: #1d4ed8;
}
.vehicle-stats-block {
  margin: 6px 0 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: linear-gradient(135deg, #f0fdf4 0%, #ecfeff 100%);
  border: 1px solid #bbf7d0;
}
.vehicle-stats-main {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 600;
  color: #14532d;
  line-height: 1.5;
}
.vehicle-stats-sub {
  margin: 0;
  line-height: 1.45;
}
.limit-block {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #e2e8f0;
}
.limit-title {
  font-weight: 600;
  font-size: 14px;
  color: #334155;
  margin-bottom: 6px;
}
.limit-desc {
  font-size: 12px;
  color: #64748b;
  margin: 0 0 10px;
  line-height: 1.5;
}
.limit-hint {
  font-size: 12px;
  color: #475569;
  margin: 0 0 10px;
  line-height: 1.55;
  padding: 8px 10px;
  background: #f1f5f9;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.limit-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.limit-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}
.limit-chip--disabled {
  background: #e2e8f0;
  border-color: #cbd5e1;
  opacity: 0.88;
}
.limit-chip--disabled .plate {
  color: #64748b;
  text-decoration: line-through;
  text-decoration-thickness: 2px;
}
.limit-chip-switch {
  flex-shrink: 0;
}
.limit-chip .plate {
  font-weight: 600;
  font-size: 13px;
  color: #0f172a;
}
.limit-reason-hint {
  cursor: help;
  font-size: 12px;
  color: #94a3b8;
}
.map-header {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
}
.map-toolbar {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
}
.map-toolbar-row {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
}
.vehicle-route-select {
  flex: 1;
  min-width: 200px;
  max-width: 420px;
}
.map-actions-inline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.limit-select-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.limit-select-label {
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
}
.limit-plate-select {
  min-width: 160px;
  max-width: 280px;
}
.col-help-icon {
  margin-left: 4px;
  vertical-align: -0.15em;
  font-size: 14px;
  color: #94a3b8;
  cursor: help;
}
.limit-chips-scroll {
  max-height: 240px;
  overflow-y: auto;
  padding-right: 4px;
}
.map-panel {
  border-radius: 8px;
  overflow: hidden;
}
/* 右侧主列：允许内部横向滚动，避免宽表被 el-col flex 卡死 */
.route-plan-row {
  align-items: flex-start;
}
.route-plan-main-col {
  min-width: 0;
}
.route-stops-table-scroll {
  width: 100%;
  max-width: 100%;
  overflow-x: auto;
  overflow-y: visible;
  -webkit-overflow-scrolling: touch;
}
.route-stops-table-scroll :deep(.el-table) {
  min-width: 920px;
}

.stops-card :deep(.el-card__header) {
  padding: 12px 16px;
}

.stops-card-header {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

.stops-card-sub {
  font-size: 12px;
  font-weight: 400;
  color: #94a3b8;
}

.stops-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.stops-search {
  flex: 1;
  min-width: 200px;
  max-width: 420px;
}

.stops-count {
  font-size: 12px;
  color: #64748b;
}

.stops-count strong {
  color: #334155;
  font-weight: 600;
}

.stops-elegant-table {
  --el-table-border-color: #e8ecf1;
  border-radius: 8px;
  overflow: hidden;
}

.stops-elegant-table :deep(.el-table__header-wrapper th) {
  background: #f8fafc !important;
  color: #475569;
  font-weight: 600;
  font-size: 12px;
}

.stops-elegant-table :deep(.el-table__body tr:hover > td) {
  background-color: #fafbfc !important;
}

.stops-elegant-table :deep(.el-table__expanded-cell) {
  padding: 0 !important;
}

.stop-expand {
  padding: 14px 16px 16px 52px;
  background: linear-gradient(180deg, #fafbfc 0%, #f8fafc 100%);
  border-top: 1px solid #eef2f6;
}

.stop-expand-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: 12px 20px;
}

.stop-expand-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.stop-expand-k {
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.stop-expand-v {
  font-size: 13px;
  color: #0f172a;
  font-variant-numeric: tabular-nums;
}

.stop-expand-sep {
  margin: 0 6px;
  color: #cbd5e1;
}

.stop-expand-constraints {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed #e2e8f0;
}

.stop-expand-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.stop-constraint-tag {
  border-radius: 6px;
}

.route-plan-top-alert :deep(.el-alert__title) {
  white-space: normal;
  word-break: break-word;
  line-height: 1.55;
  font-size: 13px;
}
</style>

<style>
.route-echo-popper.el-popover.el-popper {
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid #e8ecf1;
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.1);
}

.echo-popover-pre,
.echo-tip-pre {
  margin: 0;
  font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif;
  font-size: 12px;
  line-height: 1.6;
  color: #1e293b;
  white-space: pre-wrap;
  word-break: break-word;
}

.anim-tip {
  font-size: 13px;
  color: #334155;
  line-height: 1.45;
}
/* 注入到高德覆盖层的 HTML，勿用 scoped */
.route-stop-marker-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
}
.route-stop-marker-g {
  min-width: 24px;
  height: 22px;
  padding: 0 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(145deg, #2563eb, #1d4ed8);
  color: #fff;
  font-weight: 700;
  font-size: 11px;
  border-radius: 11px;
  box-shadow: 0 2px 10px rgba(37, 99, 235, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.35);
}
.route-stop-marker-meta {
  font-size: 10px;
  font-weight: 600;
  color: #0f172a;
  background: rgba(255, 255, 255, 0.97);
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 2px 7px;
  max-width: 128px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.12);
}
.route-stop-marker-dot {
  color: #94a3b8;
  font-weight: 400;
  margin: 0 2px;
}
.route-depot-chip {
  font-size: 11px;
  font-weight: 700;
  color: #0f172a;
  background: #fef3c7;
  border: 1px solid #fcd34d;
  border-radius: 999px;
  padding: 4px 10px;
  box-shadow: 0 2px 8px rgba(245, 158, 11, 0.25);
  white-space: nowrap;
}
.route-map-pop {
  min-width: 220px;
  max-width: 300px;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.2);
  border: 1px solid #e2e8f0;
  background: #fff;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
}
.route-map-pop-hd {
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(95deg, #334155, #0f172a);
  letter-spacing: 0.02em;
}
.route-map-pop-bd {
  padding: 10px 12px 12px;
  font-size: 12px;
  color: #334155;
  line-height: 1.55;
}
.route-map-pop-line {
  margin-bottom: 5px;
}
.route-map-pop-line:last-child {
  margin-bottom: 0;
}
.route-map-pop-line.muted {
  color: #64748b;
  font-size: 11px;
}
.route-map-pop-k {
  display: inline-block;
  min-width: 36px;
  margin-right: 4px;
  color: #94a3b8;
  font-size: 11px;
}
.route-map-pop-anim {
  box-shadow: 0 10px 28px rgba(37, 99, 235, 0.22);
  border-color: #bfdbfe;
}
.route-map-pop-anim .route-map-pop-hd {
  background: linear-gradient(95deg, #2563eb, #1d4ed8);
}

/* —— 配送任务单打印（Teleport 至 body，屏幕不占位）—— */
@media screen {
  .route-plan-print-export {
    position: absolute;
    left: -9999px;
    top: 0;
    width: 190mm;
    pointer-events: none;
  }
}
@media print {
  @page {
    margin: 10mm 12mm;
    size: A4;
  }
  /* 勿用 body visibility:hidden：#app 仍占位会导致前几页空白；打印时直接隐藏应用根节点 */
  #app {
    display: none !important;
  }
  html,
  body {
    height: auto !important;
    background: #fff !important;
  }
  .route-plan-print-export {
    display: block !important;
    position: static !important;
    left: auto !important;
    width: 100% !important;
    background: #fff !important;
    color: #0f172a !important;
    pointer-events: auto !important;
  }
  .rpp-inner {
    font-family: system-ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    font-size: 10.5pt;
    line-height: 1.45;
  }
  .rpp-hd {
    text-align: center;
    margin-bottom: 10px;
    padding-bottom: 8px;
    border-bottom: 2px solid #0f172a;
  }
  .rpp-title {
    margin: 0;
    font-size: 18pt;
    letter-spacing: 0.06em;
  }
  .rpp-sub {
    margin: 6px 0 0;
    font-size: 9.5pt;
    color: #475569;
  }
  .rpp-meta {
    margin-bottom: 12px;
    padding: 8px 10px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
  }
  .rpp-meta-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px 16px;
  }
  .rpp-meta-grid span {
    font-size: 9.5pt;
  }
  .rpp-driver--break {
    page-break-before: always;
    padding-top: 6mm;
  }
  .rpp-driver-title {
    margin: 0 0 4px;
    font-size: 13pt;
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .rpp-driver-label {
    font-size: 10pt;
    color: #64748b;
    font-weight: 600;
  }
  .rpp-driver-name {
    font-weight: 800;
    border-bottom: 2px solid #334155;
    padding-bottom: 1px;
  }
  .rpp-driver-sub {
    margin: 0 0 8px;
    font-size: 9.5pt;
    color: #475569;
  }
  .rpp-table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
    font-size: 8.5pt;
  }
  .rpp-table th,
  .rpp-table td {
    border: 1px solid #94a3b8;
    padding: 4px 5px;
    vertical-align: top;
    word-break: break-word;
  }
  .rpp-table th {
    background: #e2e8f0;
    font-weight: 700;
    text-align: center;
  }
  .rpp-table .c-seq {
    width: 7%;
    text-align: center;
  }
  .rpp-table .c-vno {
    width: 9%;
    text-align: center;
  }
  .rpp-table .c-ord {
    width: 11%;
  }
  .rpp-table .c-cli {
    width: 10%;
  }
  .rpp-table .c-addr {
    width: 22%;
  }
  .rpp-table .c-win {
    width: 14%;
  }
  .rpp-table .c-time {
    width: 10%;
    text-align: center;
  }
  .rpp-table .c-num {
    width: 6%;
    text-align: right;
  }
  .rpp-table .c-ot {
    width: 6%;
    text-align: center;
  }
  .rpp-sign {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 12px;
    margin-top: 14px;
    padding-top: 8px;
    font-size: 9.5pt;
    border-top: 1px dashed #94a3b8;
  }
  .rpp-foot {
    margin-top: 12px;
    padding-top: 8px;
    font-size: 8.5pt;
    color: #64748b;
    border-top: 1px solid #cbd5e1;
  }
}
</style>
