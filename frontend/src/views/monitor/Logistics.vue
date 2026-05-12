<script setup>
import { onMounted, ref } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import { monitorLogisticsApi } from '../../api/monitor'

const mapRef = ref(null)
const list = ref([])
const keyword = ref('')
const mapInstance = ref(null)
const markers = new Map()
const activeOrderId = ref(null)
const loading = ref(false)

const initMap = async () => {
  const key = import.meta.env.VITE_AMAP_KEY
  if (!key || !mapRef.value) return
  await AMapLoader.load({ key, version: '2.0' })
  mapInstance.value = new window.AMap.Map(mapRef.value, {
    zoom: 10,
    center: [116.4, 39.9],
  })
}

const renderMarkers = () => {
  if (!mapInstance.value) return
  list.value.forEach((item) => {
    const lat = item.current_lat || 39.9
    const lng = item.current_lng || 116.4
    const key = String(item.order_id)
    const marker = markers.get(key) || new window.AMap.Marker({ position: [lng, lat] })
    marker.setPosition([lng, lat])
    if (!markers.has(key)) mapInstance.value.add(marker)
    markers.set(key, marker)
  })
}

const load = async () => {
  loading.value = true
  try {
    const rows = await monitorLogisticsApi()
    const k = keyword.value.trim()
    list.value = k ? rows.filter((i) => String(i.order_id).includes(k) || String(i.status || '').includes(k)) : rows
    renderMarkers()
  } finally {
    loading.value = false
  }
}

const focusOrder = (item) => {
  if (!mapInstance.value) return
  activeOrderId.value = item.order_id
  const key = String(item.order_id)
  const marker = markers.get(key)
  if (marker) {
    const pos = marker.getPosition()
    mapInstance.value.setZoomAndCenter(12, [pos.lng, pos.lat])
    marker.setAnimation('AMAP_ANIMATION_BOUNCE')
    setTimeout(() => marker.setAnimation(null), 1500)
  }
}

onMounted(async () => {
  await initMap()
  await load()
})
</script>

<template>
  <div class="h-[calc(100vh-130px)] grid grid-cols-12 gap-3">
    <el-card v-loading="loading" class="col-span-4 overflow-auto">
      <div class="toolbar mb-2">
        <div class="font-semibold">在途订单</div>
        <el-button size="small" @click="load">刷新</el-button>
      </div>
      <el-input v-model="keyword" placeholder="按订单号/状态搜索" class="mb-2" clearable @input="load" />
      <div
        v-for="item in list"
        :key="item.id"
        class="py-2 border-b cursor-pointer"
        :class="activeOrderId === item.order_id ? 'text-blue-500 font-semibold' : ''"
        @click="focusOrder(item)"
      >
        <div class="row-main">{{ item.order_id }}</div>
        <div class="row-sub">
          <el-tag size="small" :type="item.status === '已送达' ? 'success' : 'warning'">{{ item.status }}</el-tag>
        </div>
      </div>
    </el-card>
    <el-card class="col-span-8"><div ref="mapRef" class="h-[calc(100vh-180px)] rounded-xl overflow-hidden" /></el-card>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.row-main {
  font-weight: 600;
}

.row-sub {
  margin-top: 4px;
}
</style>
