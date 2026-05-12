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
  updateDeliveryVehicleApi,
  deleteVehicleBindingApi,
} from '../../api/delivery'
import { vehicleLimitReason as vehicleLimitReasonUtil, vehicleLimitTag as vehicleLimitTagUtil } from '../../utils/beijingVehicleLimit'

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
const mapRef = ref(null)
const amap = ref(null)
const marker = ref(null)
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
  const title =
    [locationRow.value?.vehicle_no, locationRow.value?.vehicle_model].filter(Boolean).join(' ') || '车辆位置'

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

const openVehicleLocation = async (row) => {
  try {
    const res = await getVehicleLocationApi(row.id)
    locationRow.value = res
    locationVisible.value = true
  } catch (err) {
    const msg = err?.response?.data?.detail || '暂无位置'
    ElMessage.warning(typeof msg === 'string' ? msg : '暂无位置')
  }
}

watch(locationVisible, async (visible) => {
  if (!visible) {
    if (amap.value) {
      amap.value.destroy()
      amap.value = null
      marker.value = null
    }
    locationRow.value = null
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
  if (amap.value) {
    amap.value.destroy()
    amap.value = null
    marker.value = null
  }
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
    width="780px"
    destroy-on-close
    :title="`车辆位置 - ${locationRow?.vehicle_no || ''}`"
  >
    <div v-if="hasValidLocation" class="map-box">
      <div class="map-meta">
        <span>{{ locationRow?.vehicle_model ? `车型：${locationRow.vehicle_model}` : '' }}</span>
        <span>坐标：{{ Number(locationRow?.lng).toFixed(6) }}, {{ Number(locationRow?.lat).toFixed(6) }}（高德/GCJ-02）</span>
      </div>
      <div class="map-meta sub">
        <span>来源：{{ locationRow?.source === 'beidou' ? '北斗' : locationRow?.source === 'ys7' ? '萤石' : locationRow?.source || '-' }}</span>
        <span v-if="locationRow?.device_label">设备：{{ locationRow.device_label }}</span>
      </div>
      <div ref="mapRef" class="map-frame" />
    </div>
    <el-empty v-else description="暂无坐标" />
  </el-dialog>
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
</style>
