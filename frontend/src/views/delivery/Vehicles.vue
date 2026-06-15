<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import { ElMessage } from 'element-plus'
import {
  createDeliveryVehicleApi,
  createVehicleBindingApi,
  getBeijingVehicleRestrictionApi,
  getVehicleLocationApi,
  listDeliveryDevicesApi,
  listDeliveryVehiclesApi,
  listVehicleBindingsApi,
  postVehicleBeidouHistoryTrackApi,
  updateDeliveryVehicleApi,
  deleteVehicleBindingApi,
} from '../../api/delivery'
import { vehicleLimitReason as vehicleLimitReasonUtil, vehicleLimitTag as vehicleLimitTagUtil } from '../../utils/beijingVehicleLimit'
import { buildSortedHistoryPath } from '../../utils/amapPathPlayback'
import { useBeidouHistoryPlayback } from '../../composables/useBeidouHistoryPlayback'
import { useYs7CameraApis } from '../../composables/useYs7CameraApis'
import Ys7CameraLiveDialog from '../../components/Ys7CameraLiveDialog.vue'
import { ys7BatteryFromRow, ys7BatteryTagType, ys7SupportsPtz } from '../../utils/ys7DeviceMeta'

const { liveUrlApi, ptzControl } = useYs7CameraApis('delivery', 'device')
const cameraLiveVisible = ref(false)
const cameraLiveRow = ref(null)

const loading = ref(false)
const list = ref([])
const drawerVisible = ref(false)
const editingId = ref(null)
const form = reactive({
  vehicle_no: '',
  vehicle_model: '',
  driver_name: '',
  capacity_weight_kg: null,
  capacity_volume_m3: null,
  status: 'active',
})

const bindingVisible = ref(false)
const currentVehicle = ref(null)
const bindings = ref([])
const candidateDevices = ref([])
const selectedDeviceId = ref(null)

const locationVisible = ref(false)
const locationRow = ref(null)
const locationTab = ref('live')
const historyTrackPoints = ref([])
const historyLoading = ref(false)
const historyDemoOnly = ref(false)
const historyRange = ref(null)
const mapRef = ref(null)
const amap = ref(null)
const marker = ref(null)
const trackPolyline = ref(null)
const historyStartMarker = ref(null)
const historyEndMarker = ref(null)

const historyPb = useBeidouHistoryPlayback()
const hpPlaying = computed(() => historyPb.isPlaying)
const hpPaused = computed(() => historyPb.isPaused)
const hpCanScrub = computed(() => historyPb.canScrub)
const restrictionInfo = ref({
  source: 'seniverse',
  available: false,
  message: '',
  city: '北京',
  date: '',
  digits: [],
  raw_text: '',
})

const todayLimitDigits = computed(() => (Array.isArray(restrictionInfo.value?.digits) ? restrictionInfo.value.digits : []))

const todayLimitText = computed(() => {
  if (!restrictionInfo.value.available) {
    return `实时限号未接入：${restrictionInfo.value.message || '请配置实时接口 Key'}`
  }
  if (!todayLimitDigits.value.length) return `${restrictionInfo.value.city || '北京'}今日不限号`
  const detail = restrictionInfo.value.raw_text ? `（${restrictionInfo.value.raw_text}）` : ''
  return `${restrictionInfo.value.city || '北京'}实时尾号限行：${todayLimitDigits.value.join(' 和 ')}${detail}`
})

const vehicleLimitTag = (row) => vehicleLimitTagUtil(row, restrictionInfo.value)

const vehicleLimitReason = (row) => vehicleLimitReasonUtil(row, restrictionInfo.value)

const resetForm = () => {
  Object.assign(form, {
    vehicle_no: '',
    vehicle_model: '',
    driver_name: '',
    capacity_weight_kg: null,
    capacity_volume_m3: null,
    status: 'active',
  })
}

const load = async () => {
  loading.value = true
  try {
    const [vehicles, restriction] = await Promise.all([
      listDeliveryVehiclesApi(),
      getBeijingVehicleRestrictionApi().catch((e) => ({
        available: false,
        message: e?.message || '实时限号接口调用失败',
        digits: [],
      })),
    ])
    list.value = vehicles
    restrictionInfo.value = {
      ...restrictionInfo.value,
      ...(restriction || {}),
    }
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editingId.value = null
  resetForm()
  drawerVisible.value = true
}

const startEdit = (row) => {
  editingId.value = row.id
  Object.assign(form, { ...row })
  drawerVisible.value = true
}

const submit = async () => {
  const payload = {
    vehicle_no: String(form.vehicle_no || '').trim(),
    vehicle_model: String(form.vehicle_model || '').trim(),
    driver_name: String(form.driver_name || '').trim(),
    capacity_weight_kg: form.capacity_weight_kg,
    capacity_volume_m3: form.capacity_volume_m3,
    status: form.status,
  }
  if (!payload.vehicle_no) {
    ElMessage.warning('请填写车牌号')
    return
  }
  if (editingId.value) await updateDeliveryVehicleApi(editingId.value, payload)
  else await createDeliveryVehicleApi(payload)
  drawerVisible.value = false
  await load()
}

const refreshBindings = async () => {
  if (!currentVehicle.value) return
  const vid = Number(currentVehicle.value.id)
  if (!Number.isFinite(vid)) return
  bindings.value = await listVehicleBindingsApi(vid)
  // 必须传数字，否则 axios 可能省略参数；后端仅返回未绑定任何车辆的设备
  candidateDevices.value = await listDeliveryDevicesApi({ bind_vehicle_id: vid })
}

const deviceBindOptionLabel = (d) =>
  `${d.vendor}/${d.device_type} - ${d.device_name || d.device_code}${d.channel_no ? ` (CH${d.channel_no})` : ''}`

const openBinding = async (vehicle) => {
  currentVehicle.value = vehicle
  selectedDeviceId.value = null
  bindingVisible.value = true
  await refreshBindings()
}

const addBinding = async () => {
  if (!selectedDeviceId.value || !currentVehicle.value) {
    ElMessage.warning('请选择设备')
    return
  }
  try {
    await createVehicleBindingApi(currentVehicle.value.id, { device_id: selectedDeviceId.value })
    selectedDeviceId.value = null
    await refreshBindings()
    ElMessage.success('绑定成功')
  } catch (err) {
    ElMessage.error(err?.message || '绑定失败')
  }
}

const removeBinding = async (bindingId) => {
  if (!currentVehicle.value) return
  await deleteVehicleBindingApi(currentVehicle.value.id, bindingId)
  await refreshBindings()
}

const hasValidLocation = computed(() => {
  const lng = Number(locationRow.value?.lng)
  const lat = Number(locationRow.value?.lat)
  return Number.isFinite(lng) && Number.isFinite(lat)
})

const isBeidouLocation = computed(() => locationRow.value?.source === 'beidou')

const showMapFrame = computed(() => {
  if (!locationRow.value) return false
  if (locationRow.value.source !== 'beidou') {
    return hasValidLocation.value
  }
  if (locationTab.value === 'live') {
    return hasValidLocation.value
  }
  return true
})

const defaultHistoryRange = () => {
  const end = new Date()
  const start = new Date(end.getTime() - 6 * 3600 * 1000)
  return [start, end]
}

const getHistoryMap = () => amap.value
const getHistoryPoints = () => historyTrackPoints.value
const getHistoryTitle = () =>
  [locationRow.value?.vehicle_no, locationRow.value?.vehicle_model].filter(Boolean).join(' ') || '历史轨迹'

const onHistoryPlay = () => {
  if (!amap.value) {
    ElMessage.warning('请先等待地图加载完成')
    return
  }
  const r = historyPb.playOrContinue(getHistoryMap, getHistoryPoints, getHistoryTitle)
  if (!r?.ok) {
    ElMessage.warning(r?.reason === 'short_path' ? '轨迹点过少，无法播放' : '地图未就绪')
  }
}

const onHistoryRestart = () => {
  if (!amap.value) {
    ElMessage.warning('请先等待地图加载完成')
    return
  }
  const r = historyPb.restartFromBeginning(getHistoryMap, getHistoryPoints, getHistoryTitle)
  if (!r?.ok) {
    ElMessage.warning(r?.reason === 'short_path' ? '轨迹点过少，无法播放' : '地图未就绪')
  }
}

const destroyLocationMap = () => {
  historyPb.detachForMapDestroyed()
  if (trackPolyline.value) {
    trackPolyline.value.setMap(null)
    trackPolyline.value = null
  }
  if (historyStartMarker.value) {
    historyStartMarker.value.setMap(null)
    historyStartMarker.value = null
  }
  if (historyEndMarker.value) {
    historyEndMarker.value.setMap(null)
    historyEndMarker.value = null
  }
  if (marker.value) {
    marker.value.setMap(null)
    marker.value = null
  }
  if (amap.value) {
    amap.value.destroy()
    amap.value = null
  }
}

const renderLocationMap = async () => {
  if (!locationVisible.value || !showMapFrame.value || !mapRef.value) return
  const key = import.meta.env.VITE_AMAP_KEY
  if (!key) {
    ElMessage.warning('未配置高德地图 Key（VITE_AMAP_KEY）')
    return
  }

  destroyLocationMap()
  await AMapLoader.load({ key, version: '2.0' })

  if (locationTab.value === 'live') {
    const lng = Number(locationRow.value.lng)
    const lat = Number(locationRow.value.lat)
    const title =
      [locationRow.value?.vehicle_no, locationRow.value?.vehicle_model].filter(Boolean).join(' ') || '车辆位置'
    amap.value = new window.AMap.Map(mapRef.value, {
      zoom: 15,
      center: [lng, lat],
    })
    marker.value = new window.AMap.Marker({
      position: [lng, lat],
      title,
    })
    marker.value.setMap(amap.value)
    amap.value.resize()
    return
  }

  const pts = historyTrackPoints.value || []
  const fallbackLng = hasValidLocation.value ? Number(locationRow.value.lng) : 116.397428
  const fallbackLat = hasValidLocation.value ? Number(locationRow.value.lat) : 39.90923

  if (!pts.length) {
    amap.value = new window.AMap.Map(mapRef.value, {
      zoom: 12,
      center: [fallbackLng, fallbackLat],
    })
    amap.value.resize()
    return
  }

  const { path } = buildSortedHistoryPath(pts)

  if (path.length === 0) {
    amap.value = new window.AMap.Map(mapRef.value, {
      zoom: 12,
      center: [fallbackLng, fallbackLat],
    })
    amap.value.resize()
    return
  }

  if (path.length === 1) {
    const c = path[0]
    amap.value = new window.AMap.Map(mapRef.value, {
      zoom: 14,
      center: c,
    })
    marker.value = new window.AMap.Marker({ position: c, title: '轨迹点' })
    marker.value.setMap(amap.value)
    amap.value.resize()
    return
  }

  amap.value = new window.AMap.Map(mapRef.value, {})
  trackPolyline.value = new window.AMap.Polyline({
    path,
    strokeColor: '#2563eb',
    strokeWeight: 4,
    lineJoin: 'round',
  })
  trackPolyline.value.setMap(amap.value)
  historyStartMarker.value = new window.AMap.Marker({
    position: path[0],
    title: '起点',
    anchor: 'bottom-center',
  })
  historyEndMarker.value = new window.AMap.Marker({
    position: path[path.length - 1],
    title: '终点',
    anchor: 'bottom-center',
  })
  historyStartMarker.value.setMap(amap.value)
  historyEndMarker.value.setMap(amap.value)
  amap.value.setFitView([trackPolyline.value], false, [48, 48, 48, 48])
  amap.value.resize()
}

const loadHistoryTrack = async () => {
  const vid = Number(locationRow.value?.vehicle_id)
  if (!Number.isFinite(vid)) return
  const r = historyRange.value
  if (!Array.isArray(r) || r.length !== 2 || !r[0] || !r[1]) {
    ElMessage.warning('请选择时间范围')
    return
  }
  const st = Math.floor(new Date(r[0]).getTime() / 1000)
  const et = Math.floor(new Date(r[1]).getTime() / 1000)
  historyLoading.value = true
  try {
    const res = await postVehicleBeidouHistoryTrackApi(vid, {
      start_time: st,
      end_time: et,
      force_demo: historyDemoOnly.value,
    })
    historyTrackPoints.value = Array.isArray(res.points) ? res.points : []
    if (!historyTrackPoints.value.length) {
      ElMessage.info('该时段无轨迹点')
    } else {
      ElMessage.success(`已加载 ${historyTrackPoints.value.length} 个轨迹点`)
    }
    if (res.may_have_more) {
      ElMessage.warning('点位较多，平台可能尚有更多记录未一次返回')
    }
  } catch (err) {
    const msg = err?.response?.data?.detail
    const text = typeof msg === 'string' ? msg : err?.message || '查询失败'
    ElMessage.error(text)
    historyTrackPoints.value = []
  } finally {
    historyLoading.value = false
  }
}

const openVehicleLocation = async (row) => {
  try {
    const res = await getVehicleLocationApi(row.id)
    locationRow.value = { ...res, vehicle_id: row.id }
    locationVisible.value = true
  } catch (err) {
    const msg = err?.response?.data?.detail || '暂无位置'
    ElMessage.warning(typeof msg === 'string' ? msg : '暂无位置')
  }
}

const openCameraLive = (camera) => {
  cameraLiveRow.value = camera
  cameraLiveVisible.value = true
}

watch(locationVisible, async (visible) => {
  if (!visible) {
    destroyLocationMap()
    historyPb.destroy()
    locationRow.value = null
    locationTab.value = 'live'
    historyTrackPoints.value = []
    historyRange.value = null
    historyDemoOnly.value = false
    return
  }
  historyTrackPoints.value = []
  locationTab.value = 'live'
  if (locationRow.value?.source === 'beidou') {
    historyRange.value = defaultHistoryRange()
  } else {
    historyRange.value = null
  }
  await nextTick()
  await renderLocationMap()
})

watch(locationTab, async () => {
  if (!locationVisible.value) return
  await nextTick()
  await renderLocationMap()
})

watch(
  () => [locationRow.value?.lng, locationRow.value?.lat],
  async () => {
    if (!locationVisible.value || locationTab.value !== 'live') return
    await nextTick()
    await renderLocationMap()
  },
)

watch(
  historyTrackPoints,
  async (pts) => {
    historyPb.syncTrackPoints(pts)
    if (!locationVisible.value || locationTab.value !== 'history') return
    await nextTick()
    await renderLocationMap()
  },
  { deep: true },
)

onBeforeUnmount(() => {
  destroyLocationMap()
  historyPb.destroy()
})

onMounted(load)
</script>

<template>
  <el-card class="mb-3">
    <div class="crud-toolbar">
      <span class="limit-tip">{{ todayLimitText }}</span>
      <el-button type="primary" @click="openCreate">新增车辆</el-button>
    </div>
  </el-card>

  <el-card>
    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="vehicle_no" label="车牌号" min-width="160" />
      <el-table-column prop="vehicle_model" label="车型" min-width="140" show-overflow-tooltip />
      <el-table-column prop="driver_name" label="司机" min-width="120" />
      <el-table-column prop="capacity_weight_kg" label="载重(kg)" width="120" />
      <el-table-column prop="capacity_volume_m3" label="容积(m³)" width="120" />
      <el-table-column label="今日限号" width="100">
        <template #default="{ row }">
          <el-tooltip :content="vehicleLimitReason(row)" placement="top" effect="dark">
            <span :class="vehicleLimitTag(row) === '限行' ? 'limit-hit' : 'limit-ok'">{{ vehicleLimitTag(row) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="北斗状态" width="120" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.beidou_vehicle_status === '在线'" type="success" size="small">在线</el-tag>
          <el-tag v-else-if="row.beidou_vehicle_status === '离线'" type="info" size="small">离线</el-tag>
          <el-tag v-else type="warning" size="small">未绑定北斗</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="萤石摄像头" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">
          <div v-if="row.ys7_cameras?.length" class="camera-list-cell">
            <el-tag
              v-for="camera in row.ys7_cameras"
              :key="camera.id"
              size="small"
              :type="ys7BatteryFromRow(camera) != null ? ys7BatteryTagType(ys7BatteryFromRow(camera)) : (ys7SupportsPtz(camera) ? 'success' : 'info')"
              class="camera-tag-clickable"
              @click="openCameraLive(camera)"
            >
              {{ camera.device_name || camera.device_code }}<template v-if="camera.channel_no"> · CH{{ camera.channel_no }}</template>
              <template v-if="ys7BatteryFromRow(camera) != null"> · {{ ys7BatteryFromRow(camera) }}%</template>
              · 直播
            </el-tag>
          </div>
          <span v-else class="text-slate-400">未绑定</span>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">{{ row.status === 'active' ? '启用' : '停用' }}</template>
      </el-table-column>
      <el-table-column label="操作" min-width="300" align="center">
        <template #default="{ row }">
          <div class="op-btns">
            <el-button size="small" @click="startEdit(row)">编辑</el-button>
            <el-button size="small" type="primary" plain @click="openBinding(row)">绑定设备</el-button>
            <el-button size="small" type="primary" plain @click="openVehicleLocation(row)">位置</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-drawer v-model="drawerVisible" :title="editingId ? '编辑车辆' : '新增车辆'" size="480px">
    <el-form label-width="110px">
      <el-form-item label="车牌号"><el-input v-model="form.vehicle_no" placeholder="如 京A12345" /></el-form-item>
      <el-form-item label="车型">
        <el-input v-model="form.vehicle_model" placeholder="如 大通 EV30、福田图雅诺" clearable />
        <div class="field-tip">填写品牌与车型即可，便于调度与资产识别。</div>
      </el-form-item>
      <el-form-item label="司机姓名"><el-input v-model="form.driver_name" /></el-form-item>
      <el-form-item label="载重(kg)"><el-input-number v-model="form.capacity_weight_kg" :min="0" :precision="3" /></el-form-item>
      <el-form-item label="容积(m³)"><el-input-number v-model="form.capacity_volume_m3" :min="0" :precision="4" /></el-form-item>
      <el-form-item label="状态">
        <el-select v-model="form.status" style="width: 140px">
          <el-option value="active" label="启用" />
          <el-option value="inactive" label="停用" />
        </el-select>
        <div class="field-tip">启用/停用请在此切换；列表中不再单独提供「停用」按钮，避免与编辑重复。</div>
      </el-form-item>
      <el-button type="primary" @click="submit">{{ editingId ? '保存修改' : '确认新增' }}</el-button>
    </el-form>
  </el-drawer>

  <el-drawer v-model="bindingVisible" title="车辆设备绑定" size="760px">
    <div class="binding-head">
      <div>
        车辆：{{ currentVehicle?.vehicle_no || '-' }}
        <span v-if="currentVehicle?.vehicle_model" class="vehicle-model-tag">（{{ currentVehicle.vehicle_model }}）</span>
      </div>
      <div>约束：北斗最多 1 个，萤石最多 3 个</div>
    </div>
    <div class="binding-actions">
      <el-select v-model="selectedDeviceId" filterable placeholder="选择要绑定的设备" style="width: 400px">
        <el-option
          v-for="d in candidateDevices"
          :key="d.id"
          :value="d.id"
          :label="deviceBindOptionLabel(d)"
        />
      </el-select>
      <el-button type="primary" @click="addBinding">绑定</el-button>
    </div>
    <el-table :data="bindings" border>
      <el-table-column label="设备" min-width="250">
        <template #default="{ row }">
          {{ row.device.vendor }}/{{ row.device.device_type }} - {{ row.device.device_name || row.device.device_code }}
        </template>
      </el-table-column>
      <el-table-column label="编码" prop="device.device_code" min-width="160" />
      <el-table-column label="通道" width="80">
        <template #default="{ row }">{{ row.device.channel_no || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="center">
        <template #default="{ row }">
          <el-button size="small" type="danger" plain @click="removeBinding(row.id)">解绑</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-drawer>

  <el-dialog
    v-model="locationVisible"
    width="860px"
    destroy-on-close
    :title="`车辆位置 - ${locationRow?.vehicle_no || ''}`"
  >
    <div v-if="isBeidouLocation" class="location-mode-bar">
      <el-radio-group v-model="locationTab" size="small">
        <el-radio-button label="live">实时位置</el-radio-button>
        <el-radio-button label="history">历史轨迹</el-radio-button>
      </el-radio-group>
    </div>

    <div v-if="isBeidouLocation && locationTab === 'history'" class="history-toolbar">
      <el-date-picker
        v-model="historyRange"
        type="datetimerange"
        range-separator="至"
        start-placeholder="开始时间"
        end-placeholder="结束时间"
        style="width: 100%; max-width: 520px"
      />
      <el-checkbox v-model="historyDemoOnly">仅演示数据</el-checkbox>
      <el-button type="primary" :loading="historyLoading" @click="loadHistoryTrack">查询轨迹</el-button>
    </div>
    <p v-if="isBeidouLocation && locationTab === 'history'" class="history-hint">
      交互对齐 sxw：查询后可拖动进度条预览；支持播放/暂停/继续、停止、复位、从新播放、倍速、循环、地图跟随与渐进轨迹线（航向角来自 course 或两点推算）。
    </p>

    <div v-show="showMapFrame" class="map-box">
      <template v-if="locationTab === 'live'">
        <div class="map-meta">
          <span>{{ locationRow?.vehicle_model ? `车型：${locationRow.vehicle_model}` : '' }}</span>
          <span>坐标：{{ Number(locationRow?.lng).toFixed(6) }}, {{ Number(locationRow?.lat).toFixed(6) }}（高德/GCJ-02）</span>
        </div>
        <div class="map-meta sub">
          <span>来源：{{ locationRow?.source === 'beidou' ? '北斗' : locationRow?.source === 'ys7' ? '萤石' : locationRow?.source || '-' }}</span>
          <span v-if="locationRow?.device_label">设备：{{ locationRow.device_label }}</span>
        </div>
      </template>
      <template v-else>
        <div class="map-meta">
          <span>历史轨迹（高德 GCJ-02）</span>
          <span v-if="historyTrackPoints.length">共 {{ historyTrackPoints.length }} 点</span>
          <span v-else>选择时间范围后点击「查询轨迹」</span>
        </div>
        <div v-if="historyTrackPoints.length >= 2" class="history-playback-bar">
          <el-button size="small" type="primary" plain :disabled="hpPlaying" @click="onHistoryPlay">播放</el-button>
          <el-button size="small" :disabled="!hpPlaying" @click="historyPb.pause">暂停</el-button>
          <el-button size="small" :disabled="!hpPaused" @click="historyPb.resume">继续</el-button>
          <el-button size="small" :disabled="hpPlaying" @click="onHistoryRestart">从新播放</el-button>
          <el-button size="small" @click="historyPb.endPlayback">停止</el-button>
          <el-button size="small" @click="historyPb.resetToStart(getHistoryMap)">复位</el-button>
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
        <div v-if="historyTrackPoints.length >= 2" class="history-progress-row">
          <span class="playback-speed-label">进度</span>
          <el-slider
            class="history-progress-slider"
            :model-value="historyPb.progressPercent"
            :disabled="!hpCanScrub"
            :min="0"
            :max="100"
            :step="0.1"
            :format-tooltip="(v) => `${Number(v).toFixed(1)}%`"
            @update:model-value="(v) => historyPb.seekPercent(v, getHistoryMap)"
          />
        </div>
      </template>
      <div ref="mapRef" class="map-frame" />
    </div>
    <el-empty
      v-if="(isBeidouLocation ? locationTab === 'live' : true) && !showMapFrame"
      description="暂无坐标"
    />
  </el-dialog>

  <Ys7CameraLiveDialog
    v-model="cameraLiveVisible"
    :camera="cameraLiveRow"
    :live-url-api="liveUrlApi"
    :ptz-control="ptzControl"
    player-key="delivery-vehicle-cam"
  />
</template>

<style scoped>
.crud-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.limit-tip {
  font-size: 13px;
  color: #64748b;
}

.limit-hit {
  color: #dc2626;
  font-weight: 600;
}

.limit-ok {
  color: #475569;
}

.op-btns {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
}

.field-tip {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
}

.vehicle-model-tag {
  color: #909399;
  font-weight: normal;
}

.binding-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
  color: #606266;
}

.binding-actions {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}

.map-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.map-meta {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  color: #475569;
  font-size: 13px;
}

.map-meta.sub {
  font-size: 12px;
  color: #64748b;
}

.map-frame {
  width: 100%;
  height: 420px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}

.location-mode-bar {
  margin-bottom: 10px;
}

.history-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.history-hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.4;
}

.history-playback-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}

.playback-speed-label {
  font-size: 12px;
  color: #64748b;
}

.playback-speed-select {
  width: 96px;
}

.camera-tag-clickable {
  cursor: pointer;
}

.camera-tag-clickable:hover {
  opacity: 0.88;
}

.camera-list-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.history-progress-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 4px;
}

.history-progress-slider {
  flex: 1;
  min-width: 120px;
}
</style>
