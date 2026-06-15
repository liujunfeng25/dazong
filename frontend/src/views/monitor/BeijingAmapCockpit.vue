<script setup>
import { computed } from 'vue'
import FleetMonitorMapCard from '../../components/FleetMonitorMapCard.vue'

const resolveAmapMapStyle = () => {
  const raw = import.meta.env.VITE_AMAP_MAP_STYLE || import.meta.env.VITE_AMAP_MAP_STYLE_ID
  if (!raw) return 'amap://styles/dark'
  const s = String(raw).trim()
  if (s.startsWith('amap://')) return s
  return `amap://styles/${s}`
}

const mapInit = computed(() => ({
  zoom: 10.2,
  center: [116.407387, 39.904179],
  pitch: 54,
  rotation: -12,
  viewMode: '3D',
  mapStyle: resolveAmapMapStyle(),
  skyColor: '#0a1428',
  showLabel: true,
  showIndoorMap: false,
  resizeEnable: true,
  features: ['bg', 'road', 'building'],
}))
</script>

<template>
  <FleetMonitorMapCard
    scope="monitor"
    variant="immersive"
    title="北京全域车辆监控"
    :map-init="mapInit"
  />
</template>
