<script setup>
defineProps({
  /** 监管端北京全域等深色全屏地图 */
  immersive: { type: Boolean, default: false },
  showWarehouses: { type: Boolean, default: true },
  showVehicles: { type: Boolean, default: true },
})

defineEmits(['toggle-warehouses', 'toggle-vehicles'])
</script>

<template>
  <div
    class="fleet-map-layer-toggles"
    :class="{ 'fleet-map-layer-toggles--immersive': immersive }"
    role="group"
    aria-label="地图图层筛选"
  >
    <button
      type="button"
      class="map-layer-btn"
      :class="{ 'map-layer-btn--on': showWarehouses }"
      @click="$emit('toggle-warehouses')"
    >
      {{ showWarehouses ? '隐藏仓库' : '显示仓库' }}
    </button>
    <button
      type="button"
      class="map-layer-btn"
      :class="{ 'map-layer-btn--on': showVehicles }"
      @click="$emit('toggle-vehicles')"
    >
      {{ showVehicles ? '隐藏车辆' : '显示车辆' }}
    </button>
  </div>
</template>

<style scoped>
.fleet-map-layer-toggles {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 10;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.12);
}

.map-layer-btn {
  margin: 0;
  min-width: 88px;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
  cursor: pointer;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease,
    box-shadow 0.15s ease;
}

.map-layer-btn:hover {
  border-color: #94a3b8;
  color: #0f172a;
  background: #f8fafc;
}

.map-layer-btn--on {
  border-color: #3b82f6;
  background: #eff6ff;
  color: #1d4ed8;
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.15);
}

/* 监管端北京全域：与 fleet-immersive-side 玻璃拟态一致 */
.fleet-map-layer-toggles--immersive {
  top: 20px;
  /* 避开右侧 320px 悬浮面板 */
  right: calc(320px + 20px + 16px);
  padding: 10px;
  border-radius: 12px;
  border: 1px solid rgba(95, 248, 255, 0.28);
  background: rgba(8, 18, 38, 0.82);
  backdrop-filter: blur(14px) saturate(140%);
  -webkit-backdrop-filter: blur(14px) saturate(140%);
  box-shadow:
    0 0 24px rgba(56, 189, 248, 0.12),
    0 12px 32px rgba(2, 6, 23, 0.45);
}

.fleet-map-layer-toggles--immersive .map-layer-btn {
  min-width: 92px;
  border-color: rgba(148, 163, 184, 0.35);
  background: rgba(15, 23, 42, 0.72);
  color: #cbd5e1;
}

.fleet-map-layer-toggles--immersive .map-layer-btn:hover {
  border-color: rgba(56, 189, 248, 0.55);
  background: rgba(56, 189, 248, 0.12);
  color: #e0f2fe;
}

.fleet-map-layer-toggles--immersive .map-layer-btn--on {
  border-color: rgba(95, 248, 255, 0.75);
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.35) 0%, rgba(56, 189, 248, 0.18) 100%);
  color: #f0fdff;
  box-shadow:
    0 0 12px rgba(56, 189, 248, 0.35),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

@media (max-width: 1100px) {
  .fleet-map-layer-toggles--immersive {
    right: 12px;
    top: auto;
    bottom: 88px;
  }
}
</style>
