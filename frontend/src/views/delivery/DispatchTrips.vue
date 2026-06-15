<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  appendDispatchTripStopsApi,
  cancelDispatchTripApi,
  deliveryOrderPoolApi,
  departDispatchTripApi,
  dispatchPlanningSummaryApi,
  exceptionDepartDispatchTripApi,
  getDispatchTripApi,
  getVehicleLocationApi,
  listDeliveryVehiclesApi,
  listDispatchTripsApi,
  markDispatchItemLoadedApi,
  updateDispatchTripApi,
  uploadDispatchExceptionPhotoApi,
} from '../../api/delivery'

const route = useRoute()
const router = useRouter()
const todayYmd = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const statusOptions = [
  { label: '全部', value: '' },
  { label: '待发车', value: '待发车' },
  { label: '有阻塞', value: '有阻塞' },
  { label: '运输中', value: '运输中' },
  { label: '已取消', value: '已取消' },
]
const reasonOptions = [
  { label: '供应商迟到', value: 'supplier_late' },
  { label: '未出库', value: 'not_shipped' },
  { label: '质量问题', value: 'quality' },
  { label: '现场缺货', value: 'missing' },
  { label: '取消随车', value: 'cancelled' },
  { label: '其他异常', value: 'other' },
]
const readyStatuses = new Set(['待装车', '已装车'])
const notLoadedStatuses = new Set(['滞留未装', '取消随车', '供应商迟到', '质量问题', '现场缺货', '其他异常'])

const filters = reactive({
  planningDate: todayYmd(),
  status: '',
})
const loading = ref(false)
const trips = ref([])
const activeTrip = ref(null)
const detailVisible = ref(false)
const detailLoading = ref(false)
const vehicleLocation = ref(null)
const vehicleLocationLoading = ref(false)
const vehicleLocationError = ref('')
const exceptionVisible = ref(false)
const exceptionSubmitting = ref(false)
const uploadingKey = ref('')
const exceptionSelectedIds = ref([])
const exceptionForm = reactive({
  reason_detail: '',
  notify_customer: true,
  include_supplier_score: true,
  items: {},
})
const planningSummary = ref(null)
const appendDialogVisible = ref(false)
const appendSubmitting = ref(false)
const appendOrderIds = ref([])
const appendOrderPool = ref([])
const editVehicleId = ref(null)
const editSubmitting = ref(false)
const deliveryVehicles = ref([])

const validDate = (value) => /^\d{4}-\d{2}-\d{2}$/.test(String(value || ''))

const applyQueryFilters = () => {
  const qDate = route.query.date || route.query.planning_date
  if (validDate(qDate)) filters.planningDate = String(qDate)
  const qStatus = String(route.query.status || '')
  if (statusOptions.some((i) => i.value === qStatus)) filters.status = qStatus
}

const loadTrips = async () => {
  loading.value = true
  try {
    const params = { planning_date: filters.planningDate }
    if (filters.status) params.status = filters.status
    trips.value = await listDispatchTripsApi(params)
    await loadPlanningSummary()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '发车计划加载失败')
  } finally {
    loading.value = false
  }
}

const loadPlanningSummary = async () => {
  try {
    planningSummary.value = await dispatchPlanningSummaryApi(filters.planningDate)
  } catch {
    planningSummary.value = null
  }
}

const loadDeliveryVehicles = async () => {
  try {
    deliveryVehicles.value = (await listDeliveryVehiclesApi()) || []
  } catch {
    deliveryVehicles.value = []
  }
}

const unplannedOrderCount = computed(() => Number(planningSummary.value?.unplanned_order_count ?? 0))

const goRoutePlan = () => {
  router.push({ path: '/delivery/smart-routing', query: { tab: 'route', date: filters.planningDate } })
}

const occupancyTagType = (row) => {
  if (row?.occupancy_active) return 'warning'
  if (row?.status === '已完成' || row?.status === '已取消') return 'info'
  return 'info'
}

const editableStops = computed(() =>
  [...(activeTrip.value?.stops || [])].sort(
    (a, b) => Number(a.sequence || 0) - Number(b.sequence || 0) || Number(a.id) - Number(b.id),
  ),
)

const openAppendDialog = async () => {
  if (!canOperateTrip.value) return
  appendSubmitting.value = false
  appendOrderIds.value = []
  try {
    appendOrderPool.value = await deliveryOrderPoolApi(120, filters.planningDate, {
      statuses: ['配货'],
      excludeActiveDispatch: true,
      includeDispatchReadiness: true,
    })
    appendOrderPool.value = (appendOrderPool.value || []).filter((row) => row.dispatch_save_ready)
  } catch {
    appendOrderPool.value = []
  }
  appendDialogVisible.value = true
}

const submitAppendStops = async () => {
  if (!activeTrip.value?.id || !appendOrderIds.value.length) {
    ElMessage.warning('请选择至少一个配货订单')
    return
  }
  appendSubmitting.value = true
  try {
    activeTrip.value = await appendDispatchTripStopsApi(activeTrip.value.id, {
      order_ids: appendOrderIds.value.map(Number),
    })
    appendDialogVisible.value = false
    ElMessage.success('已追加站点并重算 ETA')
    await loadTrips()
    await loadPlanningSummary()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '追加站点失败')
  } finally {
    appendSubmitting.value = false
  }
}

const moveStop = async (idx, dir) => {
  if (!activeTrip.value?.id || !canOperateTrip.value) return
  const stops = editableStops.value
  const nextIdx = idx + dir
  if (nextIdx < 0 || nextIdx >= stops.length) return
  const orderIds = stops.map((s) => Number(s.order_id))
  ;[orderIds[idx], orderIds[nextIdx]] = [orderIds[nextIdx], orderIds[idx]]
  editSubmitting.value = true
  try {
    activeTrip.value = await updateDispatchTripApi(activeTrip.value.id, { stop_order_ids: orderIds })
    ElMessage.success('站点顺序已更新')
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '调序失败')
  } finally {
    editSubmitting.value = false
  }
}

const removeStop = async (stop) => {
  if (!activeTrip.value?.id || !canOperateTrip.value) return
  try {
    await ElMessageBox.confirm(`确认从车次中移除订单 ${stop.order_no}？`, '移除站点', { type: 'warning' })
    activeTrip.value = await updateDispatchTripApi(activeTrip.value.id, {
      remove_order_ids: [Number(stop.order_id)],
    })
    ElMessage.success('已移除站点')
    await loadTrips()
    await loadPlanningSummary()
  } catch (err) {
    if (err === 'cancel') return
    ElMessage.error(err?.response?.data?.detail || '移除失败')
  }
}

const changeTripVehicle = async () => {
  if (!activeTrip.value?.id || !editVehicleId.value) return
  editSubmitting.value = true
  try {
    activeTrip.value = await updateDispatchTripApi(activeTrip.value.id, {
      vehicle_id: Number(editVehicleId.value),
    })
    ElMessage.success('车辆已更换')
    await loadTrips()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '换车失败')
  } finally {
    editSubmitting.value = false
  }
}

const loadTripVehicleLocation = async (trip = activeTrip.value) => {
  vehicleLocation.value = null
  vehicleLocationError.value = ''
  if (!trip?.vehicle_id) {
    vehicleLocationError.value = '当前车次未绑定车辆'
    return
  }
  vehicleLocationLoading.value = true
  try {
    vehicleLocation.value = await getVehicleLocationApi(trip.vehicle_id)
  } catch (err) {
    vehicleLocationError.value = err?.response?.data?.detail || '暂无车辆位置'
  } finally {
    vehicleLocationLoading.value = false
  }
}

const openTrip = async (row) => {
  detailVisible.value = true
  detailLoading.value = true
  try {
    activeTrip.value = await getDispatchTripApi(row.id)
    editVehicleId.value = activeTrip.value?.vehicle_id ?? null
    await loadTripVehicleLocation(activeTrip.value)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '车次详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

const reloadActiveTrip = async () => {
  if (!activeTrip.value?.id) return
  activeTrip.value = await getDispatchTripApi(activeTrip.value.id)
  await loadTripVehicleLocation(activeTrip.value)
}

const statusTag = (status) => {
  if (status === '运输中' || status === '已完成') return 'success'
  if (status === '有阻塞') return 'warning'
  if (status === '已取消') return 'info'
  return ''
}

const itemTag = (status) => {
  if (status === '已装车') return 'success'
  if (status === '待装车') return ''
  if (status === '未分检') return 'warning'
  return 'danger'
}

const isBlockingItem = (item) => !readyStatuses.has(String(item?.status || ''))
const isFinalNotLoaded = (item) => notLoadedStatuses.has(String(item?.status || ''))

const overview = computed(() => {
  const total = trips.value.length
  const blocked = trips.value.filter((i) => i.status === '有阻塞').length
  const waiting = trips.value.filter((i) => i.status === '待发车').length
  const running = trips.value.filter((i) => i.status === '运输中').length
  const allocations = trips.value.reduce((sum, i) => sum + Number(i.total_allocations || 0), 0)
  return { total, blocked, waiting, running, allocations }
})

const stopMap = computed(() => {
  const map = new Map()
  for (const stop of activeTrip.value?.stops || []) map.set(Number(stop.id), stop)
  return map
})

const supplierSections = computed(() => {
  const map = new Map()
  for (const item of activeTrip.value?.items || []) {
    const key = `${item.supplier_id || 0}:${item.supplier_name || '未知供应商'}`
    if (!map.has(key)) {
      map.set(key, {
        key,
        supplier_id: Number(item.supplier_id || 0),
        supplier_name: item.supplier_name || '未知供应商',
        total: 0,
        ready: 0,
        loaded: 0,
        blocked: 0,
        notLoaded: 0,
        items: [],
      })
    }
    const group = map.get(key)
    group.total += 1
    if (readyStatuses.has(String(item.status))) group.ready += 1
    if (item.status === '已装车') group.loaded += 1
    if (isBlockingItem(item)) group.blocked += 1
    if (isFinalNotLoaded(item)) group.notLoaded += 1
    group.items.push(item)
  }
  return [...map.values()].sort((a, b) => {
    if (a.blocked !== b.blocked) return b.blocked - a.blocked
    if (a.notLoaded !== b.notLoaded) return b.notLoaded - a.notLoaded
    return a.supplier_id - b.supplier_id
  })
})

const canOperateTrip = computed(() => {
  const status = activeTrip.value?.status
  return status === '待发车' || status === '有阻塞'
})

const canNormalDepart = computed(() => {
  if (!canOperateTrip.value) return false
  const items = activeTrip.value?.items || []
  return items.length > 0 && items.every((item) => readyStatuses.has(String(item.status)))
})

const tripProgressText = (row) => {
  const total = Number(row.total_allocations || 0)
  const ready = Number(row.ready_count || 0)
  const blocked = Number(row.blocked_count || 0)
  const notLoaded = Number(row.not_loaded_count || 0)
  if (notLoaded > 0) return `已装/可装 ${ready}/${total} · 未随车 ${notLoaded}`
  if (blocked > 0) return `可装 ${ready}/${total} · 阻塞 ${blocked}`
  return `可发 ${ready}/${total}`
}

const riskMeta = (risk) => {
  const text = String(risk || '')
  if (text.includes('高德') || text.includes('降级') || text.includes('直线距离') || text.includes('经验车速')) {
    return { label: '地图降级', type: 'warning' }
  }
  if (text.includes('限行') || text.includes('外地牌') || text.includes('未纳入本次智能排线')) {
    return { label: '车辆限行', type: 'warning' }
  }
  if (text.includes('晚于') || text.includes('时段') || text.includes('窗口') || text.includes('改期')) {
    return { label: '时窗风险', type: 'warning' }
  }
  if (text.includes('坐标') || text.includes('估算路径')) {
    return { label: '坐标缺失', type: 'info' }
  }
  if (text.includes('载重') || text.includes('容积') || text.includes('装载')) {
    return { label: '装载风险', type: 'warning' }
  }
  if (text.includes('禁行') || text.includes('避让') || text.includes('avoid')) {
    return { label: '禁行避让', type: 'danger' }
  }
  return { label: '其他风险', type: 'warning' }
}

const riskBadges = (row) => {
  const risks = Array.isArray(row?.risk_alerts) ? row.risk_alerts : []
  const map = new Map()
  for (const risk of risks) {
    const meta = riskMeta(risk)
    if (!map.has(meta.label)) map.set(meta.label, meta)
  }
  return [...map.values()]
}

const riskSourceTip = '风险为保存发车计划时的智能排线快照；如已关闭 VPN 并恢复高德接口，请重新生成智能路线后再保存车次。'

const driverAppVisible = (row) => Boolean(String(row?.driver_app?.login_vehicle_no || row?.vehicle_no || '').trim())
const driverLoginPlate = (row) => String(row?.driver_app?.login_vehicle_no || row?.vehicle_no || '').trim()
const driverAppHint = (row) => {
  if (!driverAppVisible(row)) return '未绑定车牌，司机端不可见'
  if (row?.status === '运输中') return '司机端可开始配送并确认送达'
  if (row?.status === '已完成') return '司机端已完成本车次'
  if (row?.status === '已取消') return '车次已取消，司机端不再操作'
  return '司机端可查看，调度端发车后才能操作'
}
const driverAppTagType = (row) => {
  if (!driverAppVisible(row)) return 'danger'
  if (row?.status === '运输中' || row?.status === '已完成') return 'success'
  if (row?.status === '已取消') return 'info'
  return 'warning'
}
const vehicleLocationTagType = computed(() => {
  if (vehicleLocationLoading.value) return 'info'
  if (!vehicleLocation.value) return 'warning'
  return vehicleLocation.value.online_status === 'online' ? 'success' : 'warning'
})
const vehicleLocationTitle = computed(() => {
  if (vehicleLocationLoading.value) return '正在读取车辆北斗位置'
  if (!vehicleLocation.value) return vehicleLocationError.value || '暂无车辆位置'
  return vehicleLocation.value.online_status === 'online' ? '北斗定位在线' : '北斗定位离线'
})
const vehicleLocationCoordText = computed(() => {
  if (!vehicleLocation.value) return '暂无坐标'
  const lng = Number(vehicleLocation.value.lng)
  const lat = Number(vehicleLocation.value.lat)
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return '暂无坐标'
  return `${lng.toFixed(6)}, ${lat.toFixed(6)}`
})
const vehicleLocationTimeText = computed(() => {
  if (!vehicleLocation.value) return '暂无上报时间'
  return vehicleLocation.value.reported_at || vehicleLocation.value.updated_at || '暂无上报时间'
})
const copyDriverLogin = async (row) => {
  const plate = driverLoginPlate(row)
  if (!plate) {
    ElMessage.warning('当前车次未绑定车牌')
    return
  }
  const text = `司机端登录：车牌号 ${plate}，密码 demo123`
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('司机端登录信息已复制')
  } catch (err) {
    ElMessage.info(text)
  }
}

const itemStopText = (item) => {
  const stop = stopMap.value.get(Number(item.stop_id))
  if (!stop) return `订单 #${item.order_id || '-'}`
  return `${stop.order_no || '-'} · ${stop.client_name || '-'} / ${stop.canteen_name || '-'}`
}

const defaultReasonCode = (item) => {
  const status = String(item?.status || '')
  if (status === '未出库') return 'not_shipped'
  if (status === '质量问题') return 'quality'
  if (status === '现场缺货') return 'missing'
  if (status === '取消随车') return 'cancelled'
  return 'supplier_late'
}

const ensureExceptionItemForm = (item) => {
  const key = Number(item.allocation_id)
  if (!exceptionForm.items[key]) {
    exceptionForm.items[key] = {
      reason_code: defaultReasonCode(item),
      reason_detail: '',
      attachments_json: [],
    }
  }
  return exceptionForm.items[key]
}

const openExceptionDrawer = () => {
  if (!activeTrip.value?.id) return
  exceptionForm.reason_detail = ''
  exceptionForm.notify_customer = true
  exceptionForm.include_supplier_score = true
  exceptionForm.items = {}
  const defaultSelected = []
  for (const item of activeTrip.value.items || []) {
    ensureExceptionItemForm(item)
    if (isBlockingItem(item)) defaultSelected.push(Number(item.allocation_id))
  }
  exceptionSelectedIds.value = defaultSelected
  exceptionVisible.value = true
}

const isExceptionSelected = (item) => exceptionSelectedIds.value.includes(Number(item.allocation_id))

const onExceptionPhotoChange = async (file, item) => {
  if (!activeTrip.value?.id || !item?.allocation_id) return
  const raw = file?.raw
  if (!raw) return
  if (!String(raw.type || '').startsWith('image/')) {
    ElMessage.warning('仅允许上传图片')
    return
  }
  const key = `${item.allocation_id}:${raw.name}`
  uploadingKey.value = key
  try {
    const fd = new FormData()
    fd.append('file', raw)
    const res = await uploadDispatchExceptionPhotoApi(activeTrip.value.id, fd)
    const form = ensureExceptionItemForm(item)
    form.attachments_json.push(res.url)
    if (!isExceptionSelected(item)) exceptionSelectedIds.value.push(Number(item.allocation_id))
    ElMessage.success('照片已上传')
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '照片上传失败')
  } finally {
    uploadingKey.value = ''
  }
}

const removeExceptionPhoto = (item, idx) => {
  const form = ensureExceptionItemForm(item)
  form.attachments_json.splice(idx, 1)
}

const markLoaded = async (item, loaded) => {
  try {
    activeTrip.value = await markDispatchItemLoadedApi(activeTrip.value.id, item.id, { loaded })
    await loadTrips()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '装车状态更新失败')
  }
}

const departTrip = async () => {
  if (!activeTrip.value?.id) return
  try {
    await ElMessageBox.confirm(
      `确认车次 ${activeTrip.value.route_no} 整车发车？系统会将车次内订单推进到「发货」状态。`,
      '整车发车',
      {
        type: 'warning',
        confirmButtonText: '确认发车',
        cancelButtonText: '取消',
        customClass: 'dispatch-confirm-dialog',
        confirmButtonClass: 'dispatch-confirm-btn',
        cancelButtonClass: 'dispatch-cancel-btn',
      },
    )
    activeTrip.value = await departDispatchTripApi(activeTrip.value.id)
    await loadTrips()
    ElMessage.success('车次已发车')
  } catch (err) {
    if (err === 'cancel') return
    ElMessage.error(err?.response?.data?.detail || '发车失败')
  }
}

const submitExceptionDepart = async () => {
  if (!activeTrip.value?.id) return
  const selected = new Set(exceptionSelectedIds.value.map((i) => Number(i)))
  const blockers = (activeTrip.value.items || []).filter(isBlockingItem)
  const missingBlockers = blockers.filter((item) => !selected.has(Number(item.allocation_id)))
  if (missingBlockers.length) {
    ElMessage.warning('阻塞分单必须填写异常原因后才能异常发车')
    return
  }
  if (!selected.size) {
    ElMessage.warning('请选择至少一个未随车分单')
    return
  }
  const reasonDetail = exceptionForm.reason_detail.trim()
  if (!reasonDetail) {
    ElMessage.warning('请填写异常发车总说明')
    return
  }
  const items = (activeTrip.value.items || [])
    .filter((item) => selected.has(Number(item.allocation_id)))
    .map((item) => {
      const form = ensureExceptionItemForm(item)
      return {
        allocation_id: Number(item.allocation_id),
        reason_code: form.reason_code || defaultReasonCode(item),
        reason_detail: form.reason_detail || reasonDetail,
        attachments_json: form.attachments_json || [],
      }
    })
  exceptionSubmitting.value = true
  try {
    activeTrip.value = await exceptionDepartDispatchTripApi(activeTrip.value.id, {
      reason_detail: reasonDetail,
      notify_customer: exceptionForm.notify_customer,
      include_supplier_score: exceptionForm.include_supplier_score,
      items,
    })
    exceptionVisible.value = false
    await loadTrips()
    ElMessage.success('已异常发车，未随车分单已记录')
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '异常发车失败')
  } finally {
    exceptionSubmitting.value = false
  }
}

const cancelTrip = async (row = activeTrip.value) => {
  if (!row?.id) return
  try {
    const { value } = await ElMessageBox.prompt(`请输入取消车次 ${row.route_no} 的原因`, '取消车次', {
      confirmButtonText: '确认取消',
      cancelButtonText: '返回',
      customClass: 'dispatch-confirm-dialog',
      confirmButtonClass: 'dispatch-confirm-btn dispatch-confirm-btn-danger',
      cancelButtonClass: 'dispatch-cancel-btn',
      inputPlaceholder: '例如：重新排线、车辆临时不可用',
      inputValidator: (v) => Boolean(String(v || '').trim()) || '请填写取消原因',
    })
    await cancelDispatchTripApi(row.id, { reason: String(value || '').trim() })
    if (activeTrip.value?.id === row.id) {
      activeTrip.value = await getDispatchTripApi(row.id)
    }
    await loadTrips()
    ElMessage.success('车次已取消')
  } catch (err) {
    if (err === 'cancel') return
    ElMessage.error(err?.response?.data?.detail || '取消车次失败')
  }
}

watch(
  () => [route.query.date, route.query.planning_date, route.query.status],
  async () => {
    applyQueryFilters()
    await loadTrips()
  },
)

onMounted(() => {
  applyQueryFilters()
  loadDeliveryVehicles()
  loadTrips()
})
</script>

<template>
  <div class="dispatch-page">
    <section class="dispatch-head">
      <div>
        <div class="eyebrow">智能调度闭环</div>
        <h2>发车计划</h2>
        <p>从智能排线保存车次后，在这里处理装车、阻塞、异常发车和未随车留痕。</p>
      </div>
      <div class="head-actions">
        <el-date-picker v-model="filters.planningDate" type="date" value-format="YYYY-MM-DD" />
        <el-select v-model="filters.status" class="status-select">
          <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
        <el-button type="primary" :loading="loading" @click="loadTrips">刷新</el-button>
      </div>
    </section>

    <el-alert :closable="false" type="info" class="mb-3" title="占用与释放规则">
      <template #default>
        占用按<strong>计划日期</strong>计算：仅同日未完成车次占用车/单。释放 = 全部站点送达（已完成）或取消车次；无需客户确认收货。
      </template>
    </el-alert>

    <el-alert
      v-if="unplannedOrderCount > 0"
      :closable="false"
      type="warning"
      class="mb-3"
      show-icon
    >
      <template #title>
        {{ filters.planningDate }} 尚有 {{ unplannedOrderCount }} 单未排入车次
      </template>
      <template #default>
        <el-button link type="primary" @click="goRoutePlan">去智能排线选单</el-button>
        <span class="muted"> · 或对未发车车次使用「追加站点」</span>
      </template>
    </el-alert>

    <section class="stat-grid">
      <div class="stat-card">
        <span>车次数</span>
        <strong>{{ overview.total }}</strong>
      </div>
      <div class="stat-card ok">
        <span>待发车</span>
        <strong>{{ overview.waiting }}</strong>
      </div>
      <div class="stat-card warn">
        <span>有阻塞</span>
        <strong>{{ overview.blocked }}</strong>
      </div>
      <div class="stat-card">
        <span>分单数</span>
        <strong>{{ overview.allocations }}</strong>
      </div>
    </section>

    <el-card shadow="never" class="trip-card">
      <template #header>
        <div class="card-head">
          <span>车次列表</span>
          <span class="muted">绿色可发，琥珀需处理，红色为未随车/异常。</span>
        </div>
      </template>
      <el-table v-loading="loading" :data="trips" border row-key="id" empty-text="当前日期暂无发车计划">
        <el-table-column prop="route_no" label="车次号" min-width="140" fixed />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" effect="dark">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="占用" width="90">
          <template #default="{ row }">
            <el-tag :type="occupancyTagType(row)" effect="plain" size="small">
              {{ row.occupancy_label || (row.occupancy_active ? '占用中' : '已释放') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="司机/车辆" min-width="180">
          <template #default="{ row }">
            <div class="strong">{{ row.driver_name || '未登记司机' }}</div>
            <div class="muted">{{ row.vehicle_no || '未分配车辆' }}</div>
            <div class="driver-login">
              <el-tag size="small" :type="driverAppTagType(row)" effect="plain">{{ driverAppVisible(row) ? '司机端可见' : '司机端不可见' }}</el-tag>
              <el-button v-if="driverAppVisible(row)" link type="primary" @click.stop="copyDriverLogin(row)">复制登录</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="计划" min-width="170">
          <template #default="{ row }">
            <div>{{ row.planning_date }} {{ row.departure_time || '' }}</div>
            <div class="muted">{{ row.total_orders || 0 }} 单 · {{ row.distance_km ?? '-' }} km</div>
          </template>
        </el-table-column>
        <el-table-column label="装车/阻塞" min-width="190">
          <template #default="{ row }">
            <div>{{ tripProgressText(row) }}</div>
            <el-progress
              :percentage="row.total_allocations ? Math.round((Number(row.ready_count || 0) / Number(row.total_allocations || 1)) * 100) : 0"
              :stroke-width="8"
              :show-text="false"
              class="mini-progress"
            />
          </template>
        </el-table-column>
        <el-table-column label="风险" min-width="220">
          <template #default="{ row }">
            <span v-if="!(row.risk_alerts || []).length" class="muted">无明显风险</span>
            <div v-else class="risk-cell">
              <el-tag v-for="badge in riskBadges(row).slice(0, 2)" :key="badge.label" :type="badge.type" class="mr-1 mb-1">
                {{ badge.label }}
              </el-tag>
              <el-popover placement="left" :width="420" trigger="click">
                <template #reference>
                  <el-button link type="primary" class="risk-more">查看全部</el-button>
                </template>
                <div class="risk-popover">
                  <strong>风险说明</strong>
                  <p>{{ riskSourceTip }}</p>
                  <ol>
                    <li v-for="(risk, idx) in row.risk_alerts || []" :key="idx">{{ risk }}</li>
                  </ol>
                </div>
              </el-popover>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="openTrip(row)">处理车次</el-button>
            <el-button v-if="row.status === '待发车' || row.status === '有阻塞'" type="danger" link @click="cancelTrip(row)">
              取消
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="detailVisible" size="72%" title="车次详情" destroy-on-close>
      <div v-loading="detailLoading" class="trip-detail" v-if="activeTrip">
        <section class="detail-top">
          <div>
            <div class="eyebrow">车次 {{ activeTrip.route_no }}</div>
            <h3>{{ activeTrip.driver_name || '未登记司机' }} · {{ activeTrip.vehicle_no || '未分配车辆' }}</h3>
            <p>{{ activeTrip.planning_date }} {{ activeTrip.departure_time || '' }} · {{ activeTrip.total_orders }} 单 · {{ activeTrip.total_allocations }} 分单</p>
          </div>
          <div class="detail-actions">
            <el-tag :type="statusTag(activeTrip.status)" effect="dark" size="large">{{ activeTrip.status }}</el-tag>
            <el-tag :type="occupancyTagType(activeTrip)" effect="plain" size="large">
              {{ activeTrip.occupancy_label || '—' }}
            </el-tag>
            <el-button v-if="canOperateTrip" plain @click="openAppendDialog">追加站点</el-button>
            <el-button :disabled="!canNormalDepart" type="success" @click="departTrip">整车发车</el-button>
            <el-button :disabled="!canOperateTrip" type="warning" @click="openExceptionDrawer">异常发车</el-button>
          </div>
        </section>

        <section v-if="canOperateTrip" class="trip-edit-panel mb-3">
          <div class="trip-edit-head">
            <strong>编辑车次（未发车）</strong>
            <span class="muted">可调序、换车、移除站点；追加请用上方按钮</span>
          </div>
          <div class="trip-edit-vehicle">
            <el-select v-model="editVehicleId" filterable placeholder="更换车辆" class="vehicle-select">
              <el-option
                v-for="v in deliveryVehicles.filter((x) => x.status === 'active')"
                :key="v.id"
                :label="`${v.vehicle_no} · ${v.driver_name || ''}`"
                :value="v.id"
              />
            </el-select>
            <el-button :loading="editSubmitting" @click="changeTripVehicle">保存换车</el-button>
          </div>
          <el-table :data="editableStops" border size="small" empty-text="暂无站点">
            <el-table-column label="序" width="52">
              <template #default="{ row }">{{ row.sequence }}</template>
            </el-table-column>
            <el-table-column prop="order_no" label="订单号" min-width="130" />
            <el-table-column prop="client_name" label="客户" min-width="120" show-overflow-tooltip />
            <el-table-column label="计划到达" width="100">
              <template #default="{ row }">{{ row.planned_arrive_time || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="180">
              <template #default="{ $index, row }">
                <el-button link :disabled="$index === 0 || editSubmitting" @click="moveStop($index, -1)">上移</el-button>
                <el-button
                  link
                  :disabled="$index === editableStops.length - 1 || editSubmitting"
                  @click="moveStop($index, 1)"
                >
                  下移
                </el-button>
                <el-button link type="danger" :disabled="editSubmitting" @click="removeStop(row)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </section>

        <el-alert
          class="mb-3"
          :closable="false"
          :type="driverAppTagType(activeTrip)"
          :title="driverAppHint(activeTrip)"
        >
          <template #default>
            <span v-if="driverAppVisible(activeTrip)">
              司机端登录车牌：{{ driverLoginPlate(activeTrip) }}，演示密码：demo123。
            </span>
            <span v-else>请回到智能排线或车辆管理，为车次绑定有效车牌后再发车。</span>
          </template>
        </el-alert>

        <section class="detail-metrics">
          <div><span>可装/已装</span><strong>{{ activeTrip.ready_count }}/{{ activeTrip.total_allocations }}</strong></div>
          <div><span>阻塞</span><strong>{{ activeTrip.blocked_count }}</strong></div>
          <div><span>未随车</span><strong>{{ activeTrip.not_loaded_count }}</strong></div>
          <div><span>发车方式</span><strong>{{ activeTrip.depart_mode || '待定' }}</strong></div>
          <div><span>司机端</span><strong>{{ driverAppVisible(activeTrip) ? (activeTrip.status === '运输中' ? '可操作' : '可查看') : '不可见' }}</strong></div>
          <div><span>北斗定位</span><strong>{{ vehicleLocation ? (vehicleLocation.online_status === 'online' ? '在线' : '离线') : '未就绪' }}</strong></div>
        </section>

        <section class="location-panel">
          <div>
            <div class="location-line">
              <strong>北斗位置</strong>
              <el-tag :type="vehicleLocationTagType" effect="plain">{{ vehicleLocationTitle }}</el-tag>
            </div>
            <p>
              {{ vehicleLocationCoordText }}
              <span v-if="vehicleLocation"> · {{ vehicleLocation.device_label || vehicleLocation.device_code || '北斗设备' }}</span>
            </p>
            <p class="muted">
              上报时间：{{ vehicleLocationTimeText }}
              <span v-if="vehicleLocation?.speed !== undefined && vehicleLocation?.speed !== null"> · 速度：{{ vehicleLocation.speed }} km/h</span>
            </p>
          </div>
          <el-button :loading="vehicleLocationLoading" @click="loadTripVehicleLocation()">刷新位置</el-button>
        </section>

        <el-alert
          v-if="activeTrip.blocked_count > 0 && canOperateTrip"
          type="warning"
          class="mb-3"
          :closable="false"
          title="当前车次存在阻塞分单。可以等待供应商/分检完成后刷新，也可以进入异常发车，记录未随车原因和照片。"
        />

        <section v-if="(activeTrip.risk_alerts || []).length" class="risk-detail-panel">
          <div class="risk-detail-head">
            <strong>风险说明</strong>
            <span class="muted">{{ riskSourceTip }}</span>
          </div>
          <div class="risk-badges">
            <el-tag v-for="badge in riskBadges(activeTrip)" :key="badge.label" :type="badge.type">
              {{ badge.label }}
            </el-tag>
          </div>
          <ol>
            <li v-for="(risk, idx) in activeTrip.risk_alerts || []" :key="idx">{{ risk }}</li>
          </ol>
        </section>

        <section v-for="group in supplierSections" :key="group.key" class="supplier-section">
          <div class="supplier-head">
            <div>
              <strong>{{ group.supplier_name }}</strong>
              <span class="muted">共 {{ group.total }} 条 · 可装 {{ group.ready }} · 阻塞 {{ group.blocked }} · 未随车 {{ group.notLoaded }}</span>
            </div>
          </div>
          <el-table :data="group.items" border size="small" row-key="id">
            <el-table-column prop="product_name" label="商品" min-width="220" show-overflow-tooltip />
            <el-table-column prop="spec_unit" label="规格/单位" width="120" />
            <el-table-column label="数量" width="90">
              <template #default="{ row }">{{ row.quantity }}{{ row.unit }}</template>
            </el-table-column>
            <el-table-column label="客户/订单" min-width="230">
              <template #default="{ row }">{{ itemStopText(row) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="itemTag(row.status)" effect="dark">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="原因" min-width="180">
              <template #default="{ row }">
                <span>{{ row.reason_detail || row.reason_code || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="145">
              <template #default="{ row }">
                <el-button
                  v-if="canOperateTrip && row.status === '待装车'"
                  link
                  type="success"
                  @click="markLoaded(row, true)"
                >
                  标记已装
                </el-button>
                <el-button
                  v-else-if="canOperateTrip && row.status === '已装车'"
                  link
                  @click="markLoaded(row, false)"
                >
                  撤回装车
                </el-button>
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
          </el-table>
        </section>
      </div>
    </el-drawer>

    <el-drawer
      v-model="exceptionVisible"
      class="exception-depart-drawer"
      size="62%"
      title="异常发车"
      destroy-on-close
    >
      <div v-if="activeTrip" class="exception-panel">
        <el-alert
          type="warning"
          :closable="false"
          title="异常发车表示部分分单未随车，不等于客户退货。后续需要在异常台账中选择补送、取消供货或收货少收结算。"
          class="mb-3"
        />
        <el-form label-width="112px">
          <el-form-item label="总说明" required>
            <el-input
              v-model="exceptionForm.reason_detail"
              type="textarea"
              :rows="3"
              maxlength="500"
              show-word-limit
              placeholder="例如：新发地蔬菜批发档口迟到，车次先发出，迟到分单转后续补送"
            />
          </el-form-item>
          <el-form-item label="处理选项">
            <el-checkbox v-model="exceptionForm.notify_customer">通知客户/食堂</el-checkbox>
            <el-checkbox v-model="exceptionForm.include_supplier_score">计入供应商评分</el-checkbox>
          </el-form-item>
        </el-form>

        <div class="exception-list">
          <div v-for="item in activeTrip.items || []" :key="item.id" class="exception-item" :class="{ selected: isExceptionSelected(item), blocker: isBlockingItem(item) }">
            <div class="exception-line">
              <el-checkbox-group v-model="exceptionSelectedIds">
                <el-checkbox :label="Number(item.allocation_id)">
                  <span class="strong">{{ item.product_name }}</span>
                </el-checkbox>
              </el-checkbox-group>
              <el-tag :type="itemTag(item.status)" effect="dark">{{ item.status }}</el-tag>
            </div>
            <div class="muted mt-1">
              {{ item.supplier_name }} · {{ item.quantity }}{{ item.unit }} · {{ itemStopText(item) }}
            </div>
            <div v-if="isExceptionSelected(item)" class="exception-form">
              <el-select v-model="ensureExceptionItemForm(item).reason_code" class="reason-select">
                <el-option v-for="opt in reasonOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
              <el-input
                v-model="ensureExceptionItemForm(item).reason_detail"
                placeholder="该分单说明；为空时使用总说明"
                maxlength="200"
                show-word-limit
              />
              <el-upload :auto-upload="false" :show-file-list="false" accept="image/*" :on-change="(file) => onExceptionPhotoChange(file, item)">
                <el-button size="small" :loading="uploadingKey.startsWith(`${item.allocation_id}:`)">上传照片</el-button>
              </el-upload>
              <div v-if="ensureExceptionItemForm(item).attachments_json.length" class="photo-strip">
                <div v-for="(url, idx) in ensureExceptionItemForm(item).attachments_json" :key="url" class="photo-cell">
                  <el-image :src="url" fit="cover" :preview-src-list="ensureExceptionItemForm(item).attachments_json" />
                  <el-button text type="danger" size="small" @click="removeExceptionPhoto(item, idx)">移除</el-button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="exception-drawer-footer">
          <el-button class="exception-drawer-cancel" @click="exceptionVisible = false">取消</el-button>
          <el-button
            type="warning"
            class="exception-drawer-confirm"
            :loading="exceptionSubmitting"
            @click="submitExceptionDepart"
          >
            确认异常发车
          </el-button>
        </div>
      </template>
    </el-drawer>

    <el-dialog v-model="appendDialogVisible" title="追加站点" width="640px" destroy-on-close>
      <p class="muted mb-2">仅可选择计划日 {{ filters.planningDate }} 内、尚未排入其他未完成车次的配货订单。</p>
      <el-select v-model="appendOrderIds" multiple filterable class="w-full" placeholder="选择订单">
        <el-option
          v-for="row in appendOrderPool"
          :key="row.id"
          :label="`${row.order_no} · ${row.client_name || ''}`"
          :value="row.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="appendDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="appendSubmitting" @click="submitAppendStops">追加并重算 ETA</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.dispatch-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.dispatch-head,
.detail-top {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.trip-edit-panel {
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 8px;
  background: rgba(248, 250, 252, 0.9);
}

.trip-edit-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 10px;
}

.trip-edit-vehicle {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.trip-edit-vehicle .vehicle-select {
  flex: 1;
  min-width: 200px;
}

.mb-3 {
  margin-bottom: 12px;
}

.mb-2 {
  margin-bottom: 8px;
}

.w-full {
  width: 100%;
}

.dispatch-head {
  padding: 18px 20px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.9);
}

.eyebrow {
  font-size: 12px;
  color: #64748b;
  letter-spacing: 0.08em;
}

h2,
h3 {
  margin: 4px 0;
  color: #0f172a;
}

p {
  margin: 0;
  color: #64748b;
}

.head-actions,
.detail-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.detail-actions :deep(.el-button) {
  min-width: 96px;
  font-weight: 700;
}

.detail-actions :deep(.el-button--success:not(.is-disabled):not(.is-link):not(.is-text)) {
  color: #fff !important;
  background: #059669 !important;
  border-color: #059669 !important;
}

.detail-actions :deep(.el-button--warning:not(.is-disabled):not(.is-link):not(.is-text)) {
  color: #fff !important;
  background: #d97706 !important;
  border-color: #d97706 !important;
}

.detail-actions :deep(.el-button--success > span),
.detail-actions :deep(.el-button--warning > span) {
  color: inherit !important;
}

.detail-actions :deep(.el-button.is-disabled) {
  color: #64748b !important;
  background: #f8fafc !important;
  border-color: #cbd5e1 !important;
}

.status-select {
  width: 120px;
}

.stat-grid,
.detail-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}

.stat-card,
.detail-metrics > div {
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 8px;
  background: #fff;
  padding: 14px 16px;
}

.stat-card span,
.detail-metrics span {
  display: block;
  color: #64748b;
  font-size: 13px;
}

.stat-card strong,
.detail-metrics strong {
  display: block;
  margin-top: 6px;
  font-size: 24px;
  color: #0f172a;
}

.stat-card.ok strong {
  color: #059669;
}

.stat-card.warn strong {
  color: #d97706;
}

.card-head,
.supplier-head,
.exception-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.muted {
  color: #64748b;
  font-size: 13px;
}

.strong {
  font-weight: 700;
  color: #0f172a;
}

.driver-login {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}

.location-panel {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid rgba(14, 165, 233, 0.22);
  border-radius: 8px;
  background: #f8fbff;
}

.location-line {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.mini-progress {
  margin-top: 6px;
}

.risk-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.risk-more {
  padding: 0;
  min-height: 22px;
}

.risk-detail-panel {
  padding: 14px 16px;
  border: 1px solid rgba(245, 158, 11, 0.34);
  border-radius: 8px;
  background: #fffbeb;
}

.risk-detail-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 10px;
}

.risk-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.risk-detail-panel ol {
  margin: 8px 0 0;
  padding-left: 20px;
  color: #713f12;
  line-height: 1.7;
}

.trip-detail,
.exception-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.supplier-section {
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.supplier-head {
  padding: 12px 14px;
  background: #f8fafc;
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
}

.exception-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.exception-item {
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 8px;
  background: #fff;
  padding: 12px;
}

.exception-item.blocker {
  border-color: rgba(245, 158, 11, 0.45);
  background: #fffbeb;
}

.exception-item.selected {
  border-color: rgba(14, 165, 233, 0.55);
}

.exception-form {
  display: grid;
  grid-template-columns: 140px minmax(220px, 1fr) 100px;
  gap: 10px;
  margin-top: 10px;
  align-items: start;
}

.reason-select {
  width: 140px;
}

.photo-strip {
  grid-column: 1 / -1;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.photo-cell {
  width: 72px;
}

.photo-cell :deep(.el-image) {
  width: 72px;
  height: 72px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.mb-3 {
  margin-bottom: 12px;
}

.mt-1 {
  margin-top: 4px;
}

.mr-1 {
  margin-right: 4px;
}

.mb-1 {
  margin-bottom: 4px;
}
</style>
