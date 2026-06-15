<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Box,
  Aim,
  Camera,
  Check,
  CircleCheckFilled,
  Close,
  Collection,
  Cpu,
  DataAnalysis,
  Delete,
  Files,
  MagicStick,
  Picture,
  Plus,
  Refresh,
  Setting,
  Switch,
  Timer,
  UploadFilled,
  VideoPlay,
  WarningFilled,
} from '@element-plus/icons-vue'
import RoiCropEditor from '../../components/RoiCropEditor.vue'
import { formatChinaDateTime } from '../../utils/datetime'
import {
  cancelSmartScaleRecognitionTrainApi,
  createSmartScaleRecognitionCategoryApi,
  createSmartScaleRecognitionRoiProfileApi,
  deleteSmartScaleRecognitionCategoryApi,
  deleteSmartScaleRecognitionSampleApi,
  deploySmartScaleRecognitionModelApi,
  getSmartScaleRecognitionTrainStatusApi,
  importReceivingRecognitionSamplesApi,
  listProductsApi,
  listSmartScaleRecognitionCategoriesApi,
  listSmartScaleRecognitionDevicesApi,
  listSmartScaleRecognitionModelsApi,
  listSmartScaleRecognitionRoiProfilesApi,
  listSmartScaleRecognitionSamplesApi,
  recropSmartScaleRecognitionSamplesApi,
  recognizeSmartScaleApi,
  trainSmartScaleRecognitionApi,
  uploadSmartScaleRecognitionSampleApi,
  reviewSmartScaleRecognitionSamplesApi,
} from '../../api/operation'

const activeTab = ref('catalog')

const workflowItems = [
  { name: 'catalog', index: '01', title: '类目与样本', description: '管理识别类目和训练样本', icon: Collection },
  { name: 'train', index: '02', title: '训练与模型', description: '配置训练参数并管理版本', icon: Cpu },
  { name: 'recognize', index: '03', title: '识别测试', description: '上传图片验证识别效果', icon: MagicStick },
]

// —— 类目与样本 ——
const categories = ref([])
const samples = ref([])
const products = ref([])
const active = ref(null)
const loading = ref(false)
const uploadLoading = ref(false)
const form = ref({ name: '', product_id: null, product_name: '' })

const importVisible = ref(false)
const importLoading = ref(false)
const importForm = ref({ date_from: null, date_to: null, product_ids: [], limit: 500 })
const importResult = ref(null)
const sampleStatus = ref('all')
const sampleImageMode = ref('crop')
const selectedSampleIds = ref([])

const devices = ref([])
const roiProfiles = ref([])
const roiVisible = ref(false)
const roiSaving = ref(false)
const roiDeviceId = ref('')
const roiDraft = ref({ x: 0.25, y: 0.2, width: 0.5, height: 0.55, rotation: 0 })

const manualVisible = ref(false)
const manualFile = ref(null)
const manualPreview = ref('')
const manualMode = ref('device')
const manualDeviceId = ref('')
const manualRoi = ref({ x: 0.25, y: 0.2, width: 0.5, height: 0.55, rotation: 0 })
const manualHasOverride = ref(false)

const assignDeviceVisible = ref(false)
const assignDeviceId = ref('')

// —— 训练与模型 ——
const trainParams = ref({ epochs: 10, batch_size: 16, min_samples_per_class: 10 })
const models = ref([])
const modelsLoading = ref(false)
const trainingTaskId = ref(null)
const trainingProgress = ref(null)
let trainingPollHandle = null

// —— 识别测试 ——
const recognizeLoading = ref(false)
const recognizeResults = ref(null)
const recognizePreview = ref('')
const recognizeDeviceId = ref('')

const deployedModel = computed(() => models.value.find((model) => model.is_deployed) || null)
const trainableCount = computed(() =>
  categories.value.filter(
    (category) =>
      Number(category.sample_count || 0) >= Number(trainParams.value.min_samples_per_class || 10),
  ).length,
)
const totalSampleCount = computed(() =>
  categories.value.reduce((total, category) => total + Number(category.sample_count || 0), 0),
)
const pendingSampleCount = computed(() =>
  categories.value.reduce(
    (total, category) => total + Number(category.review_counts?.pending || 0),
    0,
  ),
)
const selectedSampleCount = computed(
  () => Number(active.value?.total_sample_count ?? samples.value.length ?? 0),
)
const selectedApprovedCount = computed(() => Number(active.value?.sample_count || 0))
const selectedReceivingCount = computed(
  () => samples.value.filter((sample) => sample.source === 'receiving').length,
)
const selectedManualCount = computed(
  () => samples.value.filter((sample) => sample.source !== 'receiving').length,
)
const selectedReady = computed(
  () => selectedApprovedCount.value >= Number(trainParams.value.min_samples_per_class || 10),
)
const filteredSamples = computed(() =>
  sampleStatus.value === 'all'
    ? samples.value
    : samples.value.filter((sample) => sample.review_status === sampleStatus.value),
)
const samplePreviewUrls = computed(() =>
  filteredSamples.value.map((sample) => sampleDisplayUrl(sample)).filter(Boolean),
)
const selectedSamples = computed(() =>
  samples.value.filter((sample) => selectedSampleIds.value.includes(sample.id)),
)
const selectedDevice = computed(
  () => devices.value.find((device) => device.device_id === roiDeviceId.value) || null,
)
const recognitionDevices = computed(() => {
  const boundIds = Object.keys(deployedModel.value?.roi_versions || {})
  return boundIds.length
    ? devices.value.filter((device) => boundIds.includes(device.device_id))
    : devices.value
})
const manualDevice = computed(
  () => devices.value.find((device) => device.device_id === manualDeviceId.value) || null,
)
const sampleStatusOptions = computed(() => [
  { value: 'all', label: '全部', count: selectedSampleCount.value },
  { value: 'pending', label: '待审核', count: Number(active.value?.review_counts?.pending || 0) },
  { value: 'approved', label: '已批准', count: Number(active.value?.review_counts?.approved || 0) },
  {
    value: 'needs_attention',
    label: '待处理',
    count: Number(active.value?.review_counts?.needs_attention || 0),
  },
  { value: 'rejected', label: '已驳回', count: Number(active.value?.review_counts?.rejected || 0) },
])
const trainingDetail = computed(() => trainingProgress.value?.progress || {})
const trainingIsRunning = computed(() =>
  ['preparing', 'running'].includes(trainingProgress.value?.status),
)
const trainingPercentage = computed(() => {
  const total = Number(trainingDetail.value.total_epochs || 0)
  const current = Number(trainingDetail.value.epoch || 0)
  if (!total) return trainingProgress.value?.status === 'done' ? 100 : 0
  return Math.min(100, Math.round((100 * current) / Math.max(1, total)))
})
const bestModel = computed(() =>
  models.value
    .filter((model) => model.metrics?.val_acc != null)
    .slice()
    .sort((a, b) => Number(b.metrics.val_acc) - Number(a.metrics.val_acc))[0] || null,
)
const latestModel = computed(() => models.value[0] || null)
const recognizeTopResult = computed(() => recognizeResults.value?.results?.[0] || null)

const formatPercent = (value, digits = 1) =>
  value == null || Number.isNaN(Number(value)) ? '—' : `${(Number(value) * 100).toFixed(digits)}%`

const formatDateTime = (value) => formatChinaDateTime(value)

const deviceLabel = (device) => {
  if (!device) return ''
  const name = String(device.device_name || '').trim()
  return name || '首衡智能秤'
}

const categoryProgress = (category) => {
  const minimum = Number(trainParams.value.min_samples_per_class || 10)
  return Math.min(100, Math.round((Number(category.sample_count || 0) / Math.max(1, minimum)) * 100))
}

const modelStatusMeta = (status) => {
  const map = {
    pending: { label: '待处理', type: 'info' },
    preparing: { label: '准备中', type: 'warning' },
    running: { label: '训练中', type: 'primary' },
    done: { label: '已完成', type: 'success' },
    error: { label: '失败', type: 'danger' },
    cancelled: { label: '已取消', type: 'info' },
  }
  return map[status] || { label: status || '未知', type: 'info' }
}

const confidenceMeta = (score) => {
  const value = Number(score || 0)
  if (value >= 0.8) return { label: '高置信度', className: 'is-high' }
  if (value >= 0.5) return { label: '中置信度', className: 'is-medium' }
  return { label: '低置信度', className: 'is-low' }
}

const resultName = (result) =>
  result.product_name || result.category_name || `cat_${result.category_id}`

const reviewStatusMeta = (status) => {
  const map = {
    pending: { label: '待审核', className: 'is-pending' },
    approved: { label: '已批准', className: 'is-approved' },
    needs_attention: { label: '待处理', className: 'is-attention' },
    rejected: { label: '已驳回', className: 'is-rejected' },
  }
  return map[status] || { label: status || '未知', className: 'is-pending' }
}

const sampleDisplayUrl = (sample) =>
  sampleImageMode.value === 'original'
    ? sample.original_image_url || sample.image_url
    : sample.cropped_image_url || ''

const activeProfileForDevice = (deviceId) =>
  devices.value.find((device) => device.device_id === deviceId)?.roi_profile || null

const roiFromProfile = (profile) =>
  profile
    ? {
        x: Number(profile.x),
        y: Number(profile.y),
        width: Number(profile.width),
        height: Number(profile.height),
        rotation: Number(profile.rotation || 0),
      }
    : { x: 0.25, y: 0.2, width: 0.5, height: 0.55, rotation: 0 }

// ============ 类目与样本 ============
const load = async () => {
  loading.value = true
  try {
    const res = await listSmartScaleRecognitionCategoriesApi()
    categories.value = res.items || []
    if (active.value) {
      active.value = categories.value.find((item) => item.id === active.value.id) || null
    }
  } finally {
    loading.value = false
  }
}

const loadProducts = async () => {
  const res = await listProductsApi({ page: 1, page_size: 200 })
  products.value = res.items || []
}

const selectCategory = async (row) => {
  active.value = row
  selectedSampleIds.value = []
  sampleStatus.value = 'all'
  const res = await listSmartScaleRecognitionSamplesApi(row.id)
  samples.value = res.items || []
}

const createCategory = async () => {
  const name = form.value.name.trim()
  if (!name) return ElMessage.warning('请输入类别名称')
  await createSmartScaleRecognitionCategoryApi({
    name,
    product_id: form.value.product_id || null,
    product_name: form.value.product_name || '',
  })
  form.value = { name: '', product_id: null, product_name: '' }
  await load()
}

const removeCategory = async (row) => {
  await ElMessageBox.confirm(`确认删除「${row.name}」吗？`, '删除类别', { type: 'warning' })
  await deleteSmartScaleRecognitionCategoryApi(row.id)
  if (active.value?.id === row.id) {
    active.value = null
    samples.value = []
  }
  await load()
}

const onProductChange = (id) => {
  const product = products.value.find((item) => Number(item.id) === Number(id))
  form.value.product_name = product?.name || ''
  if (product?.name && !form.value.name) form.value.name = product.name
}

const uploadSample = async (uploadFile) => {
  if (!active.value) {
    ElMessage.warning('请先选择类别')
    return
  }
  manualFile.value = uploadFile.raw
  if (manualPreview.value) URL.revokeObjectURL(manualPreview.value)
  manualPreview.value = URL.createObjectURL(uploadFile.raw)
  manualMode.value = devices.value.length ? 'device' : 'external'
  manualDeviceId.value = devices.value[0]?.device_id || ''
  manualRoi.value = roiFromProfile(activeProfileForDevice(manualDeviceId.value))
  manualHasOverride.value = manualMode.value === 'external'
  manualVisible.value = true
}

const onManualModeChange = () => {
  if (manualMode.value === 'device') {
    manualDeviceId.value = manualDeviceId.value || devices.value[0]?.device_id || ''
    manualRoi.value = roiFromProfile(activeProfileForDevice(manualDeviceId.value))
    manualHasOverride.value = false
  } else {
    manualDeviceId.value = ''
    manualRoi.value = { x: 0.2, y: 0.18, width: 0.6, height: 0.62, rotation: 0 }
    manualHasOverride.value = true
  }
}

const onManualDeviceChange = () => {
  manualRoi.value = roiFromProfile(activeProfileForDevice(manualDeviceId.value))
  manualHasOverride.value = false
}

const onManualRoiChange = () => {
  manualHasOverride.value = true
}

const submitManualSample = async () => {
  if (!active.value || !manualFile.value) return
  if (manualMode.value === 'device' && !manualDeviceId.value) {
    return ElMessage.warning('暂未找到首衡智能秤拍摄记录')
  }
  if (
    manualMode.value === 'device' &&
    !activeProfileForDevice(manualDeviceId.value) &&
    !manualHasOverride.value
  ) {
    return ElMessage.warning('首衡固定机位尚未配置 ROI，请先校准或在本图中框选')
  }
  uploadLoading.value = true
  try {
    const fd = new FormData()
    fd.append('file', manualFile.value)
    fd.append('angle', manualMode.value === 'device' ? '设备补录' : '外部素材')
    fd.append('quality', '0')
    fd.append('feature_json', '[]')
    fd.append('upload_mode', manualMode.value)
    if (manualDeviceId.value) fd.append('device_id', manualDeviceId.value)
    if (manualMode.value === 'external' || manualHasOverride.value) {
      fd.append('roi_override_json', JSON.stringify(manualRoi.value))
    }
    await uploadSmartScaleRecognitionSampleApi(active.value.id, fd)
    ElMessage.success('素材已进入待审核池')
    manualVisible.value = false
    await selectCategory(active.value)
    await load()
  } finally {
    uploadLoading.value = false
  }
}

const removeSample = async (row) => {
  await deleteSmartScaleRecognitionSampleApi(row.id)
  await selectCategory(active.value)
  await load()
}

const toggleSampleSelection = (sampleId, checked) => {
  selectedSampleIds.value = checked
    ? Array.from(new Set([...selectedSampleIds.value, sampleId]))
    : selectedSampleIds.value.filter((id) => id !== sampleId)
}

const bulkReview = async (status) => {
  if (!selectedSampleIds.value.length) return
  let rejectionReason = ''
  if (status === 'rejected') {
    const result = await ElMessageBox.prompt('请输入驳回原因', '批量驳回', {
      inputPlaceholder: '例如：空秤盘、商品被遮挡、标签不一致',
      inputValidator: (value) => Boolean(value?.trim()) || '请输入驳回原因',
    })
    rejectionReason = result.value
  }
  await reviewSmartScaleRecognitionSamplesApi({
    sample_ids: selectedSampleIds.value,
    status,
    rejection_reason: rejectionReason || null,
  })
  ElMessage.success(status === 'approved' ? '样本已批准' : '样本已驳回')
  selectedSampleIds.value = []
  await selectCategory(active.value)
  await load()
}

const bulkRecrop = async () => {
  if (!selectedSampleIds.value.length) return
  await recropSmartScaleRecognitionSamplesApi({ sample_ids: selectedSampleIds.value })
  ElMessage.success('已按首衡固定机位 ROI 重新裁剪')
  selectedSampleIds.value = []
  await selectCategory(active.value)
  await load()
}

const openAssignDevice = () => {
  if (!selectedSampleIds.value.length) return
  assignDeviceId.value = selectedSamples.value[0]?.device_id || devices.value[0]?.device_id || ''
  assignDeviceVisible.value = true
}

const assignSelectedDevice = async () => {
  if (!assignDeviceId.value) return ElMessage.warning('暂未找到首衡智能秤拍摄记录')
  await recropSmartScaleRecognitionSamplesApi({
    sample_ids: selectedSampleIds.value,
    device_id: assignDeviceId.value,
  })
  ElMessage.success('已应用首衡固定机位 ROI 并重新裁剪')
  assignDeviceVisible.value = false
  selectedSampleIds.value = []
  await selectCategory(active.value)
  await load()
}

const openImport = () => {
  importResult.value = null
  importVisible.value = true
}

const loadDevices = async () => {
  const [deviceRes, profileRes] = await Promise.all([
    listSmartScaleRecognitionDevicesApi(),
    listSmartScaleRecognitionRoiProfilesApi(),
  ])
  devices.value = deviceRes.items || []
  roiProfiles.value = profileRes.items || []
  if (!recognizeDeviceId.value && devices.value.length) {
    recognizeDeviceId.value = devices.value[0].device_id
  }
}

const onRoiDeviceChange = () => {
  roiDraft.value = roiFromProfile(selectedDevice.value?.roi_profile)
}

const openRoiSettings = async () => {
  await loadDevices()
  roiDeviceId.value = roiDeviceId.value || devices.value[0]?.device_id || ''
  onRoiDeviceChange()
  roiVisible.value = true
}

const saveRoiProfile = async () => {
  if (!roiDeviceId.value) return ElMessage.warning('暂未找到首衡智能秤拍摄记录')
  if (!selectedDevice.value?.latest_image_url) return ElMessage.warning('首衡智能秤暂无校准原图')
  roiSaving.value = true
  try {
    await createSmartScaleRecognitionRoiProfileApi({
      device_id: roiDeviceId.value,
      device_name: selectedDevice.value.device_name || '',
      reference_image_url: selectedDevice.value.latest_image_url,
      ...roiDraft.value,
    })
    ElMessage.success('ROI 新版本已保存；重新训练部署后才会影响线上识别')
    await loadDevices()
    onRoiDeviceChange()
  } finally {
    roiSaving.value = false
  }
}

const runImport = async () => {
  importLoading.value = true
  try {
    const payload = {
      date_from: importForm.value.date_from || null,
      date_to: importForm.value.date_to || null,
      product_ids: importForm.value.product_ids?.length ? importForm.value.product_ids : null,
      limit: importForm.value.limit || 500,
    }
    const res = await importReceivingRecognitionSamplesApi(payload)
    importResult.value = res
    ElMessage.success(`导入完成：新增 ${res.imported}，跳过 ${res.skipped}`)
    await load()
    if (active.value) await selectCategory(active.value)
  } finally {
    importLoading.value = false
  }
}

// ============ 训练与模型 ============
const loadModels = async () => {
  modelsLoading.value = true
  try {
    const res = await listSmartScaleRecognitionModelsApi()
    models.value = res.items || []
    const running = models.value.find(
      (model) => model.status === 'preparing' || model.status === 'running',
    )
    if (running && !trainingTaskId.value) {
      trainingTaskId.value = running.task_id
      trainingProgress.value = running
      startPolling()
    }
  } finally {
    modelsLoading.value = false
  }
}

const startPolling = () => {
  stopPolling()
  trainingPollHandle = setInterval(async () => {
    if (!trainingTaskId.value) return
    try {
      const result = await getSmartScaleRecognitionTrainStatusApi(trainingTaskId.value)
      trainingProgress.value = result
      if (['done', 'error', 'cancelled'].includes(result.status)) {
        stopPolling()
        await loadModels()
        if (result.status === 'done') {
          ElMessage.success(`训练完成，验证准确率 ${formatPercent(result.metrics?.val_acc)}`)
        } else if (result.status === 'error') {
          ElMessage.error(`训练失败：${result.error_message || '未知错误'}`)
        }
      }
    } catch {
      // 轮询暂时失败时保留当前进度，下一轮继续尝试。
    }
  }, 2000)
}

const stopPolling = () => {
  if (trainingPollHandle) {
    clearInterval(trainingPollHandle)
    trainingPollHandle = null
  }
}

const startTraining = async () => {
  if (trainableCount.value < 2) {
    return ElMessage.warning(
      `可训练类目不足 2 个（每类样本需 ≥ ${trainParams.value.min_samples_per_class}）`,
    )
  }
  try {
    const result = await trainSmartScaleRecognitionApi(trainParams.value)
    trainingTaskId.value = result.task_id
    trainingProgress.value = {
      status: result.status,
      classes: result.classes,
      version: result.version,
      progress: { message: '训练任务正在准备数据' },
    }
    ElMessage.success(`训练任务已启动 #${result.task_id}（${result.classes.length} 个类别）`)
    await loadModels()
    startPolling()
  } catch {
    // 全局响应拦截负责展示后端错误。
  }
}

const cancelTraining = async () => {
  if (!trainingTaskId.value) return
  await cancelSmartScaleRecognitionTrainApi(trainingTaskId.value)
  ElMessage.success('已取消')
  stopPolling()
  trainingProgress.value = trainingProgress.value
    ? { ...trainingProgress.value, status: 'cancelled' }
    : null
  await loadModels()
}

const deployModel = async (row) => {
  await ElMessageBox.confirm(`部署模型 ${row.version} 为当前识别模型？`, '部署模型', {
    type: 'info',
  })
  await deploySmartScaleRecognitionModelApi(row.task_id)
  ElMessage.success('部署成功')
  await loadModels()
}

// ============ 识别测试 ============
const onRecognize = async (uploadFile) => {
  if (!recognizeDeviceId.value) {
    ElMessage.warning('暂未找到首衡智能秤固定机位')
    return
  }
  recognizeLoading.value = true
  recognizeResults.value = null
  if (recognizePreview.value) URL.revokeObjectURL(recognizePreview.value)
  recognizePreview.value = URL.createObjectURL(uploadFile.raw)
  try {
    const fd = new FormData()
    fd.append('file', uploadFile.raw)
    fd.append('device_id', recognizeDeviceId.value)
    recognizeResults.value = await recognizeSmartScaleApi(fd)
  } finally {
    recognizeLoading.value = false
  }
}

onMounted(async () => {
  await Promise.all([load(), loadProducts(), loadModels(), loadDevices()])
})

onBeforeUnmount(() => {
  stopPolling()
  if (recognizePreview.value) URL.revokeObjectURL(recognizePreview.value)
  if (manualPreview.value) URL.revokeObjectURL(manualPreview.value)
})
</script>

<template>
  <div class="ssr-page">
    <header class="ssr-hero">
      <div class="hero-copy">
        <span class="hero-eyebrow">
          <el-icon><MagicStick /></el-icon>
          AI VISION · SMART SCALE
        </span>
        <h2>智能秤识别训练</h2>
        <p>按 SKU 归集训练样本，完成 MobileNetV2 模型训练、部署与识别效果验证。</p>
        <el-button class="roi-entry" :icon="Setting" @click="openRoiSettings">
          首衡 ROI
        </el-button>
      </div>

      <section class="deployment-card" :class="{ 'is-empty': !deployedModel }">
        <div class="deployment-head">
          <div>
            <span class="section-kicker">当前部署模型</span>
            <strong>{{ deployedModel?.version || '尚未部署' }}</strong>
          </div>
          <span class="online-chip" :class="{ 'is-offline': !deployedModel }">
            <i />
            {{ deployedModel ? '在线' : '待部署' }}
          </span>
        </div>
        <div class="deployment-metrics">
          <div>
            <span>类别数量</span>
            <b>{{ deployedModel ? (deployedModel.classes || []).length : '—' }}</b>
          </div>
          <div>
            <span>验证集准确率</span>
            <b class="success-value">{{ formatPercent(deployedModel?.metrics?.val_acc) }}</b>
          </div>
        </div>
      </section>
    </header>

    <section class="overview-strip" aria-label="训练数据概览">
      <div class="overview-item">
        <span class="metric-icon"><el-icon><Collection /></el-icon></span>
        <div>
          <small>类目总数</small>
          <strong>{{ categories.length }}</strong>
          <span>个识别类目</span>
        </div>
      </div>
      <div class="overview-item">
        <span class="metric-icon is-cyan"><el-icon><CircleCheckFilled /></el-icon></span>
        <div>
          <small>可训练类目</small>
          <strong>{{ trainableCount }}</strong>
          <span>满足当前阈值</span>
        </div>
      </div>
      <div class="overview-item">
        <span class="metric-icon is-violet"><el-icon><Picture /></el-icon></span>
        <div>
          <small>已批准样本</small>
          <strong>{{ totalSampleCount }}</strong>
          <span>张可训练裁剪图</span>
        </div>
      </div>
      <div class="overview-item">
        <span class="metric-icon is-amber"><el-icon><Timer /></el-icon></span>
        <div>
          <small>待审核样本</small>
          <strong>{{ pendingSampleCount }}</strong>
          <span>张候选素材</span>
        </div>
      </div>
    </section>

    <nav class="workflow-nav" role="tablist" aria-label="智能秤识别训练流程">
      <button
        v-for="item in workflowItems"
        :key="item.name"
        type="button"
        class="workflow-step"
        :class="{ 'is-active': activeTab === item.name }"
        role="tab"
        :aria-selected="activeTab === item.name"
        @click="activeTab = item.name"
      >
        <span class="step-index">{{ item.index }}</span>
        <el-icon class="step-icon"><component :is="item.icon" /></el-icon>
        <span class="step-copy">
          <strong>{{ item.title }}</strong>
          <small>{{ item.description }}</small>
        </span>
      </button>
    </nav>

    <!-- 类目与样本 -->
    <section v-show="activeTab === 'catalog'" class="catalog-workspace" role="tabpanel">
      <aside class="surface-panel catalog-sidebar">
        <div class="panel-heading">
          <div>
            <span class="section-kicker">DATASET</span>
            <h3>创建新类目</h3>
          </div>
          <el-icon class="heading-icon"><Files /></el-icon>
        </div>

        <el-form label-position="top" class="category-form" @submit.prevent>
          <el-form-item label="绑定商品 SKU（可选）">
            <el-select
              v-model="form.product_id"
              clearable
              filterable
              placeholder="不绑定则作为自由类别"
              @change="onProductChange"
            >
              <el-option v-for="product in products" :key="product.id" :label="product.name" :value="product.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="类别名称">
            <el-input
              v-model="form.name"
              placeholder="例如：苹果、土豆、牛后腱"
              @keyup.enter="createCategory"
            />
          </el-form-item>
          <el-button class="create-category-btn" type="primary" :icon="Plus" @click="createCategory">
            创建类目
          </el-button>
        </el-form>

        <div class="panel-divider" />

        <div class="list-heading">
          <div>
            <h3>类目列表</h3>
            <span>{{ categories.length }} 个类目</span>
          </div>
          <el-button link :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        </div>

        <div v-loading="loading" class="category-list">
          <div
            v-for="category in categories"
            :key="category.id"
            class="category-row"
            :class="{ 'is-active': active?.id === category.id }"
            role="button"
            tabindex="0"
            @click="selectCategory(category)"
            @keydown.enter="selectCategory(category)"
          >
            <div class="category-main">
              <div class="category-title">
                <strong>{{ category.name }}</strong>
                <span v-if="category.source === 'receiving'">来自收货</span>
              </div>
              <small>{{ category.product_name || '自由识别类目' }}</small>
              <div class="readiness-track" aria-hidden="true">
                <span :style="{ width: `${categoryProgress(category)}%` }" />
              </div>
            </div>
            <div class="category-count">
              <b>{{ category.sample_count || 0 }}</b>
              <span>张已批准</span>
            </div>
            <el-button
              class="category-delete"
              circle
              text
              type="danger"
              :icon="Delete"
              aria-label="删除类别"
              @click.stop="removeCategory(category)"
            />
          </div>
          <el-empty v-if="!loading && !categories.length" :image-size="72" description="暂无识别类目" />
        </div>
      </aside>

      <main class="surface-panel sample-workspace">
        <template v-if="active">
          <div class="sample-workspace-head">
            <div class="selected-category">
              <span class="section-kicker">CURRENT DATASET</span>
              <div>
                <h3>{{ active.name }}</h3>
                <span class="sample-count-chip">{{ selectedApprovedCount }} / {{ selectedSampleCount }} 已批准</span>
                <span class="ready-chip" :class="{ 'is-ready': selectedReady }">
                  <el-icon><CircleCheckFilled v-if="selectedReady" /><Timer v-else /></el-icon>
                  {{ selectedReady ? '可参与训练' : '样本待补充' }}
                </span>
              </div>
              <p v-if="active.product_name">已绑定商品 SKU：{{ active.product_name }}</p>
            </div>
            <div class="sample-actions">
              <el-button :icon="UploadFilled" @click="openImport">补导历史收货照片</el-button>
              <el-upload
                :show-file-list="false"
                :auto-upload="false"
                :on-change="uploadSample"
                accept="image/*"
              >
                <el-button :loading="uploadLoading" type="primary" :icon="Plus">补录素材</el-button>
              </el-upload>
            </div>
          </div>

          <div class="sample-guidance">
            <el-icon><DataAnalysis /></el-icon>
            <p>
              每类建议至少 30 张，并覆盖正面、侧面、俯视、近景和远景。
              当前训练阈值为每类 {{ trainParams.min_samples_per_class }} 张。
            </p>
            <div class="source-summary">
              <span>收货导入 <b>{{ selectedReceivingCount }}</b></span>
              <span>手动上传 <b>{{ selectedManualCount }}</b></span>
            </div>
          </div>

          <div class="gallery-heading">
            <div>
              <h4>候选样本池</h4>
              <span>只有已批准且质量合格的裁剪图参与训练</span>
            </div>
            <div class="gallery-view-switch">
              <el-button-group>
                <el-button
                  :type="sampleImageMode === 'crop' ? 'primary' : 'default'"
                  @click="sampleImageMode = 'crop'"
                >
                  训练裁剪图
                </el-button>
                <el-button
                  :type="sampleImageMode === 'original' ? 'primary' : 'default'"
                  @click="sampleImageMode = 'original'"
                >
                  原图
                </el-button>
              </el-button-group>
            </div>
          </div>

          <div class="sample-filter-row">
            <button
              v-for="option in sampleStatusOptions"
              :key="option.value"
              type="button"
              :class="{ 'is-active': sampleStatus === option.value }"
              @click="sampleStatus = option.value"
            >
              <span>{{ option.label }}</span>
              <b>{{ option.count }}</b>
            </button>
          </div>

          <div v-if="selectedSampleIds.length" class="bulk-action-bar">
            <span>已选择 {{ selectedSampleIds.length }} 张</span>
            <el-button type="success" plain :icon="Check" @click="bulkReview('approved')">批准</el-button>
            <el-button type="danger" plain :icon="Close" @click="bulkReview('rejected')">驳回</el-button>
            <el-button :icon="Switch" @click="bulkRecrop">重新裁剪</el-button>
            <el-button :icon="Setting" @click="openAssignDevice">应用首衡 ROI</el-button>
          </div>

          <div v-if="filteredSamples.length" class="sample-grid">
            <article
              v-for="(sample, index) in filteredSamples"
              :key="sample.id"
              class="sample-card"
              :class="{ 'is-selected': selectedSampleIds.includes(sample.id) }"
            >
              <el-image
                v-if="sampleDisplayUrl(sample)"
                :src="sampleDisplayUrl(sample)"
                :preview-src-list="samplePreviewUrls"
                :initial-index="index"
                fit="cover"
                class="sample-thumb"
                preview-teleported
              >
                <template #error>
                  <div class="image-fallback">
                    <el-icon><Picture /></el-icon>
                    <span>图片加载失败</span>
                  </div>
                </template>
              </el-image>
              <div v-else class="image-fallback sample-thumb">
                <el-icon><Picture /></el-icon>
                <span>尚未生成裁剪图</span>
              </div>
              <el-checkbox
                class="sample-selector"
                :model-value="selectedSampleIds.includes(sample.id)"
                aria-label="选择样本"
                @change="toggleSampleSelection(sample.id, $event)"
              />
              <div class="sample-overlay">
                <span class="source-chip" :class="{ 'is-receiving': sample.source === 'receiving' }">
                  {{ sample.source === 'receiving' ? '收货' : sample.source === 'device_manual' ? '设备补录' : '外部素材' }}
                </span>
                <el-button
                  circle
                  text
                  type="danger"
                  :icon="Delete"
                  aria-label="删除样本"
                  @click.stop="removeSample(sample)"
                />
              </div>
              <div class="sample-card-meta">
                <span class="review-chip" :class="reviewStatusMeta(sample.review_status).className">
                  {{ reviewStatusMeta(sample.review_status).label }}
                </span>
                <span>{{ sample.device_id ? '首衡智能秤' : '外部素材' }}</span>
                <span>{{ sample.roi_version ? `ROI v${sample.roi_version}` : sample.roi_override ? '单图 ROI' : '无 ROI' }}</span>
                <span v-if="sample.quality_status !== 'passed'" class="quality-warning">
                  {{ sample.quality_reason || '等待质量检查' }}
                </span>
              </div>
            </article>
          </div>

          <div v-else class="workspace-empty">
            <el-icon><Picture /></el-icon>
            <h4>{{ samples.length ? '当前筛选下没有样本' : '这个类目还没有样本' }}</h4>
            <p>收货确认后会自动进入待审核池，也可以补导历史照片或补录外部素材。</p>
            <div>
              <el-button :icon="UploadFilled" @click="openImport">补导历史收货照片</el-button>
              <el-upload
                :show-file-list="false"
                :auto-upload="false"
                :on-change="uploadSample"
                accept="image/*"
              >
                <el-button type="primary" :loading="uploadLoading" :icon="Plus">补录素材</el-button>
              </el-upload>
            </div>
          </div>
        </template>

        <div v-else class="workspace-empty is-large">
          <el-icon><Collection /></el-icon>
          <h4>选择一个识别类目</h4>
          <p>从左侧类目列表进入样本工作区，查看训练就绪度并维护图片。</p>
        </div>
      </main>
    </section>

    <!-- 训练与模型 -->
    <section v-show="activeTab === 'train'" class="training-workspace" role="tabpanel">
      <aside class="training-sidebar">
        <section class="surface-panel training-config">
          <div class="panel-heading">
            <div>
              <span class="section-kicker">TRAINING CONFIG</span>
              <h3>训练配置</h3>
            </div>
            <el-icon class="heading-icon"><Cpu /></el-icon>
          </div>

          <div class="parameter-list">
            <label>
              <span>每类最小样本数</span>
              <small>低于该数量的类目不会进入训练</small>
              <el-input-number v-model="trainParams.min_samples_per_class" :min="2" :max="100" />
            </label>
            <label>
              <span>Epochs</span>
              <small>完整遍历训练集的轮数</small>
              <el-input-number v-model="trainParams.epochs" :min="1" :max="100" />
            </label>
            <label>
              <span>Batch Size</span>
              <small>单次迭代读取的图片数量</small>
              <el-input-number v-model="trainParams.batch_size" :min="1" :max="64" />
            </label>
          </div>

          <div class="eligibility-box" :class="{ 'is-ready': trainableCount >= 2 }">
            <el-icon><CircleCheckFilled v-if="trainableCount >= 2" /><WarningFilled v-else /></el-icon>
            <div>
              <strong>可训练类目：{{ trainableCount }} 个</strong>
              <span>启动训练至少需要 2 个达标类目</span>
            </div>
          </div>

          <el-button
            class="start-training-btn"
            type="primary"
            size="large"
            :icon="VideoPlay"
            :disabled="trainableCount < 2 || trainingIsRunning"
            @click="startTraining"
          >
            {{ trainingIsRunning ? '训练正在进行' : '开始训练' }}
          </el-button>
        </section>

        <section class="surface-panel training-task">
          <div class="task-head">
            <div>
              <span class="section-kicker">LIVE TASK</span>
              <h3>训练任务</h3>
            </div>
            <span v-if="trainingProgress" class="task-status" :class="`is-${trainingProgress.status}`">
              <i />
              {{ modelStatusMeta(trainingProgress.status).label }}
            </span>
          </div>

          <template v-if="trainingProgress">
            <div class="epoch-line">
              <span>
                Epoch {{ trainingDetail.epoch || 0 }} /
                {{ trainingDetail.total_epochs || trainParams.epochs }}
              </span>
              <strong>{{ trainingPercentage }}%</strong>
            </div>
            <el-progress
              :percentage="trainingPercentage"
              :stroke-width="10"
              :show-text="false"
              :status="trainingProgress.status === 'error' ? 'exception' : undefined"
            />
            <p class="task-message">
              {{ trainingDetail.message || '等待训练进程上报实时指标' }}
            </p>
            <div class="task-metrics">
              <div>
                <span>Train Acc</span>
                <strong>{{ formatPercent(trainingDetail.train_acc) }}</strong>
              </div>
              <div>
                <span>Val Acc</span>
                <strong>{{ formatPercent(trainingDetail.val_acc) }}</strong>
              </div>
              <div>
                <span>Loss</span>
                <strong>{{ trainingDetail.loss ?? '—' }}</strong>
              </div>
            </div>
            <p v-if="trainingProgress.error_message" class="task-error">
              {{ trainingProgress.error_message }}
            </p>
            <el-button
              v-if="trainingIsRunning"
              class="cancel-training-btn"
              plain
              type="danger"
              :icon="Close"
              @click="cancelTraining"
            >
              取消训练
            </el-button>
          </template>

          <div v-else class="compact-empty">
            <el-icon><Timer /></el-icon>
            <strong>暂无实时训练任务</strong>
            <span>开始训练后，这里将展示 Epoch、准确率和 Loss。</span>
          </div>
        </section>
      </aside>

      <main class="surface-panel model-workspace">
        <div class="model-workspace-head">
          <div>
            <span class="section-kicker">MODEL REGISTRY</span>
            <h3>模型健康概览</h3>
          </div>
          <el-button :icon="Refresh" :loading="modelsLoading" @click="loadModels">刷新模型</el-button>
        </div>

        <div class="model-health">
          <div>
            <span>当前部署</span>
            <strong>{{ deployedModel?.version || '尚未部署' }}</strong>
            <small>{{ deployedModel ? `${(deployedModel.classes || []).length} 个类别` : '完成训练后可部署' }}</small>
          </div>
          <div>
            <span>最佳验证准确率</span>
            <strong class="accent-value">{{ formatPercent(bestModel?.metrics?.val_acc) }}</strong>
            <small>{{ bestModel ? `来自 ${bestModel.version}` : '暂无有效指标' }}</small>
          </div>
          <div>
            <span>最近训练状态</span>
            <strong :class="`status-text is-${latestModel?.status || 'empty'}`">
              {{ latestModel ? modelStatusMeta(latestModel.status).label : '暂无记录' }}
            </strong>
            <small>{{ formatDateTime(latestModel?.created_at) }}</small>
          </div>
        </div>

        <div class="registry-heading">
          <div>
            <h4>模型版本</h4>
            <span>共 {{ models.length }} 个训练版本</span>
          </div>
        </div>

        <el-table
          v-loading="modelsLoading"
          :data="models"
          class="model-table"
          :row-class-name="({ row }) => row.is_deployed ? 'is-deployed-row' : ''"
          empty-text="暂无模型版本"
        >
          <el-table-column label="版本" min-width="170">
            <template #default="{ row }">
              <div class="version-cell">
                <el-icon><Box /></el-icon>
                <div>
                  <strong>{{ row.version }}</strong>
                  <small v-if="row.is_deployed">当前生产模型</small>
                  <small v-else-if="Object.keys(row.roi_versions || {}).length">
                    {{ Object.keys(row.roi_versions || {}).length ? '已绑定首衡固定机位 ROI' : '未绑定 ROI' }}
                  </small>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="modelStatusMeta(row.status).type" effect="light" round>
                {{ modelStatusMeta(row.status).label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="类别数" width="86" align="center">
            <template #default="{ row }">{{ (row.classes || []).length }}</template>
          </el-table-column>
          <el-table-column label="验证准确率" width="116" align="center">
            <template #default="{ row }">
              <strong class="table-metric">{{ formatPercent(row.metrics?.val_acc) }}</strong>
            </template>
          </el-table-column>
          <el-table-column label="部署状态" width="108" align="center">
            <template #default="{ row }">
              <span v-if="row.is_deployed" class="deployed-label">
                <i />
                已部署
              </span>
              <span v-else class="muted-label">未部署</span>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" min-width="150">
            <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="96" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'done' && !row.is_deployed"
                link
                type="primary"
                @click="deployModel(row)"
              >
                部署
              </el-button>
              <span v-else-if="row.is_deployed" class="muted-label">使用中</span>
              <span v-else>—</span>
            </template>
          </el-table-column>
        </el-table>
      </main>
    </section>

    <!-- 识别测试 -->
    <section v-show="activeTab === 'recognize'" class="recognition-workspace" role="tabpanel">
      <div v-if="!deployedModel" class="surface-panel no-model-state">
        <span class="no-model-icon"><el-icon><Cpu /></el-icon></span>
        <h3>尚未部署识别模型</h3>
        <p>先在“训练与模型”中完成训练并部署一个模型，才能进行图片识别测试。</p>
        <el-button type="primary" @click="activeTab = 'train'">前往训练与模型</el-button>
      </div>

      <template v-else>
        <section class="surface-panel recognition-image-panel">
          <div class="panel-heading">
            <div>
              <span class="section-kicker">IMAGE INPUT</span>
              <h3>上传图片识别</h3>
            </div>
            <el-icon class="heading-icon"><Camera /></el-icon>
          </div>

          <div class="recognition-device">
            <span>固定机位</span>
            <div class="fixed-device-value">
              <strong>{{ deviceLabel(recognitionDevices[0]) || '首衡智能秤' }}</strong>
              <small>所有首衡设备使用相同拍摄角度和部署模型绑定的 ROI。</small>
            </div>
          </div>

          <div v-if="recognizePreview" class="recognition-preview">
            <img :src="recognizePreview" alt="待识别商品图片" />
            <div v-if="recognizeLoading" class="recognition-loading">
              <span class="loading-ring" />
              <strong>识别中</strong>
              <small>模型正在分析图片特征</small>
            </div>
          </div>

          <el-upload
            v-else
            class="recognition-dropzone"
            drag
            :show-file-list="false"
            :auto-upload="false"
            :on-change="onRecognize"
            accept="image/*"
          >
            <el-icon class="dropzone-icon"><UploadFilled /></el-icon>
            <h4>拖入一张秤盘图片</h4>
            <p>或点击选择 JPG、PNG、WebP 图片</p>
          </el-upload>

          <el-upload
            v-if="recognizePreview"
            class="recognition-reupload"
            :show-file-list="false"
            :auto-upload="false"
            :on-change="onRecognize"
            accept="image/*"
          >
            <el-button type="primary" :loading="recognizeLoading" :icon="UploadFilled">
              {{ recognizeLoading ? '正在识别' : '重新上传图片' }}
            </el-button>
          </el-upload>

          <div class="recognition-model-meta">
            <span>当前模型：<b>{{ deployedModel.version }}</b></span>
            <span>类别数量：<b>{{ (deployedModel.classes || []).length }}</b></span>
            <span>验证准确率：<b>{{ formatPercent(deployedModel.metrics?.val_acc) }}</b></span>
          </div>
        </section>

        <section class="surface-panel recognition-results-panel">
          <div class="results-heading">
            <div>
              <span class="section-kicker">INFERENCE RESULT</span>
              <h3>识别候选 Top {{ recognizeResults?.results?.length || 5 }}</h3>
            </div>
            <span v-if="recognizeResults" class="result-model">
              模型 {{ recognizeResults.model_version }}
            </span>
          </div>

          <div v-if="recognizeResults?.results?.length" class="candidate-list">
            <article
              v-for="(result, index) in recognizeResults.results"
              :key="`${result.category_id}-${index}`"
              class="candidate-row"
              :class="{ 'is-top': index === 0 }"
            >
              <span class="candidate-rank">{{ index + 1 }}</span>
              <div class="candidate-copy">
                <strong>{{ resultName(result) }}</strong>
                <small>
                  {{ result.product_id ? `SKU ID：${result.product_id}` : `类目 ID：${result.category_id}` }}
                </small>
              </div>
              <div class="confidence-column">
                <div class="confidence-head">
                  <strong>{{ formatPercent(result.score, 0) }}</strong>
                  <span
                    v-if="index === 0"
                    class="confidence-chip"
                    :class="confidenceMeta(result.score).className"
                  >
                    {{ confidenceMeta(result.score).label }}
                  </span>
                </div>
                <el-progress
                  :percentage="Math.round(Number(result.score || 0) * 100)"
                  :stroke-width="index === 0 ? 10 : 6"
                  :show-text="false"
                />
              </div>
            </article>
          </div>

          <div v-else class="result-empty">
            <el-icon><DataAnalysis /></el-icon>
            <h4>{{ recognizeLoading ? '正在生成识别候选' : '等待识别结果' }}</h4>
            <p>上传商品图片后，Top 5 候选及置信度会显示在这里。</p>
          </div>

          <div class="result-summary">
            <div>
              <span class="summary-icon"><el-icon><DataAnalysis /></el-icon></span>
              <div>
                <small>最高置信度</small>
                <strong>{{ formatPercent(recognizeTopResult?.score, 0) }}</strong>
              </div>
              <span
                v-if="recognizeTopResult"
                class="confidence-chip"
                :class="confidenceMeta(recognizeTopResult.score).className"
              >
                {{ confidenceMeta(recognizeTopResult.score).label }}
              </span>
            </div>
            <div>
              <span class="summary-icon is-violet"><el-icon><Box /></el-icon></span>
              <div>
                <small>当前模型</small>
                <strong>{{ recognizeResults?.model_version || deployedModel.version }}</strong>
              </div>
            </div>
          </div>
        </section>
      </template>
    </section>

    <el-dialog
      v-model="importVisible"
      class="ssr-import-dialog"
      title="补导历史收货照片"
      width="560px"
    >
      <div class="dialog-intro">
        <span><el-icon><UploadFilled /></el-icon></span>
        <div>
          <strong>仅用于补齐自动入池上线前的历史照片</strong>
          <p>按 SKU 自动归类并进入待审核池；重复执行不会产生重复样本。</p>
        </div>
      </div>
      <el-form label-position="top">
        <el-form-item label="确认收货日期范围（可空）">
          <div class="date-range-row">
            <el-date-picker
              v-model="importForm.date_from"
              type="date"
              placeholder="开始日期"
              value-format="YYYY-MM-DD"
            />
            <span>至</span>
            <el-date-picker
              v-model="importForm.date_to"
              type="date"
              placeholder="结束日期"
              value-format="YYYY-MM-DD"
            />
          </div>
        </el-form-item>
        <el-form-item label="商品过滤（可空 = 所有商品）">
          <el-select v-model="importForm.product_ids" multiple filterable placeholder="留空表示全部">
            <el-option v-for="product in products" :key="product.id" :label="product.name" :value="product.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="最多导入条数">
          <el-input-number v-model="importForm.limit" :min="1" :max="5000" />
        </el-form-item>
      </el-form>
      <div v-if="importResult" class="import-result">
        <div class="import-result-summary">
          <span><el-icon><CircleCheckFilled /></el-icon></span>
          <p>
            新增 <strong>{{ importResult.imported }}</strong> 张，跳过
            <strong>{{ importResult.skipped }}</strong> 张
          </p>
        </div>
        <ul v-if="importResult.by_product?.length">
          <li v-for="result in importResult.by_product" :key="result.product_id">
            <span>{{ result.product_name || `商品#${result.product_id}` }}</span>
            <b>{{ result.count }} 张</b>
          </li>
        </ul>
      </div>
      <template #footer>
        <el-button @click="importVisible = false">关闭</el-button>
        <el-button type="primary" :loading="importLoading" :icon="UploadFilled" @click="runImport">
          开始导入
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="roiVisible"
      class="roi-config-dialog"
      title="首衡固定机位 ROI"
      width="min(980px, 94vw)"
    >
      <div class="dialog-intro">
        <span><el-icon><Aim /></el-icon></span>
        <div>
          <strong>校准首衡智能秤统一训练与识别区域</strong>
          <p>所有首衡设备共用这套固定机位 ROI；保存新版本后，重新训练并部署才会切换线上配置。</p>
        </div>
      </div>
      <div class="roi-device-toolbar">
        <div class="roi-fixed-device">
          <span>机型与机位</span>
          <strong>{{ deviceLabel(selectedDevice) || '首衡智能秤' }}</strong>
          <small>统一固定拍摄角度</small>
        </div>
        <div>
          <span>当前配置</span>
          <strong>
            {{ selectedDevice?.roi_profile ? `ROI v${selectedDevice.roi_profile.version}` : '尚未配置' }}
          </strong>
        </div>
        <div>
          <span>最近拍摄</span>
          <strong>{{ formatDateTime(selectedDevice?.latest_photo_at) }}</strong>
        </div>
      </div>
      <RoiCropEditor
        v-model="roiDraft"
        :image-url="selectedDevice?.latest_image_url || ''"
        :disabled="!roiDeviceId"
      />
      <div v-if="roiDeviceId" class="roi-version-history">
        <span>版本记录</span>
        <el-tag
          v-for="profile in roiProfiles.filter((item) => item.device_id === roiDeviceId)"
          :key="profile.id"
          :type="profile.status === 'active' ? 'success' : 'info'"
          effect="plain"
          round
        >
          v{{ profile.version }} · {{ profile.status === 'active' ? '当前' : '历史' }}
        </el-tag>
      </div>
      <template #footer>
        <el-button @click="roiVisible = false">关闭</el-button>
        <el-button
          type="primary"
          :loading="roiSaving"
          :disabled="!selectedDevice?.latest_image_url"
          @click="saveRoiProfile"
        >
          保存为新版本
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="manualVisible"
      class="manual-sample-dialog"
      title="补录训练素材"
      width="min(940px, 94vw)"
    >
      <el-radio-group v-model="manualMode" class="manual-mode-switch" @change="onManualModeChange">
        <el-radio-button value="device">首衡照片补录</el-radio-button>
        <el-radio-button value="external">外部素材</el-radio-button>
      </el-radio-group>
      <div class="manual-mode-note">
        <strong>{{ manualMode === 'device' ? '自动继承首衡固定机位 ROI，可针对本图微调' : '必须人工框选商品区域' }}</strong>
        <span>
          {{ manualMode === 'device' ? '单图微调只保存为 override，不会修改首衡默认配置。' : '该素材会标记为非生产机位来源。' }}
        </span>
      </div>
      <div v-if="manualMode === 'device'" class="fixed-device-card">
        <span>素材来源</span>
        <strong>{{ deviceLabel(manualDevice) || '首衡智能秤' }}</strong>
        <small>上传时自动应用统一固定机位 ROI</small>
      </div>
      <RoiCropEditor
        v-model="manualRoi"
        :image-url="manualPreview"
        @change="onManualRoiChange"
      />
      <template #footer>
        <el-button @click="manualVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploadLoading" @click="submitManualSample">
          上传到待审核池
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="assignDeviceVisible" title="应用首衡 ROI 并重新裁剪" width="440px">
      <div class="fixed-device-card">
        <span>目标机位</span>
        <strong>{{ deviceLabel(devices[0]) || '首衡智能秤' }}</strong>
        <small>选中样本将使用统一固定机位 ROI 重新生成裁剪图。</small>
      </div>
      <template #footer>
        <el-button @click="assignDeviceVisible = false">取消</el-button>
        <el-button type="primary" @click="assignSelectedDevice">确认并重裁剪</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.ssr-page {
  --ssr-primary: var(--role-accent, #8b5cf6);
  --ssr-primary-dark: #6d3ee8;
  --ssr-primary-soft: #f2edff;
  --ssr-cyan: #0ea5e9;
  --ssr-success: #16a34a;
  --ssr-danger: #dc2626;
  --ssr-ink: #17203a;
  --ssr-muted: #68738d;
  --ssr-line: rgba(122, 102, 194, 0.18);
  min-width: 0;
  color: var(--ssr-ink);
  font-family: Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
}

.ssr-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(340px, 500px);
  gap: 24px;
  align-items: stretch;
  margin-bottom: 16px;
}

.hero-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  justify-content: center;
  padding: 8px 0;
}

.hero-eyebrow,
.section-kicker {
  color: var(--ssr-primary-dark);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
}

.hero-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  width: fit-content;
  margin-bottom: 9px;
}

.hero-copy h2 {
  margin: 0;
  color: #111a32;
  font-size: clamp(26px, 2.2vw, 36px);
  font-weight: 800;
  letter-spacing: -0.035em;
  line-height: 1.18;
}

.hero-copy p {
  max-width: 680px;
  margin: 10px 0 0;
  color: var(--ssr-muted);
  font-size: 14px;
  line-height: 1.75;
}

.roi-entry {
  width: fit-content;
  margin-top: 14px;
}

.deployment-card,
.surface-panel,
.overview-strip,
.workflow-nav {
  border: 1px solid var(--ssr-line);
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 16px 40px rgba(60, 42, 123, 0.06);
  backdrop-filter: blur(16px);
}

.deployment-card {
  position: relative;
  overflow: hidden;
  padding: 20px 22px;
  border-radius: 16px;
  background:
    radial-gradient(circle at 92% 10%, rgba(139, 92, 246, 0.15), transparent 35%),
    rgba(255, 255, 255, 0.9);
}

.deployment-card::before {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 4px;
  background: #22c55e;
  content: "";
}

.deployment-card.is-empty::before {
  background: #cbd5e1;
}

.deployment-head,
.deployment-metrics,
.panel-heading,
.list-heading,
.sample-workspace-head,
.gallery-heading,
.model-workspace-head,
.registry-heading,
.results-heading,
.task-head,
.epoch-line,
.confidence-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.deployment-head strong {
  display: block;
  margin-top: 6px;
  font-family: "JetBrains Mono", "DIN Alternate", monospace;
  font-size: 22px;
  letter-spacing: -0.03em;
}

.online-chip,
.ready-chip,
.sample-count-chip,
.confidence-chip,
.deployed-label,
.task-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 999px;
  white-space: nowrap;
}

.online-chip {
  padding: 5px 10px;
  color: #15803d;
  background: #ecfdf3;
  font-size: 12px;
  font-weight: 700;
}

.online-chip i,
.deployed-label i,
.task-status i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 0 4px color-mix(in srgb, currentColor 12%, transparent);
}

.online-chip.is-offline {
  color: #64748b;
  background: #f1f5f9;
}

.deployment-metrics {
  justify-content: flex-start;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid rgba(122, 102, 194, 0.14);
}

.deployment-metrics > div {
  min-width: 140px;
  padding-right: 24px;
}

.deployment-metrics > div + div {
  padding-left: 24px;
  border-left: 1px solid rgba(122, 102, 194, 0.16);
}

.deployment-metrics span,
.overview-item small,
.model-health span,
.task-metrics span,
.result-summary small {
  display: block;
  color: var(--ssr-muted);
  font-size: 12px;
}

.deployment-metrics b {
  display: block;
  margin-top: 5px;
  font-size: 18px;
}

.success-value {
  color: var(--ssr-success);
}

.overview-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 16px;
  overflow: hidden;
  border-radius: 16px;
}

.overview-item {
  display: flex;
  align-items: center;
  gap: 15px;
  min-width: 0;
  padding: 18px 24px;
}

.overview-item + .overview-item {
  border-left: 1px solid var(--ssr-line);
}

.metric-icon,
.summary-icon,
.no-model-icon {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  color: var(--ssr-primary-dark);
  background: var(--ssr-primary-soft);
}

.metric-icon {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  font-size: 22px;
}

.metric-icon.is-cyan {
  color: #0284c7;
  background: #e0f2fe;
}

.metric-icon.is-violet {
  color: #9333ea;
  background: #f3e8ff;
}

.metric-icon.is-amber {
  color: #b45309;
  background: #fef3c7;
}

.overview-item > div {
  min-width: 0;
}

.overview-item strong {
  display: inline-block;
  margin: 2px 7px 0 0;
  color: #111a32;
  font-family: "JetBrains Mono", "DIN Alternate", monospace;
  font-size: 25px;
}

.overview-item div > span {
  color: #8a94aa;
  font-size: 12px;
}

.workflow-nav {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-bottom: 16px;
  overflow: hidden;
  border-radius: 16px;
}

.workflow-step {
  position: relative;
  display: grid;
  grid-template-columns: 34px 28px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  min-width: 0;
  min-height: 82px;
  padding: 16px 22px;
  border: 0;
  color: #71809b;
  text-align: left;
  cursor: pointer;
  background: transparent;
  transition: color 180ms ease, background 180ms ease, box-shadow 180ms ease;
}

.workflow-step + .workflow-step {
  border-left: 1px solid var(--ssr-line);
}

.workflow-step:hover {
  color: var(--ssr-primary-dark);
  background: rgba(245, 242, 255, 0.72);
}

.workflow-step:focus,
.category-row:focus {
  outline: none;
}

.workflow-step:focus-visible,
.category-row:focus-visible {
  outline: 2px solid rgba(124, 58, 237, 0.72);
  outline-offset: -2px;
}

.workflow-step.is-active {
  color: var(--ssr-primary-dark);
  background: linear-gradient(135deg, rgba(242, 237, 255, 0.96), rgba(255, 255, 255, 0.94));
  box-shadow: inset 0 -3px 0 var(--ssr-primary);
}

.step-index {
  display: inline-flex;
  width: 32px;
  height: 32px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: #8b95ab;
  background: #f0f2f7;
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
  font-weight: 800;
}

.is-active .step-index {
  color: #fff;
  background: var(--ssr-primary);
  box-shadow: 0 8px 18px rgba(139, 92, 246, 0.24);
}

.step-icon {
  font-size: 24px;
}

.step-copy {
  min-width: 0;
}

.step-copy strong,
.step-copy small {
  display: block;
}

.step-copy strong {
  color: currentColor;
  font-size: 15px;
}

.step-copy small {
  margin-top: 4px;
  overflow: hidden;
  color: #8b95aa;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.catalog-workspace,
.training-workspace,
.recognition-workspace {
  min-width: 0;
}

.catalog-workspace {
  display: grid;
  grid-template-columns: minmax(300px, 360px) minmax(0, 1fr);
  gap: 16px;
}

.surface-panel {
  min-width: 0;
  border-radius: 16px;
}

.catalog-sidebar,
.sample-workspace,
.training-config,
.training-task,
.model-workspace,
.recognition-image-panel,
.recognition-results-panel {
  padding: 20px;
}

.panel-heading {
  align-items: flex-start;
}

.panel-heading h3,
.list-heading h3,
.selected-category h3,
.gallery-heading h4,
.model-workspace-head h3,
.registry-heading h4,
.training-task h3,
.results-heading h3 {
  margin: 4px 0 0;
  color: #17203a;
  font-size: 17px;
  line-height: 1.3;
}

.heading-icon {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  color: var(--ssr-primary-dark);
  background: var(--ssr-primary-soft);
  font-size: 20px;
}

.category-form {
  margin-top: 20px;
}

.category-form :deep(.el-select),
.category-form :deep(.el-input-number),
.parameter-list :deep(.el-input-number) {
  width: 100%;
}

.category-form :deep(.el-form-item) {
  margin-bottom: 16px;
}

.category-form :deep(.el-form-item__label) {
  padding-bottom: 7px;
  font-size: 13px;
}

.create-category-btn,
.start-training-btn {
  width: 100%;
}

.panel-divider {
  height: 1px;
  margin: 22px -20px 18px;
  background: var(--ssr-line);
}

.list-heading {
  align-items: flex-start;
  margin-bottom: 12px;
}

.list-heading > div > span,
.gallery-heading span,
.registry-heading span {
  display: block;
  margin-top: 3px;
  color: var(--ssr-muted);
  font-size: 12px;
}

.category-list {
  display: flex;
  min-height: 260px;
  max-height: 500px;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  padding-right: 3px;
}

.category-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto 32px;
  gap: 10px;
  align-items: center;
  padding: 12px 10px 11px 13px;
  border: 1px solid transparent;
  border-radius: 12px;
  cursor: pointer;
  background: #f8f9fc;
  transition: border-color 160ms ease, background 160ms ease, transform 160ms ease;
}

.category-row:hover {
  transform: translateY(-1px);
  border-color: rgba(139, 92, 246, 0.22);
}

.category-row.is-active {
  border-color: rgba(139, 92, 246, 0.4);
  background: var(--ssr-primary-soft);
  box-shadow: inset 3px 0 0 var(--ssr-primary);
}

.category-main {
  min-width: 0;
}

.category-title {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 6px;
}

.category-title > strong {
  min-width: 0;
}

.category-title > span {
  flex: 0 0 auto;
  padding: 2px 5px;
  border-radius: 5px;
  color: #166534;
  background: #dcfce7;
  font-size: 9px;
  font-weight: 700;
}

.category-main strong,
.category-main small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.category-main strong {
  color: #202944;
  font-size: 13px;
}

.category-main small {
  margin-top: 3px;
  color: #8993a8;
  font-size: 11px;
}

.readiness-track {
  height: 4px;
  margin-top: 9px;
  overflow: hidden;
  border-radius: 999px;
  background: #e2e6ef;
}

.readiness-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #8b5cf6, #60a5fa);
}

.category-count {
  text-align: right;
}

.category-count b,
.category-count span {
  display: block;
}

.category-count b {
  color: var(--ssr-primary-dark);
  font-family: "JetBrains Mono", monospace;
  font-size: 14px;
}

.category-count span {
  margin-top: 2px;
  color: #8a94aa;
  font-size: 10px;
}

.category-delete {
  opacity: 0.5;
}

.category-row:hover .category-delete {
  opacity: 1;
}

.sample-workspace {
  min-height: 600px;
}

.sample-workspace-head {
  align-items: flex-start;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--ssr-line);
}

.selected-category > div {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.selected-category h3 {
  margin: 0;
  font-size: 23px;
}

.selected-category p {
  margin: 7px 0 0;
  color: var(--ssr-muted);
  font-size: 12px;
}

.sample-count-chip,
.ready-chip {
  padding: 4px 9px;
  font-size: 11px;
  font-weight: 700;
}

.sample-count-chip {
  color: var(--ssr-primary-dark);
  background: var(--ssr-primary-soft);
}

.ready-chip {
  color: #a16207;
  background: #fef9c3;
}

.ready-chip.is-ready {
  color: #15803d;
  background: #dcfce7;
}

.sample-actions {
  display: flex;
  flex: 0 0 auto;
  gap: 10px;
}

.sample-guidance {
  display: flex;
  align-items: center;
  gap: 11px;
  margin: 16px 0 20px;
  padding: 11px 13px;
  border: 1px solid rgba(99, 102, 241, 0.18);
  border-radius: 11px;
  color: #4f5c78;
  background: #f7f8ff;
}

.sample-guidance > .el-icon {
  flex: 0 0 auto;
  color: var(--ssr-primary-dark);
  font-size: 18px;
}

.sample-guidance p {
  flex: 1;
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
}

.source-summary {
  display: flex;
  flex: 0 0 auto;
  gap: 12px;
  color: #7c879e;
  font-size: 11px;
}

.source-summary b {
  color: #2f3b58;
}

.gallery-heading {
  align-items: flex-end;
  margin-bottom: 12px;
}

.gallery-view-switch :deep(.el-button) {
  padding-inline: 12px;
  font-size: 11px;
}

.sample-filter-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.sample-filter-row button {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 7px;
  padding: 7px 10px;
  border: 1px solid rgba(122, 102, 194, 0.16);
  border-radius: 9px;
  color: #64708a;
  cursor: pointer;
  background: #fff;
}

.sample-filter-row button.is-active {
  border-color: rgba(139, 92, 246, 0.42);
  color: var(--ssr-primary-dark);
  background: var(--ssr-primary-soft);
}

.sample-filter-row span {
  font-size: 11px;
}

.sample-filter-row b {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
}

.bulk-action-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 9px 11px;
  border: 1px solid rgba(139, 92, 246, 0.22);
  border-radius: 11px;
  background: #faf8ff;
}

.bulk-action-bar > span {
  margin-right: auto;
  color: #4e5973;
  font-size: 12px;
  font-weight: 700;
}

.sample-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}

.sample-card {
  position: relative;
  min-width: 0;
  overflow: hidden;
  border: 1px solid rgba(116, 126, 154, 0.16);
  border-radius: 12px;
  background: #f3f5f9;
}

.sample-card.is-selected {
  border-color: rgba(139, 92, 246, 0.7);
  box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.12);
}

.sample-card :deep(.sample-thumb),
.sample-card :deep(.sample-thumb .el-image__inner) {
  width: 100%;
  height: 150px;
  display: block;
}

.sample-card :deep(.sample-thumb .el-image__inner) {
  cursor: zoom-in;
  transition: transform 220ms ease;
}

.sample-card:hover :deep(.sample-thumb .el-image__inner) {
  transform: scale(1.035);
}

.sample-overlay {
  position: absolute;
  top: 112px;
  right: 8px;
  left: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  pointer-events: none;
}

.sample-selector {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 2;
  padding: 3px 6px;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(8px);
}

.sample-card-meta {
  display: flex;
  min-height: 62px;
  flex-wrap: wrap;
  align-content: flex-start;
  gap: 5px 7px;
  padding: 10px;
  color: #7b879e;
  background: #fff;
  font-size: 9px;
}

.review-chip {
  padding: 2px 6px;
  border-radius: 999px;
  font-weight: 700;
}

.review-chip.is-pending {
  color: #a16207;
  background: #fef3c7;
}

.review-chip.is-approved {
  color: #15803d;
  background: #dcfce7;
}

.review-chip.is-attention {
  color: #c2410c;
  background: #ffedd5;
}

.review-chip.is-rejected {
  color: #b91c1c;
  background: #fee2e2;
}

.quality-warning {
  width: 100%;
  overflow: hidden;
  color: #c2410c;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sample-overlay .el-button {
  color: #fff;
  background: rgba(23, 32, 58, 0.68);
  pointer-events: auto;
  backdrop-filter: blur(8px);
}

.source-chip {
  padding: 4px 8px;
  border-radius: 7px;
  color: #465168;
  background: rgba(255, 255, 255, 0.88);
  font-size: 10px;
  font-weight: 700;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(8px);
}

.source-chip.is-receiving {
  color: #166534;
  background: rgba(240, 253, 244, 0.92);
}

.image-fallback {
  display: flex;
  height: 100%;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 7px;
  color: #94a3b8;
  font-size: 11px;
}

.image-fallback .el-icon {
  font-size: 28px;
}

.workspace-empty,
.compact-empty,
.result-empty,
.no-model-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--ssr-muted);
  text-align: center;
}

.workspace-empty {
  min-height: 360px;
}

.workspace-empty.is-large {
  min-height: 550px;
}

.workspace-empty > .el-icon {
  margin-bottom: 14px;
  color: #b8aedf;
  font-size: 50px;
}

.workspace-empty h4,
.result-empty h4 {
  margin: 0;
  color: #27324e;
  font-size: 16px;
}

.workspace-empty p,
.result-empty p {
  margin: 8px 0 18px;
  font-size: 12px;
}

.workspace-empty > div {
  display: flex;
  gap: 10px;
}

.training-workspace {
  display: grid;
  grid-template-columns: minmax(320px, 380px) minmax(0, 1fr);
  gap: 16px;
}

.training-sidebar {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 16px;
}

.parameter-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 20px;
}

.parameter-list label {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 126px;
  gap: 3px 14px;
  align-items: center;
}

.parameter-list label > span {
  color: #2b3652;
  font-size: 13px;
  font-weight: 700;
}

.parameter-list label > small {
  grid-column: 1;
  color: #929caf;
  font-size: 10px;
}

.parameter-list label > .el-input-number {
  grid-column: 2;
  grid-row: 1 / span 2;
}

.eligibility-box {
  display: flex;
  align-items: center;
  gap: 11px;
  margin: 20px 0 14px;
  padding: 13px;
  border: 1px solid #fed7aa;
  border-radius: 11px;
  color: #a16207;
  background: #fffbeb;
}

.eligibility-box.is-ready {
  border-color: #bbf7d0;
  color: #15803d;
  background: #f0fdf4;
}

.eligibility-box > .el-icon {
  font-size: 20px;
}

.eligibility-box strong,
.eligibility-box span {
  display: block;
}

.eligibility-box strong {
  font-size: 12px;
}

.eligibility-box span {
  margin-top: 3px;
  color: #768197;
  font-size: 10px;
}

.training-task {
  min-height: 250px;
}

.task-status {
  padding: 5px 9px;
  color: #64748b;
  background: #f1f5f9;
  font-size: 11px;
  font-weight: 700;
}

.task-status.is-running,
.task-status.is-preparing {
  color: #15803d;
  background: #ecfdf3;
}

.task-status.is-error {
  color: #b91c1c;
  background: #fef2f2;
}

.epoch-line {
  margin: 22px 0 9px;
  color: #4b5872;
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
}

.epoch-line strong {
  color: var(--ssr-primary-dark);
}

.task-message {
  min-height: 19px;
  margin: 10px 0 15px;
  color: var(--ssr-muted);
  font-size: 11px;
}

.task-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 12px;
  border-top: 1px solid var(--ssr-line);
  border-bottom: 1px solid var(--ssr-line);
}

.task-metrics > div {
  padding: 14px 8px;
  text-align: center;
}

.task-metrics > div + div {
  border-left: 1px solid var(--ssr-line);
}

.task-metrics strong {
  display: block;
  margin-top: 4px;
  color: #222d49;
  font-family: "JetBrains Mono", monospace;
  font-size: 17px;
}

.task-error {
  margin: 12px 0 0;
  color: var(--ssr-danger);
  font-size: 11px;
}

.cancel-training-btn {
  width: 100%;
  margin-top: 14px;
}

.compact-empty {
  min-height: 170px;
  gap: 7px;
}

.compact-empty .el-icon {
  margin-bottom: 6px;
  color: #b8aedf;
  font-size: 34px;
}

.compact-empty strong {
  color: #34405c;
  font-size: 13px;
}

.compact-empty span {
  max-width: 260px;
  font-size: 11px;
  line-height: 1.6;
}

.model-workspace {
  overflow: hidden;
}

.model-workspace-head {
  align-items: flex-start;
}

.model-health {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: 20px 0;
  overflow: hidden;
  border: 1px solid var(--ssr-line);
  border-radius: 13px;
  background: #fafaff;
}

.model-health > div {
  min-width: 0;
  padding: 18px;
}

.model-health > div + div {
  border-left: 1px solid var(--ssr-line);
}

.model-health strong,
.model-health small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-health strong {
  margin-top: 7px;
  color: #1b2643;
  font-family: "JetBrains Mono", monospace;
  font-size: 17px;
}

.model-health small {
  margin-top: 5px;
  color: #8a94aa;
  font-size: 10px;
}

.model-health .accent-value {
  color: var(--ssr-primary-dark);
}

.status-text.is-done {
  color: var(--ssr-success);
}

.status-text.is-error {
  color: var(--ssr-danger);
}

.status-text.is-running,
.status-text.is-preparing {
  color: #0284c7;
}

.registry-heading {
  margin-bottom: 10px;
}

.model-table {
  width: 100%;
}

.model-table :deep(.el-table__inner-wrapper::before) {
  display: none;
}

.model-table :deep(th.el-table__cell) {
  height: 46px;
  color: #59647c;
  background: #f7f6fc;
  font-size: 11px;
}

.model-table :deep(td.el-table__cell) {
  height: 58px;
  color: #4b5670;
  font-size: 12px;
}

.model-table :deep(.is-deployed-row td.el-table__cell:first-child) {
  box-shadow: inset 3px 0 0 #22c55e;
}

.model-table :deep(.is-deployed-row td.el-table__cell) {
  background: #f6fff8;
}

.version-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.version-cell > .el-icon {
  color: var(--ssr-primary-dark);
  font-size: 19px;
}

.version-cell strong,
.version-cell small {
  display: block;
}

.version-cell strong,
.table-metric {
  color: #27324d;
  font-family: "JetBrains Mono", monospace;
}

.version-cell small {
  margin-top: 3px;
  color: #16a34a;
  font-size: 10px;
}

.deployed-label {
  color: #15803d;
  font-size: 11px;
  font-weight: 700;
}

.muted-label {
  color: #99a2b5;
  font-size: 11px;
}

.recognition-workspace {
  display: grid;
  grid-template-columns: minmax(360px, 0.92fr) minmax(0, 1.08fr);
  gap: 16px;
}

.recognition-image-panel,
.recognition-results-panel {
  min-height: 570px;
}

.recognition-preview {
  position: relative;
  min-height: 360px;
  margin-top: 18px;
  overflow: hidden;
  border: 1px solid rgba(82, 69, 150, 0.2);
  border-radius: 14px;
  background: #f0f2f6;
}

.recognition-preview::after {
  position: absolute;
  inset: 14px;
  border: 1px solid rgba(14, 165, 233, 0.5);
  border-radius: 10px;
  content: "";
  pointer-events: none;
  box-shadow: inset 0 0 28px rgba(14, 165, 233, 0.08);
}

.recognition-preview img {
  display: block;
  width: 100%;
  height: 420px;
  object-fit: contain;
}

.recognition-loading {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: rgba(17, 24, 39, 0.52);
  backdrop-filter: blur(3px);
}

.loading-ring {
  width: 44px;
  height: 44px;
  margin-bottom: 12px;
  border: 3px solid rgba(255, 255, 255, 0.28);
  border-top-color: #fff;
  border-radius: 50%;
  animation: ssr-spin 800ms linear infinite;
}

.recognition-loading strong {
  font-size: 15px;
}

.recognition-loading small {
  margin-top: 5px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 11px;
}

@keyframes ssr-spin {
  to { transform: rotate(360deg); }
}

.recognition-dropzone {
  display: block;
  margin-top: 18px;
}

.recognition-dropzone :deep(.el-upload),
.recognition-dropzone :deep(.el-upload-dragger) {
  width: 100%;
}

.recognition-dropzone :deep(.el-upload-dragger) {
  display: flex;
  min-height: 390px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 1px dashed rgba(139, 92, 246, 0.42);
  border-radius: 14px;
  background: #faf9ff;
}

.dropzone-icon {
  color: var(--ssr-primary);
  font-size: 54px;
}

.recognition-dropzone h4 {
  margin: 18px 0 0;
  color: #26314d;
  font-size: 16px;
}

.recognition-dropzone p {
  margin: 8px 0 0;
  color: var(--ssr-muted);
  font-size: 12px;
}

.recognition-reupload {
  display: flex;
  justify-content: center;
  margin-top: 14px;
}

.recognition-model-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 12px 20px;
  margin-top: 16px;
  padding: 12px;
  border-radius: 10px;
  color: #69748b;
  background: #f7f7fb;
  font-size: 11px;
}

.recognition-model-meta b {
  color: var(--ssr-primary-dark);
  font-family: "JetBrains Mono", monospace;
}

.results-heading {
  align-items: flex-start;
  padding-bottom: 17px;
  border-bottom: 1px solid var(--ssr-line);
}

.result-model {
  color: var(--ssr-primary-dark);
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
}

.candidate-list {
  display: flex;
  flex-direction: column;
  gap: 9px;
  margin-top: 16px;
}

.candidate-row {
  display: grid;
  grid-template-columns: 34px minmax(120px, 0.75fr) minmax(160px, 1.25fr);
  gap: 12px;
  align-items: center;
  padding: 12px 14px;
  border: 1px solid rgba(118, 129, 157, 0.15);
  border-radius: 12px;
  background: #fff;
}

.candidate-row.is-top {
  padding: 17px 16px;
  border-color: rgba(139, 92, 246, 0.38);
  background: linear-gradient(135deg, rgba(247, 244, 255, 0.96), #fff);
  box-shadow: 0 12px 28px rgba(78, 56, 153, 0.07);
}

.candidate-rank {
  display: inline-flex;
  width: 30px;
  height: 30px;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  color: #727d94;
  background: #f0f2f7;
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
  font-weight: 800;
}

.is-top .candidate-rank {
  color: #fff;
  background: var(--ssr-primary);
}

.candidate-copy {
  min-width: 0;
}

.candidate-copy strong,
.candidate-copy small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.candidate-copy strong {
  color: #28334f;
  font-size: 14px;
}

.is-top .candidate-copy strong {
  font-size: 17px;
}

.candidate-copy small {
  margin-top: 4px;
  color: #8b95aa;
  font-size: 10px;
}

.confidence-column {
  min-width: 0;
}

.confidence-head {
  justify-content: flex-end;
  margin-bottom: 7px;
}

.confidence-head strong {
  color: var(--ssr-primary-dark);
  font-family: "JetBrains Mono", monospace;
  font-size: 14px;
}

.is-top .confidence-head strong {
  font-size: 20px;
}

.confidence-chip {
  padding: 4px 8px;
  font-size: 10px;
  font-weight: 700;
}

.confidence-chip.is-high {
  color: #15803d;
  background: #dcfce7;
}

.confidence-chip.is-medium {
  color: #a16207;
  background: #fef9c3;
}

.confidence-chip.is-low {
  color: #64748b;
  background: #f1f5f9;
}

.result-empty {
  min-height: 350px;
}

.result-empty > .el-icon {
  margin-bottom: 14px;
  color: #b8aedf;
  font-size: 48px;
}

.result-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: 18px;
  overflow: hidden;
  border: 1px solid var(--ssr-line);
  border-radius: 13px;
  background: #fafaff;
}

.result-summary > div {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 12px;
  padding: 16px;
}

.result-summary > div + div {
  border-left: 1px solid var(--ssr-line);
}

.summary-icon {
  width: 38px;
  height: 38px;
  border-radius: 11px;
  color: #0284c7;
  background: #e0f2fe;
  font-size: 19px;
}

.summary-icon.is-violet {
  color: var(--ssr-primary-dark);
  background: var(--ssr-primary-soft);
}

.result-summary strong {
  display: block;
  max-width: 180px;
  margin-top: 3px;
  overflow: hidden;
  color: #27324d;
  font-family: "JetBrains Mono", monospace;
  font-size: 17px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-summary .confidence-chip {
  margin-left: auto;
}

.no-model-state {
  grid-column: 1 / -1;
  min-height: 520px;
  padding: 40px;
}

.no-model-icon {
  width: 68px;
  height: 68px;
  margin-bottom: 18px;
  border-radius: 20px;
  font-size: 34px;
}

.no-model-state h3 {
  margin: 0;
  color: #27324e;
  font-size: 20px;
}

.no-model-state p {
  max-width: 430px;
  margin: 10px 0 22px;
  font-size: 13px;
  line-height: 1.7;
}

.dialog-intro {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
  padding: 13px;
  border: 1px solid var(--ssr-line);
  border-radius: 12px;
  background: #f8f7ff;
}

.roi-device-toolbar {
  display: grid;
  grid-template-columns: minmax(260px, 1.4fr) repeat(2, minmax(150px, 0.7fr));
  gap: 12px;
  margin-bottom: 14px;
}

.roi-device-toolbar > label,
.roi-device-toolbar > div {
  min-width: 0;
  padding: 11px 12px;
  border: 1px solid var(--ssr-line);
  border-radius: 11px;
  background: #fafbff;
}

.roi-device-toolbar span,
.roi-device-toolbar strong {
  display: block;
}

.roi-device-toolbar span {
  margin-bottom: 6px;
  color: #7b879e;
  font-size: 10px;
}

.roi-device-toolbar strong {
  overflow: hidden;
  color: #2c3753;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.roi-fixed-device small,
.fixed-device-card small {
  display: block;
  margin-top: 4px;
  color: #8b95aa;
  font-size: 10px;
}

.roi-device-toolbar :deep(.el-select) {
  width: 100%;
}

.roi-version-history {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px;
  margin-top: 14px;
}

.roi-version-history > span {
  margin-right: 3px;
  color: #6f7a92;
  font-size: 11px;
  font-weight: 700;
}

.manual-mode-switch {
  margin-bottom: 12px;
}

.manual-mode-note {
  margin-bottom: 14px;
  padding: 11px 12px;
  border-radius: 10px;
  color: #5a6681;
  background: #f7f8ff;
}

.manual-mode-note strong,
.manual-mode-note span {
  display: block;
}

.manual-mode-note strong {
  color: #33405d;
  font-size: 12px;
}

.manual-mode-note span {
  margin-top: 4px;
  font-size: 10px;
}

.fixed-device-card {
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid var(--ssr-line);
  border-radius: 11px;
  background: #fafbff;
}

.fixed-device-card > span,
.fixed-device-card > strong {
  display: block;
}

.fixed-device-card > span {
  margin-bottom: 5px;
  color: #7b879e;
  font-size: 10px;
}

.fixed-device-card > strong {
  color: #2c3753;
  font-size: 13px;
}

.manual-sample-dialog :deep(.el-select),
.assign-device-dialog :deep(.el-select) {
  width: 100%;
}

:global(.roi-config-dialog.el-dialog),
:global(.manual-sample-dialog.el-dialog) {
  --el-dialog-bg-color: #fff;
  overflow: hidden;
  border: 1px solid rgba(122, 102, 194, 0.2);
  border-radius: 16px;
  opacity: 1;
  background: #fff !important;
  box-shadow: 0 28px 80px rgba(31, 24, 74, 0.24);
}

:global(.roi-config-dialog.el-dialog .el-dialog__header),
:global(.roi-config-dialog.el-dialog .el-dialog__body),
:global(.roi-config-dialog.el-dialog .el-dialog__footer),
:global(.manual-sample-dialog.el-dialog .el-dialog__header),
:global(.manual-sample-dialog.el-dialog .el-dialog__body),
:global(.manual-sample-dialog.el-dialog .el-dialog__footer) {
  opacity: 1;
  background: #fff !important;
}

.recognition-device {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr);
  gap: 5px 10px;
  align-items: center;
  margin: 16px 0;
  padding: 11px 12px;
  border: 1px solid var(--ssr-line);
  border-radius: 11px;
  background: #fafbff;
}

.recognition-device > span {
  color: #44506c;
  font-size: 12px;
  font-weight: 700;
}

.fixed-device-value strong,
.fixed-device-value small {
  display: block;
}

.fixed-device-value strong {
  color: #2c3753;
  font-size: 13px;
}

.fixed-device-value small {
  margin-top: 3px;
  color: #8b95aa;
  font-size: 10px;
}

.dialog-intro > span {
  display: inline-flex;
  width: 38px;
  height: 38px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 11px;
  color: var(--ssr-primary-dark);
  background: var(--ssr-primary-soft);
  font-size: 19px;
}

.dialog-intro strong {
  color: #29344f;
  font-size: 13px;
}

.dialog-intro p {
  margin: 4px 0 0;
  color: var(--ssr-muted);
  font-size: 11px;
  line-height: 1.5;
}

.date-range-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  width: 100%;
}

.date-range-row :deep(.el-date-editor) {
  width: 100%;
}

.date-range-row > span {
  color: #8b95aa;
  font-size: 12px;
}

.import-result {
  margin-top: 10px;
  padding: 13px;
  border: 1px solid #bbf7d0;
  border-radius: 12px;
  background: #f0fdf4;
}

.import-result-summary {
  display: flex;
  align-items: center;
  gap: 9px;
  color: #15803d;
}

.import-result-summary p {
  margin: 0;
  font-size: 12px;
}

.import-result ul {
  margin: 10px 0 0;
  padding: 10px 0 0;
  border-top: 1px solid #dcfce7;
  list-style: none;
}

.import-result li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 0;
  color: #4b6655;
  font-size: 11px;
}

@media (max-width: 1180px) {
  .ssr-hero {
    grid-template-columns: minmax(0, 1fr) 380px;
  }

  .catalog-workspace,
  .training-workspace {
    grid-template-columns: 320px minmax(0, 1fr);
  }

  .sample-actions {
    flex-direction: column;
  }

  .sample-actions :deep(.el-button),
  .sample-actions :deep(.el-upload) {
    width: 100%;
  }

  .recognition-workspace {
    grid-template-columns: minmax(320px, 0.9fr) minmax(0, 1.1fr);
  }
}

@media (max-width: 900px) {
  .ssr-hero,
  .catalog-workspace,
  .training-workspace,
  .recognition-workspace {
    grid-template-columns: minmax(0, 1fr);
  }

  .overview-strip,
  .workflow-nav {
    grid-template-columns: minmax(0, 1fr);
  }

  .roi-device-toolbar {
    grid-template-columns: 1fr;
  }

  .overview-item + .overview-item {
    border-top: 1px solid var(--ssr-line);
    border-left: 0;
  }

  .workflow-step + .workflow-step {
    border-top: 1px solid var(--ssr-line);
    border-left: 0;
  }

  .deployment-card {
    min-width: 0;
  }

  .workflow-step {
    grid-template-columns: 32px minmax(0, 1fr);
  }

  .step-icon {
    display: none;
  }

  .sample-workspace-head {
    flex-direction: column;
  }

  .sample-actions {
    width: 100%;
    flex-direction: row;
  }

  .category-list {
    max-height: 360px;
  }

  .recognition-image-panel,
  .recognition-results-panel {
    min-height: auto;
  }
}

@media (max-width: 640px) {
  .ssr-hero {
    gap: 14px;
  }

  .workflow-step {
    min-height: 68px;
  }

  .sample-actions,
  .workspace-empty > div {
    flex-direction: column;
  }

  .sample-actions :deep(.el-button),
  .sample-actions :deep(.el-upload),
  .workspace-empty :deep(.el-button),
  .workspace-empty :deep(.el-upload) {
    width: 100%;
  }

  .sample-guidance {
    align-items: flex-start;
  }

  .gallery-heading,
  .bulk-action-bar {
    align-items: stretch;
    flex-direction: column;
  }

  .gallery-view-switch :deep(.el-button-group),
  .gallery-view-switch :deep(.el-button) {
    width: 100%;
  }

  .bulk-action-bar > span {
    margin-right: 0;
  }

  .bulk-action-bar :deep(.el-button) {
    width: 100%;
    margin-left: 0;
  }

  .recognition-device {
    grid-template-columns: 1fr;
  }

  .source-summary {
    flex-direction: column;
    gap: 4px;
  }

  .sample-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .model-health,
  .result-summary {
    grid-template-columns: 1fr;
  }

  .model-health > div + div,
  .result-summary > div + div {
    border-top: 1px solid var(--ssr-line);
    border-left: 0;
  }

  .candidate-row,
  .candidate-row.is-top {
    grid-template-columns: 32px minmax(0, 1fr);
    padding: 12px;
  }

  .confidence-column {
    grid-column: 1 / -1;
  }

  .recognition-preview img {
    height: 300px;
  }

  .date-range-row {
    grid-template-columns: 1fr;
  }

  .date-range-row > span {
    text-align: center;
  }
}
</style>
