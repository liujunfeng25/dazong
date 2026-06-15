<script setup>
import { computed, ref, watch } from 'vue'
import {
  getWarehouseElitechApi,
  getWarehouseElitechRealtimeApi,
} from '../api/delivery'
import { useYs7CameraApis } from '../composables/useYs7CameraApis'
import WarehouseElitechBrief from './WarehouseElitechBrief.vue'
import WarehouseElitechDrawer from './WarehouseElitechDrawer.vue'
import Ys7CameraLiveWithPtz from './Ys7CameraLiveWithPtz.vue'

const batteryStreamDelay = (index) => {
  if (index <= 0) return 0
  return index * 1500
}

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  warehouse: { type: Object, default: null },
  scope: { type: String, default: 'delivery' },
  playerKey: { type: String, default: 'warehouse-live' },
})

const emit = defineEmits(['update:modelValue', 'elitech-changed'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const ys7Apis = computed(() => useYs7CameraApis(props.scope, 'fleet'))
const elitechVisible = ref(false)
const elitechLoading = ref(false)
const elitechFetched = ref(null)
const canManageElitech = computed(() => props.scope === 'delivery')

const warehouseForElitech = computed(() => {
  const base = props.warehouse || {}
  const extra = elitechFetched.value || {}
  return {
    ...base,
    ...extra,
    elitech_bound: Boolean(
      extra.elitech_bound ?? base.elitech_bound ?? base.elitech_sn ?? extra.elitech_sn,
    ),
  }
})

const slotCameras = computed(() => {
  const source = Array.isArray(props.warehouse?.cameras) ? props.warehouse.cameras : []
  const slotCount = Math.max(3, source.length)
  return Array.from({ length: slotCount }, (_, i) => source[i] || null)
})

const loadElitechBrief = async () => {
  const id = Number(props.warehouse?.id)
  if (!id || props.scope !== 'delivery') return
  elitechLoading.value = true
  try {
    const binding = await getWarehouseElitechApi(id)
    if (!binding?.elitech_sn) {
      elitechFetched.value = {
        elitech_bound: false,
        elitech_sn: '',
        elitech_device_name: '',
        elitech_temperature: '',
        elitech_humidity: '',
        elitech_online: null,
      }
      return
    }
    let temperature = ''
    let humidity = ''
    let online = null
    try {
      const res = await getWarehouseElitechRealtimeApi(id)
      const rt = res?.data || {}
      temperature = rt.temperature != null ? String(rt.temperature) : ''
      humidity = rt.humidity != null ? String(rt.humidity) : ''
      online = rt.status != null ? Number(rt.status) === 0 : null
    } catch {
      // 实时接口失败仍展示已绑定状态
    }
    elitechFetched.value = {
      elitech_bound: true,
      elitech_sn: binding.elitech_sn,
      elitech_device_name: binding.device_name || '',
      elitech_temperature: temperature,
      elitech_humidity: humidity,
      elitech_online: online,
    }
  } catch {
    elitechFetched.value = null
  } finally {
    elitechLoading.value = false
  }
}

watch(visible, (open) => {
  if (!open) {
    elitechVisible.value = false
    elitechFetched.value = null
    return
  }
  if (props.scope === 'delivery') {
    loadElitechBrief()
  }
})

const onElitechChanged = () => {
  emit('elitech-changed')
  if (props.scope === 'delivery') loadElitechBrief()
}
</script>

<template>
  <el-drawer
    v-model="visible"
    size="60%"
    destroy-on-close
    :title="`仓库 - ${warehouse?.name || ''}`"
  >
    <div v-if="warehouse" class="warehouse-detail">
      <section class="warehouse-meta">
        <div><span>名称</span><strong>{{ warehouse.name }}</strong></div>
        <div v-if="warehouse.delivery_name"><span>归属</span><strong>{{ warehouse.delivery_name }}</strong></div>
        <div><span>地址</span><strong>{{ warehouse.address || '—' }}</strong></div>
        <div v-if="Number.isFinite(Number(warehouse.lng)) && Number.isFinite(Number(warehouse.lat))">
          <span>坐标</span><strong>{{ Number(warehouse.lng).toFixed(6) }}, {{ Number(warehouse.lat).toFixed(6) }}</strong>
        </div>
        <div><span>摄像头</span><strong>{{ (warehouse.cameras || []).length }}</strong></div>
      </section>

      <section v-loading="elitechLoading" class="warehouse-elitech-panel">
        <div class="warehouse-elitech-head">
          <span class="warehouse-elitech-title">温湿度</span>
          <el-button
            v-if="canManageElitech"
            size="small"
            type="warning"
            plain
            @click="elitechVisible = true"
          >
            温湿度详情
          </el-button>
        </div>
        <WarehouseElitechBrief :warehouse="warehouseForElitech" variant="card" />
      </section>

      <aside class="camera-panel">
        <div class="camera-title">仓库监控画面</div>
        <div
          v-for="(cam, idx) in slotCameras"
          :key="`${playerKey}-w-${warehouse.id}-${idx}`"
          class="camera-box"
        >
          <Ys7CameraLiveWithPtz
            v-if="cam"
            :camera="cam"
            :live-url-api="ys7Apis.liveUrlApi"
            :ptz-control="ys7Apis.ptzControl"
            :ez-dom-id="`${playerKey}-ez-${scope}-w-${cam.id}`"
            layout="side"
            ptz-theme="dark"
            compact-ptz
            :start-delay-ms="batteryStreamDelay(idx)"
          />
          <div v-else class="camera-empty">摄像头 {{ idx + 1 }} · 未绑定</div>
        </div>
        <el-empty
          v-if="!(warehouse.cameras || []).length"
          description="该仓库未绑定摄像头"
          :image-size="64"
        />
      </aside>
    </div>
  </el-drawer>

  <WarehouseElitechDrawer
    v-if="canManageElitech"
    v-model="elitechVisible"
    :warehouse="warehouseForElitech"
    @changed="onElitechChanged"
  />
</template>

<style scoped>
.warehouse-detail {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

.warehouse-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}

.warehouse-meta div {
  padding: 9px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
}

.warehouse-meta span {
  display: block;
  font-size: 12px;
  color: #64748b;
}

.warehouse-meta strong {
  color: #0f172a;
}

.warehouse-elitech-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 72px;
}

.warehouse-elitech-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.warehouse-elitech-title {
  font-weight: 700;
  color: #0f172a;
}

.camera-panel {
  min-width: 0;
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
  font-size: 13px;
}
</style>
