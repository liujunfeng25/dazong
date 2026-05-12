<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import Hls from 'hls.js'
import { ElMessage } from 'element-plus'
import {
  createDeliveryDeviceApi,
  getDeliveryCameraLiveUrlApi,
  listDeliveryDevicesApi,
  refreshBeidouDevicesApi,
  refreshYs7DevicesApi,
  updateDeliveryDeviceApi,
} from '../../api/delivery'

const loading = ref(false)
const list = ref([])
const activeTab = ref('beidou')
const drawerVisible = ref(false)
const renameVisible = ref(false)
const renaming = ref(false)
const renameForm = reactive({ id: null, device_name: '' })
const locationVisible = ref(false)
const locationRow = ref(null)
const mapRef = ref(null)
const amap = ref(null)
const marker = ref(null)
const liveVisible = ref(false)
const liveLoading = ref(false)
const liveUrl = ref('')
const liveRow = ref(null)
const liveVideoRef = ref(null)
const hlsPlayer = ref(null)
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
  activeTab.value = String(name || 'beidou')
  await load()
}

const onlineText = (row) => (String(row.online_status || 'offline') === 'online' ? '在线' : '离线')
const onlineTagType = (row) => (String(row.online_status || 'offline') === 'online' ? 'success' : 'info')

const openLocation = (row) => {
  locationRow.value = row
  locationVisible.value = true
}

const openLive = async (row) => {
  liveRow.value = row
  liveVisible.value = true
  liveLoading.value = true
  try {
    const res = await getDeliveryCameraLiveUrlApi(row.id)
    const url = String(res?.live_url || '').trim()
    if (!url) {
      ElMessage.warning('未获取到直播地址')
      return
    }
    liveUrl.value = url
    await nextTick()
    initLivePlayer()
  } catch (err) {
    liveVisible.value = false
    ElMessage.error(err?.response?.data?.detail || '获取直播地址失败')
  } finally {
    liveLoading.value = false
  }
}

const destroyLivePlayer = () => {
  if (hlsPlayer.value) {
    hlsPlayer.value.destroy()
    hlsPlayer.value = null
  }
  const video = liveVideoRef.value
  if (video) {
    try {
      video.pause()
    } catch (e) {}
    video.removeAttribute('src')
    video.load()
  }
}

const initLivePlayer = () => {
  const video = liveVideoRef.value
  if (!video || !liveUrl.value) return
  destroyLivePlayer()

  if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = liveUrl.value
    video.play().catch(() => {})
    return
  }
  if (Hls.isSupported()) {
    const hls = new Hls()
    hls.loadSource(liveUrl.value)
    hls.attachMedia(video)
    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      video.play().catch(() => {})
    })
    hls.on(Hls.Events.ERROR, (_, data) => {
      if (data?.fatal) {
        ElMessage.error('直播流播放失败，请稍后重试')
      }
    })
    hlsPlayer.value = hls
    return
  }
  ElMessage.warning('当前浏览器不支持 HLS 播放')
}

const hasValidLocation = computed(() => {
  const lng = Number(locationRow.value?.lng)
  const lat = Number(locationRow.value?.lat)
  return Number.isFinite(lng) && Number.isFinite(lat)
})

const initLocationMap = async () => {
  if (!hasValidLocation.value || !mapRef.value) return
  const key = import.meta.env.VITE_AMAP_KEY
  if (!key) {
    ElMessage.warning('未配置高德地图 Key（VITE_AMAP_KEY）')
    return
  }

  await AMapLoader.load({ key, version: '2.0' })
  const lng = Number(locationRow.value?.lng)
  const lat = Number(locationRow.value?.lat)
  const title = locationRow.value?.device_name || locationRow.value?.device_code || '设备位置'

  // 弹窗使用 destroy-on-close，每次打开都重建地图，避免绑定到旧容器导致空白
  if (amap.value) {
    amap.value.destroy()
    amap.value = null
    marker.value = null
  }
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
}

watch(locationVisible, async (visible) => {
  if (!visible) {
    if (amap.value) {
      amap.value.destroy()
      amap.value = null
      marker.value = null
    }
    return
  }
  await nextTick()
  await initLocationMap()
})

watch(
  () => [locationRow.value?.lng, locationRow.value?.lat],
  async () => {
    if (!locationVisible.value) return
    await nextTick()
    await initLocationMap()
  },
)

onBeforeUnmount(() => {
  destroyLivePlayer()
  if (amap.value) {
    amap.value.destroy()
    amap.value = null
    marker.value = null
  }
})

watch(liveVisible, (visible) => {
  if (!visible) {
    destroyLivePlayer()
    liveUrl.value = ''
    liveRow.value = null
  }
})

onMounted(load)
</script>

<template>
  <el-card class="mb-3">
    <el-tabs :model-value="activeTab" class="device-tabs" @tab-change="onTabChange">
      <el-tab-pane label="北斗定位" name="beidou" />
      <el-tab-pane label="摄像头" name="camera" />
    </el-tabs>
    <div class="crud-toolbar">
      <div />
      <div class="right-actions">
        <el-button v-if="isBeidouTab" @click="refreshBeidou">同步北斗</el-button>
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
      <el-table-column label="绑定车辆" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <template v-if="row.bound_vehicle_id">
            <div class="cell-strong">{{ row.bound_vehicle_no || '车辆#' + row.bound_vehicle_id }}</div>
            <div v-if="row.bound_vehicle_driver" class="text-xs text-slate-500">{{ row.bound_vehicle_driver }}</div>
          </template>
          <span v-else class="text-slate-400">未绑定</span>
        </template>
      </el-table-column>
      <el-table-column label="当前位置" min-width="240" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.location_address">{{ row.location_address }}</span>
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
      <el-table-column prop="device_code" label="设备编码" min-width="180" />
      <el-table-column prop="device_name" label="设备名称" min-width="220" />
      <el-table-column prop="channel_no" label="通道" width="90" />
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

  <el-dialog v-model="locationVisible" title="设备位置" width="760px" destroy-on-close>
    <div v-if="hasValidLocation" class="map-box">
      <div class="map-meta">
        <span>设备：{{ locationRow?.device_name || locationRow?.device_code }}</span>
        <span>坐标：{{ Number(locationRow?.lng).toFixed(6) }}, {{ Number(locationRow?.lat).toFixed(6) }}</span>
      </div>
      <div v-if="locationRow?.location_address" class="map-address">{{ locationRow.location_address }}</div>
      <div ref="mapRef" class="map-frame" />
    </div>
    <el-empty v-else description="暂无该设备位置（官方接口未返回经纬度）" />
  </el-dialog>

  <el-dialog v-model="liveVisible" title="摄像头直播" width="900px" destroy-on-close>
    <div class="live-box" v-loading="liveLoading">
      <div class="live-meta">
        <span>设备：{{ liveRow?.device_name || liveRow?.device_code || '摄像头' }}</span>
        <span>通道：{{ liveRow?.channel_no || 1 }}</span>
      </div>
      <video
        ref="liveVideoRef"
        class="live-video"
        controls
        autoplay
        muted
        playsinline
        webkit-playsinline
      />
    </div>
  </el-dialog>
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

.live-box {
  width: 100%;
}

.live-meta {
  display: flex;
  justify-content: space-between;
  color: #475569;
  font-size: 13px;
  margin-bottom: 8px;
}

.live-video {
  width: 100%;
  height: 500px;
  background: #000;
  border-radius: 8px;
}
</style>
