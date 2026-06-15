<script setup>
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Location } from '@element-plus/icons-vue'
import {
  createDeliverySupplierApi,
  deleteDeliverySupplierApi,
  listDeliverySupplierQuoteFilterCategoriesApi,
  listDeliverySupplierQuotesApi,
  listDeliverySuppliersApi,
  searchSupplierAddressTipsApi,
  updateDeliverySupplierApi,
} from '../../api/delivery'
import { formatChinaDateTime } from '../../utils/datetime'
import { isUsableGeoCoord } from '../../utils/geoCoords'

const list = ref([])
const loading = ref(false)
const drawerVisible = ref(false)
const editingId = ref(null)
const amapEnabled = ref(true)
const lastTipItems = ref([])
const quoteDialogVisible = ref(false)
const quoteLoading = ref(false)
const quoteRows = ref([])
const quoteTotal = ref(0)
const quotePage = ref(1)
const quotePageSize = ref(10)
const quoteKeyword = ref('')
const quoteCategory1Id = ref(null)
const quoteFilterCategories = ref([])
const activeSupplier = ref(null)
const locationVisible = ref(false)
const locationRow = ref(null)
const mapRef = ref(null)
const amap = ref(null)
const marker = ref(null)
const form = reactive({
  username: '',
  password: 'demo123',
  company_name: '',
  contact_phone: '',
  address: '',
  lng: null,
  lat: null,
  status: 'active',
})

const supplierMapWrapRef = ref(null)
const supplierMap = ref(null)
const supplierMarker = ref(null)

const resetForm = () => {
  Object.assign(form, {
    username: '',
    password: 'demo123',
    company_name: '',
    contact_phone: '',
    address: '',
    lng: null,
    lat: null,
    status: 'active',
  })
}

const placeOrMoveSupplierMarker = (lng, lat, recenter = false) => {
  if (!supplierMap.value) return
  if (!supplierMarker.value) {
    supplierMarker.value = new window.AMap.Marker({
      position: [lng, lat],
      draggable: true,
      cursor: 'move',
    })
    supplierMarker.value.setMap(supplierMap.value)
    supplierMarker.value.on('dragend', (e) => {
      const p = e.lnglat
      if (!p) return
      form.lng = Number(p.lng)
      form.lat = Number(p.lat)
    })
  } else {
    supplierMarker.value.setPosition([lng, lat])
  }
  if (recenter) supplierMap.value.setZoomAndCenter(15, [lng, lat])
}

const initSupplierMap = async () => {
  if (!supplierMapWrapRef.value) return
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
  if (supplierMap.value) {
    try { supplierMap.value.destroy() } catch {}
    supplierMap.value = null
    supplierMarker.value = null
  }
  const initLng = Number.isFinite(Number(form.lng)) ? Number(form.lng) : 116.407387
  const initLat = Number.isFinite(Number(form.lat)) ? Number(form.lat) : 39.904179
  supplierMap.value = new window.AMap.Map(supplierMapWrapRef.value, {
    zoom: Number.isFinite(Number(form.lng)) ? 15 : 11,
    center: [initLng, initLat],
  })
  if (Number.isFinite(Number(form.lng)) && Number.isFinite(Number(form.lat))) {
    placeOrMoveSupplierMarker(Number(form.lng), Number(form.lat))
  }
  supplierMap.value.on('click', (e) => {
    const p = e.lnglat
    if (!p) return
    form.lng = Number(p.lng)
    form.lat = Number(p.lat)
    placeOrMoveSupplierMarker(Number(p.lng), Number(p.lat))
  })
}

watch(drawerVisible, async (visible) => {
  if (!visible) {
    if (supplierMap.value) {
      try { supplierMap.value.destroy() } catch {}
      supplierMap.value = null
      supplierMarker.value = null
    }
    return
  }
  await nextTick()
  await initSupplierMap()
})

const load = async () => {
  loading.value = true
  try {
    list.value = await listDeliverySuppliersApi()
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
  Object.assign(form, {
    ...row,
    password: 'demo123',
    lng: Number.isFinite(Number(row?.lng)) ? Number(row.lng) : null,
    lat: Number.isFinite(Number(row?.lat)) ? Number(row.lat) : null,
  })
  drawerVisible.value = true
}

const submit = async () => {
  if (!form.company_name?.trim()) {
    ElMessage.warning('请输入企业名称')
    return
  }
  if (!form.address?.trim()) {
    ElMessage.warning('请输入用户地址')
    return
  }
  if (!isUsableGeoCoord(form.lng, form.lat)) {
    ElMessage.warning('请从地址联想选择带坐标的条目，或点击地图扎针定位')
    return
  }
  const payload = {
    ...form,
    lng: Number(form.lng),
    lat: Number(form.lat),
  }
  if (editingId.value) await updateDeliverySupplierApi(editingId.value, payload)
  else await createDeliverySupplierApi(payload)
  drawerVisible.value = false
  await load()
}

const queryAddressTips = async (queryString, cb) => {
  const q = String(queryString || '').trim()
  if (!q) {
    lastTipItems.value = []
    cb([])
    return
  }
  try {
    const res = await searchSupplierAddressTipsApi({ keywords: q, city: '北京' })
    amapEnabled.value = Boolean(res?.amap_enabled)
    const items = Array.isArray(res?.items) ? res.items : []
    lastTipItems.value = items
    cb(items.map((item) => ({ value: item.display || item.name || '' })))
  } catch (err) {
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
    placeOrMoveSupplierMarker(lng, lat, true)
    return
  }
  ElMessage.warning('该联想结果无精确坐标，请换一条或点击地图扎针')
}

const openMapLocation = (row) => {
  const lng = Number(row?.lng)
  const lat = Number(row?.lat)
  if (!isUsableGeoCoord(lng, lat)) {
    ElMessage.warning('该供货商暂无有效坐标，请编辑后重新扎针')
    return
  }
  locationRow.value = row
  locationVisible.value = true
}

const remove = async (id) => {
  await ElMessageBox.confirm('确认删除该供货商账号吗？', '删除确认', {
    type: 'warning',
    confirmButtonText: '确认删除',
    cancelButtonText: '取消',
    customClass: 'danger-confirm-dialog',
    confirmButtonClass: 'danger-confirm-btn',
  })
  await deleteDeliverySupplierApi(id)
  await load()
}

const loadSupplierQuotes = async () => {
  if (!activeSupplier.value?.id) return
  quoteLoading.value = true
  try {
    const params = {
      page: quotePage.value,
      page_size: quotePageSize.value,
    }
    const kw = String(quoteKeyword.value || '').trim()
    if (kw) params.keyword = kw
    if (quoteCategory1Id.value != null && quoteCategory1Id.value !== '') {
      const c1 = Number(quoteCategory1Id.value)
      if (Number.isFinite(c1) && c1 > 0) params.category1_id = c1
    }
    const res = await listDeliverySupplierQuotesApi(activeSupplier.value.id, params)
    quoteRows.value = res.items || []
    quoteTotal.value = Number(res.total || 0)
  } finally {
    quoteLoading.value = false
  }
}

const loadQuoteFilterCategories = async () => {
  try {
    quoteFilterCategories.value = await listDeliverySupplierQuoteFilterCategoriesApi()
  } catch {
    quoteFilterCategories.value = []
  }
}

const applyQuoteFilters = async () => {
  quotePage.value = 1
  await loadSupplierQuotes()
}

const resetQuoteFilters = async () => {
  quoteKeyword.value = ''
  quoteCategory1Id.value = null
  quotePage.value = 1
  await loadSupplierQuotes()
}

const openSupplierQuotes = async (row) => {
  activeSupplier.value = row
  quotePage.value = 1
  quoteKeyword.value = ''
  quoteCategory1Id.value = null
  quoteRows.value = []
  quoteTotal.value = 0
  quoteDialogVisible.value = true
  await loadQuoteFilterCategories()
  await loadSupplierQuotes()
}

const onQuotePageChange = async (page) => {
  quotePage.value = page
  await loadSupplierQuotes()
}

const floatQuoteSummary = (row) => {
  const list = Array.isArray(row?.client_float_quotes) ? row.client_float_quotes : []
  if (!list.length) return '无合约'
  const inPeriodCount = list.filter((v) => v?.in_period).length
  return `期内 ${inPeriodCount} / ${list.length} 家`
}

/** 合约期内优先，其余按客户名排序；用于默认展示一条 + 悬浮看全部 */
const sortClientFloatQuotes = (row) => {
  const list = Array.isArray(row?.client_float_quotes) ? [...row.client_float_quotes] : []
  list.sort((a, b) => {
    if (Boolean(a?.in_period) !== Boolean(b?.in_period)) return a?.in_period ? -1 : 1
    return String(a?.client_name || '').localeCompare(String(b?.client_name || ''), 'zh-CN')
  })
  return list
}

/** 每行只算一次排序结果，供模板绑定 */
const floatQuotePack = (row) => {
  const sorted = sortClientFloatQuotes(row)
  const first = sorted[0] ?? null
  return {
    sorted,
    first,
    extraCount: Math.max(0, sorted.length - 1),
  }
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
  } catch (err) {
    ElMessage.error('高德地图加载失败，请检查 Key/域名白名单配置')
    return
  }
  const title = locationRow.value?.company_name || locationRow.value?.username || '供货商位置'
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

watch(locationVisible, async (visible) => {
  if (!visible) return
  await nextTick()
  await initLocationMap()
})

onBeforeUnmount(() => {
  if (amap.value) {
    amap.value.destroy()
    amap.value = null
    marker.value = null
  }
  if (supplierMap.value) {
    try { supplierMap.value.destroy() } catch {}
    supplierMap.value = null
    supplierMarker.value = null
  }
})

onMounted(load)
</script>

<template>
  <el-card class="mb-3">
    <div class="crud-toolbar">
      <div />
      <div class="crud-actions">
        <el-button type="primary" @click="openCreate">新增供货商</el-button>
      </div>
    </div>
  </el-card>
  <el-card>
    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="id" label="编号" width="70" />
      <el-table-column prop="username" label="用户名" />
      <el-table-column prop="company_name" label="企业" />
      <el-table-column prop="contact_phone" label="联系方式" />
      <el-table-column prop="address" label="用户地址" min-width="220" show-overflow-tooltip />
      <el-table-column label="坐标" min-width="170">
        <template #default="{ row }">
          <el-button
            v-if="row.lng != null && row.lat != null"
            type="primary"
            link
            class="coord-link"
            @click="openMapLocation(row)"
          >
            <el-icon><Location /></el-icon>
            {{ `${Number(row.lng).toFixed(6)}, ${Number(row.lat).toFixed(6)}` }}
          </el-button>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">{{ row.status === 'active' ? '启用' : '停用' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="center">
        <template #default="{ row }">
          <div class="op-btns">
            <el-button size="small" type="primary" plain @click="openSupplierQuotes(row)">查看报价</el-button>
            <el-button size="small" @click="startEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="remove(row.id)">删除</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-drawer v-model="drawerVisible" :title="editingId ? '编辑供货商' : '新增供货商'" size="520px">
    <el-form label-width="100px">
      <el-form-item label="用户名">
        <el-input v-model="form.username" :disabled="!!editingId" />
      </el-form-item>
      <el-form-item v-if="!editingId" label="初始密码">
        <el-input v-model="form.password" disabled />
        <div class="field-tip">新供货商初始密码为 {{ form.password }}。</div>
      </el-form-item>
      <el-form-item label="企业"><el-input v-model="form.company_name" /></el-form-item>
      <el-form-item label="联系方式"><el-input v-model="form.contact_phone" /></el-form-item>
      <el-form-item label="用户地址">
        <el-autocomplete
          v-model="form.address"
          :fetch-suggestions="queryAddressTips"
          class="address-input"
          clearable
          placeholder="请输入并从联想结果选择地址"
          @select="onAddressSelect"
        />
        <div class="field-tip">建议从联想结果中选择，可提高定位成功率。</div>
        <div v-if="!amapEnabled" class="field-tip field-tip-warn">当前未启用高德 Key，地址联想不可用。</div>
      </el-form-item>
      <el-form-item label="精确位置">
        <div ref="supplierMapWrapRef" class="supplier-map" />
        <div class="supplier-coord-row">
          <span>经度：<strong>{{ Number.isFinite(Number(form.lng)) ? Number(form.lng).toFixed(6) : '—' }}</strong></span>
          <span>纬度：<strong>{{ Number.isFinite(Number(form.lat)) ? Number(form.lat).toFixed(6) : '—' }}</strong></span>
          <span class="supplier-coord-tip">点击地图或拖动 marker 可微调点位</span>
        </div>
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="form.status" style="width: 130px">
          <el-option value="active" label="启用" />
          <el-option value="disabled" label="停用" />
        </el-select>
      </el-form-item>
      <el-button type="primary" class="submit-btn" @click="submit">
        {{ editingId ? '保存修改' : '确认新增' }}
      </el-button>
    </el-form>
  </el-drawer>

  <el-dialog
    v-model="quoteDialogVisible"
    width="1120px"
    destroy-on-close
    :title="`供应商报价 - ${activeSupplier?.company_name || activeSupplier?.username || ''}`"
  >
    <div class="quote-filter-bar">
      <el-input
        v-model="quoteKeyword"
        clearable
        placeholder="商品名称 / 编码"
        class="quote-filter-input"
        @keyup.enter="applyQuoteFilters"
      />
      <el-select
        v-model="quoteCategory1Id"
        clearable
        placeholder="一级分类"
        class="quote-filter-select"
        filterable
      >
        <el-option v-for="c in quoteFilterCategories" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
      <el-button type="primary" @click="applyQuoteFilters">查询</el-button>
      <el-button @click="resetQuoteFilters">重置</el-button>
    </div>
    <el-table v-loading="quoteLoading" :data="quoteRows" border>
      <el-table-column prop="goods_sn" label="商品编码" min-width="130" />
      <el-table-column prop="product_name" label="商品名称" min-width="180" />
      <el-table-column prop="category1_name" label="一级分类" width="120" />
      <el-table-column label="参考价" width="110">
        <template #default="{ row }">¥{{ Number(row.reference_price || 0).toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="报价" width="110">
        <template #default="{ row }">¥{{ Number(row.quote_price || 0).toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="同品其他供货商报价" min-width="280">
        <template #default="{ row }">
          <div v-if="Array.isArray(row.peer_supplier_quotes) && row.peer_supplier_quotes.length" class="peer-quote-box">
            <div class="peer-quote-summary">
              最低价 ¥{{ Number(row.peer_quote_min || 0).toFixed(2) }} / 均价 ¥{{ Number(row.peer_quote_avg || 0).toFixed(2) }}
            </div>
            <div class="peer-quote-rank">本供货商排名：{{ row.quote_rank || '-' }}/{{ row.quote_rank_total || '-' }}</div>
            <div class="peer-quote-list">
              <span
                v-for="peer in row.peer_supplier_quotes"
                :key="`${row.product_id}-${peer.supplier_id}`"
                class="peer-quote-item"
              >
                {{ peer.supplier_name }} ¥{{ Number(peer.quote_price || 0).toFixed(2) }}
              </span>
            </div>
          </div>
          <span v-else class="muted-text">暂无其他供货商报价</span>
        </template>
      </el-table-column>
      <el-table-column label="浮动报价摘要" width="130">
        <template #default="{ row }">
          <el-tag size="small" :type="(row.client_float_quotes || []).some((it) => it.in_period) ? 'success' : 'info'">
            {{ floatQuoteSummary(row) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="unit" label="单位" width="80" />
      <el-table-column label="更新时间" min-width="170">
        <template #default="{ row }">{{ formatChinaDateTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="客户端浮动报价（合约）" min-width="280">
        <template #default="{ row }">
          <template v-for="fq in [floatQuotePack(row)]" :key="row.product_id">
            <template v-if="fq.first">
              <div class="float-quote-cell">
                <div class="float-quote-preview">
                  <div class="float-quote-item float-quote-item-compact">
                    <span class="client-name text-ellipsis">{{ fq.first.client_name }}</span>
                    <span class="client-price">¥{{ Number(fq.first.floating_price || 0).toFixed(2) }}</span>
                    <el-tag :type="fq.first.in_period ? 'success' : 'info'" size="small">
                      {{ fq.first.in_period ? '合约期内' : '非合约期' }}
                    </el-tag>
                    <span class="period-text">{{ fq.first.period_start }} ~ {{ fq.first.period_end }}</span>
                  </div>
                  <el-popover
                    v-if="fq.extraCount > 0"
                    placement="top-start"
                    :width="440"
                    trigger="hover"
                    :show-after="180"
                  >
                    <template #reference>
                      <el-button type="primary" link size="small" class="more-float-link">
                        更多（{{ fq.extraCount }}）
                      </el-button>
                    </template>
                    <div class="float-quote-popover">
                      <div
                        v-for="it in fq.sorted"
                        :key="`${row.product_id}-${it.client_id}`"
                        class="float-quote-popover-row"
                      >
                        <span class="client-name">{{ it.client_name }}</span>
                        <span class="client-price">¥{{ Number(it.floating_price || 0).toFixed(2) }}</span>
                        <el-tag :type="it.in_period ? 'success' : 'info'" size="small">
                          {{ it.in_period ? '合约期内' : '非合约期' }}
                        </el-tag>
                        <span class="period-text">{{ it.period_start }} ~ {{ it.period_end }}</span>
                      </div>
                    </div>
                  </el-popover>
                </div>
              </div>
            </template>
            <span v-else class="muted-text">无已中标合约</span>
          </template>
        </template>
      </el-table-column>
    </el-table>
    <div class="quote-pager">
      <el-pagination
        :current-page="quotePage"
        :page-size="quotePageSize"
        layout="total, prev, pager, next"
        :total="quoteTotal"
        @current-change="onQuotePageChange"
      />
    </div>
  </el-dialog>

  <el-dialog
    v-model="locationVisible"
    width="780px"
    destroy-on-close
    :title="`地图定位 - ${locationRow?.company_name || locationRow?.username || ''}`"
  >
    <div class="map-meta">
      <div>地址：{{ locationRow?.address || '—' }}</div>
      <div>坐标：{{ locationRow?.lng }}, {{ locationRow?.lat }}（高德/GCJ-02）</div>
    </div>
    <div ref="mapRef" class="map-canvas"></div>
  </el-dialog>
</template>

<style scoped>
.crud-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.crud-actions {
  display: flex;
  align-items: center;
}

.op-btns {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.field-tip {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}

.submit-btn {
  min-width: 96px;
}

.supplier-map {
  width: 100%;
  height: 320px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  overflow: hidden;
}

.supplier-coord-row {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 8px;
  font-size: 13px;
  color: #475569;
}

.supplier-coord-row strong {
  color: #0f172a;
}

.supplier-coord-tip {
  color: #94a3b8;
  font-size: 12px;
}

.address-input {
  width: 100%;
}

.field-tip-warn {
  color: #e6a23c;
}

.quote-filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.quote-filter-input {
  width: 220px;
}

.quote-filter-select {
  width: 180px;
}

.quote-pager {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}

.coord-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.float-quote-cell {
  min-width: 0;
}

.float-quote-preview {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  min-width: 0;
}

.float-quote-item-compact {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
  max-width: 100%;
}

.text-ellipsis {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.more-float-link {
  flex-shrink: 0;
  padding: 0 4px;
}

.float-quote-popover {
  max-height: 380px;
  overflow-y: auto;
}

.float-quote-popover-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.float-quote-popover-row:last-child {
  border-bottom: none;
}

.float-quote-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.client-name {
  color: #303133;
  font-weight: 500;
}

.client-price {
  color: #1f8d49;
  font-weight: 600;
}

.period-text,
.muted-text {
  color: #909399;
  font-size: 12px;
}

.peer-quote-box {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.peer-quote-summary {
  color: #303133;
  font-size: 12px;
}

.peer-quote-rank {
  color: #606266;
  font-size: 12px;
}

.peer-quote-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.peer-quote-item {
  color: #1f8d49;
  font-size: 12px;
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
