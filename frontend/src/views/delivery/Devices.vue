<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import { ElMessage } from 'element-plus'
import {
  createDeliveryDeviceApi,
  listDeliveryDevicesApi,
  getDeviceBeidouLiveApi,
  postDeviceBeidouHistoryTrackApi,
  refreshBeidouDevicesApi,
  refreshYs7DevicesApi,
  updateDeliveryDeviceApi,
} from '../../api/delivery'
import { buildSortedHistoryPath } from '../../utils/amapPathPlayback'
import { useBeidouHistoryPlayback } from '../../composables/useBeidouHistoryPlayback'
import { useYs7CameraApis } from '../../composables/useYs7CameraApis'
import Ys7CameraLiveDialog from '../../components/Ys7CameraLiveDialog.vue'
import { deviceBindingDisplay, deviceBindingTagType } from '../../utils/deviceBindingDisplay'
import Ys7BatteryDisplay from '../../components/Ys7BatteryDisplay.vue'
import { ys7MetaFromRow, ys7PowerTagType } from '../../utils/ys7DeviceMeta'

const { liveUrlApi, ptzControl } = useYs7CameraApis('delivery', 'device')

const loading = ref(false)
const list = ref([])
const activeTab = ref('camera')
const drawerVisible = ref(false)
const renameVisible = ref(false)
const renaming = ref(false)
const renameForm = reactive({ id: null, device_name: '' })
const locationVisible = ref(false)
const locationRow = ref(null)
const locationLiveLoading = ref(false)
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
const liveVisible = ref(false)
const liveRow = ref(null)
const form = reactive({
  device_type: 'beidou',
  vendor: 'beidou',
  device_code: '',
  device_name: '',
  channel_no: 0,
  status: 'active',
})

const resetForm = () => {
  Object.assign(form, {
    device_type: 'beidou',
    vendor: 'beidou',
    device_code: '',
    device_name: '',
    channel_no: 0,
    status: 'active',
  })
}

const syncTypeVendor = () => {
  if (form.vendor === 'beidou') {
    form.device_type = 'beidou'
    form.channel_no = 0
  } else {
    form.device_type = 'camera'
  }
}

const showChannel = computed(() => form.vendor === 'ys7')
const isBeidouTab = computed(() => activeTab.value === 'beidou')
const isCameraTab = computed(() => activeTab.value === 'camera')

const load = async () => {
  loading.value = true
  try {
    list.value = await listDeliveryDevicesApi({ device_type: activeTab.value })
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  resetForm()
  if (isCameraTab.value) {
    form.vendor = 'ys7'
    form.device_type = 'camera'
    form.channel_no = 1
  }
  drawerVisible.value = true
}

const startEdit = (row) => {
  renameForm.id = row.id
  renameForm.device_name = row.device_name || ''
  renameVisible.value = true
}

const submit = async () => {
  const payload = {
    device_type: form.device_type,
    vendor: form.vendor,
    device_code: String(form.device_code || '').trim(),
    device_name: String(form.device_name || '').trim(),
    channel_no: Number(form.channel_no || 0),
    status: form.status,
  }
  if (!payload.device_code) {
    ElMessage.warning('请填写设备编码')
    return
  }
  await createDeliveryDeviceApi(payload)
  drawerVisible.value = false
  await load()
}

const submitRename = async () => {
  if (!renameForm.id) return
  const row = list.value.find((i) => Number(i.id) === Number(renameForm.id))
  if (!row) {
    ElMessage.warning('设备不存在或已刷新，请重试')
    return
  }
  const name = String(renameForm.device_name || '').trim()
  if (!name) {
    ElMessage.warning('请输入设备名称')
    return
  }
  renaming.value = true
  try {
    await updateDeliveryDeviceApi(row.id, {
      device_type: row.device_type,
      vendor: row.vendor,
      device_code: row.device_code,
      device_name: name,
      channel_no: Number(row.channel_no || 0),
      status: row.status || 'active',
      raw_payload_json: row.raw_payload_json ?? undefined,
    })
    ElMessage.success('重命名成功')
    renameVisible.value = false
    await load()
  } finally {
    renaming.value = false
  }
}

const refreshBeidou = async () => {
  loading.value = true
  try {
    const res = await refreshBeidouDevicesApi()
    ElMessage.success(`北斗设备已刷新，更新 ${res.upserted || 0} 条`)
  } finally {
    loading.value = false
  }
  await load()
}

const refreshYs7 = async () => {
  loading.value = true
  try {
    const res = await refreshYs7DevicesApi()
    ElMessage.success(`萤石设备已刷新，更新 ${res.upserted || 0} 条`)
  } finally {
    loading.value = false
  }
  await load()
}

const onTabChange = async (name) => {
  activeTab.value = String(name || 'camera')
  await load()
}

const onlineText = (row) => (String(row.online_status || 'offline') === 'online' ? '在线' : '离线')
const onlineTagType = (row) => (String(row.online_status || 'offline') === 'online' ? 'success' : 'info')

const formatPositionReportedAt = (value) => {
  if (!value) return ''
  const text = String(value).trim()
  if (!text) return ''
  const d = new Date(text.endsWith('Z') ? text : `${text}Z`)
  if (Number.isNaN(d.getTime())) return text
  return d.toLocaleString('zh-CN', { hour12: false })
}

const openLocation = async (row) => {
  locationRow.value = { ...row }
  locationVisible.value = true
  if (String(row?.vendor || '').toLowerCase() !== 'beidou' || !row?.id) return
  locationLiveLoading.value = true
  try {
    const live = await getDeviceBeidouLiveApi(row.id)
    locationRow.value = {
      ...locationRow.value,
      lng: live.lng,
      lat: live.lat,
      online_status: live.online_status,
      location_stale: live.location_stale,
      position_reported_at: live.position_reported_at,
    }
    const idx = list.value.findIndex((i) => Number(i.id) === Number(row.id))
    if (idx >= 0) {
      list.value[idx] = { ...list.value[idx], ...locationRow.value }
    }
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '拉取实时位置失败')
  } finally {
    locationLiveLoading.value = false
  }
}

const openLive = (row) => {
  liveRow.value = row
  liveVisible.value = true
}

const hasValidLocation = computed(() => {
  const lng = Number(locationRow.value?.lng)
  const lat = Number(locationRow.value?.lat)
  return Number.isFinite(lng) && Number.isFinite(lat)
})

const isBeidouLocation = computed(() => String(locationRow.value?.vendor || '').toLowerCase() === 'beidou')

const showMapFrame = computed(() => {
  if (!locationRow.value) return false
  if (String(locationRow.value.vendor || '').toLowerCase() !== 'beidou') {
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
  [locationRow.value?.device_name, locationRow.value?.device_code].filter(Boolean).join(' / ') || '历史轨迹'

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
    const title = locationRow.value?.device_name || locationRow.value?.device_code || '设备位置'
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
  const deviceId = Number(locationRow.value?.id)
  if (!Number.isFinite(deviceId)) return
  const r = historyRange.value
  if (!Array.isArray(r) || r.length !== 2 || !r[0] || !r[1]) {
    ElMessage.warning('请选择时间范围')
    return
  }
  const st = Math.floor(new Date(r[0]).getTime() / 1000)
  const et = Math.floor(new Date(r[1]).getTime() / 1000)
  historyLoading.value = true
  try {
    const res = await postDeviceBeidouHistoryTrackApi(deviceId, {
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
  if (String(locationRow.value?.vendor || '').toLowerCase() === 'beidou') {
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

watch(liveVisible, (visible) => {
  if (!visible) liveRow.value = null
})

onMounted(load)
</script>

<template>
  <el-card class="mb-3">
    <el-tabs :model-value="activeTab" class="device-tabs" @tab-change="onTabChange">
      <el-tab-pane label="摄像头" name="camera" />
      <el-tab-pane label="北斗定位" name="beidou" />
    </el-tabs>
    <div class="crud-toolbar">
      <div />
      <div class="right-actions">
        <el-button v-if="isBeidouTab" title="从 18gps 拉取账号下设备清单并写入本地（新增/更新设备档案）" @click="refreshBeidou">
          同步北斗
        </el-button>
        <el-button v-if="isCameraTab" @click="refreshYs7">同步萤石</el-button>
        <el-button type="primary" @click="openCreate">手工添加</el-button>
      </div>
    </div>
  </el-card>

  <el-card>
    <el-table v-if="isBeidouTab" v-loading="loading" :data="list" border>
      <el-table-column prop="vendor" label="来源" width="110" />
      <el-table-column prop="device_type" label="类型" width="110" />
      <el-table-column prop="device_code" label="设备编码" min-width="180" />
      <el-table-column prop="device_name" label="设备名称" min-width="180" />
      <el-table-column label="绑定归属" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <template v-if="deviceBindingDisplay(row)">
            <el-tag size="small" :type="deviceBindingTagType(deviceBindingDisplay(row).kind)" effect="light" class="binding-kind-tag">
              {{ deviceBindingDisplay(row).tag }}
            </el-tag>
            <div class="cell-strong binding-primary">{{ deviceBindingDisplay(row).primary }}</div>
            <div v-if="deviceBindingDisplay(row).secondary" class="text-xs text-slate-500">{{ deviceBindingDisplay(row).secondary }}</div>
          </template>
          <span v-else class="text-slate-400">未绑定</span>
        </template>
      </el-table-column>
      <el-table-column label="当前位置" min-width="260" show-overflow-tooltip>
        <template #default="{ row }">
          <template v-if="row.location_address">
            <span>{{ row.location_address }}</span>
            <div v-if="row.location_stale" class="text-xs text-amber-600">GPS 已过期，非实时位置</div>
          </template>
          <span v-else class="text-slate-400">—</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="onlineTagType(row)">{{ onlineText(row) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" align="center">
        <template #default="{ row }">
          <div class="op-btns">
            <el-button size="small" @click="startEdit(row)">重命名</el-button>
            <el-button size="small" type="primary" plain @click="openLocation(row)">位置</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-table v-else v-loading="loading" :data="list" border>
      <el-table-column prop="vendor" label="来源" width="110" />
      <el-table-column label="供电类型" width="100" align="center">
        <template #default="{ row }">
          <el-tag
            v-if="ys7MetaFromRow(row).powerLabel"
            :type="ys7PowerTagType(ys7MetaFromRow(row).powerKind)"
            effect="light"
            size="small"
          >
            {{ ys7MetaFromRow(row).powerLabel }}
          </el-tag>
          <span v-else class="text-slate-400">—</span>
        </template>
      </el-table-column>
      <el-table-column label="电量" width="130" align="center">
        <template #default="{ row }">
          <Ys7BatteryDisplay :row="row" compact />
        </template>
      </el-table-column>
      <el-table-column label="型号" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          <span>{{ ys7MetaFromRow(row).model || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="device_code" label="设备编码" min-width="160" />
      <el-table-column prop="device_name" label="设备名称" min-width="160" />
      <el-table-column prop="channel_no" label="通道" width="70" />
      <el-table-column label="绑定归属" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <template v-if="deviceBindingDisplay(row)">
            <el-tag size="small" :type="deviceBindingTagType(deviceBindingDisplay(row).kind)" effect="light" class="binding-kind-tag">
              {{ deviceBindingDisplay(row).tag }}
            </el-tag>
            <div class="cell-strong binding-primary">{{ deviceBindingDisplay(row).primary }}</div>
            <div v-if="deviceBindingDisplay(row).secondary" class="text-xs text-slate-500">{{ deviceBindingDisplay(row).secondary }}</div>
          </template>
          <span v-else class="text-slate-400">未绑定</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="onlineTagType(row)">{{ onlineText(row) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" align="center">
        <template #default="{ row }">
          <div class="op-btns">
            <el-button size="small" @click="startEdit(row)">重命名</el-button>
            <el-button size="small" type="primary" plain @click="openLive(row)">直播</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-drawer v-model="drawerVisible" title="手工添加设备" size="500px">
    <el-form label-width="110px">
      <el-form-item label="来源">
        <el-select v-model="form.vendor" style="width: 150px" @change="syncTypeVendor">
          <el-option value="beidou" label="北斗" />
          <el-option value="ys7" label="萤石" />
        </el-select>
      </el-form-item>
      <el-form-item label="设备类型">
        <el-select v-model="form.device_type" style="width: 150px" :disabled="true">
          <el-option value="beidou" label="北斗" />
          <el-option value="camera" label="摄像头" />
        </el-select>
      </el-form-item>
      <el-form-item label="设备编码"><el-input v-model="form.device_code" /></el-form-item>
      <el-form-item label="设备名称"><el-input v-model="form.device_name" /></el-form-item>
      <el-form-item v-if="showChannel" label="通道号">
        <el-input-number v-model="form.channel_no" :min="1" :step="1" />
      </el-form-item>
      <el-button type="primary" @click="submit">确认新增</el-button>
    </el-form>
  </el-drawer>

  <el-dialog v-model="renameVisible" title="设备重命名" width="460px" destroy-on-close>
    <el-form label-width="90px">
      <el-form-item label="新名称">
        <el-input v-model="renameForm.device_name" placeholder="请输入设备名称" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="renameVisible = false">取消</el-button>
      <el-button type="primary" :loading="renaming" @click="submitRename">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="locationVisible" title="设备位置" width="860px" destroy-on-close>
    <div v-if="locationLiveLoading" v-loading="true" class="location-live-loading" />
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
          <span>设备：{{ locationRow?.device_name || locationRow?.device_code }}</span>
          <span>坐标：{{ Number(locationRow?.lng).toFixed(6) }}, {{ Number(locationRow?.lat).toFixed(6) }}</span>
          <span v-if="locationRow?.position_reported_at">
            GPS 上报：{{ formatPositionReportedAt(locationRow.position_reported_at) }}
          </span>
        </div>
        <el-alert
          v-if="locationRow?.location_stale"
          class="location-stale-alert"
          type="warning"
          :closable="false"
          show-icon
          title="当前坐标不是实时位置"
          description="设备已超过 30 分钟未上报 GPS，地图显示的是最后一次定位。若设备实际已移动，请检查终端是否在线上报。"
        />
        <div v-if="locationRow?.location_address" class="map-address">{{ locationRow.location_address }}</div>
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
      description="暂无该设备位置（官方接口未返回经纬度）"
    />
  </el-dialog>

  <Ys7CameraLiveDialog
    v-model="liveVisible"
    :camera="liveRow"
    :live-url-api="liveUrlApi"
    :ptz-control="ptzControl"
    player-key="delivery-device"
  />
</template>

<style scoped>
.crud-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.device-tabs {
  margin-bottom: 8px;
}

.left-actions,
.right-actions,
.op-btns {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.map-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.location-live-loading {
  min-height: 48px;
  margin-bottom: 8px;
}

.location-stale-alert {
  margin-bottom: 10px;
}

.map-meta {
  display: flex;
  justify-content: space-between;
  color: #475569;
  font-size: 13px;
}

.map-address {
  color: #334155;
  font-size: 13px;
  line-height: 1.5;
}

.cell-strong {
  font-weight: 600;
  color: #0f172a;
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

.binding-kind-tag {
  margin-right: 6px;
  vertical-align: middle;
}

.binding-primary {
  display: inline;
}
</style>
