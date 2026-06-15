<script setup>
import AMapLoader from '@amap/amap-jsapi-loader'
import { ElMessage } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { orderLogisticsTrackingApi } from '../api/orders'
import { formatChinaDateTime } from '../utils/datetime'

const props = defineProps({
  tracking: { type: Object, default: () => ({}) },
  title: { type: String, default: '在途物流' },
  orderId: { type: [Number, String], default: null },
  autoRefresh: { type: Boolean, default: true },
  refreshIntervalMs: { type: Number, default: 15000 },
})

const mapRef = ref(null)
const mapError = ref('')
const localTracking = ref(props.tracking || {})
const refreshing = ref(false)
const lastRefreshedAt = ref('')
let amap = null
let overlays = []
let refreshTimer = null

const currentTracking = computed(() => localTracking.value || {})
const modeText = computed(() => {
  const map = {
    pre_departure: '未发车',
    in_transit: '配送途中',
    arrived: '已送达',
    unavailable: '不可追踪',
  }
  return map[currentTracking.value?.mode] || '履约中'
})

const points = computed(() =>
  (currentTracking.value?.points || []).filter((p) => Number.isFinite(Number(p.lng)) && Number.isFinite(Number(p.lat))),
)
const hasMapPoints = computed(() => points.value.length > 0)
const vehicle = computed(() => currentTracking.value?.vehicle || {})
const delivery = computed(() => currentTracking.value?.delivery || {})
const centerPoint = computed(() => currentTracking.value?.map_center || points.value[0] || null)
const canRefresh = computed(() => Boolean(props.orderId) && currentTracking.value?.mode === 'in_transit')
const shouldAutoRefresh = computed(
  () =>
    Boolean(props.autoRefresh) &&
    canRefresh.value &&
    !document.hidden,
)
const refreshStatusText = computed(() => {
  if (!lastRefreshedAt.value) return '随页面加载'
  return formatChinaDateTime(lastRefreshedAt.value)
})
const phaseHintText = computed(() => {
  const mode = currentTracking.value?.mode
  if (mode === 'in_transit') return `自动刷新中 · 上次刷新：${refreshStatusText.value}`
  if (mode === 'arrived') return '已送达，位置以客户收货点为准'
  if (mode === 'pre_departure') return '未发车，位置以配送商为准'
  if (mode === 'unavailable') return '该订单不可追踪'
  return '当前位置随订单履约阶段展示'
})

const pointLabel = (p) => {
  if (p.type === 'vehicle') return '车辆'
  if (p.type === 'customer_destination') return '收货点'
  return '配送商'
}

const clearOverlays = () => {
  if (amap) {
    overlays.forEach((o) => {
      try {
        amap.remove(o)
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
  if (!mapRef.value || !hasMapPoints.value) {
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
    const center = centerPoint.value || points.value[0]
    if (!amap) {
      amap = new window.AMap.Map(mapRef.value, {
        zoom: points.value.length > 1 ? 12 : 15,
        center: [Number(center.lng), Number(center.lat)],
      })
    } else {
      amap.setCenter([Number(center.lng), Number(center.lat)])
    }
    clearOverlays()
    points.value.forEach((p) => {
      const marker = new window.AMap.Marker({
        position: [Number(p.lng), Number(p.lat)],
        title: p.label || pointLabel(p),
        label: {
          content: `<div class="order-map-label">${pointLabel(p)} · ${p.label || ''}</div>`,
          direction: 'top',
        },
        offset: new window.AMap.Pixel(-13, -30),
      })
      marker.setMap(amap)
      overlays.push(marker)
    })
    if (overlays.length > 1) {
      amap.setFitView(overlays, false, [40, 40, 40, 40], 16)
    }
    amap.resize()
  } catch {
    mapError.value = '地图加载失败，请确认网络、高德 Key 或关闭 VPN 后重试。'
  }
}

const stopAutoRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

const startAutoRefresh = () => {
  stopAutoRefresh()
  if (!shouldAutoRefresh.value) return
  const interval = Math.max(5000, Number(props.refreshIntervalMs || 15000))
  refreshTimer = setInterval(() => {
    refreshTracking({ silent: true })
  }, interval)
}

const refreshTracking = async ({ silent = false } = {}) => {
  if (!canRefresh.value || refreshing.value) return
  refreshing.value = true
  try {
    const resp = await orderLogisticsTrackingApi(props.orderId)
    localTracking.value = resp?.logistics_tracking || {}
    lastRefreshedAt.value = resp?.refreshed_at || new Date().toISOString()
    await nextTick()
    await renderMap()
  } catch {
    if (!silent) ElMessage.warning('定位刷新失败，请稍后重试')
  } finally {
    refreshing.value = false
    startAutoRefresh()
  }
}

const handleVisibilityChange = () => {
  if (document.hidden) {
    stopAutoRefresh()
    return
  }
  if (shouldAutoRefresh.value) {
    refreshTracking({ silent: true })
  } else {
    startAutoRefresh()
  }
}

watch(
  () => props.tracking,
  (val) => {
    localTracking.value = val || {}
    if (!lastRefreshedAt.value) lastRefreshedAt.value = new Date().toISOString()
  },
  { immediate: true },
)

watch(
  () => props.orderId,
  () => {
    lastRefreshedAt.value = ''
    stopAutoRefresh()
  },
)

watch(
  () => JSON.stringify(currentTracking.value || {}),
  async () => {
    await nextTick()
    await renderMap()
  },
  { immediate: true },
)

watch(
  () => [props.orderId, props.autoRefresh, currentTracking.value?.mode],
  startAutoRefresh,
  { immediate: true },
)

onMounted(() => document.addEventListener('visibilitychange', handleVisibilityChange))
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  stopAutoRefresh()
  destroyMap()
})
</script>

<template>
  <el-card shadow="never" class="order-logistics-card">
    <template #header>
      <div class="ol-head">
        <div class="ol-head-title">
          <span class="font-semibold">{{ title }}</span>
          <el-tag
            size="small"
            :type="currentTracking?.mode === 'in_transit' ? 'primary' : currentTracking?.mode === 'arrived' ? 'success' : 'warning'"
          >
            {{ modeText }}
          </el-tag>
        </div>
        <div class="ol-actions">
          <span class="ol-refresh-time">{{ phaseHintText }}</span>
          <el-button v-if="canRefresh" size="small" :loading="refreshing" @click="refreshTracking()">
            刷新
          </el-button>
        </div>
      </div>
    </template>

    <div class="ol-status">
      <div>
        <div class="ol-title">{{ currentTracking?.status_label || '暂无物流状态' }}</div>
        <div class="ol-hint">{{ currentTracking?.status_hint || '系统正在等待下一步履约动作。' }}</div>
      </div>
      <div v-if="vehicle.vehicle_no || vehicle.driver_name" class="ol-vehicle">
        <span v-if="vehicle.vehicle_no">{{ vehicle.vehicle_no }}</span>
        <span v-if="vehicle.driver_name">{{ vehicle.driver_name }}</span>
      </div>
    </div>

    <div v-if="hasMapPoints" class="ol-map-wrap">
      <div ref="mapRef" class="ol-map" />
      <div v-if="mapError" class="ol-map-fallback">{{ mapError }}</div>
    </div>
    <el-empty v-else description="暂无可用于地图展示的坐标" :image-size="64" />

    <div class="ol-meta">
      <div v-if="delivery.route_no"><span>车次</span><strong>{{ delivery.route_no }}</strong></div>
      <div v-if="delivery.departed_at"><span>发车</span><strong>{{ formatChinaDateTime(delivery.departed_at) }}</strong></div>
      <div v-if="delivery.arrived_at"><span>到达</span><strong>{{ formatChinaDateTime(delivery.arrived_at) }}</strong></div>
      <div v-if="vehicle.online_status"><span>定位</span><strong>{{ vehicle.online_status === 'online' ? '在线' : '离线' }}</strong></div>
      <div v-if="vehicle.reported_at"><span>上报</span><strong>{{ vehicle.reported_at }}</strong></div>
    </div>
  </el-card>
</template>

<style scoped>
.order-logistics-card {
  overflow: hidden;
}
.ol-head,
.ol-status,
.ol-vehicle,
.ol-meta {
  display: flex;
  align-items: center;
}
.ol-head,
.ol-status {
  justify-content: space-between;
  gap: 12px;
}
.ol-head-title,
.ol-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.ol-refresh-time {
  font-size: 12px;
  color: #64748b;
}
.ol-title {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}
.ol-hint {
  margin-top: 4px;
  font-size: 13px;
  color: #64748b;
}
.ol-vehicle {
  gap: 8px;
  flex-wrap: wrap;
  font-weight: 600;
  color: #1d4ed8;
}
.ol-map-wrap {
  position: relative;
  margin-top: 14px;
}
.ol-map {
  width: 100%;
  height: 260px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
  background: #f8fafc;
}
.ol-map-fallback {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18px;
  border-radius: 8px;
  background: rgba(248, 250, 252, 0.9);
  color: #475569;
  text-align: center;
}
.ol-meta {
  margin-top: 12px;
  gap: 10px;
  flex-wrap: wrap;
}
.ol-meta > div {
  display: inline-flex;
  gap: 5px;
  padding: 6px 9px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  font-size: 12px;
}
.ol-meta span {
  color: #64748b;
}
.ol-meta strong {
  color: #0f172a;
}
:global(.order-map-label) {
  padding: 3px 7px;
  border-radius: 999px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.18);
  color: #0f172a;
  font-size: 12px;
}
</style>
