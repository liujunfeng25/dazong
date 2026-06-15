<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import {
  createOrderApi,
  ocrEngineStatusApi,
  orderMetaApi,
  parseOrderByOcrApi,
  parseOrderByVoiceApi,
  searchOrderProductsApi,
} from '../../api/orders'
import { useUserStore } from '../../stores/user'
import { useIsMobile } from '../../composables/useIsMobile'
import {
  productStandardTypeCardClass,
  productStandardTypeLabel,
} from '../../utils/productStandardType'
import { resolveCategoryImage } from '../../utils/categoryImage'

const catImage = (cat) => resolveCategoryImage(cat?.name, cat?.image_url)

const { isMobile } = useIsMobile()
const cartDrawerSize = computed(() => (isMobile.value ? '92vw' : '440px'))
const formLabelWidth = computed(() => (isMobile.value ? '72px' : '100px'))

const form = reactive({
  delivery_id: null,
  items: [],
})
const userStore = useUserStore()
const deliveryOptions = ref([])
/** 当前配送单位对应合约的一级分类上浮（与下单计价一致） */
const contractRates = ref(null)
const productOptions = ref([])
const productSearchLoading = ref(false)
let searchTimer = null
const ocrProgress = ref(0)
const ocrLoading = ref(false)
const ocrEngineInfo = ref(null)
const ocrPreviewVisible = ref(false)
const ocrPreviewData = ref(null)
const voiceText = ref('')
const showVoiceInput = ref(false)
const submitting = ref(false)
const scheduleDialogVisible = ref(false)
const scheduleForm = reactive({
  delivery_date: '',
  delivery_slot_start: '',
  delivery_slot_end: '',
  delivery_address: '',
  delivery_lng: null,
  delivery_lat: null,
  service_duration_min: 30,
})

const hourOptions = Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, '0')}:00`)
const endHourOptions = [...hourOptions.slice(1), '24:00']

const isTodaySelected = computed(() => {
  if (!scheduleForm.delivery_date) return false
  const t = new Date()
  const y = t.getFullYear()
  const m = String(t.getMonth() + 1).padStart(2, '0')
  const d = String(t.getDate()).padStart(2, '0')
  return scheduleForm.delivery_date === `${y}-${m}-${d}`
})

/** 当日下单时最早可选的开始整点：向上取整(now + 2h)，例如 11:30 -> 14:00；23:30 -> 跨天则不可选 */
const earliestStartHourToday = () => {
  const now = new Date()
  const cutoff = new Date(now.getTime() + 2 * 60 * 60 * 1000)
  const h = cutoff.getHours()
  const mm = cutoff.getMinutes()
  const s = cutoff.getSeconds()
  return mm === 0 && s === 0 ? h : h + 1 // 不到整点就向上取整
}

const isStartHourDisabled = (hStr) => {
  if (!isTodaySelected.value) return false
  const h = parseInt(hStr.slice(0, 2), 10)
  return h < earliestStartHourToday()
}

const isEndHourDisabled = (hStr) => {
  if (!scheduleForm.delivery_slot_start) return false
  const start = parseInt(scheduleForm.delivery_slot_start.slice(0, 2), 10)
  const end = hStr === '24:00' ? 24 : parseInt(hStr.slice(0, 2), 10)
  return end <= start
}

const disabledOrderDate = (d) => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return d.getTime() < today.getTime()
}

watch(
  () => scheduleForm.delivery_date,
  () => {
    if (scheduleForm.delivery_slot_start && isStartHourDisabled(scheduleForm.delivery_slot_start)) {
      scheduleForm.delivery_slot_start = ''
      scheduleForm.delivery_slot_end = ''
    }
  },
)
watch(
  () => scheduleForm.delivery_slot_start,
  () => {
    if (scheduleForm.delivery_slot_end && isEndHourDisabled(scheduleForm.delivery_slot_end)) {
      scheduleForm.delivery_slot_end = ''
    }
  },
)

/** 商品陈列区 */
const catalogKeyword = ref('')
const catalogPage = ref(1)
const catalogPageSize = ref(24)
const catalogTotal = ref(0)
const catalogProducts = ref([])
const catalogLoading = ref(false)
const catalogLoadingMore = ref(false)
const catalogCategoryId = ref(null)
const catalogCategory2Id = ref(null)
const contractCategories = ref([])
const catalogGridRef = ref(null)
const catalogLoadMoreRef = ref(null)
let catalogSearchTimer = null
let catalogLoadMoreObserver = null

const catalogHasMore = computed(() => catalogProducts.value.length < catalogTotal.value)
// 选中一级分类下的二级子分类（用于顶部二级 chip）
const subCategories = computed(() => {
  if (catalogCategoryId.value == null) return []
  const cat = contractCategories.value.find((c) => c.id === catalogCategoryId.value)
  return Array.isArray(cat?.children) ? cat.children : []
})

/** 卡片上「加入购物车」默认数量 */
const addQtyMap = reactive({})

/** 购物车抽屉 */
const cartDrawerVisible = ref(false)

const cartLineCount = computed(() => form.items.length)
const matchedLineCount = computed(() => form.items.filter((i) => Number(i.product_id) > 0).length)
const pendingLineCount = computed(() => Math.max(cartLineCount.value - matchedLineCount.value, 0))
const cartPieceCount = computed(() =>
  form.items.reduce((acc, i) => acc + (Number(i.quantity) || 0), 0),
)
const matchedPieceCount = computed(() =>
  form.items.reduce((acc, i) => acc + (Number(i.product_id) > 0 ? Number(i.quantity) || 0 : 0), 0),
)
const estimatedTotal = computed(() =>
  form.items.reduce(
    (acc, item) => acc + (Number(item.quantity) || 0) * (Number(item.unit_price) || 0),
    0,
  ),
)

const ocrPreviewTable = computed(() => {
  const t = ocrPreviewData.value?.structured?.tables?.[0]
  if (!t) return null
  return { headers: t.headers || [], rows: t.rows || [] }
})

const normalizeForSubmit = () => ({
  delivery_id: form.delivery_id,
  delivery_address: scheduleForm.delivery_address?.trim() || '',
  delivery_lng:
    scheduleForm.delivery_lng === null || scheduleForm.delivery_lng === '' ? null : Number(scheduleForm.delivery_lng),
  delivery_lat:
    scheduleForm.delivery_lat === null || scheduleForm.delivery_lat === '' ? null : Number(scheduleForm.delivery_lat),
  expected_delivery_date: scheduleForm.delivery_date,
  expected_delivery_slot:
    scheduleForm.delivery_slot_start && scheduleForm.delivery_slot_end
      ? `${scheduleForm.delivery_slot_start}-${scheduleForm.delivery_slot_end}`
      : '',
  service_duration_min: Number(scheduleForm.service_duration_min) || 30,
  items: form.items.map((i) => ({
    product_id: Number(i.product_id),
    quantity: Number(i.quantity) || 1,
    unit_price: Number(i.unit_price) || 0,
  })),
})

const loadCatalog = async (append = false) => {
  if (append) {
    if (catalogLoadingMore.value || catalogLoading.value || !catalogHasMore.value) return
    catalogLoadingMore.value = true
  } else {
    catalogLoading.value = true
  }
  try {
    const res = await searchOrderProductsApi({
      keyword: catalogKeyword.value || undefined,
      page: catalogPage.value,
      page_size: catalogPageSize.value,
      delivery_id: form.delivery_id || undefined,
      category1_id: catalogCategoryId.value || undefined,
      category2_id: catalogCategory2Id.value || undefined,
    })
    const items = res.items || []
    catalogProducts.value = append ? [...catalogProducts.value, ...items] : items
    catalogTotal.value = res.total ?? 0
  } finally {
    catalogLoading.value = false
    catalogLoadingMore.value = false
    if (isMobile.value) {
      await nextTick()
      setupCatalogLoadMoreObserver()
    }
  }
}

const loadMoreCatalog = async () => {
  if (!catalogHasMore.value || catalogLoading.value || catalogLoadingMore.value) return
  catalogPage.value += 1
  await loadCatalog(true)
}

const selectCatalogCategory = (categoryId) => {
  catalogCategoryId.value = categoryId
  catalogCategory2Id.value = null // 切一级时重置二级
  catalogPage.value = 1
  loadCatalog()
}

const selectCatalogCategory2 = (categoryId) => {
  catalogCategory2Id.value = categoryId
  catalogPage.value = 1
  loadCatalog()
}

const setupCatalogLoadMoreObserver = () => {
  if (!isMobile.value) return
  catalogLoadMoreObserver?.disconnect()
  catalogLoadMoreObserver = null
  if (!catalogLoadMoreRef.value || !catalogGridRef.value) return
  catalogLoadMoreObserver = new IntersectionObserver(
    (entries) => {
      if (entries[0]?.isIntersecting) loadMoreCatalog()
    },
    { root: catalogGridRef.value, rootMargin: '120px', threshold: 0 },
  )
  catalogLoadMoreObserver.observe(catalogLoadMoreRef.value)
}

const debouncedCatalogSearch = () => {
  clearTimeout(catalogSearchTimer)
  catalogSearchTimer = setTimeout(() => {
    catalogPage.value = 1
    loadCatalog()
  }, 280)
}

watch(catalogPage, () => {
  if (isMobile.value) return
  loadCatalog()
})

const onDeliveryChange = async () => {
  scheduleForm.delivery_date = ''
  scheduleForm.delivery_slot_start = ''
  scheduleForm.delivery_slot_end = ''
  catalogCategoryId.value = null
  catalogCategory2Id.value = null
  catalogPage.value = 1
  hydrateScheduleAddressFromUser(true)
  scheduleForm.service_duration_min = 30
  await refreshContractRates()
  await loadCatalog()
  recalcCartUnitPrices()
}

const getAddQty = (productId) => {
  const q = addQtyMap[productId]
  return q != null && q >= 1 ? q : 1
}

const setAddQty = (productId, val) => {
  const n = Number(val)
  addQtyMap[productId] = n >= 1 ? n : 1
}

/** 与后端下单计价一致：有合约价用合约价，否则参考价 */
const lineUnitPriceFromProduct = (p) => {
  if (form.delivery_id && p.contract_unit_price != null && p.contract_unit_price !== undefined) {
    return Number(p.contract_unit_price)
  }
  return Number(p.reference_price) || 0
}

/** 指导价：商品基础参考价（入库参考价） */
const guidePriceDisplay = (p) => {
  if (!p) return 0
  if (p.guide_price != null && p.guide_price !== undefined) return Number(p.guide_price)
  return Number(p.reference_price) || 0
}

/** 指导上限价：基础价×(1+运营端为该一级分类设置的「最高上浮率上限」max_float_rate） */
const guideCeilingDisplay = (p) => {
  if (!p) return 0
  if (p.guide_ceiling_price != null && p.guide_ceiling_price !== undefined) {
    return Number(p.guide_ceiling_price)
  }
  const ref = Number(p.reference_price) || 0
  const cap = Number(p.category_max_float_rate ?? 1)
  return Math.round(ref * (1 + cap) * 100) / 100
}

const recalcCartUnitPrices = () => {
  const by = contractRates.value?.by_category || {}
  const fb = Number(contractRates.value?.fallback ?? 0)
  for (const item of form.items) {
    if (item.reference_price == null || item.category1_id == null) continue
    const k1 = String(item.category1_id)
    const r = by[k1] ?? by[item.category1_id] ?? fb
    item.unit_price = Math.round(Number(item.reference_price) * (1 + Number(r || 0)) * 100) / 100
  }
}

/** 仅合并已匹配（product_id>0）的购物车行；未匹配行保留原样 */
const mergeMatchedCartItems = () => {
  const merged = []
  const idxByProduct = new Map()
  for (const row of form.items) {
    const pid = Number(row.product_id || 0)
    if (!pid) {
      merged.push({ ...row })
      continue
    }
    const hit = idxByProduct.get(pid)
    if (hit == null) {
      idxByProduct.set(pid, merged.length)
      merged.push({ ...row, quantity: Number(row.quantity) || 0 })
      continue
    }
    const target = merged[hit]
    target.quantity = Number(target.quantity || 0) + (Number(row.quantity) || 0)
    // 合并时优先保留完整字段，单价最终由合约重算
    if (!target.product_name && row.product_name) target.product_name = row.product_name
    if (!target.unit && row.unit) target.unit = row.unit
    if (target.reference_price == null && row.reference_price != null) target.reference_price = row.reference_price
    if (target.category1_id == null && row.category1_id != null) target.category1_id = row.category1_id
  }
  form.items = merged
  recalcCartUnitPrices()
}

const upsertCartItem = (p, quantity = 1, silent = false) => {
  const q = Number(quantity) >= 1 ? Number(quantity) : 1
  if (!form.delivery_id) {
    ElMessage.warning('请先选择已签约的配送单位')
    return false
  }
  const existing = form.items.find((i) => Number(i.product_id) === Number(p.id))
  if (existing) {
    existing.quantity = (Number(existing.quantity) || 0) + q
    existing.unit_price = lineUnitPriceFromProduct(p)
    existing.reference_price = Number(p.reference_price) || 0
    existing.category1_id = p.category1_id
  } else {
    form.items.push({
      product_name: p.name,
      product_id: p.id,
      quantity: q,
      unit: p.unit || '件',
      reference_price: Number(p.reference_price) || 0,
      category1_id: p.category1_id,
      unit_price: lineUnitPriceFromProduct(p),
    })
  }
  if (!silent) ElMessage.success(`已加入购物车：${p.name} × ${q}`)
  return true
}

const addToCart = (p) => {
  upsertCartItem(p, getAddQty(p.id), false)
}

const removeItem = (idx) => {
  form.items.splice(idx, 1)
}

const loadProductsForSelect = async (keyword = '') => {
  productSearchLoading.value = true
  try {
    const res = await searchOrderProductsApi({
      keyword: keyword || undefined,
      page: 1,
      page_size: 50,
      delivery_id: form.delivery_id || undefined,
    })
    productOptions.value = res.items || []
  } finally {
    productSearchLoading.value = false
  }
}

const searchProducts = (keyword) => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    loadProductsForSelect(keyword || '')
  }, 200)
}

const onSelectProductInCart = (item) => {
  const id = Number(item.product_id)
  let selected = productOptions.value.find((p) => Number(p.id) === id)
  if (!selected && item.match_candidates?.length) {
    selected = item.match_candidates.find((c) => Number(c.id) === id)
  }
  if (!selected) return
  item.product_name = selected.name
  item.unit = selected.unit
  item.reference_price = Number(selected.reference_price || 0)
  item.category1_id = selected.category1_id
  item.unit_price = lineUnitPriceFromProduct(selected)
  item.match_status = 'matched'
  item.match_candidates = []
  // 红色待选行在选品后触发一次“已匹配行合并”
  mergeMatchedCartItems()
}

const loadOcrEngine = async () => {
  try {
    ocrEngineInfo.value = await ocrEngineStatusApi()
  } catch {
    ocrEngineInfo.value = null
  }
}

const refreshContractRates = async () => {
  if (!form.delivery_id) {
    contractRates.value = null
    contractCategories.value = []
    return
  }
  const meta = await orderMetaApi({ delivery_id: form.delivery_id })
  contractRates.value = meta.contract_rates || null
  contractCategories.value = meta.contract_categories || []
}

const loadMeta = async () => {
  if (!userStore.userInfo) {
    try {
      await userStore.fetchMe()
    } catch {
      // 登录态异常由路由守卫接管
    }
  }
  const meta = await orderMetaApi()
  deliveryOptions.value = meta.deliveries || []
  if (!deliveryOptions.value.length) {
    form.delivery_id = null
    contractRates.value = null
    contractCategories.value = []
  } else if (form.delivery_id == null || !deliveryOptions.value.some((d) => d.id === form.delivery_id)) {
    form.delivery_id = deliveryOptions.value[0].id
  }
  await refreshContractRates()
  hydrateScheduleAddressFromUser()
  await loadCatalog()
  await loadOcrEngine()
}

const hydrateScheduleAddressFromUser = (force = false) => {
  const me = userStore.userInfo || {}
  const hasAddress = !!String(scheduleForm.delivery_address || '').trim()
  const hasLngLat =
    scheduleForm.delivery_lng !== null &&
    scheduleForm.delivery_lng !== '' &&
    scheduleForm.delivery_lat !== null &&
    scheduleForm.delivery_lat !== ''
  if (!force && hasAddress && hasLngLat) return
  if (String(me.address || '').trim()) {
    scheduleForm.delivery_address = String(me.address).trim()
  }
  if (me.lng !== null && me.lng !== undefined && me.lat !== null && me.lat !== undefined) {
    scheduleForm.delivery_lng = Number(me.lng)
    scheduleForm.delivery_lat = Number(me.lat)
  }
}

const fillRecognizedItems = (recognizedItems = []) => {
  if (!recognizedItems.length) return
  let autoPicked = 0
  form.items = recognizedItems.map((item) => {
    let product_id = item.product_id != null ? Number(item.product_id) : null
    let product_name = item.product_name
    let unit = item.unit || '斤'
    let unit_price = Number(item.unit_price) || 0
    let match_status = item.match_status
    let candidates = item.match_candidates || []

    // 对“歧义但头部候选明显领先”的行自动代选，减少客户手工操作
    if (!product_id && match_status === 'ambiguous' && candidates.length) {
      const c1 = candidates[0]
      const c2 = candidates[1]
      const s1 = Number(c1?.score || 0)
      const s2 = Number(c2?.score || 0)
      if (s1 >= 0.85 && (candidates.length === 1 || s1 - s2 >= 0.12)) {
        product_id = Number(c1.id)
        product_name = c1.name
        unit = c1.unit || unit
        unit_price = Number(c1.reference_price || 0)
        match_status = 'matched'
        candidates = []
        autoPicked += 1
      }
    }

    return {
      product_name,
      product_id,
      quantity: item.quantity,
      unit,
      unit_price,
      reference_price: item.reference_price != null ? Number(item.reference_price) : undefined,
      category1_id: item.category1_id != null ? Number(item.category1_id) : undefined,
      ocr_product_name: item.ocr_product_name,
      match_status,
      match_candidates: candidates,
    }
  })
  if (autoPicked > 0) {
    ElMessage.success(`已自动确认 ${autoPicked} 条高置信候选，剩余疑似项请你快速核对。`)
  }
  // OCR 导入后：先合并所有已匹配行；未匹配行先保留
  mergeMatchedCartItems()
  cartDrawerVisible.value = true
  loadProductsForSelect('')
}

const ensureScheduleValid = () => {
  if (!scheduleForm.delivery_address?.trim()) {
    ElMessage.warning('配送地址为空，请前往「我的资料」补充默认地址后再下单')
    return false
  }
  if (!scheduleForm.delivery_date) {
    ElMessage.warning('请选择配送日期')
    return false
  }
  if (!scheduleForm.delivery_slot_start || !scheduleForm.delivery_slot_end) {
    ElMessage.warning('请选择配送时段（开始与结束）')
    return false
  }
  const todayStr = (() => {
    const t = new Date()
    return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`
  })()
  if (scheduleForm.delivery_date < todayStr) {
    ElMessage.error('配送日期不能早于今天')
    return false
  }
  const startH = parseInt(scheduleForm.delivery_slot_start.slice(0, 2), 10)
  const endH = scheduleForm.delivery_slot_end === '24:00' ? 24 : parseInt(scheduleForm.delivery_slot_end.slice(0, 2), 10)
  if (endH <= startH) {
    ElMessage.error('配送时段结束时刻必须晚于开始时刻')
    return false
  }
  const [yy, mm, dd] = scheduleForm.delivery_date.split('-').map(Number)
  const windowStart = new Date(yy, (mm || 1) - 1, dd || 1, startH, 0, 0, 0)
  if (windowStart.getTime() < Date.now() + 2 * 60 * 60 * 1000) {
    ElMessage.error('配送时段须距当前时间至少 2 小时，请重新选择')
    return false
  }
  const start = contractRates.value?.period_start
  const end = contractRates.value?.period_end
  if (start && end && (scheduleForm.delivery_date < start || scheduleForm.delivery_date > end)) {
    ElMessage.error(`配送日期需在合约有效期内：${start} ~ ${end}`)
    return false
  }
  if ((Number(scheduleForm.service_duration_min) || 0) <= 0 || Number(scheduleForm.service_duration_min) > 240) {
    ElMessage.warning('预计服务耗时需在 1-240 分钟内')
    return false
  }
  return true
}

const openScheduleDialog = () => {
  if (!form.delivery_id) {
    ElMessage.warning('请选择配送单位')
    return
  }
  const invalidItem = form.items.find((i) => !i.product_id || Number(i.quantity) <= 0)
  if (invalidItem) {
    ElMessage.warning('购物车中存在未选择商品或数量无效的行，请在购物车中处理')
    cartDrawerVisible.value = true
    return
  }
  if (!scheduleForm.delivery_date) {
    const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000)
    const localDate = new Date(tomorrow.getTime() - tomorrow.getTimezoneOffset() * 60000)
    scheduleForm.delivery_date = localDate.toISOString().slice(0, 10)
  }
  if (!scheduleForm.delivery_slot_start || !scheduleForm.delivery_slot_end) {
    // 默认给到 now + 2h 整点起，再 +1h 作为结束（与 2h 缓冲保持一致）
    const cutoff = new Date(Date.now() + 2 * 60 * 60 * 1000)
    const h = cutoff.getMinutes() === 0 && cutoff.getSeconds() === 0 ? cutoff.getHours() : cutoff.getHours() + 1
    const safeStart = Math.min(h, 23)
    scheduleForm.delivery_slot_start = `${String(safeStart).padStart(2, '0')}:00`
    scheduleForm.delivery_slot_end = safeStart >= 23 ? '24:00' : `${String(safeStart + 1).padStart(2, '0')}:00`
  }
  hydrateScheduleAddressFromUser()
  scheduleDialogVisible.value = true
}

const submit = async (force = false) => {
  if (!ensureScheduleValid()) return
  submitting.value = true
  try {
    const res = await createOrderApi({ ...normalizeForSubmit(), force })
    if (res.need_confirm) {
      const abnormalLines = (res.abnormal_items || []).map((i) => {
        const reason = i.reason ? `（${i.reason}）` : ''
        return `${i.product_name}${reason}`
      })
      await ElMessageBox.confirm(
        `以下商品当前不在「有效合约覆盖范围」内（这是合约覆盖校验，不是浮动率校验），是否继续下单？\n${abnormalLines.join('，')}`,
        '异常提示',
        {
          type: 'warning',
          customClass: 'order-abnormal-confirm-dialog',
          confirmButtonClass: 'order-abnormal-confirm-btn',
          cancelButtonClass: 'order-abnormal-cancel-btn',
          confirmButtonText: '继续下单',
          cancelButtonText: '返回检查',
        },
      )
      await submit(true)
    } else {
      ElMessage.success('订单提交成功')
      form.items = []
      scheduleDialogVisible.value = false
    }
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '提交失败'
    ElMessage.error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  } finally {
    submitting.value = false
  }
}

const runProgressAnimation = () =>
  new Promise((resolve) => {
    ocrProgress.value = 0
    const timer = setInterval(() => {
      ocrProgress.value += 10
      if (ocrProgress.value >= 100) {
        clearInterval(timer)
        resolve()
      }
    }, 150)
  })

const onUploadOrderSheet = async (rawFile) => {
  if (!rawFile) return
  const fd = new FormData()
  fd.append('file', rawFile)
  ocrLoading.value = true
  try {
    const [res] = await Promise.all([parseOrderByOcrApi(fd), runProgressAnimation()])
    ocrPreviewData.value = {
      structured: res.structured,
      warnings: res.warnings || [],
      match_summary: res.match_summary,
      match_details: res.match_details || { unmatched: [], ambiguous: [] },
      using_mock_data: res.using_mock_data,
    }
    ocrPreviewVisible.value = true
    const lines = res.recognized_items || []
    if (lines.length) {
      fillRecognizedItems(lines)
    } else {
      ElMessage.warning('未解析到有效采购行，请对照弹窗中的表格手动选购')
    }
    const conf = res.confidence != null ? (res.confidence * 100).toFixed(0) : '—'
    if (lines.length) {
      ElMessage.success(`识别完成，置信度 ${conf}%（详情见弹窗）`)
    } else {
      ElMessage.info(`已获取识别内容，置信度 ${conf}%（请见弹窗）`)
    }
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || 'OCR 识别失败'
    const text = typeof msg === 'string' ? msg : JSON.stringify(msg)
    ElMessage.error(text)
  } finally {
    ocrLoading.value = false
  }
}

const parseVoice = async () => {
  const res = await parseOrderByVoiceApi({ text: voiceText.value })
  fillRecognizedItems(res.recognized_items)
  if (res.success) {
    ElMessage.success('语音解析成功，已自动填充')
  } else {
    ElMessage.warning('未解析到有效商品，请调整文本')
  }
}

const openCart = () => {
  cartDrawerVisible.value = true
}

const formatMoney = (n) => Number(n || 0).toFixed(2)

onMounted(loadMeta)
onUnmounted(() => {
  catalogLoadMoreObserver?.disconnect()
})

const matchStatusLabel = (s) => {
  if (s === 'matched') return { type: 'success', text: '已匹配' }
  if (s === 'ambiguous') return { type: 'warning', text: '待选择' }
  if (s === 'unmatched_suggested') return { type: 'warning', text: '未匹配(有推荐)' }
  if (s === 'unmatched') return { type: 'danger', text: '无匹配' }
  return null
}

const candidateLabel = (opt) => {
  const score = opt?.score != null ? `（推荐 ${(Number(opt.score) * 100).toFixed(0)}%）` : ''
  return `${opt.name}（${opt.unit}）${score}`
}
</script>

<template>
  <!-- ── Mobile ── -->
  <div v-if="isMobile" class="m-order-page">
    <!-- Delivery partner -->
    <div class="m-section">
      <div class="m-section__label">配送单位</div>
      <el-select
        v-model="form.delivery_id"
        placeholder="请选择已签约配送单位"
        style="width:100%"
        :disabled="!deliveryOptions.length"
        @change="onDeliveryChange"
      >
        <el-option v-for="item in deliveryOptions" :key="item.id" :label="item.name" :value="item.id" />
      </el-select>
      <el-alert
        v-if="!deliveryOptions.length"
        type="warning"
        show-icon
        :closable="false"
        style="margin-top:8px"
        title="暂无可选配送单位"
        description="请先完成招标定标。"
      />
    </div>

    <!-- OCR / Voice -->
    <div class="m-section m-ocr-row">
      <el-upload :show-file-list="false" :auto-upload="false" :on-change="(f) => onUploadOrderSheet(f.raw)" style="flex:1">
        <el-button type="primary" plain :loading="ocrLoading" style="width:100%">上传采购单</el-button>
      </el-upload>
      <el-button style="flex:1" @click="showVoiceInput = !showVoiceInput">语音下单</el-button>
    </div>
    <div v-if="ocrLoading" class="m-section">
      <el-progress :percentage="ocrProgress" />
    </div>
    <div v-if="showVoiceInput" class="m-section">
      <el-input v-model="voiceText" placeholder="我要订100斤大白菜和50斤西红柿" />
      <el-button class="mt-2" type="primary" style="width:100%" @click="parseVoice">解析语音</el-button>
    </div>

    <!-- Search bar -->
    <div class="m-section m-search-section">
      <el-input
        v-model="catalogKeyword"
        clearable
        placeholder="搜索商品..."
        @clear="debouncedCatalogSearch"
        @input="debouncedCatalogSearch"
      />
    </div>

    <!-- Product catalog -->
    <div class="m-catalog-shell">
      <nav class="m-category-rail">
        <button
          type="button"
          class="m-category-item"
          :class="{ 'is-active': catalogCategoryId === null }"
          @click="selectCatalogCategory(null)"
        >
          <span class="m-cat-thumb m-cat-thumb--all">
            <span class="material-symbols-outlined">apps</span>
          </span>
          <span class="m-cat-name">全部</span>
        </button>
        <button
          v-for="cat in contractCategories"
          :key="cat.id"
          type="button"
          class="m-category-item"
          :class="{ 'is-active': catalogCategoryId === cat.id }"
          @click="selectCatalogCategory(cat.id)"
        >
          <span
            class="m-cat-thumb"
            :style="catImage(cat).type === 'emoji' ? { background: catImage(cat).bg } : null"
          >
            <img v-if="catImage(cat).type === 'photo'" :src="catImage(cat).src" :alt="cat.name" loading="lazy" />
            <span v-else class="m-cat-glyph">{{ catImage(cat).glyph }}</span>
          </span>
          <span class="m-cat-name">{{ cat.name }}</span>
        </button>
      </nav>

      <div ref="catalogGridRef" class="m-product-grid-wrap">
        <div v-if="subCategories.length" class="m-subcat-bar">
          <button
            type="button"
            class="m-subcat-chip"
            :class="{ 'is-active': catalogCategory2Id === null }"
            @click="selectCatalogCategory2(null)"
          >全部</button>
          <button
            v-for="sub in subCategories"
            :key="sub.id"
            type="button"
            class="m-subcat-chip"
            :class="{ 'is-active': catalogCategory2Id === sub.id }"
            @click="selectCatalogCategory2(sub.id)"
          >{{ sub.name }}</button>
        </div>
        <div v-if="catalogLoading && !catalogProducts.length" class="m-empty">加载商品...</div>
        <div v-else-if="!catalogLoading && !catalogProducts.length" class="m-empty">暂无商品</div>
        <div v-else class="m-product-grid">
          <div
            v-for="p in catalogProducts"
            :key="p.id"
            class="m-product-card"
            data-testid="order-product-card"
          >
            <div class="m-product-thumb-wrap">
              <img
                v-if="p.thumb_url || p.logo"
                :src="p.thumb_url || p.logo"
                :alt="p.name"
                class="m-product-thumb"
                loading="lazy"
              />
              <div v-else class="m-product-thumb-placeholder">暂无图片</div>
            </div>
            <div class="m-product-card__body">
              <div class="m-product-card__name" :title="p.name">{{ p.name }}</div>
              <div class="m-product-card__meta">
                <span v-if="p.spec" class="m-product-spec">{{ p.spec }}</span>
                <span class="m-product-unit">{{ p.unit || '件' }}</span>
              </div>
              <div class="m-product-price-line">
                <div class="m-product-price-group">
                  <span class="m-product-price">¥{{ formatMoney(lineUnitPriceFromProduct(p)) }}</span>
                  <span class="m-product-price-unit">/{{ p.unit || '件' }}</span>
                </div>
                <span
                  v-if="productStandardTypeLabel(p.standard_type)"
                  class="m-product-standard-tag"
                  :class="productStandardTypeCardClass(p.standard_type)"
                >{{ productStandardTypeLabel(p.standard_type) }}</span>
              </div>
              <div class="m-product-card__actions">
                <el-input-number
                  :model-value="getAddQty(p.id)"
                  :min="1"
                  size="small"
                  controls-position="right"
                  class="m-product-qty"
                  @change="(v) => setAddQty(p.id, v)"
                />
                <el-button type="primary" size="small" class="m-product-add-btn" @click="addToCart(p)">
                  <el-icon><Plus /></el-icon>
                </el-button>
              </div>
            </div>
          </div>
        </div>
        <div v-if="catalogLoadingMore" class="m-catalog-loading-more">加载中...</div>
        <div v-else-if="catalogHasMore" ref="catalogLoadMoreRef" class="m-catalog-load-more-sentinel" />
        <div v-else-if="catalogProducts.length" class="m-catalog-end">没有更多了</div>
      </div>
    </div>

    <!-- Floating cart bar -->
    <div v-if="cartLineCount > 0" class="m-cart-bar" @click="cartDrawerVisible = true">
      <div class="m-cart-bar__left">
        <span class="material-symbols-outlined">shopping_cart</span>
        <span class="m-cart-bar__badge">{{ cartLineCount }}</span>
        <span class="m-cart-bar__text">{{ matchedLineCount }} 种 · 预计 ¥{{ formatMoney(estimatedTotal) }}</span>
      </div>
      <button class="m-cart-bar__btn" @click.stop="openScheduleDialog">去下单</button>
    </div>
  </div>

  <!-- ── PC ── -->
  <div v-else class="order-new-page">
    <el-card class="toolbar-card">
      <el-alert
        v-if="ocrEngineInfo?.using_mock_data"
        type="info"
        show-icon
        :closable="false"
        class="ocr-engine-alert"
        title="当前 OCR 为演示模式（未配置百度表格识别密钥），结果为示例表格。可在后端环境变量设置 BAIDU_TABLE_API_KEY / DOCUMENTS_BAIDU_TABLE_API_KEY 并设 OCR_ENGINE=baidu。"
      />
      <el-alert
        v-if="!deliveryOptions.length"
        type="warning"
        show-icon
        :closable="false"
        class="mb-3"
        title="暂无可选配送单位"
        description="仅显示已在「我的合约」中签订（已中标）的配送单位；请先完成招标定标后再下单。"
      />
      <el-form :label-width="formLabelWidth" class="toolbar-form">
        <el-form-item label="配送单位">
          <el-select
            v-model="form.delivery_id"
            placeholder="请选择已签约的配送单位"
            style="min-width: 220px"
            :disabled="!deliveryOptions.length"
            @change="onDeliveryChange"
          >
            <el-option v-for="item in deliveryOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="快捷入口">
          <el-upload :show-file-list="false" :auto-upload="false" :on-change="(f) => onUploadOrderSheet(f.raw)">
            <el-button type="primary" plain :loading="ocrLoading">上传采购单</el-button>
          </el-upload>
          <el-button class="ml-2" @click="showVoiceInput = !showVoiceInput">语音下单</el-button>
        </el-form-item>
        <el-form-item v-if="ocrLoading" label="OCR进度">
          <el-progress :percentage="ocrProgress" style="max-width: 320px" />
        </el-form-item>
        <el-form-item v-if="showVoiceInput" label="语音文本">
          <el-input v-model="voiceText" placeholder="我要订100斤大白菜和50斤西红柿" style="max-width: 360px" />
          <el-button class="ml-2" @click="parseVoice">解析</el-button>
        </el-form-item>
      </el-form>

      <div class="cart-summary-bar">
        <div class="cart-summary-text">
          已匹配 <span class="summary-strong">{{ matchedLineCount }}</span> 种，共
          <span class="summary-strong">{{ matchedPieceCount }}</span> 件
          <span v-if="pendingLineCount > 0" class="summary-pending"
            >· 待处理 <span class="summary-strong">{{ pendingLineCount }}</span> 种</span
          >
          · 预计 <span class="summary-price">¥{{ formatMoney(estimatedTotal) }}</span>
        </div>
        <el-button type="primary" @click="openCart">
          打开购物车
          <el-badge v-if="cartLineCount > 0" :value="cartLineCount" class="cart-badge-inline" />
        </el-button>
      </div>
    </el-card>

    <el-card class="catalog-card">
      <template #header>
        <div class="catalog-header">
          <span class="catalog-title">选购商品</span>
          <el-input
            v-model="catalogKeyword"
            clearable
            placeholder="搜索商品名称"
            class="catalog-search"
            @clear="debouncedCatalogSearch"
            @input="debouncedCatalogSearch"
          />
        </div>
      </template>

      <div class="catalog-body">
        <div v-if="catalogLoading" class="catalog-loading">正在加载商品…</div>
        <template v-if="!catalogLoading">
          <div v-if="!catalogProducts.length" class="catalog-empty">暂无商品，请调整搜索条件</div>
          <div v-else class="product-grid">
          <div v-for="p in catalogProducts" :key="p.id" class="product-card" data-testid="order-product-card">
            <div class="product-thumb-wrap">
              <img
                v-if="p.thumb_url || p.logo"
                :src="p.thumb_url || p.logo"
                :alt="p.name"
                class="product-thumb"
                loading="lazy"
              />
              <div v-else class="product-thumb-placeholder">暂无图片</div>
            </div>
            <div class="product-body">
              <div class="product-name" :title="p.name">{{ p.name }}</div>
              <div v-if="p.spec" class="product-spec">{{ p.spec }}</div>
              <div class="product-meta">
                <div class="product-price-line">
                  <span class="product-price">¥{{ formatMoney(lineUnitPriceFromProduct(p)) }}</span>
                  <span class="product-unit">/{{ p.unit }}</span>
                </div>
                <span
                  v-if="productStandardTypeLabel(p.standard_type)"
                  class="product-standard-tag"
                  :class="productStandardTypeCardClass(p.standard_type)"
                >{{ productStandardTypeLabel(p.standard_type) }}</span>
              </div>
              <div v-if="!form.delivery_id" class="product-price-hint">主价：选择配送单位后显示按合约上浮的单价</div>
              <div v-else class="product-price-hint">主价：按合约一级分类上浮后的单价</div>
              <div class="product-guide-block">
                <div class="product-guide-row">
                  <span class="pg-label">指导价</span>
                  <span class="pg-value"
                    >¥{{ formatMoney(guidePriceDisplay(p)) }}<span class="pg-per">/{{ p.unit }}</span></span
                  >
                </div>
                <div class="product-guide-row">
                  <span class="pg-label">指导上限价</span>
                  <span class="pg-value pg-ceiling"
                    >¥{{ formatMoney(guideCeilingDisplay(p)) }}<span class="pg-per">/{{ p.unit }}</span></span
                  >
                </div>
                <div
                  v-if="p.category_max_float_rate != null && p.category_max_float_rate !== undefined"
                  class="product-guide-foot"
                  title="运营端「分类管理」中该一级分类的「最高上浮率上限」。指导上限价=指导价×(1+该上限)。合约实际采用上浮率由招标结果决定，可低于此上限。"
                >
                  上限按一级分类运营上限 {{ (Number(p.category_max_float_rate) * 100).toFixed(2) }}% 折算
                </div>
              </div>
              <div class="product-actions">
                <el-input-number
                  :model-value="getAddQty(p.id)"
                  :min="1"
                  :max="99999"
                  size="small"
                  class="add-qty"
                  @update:model-value="(v) => setAddQty(p.id, v)"
                />
                <el-button type="primary" size="small" @click="addToCart(p)">加入购物车</el-button>
              </div>
            </div>
          </div>
        </div>
        </template>
      </div>

      <div v-if="catalogTotal > 0" class="catalog-pager">
        <el-pagination
          v-model:current-page="catalogPage"
          layout="total, prev, pager, next"
          :total="catalogTotal"
          :page-size="catalogPageSize"
          background
        />
      </div>
    </el-card>

    <!-- 悬浮购物车入口 -->
    <div class="fab-cart" @click="openCart">
      <el-badge :value="cartLineCount" :hidden="cartLineCount === 0" class="fab-badge">
        <el-button type="primary" circle size="large" class="fab-btn" aria-label="打开购物车"> 购 </el-button>
      </el-badge>
      <div v-if="cartLineCount" class="fab-hint">¥{{ formatMoney(estimatedTotal) }}</div>
    </div>
  </div>

  <!-- Shared drawers/dialogs (used by both mobile and PC) -->
  <el-drawer
    v-model="cartDrawerVisible"
    title="购物车"
    :size="isMobile ? '100%' : cartDrawerSize"
    :direction="isMobile ? 'btt' : 'rtl'"
    class="cart-drawer">
      <div class="drawer-inner">
        <div v-if="!form.items.length" class="drawer-empty">购物车还是空的，先去上面选购商品吧</div>
        <div v-else class="cart-lines">
          <div v-for="(item, idx) in form.items" :key="idx" class="cart-line" data-testid="order-cart-line">
            <div class="cart-line-main">
              <div v-if="item.product_id" class="cart-line-title-row">
                <el-tag
                  v-if="matchStatusLabel(item.match_status)"
                  :type="matchStatusLabel(item.match_status).type"
                  size="small"
                  class="cart-status-tag"
                >
                  {{ matchStatusLabel(item.match_status).text }}
                </el-tag>
                <span class="cart-line-title-text">{{ item.product_name || '商品' }}</span>
              </div>
              <div
                v-else-if="item.match_status === 'ambiguous' && (item.match_candidates || []).length"
                class="cart-line-unmapped"
              >
                <div class="cart-line-title-row">
                  <el-tag type="warning" size="small" class="cart-status-tag">待选择</el-tag>
                  <span class="cart-line-title need-map">{{ item.ocr_product_name || item.product_name }}</span>
                </div>
                <el-select
                  v-model="item.product_id"
                  filterable
                  placeholder="请选择对应商品"
                  class="cart-select"
                  @change="onSelectProductInCart(item)"
                >
                  <el-option
                    v-for="opt in item.match_candidates"
                    :key="opt.id"
                    :label="candidateLabel(opt)"
                    :value="opt.id"
                  />
                </el-select>
              </div>
              <div v-else class="cart-line-unmapped">
                <div
                  v-if="item.match_status === 'unmatched' || item.match_status === 'unmatched_suggested'"
                  class="cart-line-title-row"
                >
                  <el-tag type="danger" size="small" class="cart-status-tag">无匹配</el-tag>
                  <el-tag v-if="item.match_status === 'unmatched_suggested'" type="warning" size="small" class="cart-status-tag"
                    >有推荐</el-tag
                  >
                  <span class="cart-line-title need-map">{{
                    item.ocr_product_name || item.product_name || '未识别商品'
                  }}</span>
                </div>
                <div v-else class="cart-line-title need-map">{{ item.product_name || '未识别商品' }}</div>
                <el-select
                  v-model="item.product_id"
                  filterable
                  :remote="!(item.match_candidates || []).length"
                  clearable
                  reserve-keyword
                  placeholder="请搜索并选择商品"
                  class="cart-select"
                  :remote-method="(item.match_candidates || []).length ? undefined : searchProducts"
                  :loading="productSearchLoading"
                  @change="onSelectProductInCart(item)"
                >
                  <el-option
                    v-for="opt in item.match_candidates || []"
                    :key="`cand-${opt.id}`"
                    :label="`推荐：${candidateLabel(opt)}`"
                    :value="opt.id"
                  />
                  <el-option
                    v-for="opt in productOptions"
                    :key="opt.id"
                    :label="`${opt.name}（${opt.unit}）`"
                    :value="opt.id"
                  />
                </el-select>
              </div>
              <div class="cart-line-row">
                <el-input-number v-model="item.quantity" :min="1" :max="99999" size="small" />
                <span class="cart-unit">{{ item.unit || '—' }}</span>
                <span class="cart-unit-price">¥{{ formatMoney(item.unit_price) }}</span>
                <span class="cart-line-sum"
                  >小计 ¥{{ formatMoney((Number(item.quantity) || 0) * (Number(item.unit_price) || 0)) }}</span
                >
                <el-button type="danger" link size="small" @click="removeItem(idx)">删除</el-button>
              </div>
            </div>
          </div>
        </div>

        <div class="drawer-footer">
          <div class="drawer-total">预计总额：<span class="drawer-total-num">¥{{ formatMoney(estimatedTotal) }}</span></div>
          <el-button
            type="primary"
            size="large"
            class="submit-order-btn"
            data-testid="order-submit-cart"
            :loading="submitting"
            :disabled="!form.items.length"
            @click="openScheduleDialog"
          >
            提交订单
          </el-button>
        </div>
      </div>
    </el-drawer>

    <el-dialog
      v-model="scheduleDialogVisible"
      title="选择配送时间"
      width="min(92vw, 560px)"
      class="delivery-schedule-dialog"
      :fullscreen="isMobile"
      destroy-on-close
    >
      <div class="schedule-tip">
        请选择配送日期与时段：须为<strong>整点起止区间</strong>（如 06:00-07:00 或 14:00-18:00），且开始时刻须距当前时间至少 2 小时。系统将校验是否在合约有效期内。
      </div>
      <div class="schedule-contract-range">
        合约有效期：{{ contractRates?.period_start || '—' }} ~ {{ contractRates?.period_end || '—' }}
      </div>
      <el-form :label-width="formLabelWidth" class="schedule-form">
        <el-form-item label="配送日期" required>
          <el-date-picker
            v-model="scheduleForm.delivery_date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="请选择配送日期"
            :disabled-date="disabledOrderDate"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="配送地址" required>
          <el-input
            v-model="scheduleForm.delivery_address"
            disabled
            placeholder="请前往「我的资料」修改默认配送地址"
          />
        </el-form-item>
        <el-form-item label="配送时段" required>
          <div class="slot-range">
            <el-select v-model="scheduleForm.delivery_slot_start" placeholder="开始" style="flex: 1">
              <el-option
                v-for="h in hourOptions"
                :key="`start-${h}`"
                :value="h"
                :label="h"
                :disabled="isStartHourDisabled(h)"
              />
            </el-select>
            <span class="slot-sep">—</span>
            <el-select v-model="scheduleForm.delivery_slot_end" placeholder="结束" style="flex: 1">
              <el-option
                v-for="h in endHourOptions"
                :key="`end-${h}`"
                :value="h"
                :label="h"
                :disabled="isEndHourDisabled(h)"
              />
            </el-select>
          </div>
        </el-form-item>
        <el-form-item label="预计耗时(分)" required>
          <el-input-number v-model="scheduleForm.service_duration_min" :min="1" :max="240" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="scheduleDialogVisible = false">取消</el-button>
        <el-button type="primary" data-testid="order-confirm-submit" :loading="submitting" @click="submit(false)">确认并提交</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="ocrPreviewVisible"
      title="采购单识别结果"
      width="min(92vw, 920px)"
      class="ocr-preview-dialog"
      :fullscreen="isMobile"
      destroy-on-close
    >
      <div v-if="ocrPreviewData?.warnings?.length" class="ocr-warnings-block">
        <el-alert
          v-for="(w, wi) in ocrPreviewData.warnings"
          :key="wi"
          type="warning"
          :closable="false"
          show-icon
          class="ocr-warn-item"
          :title="w"
        />
      </div>
      <div v-if="ocrPreviewData?.match_summary" class="ocr-match-summary">
        匹配：
        <strong>{{ ocrPreviewData.match_summary.matched }}</strong>
        条已对应 · 待选择
        <strong>{{ ocrPreviewData.match_summary.ambiguous }}</strong>
        · 未匹配
        <strong>{{ ocrPreviewData.match_summary.unmatched }}</strong>
      </div>
      <div
        v-if="ocrPreviewData?.match_details?.ambiguous?.length"
        class="ocr-detail-block ocr-detail-ambiguous"
      >
        <div class="ocr-detail-title">对应多个商品（请在购物车点选）</div>
        <div class="ocr-detail-list">
          <div v-for="(row, ai) in ocrPreviewData.match_details.ambiguous" :key="`a-${ai}`" class="ocr-detail-row">
            <span class="ocr-detail-name">{{ row.ocr_product_name }}</span>
            <span class="ocr-detail-arrow">→</span>
            <span class="ocr-detail-cands">{{
              (row.candidates || []).map((c) => c.name).join('、') || '无候选'
            }}</span>
          </div>
        </div>
      </div>
      <div
        v-if="ocrPreviewData?.match_details?.unmatched?.length"
        class="ocr-detail-block ocr-detail-unmatched"
      >
        <div class="ocr-detail-title">未自动匹配（红色优先处理）</div>
        <div class="ocr-detail-list">
          <div v-for="(row, ui) in ocrPreviewData.match_details.unmatched" :key="`u-${ui}`" class="ocr-detail-row">
            <span class="ocr-detail-name">{{ row.ocr_product_name }}</span>
            <span class="ocr-detail-arrow">→</span>
            <span class="ocr-detail-cands" :class="{ 'has-suggest': (row.candidates || []).length }">{{
              (row.candidates || []).length
                ? `推荐：${row.candidates.map((c) => c.name).join('、')}`
                : '未找到推荐，请手动搜索'
            }}</span>
          </div>
        </div>
      </div>
      <div
        v-if="ocrPreviewData?.structured?.key_values?.length"
        class="ocr-key-values"
      >
        <div v-for="(kv, ki) in ocrPreviewData.structured.key_values" :key="ki" class="ocr-kv-line">
          <span class="ocr-kv-k">{{ kv.key }}</span>
          <span class="ocr-kv-v">{{ kv.value }}</span>
        </div>
      </div>
      <div v-if="ocrPreviewTable" class="ocr-table-wrap">
        <el-table :data="ocrPreviewTable.rows" border stripe max-height="380" style="width: 100%">
          <el-table-column
            v-for="(h, colIdx) in ocrPreviewTable.headers"
            :key="colIdx"
            :label="h || `列${colIdx + 1}`"
            min-width="100"
            show-overflow-tooltip
          >
            <template #default="{ row }">{{ row[colIdx] ?? '' }}</template>
          </el-table-column>
        </el-table>
      </div>
      <div v-else class="ocr-table-empty">暂无表格数据</div>
      <template #footer>
        <el-button type="primary" @click="ocrPreviewVisible = false">已了解，去购物车核对</el-button>
      </template>
    </el-dialog>
</template>

<style scoped>
.order-new-page {
  position: relative;
  padding-bottom: 80px;
}

.ocr-engine-alert {
  margin-bottom: 12px;
}

.ocr-warnings-block {
  margin-bottom: 12px;
}

.ocr-warn-item {
  margin-bottom: 8px;
}

.ocr-match-summary {
  font-size: 14px;
  color: #475569;
  margin-bottom: 12px;
}

.ocr-detail-block {
  margin-bottom: 12px;
  border-radius: 8px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
}

.ocr-detail-ambiguous {
  background: #fffbeb;
  border-color: #fcd34d;
}

.ocr-detail-unmatched {
  background: #fff7ed;
  border-color: #fdba74;
}

.ocr-detail-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
  color: #334155;
}

.ocr-detail-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ocr-detail-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  line-height: 1.4;
}

.ocr-detail-name {
  color: #0f172a;
  font-weight: 600;
}

.ocr-detail-arrow {
  color: #94a3b8;
}

.ocr-detail-cands {
  color: #64748b;
}

.ocr-detail-cands.has-suggest {
  color: #0369a1;
}

.ocr-key-values {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 20px;
  margin-bottom: 12px;
  padding: 10px 12px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.ocr-kv-line {
  font-size: 13px;
}

.ocr-kv-k {
  font-weight: 600;
  color: #334155;
  margin-right: 6px;
}

.ocr-kv-v {
  color: #0f172a;
}

.ocr-table-wrap {
  overflow-x: auto;
}

.ocr-table-empty {
  color: #94a3b8;
  font-size: 14px;
  padding: 12px 0;
}

.schedule-tip {
  font-size: 13px;
  color: #475569;
  margin-bottom: 8px;
}

.schedule-contract-range {
  margin-bottom: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #334155;
  font-size: 12px;
}

.slot-range {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.slot-sep {
  color: #94a3b8;
}

.cart-line-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.cart-line-title-text {
  font-weight: 600;
  color: #0f172a;
}

.cart-status-tag {
  flex-shrink: 0;
}

.toolbar-card {
  margin-bottom: 16px;
}

.toolbar-form {
  margin-bottom: 0;
}

.cart-summary-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px 16px;
  margin-top: 8px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.cart-summary-text {
  font-size: 14px;
  color: #64748b;
}

.summary-strong {
  font-weight: 600;
  color: #0f172a;
}

.summary-price {
  font-weight: 600;
  color: #0ea5e9;
  font-size: 16px;
}

.summary-pending {
  color: #b45309;
}

.cart-badge-inline {
  margin-left: 8px;
  vertical-align: middle;
}

.catalog-card :deep(.el-card__header) {
  padding: 12px 20px;
}

.catalog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.catalog-title {
  font-weight: 600;
  font-size: 16px;
  color: #0f172a;
}

.catalog-search {
  max-width: 320px;
  min-width: 200px;
}

.product-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.product-card {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
  display: flex;
  flex-direction: column;
  transition: box-shadow 0.2s;
}

.product-card:hover {
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.08);
}

.product-thumb-wrap {
  aspect-ratio: 1;
  background: #f8fafc;
  display: flex;
  align-items: center;
  justify-content: center;
}

.product-standard-tag {
  flex-shrink: 0;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 600;
  line-height: 18px;
  border-radius: 4px;
}

.product-standard-tag.standard {
  color: #15803d;
  background: #dcfce7;
}

.product-standard-tag.non-standard {
  color: #b45309;
  background: #fef3c7;
}

.product-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.product-thumb-placeholder {
  font-size: 12px;
  color: #94a3b8;
}

.product-body {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
}

.product-name {
  font-size: 14px;
  font-weight: 500;
  color: #0f172a;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 2.7em;
}

.product-spec {
  font-size: 12px;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.product-meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
}

.product-price-line {
  min-width: 0;
}

.product-price {
  font-size: 18px;
  font-weight: 600;
  color: #dc2626;
}

.product-unit {
  font-size: 12px;
  color: #64748b;
}

.product-price-hint {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 2px;
  line-height: 1.4;
}

.product-guide-block {
  padding: 8px 0 4px;
  margin-top: 2px;
  border-top: 1px dashed #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.product-guide-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  line-height: 1.35;
}

.pg-label {
  color: #64748b;
  flex-shrink: 0;
}

.pg-value {
  font-weight: 600;
  color: #334155;
  text-align: right;
}

.pg-value.pg-ceiling {
  color: #0c4a6e;
}

.pg-per {
  font-size: 11px;
  font-weight: 500;
  color: #94a3b8;
  margin-left: 2px;
}

.product-guide-foot {
  font-size: 10px;
  color: #94a3b8;
  line-height: 1.35;
  margin-top: 2px;
}

.product-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.add-qty {
  width: 110px;
}

.catalog-body {
  min-height: 220px;
  position: relative;
}

.catalog-loading {
  text-align: center;
  padding: 48px 16px;
  color: #94a3b8;
  font-size: 14px;
}

.catalog-empty {
  text-align: center;
  padding: 48px 16px;
  color: #94a3b8;
}

.catalog-pager {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

.fab-btn {
  font-size: 15px;
  font-weight: 600;
  min-width: 48px;
}

.submit-order-btn {
  width: 100%;
}

.fab-cart {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.fab-hint {
  font-size: 12px;
  color: #0f172a;
  background: #fff;
  padding: 4px 8px;
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.12);
}

.drawer-inner {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 120px);
  padding-bottom: 8px;
}

.drawer-empty {
  color: #94a3b8;
  text-align: center;
  padding: 40px 16px;
}

.cart-lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cart-line {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  background: #fafafa;
}

.cart-line-title {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 8px;
  color: #0f172a;
}

.cart-line-unmapped {
  margin-bottom: 8px;
}

.need-map {
  color: #d97706;
}

.cart-select {
  width: 100%;
  margin-top: 8px;
}

.cart-line-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  font-size: 13px;
}

.cart-unit {
  color: #64748b;
}

.cart-unit-price {
  color: #0f172a;
}

.cart-line-sum {
  margin-left: auto;
  font-weight: 500;
  color: #0f172a;
}

.drawer-footer {
  margin-top: auto;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}

.drawer-total {
  font-size: 15px;
  margin-bottom: 12px;
  color: #64748b;
}

.drawer-total-num {
  font-size: 20px;
  font-weight: 600;
  color: #dc2626;
}

/* ── Mobile styles ── */
.m-order-page {
  font-family: var(--m-font-body);
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 100%;
  overflow: hidden;
}
.m-section {
  flex: none;
  padding: 12px 16px;
  border-bottom: 1px solid var(--m-outline-variant);
  background: var(--m-surface-container-lowest);
}
.m-section__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--m-on-surface-variant);
  margin-bottom: 8px;
}
.m-ocr-row {
  display: flex;
  gap: 8px;
}
.m-search-section {
  flex: none;
  background: var(--m-surface-container-lowest);
  border-bottom: 1px solid var(--m-outline-variant);
}
.m-catalog-shell {
  flex: 1;
  min-height: 0;
  display: flex;
  background: var(--m-surface-container);
}
.m-category-rail {
  flex: none;
  width: 84px;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  background: var(--m-surface-container-lowest);
  border-right: 1px solid var(--m-outline-variant);
  padding: 6px 0;
}
.m-category-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  width: 100%;
  padding: 10px 6px;
  border: none;
  background: transparent;
  color: var(--m-on-surface-variant);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.25;
  text-align: center;
  cursor: pointer;
  position: relative;
  transition: color 0.18s, background 0.18s;
}
.m-cat-thumb {
  flex: none;
  width: 46px;
  height: 46px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  font-size: 25px;
  overflow: hidden;
  background: var(--m-surface-container);
  transition: transform 0.18s, box-shadow 0.18s;
}
.m-cat-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.m-cat-thumb--all {
  background: var(--m-secondary-fixed);
  color: var(--m-primary);
}
.m-cat-thumb--all .material-symbols-outlined { font-size: 24px; }
.m-cat-name {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.m-category-item.is-active {
  color: var(--m-primary);
  font-weight: 700;
  background: var(--m-surface-container);
}
.m-category-item.is-active .m-cat-thumb {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(31, 122, 83, 0.28);
  outline: 2px solid var(--m-primary);
  outline-offset: 1px;
}
.m-category-item.is-active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--m-primary);
}
.m-product-grid-wrap {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  padding: 8px 8px calc(72px + env(safe-area-inset-bottom, 0px));
}
/* 二级分类筛选 chip 行（吸顶横滑） */
.m-subcat-bar {
  position: sticky;
  top: -8px;
  z-index: 5;
  display: flex;
  gap: 7px;
  margin: -8px -8px 8px;
  padding: 8px;
  background: var(--m-surface);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  border-bottom: 1px solid var(--m-outline-variant);
}
.m-subcat-bar::-webkit-scrollbar { display: none; }
.m-subcat-chip {
  flex: none;
  padding: 5px 14px;
  border-radius: 16px;
  border: 1.5px solid var(--m-outline-variant);
  background: var(--m-surface-container-lowest);
  color: var(--m-on-surface-variant);
  font-size: 12.5px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  transition: all 0.16s;
}
.m-subcat-chip.is-active {
  background: var(--m-secondary-fixed);
  border-color: var(--m-primary);
  color: var(--m-primary);
  font-weight: 700;
}
.m-product-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.m-product-card {
  background: var(--m-surface-container-lowest);
  border: 1px solid var(--m-outline-variant);
  border-radius: 10px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.m-product-thumb-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  background: var(--m-surface-container-high);
}
.m-product-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.m-product-thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--m-on-surface-variant);
  background: var(--m-surface-container);
}
.m-product-standard-tag {
  flex: none;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  line-height: 1.4;
  white-space: nowrap;
}
.m-product-standard-tag.standard {
  color: #15803d;
  background: #dcfce7;
}
.m-product-standard-tag.non-standard {
  color: #b45309;
  background: #fef3c7;
}
.m-product-card__body {
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}
.m-product-card__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--m-on-surface);
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 2.7em;
}
.m-product-card__meta {
  font-size: 11px;
  color: var(--m-on-surface-variant);
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.m-product-spec {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}
.m-product-price-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-top: 2px;
}
.m-product-price-group {
  display: flex;
  align-items: baseline;
  gap: 2px;
  min-width: 0;
}
.m-product-price {
  font-size: 15px;
  font-weight: 700;
  color: var(--m-primary);
}
.m-product-price-unit {
  font-size: 11px;
  color: var(--m-on-surface-variant);
}
.m-product-card__actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: auto;
  padding-top: 4px;
}
.m-product-qty {
  flex: 1;
  min-width: 0;
}
.m-product-qty :deep(.el-input__wrapper) {
  padding-left: 6px;
  padding-right: 6px;
}
.m-product-add-btn {
  flex: none;
  padding: 8px 10px;
}
.m-catalog-loading-more,
.m-catalog-end {
  text-align: center;
  padding: 12px 0 4px;
  font-size: 12px;
  color: var(--m-on-surface-variant);
}
.m-catalog-load-more-sentinel {
  height: 1px;
}
.m-cart-bar {
  position: fixed;
  bottom: calc(64px + env(safe-area-inset-bottom, 0px));
  left: 0;
  right: 0;
  background: var(--m-primary);
  color: var(--m-on-primary);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  z-index: 50;
  cursor: pointer;
}
.m-cart-bar__left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}
.m-cart-bar__badge {
  background: #ef4444;
  color: #fff;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 700;
  flex: none;
}
.m-cart-bar__text {
  font-size: 14px;
  font-weight: 500;
}
.m-cart-bar__btn {
  padding: 8px 20px;
  border-radius: 20px;
  border: 2px solid rgba(255,255,255,0.8);
  background: transparent;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  font-family: var(--m-font-body);
}
.m-empty {
  text-align: center;
  color: var(--m-on-surface-variant);
  padding: 32px 16px;
  font-size: 14px;
}
</style>
