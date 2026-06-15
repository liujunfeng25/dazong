<script setup>
import AMapLoader from '@amap/amap-jsapi-loader'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { monitorDispatchTripApi } from '../api/monitor'
import { formatChinaDateTime } from '../utils/datetime'

const props = defineProps({
  tripDetail: { type: Object, default: () => ({}) },
  focusedStopId: { type: [Number, String, null], default: null },
  theme: { type: String, default: 'dark' },
  autoRefresh: { type: Boolean, default: true },
  refreshIntervalMs: { type: Number, default: 15000 },
  mapHeight: { type: Number, default: 420 },
})

const emit = defineEmits(['update:focusedStopId', 'trip-updated'])

const mapRef = ref(null)
const mapError = ref('')
const localDetail = ref(props.tripDetail || {})
const lastRefreshedAt = ref('')
let amap = null
let overlays = []
let refreshTimer = null

const isDark = computed(() => props.theme === 'dark')
const trip = computed(() => localDetail.value || {})
const stops = computed(() => (Array.isArray(trip.value.stops) ? trip.value.stops : []))
const vehicleLocation = computed(() => trip.value.vehicle_location || null)
const deliveryOrigin = computed(() => trip.value.delivery_origin || null)
const isInTransit = computed(() => String(trip.value.status || '') === '运输中')
const tripId = computed(() => trip.value.id)

const isStopDelivered = (stop) => String(stop?.status || '') === '已送达'

const nextStop = computed(() =>
  stops.value.find((stop) => !isStopDelivered(stop) && String(stop.status || '') !== '未随车') || null,
)

const effectiveFocusId = computed(() => {
  const raw = props.focusedStopId
  if (raw != null && raw !== '') return Number(raw)
  return nextStop.value ? Number(nextStop.value.id) : null
})

const normalizeRoutePath = (raw) => {
  if (!Array.isArray(raw)) return []
  return raw
    .map((point) => {
      if (Array.isArray(point) && point.length >= 2) {
        return [Number(point[0]), Number(point[1])]
      }
      if (point && typeof point === 'object') {
        return [Number(point.lng), Number(point.lat)]
      }
      return null
    })
    .filter((pair) => pair && Number.isFinite(pair[0]) && Number.isFinite(pair[1]))
}

const routePath = computed(() => normalizeRoutePath(trip.value.route_path))

const hasMapContent = computed(() => {
  const hasStops = stops.value.some((s) => Number.isFinite(Number(s.lng)) && Number.isFinite(Number(s.lat)))
  const hasVehicle = vehicleLocation.value?.lng != null && vehicleLocation.value?.lat != null
  const hasOrigin = deliveryOrigin.value?.lng != null && deliveryOrigin.value?.lat != null
  return hasStops || hasVehicle || hasOrigin || routePath.value.length > 0
})

const refreshStatusText = computed(() => {
  if (!lastRefreshedAt.value) return '随页面加载'
  return formatChinaDateTime(lastRefreshedAt.value)
})

const stopMarkerHtml = (stop, focused) => {
  const delivered = isStopDelivered(stop)
  const isNext = nextStop.value && Number(nextStop.value.id) === Number(stop.id)
  let bg = '#3b82f6'
  if (delivered) bg = '#64748b'
  else if (focused || isNext) bg = '#f97316'
  return `<div class="trip-stop-chip" style="background:${bg}">${stop.sequence}</div>`
}

const vehicleMarkerHtml = () =>
  '<div class="trip-vehicle-chip">车</div>'

const originMarkerHtml = () =>
  '<div class="trip-origin-chip">起</div>'

const clearOverlays = () => {
  if (amap) {
    overlays.forEach((overlay) => {
      try {
        amap.remove(overlay)
      } catch {
        // ignore
      }
    })
  }
  overlays = []
}

const destroyMap = () => {
  clearOverlays()
  if (amap) {
    try {
      amap.destroy()
    } catch {
      // ignore
    }
  }
  amap = null
}

const renderMap = async () => {
  mapError.value = ''
  if (!mapRef.value || !hasMapContent.value) {
    clearOverlays()
    return
  }
  const key = import.meta.env.VITE_AMAP_KEY
  if (!key) {
    mapError.value = '未配置高德地图 Key，暂不显示地图。'
    return
  }
  try {
    await AMapLoader.load({ key, version: '2.0' })
    const focusStop = stops.value.find((s) => Number(s.id) === Number(effectiveFocusId.value))
    const defaultCenter = focusStop?.lng != null
      ? [Number(focusStop.lng), Number(focusStop.lat)]
      : vehicleLocation.value?.lng != null
        ? [Number(vehicleLocation.value.lng), Number(vehicleLocation.value.lat)]
        : deliveryOrigin.value?.lng != null
          ? [Number(deliveryOrigin.value.lng), Number(deliveryOrigin.value.lat)]
          : routePath.value[0] || [116.397428, 39.90923]

    if (!amap) {
      amap = new window.AMap.Map(mapRef.value, {
        zoom: 12,
        center: defaultCenter,
        mapStyle: isDark.value ? 'amap://styles/darkblue' : undefined,
      })
    } else {
      amap.setCenter(defaultCenter)
    }

    clearOverlays()

    if (routePath.value.length > 1) {
      const line = new window.AMap.Polyline({
        path: routePath.value,
        strokeColor: '#22d3ee',
        strokeWeight: 5,
        strokeOpacity: 0.85,
        lineJoin: 'round',
        lineCap: 'round',
      })
      line.setMap(amap)
      overlays.push(line)
    }

    const origin = deliveryOrigin.value
    if (origin?.lng != null && origin?.lat != null) {
      const marker = new window.AMap.Marker({
        position: [Number(origin.lng), Number(origin.lat)],
        title: origin.label || '配送起点',
        content: originMarkerHtml(),
        offset: new window.AMap.Pixel(-14, -14),
        zIndex: 120,
      })
      marker.setMap(amap)
      overlays.push(marker)
    }

    stops.value.forEach((stop) => {
      if (stop.lng == null || stop.lat == null) return
      const focused = Number(stop.id) === Number(effectiveFocusId.value)
      const marker = new window.AMap.Marker({
        position: [Number(stop.lng), Number(stop.lat)],
        title: stop.canteen_name || stop.client_name || `第${stop.sequence}站`,
        content: stopMarkerHtml(stop, focused),
        offset: new window.AMap.Pixel(-14, -14),
        zIndex: focused ? 130 : 110,
      })
      marker.on('click', () => focusStop(stop.id))
      marker.setMap(amap)
      overlays.push(marker)
    })

    const vehicle = vehicleLocation.value
    if (vehicle?.lng != null && vehicle?.lat != null) {
      const marker = new window.AMap.Marker({
        position: [Number(vehicle.lng), Number(vehicle.lat)],
        title: vehicle.label || trip.value.vehicle_no || '车辆',
        content: vehicleMarkerHtml(),
        offset: new window.AMap.Pixel(-14, -14),
        zIndex: 140,
      })
      marker.setMap(amap)
      overlays.push(marker)
    }

    if (overlays.length) {
      amap.setFitView(overlays, false, [48, 48, 48, 48], 16)
    }
    if (focusStop?.lng != null && focusStop?.lat != null) {
      amap.setCenter([Number(focusStop.lng), Number(focusStop.lat)])
      amap.setZoom(Math.max(amap.getZoom(), 14))
    }
    amap.resize()
  } catch {
    mapError.value = '地图加载失败，请确认网络、高德 Key 或关闭 VPN 后重试。'
  }
}

const focusStop = (stopId) => {
  emit('update:focusedStopId', Number(stopId))
}

const stopTone = (stop) => {
  if (Number(stop.id) === Number(effectiveFocusId.value)) return 'focus'
  if (isStopDelivered(stop)) return 'done'
  if (nextStop.value && Number(nextStop.value.id) === Number(stop.id)) return 'next'
  return ''
}

const stopStatusLabel = (stop) => {
  if (isStopDelivered(stop)) return '已送达'
  if (nextStop.value && Number(nextStop.value.id) === Number(stop.id)) return '下一站'
  return stop.status || '待配送'
}

const stopAutoRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

const startAutoRefresh = () => {
  stopAutoRefresh()
  if (!props.autoRefresh || !isInTransit.value || !tripId.value || document.hidden) return
  const interval = Math.max(5000, Number(props.refreshIntervalMs || 15000))
  refreshTimer = setInterval(() => {
    refreshTrip({ silent: true })
  }, interval)
}

const refreshTrip = async ({ silent = false } = {}) => {
  if (!tripId.value || !isInTransit.value) return
  try {
    const resp = await monitorDispatchTripApi(tripId.value)
    localDetail.value = resp || localDetail.value
    lastRefreshedAt.value = new Date().toISOString()
    emit('trip-updated', localDetail.value)
    await nextTick()
    await renderMap()
  } catch {
    if (!silent) mapError.value = '车辆位置刷新失败，请稍后重试'
  }
}

const handleVisibility = () => {
  if (document.hidden) {
    stopAutoRefresh()
    return
  }
  if (isInTransit.value) refreshTrip({ silent: true })
  startAutoRefresh()
}

watch(
  () => props.tripDetail,
  (val) => {
    localDetail.value = val || {}
    if (!lastRefreshedAt.value) lastRefreshedAt.value = new Date().toISOString()
  },
  { immediate: true, deep: true },
)

watch(
  () => [effectiveFocusId.value, JSON.stringify(localDetail.value)],
  async () => {
    await nextTick()
    await renderMap()
  },
)

watch(
  () => [props.autoRefresh, isInTransit.value, tripId.value],
  () => {
    startAutoRefresh()
  },
  { immediate: true },
)

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibility)
  nextTick().then(renderMap)
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handleVisibility)
  stopAutoRefresh()
  destroyMap()
})
</script>

<template>
  <div class="trip-route-card" :class="{ dark: isDark }">
    <div class="trip-route-grid">
      <div class="trip-map-wrap" :style="{ minHeight: `${mapHeight}px` }">
        <div v-if="isInTransit && autoRefresh" class="trip-map-hint">
          运输中 · 自动刷新 · {{ refreshStatusText }}
        </div>
        <div ref="mapRef" class="trip-map" />
        <div v-if="mapError" class="trip-map-fallback">{{ mapError }}</div>
        <div v-else-if="!hasMapContent" class="trip-map-fallback">
          暂无可用坐标，站点列表仍可查看地址与配送窗口。
        </div>
      </div>

      <aside class="trip-stop-panel">
        <div class="trip-stop-head">
          <strong>今日配送站点</strong>
          <span>{{ stops.length }} 站</span>
        </div>
        <div v-if="stops.length" class="trip-stop-list">
          <button
            v-for="stop in stops"
            :key="stop.id"
            type="button"
            class="trip-stop-row"
            :class="stopTone(stop)"
            @click="focusStop(stop.id)"
          >
            <span class="trip-stop-seq">{{ stop.sequence }}</span>
            <div class="trip-stop-main">
              <strong>{{ stop.canteen_name || stop.client_name || stop.order_no }}</strong>
              <span>{{ stop.client_name }} · {{ stop.address || '地址待补' }}</span>
              <span>{{ stop.expected_delivery_slot || '窗口待定' }} · {{ stopStatusLabel(stop) }}</span>
            </div>
          </button>
        </div>
        <el-empty v-else description="暂无配送站点" :image-size="56" />
      </aside>
    </div>
  </div>
</template>

<style scoped>
.trip-route-card {
  width: 100%;
}

.trip-route-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(260px, 0.8fr);
  gap: 14px;
  align-items: stretch;
}

.trip-map-wrap {
  position: relative;
  min-height: 420px;
}

.trip-map {
  width: 100%;
  height: 100%;
  min-height: 420px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.25);
}

.trip-route-card.dark .trip-map {
  border-color: rgba(0, 218, 243, 0.18);
  background: #0b1220;
}

.trip-map-hint {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 2;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  color: #cbd5e1;
  background: rgba(15, 23, 42, 0.78);
  border: 1px solid rgba(148, 163, 184, 0.25);
}

.trip-map-fallback {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  border-radius: 10px;
  text-align: center;
  font-size: 13px;
  color: #94a3b8;
  background: rgba(15, 23, 42, 0.72);
}

.trip-stop-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  max-height: 420px;
}

.trip-stop-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
  color: #94a3b8;
}

.trip-route-card.dark .trip-stop-head strong {
  color: #e2e8f0;
}

.trip-stop-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: auto;
  padding-right: 4px;
}

.trip-stop-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  width: 100%;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(15, 23, 42, 0.55);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.trip-stop-row:hover,
.trip-stop-row.focus {
  border-color: rgba(249, 115, 22, 0.65);
  background: rgba(249, 115, 22, 0.08);
}

.trip-stop-row.next {
  border-color: rgba(34, 211, 238, 0.45);
}

.trip-stop-row.done {
  opacity: 0.72;
}

.trip-stop-seq {
  flex: 0 0 28px;
  height: 28px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: #3b82f6;
}

.trip-stop-row.focus .trip-stop-seq,
.trip-stop-row.next .trip-stop-seq {
  background: #f97316;
}

.trip-stop-row.done .trip-stop-seq {
  background: #64748b;
}

.trip-stop-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.trip-stop-main strong {
  font-size: 14px;
  color: #e2e8f0;
}

.trip-stop-main span {
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.4;
}

:global(.trip-stop-chip),
:global(.trip-vehicle-chip),
:global(.trip-origin-chip) {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
}

:global(.trip-vehicle-chip) {
  background: #22c55e;
}

:global(.trip-origin-chip) {
  background: #8b5cf6;
}

@media (max-width: 960px) {
  .trip-route-grid {
    grid-template-columns: 1fr;
  }

  .trip-stop-panel {
    max-height: none;
  }
}
</style>
