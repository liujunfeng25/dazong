<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listDeliveryGeofencesApi,
  createDeliveryGeofenceApi,
  updateDeliveryGeofenceApi,
  deleteDeliveryGeofenceApi,
  seedReceivingGeofencesApi,
} from '../../api/delivery'
import { circleToPolygonGeoJson, rectangleRingFromBounds } from '../../utils/fenceMapGeometry'

const mapRef = ref(null)
const map = ref(null)
const fences = ref([])
const loading = ref(false)
const seeding = ref(false)
const drawFenceType = ref('no_go')

/**
 * 地图工具：浏览 | 绘制工具（点击即进入对应 MouseTool，与围栏类型组合决定会话类型）
 * 主流地图编辑：左侧竖条选工具，不再依赖「先选形状再点开始绘制」的两步易混流程。
 */
const mapTool = ref('pan')

const drawing = ref(false)
const draftReady = ref(false)
/** 本次 MouseTool 会话的图形类型，绘制完成回调只信它，避免与 UI 状态竞态 */
const sessionDrawKind = ref(null)

let mouseTool = null
let drawListener = null
let drawHandlerRef = null
/** 递增以作废尚未完成的 activateMapTool 异步流程，避免叠多个 MouseTool（表现为圆+多边形同时出现） */
let mapToolActivateSeq = 0
const mapOverlays = ref([])

const saveVisible = ref(false)
/** 仅在为保存围栏打开过弹窗后，@closed 才整页刷新，避免组件首次挂载误触发 closed */
const reloadAfterSaveDialogClose = ref(false)
const saveName = ref('')
const saveRadius = ref(200)
const pending = ref(null)

const typeLabel = {
  no_go: '禁行区域',
  staging: '分检/待命区域',
  receiving: '收货区域',
}

const shapeLabel = {
  rectangle: '矩形',
  circle: '圆形',
  polygon: '多边形',
  freehand: '手绘',
  receiving_circle: '圆形（收货）',
}

const typeTag = (t) => (t === 'no_go' ? 'danger' : t === 'staging' ? 'primary' : 'success')

const drawBusy = computed(() => drawing.value || draftReady.value)

const draftHint = computed(() => {
  if (!draftReady.value || !pending.value) return ''
  const t = typeLabel[drawFenceType.value] || ''
  const dk = pending.value.drawKind
  const s = shapeLabel[dk] || dk || ''
  return `已生成「${t} · ${s}」预览，确认后点「保存」填写名称入库，或「取消」丢弃。`
})

watch(drawFenceType, (t) => {
  if (draftReady.value || drawing.value) return
  if (t === 'receiving') mapTool.value = 'circle'
})

const loadList = async () => {
  loading.value = true
  try {
    fences.value = await listDeliveryGeofencesApi()
    await nextTick()
    renderFences()
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '加载围栏失败'
    ElMessage.error(typeof msg === 'string' ? msg : '加载围栏失败')
  } finally {
    loading.value = false
  }
}

const clearOverlays = () => {
  const m = map.value
  if (!m) return
  mapOverlays.value.forEach((o) => {
    try {
      o.setMap(null)
    } catch {
      /* ignore */
    }
  })
  mapOverlays.value = []
}

const renderFences = () => {
  clearOverlays()
  if (!map.value || !window.AMap) return
  const AMap = window.AMap
  const toShow = fences.value.filter((f) => f.is_active)
  for (const f of toShow) {
    if (f.fence_type === 'receiving' && f.center_lng != null && f.center_lat != null && f.radius_m) {
      const c = new AMap.Circle({
        center: [Number(f.center_lng), Number(f.center_lat)],
        radius: Number(f.radius_m),
        strokeColor: '#15803d',
        strokeWeight: 2,
        fillColor: '#86efac',
        fillOpacity: 0.22,
      })
      c.setMap(map.value)
      mapOverlays.value.push(c)
    } else if (f.geometry_json?.type === 'Polygon' && Array.isArray(f.geometry_json.coordinates?.[0])) {
      const ring = f.geometry_json.coordinates[0].map(([lng, lat]) => [Number(lng), Number(lat)])
      if (ring.length < 3) continue
      const strokeColor = f.fence_type === 'no_go' ? '#b91c1c' : '#1d4ed8'
      const fillColor = f.fence_type === 'no_go' ? '#fecaca' : '#bfdbfe'
      const poly = new AMap.Polygon({
        path: ring,
        strokeColor,
        strokeWeight: 2,
        fillColor,
        fillOpacity: 0.22,
      })
      poly.setMap(map.value)
      mapOverlays.value.push(poly)
    }
  }
  /** 不在此自动 setFitView，避免「一加载就缩放到满屏圆」造成误以为绘制模式错误 */
}

const removeDrawListeners = () => {
  if (mouseTool && drawHandlerRef && typeof mouseTool.off === 'function') {
    try {
      mouseTool.off('draw', drawHandlerRef)
    } catch {
      /* ignore */
    }
  }
  drawHandlerRef = null
  if (drawListener && window.AMap?.Event?.removeListener) {
    try {
      window.AMap.Event.removeListener(drawListener)
    } catch {
      /* ignore */
    }
  }
  drawListener = null
}

const closeMouseToolInstance = () => {
  if (!mouseTool) return
  try {
    mouseTool.close(true)
  } catch {
    /* ignore */
  }
  try {
    if (typeof mouseTool.turnOff === 'function') mouseTool.turnOff()
  } catch {
    /* ignore */
  }
  mouseTool = null
}

/** 清掉地图上所有覆盖物后重画已入库围栏，用于消除 MouseTool 残留的半成品/幽灵图形 */
const resyncMapOverlaysAfterToolAbort = () => {
  if (!map.value) return
  try {
    if (typeof map.value.clearMap === 'function') {
      map.value.clearMap()
    }
  } catch {
    /* ignore */
  }
  mapOverlays.value = []
  renderFences()
}

const abortMouseToolCore = () => {
  removeDrawListeners()
  closeMouseToolInstance()
  drawing.value = false
  sessionDrawKind.value = null
}

/** 结束 MouseTool；若此前正在绘制则清屏并重画已入库围栏（不碰仅预览态的 pending 图形） */
const abortActiveDrawTool = () => {
  const hadActiveDraw = drawing.value
  abortMouseToolCore()
  if (hadActiveDraw) resyncMapOverlaysAfterToolAbort()
}

const discardDraft = () => {
  if (pending.value?.overlay) {
    try {
      pending.value.overlay.setMap(null)
    } catch {
      /* ignore */
    }
  }
  pending.value = null
  draftReady.value = false
  sessionDrawKind.value = null
  removeDrawListeners()
  closeMouseToolInstance()
  drawing.value = false
  resyncMapOverlaysAfterToolAbort()
  mapTool.value = 'pan'
}

/** 结束 MouseTool 或放弃预览（与 Esc 行为一致，避免残留图形） */
const exitDrawingOrDiscardDraft = () => {
  if (draftReady.value) {
    discardDraft()
    ElMessage.info('已放弃预览')
    return
  }
  if (drawing.value) {
    abortActiveDrawTool()
    mapTool.value = 'pan'
    ElMessage.info('已取消当前绘制')
  }
}

const isTypingTarget = (el) => {
  if (!el || typeof el.closest !== 'function') return false
  return Boolean(
    el.closest('input, textarea, [contenteditable="true"], .el-dialog, .el-message-box, .el-select__popper'),
  )
}

const onFenceKeydown = (e) => {
  if (e.key !== 'Escape') return
  if (isTypingTarget(e.target)) return
  if (!drawing.value && !draftReady.value) return
  e.preventDefault()
  e.stopPropagation()
  exitDrawingOrDiscardDraft()
}

const initMap = async () => {
  const key = import.meta.env.VITE_AMAP_KEY
  if (!key || !mapRef.value) {
    ElMessage.warning('未配置高德 Key，无法加载电子围栏地图')
    return
  }
  await AMapLoader.load({ key, version: '2.0' })
  await new Promise((resolve) => {
    window.AMap.plugin(['AMap.MouseTool'], () => resolve())
  })
  map.value = new window.AMap.Map(mapRef.value, {
    zoom: 11,
    center: [116.397428, 39.90923],
    viewMode: '2D',
  })
  await loadList()
}

const strokeForFenceType = () => {
  const noGoStyle = {
    strokeColor: '#b91c1c',
    strokeWeight: 2,
    fillColor: '#fecaca',
    fillOpacity: 0.35,
  }
  const stagingStyle = {
    strokeColor: '#1d4ed8',
    strokeWeight: 2,
    fillColor: '#bfdbfe',
    fillOpacity: 0.35,
  }
  const recvStyle = {
    strokeColor: '#15803d',
    strokeWeight: 2,
    fillColor: '#86efac',
    fillOpacity: 0.35,
  }
  if (drawFenceType.value === 'receiving') return recvStyle
  return drawFenceType.value === 'no_go' ? noGoStyle : stagingStyle
}

/** 根据围栏类型 + 用户点的工具，得到本次会话类型（回调里只解析这一种） */
const resolveSessionKind = (tool) => {
  if (drawFenceType.value === 'receiving') return 'receiving_circle'
  if (tool === 'circle') return 'circle'
  if (tool === 'rectangle') return 'rectangle'
  if (tool === 'freehand') return 'freehand'
  return 'polygon'
}

const onDrawComplete = (e) => {
  const obj = e?.obj
  if (!obj) return
  const kind = sessionDrawKind.value
  if (!kind) return

  removeDrawListeners()
  closeMouseToolInstance()
  drawing.value = false
  sessionDrawKind.value = null
  mapTool.value = 'pan'

  try {
    if (kind === 'receiving_circle' || kind === 'circle') {
      if (typeof obj.getRadius !== 'function' || typeof obj.getCenter !== 'function') {
        ElMessage.warning('圆形绘制异常，请重试')
        try {
          obj.setMap(null)
        } catch {
          /* ignore */
        }
        return
      }
      const c = obj.getCenter()
      const lng = c.getLng()
      const lat = c.getLat()
      const r = Math.round(Number(obj.getRadius()) || saveRadius.value || 200)
      saveRadius.value = r
      if (kind === 'receiving_circle') {
        pending.value = { kind: 'receiving_circle', drawKind: 'receiving_circle', lng, lat, r, overlay: obj }
      } else {
        const geometry_json = circleToPolygonGeoJson(lng, lat, r)
        pending.value = { kind: 'polygon', drawKind: 'circle', geometry_json, overlay: obj }
      }
    } else if (kind === 'rectangle') {
      if (typeof obj.getBounds !== 'function') {
        ElMessage.warning('矩形绘制异常，请重试')
        try {
          obj.setMap(null)
        } catch {
          /* ignore */
        }
        return
      }
      const b = obj.getBounds()
      const sw = b.getSouthWest()
      const ne = b.getNorthEast()
      const ring = rectangleRingFromBounds(sw, ne)
      pending.value = {
        kind: 'polygon',
        drawKind: 'rectangle',
        geometry_json: { type: 'Polygon', coordinates: [ring] },
        overlay: obj,
      }
    } else if (kind === 'freehand') {
      const path = typeof obj.getPath === 'function' ? obj.getPath() : []
      const raw = path.map((p) => (typeof p.getLng === 'function' ? [p.getLng(), p.getLat()] : [p.lng, p.lat]))
      const ring = raw.map(([lng, lat]) => [Number(lng), Number(lat)])
      if (ring.length < 3) {
        ElMessage.warning('手绘路径至少需 3 个点')
        try {
          obj.setMap(null)
        } catch {
          /* ignore */
        }
        return
      }
      if (ring[0][0] !== ring[ring.length - 1][0] || ring[0][1] !== ring[ring.length - 1][1]) {
        ring.push([ring[0][0], ring[0][1]])
      }
      pending.value = {
        kind: 'polygon',
        drawKind: 'freehand',
        geometry_json: { type: 'Polygon', coordinates: [ring] },
        overlay: obj,
      }
    } else if (kind === 'polygon') {
      const path = typeof obj.getPath === 'function' ? obj.getPath() : []
      const raw = path.map((p) => (typeof p.getLng === 'function' ? [p.getLng(), p.getLat()] : [p.lng, p.lat]))
      const ring = raw.map(([lng, lat]) => [Number(lng), Number(lat)])
      if (ring.length < 3) {
        ElMessage.warning('多边形顶点过少，请重新绘制')
        try {
          obj.setMap(null)
        } catch {
          /* ignore */
        }
        return
      }
      if (ring[0][0] !== ring[ring.length - 1][0] || ring[0][1] !== ring[ring.length - 1][1]) {
        ring.push([ring[0][0], ring[0][1]])
      }
      pending.value = {
        kind: 'polygon',
        drawKind: 'polygon',
        geometry_json: { type: 'Polygon', coordinates: [ring] },
        overlay: obj,
      }
    } else {
      try {
        obj.setMap(null)
      } catch {
        /* ignore */
      }
      return
    }
  } catch (err) {
    console.error(err)
    ElMessage.error('解析绘制结果失败，请重试')
    try {
      obj.setMap(null)
    } catch {
      /* ignore */
    }
    return
  }

  draftReady.value = true
}

const attachDrawListener = () => {
  const AMap = window.AMap
  const handler = (ev) => onDrawComplete(ev)
  drawHandlerRef = handler
  if (typeof mouseTool.on === 'function') {
    mouseTool.on('draw', drawHandlerRef)
  } else {
    drawListener = AMap.Event.addListener(mouseTool, 'draw', drawHandlerRef)
  }
}

/**
 * @param {'pan'|'polygon'|'rectangle'|'circle'|'freehand'} tool
 */
const activateMapTool = async (tool) => {
  if (!map.value) {
    ElMessage.warning('地图未就绪')
    return
  }

  if (tool === 'pan') {
    mapToolActivateSeq += 1
    abortActiveDrawTool()
    mapTool.value = 'pan'
    return
  }

  if (drawFenceType.value === 'receiving' && tool !== 'circle') {
    ElMessage.info('收货区域仅支持圆形')
    return
  }

  if (draftReady.value) {
    try {
      await ElMessageBox.confirm('当前有未保存的预览，切换工具将丢弃。是否继续？', '提示', {
        type: 'warning',
      })
    } catch {
      return
    }
    discardDraft()
  }

  const seq = (mapToolActivateSeq += 1)

  abortMouseToolCore()
  /** 每次进入新绘制前整图同步一次，清掉 MouseTool 残留在地图上的半成品（仅依赖 close 时高德偶发仍留一层） */
  resyncMapOverlaysAfterToolAbort()

  await nextTick()
  await new Promise((r) => setTimeout(r, 48))
  if (seq !== mapToolActivateSeq) return

  closeMouseToolInstance()
  removeDrawListeners()
  if (seq !== mapToolActivateSeq) return

  const kind = resolveSessionKind(tool)
  sessionDrawKind.value = kind
  mapTool.value = tool

  const AMap = window.AMap
  mouseTool = new AMap.MouseTool(map.value)
  drawing.value = true
  draftReady.value = false

  const st = strokeForFenceType()

  try {
    if (kind === 'receiving_circle' || kind === 'circle') {
      mouseTool.circle({
        ...st,
        radius: saveRadius.value || 200,
      })
    } else if (kind === 'rectangle') {
      if (typeof mouseTool.rectangle !== 'function') {
        ElMessage.error('当前运行环境不支持矩形 MouseTool，请使用「多边形」描矩形边')
        abortActiveDrawTool()
        mapTool.value = 'pan'
        return
      }
      mouseTool.rectangle(st)
    } else if (kind === 'freehand') {
      mouseTool.polyline({
        strokeColor: st.strokeColor,
        strokeWeight: 3,
        strokeOpacity: 0.95,
      })
    } else {
      mouseTool.polygon(st)
    }
  } catch (err) {
    console.error(err)
    ElMessage.error('启动绘制工具失败')
    abortActiveDrawTool()
    mapTool.value = 'pan'
    return
  }

  if (seq !== mapToolActivateSeq) {
    abortMouseToolCore()
    resyncMapOverlaysAfterToolAbort()
    mapTool.value = 'pan'
    return
  }

  attachDrawListener()
}

const openSaveDialog = () => {
  if (!pending.value) return
  saveName.value = ''
  reloadAfterSaveDialogClose.value = true
  saveVisible.value = true
}

/** 保存围栏弹窗任意关闭方式（确定 / 返回修改 / 右上角 X / 点遮罩）后整页刷新，避免地图 MouseTool 残留 */
const onFenceSaveDialogClosed = () => {
  if (!reloadAfterSaveDialogClose.value) return
  reloadAfterSaveDialogClose.value = false
  window.location.reload()
}

const cancelSave = () => {
  saveVisible.value = false
}

const confirmSave = async () => {
  if (!pending.value) return
  try {
    if (pending.value.kind === 'receiving_circle') {
      await createDeliveryGeofenceApi({
        fence_type: 'receiving',
        name: saveName.value.trim(),
        center_lng: pending.value.lng,
        center_lat: pending.value.lat,
        radius_m: Math.max(50, Math.min(5000, Number(saveRadius.value) || pending.value.r || 200)),
      })
    } else {
      await createDeliveryGeofenceApi({
        fence_type: drawFenceType.value,
        name: saveName.value.trim(),
        geometry_json: pending.value.geometry_json,
      })
    }
    try {
      pending.value.overlay.setMap(null)
    } catch {
      /* ignore */
    }
    pending.value = null
    draftReady.value = false
    mapTool.value = 'pan'
    ElMessage.success('已保存围栏')
    saveVisible.value = false
    /* 列表刷新由 onFenceSaveDialogClosed → 整页 reload 完成 */
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '保存失败'
    ElMessage.error(typeof msg === 'string' ? msg : '保存失败')
  }
}

const onActiveChange = async (row, val) => {
  try {
    await updateDeliveryGeofenceApi(row.id, { is_active: Boolean(val) })
    await loadList()
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '更新失败'
    ElMessage.error(typeof msg === 'string' ? msg : '更新失败')
    await loadList()
  }
}

const removeFence = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除围栏「${row.name || typeLabel[row.fence_type]}」？`, '删除确认', {
      type: 'warning',
    })
  } catch {
    window.location.reload()
    return
  }
  try {
    await deleteDeliveryGeofenceApi(row.id)
    ElMessage.success('已删除')
    window.location.reload()
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '删除失败'
    ElMessage.error(typeof msg === 'string' ? msg : '删除失败')
  }
}

const fitFence = (row) => {
  if (!map.value) return
  const AMap = window.AMap
  const overlays = []
  if (row.fence_type === 'receiving' && row.center_lng != null && row.center_lat != null && row.radius_m) {
    overlays.push(
      new AMap.Circle({
        center: [Number(row.center_lng), Number(row.center_lat)],
        radius: Number(row.radius_m),
      }),
    )
  } else if (row.geometry_json?.coordinates?.[0]) {
    const ring = row.geometry_json.coordinates[0].map(([lng, lat]) => [Number(lng), Number(lat)])
    overlays.push(new AMap.Polygon({ path: ring }))
  }
  if (overlays.length) {
    overlays.forEach((o) => o.setMap(map.value))
    try {
      map.value.setFitView(overlays, false, [80, 80, 80, 80], 16)
    } catch {
      /* ignore */
    }
    setTimeout(() => overlays.forEach((o) => o.setMap(null)), 400)
  }
}

const fitAllFences = () => {
  if (!map.value || !mapOverlays.value.length) {
    ElMessage.info('暂无已启用围栏可缩放')
    return
  }
  try {
    map.value.setFitView(mapOverlays.value, false, [48, 48, 48, 48], 14)
  } catch {
    /* ignore */
  }
}

const seedFromContracts = async () => {
  seeding.value = true
  try {
    const res = await seedReceivingGeofencesApi({ radius_m: 200 })
    const u = Number(res?.upserted || 0)
    const sk = Array.isArray(res?.skipped) ? res.skipped.length : 0
    ElMessage.success(`已同步收货区 ${u} 个；跳过 ${sk} 个（无坐标或未匹配合约）`)
    await loadList()
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '生成失败'
    ElMessage.error(typeof msg === 'string' ? msg : '生成失败')
  } finally {
    seeding.value = false
  }
}

onMounted(async () => {
  await nextTick()
  await initMap()
  window.addEventListener('keydown', onFenceKeydown, true)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onFenceKeydown, true)
  discardDraft()
  clearOverlays()
  if (map.value) {
    try {
      map.value.destroy()
    } catch {
      /* ignore */
    }
    map.value = null
  }
})
</script>

<template>
  <div class="fence-page">
    <el-alert
      class="mb-3"
      type="info"
      :closable="false"
      title="① 选围栏类型；② 左侧点绘制工具；③ 画完后底部「取消 / 保存」。绘制中或预览未保存时按 Esc 或点「结束 / 放弃」可立即清除地图上的临时图形（与微信截图条类似）。列表中的圆/面为已保存数据。「禁行区域」会参与智能排线的驾车路径（高德避让）与分配阶段直线穿越惩罚；分检/待命与收货区域不参与排线计算，仅作现场管理展示。"
    />
    <div class="fence-toolbar">
      <span class="fence-label">围栏类型</span>
      <el-radio-group v-model="drawFenceType" size="small" :disabled="drawBusy">
        <el-radio-button label="no_go">禁行区域</el-radio-button>
        <el-radio-button label="staging">分检/待命</el-radio-button>
        <el-radio-button label="receiving">收货区域</el-radio-button>
      </el-radio-group>
      <el-button size="small" :disabled="!map || !mapOverlays.length" @click="fitAllFences">缩放到全部围栏</el-button>
      <el-button
        size="small"
        type="warning"
        plain
        :disabled="!map || (!drawing && !draftReady)"
        @click="exitDrawingOrDiscardDraft"
      >
        结束 / 放弃
      </el-button>
      <el-button size="small" :disabled="!draftReady" @click="discardDraft">放弃预览</el-button>
      <el-button type="success" plain size="small" :loading="seeding" :disabled="drawBusy" @click="seedFromContracts">
        从合约客户生成收货区（200m）
      </el-button>
    </div>
    <div v-if="drawFenceType === 'receiving'" class="fence-hint text-xs text-slate-500 mb-2">
      圆形初始半径（米），保存对话框中可再改。
      <el-input-number v-model="saveRadius" :min="50" :max="5000" size="small" class="ml-2" :disabled="drawBusy" />
    </div>

    <div class="fence-map-wrap" tabindex="-1" @keydown.esc.stop.prevent="exitDrawingOrDiscardDraft">
      <div ref="mapRef" class="fence-map" />

      <div class="fence-map-tools" @mousedown.stop @touchstart.stop>
        <div class="fence-map-tools-title">绘制工具</div>
        <button
          type="button"
          class="fence-tool-btn"
          :class="{ active: mapTool === 'pan' }"
          :disabled="!map"
          @click="activateMapTool('pan')"
        >
          浏览
        </button>
        <template v-if="drawFenceType !== 'receiving'">
          <button
            type="button"
            class="fence-tool-btn"
            :class="{ active: mapTool === 'polygon' && drawing }"
            :disabled="!map || drawBusy"
            @click="activateMapTool('polygon')"
          >
            多边形
          </button>
          <button
            type="button"
            class="fence-tool-btn"
            :class="{ active: mapTool === 'rectangle' && drawing }"
            :disabled="!map || drawBusy"
            @click="activateMapTool('rectangle')"
          >
            矩形
          </button>
          <button
            type="button"
            class="fence-tool-btn"
            :class="{ active: mapTool === 'circle' && drawing }"
            :disabled="!map || drawBusy"
            @click="activateMapTool('circle')"
          >
            圆形
          </button>
          <button
            type="button"
            class="fence-tool-btn"
            :class="{ active: mapTool === 'freehand' && drawing }"
            :disabled="!map || drawBusy"
            @click="activateMapTool('freehand')"
          >
            手绘
          </button>
        </template>
        <template v-else>
          <button
            type="button"
            class="fence-tool-btn"
            :class="{ active: mapTool === 'circle' && drawing }"
            :disabled="!map || drawBusy"
            @click="activateMapTool('circle')"
          >
            圆形
          </button>
        </template>
      </div>

      <transition name="fade">
        <div v-if="draftReady" class="fence-draft-bar">
          <span class="fence-draft-text">{{ draftHint }}</span>
          <div class="fence-draft-actions">
            <el-button size="default" round @click="discardDraft">取消</el-button>
            <el-button type="primary" size="default" round @click="openSaveDialog">保存</el-button>
          </div>
        </div>
      </transition>
      <div v-if="drawing || draftReady" class="fence-drawing-hint">
        <template v-if="draftReady">预览未入库：底部可保存或取消，也可按 Esc / 点「结束 / 放弃」</template>
        <template v-else-if="mapTool === 'polygon'">多边形：单击加点，双击结束 · Esc 取消</template>
        <template v-else-if="mapTool === 'freehand'">手绘：单击加点，双击结束 · Esc 取消</template>
        <template v-else-if="mapTool === 'rectangle'">矩形：按下拖动，松开结束 · Esc 取消</template>
        <template v-else>圆形：按下拖动拉出半径，松开结束 · Esc 取消</template>
      </div>
    </div>

    <el-card class="mt-3" shadow="never">
      <template #header>围栏列表</template>
      <el-table v-loading="loading" :data="fences" border size="small" empty-text="暂无围栏，请绘制或从合约生成">
        <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="typeTag(row.fence_type)">{{ typeLabel[row.fence_type] }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="radius_m" label="半径(m)" width="88" align="center">
          <template #default="{ row }">{{ row.radius_m ?? '—' }}</template>
        </el-table-column>
        <el-table-column prop="client_id" label="客户ID" width="88" align="center">
          <template #default="{ row }">{{ row.client_id ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="启用" width="88" align="center">
          <template #default="{ row }">
            <el-switch :model-value="row.is_active" @change="(v) => onActiveChange(row, v)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="fitFence(row)">定位</el-button>
            <el-button link type="danger" size="small" @click="removeFence(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="saveVisible"
      title="保存围栏"
      width="420px"
      destroy-on-close
      @closed="onFenceSaveDialogClosed"
    >
      <el-form label-width="88px">
        <el-form-item label="名称">
          <el-input v-model="saveName" maxlength="128" placeholder="可选，便于列表识别" />
        </el-form-item>
        <el-form-item v-if="pending?.kind === 'receiving_circle'" label="半径(米)">
          <el-input-number v-model="saveRadius" :min="50" :max="5000" class="w-full" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cancelSave">返回修改</el-button>
        <el-button type="primary" @click="confirmSave">确定保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.fence-page {
  min-height: 400px;
}
.fence-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.fence-label {
  font-size: 13px;
  color: #475569;
  font-weight: 600;
}
.fence-map-wrap {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e2e8f0;
}
.fence-map {
  height: 460px;
  width: 100%;
}
.fence-map-tools {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 130;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.96);
  border-radius: 10px;
  box-shadow: 0 2px 14px rgba(15, 23, 42, 0.12);
  border: 1px solid #e2e8f0;
  max-width: 96px;
}
.fence-map-tools-title {
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  text-align: center;
  line-height: 1.2;
  margin-bottom: 2px;
}
.fence-tool-btn {
  display: block;
  width: 100%;
  padding: 8px 6px;
  font-size: 12px;
  line-height: 1.2;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
  color: #334155;
  cursor: pointer;
  transition:
    background 0.15s,
    border-color 0.15s,
    color 0.15s;
}
.fence-tool-btn:hover:not(:disabled) {
  background: #f8fafc;
  border-color: #cbd5e1;
}
.fence-tool-btn.active {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}
.fence-tool-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.fence-draft-bar {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 120;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  background: rgba(15, 23, 42, 0.82);
  backdrop-filter: blur(6px);
  border-top: 1px solid rgba(255, 255, 255, 0.12);
}
.fence-draft-text {
  flex: 1;
  min-width: 200px;
  font-size: 13px;
  color: #f1f5f9;
  line-height: 1.45;
}
.fence-draft-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}
.fence-drawing-hint {
  position: absolute;
  top: 10px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 110;
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 12px;
  color: #0f172a;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 2px 10px rgba(15, 23, 42, 0.15);
  max-width: 90%;
  text-align: center;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
