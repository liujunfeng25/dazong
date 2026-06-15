<script setup>
import AMapLoader from '@amap/amap-jsapi-loader'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  createDeliveryWarehouseApi,
  createDeliveryWarehouseBindingApi,
  deleteDeliveryWarehouseApi,
  deleteDeliveryWarehouseBindingApi,
  deliveryFleetMonitorWarehousesApi,
  listDeliveryDevicesApi,
  listDeliveryWarehousesApi,
  listDeliveryWarehouseBindingsApi,
  searchDeliveryWarehouseAddressTipsApi,
  updateDeliveryWarehouseApi,
} from '../../api/delivery'
import WarehouseCameraLiveDrawer from '../../components/WarehouseCameraLiveDrawer.vue'
import WarehouseElitechBrief from '../../components/WarehouseElitechBrief.vue'
import WarehouseElitechDrawer from '../../components/WarehouseElitechDrawer.vue'
import Ys7BatteryDisplay from '../../components/Ys7BatteryDisplay.vue'
import { isUsableGeoCoord } from '../../utils/geoCoords'
import { ys7MetaFromRow, ys7PowerTagType } from '../../utils/ys7DeviceMeta'

const loading = ref(false)
const list = ref([])
const keywords = ref('')

const editVisible = ref(false)
const editingId = ref(null)
const form = reactive({
  name: '',
  address: '',
  lng: null,
  lat: null,
})

const mapWrapRef = ref(null)
const editMap = ref(null)
const editMarker = ref(null)

const addressTipItems = ref([])
const amapEnabled = ref(true)

const bindVisible = ref(false)
const bindWarehouse = ref(null)
const cameraDevices = ref([])
const warehouseBindings = ref([])
const bindLoading = ref(false)

const liveVisible = ref(false)
const liveWarehouse = ref(null)
const liveLoadingId = ref(null)

const elitechVisible = ref(false)
const elitechWarehouse = ref(null)

const fmtCoord = (n) => (Number.isFinite(Number(n)) ? Number(n).toFixed(6) : '—')

const load = async () => {
  loading.value = true
  try {
    const res = await listDeliveryWarehousesApi({ keywords: keywords.value?.trim() || undefined })
    list.value = Array.isArray(res) ? res : []
  } catch (err) {
    ElMessage.warning(err?.response?.data?.detail || '仓库列表加载失败')
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  editingId.value = null
  form.name = ''
  form.address = ''
  form.lng = null
  form.lat = null
}

const openCreate = () => {
  resetForm()
  editVisible.value = true
}

const openEdit = (row) => {
  editingId.value = Number(row.id)
  form.name = row.name || ''
  form.address = row.address || ''
  form.lng = Number(row.lng)
  form.lat = Number(row.lat)
  editVisible.value = true
}

const queryAddressTips = async (q, cb) => {
  const s = String(q || '').trim()
  if (!s) {
    addressTipItems.value = []
    cb([])
    return
  }
  try {
    const res = await searchDeliveryWarehouseAddressTipsApi({ keywords: s, city: '北京' })
    amapEnabled.value = Boolean(res?.amap_enabled)
    const items = Array.isArray(res?.items) ? res.items : []
    addressTipItems.value = items
    cb(items.map((item) => ({ value: item.display || item.name || '' })))
  } catch (err) {
    cb([])
  }
}

const onAddressSelect = (selection) => {
  const picked = addressTipItems.value.find((v) => (v.display || v.name || '') === selection.value)
  if (!picked) return
  form.address = picked.display || picked.name || form.address
  const lng = Number(picked.lng)
  const lat = Number(picked.lat)
  if (isUsableGeoCoord(lng, lat)) {
    form.lng = lng
    form.lat = lat
    placeOrMoveMarker(lng, lat, true)
    return
  }
  ElMessage.warning('该联想结果无精确坐标，请换一条或点击地图扎针')
}

const placeOrMoveMarker = (lng, lat, recenter = false) => {
  if (!editMap.value) return
  if (!editMarker.value) {
    editMarker.value = new window.AMap.Marker({
      position: [lng, lat],
      draggable: true,
      cursor: 'move',
    })
    editMarker.value.setMap(editMap.value)
    editMarker.value.on('dragend', (e) => {
      const p = e.lnglat
      if (!p) return
      form.lng = Number(p.lng)
      form.lat = Number(p.lat)
    })
  } else {
    editMarker.value.setPosition([lng, lat])
  }
  if (recenter) editMap.value.setZoomAndCenter(15, [lng, lat])
}

const initEditMap = async () => {
  if (!mapWrapRef.value) return
  const key = import.meta.env.VITE_AMAP_KEY
  if (!key) {
    ElMessage.warning('未配置高德 Key（VITE_AMAP_KEY），地图不可用')
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
  } catch (err) {
    ElMessage.error('高德地图加载失败，请关闭 VPN 或检查 Key/白名单')
    return
  }
  if (editMap.value) {
    try { editMap.value.destroy() } catch {}
    editMap.value = null
    editMarker.value = null
  }
  const initLng = Number.isFinite(Number(form.lng)) ? Number(form.lng) : 116.407387
  const initLat = Number.isFinite(Number(form.lat)) ? Number(form.lat) : 39.904179
  editMap.value = new window.AMap.Map(mapWrapRef.value, {
    zoom: Number.isFinite(Number(form.lng)) ? 15 : 11,
    center: [initLng, initLat],
  })
  if (Number.isFinite(Number(form.lng)) && Number.isFinite(Number(form.lat))) {
    placeOrMoveMarker(Number(form.lng), Number(form.lat))
  }
  editMap.value.on('click', (e) => {
    const p = e.lnglat
    if (!p) return
    form.lng = Number(p.lng)
    form.lat = Number(p.lat)
    placeOrMoveMarker(Number(p.lng), Number(p.lat))
  })
}

watch(editVisible, async (visible) => {
  if (!visible) {
    if (editMap.value) {
      try { editMap.value.destroy() } catch {}
      editMap.value = null
      editMarker.value = null
    }
    return
  }
  await nextTick()
  await initEditMap()
})

const submitForm = async () => {
  if (!form.name?.trim()) {
    ElMessage.warning('请输入仓库名称')
    return
  }
  if (!isUsableGeoCoord(form.lng, form.lat)) {
    ElMessage.warning('请从地址联想选择带坐标的条目，或点击地图扎针定位')
    return
  }
  const payload = {
    name: form.name.trim(),
    address: form.address?.trim() || null,
    lng: Number(form.lng),
    lat: Number(form.lat),
  }
  try {
    if (editingId.value) {
      await updateDeliveryWarehouseApi(editingId.value, payload)
      ElMessage.success('仓库已更新')
    } else {
      await createDeliveryWarehouseApi(payload)
      ElMessage.success('仓库已创建')
    }
    editVisible.value = false
    await load()
  } catch (err) {
    // 全局拦截器已 toast；此处不重复
  }
}

const removeRow = async (row) => {
  try {
    await ElMessageBox.confirm(`确认删除仓库《${row.name}》？需先解绑全部摄像头。`, '确认', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteDeliveryWarehouseApi(Number(row.id))
    ElMessage.success('仓库已删除')
    await load()
  } catch (err) {
    // 全局拦截器已 toast
  }
}

const openElitech = (row) => {
  elitechWarehouse.value = row
  elitechVisible.value = true
}

const onElitechChanged = () => {
  load()
}

const openLiveMonitor = async (row) => {
  if (!Number(row?.camera_count)) {
    ElMessage.warning('该仓库未绑定摄像头')
    return
  }
  liveLoadingId.value = Number(row.id)
  try {
    const res = await deliveryFleetMonitorWarehousesApi()
    const wh = (res?.warehouses || []).find((w) => Number(w.id) === Number(row.id))
    if (!wh) {
      ElMessage.warning('未找到仓库监控信息')
      return
    }
    if (!wh.cameras?.length) {
      ElMessage.warning('该仓库未绑定摄像头')
      return
    }
    liveWarehouse.value = {
      ...wh,
      elitech_bound: Boolean(row.elitech_bound || wh.elitech_bound || row.elitech_sn || wh.elitech_sn),
      elitech_sn: row.elitech_sn || wh.elitech_sn || '',
      elitech_device_name: row.elitech_device_name || wh.elitech_device_name || '',
      elitech_temperature: row.elitech_temperature || wh.elitech_temperature || '',
      elitech_humidity: row.elitech_humidity || wh.elitech_humidity || '',
      elitech_online: row.elitech_online ?? wh.elitech_online ?? null,
    }
    liveVisible.value = true
  } catch (err) {
    ElMessage.warning(err?.response?.data?.detail || '加载仓库监控失败')
  } finally {
    liveLoadingId.value = null
  }
}

const openBind = async (row) => {
  bindWarehouse.value = row
  bindVisible.value = true
  bindLoading.value = true
  try {
    const [devicesRes, bindingsRes] = await Promise.all([
      listDeliveryDevicesApi({ device_type: 'camera', page_size: 500 }),
      listDeliveryWarehouseBindingsApi(Number(row.id)),
    ])
    cameraDevices.value = Array.isArray(devicesRes?.items)
      ? devicesRes.items
      : Array.isArray(devicesRes)
      ? devicesRes
      : []
    warehouseBindings.value = Array.isArray(bindingsRes) ? bindingsRes : []
  } catch (err) {
    ElMessage.warning('摄像头列表加载失败')
  } finally {
    bindLoading.value = false
  }
}

const isBoundToThisWarehouse = (deviceId) =>
  warehouseBindings.value.some((b) => Number(b.device?.id) === Number(deviceId))

const occupancyOf = (device) => {
  if (isBoundToThisWarehouse(Number(device.id))) return { kind: 'self', label: '已绑到本仓库' }
  const whId = Number(bindWarehouse.value?.id)
  if (device.bound_warehouse_id && Number(device.bound_warehouse_id) !== whId) {
    const name = device.bound_warehouse_name || `仓库#${device.bound_warehouse_id}`
    return { kind: 'warehouse', label: `已绑仓库 ${name}` }
  }
  if (device.bound_vehicle_no) return { kind: 'vehicle', label: `已绑车辆 ${device.bound_vehicle_no}` }
  return { kind: 'free', label: '未绑定' }
}

const handleToggleBind = async (device) => {
  const occ = occupancyOf(device)
  if (occ.kind === 'vehicle') {
    ElMessage.warning(occ.label + '；请先在车辆管理解绑')
    return
  }
  if (occ.kind === 'warehouse') {
    ElMessage.warning(occ.label + '；请先在对应仓库解绑')
    return
  }
  try {
    if (occ.kind === 'self') {
      const bindingRow = warehouseBindings.value.find((b) => Number(b.device?.id) === Number(device.id))
      if (!bindingRow) return
      await deleteDeliveryWarehouseBindingApi(Number(bindWarehouse.value.id), Number(bindingRow.id))
      ElMessage.success('已解绑')
    } else {
      await createDeliveryWarehouseBindingApi(Number(bindWarehouse.value.id), { device_id: Number(device.id) })
      ElMessage.success('已绑定')
    }
    // 刷新当前抽屉的绑定 + 顶层列表
    const bindingsRes = await listDeliveryWarehouseBindingsApi(Number(bindWarehouse.value.id))
    warehouseBindings.value = Array.isArray(bindingsRes) ? bindingsRes : []
    await load()
  } catch (err) {
    // 全局拦截器已 toast 互斥/重复绑定等错误
  }
}

onMounted(load)
onBeforeUnmount(() => {
  if (editMap.value) {
    try { editMap.value.destroy() } catch {}
    editMap.value = null
    editMarker.value = null
  }
})
</script>

<template>
  <el-card class="mb-3">
    <div class="warehouse-toolbar">
      <el-input
        v-model="keywords"
        placeholder="搜索仓库名称"
        style="width: 240px"
        clearable
        @keyup.enter="load"
        @clear="load"
      />
      <div class="warehouse-toolbar-spacer" />
      <el-button @click="load">刷新</el-button>
      <el-button type="primary" @click="openCreate">新建仓库</el-button>
    </div>
  </el-card>

  <el-card v-loading="loading">
    <el-table :data="list" border>
      <el-table-column prop="id" label="编号" width="80" />
      <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
      <el-table-column prop="address" label="地址" min-width="220" show-overflow-tooltip />
      <el-table-column label="坐标" width="200">
        <template #default="{ row }">
          {{ fmtCoord(row.lng) }}, {{ fmtCoord(row.lat) }}
        </template>
      </el-table-column>
      <el-table-column label="已绑摄像头" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="row.camera_count > 0 ? 'success' : 'info'" effect="plain">
            {{ row.camera_count || 0 }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="温湿度" min-width="200">
        <template #default="{ row }">
          <WarehouseElitechBrief :warehouse="row" />
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'" effect="light">
            {{ row.status === 'active' ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="400" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button
            size="small"
            type="success"
            plain
            :disabled="!row.camera_count"
            :loading="liveLoadingId === row.id"
            @click="openLiveMonitor(row)"
          >
            查看直播
          </el-button>
          <el-button size="small" type="primary" @click="openBind(row)">绑定摄像头</el-button>
          <el-button size="small" type="warning" plain @click="openElitech(row)">温湿度</el-button>
          <el-button size="small" type="danger" plain @click="removeRow(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无仓库，点击右上角「新建仓库」开始" :image-size="80" />
      </template>
    </el-table>
  </el-card>

  <el-dialog
    v-model="editVisible"
    :title="editingId ? '编辑仓库' : '新建仓库'"
    width="800px"
    destroy-on-close
  >
    <el-form label-width="92px" class="warehouse-form">
      <el-form-item label="名称" required>
        <el-input v-model="form.name" placeholder="如：朝阳冷链分拣中心" maxlength="128" show-word-limit />
      </el-form-item>
      <el-form-item label="详细地址">
        <el-autocomplete
          v-model="form.address"
          :fetch-suggestions="queryAddressTips"
          placeholder="输入地址关键词联想，选中后地图自动落点"
          style="width: 100%"
          clearable
          @select="onAddressSelect"
        />
        <div v-if="!amapEnabled" class="warehouse-hint">高德 Key 未配置，联想已不可用，请直接在地图扎针</div>
      </el-form-item>
      <el-form-item label="位置">
        <div ref="mapWrapRef" class="warehouse-map" />
        <div class="warehouse-coord-row">
          <span>经度：<strong>{{ fmtCoord(form.lng) }}</strong></span>
          <span>纬度：<strong>{{ fmtCoord(form.lat) }}</strong></span>
          <span class="warehouse-coord-tip">点击地图任意位置或拖动 marker 调整点位</span>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="editVisible = false">取消</el-button>
      <el-button type="primary" @click="submitForm">保存</el-button>
    </template>
  </el-dialog>

  <el-drawer
    v-model="bindVisible"
    size="60%"
    destroy-on-close
    :title="`绑定摄像头 - ${bindWarehouse?.name || ''}`"
  >
    <div v-loading="bindLoading">
      <el-alert
        type="info"
        :closable="false"
        title="规则：摄像头一旦绑定仓库就不能再绑车辆；同理已绑车辆的摄像头也不能绑仓库。"
        style="margin-bottom: 12px"
      />
      <el-table :data="cameraDevices" border max-height="520">
        <el-table-column label="供电" width="88" align="center">
          <template #default="{ row }">
            <el-tag
              v-if="ys7MetaFromRow(row).powerLabel"
              size="small"
              effect="light"
              :type="ys7PowerTagType(ys7MetaFromRow(row).powerKind)"
            >
              {{ ys7MetaFromRow(row).powerLabel }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="电量" width="120" align="center">
          <template #default="{ row }">
            <Ys7BatteryDisplay :row="row" compact />
          </template>
        </el-table-column>
        <el-table-column label="型号" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ ys7MetaFromRow(row).model || '—' }}</template>
        </el-table-column>
        <el-table-column prop="device_code" label="设备编号" min-width="120" show-overflow-tooltip />
        <el-table-column prop="device_name" label="名称" min-width="120" show-overflow-tooltip />
        <el-table-column prop="channel_no" label="通道" width="70" align="center" />
        <el-table-column label="当前归属" min-width="180">
          <template #default="{ row }">
            <el-tag
              :type="occupancyOf(row).kind === 'self' ? 'success' : occupancyOf(row).kind === 'vehicle' ? 'warning' : occupancyOf(row).kind === 'warehouse' ? 'danger' : 'info'"
              effect="plain"
            >
              {{ occupancyOf(row).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="right">
          <template #default="{ row }">
            <template v-if="occupancyOf(row).kind === 'self'">
              <el-button size="small" type="danger" plain @click="handleToggleBind(row)">解绑</el-button>
            </template>
            <template v-else-if="occupancyOf(row).kind === 'free'">
              <el-button size="small" type="primary" @click="handleToggleBind(row)">绑定到本仓库</el-button>
            </template>
            <template v-else>
              <el-button size="small" disabled>不可绑定</el-button>
            </template>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无摄像头，请前往「设备管理 - 摄像头」新增" :image-size="64" />
        </template>
      </el-table>
    </div>
  </el-drawer>

  <WarehouseCameraLiveDrawer
    v-model="liveVisible"
    :warehouse="liveWarehouse"
    scope="delivery"
    @elitech-changed="load"
  />
  <WarehouseElitechDrawer
    v-model="elitechVisible"
    :warehouse="elitechWarehouse"
    @changed="onElitechChanged"
  />
</template>

<style scoped>
.mb-3 {
  margin-bottom: 12px;
}

.warehouse-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.warehouse-toolbar-spacer {
  flex: 1;
}

.warehouse-form {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.warehouse-map {
  width: 100%;
  height: 360px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  overflow: hidden;
}

.warehouse-coord-row {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 8px;
  font-size: 13px;
  color: #475569;
}

.warehouse-coord-row strong {
  color: #0f172a;
}

.warehouse-coord-tip {
  color: #94a3b8;
  font-size: 12px;
}

.warehouse-hint {
  font-size: 12px;
  color: #b45309;
  margin-top: 4px;
}

</style>
