<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Location } from '@element-plus/icons-vue'
import {
  createAccountApi,
  deleteAccountApi,
  listAccountsApi,
  searchOperationAccountAddressTipsApi,
  updateAccountApi,
} from '../../api/operation'
import { useUserStore } from '../../stores/user'
import { can } from '../../utils/permissions'
import { formatGeoCoord, isUsableGeoCoord } from '../../utils/geoCoords'

/** 演示环境统一默认密码；创建与「重置密码」均使用此值 */
const DEFAULT_DEMO_PASSWORD = 'demo123'

const role = ref('')
const keyword = ref('')
const statusFilter = ref('')
const supplierDeliveryFilter = ref(null)
const list = ref([])
const deliveryOptions = ref([])
const userStore = useUserStore()
const drawerVisible = ref(false)
const editingId = ref(null)
const locationVisible = ref(false)
const locationRow = ref(null)
const mapRef = ref(null)
const amap = ref(null)
const marker = ref(null)
const overviewVisible = ref(false)
const overviewMapRef = ref(null)
const overviewAmap = ref(null)
const overviewMarkers = ref([])
const overviewInfoWindow = ref(null)
const overviewRoleFilter = ref('')
const form = reactive({
  username: '',
  password: DEFAULT_DEMO_PASSWORD,
  role: 'client',
  company_name: '',
  contact_phone: '',
  address: '',
  lng: null,
  lat: null,
  status: 'active',
  return_review_required: false,
})
const lastTipItems = ref([])

const accountMapWrapRef = ref(null)
const accountMap = ref(null)
const accountMarker = ref(null)

const buildAccountPayload = (password = (form.password || '').trim() || DEFAULT_DEMO_PASSWORD) => ({
  username: form.username,
  password,
  role: form.role,
  company_name: form.company_name,
  contact_phone: form.contact_phone,
  address: form.address,
  lng: Number.isFinite(Number(form.lng)) ? Number(form.lng) : null,
  lat: Number.isFinite(Number(form.lat)) ? Number(form.lat) : null,
  status: form.status,
  return_review_required: form.role === 'delivery' ? Boolean(form.return_review_required) : false,
})

const placeOrMoveAccountMarker = (lng, lat, recenter = false) => {
  if (!accountMap.value) return
  if (!accountMarker.value) {
    accountMarker.value = new window.AMap.Marker({
      position: [lng, lat],
      draggable: true,
      cursor: 'move',
    })
    accountMarker.value.setMap(accountMap.value)
    accountMarker.value.on('dragend', (e) => {
      const p = e.lnglat
      if (!p) return
      form.lng = Number(p.lng)
      form.lat = Number(p.lat)
    })
  } else {
    accountMarker.value.setPosition([lng, lat])
  }
  if (recenter) accountMap.value.setZoomAndCenter(15, [lng, lat])
}

const initAccountMap = async () => {
  if (!accountMapWrapRef.value) return
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
  if (accountMap.value) {
    try { accountMap.value.destroy() } catch {}
    accountMap.value = null
    accountMarker.value = null
  }
  const initLng = Number.isFinite(Number(form.lng)) ? Number(form.lng) : 116.407387
  const initLat = Number.isFinite(Number(form.lat)) ? Number(form.lat) : 39.904179
  accountMap.value = new window.AMap.Map(accountMapWrapRef.value, {
    zoom: Number.isFinite(Number(form.lng)) ? 15 : 11,
    center: [initLng, initLat],
  })
  if (Number.isFinite(Number(form.lng)) && Number.isFinite(Number(form.lat))) {
    placeOrMoveAccountMarker(Number(form.lng), Number(form.lat))
  }
  accountMap.value.on('click', (e) => {
    const p = e.lnglat
    if (!p) return
    form.lng = Number(p.lng)
    form.lat = Number(p.lat)
    placeOrMoveAccountMarker(Number(p.lng), Number(p.lat))
  })
}

watch(drawerVisible, async (visible) => {
  if (!visible) {
    if (accountMap.value) {
      try { accountMap.value.destroy() } catch {}
      accountMap.value = null
      accountMarker.value = null
    }
    return
  }
  await nextTick()
  await initAccountMap()
})

const roleLabelMap = {
  client: '采购方',
  supplier: '供货商',
  delivery: '配送方',
  factory: '生产方',
  operation: '运营方',
  monitor: '监管方',
}
const roleTagTypeMap = {
  client: 'success',
  supplier: 'warning',
  delivery: 'primary',
  factory: 'info',
  operation: 'danger',
  monitor: 'default',
}
const accountStatusLabel = (value) => ({ active: '启用', disabled: '停用' }[value] || value)
const roleLabel = (value) => roleLabelMap[value] || value
const roleThemeMap = {
  operation: '#312E81',
  client: '#264A9E',
  delivery: '#1E3A8A',
  factory: '#14532D',
  supplier: '#9A3412',
  monitor: '#111827',
}
const roleThemeColor = (value) => roleThemeMap[value] || '#6b7280'
const roleTagType = (value) => roleTagTypeMap[value] || 'default'
const roleChipStyle = (value, active) => {
  const color = roleThemeColor(value)
  return active
    ? { backgroundColor: color, borderColor: color, color: '#fff' }
    : { backgroundColor: '#fff', borderColor: color, color }
}
const deliveryNameMap = computed(() =>
  Object.fromEntries(
    deliveryOptions.value.map((item) => [item.id, item.company_name || item.username || `配送方#${item.id}`]),
  ),
)

const tableList = computed(() =>
  list.value.map((item) => ({
    ...item,
    username: (item.username || '').trim() || '（未填写）',
    company_name: (item.company_name || '').trim() || '（未填写）',
  })),
)
const locatableRoles = new Set(['delivery', 'client', 'supplier', 'factory'])
const roleLocationMeta = {
  delivery: { label: '配送方', color: '#1E3A8A', icon: 'D' },
  client: { label: '采购方', color: '#264A9E', icon: 'C' },
  supplier: { label: '供货商', color: '#9A3412', icon: 'S' },
  factory: { label: '生产方', color: '#14532D', icon: 'F' },
}
const overviewRows = computed(() =>
  tableList.value.filter((row) => locatableRoles.has(row.role) && isUsableGeoCoord(row.lng, row.lat)),
)
const filteredOverviewRows = computed(() =>
  overviewRows.value.filter((row) => !overviewRoleFilter.value || row.role === overviewRoleFilter.value),
)

const normalizeForm = () => {
  form.username = (form.username || '').trim()
  form.company_name = (form.company_name || '').trim()
  form.contact_phone = (form.contact_phone || '').trim()
  form.address = (form.address || '').trim()
}

const validateForm = () => {
  normalizeForm()
  if (!editingId.value && !form.username) {
    ElMessage.warning('请输入用户名')
    return false
  }
  if (!form.company_name) {
    ElMessage.warning('请输入企业名称')
    return false
  }
  if (['delivery', 'client', 'factory'].includes(form.role)) {
    const roleName = form.role === 'client' ? '采购方' : form.role === 'factory' ? '生产方' : '配送方'
    if (!form.address) {
      ElMessage.warning(`${roleName}请填写地址`)
      return false
    }
    if (!isUsableGeoCoord(form.lng, form.lat)) {
      ElMessage.warning('请从地址联想中选择带坐标的条目，或点击地图扎针定位（不可仅填区县名）')
      return false
    }
  }
  return true
}

const load = async () => {
  list.value = await listAccountsApi({
    role: role.value || undefined,
    keyword: keyword.value?.trim() || undefined,
    status: statusFilter.value || undefined,
    supplier_delivery_id: supplierDeliveryFilter.value || undefined,
  })
}
const resetFilters = () => {
  keyword.value = ''
  statusFilter.value = ''
  supplierDeliveryFilter.value = null
  role.value = ''
  load()
}
const loadDeliveries = async () => {
  deliveryOptions.value = await listAccountsApi({ role: 'delivery' })
}
const create = async () => {
  if (!validateForm()) return
  await createAccountApi(buildAccountPayload())
  drawerVisible.value = false
  await load()
}
const remove = async (id) => {
  await ElMessageBox.confirm('确认删除该账号吗？', '删除确认', {
    type: 'warning',
    confirmButtonText: '确认删除',
    cancelButtonText: '取消',
    customClass: 'danger-confirm-dialog',
    confirmButtonClass: 'danger-confirm-btn',
  })
  await deleteAccountApi(id)
  await load()
}
const openCreate = () => {
  editingId.value = null
  Object.assign(form, {
    username: '',
    password: DEFAULT_DEMO_PASSWORD,
    role: 'client',
    company_name: '',
    contact_phone: '',
    address: '',
    lng: null,
    lat: null,
    status: 'active',
    return_review_required: false,
  })
  drawerVisible.value = true
}
const startEdit = (row) => {
  editingId.value = row.id
  Object.assign(form, {
    ...row,
    password: DEFAULT_DEMO_PASSWORD,
    lng: Number.isFinite(Number(row?.lng)) ? Number(row.lng) : null,
    lat: Number.isFinite(Number(row?.lat)) ? Number(row.lat) : null,
    return_review_required: Boolean(row?.return_review_required),
  })
  drawerVisible.value = true
}
const saveEdit = async () => {
  if (!validateForm()) return
  await updateAccountApi(editingId.value, buildAccountPayload())
  editingId.value = null
  drawerVisible.value = false
  await load()
}

const resetPassword = async () => {
  if (!editingId.value || !validateForm()) return
  try {
    await ElMessageBox.confirm(
      `将把该账号登录密码重置为 ${DEFAULT_DEMO_PASSWORD}，对方需使用新密码登录。是否继续？`,
      '重置密码',
      {
        type: 'warning',
        confirmButtonText: '确认重置',
        cancelButtonText: '取消',
      },
    )
  } catch {
    return
  }
  try {
    await updateAccountApi(editingId.value, buildAccountPayload(DEFAULT_DEMO_PASSWORD))
    ElMessage.success(`密码已重置为 ${DEFAULT_DEMO_PASSWORD}`)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '重置失败')
  }
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
    form.lng = lng
    form.lat = lat
    placeOrMoveAccountMarker(lng, lat, true)
    return
  }
  ElMessage.warning('该联想结果无精确坐标，请换一条或点击地图扎针')
}

const openMapLocation = (row) => {
  if (!isUsableGeoCoord(row?.lng, row?.lat)) {
    ElMessage.warning('该账号暂无有效坐标，请编辑后重新扎针定位')
    return
  }
  const lng = Number(row.lng)
  const lat = Number(row.lat)
  locationRow.value = row
  locationVisible.value = true
}

const openOverviewMap = () => {
  if (!overviewRows.value.length) {
    ElMessage.warning('暂无可展示坐标的采购方/配送方/供货商/生产方账号')
    return
  }
  overviewRoleFilter.value = ''
  overviewVisible.value = true
}

const createMarkerContent = (row) => {
  const meta = roleLocationMeta[row.role] || { color: '#64748b', icon: '?' }
  return `
    <div style="
      width: 28px;
      height: 28px;
      border-radius: 9999px;
      background: ${meta.color};
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      box-shadow: 0 2px 6px rgba(15, 23, 42, 0.25);
      border: 2px solid #fff;
      font-size: 12px;
    ">${meta.icon}</div>
  `
}

const initLocationMap = async () => {
  const lng = Number(locationRow.value?.lng)
  const lat = Number(locationRow.value?.lat)
  if (!Number.isFinite(lng) || !Number.isFinite(lat) || !mapRef.value) return
  const key = import.meta.env.VITE_AMAP_KEY
  if (!key) {
    ElMessage.warning('未配置高德地图 Key（VITE_AMAP_KEY）')
    return
  }
  try {
    await AMapLoader.load({ key, version: '2.0' })
  } catch {
    ElMessage.error('高德地图加载失败，请检查 Key/域名白名单配置')
    return
  }
  const title = locationRow.value?.company_name || locationRow.value?.username || '账号位置'
  if (amap.value) {
    amap.value.destroy()
    amap.value = null
    marker.value = null
  }
  amap.value = new window.AMap.Map(mapRef.value, {
    zoom: 16,
    center: [lng, lat],
  })
  marker.value = new window.AMap.Marker({ position: [lng, lat], title })
  marker.value.setMap(amap.value)
}

const clearOverviewMapObjects = () => {
  if (overviewMarkers.value.length) {
    overviewMarkers.value.forEach((m) => m.setMap(null))
    overviewMarkers.value = []
  }
  if (overviewInfoWindow.value) {
    overviewInfoWindow.value.close()
    overviewInfoWindow.value = null
  }
}

const initOverviewMap = async () => {
  if (!overviewMapRef.value) return
  if (!filteredOverviewRows.value.length) {
    clearOverviewMapObjects()
    if (overviewAmap.value) {
      overviewAmap.value.destroy()
      overviewAmap.value = null
    }
    return
  }
  const key = import.meta.env.VITE_AMAP_KEY
  if (!key) {
    ElMessage.warning('未配置高德地图 Key（VITE_AMAP_KEY）')
    return
  }
  try {
    await AMapLoader.load({ key, version: '2.0' })
  } catch {
    ElMessage.error('高德地图加载失败，请检查 Key/域名白名单配置')
    return
  }
  if (overviewAmap.value) {
    overviewAmap.value.destroy()
    overviewAmap.value = null
  }
  clearOverviewMapObjects()
  overviewAmap.value = new window.AMap.Map(overviewMapRef.value, {
    zoom: 11,
    center: [116.397428, 39.90923],
  })
  overviewInfoWindow.value = new window.AMap.InfoWindow({ offset: new window.AMap.Pixel(0, -20) })
  const points = []
  filteredOverviewRows.value.forEach((row) => {
    const lng = Number(row.lng)
    const lat = Number(row.lat)
    const meta = roleLocationMeta[row.role] || { label: row.role }
    const title = row.company_name || row.username || '未命名'
    const markerObj = new window.AMap.Marker({
      position: [lng, lat],
      title,
      content: createMarkerContent(row),
      anchor: 'bottom-center',
    })
    markerObj.setMap(overviewAmap.value)
    markerObj.on('mouseover', () => {
      const html = `
        <div style="min-width:220px;line-height:1.55;">
          <div style="font-weight:700;color:#111827;">${title}</div>
          <div style="color:#4b5563;">角色：${meta.label}</div>
          <div style="color:#4b5563;">用户名：${row.username || '-'}</div>
          <div style="color:#4b5563;">地址：${row.address || '-'}</div>
        </div>
      `
      overviewInfoWindow.value.setContent(html)
      overviewInfoWindow.value.open(overviewAmap.value, markerObj.getPosition())
    })
    markerObj.on('mouseout', () => {
      if (overviewInfoWindow.value) overviewInfoWindow.value.close()
    })
    overviewMarkers.value.push(markerObj)
    points.push([lng, lat])
  })
  if (points.length) {
    overviewAmap.value.setFitView(overviewMarkers.value, false, [60, 60, 60, 60])
  }
}

watch(locationVisible, async (visible) => {
  if (!visible) return
  await nextTick()
  await initLocationMap()
})

watch(overviewVisible, async (visible) => {
  if (!visible) return
  await nextTick()
  await initOverviewMap()
})
watch(overviewRoleFilter, async () => {
  if (!overviewVisible.value) return
  await nextTick()
  await initOverviewMap()
})

onBeforeUnmount(() => {
  if (amap.value) {
    amap.value.destroy()
    amap.value = null
    marker.value = null
  }
  clearOverviewMapObjects()
  if (overviewAmap.value) {
    overviewAmap.value.destroy()
    overviewAmap.value = null
  }
  if (accountMap.value) {
    try { accountMap.value.destroy() } catch {}
    accountMap.value = null
    accountMarker.value = null
  }
})
onMounted(async () => {
  await Promise.all([load(), loadDeliveries()])
})
</script>

<template>
  <el-card class="mb-3">
    <div class="crud-toolbar">
      <div class="account-filter-section">
        <el-form inline class="crud-form account-filter-form">
          <el-form-item label="关键词">
            <el-input
              v-model="keyword"
              clearable
              placeholder="用户名 / 企业 / 地址"
              style="width: 220px"
              @keyup.enter="load"
              @clear="load"
            />
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="statusFilter" clearable placeholder="全部" style="width: 120px" @change="load">
              <el-option value="" label="全部" />
              <el-option value="active" label="启用" />
              <el-option value="disabled" label="停用" />
            </el-select>
          </el-form-item>
          <el-form-item label="所属配送方">
            <el-select
              v-model="supplierDeliveryFilter"
              clearable
              filterable
              placeholder="全部"
              style="width: 200px"
              @change="load"
            >
              <el-option
                v-for="item in deliveryOptions"
                :key="item.id"
                :label="item.company_name || item.username"
                :value="item.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="角色">
            <el-select v-model="role" clearable placeholder="全部" style="width: 140px" @change="load">
              <el-option value="" label="全部" />
              <el-option value="client" :label="roleLabel('client')" />
              <el-option value="supplier" :label="roleLabel('supplier')" />
              <el-option value="delivery" :label="roleLabel('delivery')" />
              <el-option value="factory" :label="roleLabel('factory')" />
              <el-option value="operation" :label="roleLabel('operation')" />
              <el-option value="monitor" :label="roleLabel('monitor')" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" plain @click="load">查询</el-button>
            <el-button @click="resetFilters">重置</el-button>
          </el-form-item>
        </el-form>
        <div class="role-quick-filters">
        <el-tag
          class="role-chip"
          :effect="!role ? 'dark' : 'plain'"
          :type="!role ? 'danger' : 'info'"
          @click="role = ''; load()"
        >
          全部
        </el-tag>
        <el-tag
          class="role-chip"
          :effect="role === 'client' ? 'dark' : 'plain'"
          :style="roleChipStyle('client', role === 'client')"
          @click="role = 'client'; load()"
        >
          采购方
        </el-tag>
        <el-tag
          class="role-chip"
          :effect="role === 'delivery' ? 'dark' : 'plain'"
          :style="roleChipStyle('delivery', role === 'delivery')"
          @click="role = 'delivery'; load()"
        >
          配送方
        </el-tag>
        <el-tag
          class="role-chip"
          :effect="role === 'supplier' ? 'dark' : 'plain'"
          :style="roleChipStyle('supplier', role === 'supplier')"
          @click="role = 'supplier'; load()"
        >
          供货商
        </el-tag>
        <el-tag
          class="role-chip"
          :effect="role === 'factory' ? 'dark' : 'plain'"
          :style="roleChipStyle('factory', role === 'factory')"
          @click="role = 'factory'; load()"
        >
          生产方
        </el-tag>
        <el-tag
          class="role-chip"
          :effect="role === 'operation' ? 'dark' : 'plain'"
          :style="roleChipStyle('operation', role === 'operation')"
          @click="role = 'operation'; load()"
        >
          运营方
        </el-tag>
        <el-tag
          class="role-chip"
          :effect="role === 'monitor' ? 'dark' : 'plain'"
          :style="roleChipStyle('monitor', role === 'monitor')"
          @click="role = 'monitor'; load()"
        >
          监管方
        </el-tag>
        </div>
      </div>
      <div class="crud-actions">
        <el-button type="info" plain @click="openOverviewMap">位置总览</el-button>
        <el-button v-if="can(userStore.role, 'account:create')" type="primary" class="primary-visible-btn" @click="openCreate">
          新增账号
        </el-button>
      </div>
    </div>
  </el-card>
  <el-card>
    <template #header><span class="font-semibold">账号列表</span></template>
    <el-table :data="tableList" border>
      <el-table-column prop="id" label="编号" width="70" />
      <el-table-column prop="username" label="用户名" />
      <el-table-column prop="role" label="角色">
        <template #default="{ row }">
          <el-tag
            :type="roleTagType(row.role)"
            effect="dark"
            :style="{ backgroundColor: roleThemeColor(row.role), borderColor: roleThemeColor(row.role), color: '#fff' }"
          >
            {{ roleLabel(row.role) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="company_name" label="企业" />
      <el-table-column prop="address" label="地址" min-width="220" show-overflow-tooltip />
      <el-table-column label="坐标" min-width="180">
        <template #default="{ row }">
          <el-button
            v-if="locatableRoles.has(row.role) && isUsableGeoCoord(row.lng, row.lat)"
            type="primary"
            link
            class="coord-link"
            @click="openMapLocation(row)"
          >
            <el-icon><Location /></el-icon>
            {{ formatGeoCoord(row.lng, row.lat) }}
          </el-button>
          <span v-else-if="locatableRoles.has(row.role)" class="coord-invalid">未定位</span>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="所属配送方" width="170">
        <template #default="{ row }">
          {{ row.role === 'supplier' ? (deliveryNameMap[row.supplier_delivery_id] || '未绑定') : '—' }}
        </template>
      </el-table-column>
      <el-table-column label="退货审核" width="120">
        <template #default="{ row }">
          <el-tag v-if="row.role === 'delivery'" :type="row.return_review_required ? 'warning' : 'info'" size="small">
            {{ row.return_review_required ? '需审核' : '免审核' }}
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态">
        <template #default="{ row }">{{ accountStatusLabel(row.status) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="center">
        <template #default="{ row }">
          <div class="op-btns">
            <el-button
              v-if="can(userStore.role, 'account:update') && row.role !== 'supplier'"
              size="small"
              @click="startEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="can(userStore.role, 'account:delete') && row.role !== 'supplier'"
              size="small"
              type="danger"
              plain
              @click="remove(row.id)"
            >
              删除
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-drawer v-model="drawerVisible" :title="editingId ? '编辑账号' : '新增账号'" size="520px">
    <el-form label-width="100px">
      <el-form-item label="用户名"><el-input v-model="form.username" :disabled="!!editingId" /></el-form-item>
      <el-form-item v-if="editingId" label="登录密码">
        <div class="password-reset-block">
          <p class="field-tip">出于安全考虑，不显示当前密码。若对方忘记密码，可点击下方按钮重置。</p>
          <el-button
            v-if="can(userStore.role, 'account:update')"
            type="warning"
            plain
            @click="resetPassword"
          >
            重置为 {{ DEFAULT_DEMO_PASSWORD }}
          </el-button>
        </div>
      </el-form-item>
      <el-form-item v-if="!editingId" label="初始密码">
        <el-input v-model="form.password" disabled />
        <div class="field-tip">新账号默认密码为 {{ DEFAULT_DEMO_PASSWORD }}，请提醒对方首次登录后及时修改。</div>
      </el-form-item>
      <el-form-item label="角色">
        <el-select v-model="form.role" style="width: 130px">
          <el-option value="client" :label="roleLabel('client')" />
          <el-option value="delivery" :label="roleLabel('delivery')" />
          <el-option value="factory" :label="roleLabel('factory')" />
          <el-option value="operation" :label="roleLabel('operation')" />
          <el-option value="monitor" :label="roleLabel('monitor')" />
        </el-select>
      </el-form-item>
      <el-form-item label="企业"><el-input v-model="form.company_name" /></el-form-item>
      <el-form-item label="联系方式"><el-input v-model="form.contact_phone" /></el-form-item>
      <el-form-item v-if="['delivery', 'client', 'factory'].includes(form.role)" label="地址">
        <el-autocomplete
          v-model="form.address"
          :fetch-suggestions="queryAddressTips"
          class="address-input"
          clearable
          placeholder="请输入并从联想结果选择地址"
          @select="onAddressSelect"
        />
        <div class="field-tip">
          {{
            form.role === 'client'
              ? '采购方将基于该地址解析高德坐标，用于下单与履约链路。'
              : form.role === 'factory'
                ? '生产方将基于该地址解析高德坐标，用于质检履约与位置展示。'
                : '配送方将基于该地址解析高德坐标，用于路线与分单算法。'
          }}
        </div>
      </el-form-item>
      <el-form-item v-if="['delivery', 'client', 'factory'].includes(form.role)" label="精确位置">
        <div ref="accountMapWrapRef" class="account-map" />
        <div class="account-coord-row">
          <span>经度：<strong>{{ isUsableGeoCoord(form.lng, form.lat) ? Number(form.lng).toFixed(6) : '—' }}</strong></span>
          <span>纬度：<strong>{{ isUsableGeoCoord(form.lng, form.lat) ? Number(form.lat).toFixed(6) : '—' }}</strong></span>
          <span class="account-coord-tip">须从联想选点或地图扎针；仅填「朝阳」「海淀」等无法保存</span>
        </div>
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="form.status" style="width: 130px">
          <el-option value="active" label="启用" />
          <el-option value="disabled" label="停用" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="form.role === 'delivery'" label="退货审核">
        <el-switch
          v-model="form.return_review_required"
          active-text="少收退货需配送商审核"
          inactive-text="直接确认"
        />
        <div class="field-tip">开启后，智能秤少收退货单会先进入待审核，配送商通过后才扣减账单。</div>
      </el-form-item>
      <el-button v-if="!editingId" type="primary" class="submit-btn" @click="create">确认新增</el-button>
      <el-button v-else type="primary" class="submit-btn" @click="saveEdit">保存修改</el-button>
    </el-form>
  </el-drawer>

  <el-dialog
    v-model="locationVisible"
    width="780px"
    destroy-on-close
    :title="`地图定位 - ${locationRow?.company_name || locationRow?.username || ''}`"
  >
    <div class="map-meta">
      <div>角色：{{ roleLabel(locationRow?.role) }}</div>
      <div>地址：{{ locationRow?.address || '—' }}</div>
      <div>坐标：{{ locationRow?.lng }}, {{ locationRow?.lat }}（高德/GCJ-02）</div>
    </div>
    <div ref="mapRef" class="map-canvas"></div>
  </el-dialog>

  <el-dialog v-model="overviewVisible" width="980px" destroy-on-close title="账号位置总览（采购方/配送方/供货商/生产方）">
    <div class="overview-toolbar">
      <div class="legend-item legend-item-all" :class="{ active: !overviewRoleFilter }" @click="overviewRoleFilter = ''">
        <span class="legend-text">全部</span>
      </div>
      <div
        class="legend-item"
        :class="{ active: overviewRoleFilter === 'delivery' }"
        @click="overviewRoleFilter = 'delivery'"
      >
        <span class="legend-dot legend-dot-delivery">D</span>
        <span>配送方</span>
      </div>
      <div
        class="legend-item"
        :class="{ active: overviewRoleFilter === 'client' }"
        @click="overviewRoleFilter = 'client'"
      >
        <span class="legend-dot legend-dot-client">C</span>
        <span>采购方</span>
      </div>
      <div
        class="legend-item"
        :class="{ active: overviewRoleFilter === 'supplier' }"
        @click="overviewRoleFilter = 'supplier'"
      >
        <span class="legend-dot legend-dot-supplier">S</span>
        <span>供货商</span>
      </div>
      <div
        class="legend-item"
        :class="{ active: overviewRoleFilter === 'factory' }"
        @click="overviewRoleFilter = 'factory'"
      >
        <span class="legend-dot legend-dot-factory">F</span>
        <span>生产方</span>
      </div>
      <span class="overview-count">
        共 {{ filteredOverviewRows.length }} / {{ overviewRows.length }} 个有坐标账号（鼠标移到标记可看名称）
      </span>
    </div>
    <div ref="overviewMapRef" class="overview-map-canvas"></div>
  </el-dialog>
</template>

<style scoped>
.crud-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.account-filter-section {
  flex: 1;
  min-width: 0;
}

.account-filter-form {
  margin-bottom: 4px;
}

.crud-form {
  margin-bottom: 0;
}

.crud-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.role-quick-filters {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.role-chip {
  cursor: pointer;
  user-select: none;
}

.op-btns {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.password-reset-block {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
}

.password-reset-block .field-tip {
  margin-top: 0;
}

.field-tip {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
  line-height: 1.4;
}

.submit-btn {
  min-width: 96px;
}

.address-input {
  width: 100%;
}

.account-map {
  width: 100%;
  height: 320px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  overflow: hidden;
}

.account-coord-row {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 8px;
  font-size: 13px;
  color: #475569;
}

.account-coord-row strong {
  color: #0f172a;
}

.account-coord-tip {
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

.overview-toolbar {
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  color: #606266;
  font-size: 13px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid #d1d5db;
  border-radius: 9999px;
  padding: 4px 10px;
  cursor: pointer;
  user-select: none;
  background: #fff;
  transition: all 0.2s ease;
}

.legend-item:hover {
  border-color: #9ca3af;
}

.legend-item.active {
  border-color: #374151;
  background: #f3f4f6;
}

.legend-item-all .legend-text {
  font-weight: 600;
  color: #111827;
}

.legend-dot {
  width: 22px;
  height: 22px;
  border-radius: 9999px;
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
}

.legend-dot-delivery {
  background: #1E3A8A;
}

.legend-dot-client {
  background: #264A9E;
}

.legend-dot-supplier {
  background: #9A3412;
}

.legend-dot-factory {
  background: #14532D;
}

.overview-count {
  margin-left: auto;
  color: #909399;
}

.overview-map-canvas {
  width: 100%;
  height: 520px;
  border-radius: 8px;
}

:deep(.primary-visible-btn.el-button--primary),
:deep(.submit-btn.el-button--primary) {
  color: #fff !important;
}

</style>
