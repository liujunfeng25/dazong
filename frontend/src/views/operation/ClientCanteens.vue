<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createOperationClientCanteenApi,
  deleteOperationClientCanteenApi,
  listAccountsApi,
  listOperationClientCanteensApi,
  searchOperationAccountAddressTipsApi,
  updateOperationClientCanteenApi,
} from '../../api/operation'
import { isUsableGeoCoord } from '../../utils/geoCoords'

const clients = ref([])
const list = ref([])
/** 食堂名称 / 采购方单位名 / 登录名 模糊搜索 */
const filterKeyword = ref('')
const drawerVisible = ref(false)
const isEditing = ref(false)
const mapWrapRef = ref(null)
const map = ref(null)
const mapMarker = ref(null)
const locationVisible = ref(false)
const locationRow = ref(null)
const locationMapRef = ref(null)
const locationMap = ref(null)
const locationMarker = ref(null)
const lastTipItems = ref([])
const form = reactive({
  id: null,
  school_client_id: '',
  name: '',
  address: '',
  lng: '',
  lat: '',
  status: 'active',
  sort_order: 0,
})

const placeOrMoveMarker = (lng, lat, recenter = false) => {
  if (!map.value) return
  if (!mapMarker.value) {
    mapMarker.value = new window.AMap.Marker({
      position: [lng, lat],
      draggable: true,
      cursor: 'move',
    })
    mapMarker.value.setMap(map.value)
    mapMarker.value.on('dragend', (e) => {
      const p = e.lnglat
      if (!p) return
      form.lng = Number(p.lng).toFixed(6)
      form.lat = Number(p.lat).toFixed(6)
    })
  } else {
    mapMarker.value.setPosition([lng, lat])
  }
  if (recenter) map.value.setZoomAndCenter(15, [lng, lat])
}

const initMap = async () => {
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
  } catch {
    ElMessage.error('高德地图加载失败，请检查 Key/域名白名单配置')
    return
  }
  if (map.value) {
    try {
      map.value.destroy()
    } catch {}
    map.value = null
    mapMarker.value = null
  }
  const hasCoord = Number.isFinite(Number(form.lng)) && Number.isFinite(Number(form.lat))
  const initLng = hasCoord ? Number(form.lng) : 116.397428
  const initLat = hasCoord ? Number(form.lat) : 39.90923
  map.value = new window.AMap.Map(mapWrapRef.value, {
    zoom: hasCoord ? 15 : 11,
    center: [initLng, initLat],
  })
  if (hasCoord) {
    placeOrMoveMarker(Number(form.lng), Number(form.lat))
  }
  map.value.on('click', (e) => {
    const p = e.lnglat
    if (!p) return
    form.lng = Number(p.lng).toFixed(6)
    form.lat = Number(p.lat).toFixed(6)
    placeOrMoveMarker(Number(p.lng), Number(p.lat))
  })
}

const clientLabelMap = computed(() =>
  Object.fromEntries(
    clients.value.map((u) => [
      u.id,
      `${u.company_name || u.username || '未命名采购方'}${u.username ? `（${u.username}）` : ''}`,
    ]),
  ),
)

const resetForm = () => {
  Object.assign(form, {
    id: null,
    school_client_id: '',
    name: '',
    address: '',
    lng: '',
    lat: '',
    status: 'active',
    sort_order: 0,
  })
}

const loadClients = async () => {
  clients.value = await listAccountsApi({ role: 'client' })
}

const load = async () => {
  const params = {}
  const k = (filterKeyword.value || '').trim()
  if (k) params.keyword = k
  list.value = await listOperationClientCanteensApi(params)
}

const statusTag = (status) => {
  if (status === 'active') return { type: 'success', text: '启用' }
  if (status === 'disabled') return { type: 'info', text: '停用' }
  return { type: 'warning', text: String(status || '—') }
}

const clientLabel = (row) => {
  if (row.client_name || row.client_username) {
    return `${row.client_name || row.client_username}${row.client_username ? `（${row.client_username}）` : ''}`
  }
  return clientLabelMap.value[row.school_client_id] || '未绑定采购方'
}

const buildPayload = () => {
  const lng = form.lng === '' || form.lng == null ? null : Number(form.lng)
  const lat = form.lat === '' || form.lat == null ? null : Number(form.lat)
  return {
    school_client_id: Number(form.school_client_id),
    name: (form.name || '').trim(),
    address: (form.address || '').trim(),
    lng: Number.isFinite(lng) ? lng : null,
    lat: Number.isFinite(lat) ? lat : null,
    status: form.status,
    sort_order: Number(form.sort_order) || 0,
  }
}

const submit = async () => {
  const payload = buildPayload()
  if (!payload.school_client_id) {
    ElMessage.warning('请选择采购方账号')
    return
  }
  if (!payload.name) {
    ElMessage.warning('请填写食堂名称')
    return
  }
  if (!payload.address) {
    ElMessage.warning('请填写食堂地址')
    return
  }
  if (!isUsableGeoCoord(payload.lng, payload.lat)) {
    ElMessage.warning('请从地址联想选择带坐标的条目，或点击地图扎针定位')
    return
  }
  if (form.id) await updateOperationClientCanteenApi(form.id, payload)
  else await createOperationClientCanteenApi(payload)
  resetForm()
  drawerVisible.value = false
  await load()
}

const openCreate = () => {
  isEditing.value = false
  resetForm()
  drawerVisible.value = true
}

const edit = (row) => {
  isEditing.value = true
  Object.assign(form, {
    id: row.id,
    school_client_id: row.school_client_id,
    name: row.name,
    address: row.address || '',
    lng: row.lng != null ? String(row.lng) : '',
    lat: row.lat != null ? String(row.lat) : '',
    status: row.status,
    sort_order: row.sort_order ?? 0,
  })
  drawerVisible.value = true
}

const queryAddressTips = async (queryString, cb) => {
  const q = String(queryString || '').trim()
  if (!q) {
    lastTipItems.value = []
    cb([])
    return
  }
  try {
    const res = await searchOperationAccountAddressTipsApi({ keywords: q, city: '北京' })
    const items = Array.isArray(res?.items) ? res.items : []
    lastTipItems.value = items
    cb(items.map((item) => ({ value: item.display || item.name || '' })))
  } catch {
    cb([])
  }
}

const onAddressSelect = (item) => {
  const selected = lastTipItems.value.find((v) => (v.display || v.name || '') === item.value)
  if (!selected) return
  if (selected.display) form.address = selected.display
  const lng = Number(selected.lng)
  const lat = Number(selected.lat)
  if (isUsableGeoCoord(lng, lat)) {
    form.lng = lng.toFixed(6)
    form.lat = lat.toFixed(6)
    placeOrMoveMarker(lng, lat, true)
    return
  }
  ElMessage.warning('该联想结果无精确坐标，请换一条或点击地图扎针')
}

watch(drawerVisible, async (visible) => {
  if (!visible) {
    if (map.value) {
      try {
        map.value.destroy()
      } catch {}
      map.value = null
      mapMarker.value = null
    }
    return
  }
  await nextTick()
  await initMap()
})

const remove = async (row) => {
  await ElMessageBox.confirm(`删除食堂「${row.name}」？若已有订单将无法删除。`, '删除确认', {
    type: 'warning',
  })
  await deleteOperationClientCanteenApi(row.id)
  await load()
}

const openMapLocation = (row) => {
  const lng = Number(row?.lng)
  const lat = Number(row?.lat)
  if (!isUsableGeoCoord(lng, lat)) {
    ElMessage.warning('该食堂暂无有效坐标，请编辑后重新扎针')
    return
  }
  locationRow.value = row
  locationVisible.value = true
}

const initLocationMap = async () => {
  const lng = Number(locationRow.value?.lng)
  const lat = Number(locationRow.value?.lat)
  if (!Number.isFinite(lng) || !Number.isFinite(lat) || !locationMapRef.value) return
  const key = import.meta.env.VITE_AMAP_KEY
  if (!key) {
    ElMessage.warning('未配置高德地图 Key（VITE_AMAP_KEY）')
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
  } catch {
    ElMessage.error('高德地图加载失败，请检查 Key/域名白名单配置')
    return
  }
  if (locationMap.value) {
    try {
      locationMap.value.destroy()
    } catch {}
    locationMap.value = null
    locationMarker.value = null
  }
  locationMap.value = new window.AMap.Map(locationMapRef.value, {
    zoom: 16,
    center: [lng, lat],
  })
  locationMarker.value = new window.AMap.Marker({
    position: [lng, lat],
    title: locationRow.value?.name || '食堂位置',
  })
  locationMarker.value.setMap(locationMap.value)
}

watch(locationVisible, async (visible) => {
  if (!visible) return
  await nextTick()
  await initLocationMap()
})

onMounted(async () => {
  await loadClients()
  await load()
})

onBeforeUnmount(() => {
  if (map.value) {
    try {
      map.value.destroy()
    } catch {}
    map.value = null
    mapMarker.value = null
  }
  if (locationMap.value) {
    try {
      locationMap.value.destroy()
    } catch {}
    locationMap.value = null
    locationMarker.value = null
  }
})
</script>

<template>
  <el-alert
    class="mb-3"
    type="info"
    show-icon
    :closable="false"
    title="各采购方下属的食堂仅在本页由运营维护：绑定到采购方登录账号后，该单位登录客户端时须在选食堂中转页选用后方可进入业务功能。"
  />
  <el-card class="mb-3">
    <div class="cc-toolbar">
      <div class="cc-filters">
        <div class="cc-field cc-field-grow">
          <span class="cc-field-label">名称模糊搜索</span>
          <el-input
            v-model="filterKeyword"
            clearable
            placeholder="匹配食堂名称、采购方单位名或登录名"
            @clear="load"
            @keyup.enter="load"
          />
        </div>
        <el-button type="primary" @click="load">查询</el-button>
      </div>
      <div class="cc-toolbar-actions">
        <el-button type="primary" @click="openCreate">新建食堂</el-button>
      </div>
    </div>
  </el-card>
  <el-card>
    <el-table :data="list" border>
      <el-table-column label="采购方" min-width="160">
        <template #default="{ row }">{{ clientLabel(row) }}</template>
      </el-table-column>
      <el-table-column prop="name" label="食堂名称" min-width="140" />
      <el-table-column prop="address" label="地址" min-width="180" show-overflow-tooltip />
      <el-table-column label="坐标" min-width="180">
        <template #default="{ row }">
          <el-button
            v-if="row.lng != null && row.lat != null"
            type="primary"
            link
            class="coord-link"
            @click="openMapLocation(row)"
          >
            {{ `${Number(row.lng).toFixed(6)}, ${Number(row.lat).toFixed(6)}` }}
          </el-button>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="108" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status).type" effect="light" round class="status-tag">
            {{ statusTag(row.status).text }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="center">
        <template #default="{ row }">
          <div class="op-btns">
            <el-button size="small" @click="edit(row)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="remove(row)">删除</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-drawer v-model="drawerVisible" :title="isEditing ? '编辑食堂' : '新建食堂'" size="620px">
    <el-form label-width="108px">
      <el-form-item label="采购方账号">
        <el-select v-model="form.school_client_id" filterable placeholder="请选择采购方登录账号" style="width: 100%">
          <el-option
            v-for="u in clients"
            :key="u.id"
            :label="`${u.company_name || u.username || '未命名采购方'}${u.username ? `（${u.username}）` : ''}`"
            :value="u.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="食堂名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="地址">
        <el-autocomplete
          v-model="form.address"
          :fetch-suggestions="queryAddressTips"
          class="address-input"
          clearable
          placeholder="请输入并从联想结果选择食堂地址"
          @select="onAddressSelect"
        />
      </el-form-item>
      <el-form-item label="精确位置">
        <div ref="mapWrapRef" class="canteen-map" />
        <div class="canteen-coord-row">
          <span>经度：<strong>{{ Number.isFinite(Number(form.lng)) ? Number(form.lng).toFixed(6) : '—' }}</strong></span>
          <span>纬度：<strong>{{ Number.isFinite(Number(form.lat)) ? Number(form.lat).toFixed(6) : '—' }}</strong></span>
          <span class="canteen-coord-tip">点击地图任意位置或拖动 marker 可微调食堂点位</span>
        </div>
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="form.status">
          <el-option value="active" label="启用" />
          <el-option value="disabled" label="停用" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="submit">{{ isEditing ? '保存' : '创建' }}</el-button>
      </el-form-item>
    </el-form>
  </el-drawer>

  <el-dialog
    v-model="locationVisible"
    width="780px"
    destroy-on-close
    :title="`地图定位 - ${locationRow?.name || ''}`"
  >
    <div class="map-meta">
      <div>采购方：{{ clientLabel(locationRow || {}) }}</div>
      <div>地址：{{ locationRow?.address || '—' }}</div>
      <div>坐标：{{ locationRow?.lng }}, {{ locationRow?.lat }}（高德/GCJ-02）</div>
    </div>
    <div ref="locationMapRef" class="map-canvas"></div>
  </el-dialog>
</template>

<style scoped>
.cc-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}
.cc-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
  flex: 1;
  min-width: 0;
}
.cc-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cc-field-grow {
  flex: 1;
  min-width: 200px;
  max-width: 420px;
}
.cc-field-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.status-tag {
  font-weight: 600;
}
.address-input {
  width: 100%;
}
.canteen-map {
  width: 100%;
  height: 320px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  overflow: hidden;
}
.canteen-coord-row {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 8px;
  font-size: 13px;
  color: #475569;
}
.canteen-coord-row strong {
  color: #0f172a;
}
.canteen-coord-tip {
  color: #94a3b8;
  font-size: 12px;
}
.coord-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.map-meta {
  margin-bottom: 10px;
  color: #606266;
  font-size: 13px;
}
.map-canvas {
  width: 100%;
  height: 420px;
  border-radius: 8px;
}
</style>
