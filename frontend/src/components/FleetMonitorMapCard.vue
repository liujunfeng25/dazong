<script setup>
import AMapLoader from '@amap/amap-jsapi-loader'
import { ElMessage } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { buildSortedHistoryPath } from '../utils/amapPathPlayback'
import { useBeidouHistoryPlayback } from '../composables/useBeidouHistoryPlayback'
import {
  deliveryFleetMonitorVehiclesApi,
  deliveryFleetMonitorWarehousesApi,
  postVehicleBeidouHistoryTrackApi,
} from '../api/delivery'
import {
  monitorFleetMonitorVehicleHistoryTrackApi,
  monitorFleetMonitorVehiclesApi,
  monitorFleetMonitorWarehousesApi,
} from '../api/monitor'
import {
  operationFleetMonitorVehicleHistoryTrackApi,
  operationFleetMonitorVehiclesApi,
  operationFleetMonitorWarehousesApi,
} from '../api/operation'
import { useYs7CameraApis } from '../composables/useYs7CameraApis'
import { useUserStore } from '../stores/user'
import { ys7MetaFromRow } from '../utils/ys7DeviceMeta'
import { sleep } from '../utils/sleep'
import { formatChinaDateTime } from '../utils/datetime'
import { warehouseMapMarkerHtml } from '../utils/warehouseElitechDisplay'
import FleetMapLayerToggles from './FleetMapLayerToggles.vue'
import WarehouseCameraLiveDrawer from './WarehouseCameraLiveDrawer.vue'
import Ys7CameraLiveWithPtz from './Ys7CameraLiveWithPtz.vue'

const props = defineProps({
  scope: { type: String, default: 'delivery' },
  title: { type: String, default: '车队实时监控' },
  height: { type: Number, default: 520 },
  variant: { type: String, default: 'card' }, // 'card' | 'immersive'
  mapInit: { type: Object, default: () => ({}) },
})
const userStore = useUserStore()
const canLoadScope = computed(() => !userStore.role || userStore.role === props.scope)

const mapRef = ref(null)
const detailMapRef = ref(null)
const loading = ref(false)
const mapError = ref('')
const vehicles = ref([])
const summary = ref({ total: 0, online: 0, offline: 0, unlocated: 0, cameras: 0 })
const lastRefreshedAt = ref('')
const selectedVehicle = ref(null)
const detailVisible = ref(false)
const detailTab = ref('live')
const historyRange = ref(null)
const historyPoints = ref([])
const historyLoading = ref(false)
const historyPb = useBeidouHistoryPlayback()
const hpPlaying = computed(() => historyPb.isPlaying)
const hpPaused = computed(() => historyPb.isPaused)
const hpCanScrub = computed(() => historyPb.canScrub)
const cameraStates = ref([])
let amap = null
let detailMap = null
let detailTrackPolyline = null
let detailHistoryStartMarker = null
let detailHistoryEndMarker = null
let refreshTimer = null
let overlays = []
let detailOverlays = []

const vehicleApi = computed(() => {
  if (props.scope === 'operation') return operationFleetMonitorVehiclesApi
  if (props.scope === 'monitor') return monitorFleetMonitorVehiclesApi
  return deliveryFleetMonitorVehiclesApi
})
const ys7Apis = computed(() => useYs7CameraApis(props.scope, 'fleet'))
const historyApi = computed(() => {
  if (props.scope === 'operation') return operationFleetMonitorVehicleHistoryTrackApi
  if (props.scope === 'monitor') return monitorFleetMonitorVehicleHistoryTrackApi
  return postVehicleBeidouHistoryTrackApi
})
const warehouseApi = computed(() => {
  if (props.scope === 'operation') return operationFleetMonitorWarehousesApi
  if (props.scope === 'monitor') return monitorFleetMonitorWarehousesApi
  return deliveryFleetMonitorWarehousesApi
})
const isImmersive = computed(() => props.variant === 'immersive')

const warehouses = ref([])
const warehouseSummary = ref({ total: 0, cameras: 0 })
/** 地图图层显隐（默认全部显示） */
const showVehiclesOnMap = ref(true)
const showWarehousesOnMap = ref(true)
const selectedWarehouse = ref(null)
const warehouseDetailVisible = ref(false)
/** null/undefined 经 Number() 会变成 0，误落在非洲几内亚湾 (0,0)，必须显式排除 */
const hasFleetCoords = (v) => {
  const lng = v?.lng
  const lat = v?.lat
  if (lng == null || lat == null || lng === '' || lat === '') return false
  const lngN = Number(lng)
  const latN = Number(lat)
  if (!Number.isFinite(lngN) || !Number.isFinite(latN)) return false
  if (lngN === 0 && latN === 0) return false
  if (v.coordinate_valid === false) return false
  return true
}

const locatedVehicles = computed(() => vehicles.value.filter(hasFleetCoords))
const unlocatedVehicles = computed(() => vehicles.value.filter((v) => !hasFleetCoords(v)))
const refreshText = computed(() => (lastRefreshedAt.value ? formatChinaDateTime(lastRefreshedAt.value) : '尚未刷新'))

const defaultHistoryRange = () => {
  const end = new Date()
  const start = new Date(end.getTime() - 2 * 60 * 60 * 1000)
  return [start, end]
}

const vehicleStatusText = (v) => {
  if (!hasFleetCoords(v)) return '未定位'
  return String(v.online_status || '') === 'online' ? '在线' : '离线'
}

const vehicleStatusClass = (v) => {
  if (!hasFleetCoords(v)) return 'status-unlocated'
  return String(v.online_status || '') === 'online' ? 'status-online' : 'status-offline'
}

const clearOverlays = (map, list) => {
  if (map) {
    list.forEach((o) => {
      try {
        map.remove(o)
      } catch {}
    })
  }
  list.splice(0, list.length)
}

const destroyMap = () => {
  clearOverlays(amap, overlays)
  try {
    amap?.destroy()
  } catch {}
  amap = null
}

const destroyDetailMap = () => {
  historyPb.detachForMapDestroyed()
  if (detailTrackPolyline) {
    try {
      detailTrackPolyline.setMap(null)
    } catch {}
    detailTrackPolyline = null
  }
  if (detailHistoryStartMarker) {
    try {
      detailHistoryStartMarker.setMap(null)
    } catch {}
    detailHistoryStartMarker = null
  }
  if (detailHistoryEndMarker) {
    try {
      detailHistoryEndMarker.setMap(null)
    } catch {}
    detailHistoryEndMarker = null
  }
  clearOverlays(detailMap, detailOverlays)
  try {
    detailMap?.destroy()
  } catch {}
  detailMap = null
}

const getDetailHistoryMap = () => detailMap
const getDetailHistoryPoints = () => historyPoints.value
const getDetailHistoryTitle = () => selectedVehicle.value?.vehicle_no || '历史轨迹'

const onDetailHistoryPlay = () => {
  if (!detailMap) {
    ElMessage.warning('请先等待地图加载完成')
    return
  }
  const r = historyPb.playOrContinue(getDetailHistoryMap, getDetailHistoryPoints, getDetailHistoryTitle)
  if (!r?.ok) {
    ElMessage.warning(r?.reason === 'short_path' ? '轨迹点过少，无法播放' : '地图未就绪')
  }
}

const onDetailHistoryRestart = () => {
  if (!detailMap) {
    ElMessage.warning('请先等待地图加载完成')
    return
  }
  const r = historyPb.restartFromBeginning(getDetailHistoryMap, getDetailHistoryPoints, getDetailHistoryTitle)
  if (!r?.ok) {
    ElMessage.warning(r?.reason === 'short_path' ? '轨迹点过少，无法播放' : '地图未就绪')
  }
}

const markerColor = (v) => {
  if (vehicleStatusClass(v) === 'status-online') return '#16a34a'
  if (vehicleStatusClass(v) === 'status-offline') return '#64748b'
  return '#f59e0b'
}

const renderMap = async () => {
  mapError.value = ''
  if (!mapRef.value) return
  const key = import.meta.env.VITE_AMAP_KEY
  if (!key) {
    mapError.value = '未配置高德地图 Key，暂不显示地图。'
    return
  }
  try {
    const securityJsCode = import.meta.env.VITE_AMAP_SECURITY_JS_CODE
    if (typeof window !== 'undefined' && securityJsCode) {
      window._AMapSecurityConfig = {
        ...(window._AMapSecurityConfig || {}),
        securityJsCode: String(securityJsCode),
      }
    }
    await AMapLoader.load({ key, version: '2.0' })
    if (!amap) {
      amap = new window.AMap.Map(mapRef.value, {
        zoom: 10,
        center: [116.4074, 39.9042],
        ...(props.mapInit || {}),
      })
    }
    clearOverlays(amap, overlays)
    if (showVehiclesOnMap.value) {
      locatedVehicles.value.forEach((v) => {
        const marker = new window.AMap.Marker({
          position: [Number(v.lng), Number(v.lat)],
          title: v.vehicle_no,
          content: `<div class="fleet-marker" style="background:${markerColor(v)}">${v.vehicle_no || '车'}</div>`,
          offset: new window.AMap.Pixel(-18, -18),
        })
        marker.on('click', () => openVehicle(v))
        marker.setMap(amap)
        overlays.push(marker)
      })
    }
    if (showWarehousesOnMap.value) {
      warehouses.value.forEach((w) => {
        const lng = Number(w.lng)
        const lat = Number(w.lat)
        if (!Number.isFinite(lng) || !Number.isFinite(lat)) return
        const titleParts = [w.name]
        if (w.elitech_bound) {
          const t = w.elitech_temperature != null && w.elitech_temperature !== '' ? `${w.elitech_temperature}℃` : '—'
          const h = w.elitech_humidity != null && w.elitech_humidity !== '' ? `${w.elitech_humidity}%RH` : '—'
          titleParts.push(`${t} / ${h}`)
        }
        const marker = new window.AMap.Marker({
          position: [lng, lat],
          title: titleParts.filter(Boolean).join(' · '),
          content: warehouseMapMarkerHtml(w),
          offset: new window.AMap.Pixel(-22, -22),
        })
        marker.on('click', () => openWarehouse(w))
        marker.setMap(amap)
        overlays.push(marker)
      })
    }
    if (overlays.length) {
      amap.setFitView(overlays, false, [56, 56, 56, 56], 14)
    } else {
      amap.setZoomAndCenter(10, [116.4074, 39.9042])
    }
    amap.resize()
  } catch {
    mapError.value = '地图加载失败，请关闭 VPN 或检查高德 Key 后重试。'
  }
}

const renderDetailMap = async () => {
  if (!detailVisible.value || !detailMapRef.value || !selectedVehicle.value) return
  const key = import.meta.env.VITE_AMAP_KEY
  if (!key) return
  try {
    const securityJsCode = import.meta.env.VITE_AMAP_SECURITY_JS_CODE
    if (typeof window !== 'undefined' && securityJsCode) {
      window._AMapSecurityConfig = {
        ...(window._AMapSecurityConfig || {}),
        securityJsCode: String(securityJsCode),
      }
    }
    await AMapLoader.load({ key, version: '2.0' })
    destroyDetailMap()
    const v = selectedVehicle.value
    const fallbackLng = hasFleetCoords(v) ? Number(v.lng) : 116.4074
    const fallbackLat = hasFleetCoords(v) ? Number(v.lat) : 39.9042

    if (detailTab.value === 'live') {
      detailMap = new window.AMap.Map(detailMapRef.value, {
        zoom: 13,
        center: [fallbackLng, fallbackLat],
      })
      if (hasFleetCoords(v)) {
        const marker = new window.AMap.Marker({
          position: [Number(v.lng), Number(v.lat)],
          title: v.vehicle_no,
        })
        marker.setMap(detailMap)
        detailOverlays.push(marker)
      }
      detailMap.resize()
      return
    }

    const pts = historyPoints.value || []
    if (!pts.length) {
      detailMap = new window.AMap.Map(detailMapRef.value, {
        zoom: 12,
        center: [fallbackLng, fallbackLat],
      })
      detailMap.resize()
      return
    }

    const { path } = buildSortedHistoryPath(pts)
    if (path.length === 0) {
      detailMap = new window.AMap.Map(detailMapRef.value, {
        zoom: 12,
        center: [fallbackLng, fallbackLat],
      })
      detailMap.resize()
      return
    }
    if (path.length === 1) {
      detailMap = new window.AMap.Map(detailMapRef.value, { zoom: 14, center: path[0] })
      const marker = new window.AMap.Marker({ position: path[0], title: '轨迹点' })
      marker.setMap(detailMap)
      detailOverlays.push(marker)
      detailMap.resize()
      return
    }

    detailMap = new window.AMap.Map(detailMapRef.value, {})
    detailTrackPolyline = new window.AMap.Polyline({
      path,
      strokeColor: '#2563eb',
      strokeWeight: 4,
      lineJoin: 'round',
    })
    detailTrackPolyline.setMap(detailMap)
    detailHistoryStartMarker = new window.AMap.Marker({
      position: path[0],
      title: '起点',
      anchor: 'bottom-center',
    })
    detailHistoryEndMarker = new window.AMap.Marker({
      position: path[path.length - 1],
      title: '终点',
      anchor: 'bottom-center',
    })
    detailHistoryStartMarker.setMap(detailMap)
    detailHistoryEndMarker.setMap(detailMap)
    detailMap.setFitView([detailTrackPolyline], false, [48, 48, 48, 48])
    detailMap.resize()
  } catch {
    ElMessage.warning('详情地图加载失败，请关闭 VPN 或检查高德 Key')
  }
}

const loadVehicles = async ({ silent = false } = {}) => {
  if (!canLoadScope.value) {
    stopRefresh()
    return
  }
  loading.value = true
  try {
    const res = await vehicleApi.value()
    vehicles.value = Array.isArray(res?.vehicles) ? res.vehicles : []
    summary.value = res?.summary || summary.value
    lastRefreshedAt.value = res?.refreshed_at || new Date().toISOString()
    if (selectedVehicle.value) {
      const next = vehicles.value.find((v) => Number(v.id) === Number(selectedVehicle.value.id))
      if (next) selectedVehicle.value = next
    }
    await nextTick()
    await renderMap()
    if (detailVisible.value && detailTab.value === 'live') await renderDetailMap()
  } catch (err) {
    if (!silent) ElMessage.warning(err?.response?.data?.detail || '车辆监控数据加载失败')
  } finally {
    loading.value = false
  }
}

const stopRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

const startRefresh = () => {
  stopRefresh()
  if (document.hidden || !canLoadScope.value) return
  refreshTimer = setInterval(() => {
    loadVehicles({ silent: true })
    loadWarehouses({ silent: true })
  }, 15000)
}

const loadCameraStreams = async (camerasInput, subjectKey) => {
  const source = Array.isArray(camerasInput)
    ? camerasInput
    : (selectedVehicle.value?.cameras || [])
  const slotCount = Math.max(3, source.length)
  const cams = source.slice(0, slotCount)
  const keyPrefix = subjectKey || `v-${selectedVehicle.value?.id || ''}`
  cameraStates.value = Array.from({ length: slotCount }, (_, i) => ({
    key: `${keyPrefix}-${i}`,
    camera: cams[i] || null,
    loading: Boolean(cams[i]),
    url: '',
    mode: 'hls',
    accessToken: '',
    error: cams[i] ? '' : '未绑定摄像头',
  }))
  await nextTick()
  // 电池机同时唤醒易失败：有线并行，电池机按序间隔拉流
  for (let i = 0; i < cameraStates.value.length; i++) {
    const state = cameraStates.value[i]
    if (!state.camera) {
      state.loading = false
      continue
    }
    if (i > 0 && ys7MetaFromRow(state.camera).powerKind === 'battery') {
      await sleep(1500)
    }
    try {
      const res = await ys7Apis.value.liveUrlApi(state.camera.id)
      state.url = String(res?.hls || '')
      state.mode = String(res?.ys7_play_mode || 'hls')
      state.accessToken = String(res?.ys7_access_token || '')
      state.error = state.url ? '' : '未获取到直播地址'
    } catch (err) {
      state.error = err?.response?.data?.detail || '萤石视频加载失败，请关闭 VPN 后重试'
    } finally {
      state.loading = false
    }
  }
}

const openVehicle = async (vehicle) => {
  historyPb.destroy()
  selectedVehicle.value = vehicle
  detailVisible.value = true
  detailTab.value = 'live'
  historyRange.value = defaultHistoryRange()
  historyPoints.value = []
  await nextTick()
  await Promise.all([renderDetailMap(), loadCameraStreams()])
}

const openWarehouse = (warehouse) => {
  selectedWarehouse.value = warehouse
  warehouseDetailVisible.value = true
}

const loadWarehouses = async ({ silent = false } = {}) => {
  if (!canLoadScope.value) return
  try {
    const res = await warehouseApi.value()
    warehouses.value = Array.isArray(res?.warehouses) ? res.warehouses : []
    warehouseSummary.value = res?.summary || warehouseSummary.value
    await nextTick()
    await renderMap()
  } catch (err) {
    if (!silent) {
      // 仓库列表加载失败不阻塞车辆地图，仅在控制台留痕
      // eslint-disable-next-line no-console
      console.warn('[fleet-monitor] load warehouses failed', err?.response?.data?.detail || err?.message)
    }
  }
}

const applyMapLayerVisibility = async () => {
  await nextTick()
  await renderMap()
}

const toggleWarehousesOnMap = () => {
  showWarehousesOnMap.value = !showWarehousesOnMap.value
  applyMapLayerVisibility()
}

const toggleVehiclesOnMap = () => {
  showVehiclesOnMap.value = !showVehiclesOnMap.value
  applyMapLayerVisibility()
}

const loadHistory = async () => {
  if (!selectedVehicle.value) return
  const r = historyRange.value
  if (!Array.isArray(r) || r.length !== 2 || !r[0] || !r[1]) {
    ElMessage.warning('请选择时间范围')
    return
  }
  historyLoading.value = true
  try {
    const st = Math.floor(new Date(r[0]).getTime() / 1000)
    const et = Math.floor(new Date(r[1]).getTime() / 1000)
    const res = await historyApi.value(selectedVehicle.value.id, { start_time: st, end_time: et, force_demo: false })
    historyPoints.value = Array.isArray(res?.points) ? res.points : []
    historyPb.syncTrackPoints(historyPoints.value)
    if (!historyPoints.value.length) {
      ElMessage.info('该时段无轨迹点')
    } else {
      ElMessage.success(`已加载 ${historyPoints.value.length} 个轨迹点`)
    }
    await nextTick()
    await renderDetailMap()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '历史轨迹查询失败')
    historyPoints.value = []
  } finally {
    historyLoading.value = false
  }
}

watch(detailTab, async () => {
  if (detailTab.value === 'live') {
    historyPb.endPlayback()
  }
  await nextTick()
  await renderDetailMap()
})

watch(detailVisible, (visible) => {
  if (!visible) {
    destroyDetailMap()
    historyPb.destroy()
    selectedVehicle.value = null
    cameraStates.value = []
    historyPoints.value = []
  }
})

watch(
  historyPoints,
  async (pts) => {
    historyPb.syncTrackPoints(pts)
    if (!detailVisible.value || detailTab.value !== 'history') return
    await nextTick()
    await renderDetailMap()
  },
  { deep: true },
)

watch(warehouseDetailVisible, (visible) => {
  if (!visible) selectedWarehouse.value = null
})

const handleVisibility = () => {
  if (document.hidden || !canLoadScope.value) {
    stopRefresh()
    return
  }
  loadVehicles({ silent: true })
  loadWarehouses({ silent: true })
  startRefresh()
}

onMounted(async () => {
  if (!canLoadScope.value) return
  await loadVehicles()
  await loadWarehouses({ silent: true })
  startRefresh()
  document.addEventListener('visibilitychange', handleVisibility)
})

watch(
  () => userStore.role,
  () => {
    if (!canLoadScope.value) {
      stopRefresh()
      return
    }
    loadVehicles({ silent: true })
    loadWarehouses({ silent: true })
    startRefresh()
  },
)
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handleVisibility)
  stopRefresh()
  destroyMap()
  destroyDetailMap()
  historyPb.destroy()
})
</script>

<template>
  <el-card
    v-if="!isImmersive"
    shadow="never"
    class="fleet-card"
    v-loading="loading"
  >
    <template #header>
      <div class="fleet-head">
        <div>
          <div class="fleet-title">{{ title }}</div>
          <div class="fleet-sub">北斗车辆位置每 15 秒刷新 · 高德/萤石/北斗在 VPN 下失败属于正常降级</div>
        </div>
        <div class="fleet-actions">
          <span>上次刷新：{{ refreshText }}</span>
          <el-button size="small" @click="loadVehicles()">刷新</el-button>
        </div>
      </div>
    </template>

    <div class="fleet-grid">
      <div class="fleet-map-wrap" :style="{ height: `${height}px` }">
        <FleetMapLayerToggles
          :show-warehouses="showWarehousesOnMap"
          :show-vehicles="showVehiclesOnMap"
          @toggle-warehouses="toggleWarehousesOnMap"
          @toggle-vehicles="toggleVehiclesOnMap"
        />
        <div ref="mapRef" class="fleet-map" />
        <div v-if="mapError" class="fleet-map-fallback">{{ mapError }}</div>
      </div>
      <aside class="fleet-side">
        <div class="fleet-summary">
          <div><span>车辆</span><strong>{{ summary.total }}</strong></div>
          <div><span>在线</span><strong class="green">{{ summary.online }}</strong></div>
          <div><span>离线</span><strong>{{ summary.offline }}</strong></div>
          <div><span>未定位</span><strong class="amber">{{ summary.unlocated }}</strong></div>
          <div><span>仓库</span><strong>{{ warehouseSummary.total }}</strong></div>
          <div><span>摄像头</span><strong>{{ Number(summary.cameras || 0) + Number(warehouseSummary.cameras || 0) }}</strong></div>
        </div>
        <div class="vehicle-list">
          <button
            v-for="v in vehicles"
            :key="v.id"
            class="vehicle-row"
            type="button"
            @click="openVehicle(v)"
          >
            <span class="dot" :class="vehicleStatusClass(v)" />
            <span class="vehicle-main">
              <strong>{{ v.vehicle_no }}</strong>
              <small>{{ v.driver_name || '未填司机' }}<template v-if="scope === 'operation' || scope === 'monitor'"> · {{ v.delivery_name || '配送商' }}</template></small>
            </span>
            <span class="vehicle-state">{{ vehicleStatusText(v) }}</span>
          </button>
          <el-empty v-if="!vehicles.length" description="暂无车辆" :image-size="64" />
        </div>
        <div v-if="unlocatedVehicles.length" class="unlocated-box">
          <strong>未定位车辆</strong>
          <span v-for="v in unlocatedVehicles" :key="`unlocated-${v.id}`">
            {{ v.vehicle_no }}<small v-if="v.coordinate_hint">（{{ v.coordinate_hint }}）</small>
          </span>
        </div>
      </aside>
    </div>
  </el-card>

  <div v-else class="fleet-immersive" v-loading="loading" element-loading-background="rgba(7,15,33,0.55)">
    <FleetMapLayerToggles
      immersive
      :show-warehouses="showWarehousesOnMap"
      :show-vehicles="showVehiclesOnMap"
      @toggle-warehouses="toggleWarehousesOnMap"
      @toggle-vehicles="toggleVehiclesOnMap"
    />
    <div ref="mapRef" class="fleet-immersive-map" />
    <div v-if="mapError" class="fleet-immersive-fallback">{{ mapError }}</div>

    <aside class="fleet-immersive-side">
      <header class="fis-header">
        <div>
          <div class="fis-title">{{ title }}</div>
          <div class="fis-sub">每 15 秒刷新 · {{ refreshText }}</div>
        </div>
        <el-button size="small" type="primary" plain @click="loadVehicles()">刷新</el-button>
      </header>
      <div class="fis-summary">
        <div><span>车辆</span><strong>{{ summary.total }}</strong></div>
        <div><span>在线</span><strong class="green">{{ summary.online }}</strong></div>
        <div><span>离线</span><strong>{{ summary.offline }}</strong></div>
        <div><span>未定位</span><strong class="amber">{{ summary.unlocated }}</strong></div>
        <div><span>仓库</span><strong>{{ warehouseSummary.total }}</strong></div>
        <div><span>摄像头</span><strong>{{ Number(summary.cameras || 0) + Number(warehouseSummary.cameras || 0) }}</strong></div>
      </div>
      <div class="fis-vehicle-list">
        <button
          v-for="v in vehicles"
          :key="v.id"
          class="fis-vehicle-row"
          type="button"
          @click="openVehicle(v)"
        >
          <span class="dot" :class="vehicleStatusClass(v)" />
          <span class="vehicle-main">
            <strong>{{ v.vehicle_no }}</strong>
            <small>{{ v.driver_name || '未填司机' }}<template v-if="scope === 'operation' || scope === 'monitor'"> · {{ v.delivery_name || '配送商' }}</template></small>
          </span>
          <span class="fis-vehicle-state">{{ vehicleStatusText(v) }}</span>
        </button>
        <el-empty v-if="!vehicles.length" description="暂无车辆" :image-size="64" />
      </div>
      <div v-if="unlocatedVehicles.length" class="fis-unlocated">
        <strong>未定位车辆</strong>
        <span v-for="v in unlocatedVehicles" :key="`fis-unlocated-${v.id}`">
          {{ v.vehicle_no }}<small v-if="v.coordinate_hint">（{{ v.coordinate_hint }}）</small>
        </span>
      </div>
    </aside>
  </div>

  <el-drawer v-model="detailVisible" size="86%" destroy-on-close :title="`车辆监控 - ${selectedVehicle?.vehicle_no || ''}`">
    <div v-if="selectedVehicle" class="fleet-detail">
      <section class="detail-map-panel">
        <div class="detail-meta">
          <div><span>车牌</span><strong>{{ selectedVehicle.vehicle_no }}</strong></div>
          <div><span>司机</span><strong>{{ selectedVehicle.driver_name || '—' }}</strong></div>
          <div><span>定位</span><strong>{{ vehicleStatusText(selectedVehicle) }}</strong></div>
          <div><span>上报</span><strong>{{ selectedVehicle.reported_at || '—' }}</strong></div>
        </div>
        <el-tabs v-model="detailTab">
          <el-tab-pane label="实时位置" name="live">
            <div class="detail-actions">
              <el-button size="small" @click="loadVehicles()">刷新位置</el-button>
              <span>坐标：{{ selectedVehicle.lng || '—' }}, {{ selectedVehicle.lat || '—' }}</span>
              <span>速度：{{ selectedVehicle.speed ?? '—' }}</span>
              <span>方向：{{ selectedVehicle.course || '—' }}</span>
            </div>
          </el-tab-pane>
          <el-tab-pane label="历史轨迹" name="history">
            <div class="history-toolbar">
              <el-date-picker
                v-model="historyRange"
                type="datetimerange"
                range-separator="至"
                start-placeholder="开始时间"
                end-placeholder="结束时间"
                style="width: min(100%, 520px)"
              />
              <el-button type="primary" :loading="historyLoading" @click="loadHistory">查询轨迹</el-button>
              <span v-if="historyPoints.length">共 {{ historyPoints.length }} 点</span>
            </div>
            <p v-if="historyPoints.length >= 2" class="history-hint">
              支持播放/暂停/继续、停止、复位、从新播放、倍速、循环、地图跟随与渐进轨迹线。
            </p>
            <div v-if="historyPoints.length >= 2" class="history-playback-bar">
              <el-button size="small" type="primary" plain :disabled="hpPlaying" @click="onDetailHistoryPlay">播放</el-button>
              <el-button size="small" :disabled="!hpPlaying" @click="historyPb.pause">暂停</el-button>
              <el-button size="small" :disabled="!hpPaused" @click="historyPb.resume">继续</el-button>
              <el-button size="small" :disabled="hpPlaying" @click="onDetailHistoryRestart">从新播放</el-button>
              <el-button size="small" @click="historyPb.endPlayback">停止</el-button>
              <el-button size="small" @click="historyPb.resetToStart(getDetailHistoryMap)">复位</el-button>
              <span class="playback-speed-label">倍速</span>
              <el-select v-model="historyPb.playSpeed" size="small" class="playback-speed-select" :disabled="hpPlaying">
                <el-option :value="0.5" label="0.5×" />
                <el-option :value="1" label="1×" />
                <el-option :value="2" label="2×" />
                <el-option :value="4" label="4×" />
                <el-option :value="8" label="8×" />
              </el-select>
              <el-checkbox v-model="historyPb.followMap">地图跟随</el-checkbox>
              <el-checkbox v-model="historyPb.loopPlay">循环播放</el-checkbox>
              <el-checkbox v-model="historyPb.progressiveTrail">渐进轨迹线</el-checkbox>
            </div>
            <div v-if="historyPoints.length >= 2" class="history-progress-row">
              <span class="playback-speed-label">进度</span>
              <el-slider
                class="history-progress-slider"
                :model-value="historyPb.progressPercent"
                :disabled="!hpCanScrub"
                :min="0"
                :max="100"
                :step="0.1"
                :format-tooltip="(v) => `${Number(v).toFixed(1)}%`"
                @update:model-value="(v) => historyPb.seekPercent(v, getDetailHistoryMap)"
              />
            </div>
          </el-tab-pane>
        </el-tabs>
        <div ref="detailMapRef" class="detail-map" />
      </section>

      <aside class="camera-panel">
        <div class="camera-title">车辆监控画面</div>
        <div v-for="(state, idx) in cameraStates" :key="state.key" class="camera-box">
          <Ys7CameraLiveWithPtz
            v-if="state.camera"
            :camera="state.camera"
            :url="state.url"
            :mode="state.mode"
            :access-token="state.accessToken"
            :loading="state.loading"
            :error="state.error"
            :ptz-control="ys7Apis.ptzControl"
            :ez-dom-id="`fleet-ez-${scope}-${state.camera.id}`"
            layout="side"
            ptz-theme="dark"
            compact-ptz
            :start-delay-ms="idx * (ys7MetaFromRow(state.camera).powerKind === 'battery' ? 1500 : 0)"
          />
          <div v-else class="camera-empty">{{ state.error || `摄像头 ${idx + 1} 未绑定` }}</div>
        </div>
      </aside>
    </div>
  </el-drawer>

  <WarehouseCameraLiveDrawer
    v-model="warehouseDetailVisible"
    :warehouse="selectedWarehouse"
    :scope="scope"
    player-key="fleet"
    @elitech-changed="loadWarehouses({ silent: true })"
  />
</template>

<style scoped>
.fleet-card {
  border-radius: 14px;
  border: 1px solid #e2e8f0;
}

.fleet-head,
.fleet-actions,
.detail-meta,
.detail-actions,
.history-toolbar,
.camera-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.fleet-head {
  justify-content: space-between;
}

.fleet-title {
  font-size: 17px;
  font-weight: 700;
  color: #0f172a;
}

.fleet-sub,
.fleet-actions,
.detail-actions,
.camera-meta span {
  font-size: 12px;
  color: #64748b;
}

.fleet-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 14px;
}

.fleet-map-wrap {
  position: relative;
  min-height: 420px;
}

.fleet-map,
.detail-map {
  width: 100%;
  height: 100%;
  min-height: 420px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
  overflow: hidden;
}

.fleet-map-fallback {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  border-radius: 10px;
  background: rgba(248, 250, 252, 0.92);
  color: #475569;
}

.fleet-side {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.fleet-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.fleet-summary div,
.detail-meta div {
  padding: 9px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
}

.fleet-summary span,
.detail-meta span {
  display: block;
  font-size: 12px;
  color: #64748b;
}

.fleet-summary strong,
.detail-meta strong {
  color: #0f172a;
}

.green {
  color: #15803d !important;
}

.amber {
  color: #b45309 !important;
}

.vehicle-list {
  max-height: 340px;
  overflow: auto;
}

.vehicle-row {
  width: 100%;
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 9px 8px;
  border: 0;
  border-bottom: 1px solid #e2e8f0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.vehicle-row:hover {
  background: #f8fafc;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
}

.status-online {
  background: #16a34a;
}

.status-offline {
  background: #64748b;
}

.status-unlocated {
  background: #f59e0b;
}

.vehicle-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.vehicle-main strong,
.vehicle-main small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vehicle-main small,
.vehicle-state,
.unlocated-box {
  color: #64748b;
  font-size: 12px;
}

.unlocated-box {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px;
  border-radius: 8px;
  background: #fffbeb;
  color: #92400e;
  line-height: 1.5;
}

.unlocated-box small {
  color: #b45309;
}

.fleet-detail {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
}

.detail-map-panel,
.camera-panel {
  min-width: 0;
}

.detail-map {
  height: 420px;
}

.detail-meta {
  margin-bottom: 10px;
}

.detail-actions,
.history-toolbar {
  margin-top: 10px;
}

.history-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.45;
}

.history-playback-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.playback-speed-label {
  font-size: 12px;
  color: #64748b;
}

.playback-speed-select {
  width: 96px;
}

.history-progress-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
}

.history-progress-slider {
  flex: 1;
  min-width: 120px;
}

.camera-title {
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 10px;
}

.camera-box {
  min-height: 170px;
  margin-bottom: 12px;
  padding: 10px;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  background: #0f172a;
  color: #fff;
}

.camera-empty {
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #cbd5e1;
  text-align: center;
}

.camera-video,
.camera-ez {
  width: 100%;
  aspect-ratio: 16 / 9;
  min-height: 130px;
  border-radius: 8px;
  background: #020617;
}

:global(.fleet-marker) {
  min-width: 36px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 8px;
  border-radius: 999px;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.25);
  white-space: nowrap;
}

:global(.warehouse-marker) {
  position: relative;
  min-width: 44px;
  display: inline-flex;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
  padding: 4px 10px 4px 4px;
  border-radius: 8px;
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  border: 1px solid rgba(56, 189, 248, 0.55);
  color: #e2e8f0;
  font-size: 12px;
  font-weight: 600;
  box-shadow: 0 6px 18px rgba(2, 6, 23, 0.55);
  white-space: nowrap;
  cursor: pointer;
}
:global(.warehouse-marker-row) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
:global(.warehouse-marker-elitech) {
  display: block;
  padding-left: 28px;
  font-size: 10px;
  font-weight: 500;
  font-style: normal;
  color: #7dd3fc;
  line-height: 1.2;
}
:global(.warehouse-marker i) {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  background: rgba(56, 189, 248, 0.18);
  color: #38bdf8;
  font-style: normal;
  font-size: 13px;
  font-weight: 700;
}
:global(.warehouse-marker b) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: #ef4444;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  position: absolute;
  top: -8px;
  right: -8px;
}
:global(.warehouse-marker:hover) {
  transform: translateY(-1px);
  transition: transform 120ms ease;
}

@media (max-width: 1200px) {
  .fleet-grid,
  .fleet-detail {
    grid-template-columns: 1fr;
  }
}

/* ===== Immersive variant (监管端 北京全域) ===== */
.fleet-immersive {
  position: absolute;
  inset: 0;
  background: #050b1a;
  overflow: hidden;
}

.fleet-immersive-map {
  position: absolute;
  inset: 0;
}

.fleet-immersive-fallback {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: #cbd5e1;
  background: rgba(7, 15, 33, 0.72);
  text-align: center;
  z-index: 2;
}

.fleet-immersive-side {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 320px;
  max-height: calc(100% - 40px);
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: 14px;
  border: 1px solid rgba(95, 248, 255, 0.18);
  background: rgba(8, 18, 38, 0.78);
  backdrop-filter: blur(14px) saturate(140%);
  -webkit-backdrop-filter: blur(14px) saturate(140%);
  color: #e2e8f0;
  box-shadow: 0 12px 36px rgba(2, 6, 23, 0.55);
  z-index: 5;
}

.fis-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.fis-title {
  font-size: 15px;
  font-weight: 700;
  color: #f8fafc;
}

.fis-sub {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 2px;
}

.fis-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.fis-summary div {
  padding: 8px 10px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.55);
}

.fis-summary span {
  display: block;
  font-size: 11px;
  color: #94a3b8;
}

.fis-summary strong {
  font-size: 16px;
  color: #f8fafc;
}

.fis-summary strong.green {
  color: #4ade80 !important;
}

.fis-summary strong.amber {
  color: #fbbf24 !important;
}

.fis-vehicle-list {
  flex: 1;
  min-height: 80px;
  max-height: 320px;
  overflow: auto;
  border-top: 1px solid rgba(148, 163, 184, 0.16);
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
}

.fis-vehicle-row {
  width: 100%;
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 9px 4px;
  border: 0;
  border-bottom: 1px solid rgba(148, 163, 184, 0.10);
  background: transparent;
  color: #e2e8f0;
  text-align: left;
  cursor: pointer;
}

.fis-vehicle-row:hover {
  background: rgba(56, 189, 248, 0.10);
}

.fis-vehicle-row .vehicle-main strong {
  color: #f8fafc;
  font-size: 13px;
}

.fis-vehicle-row .vehicle-main small {
  color: #94a3b8;
  font-size: 11px;
}

.fis-vehicle-state {
  color: #cbd5e1;
  font-size: 11px;
}

.fis-unlocated {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px;
  border-radius: 8px;
  background: rgba(245, 158, 11, 0.12);
  color: #fbbf24;
  line-height: 1.5;
  font-size: 12px;
}

.fis-unlocated small {
  color: #fcd34d;
}
</style>
