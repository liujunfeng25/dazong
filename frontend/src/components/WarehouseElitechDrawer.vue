<script setup>
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  bindWarehouseElitechApi,
  getWarehouseElitechHistoryApi,
  getWarehouseElitechHistoryCurveApi,
  getWarehouseElitechRealtimeApi,
  getWarehouseElitechRealtimeCurveApi,
  getWarehouseElitechApi,
  getWarehouseElitechWarningsApi,
  listElitechDevicesApi,
  unbindWarehouseElitechApi,
} from '../api/delivery'
import {
  defaultHistoryRange,
  elitechHistoryStatsFromRows,
  elitechElectricityLabel,
  elitechFormatValue,
  elitechOnlineLabel,
  elitechSensorSummary,
  elitechWarningLabel,
  elitechWarningText,
} from '../utils/elitechDeviceMeta'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  warehouse: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'changed'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const warehouseId = computed(() => Number(props.warehouse?.id) || 0)
const warehouseName = computed(() => props.warehouse?.name || '')
const boundFromList = computed(() => Boolean(props.warehouse?.elitech_bound))

const loading = ref(false)
const activeTab = ref('bind')
const binding = ref(null)
const deviceList = ref([])
const realtime = ref(null)
const historyRange = ref(defaultHistoryRange())
const historyPage = ref(1)
const historyRows = ref(50)
const historyData = ref({ dataList: [], count: 0 })
const warningPage = ref(1)
const warningRows = ref(50)
const warningData = ref({ dataList: [], count: 0 })
const historyStats = ref(null)
const curveMode = ref('realtime')
const curveChartRef = ref(null)
const curveHasData = ref(false)
const tabLoadedAt = ref({})
const TAB_CACHE_MS = 45000
let openDrawerSeq = 0
let curveLoadSeq = 0
let curveChart = null

const isBound = computed(() => Boolean(binding.value?.elitech_sn || props.warehouse?.elitech_sn))

const boundSn = computed(
  () => binding.value?.elitech_sn || props.warehouse?.elitech_sn || '',
)

const occupancyOf = (device) => {
  const whId = warehouseId.value
  const sn = String(device.sn || '')
  if (boundSn.value && sn === boundSn.value) {
    return { kind: 'self', label: '已绑本仓库' }
  }
  if (device.bound_warehouse_id && Number(device.bound_warehouse_id) !== whId) {
    const name = device.bound_warehouse_name || `仓库#${device.bound_warehouse_id}`
    return { kind: 'warehouse', label: `已绑仓库 ${name}` }
  }
  if (binding.value?.elitech_sn && boundSn.value !== sn) {
    return { kind: 'blocked', label: '本仓已绑其他设备' }
  }
  return { kind: 'free', label: '未绑定' }
}

const loadBinding = async () => {
  if (!warehouseId.value) return
  try {
    const res = await getWarehouseElitechApi(warehouseId.value)
    binding.value = res && res.elitech_sn ? res : null
  } catch {
    binding.value = null
  }
}

const shouldReloadTab = (name) => {
  const at = Number(tabLoadedAt.value[name] || 0)
  return !at || Date.now() - at > TAB_CACHE_MS
}

const markTabLoaded = (name) => {
  tabLoadedAt.value = { ...tabLoadedAt.value, [name]: Date.now() }
}

/** 滚动最近 1 小时（结束时间为当前时刻） */
const resetHistoryToDefault = () => {
  historyRange.value = defaultHistoryRange()
  historyPage.value = 1
}

const loadDevices = async () => {
  try {
    const res = await listElitechDevicesApi()
    deviceList.value = Array.isArray(res?.items) ? res.items : []
  } catch (err) {
    if (!deviceList.value.length) throw err
  }
}

const openDrawer = async () => {
  if (!warehouseId.value) return
  const seq = ++openDrawerSeq
  loading.value = true
  tabLoadedAt.value = {}
  resetHistoryToDefault()
  historyData.value = { dataList: [], count: 0 }
  historyStats.value = null
  curveHasData.value = false
  activeTab.value = boundFromList.value || props.warehouse?.elitech_sn ? 'realtime' : 'bind'
  try {
    await loadBinding()
    if (seq !== openDrawerSeq) return
    if (activeTab.value === 'bind') {
      await loadDevices()
      markTabLoaded('bind')
    } else if (activeTab.value === 'realtime' && isBound.value) {
      await loadRealtime()
      markTabLoaded('realtime')
    }
  } catch {
    // 全局 http 拦截器已提示错误，此处不再重复弹窗
  } finally {
    if (seq === openDrawerSeq) loading.value = false
  }
}

const handleToggleBind = async (device) => {
  const occ = occupancyOf(device)
  if (occ.kind === 'warehouse' || occ.kind === 'blocked') return
  loading.value = true
  try {
    if (occ.kind === 'self') {
      await unbindWarehouseElitechApi(warehouseId.value)
      binding.value = null
      ElMessage.success('已解绑')
    } else {
      await bindWarehouseElitechApi(warehouseId.value, { sn: device.sn })
      await loadBinding()
      ElMessage.success('已绑定')
      activeTab.value = 'realtime'
      await loadRealtime()
    }
    emit('changed')
    await loadDevices()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  } finally {
    loading.value = false
  }
}

const loadRealtime = async () => {
  if (!warehouseId.value || !isBound.value) return
  const res = await getWarehouseElitechRealtimeApi(warehouseId.value)
  realtime.value = res?.data || null
}

const loadHistory = async () => {
  if (!warehouseId.value || !isBound.value) return
  const res = await getWarehouseElitechHistoryApi(warehouseId.value, {
    page: Math.max(0, historyPage.value - 1),
    rows: historyRows.value,
    start_time: historyRange.value.start_time,
    end_time: historyRange.value.end_time,
  })
  const dataList = Array.isArray(res?.dataList) ? res.dataList : []
  historyData.value = {
    dataList,
    count: Number(res?.count) || 0,
  }
  historyStats.value = elitechHistoryStatsFromRows(dataList)
}

const loadHistoryTab = async (force = false) => {
  if (!warehouseId.value || !isBound.value) return
  if (force) {
    tabLoadedAt.value = { ...tabLoadedAt.value, history: 0 }
  } else if (!shouldReloadTab('history')) {
    return
  }
  loading.value = true
  try {
    await loadHistory()
    markTabLoaded('history')
  } catch {
    // 全局 http 拦截器已提示
  } finally {
    loading.value = false
  }
}

const loadWarnings = async () => {
  if (!warehouseId.value || !isBound.value) return
  const res = await getWarehouseElitechWarningsApi(warehouseId.value, {
    page: Math.max(0, warningPage.value - 1),
    rows: warningRows.value,
    sort_type: 1,
    start_time: historyRange.value.start_time,
    end_time: historyRange.value.end_time,
  })
  warningData.value = {
    dataList: Array.isArray(res?.dataList) ? res.dataList : [],
    count: Number(res?.count) || 0,
  }
}

const waitForCurveChartDom = async () => {
  for (let i = 0; i < 12; i += 1) {
    await nextTick()
    const el = curveChartRef.value
    if (el && (el.clientWidth > 0 || i >= 3)) return true
    await new Promise((r) => setTimeout(r, 40))
  }
  return Boolean(curveChartRef.value)
}

const renderCurve = (curve) => {
  if (!curveChartRef.value) return false
  const dates = curve?.dateList || []
  curveHasData.value = dates.length > 0
  if (!dates.length) {
    if (curveChart) {
      try { curveChart.clear() } catch {}
    }
    return true
  }
  if (!curveChart) curveChart = echarts.init(curveChartRef.value)
  const temps = (curve?.temperatureList || []).map((v) => (v == null || v === -999 ? null : Number(v)))
  const hums = (curve?.humidityList || []).map((v) => (v == null || v === -999 ? null : Number(v)))
  curveChart.setOption({
    legend: { data: ['温度℃', '湿度%RH'], bottom: 0 },
    grid: { left: 48, right: 48, top: 24, bottom: 56 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        rotate: 35,
        fontSize: 10,
        formatter: (v) => {
          const s = String(v || '')
          if (!s) return ''
          return s.length >= 16 ? s.slice(5, 16) : s
        },
      },
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const items = Array.isArray(params) ? params : [params]
        const idx = items[0]?.dataIndex ?? 0
        const title = dates[idx] || ''
        const lines = items.map((p) => `${p.marker}${p.seriesName}: ${p.value ?? '—'}`)
        return [title, ...lines].filter(Boolean).join('<br/>')
      },
    },
    yAxis: [
      { type: 'value', name: '温度', position: 'left' },
      { type: 'value', name: '湿度', position: 'right' },
    ],
    series: [
      { name: '温度℃', type: 'line', smooth: true, data: temps, yAxisIndex: 0 },
      { name: '湿度%RH', type: 'line', smooth: true, data: hums, yAxisIndex: 1 },
    ],
    color: ['#dc2626', '#0891b2'],
  }, true)
  curveChart.resize()
  return true
}

const loadCurve = async () => {
  if (!warehouseId.value || !isBound.value) return
  const seq = ++curveLoadSeq
  let curve = null
  if (curveMode.value === 'realtime') {
    const res = await getWarehouseElitechRealtimeCurveApi(warehouseId.value, { page: 0, rows: 15 })
    curve = res?.curve || null
  } else {
    const res = await getWarehouseElitechHistoryCurveApi(warehouseId.value, {
      start_time: historyRange.value.start_time,
      end_time: historyRange.value.end_time,
    })
    curve = res?.curve || null
  }
  if (seq !== curveLoadSeq) return
  await waitForCurveChartDom()
  if (seq !== curveLoadSeq) return
  if (!renderCurve(curve)) {
    await waitForCurveChartDom()
    renderCurve(curve)
  }
}

const loadCurveTab = async () => {
  if (!warehouseId.value || !isBound.value) return
  loading.value = true
  try {
    await loadCurve()
  } catch {
    curveHasData.value = false
  } finally {
    loading.value = false
  }
}

const onTabChange = async (name) => {
  if (!isBound.value && name !== 'bind') {
    activeTab.value = 'bind'
    return
  }
  if (name === 'history') {
    resetHistoryToDefault()
    await loadHistoryTab(true)
    return
  }
  if (name === 'curve') {
    await loadCurveTab()
    return
  }
  if (name !== 'bind' && !shouldReloadTab(name)) return
  loading.value = true
  try {
    if (name === 'bind') await loadDevices()
    if (name === 'realtime') await loadRealtime()
    if (name === 'warnings') await loadWarnings()
    markTabLoaded(name)
  } catch {
    // 全局 http 拦截器已提示错误
  } finally {
    loading.value = false
  }
}

watch(
  () => props.modelValue,
  (v) => {
    if (v) openDrawer()
    else {
      if (curveChart) {
        try { curveChart.dispose() } catch {}
        curveChart = null
      }
    }
  },
)

watch(curveMode, () => {
  if (activeTab.value !== 'curve' || !visible.value) return
  loadCurveTab()
})

onBeforeUnmount(() => {
  if (curveChart) {
    try { curveChart.dispose() } catch {}
    curveChart = null
  }
})

const rt = computed(() => realtime.value || {})
const online = computed(() => elitechOnlineLabel(rt.value.status))
</script>

<template>
  <el-drawer
    v-model="visible"
    size="68%"
    destroy-on-close
    :title="`温湿度仪 - ${warehouseName}`"
    class="warehouse-elitech-drawer"
  >
    <div v-loading="loading">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane label="绑定" name="bind">
          <el-alert
            type="info"
            :closable="false"
            title="每仓最多 1 台温湿度仪；每台设备全局只能绑定一个仓库。"
            style="margin-bottom: 12px"
          />
          <el-table :data="deviceList" border max-height="480">
            <el-table-column prop="sn" label="设备 GUID" min-width="180" show-overflow-tooltip />
            <el-table-column prop="device_name" label="名称" min-width="120" show-overflow-tooltip />
            <el-table-column label="能力" min-width="120">
              <template #default="{ row }">{{ elitechSensorSummary(row.device_types) }}</template>
            </el-table-column>
            <el-table-column label="归属" min-width="160">
              <template #default="{ row }">
                <el-tag
                  :type="occupancyOf(row).kind === 'self' ? 'success' : occupancyOf(row).kind === 'warehouse' ? 'danger' : occupancyOf(row).kind === 'blocked' ? 'warning' : 'info'"
                  effect="plain"
                >
                  {{ occupancyOf(row).label }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="160" align="right">
              <template #default="{ row }">
                <el-button
                  v-if="occupancyOf(row).kind === 'self'"
                  size="small"
                  type="danger"
                  plain
                  @click="handleToggleBind(row)"
                >解绑</el-button>
                <el-button
                  v-else-if="occupancyOf(row).kind === 'free'"
                  size="small"
                  type="primary"
                  @click="handleToggleBind(row)"
                >绑定到本仓库</el-button>
                <el-button v-else size="small" disabled>不可绑定</el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="暂无已开通 API 的设备；若列表为空请先检查 backend/.env 中 ELITECH_USERNAME/PASSWORD" :image-size="64" />
            </template>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="实时" name="realtime" :disabled="!isBound">
          <div v-if="isBound" class="elitech-realtime-grid">
            <el-descriptions :column="2" border>
              <el-descriptions-item label="GUID">{{ boundSn }}</el-descriptions-item>
              <el-descriptions-item label="在线">
                <el-tag :type="online.type" effect="light">{{ online.text }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="温度">{{ elitechFormatValue(rt.temperature, '℃') }}</el-descriptions-item>
              <el-descriptions-item label="湿度">{{ elitechFormatValue(rt.humidity, '%RH') }}</el-descriptions-item>
              <el-descriptions-item label="电量">{{ elitechElectricityLabel(rt.electricity) }}</el-descriptions-item>
              <el-descriptions-item label="上报时间">{{ rt.date || '—' }}</el-descriptions-item>
              <el-descriptions-item label="当前告警" :span="2">
                {{ elitechWarningText(rt.warning) }}
              </el-descriptions-item>
            </el-descriptions>
            <el-button type="primary" plain style="margin-top: 12px" @click="loadRealtime">刷新</el-button>
          </div>
        </el-tab-pane>

        <el-tab-pane label="曲线" name="curve" :disabled="!isBound">
          <div class="elitech-curve-toolbar">
            <el-radio-group v-model="curveMode" size="small">
              <el-radio-button value="realtime">最近数据</el-radio-button>
              <el-radio-button value="history">历史区间</el-radio-button>
            </el-radio-group>
            <template v-if="curveMode === 'history'">
              <el-date-picker
                v-model="historyRange.start_time"
                type="datetime"
                value-format="YYYY-MM-DD HH:mm:ss"
                placeholder="开始"
                style="width: 190px"
              />
              <el-date-picker
                v-model="historyRange.end_time"
                type="datetime"
                value-format="YYYY-MM-DD HH:mm:ss"
                placeholder="结束"
                style="width: 190px"
              />
            </template>
            <el-button size="small" type="primary" @click="loadCurveTab">加载曲线</el-button>
          </div>
          <div ref="curveChartRef" class="elitech-curve-chart" />
          <el-empty
            v-if="activeTab === 'curve' && !loading && !curveHasData"
            description="暂无曲线数据，可切换「历史区间」或稍后重试"
          />
        </el-tab-pane>

        <el-tab-pane label="历史明细" name="history" :disabled="!isBound">
          <div class="elitech-curve-toolbar">
            <el-date-picker
              v-model="historyRange.start_time"
              type="datetime"
              value-format="YYYY-MM-DD HH:mm:ss"
              placeholder="开始"
              style="width: 190px"
            />
            <el-date-picker
              v-model="historyRange.end_time"
              type="datetime"
              value-format="YYYY-MM-DD HH:mm:ss"
              placeholder="结束"
              style="width: 190px"
            />
            <el-button size="small" type="primary" @click="historyPage = 1; loadHistoryTab(true)">查询</el-button>
            <el-button
              size="small"
              @click="resetHistoryToDefault(); loadHistoryTab(true)"
            >
              最近一小时
            </el-button>
          </div>
          <p v-if="historyStats?.printStsList?.length" class="elitech-history-stats-hint">
            以下为当前页数据的温度/湿度统计（详细趋势请看「曲线」）
          </p>
          <el-table
            v-if="historyStats?.printStsList?.length"
            :data="historyStats.printStsList"
            border
            size="small"
            style="margin-bottom: 12px"
          >
            <el-table-column prop="text" label="指标" width="140" />
            <el-table-column prop="minValue" label="最小" />
            <el-table-column prop="averageValue" label="平均" />
            <el-table-column prop="maxValue" label="最大" />
          </el-table>
          <el-table :data="historyData.dataList" border max-height="360">
            <el-table-column prop="date" label="时间" width="170" />
            <el-table-column label="温度" width="100">
              <template #default="{ row }">{{ elitechFormatValue(row.temperature, '℃') }}</template>
            </el-table-column>
            <el-table-column label="湿度" width="100">
              <template #default="{ row }">{{ elitechFormatValue(row.humidity, '%RH') }}</template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-model:current-page="historyPage"
            :page-size="historyRows"
            layout="prev, pager, next, total"
            :total="historyData.count"
            style="margin-top: 12px"
            @current-change="loadHistoryTab(true)"
          />
        </el-tab-pane>

        <el-tab-pane label="告警" name="warnings" :disabled="!isBound">
          <div class="elitech-curve-toolbar">
            <el-date-picker
              v-model="historyRange.start_time"
              type="datetime"
              value-format="YYYY-MM-DD HH:mm:ss"
              placeholder="开始"
              style="width: 190px"
            />
            <el-date-picker
              v-model="historyRange.end_time"
              type="datetime"
              value-format="YYYY-MM-DD HH:mm:ss"
              placeholder="结束"
              style="width: 190px"
            />
            <el-button size="small" type="primary" @click="onTabChange('warnings')">查询</el-button>
          </div>
          <el-table :data="warningData.dataList" border max-height="420">
            <el-table-column prop="date" label="时间" width="170" />
            <el-table-column label="类型" min-width="140">
              <template #default="{ row }">{{ row.content || elitechWarningLabel(row.wrId) }}</template>
            </el-table-column>
            <el-table-column prop="wrData" label="告警值" width="100" />
          </el-table>
          <el-pagination
            v-model:current-page="warningPage"
            :page-size="warningRows"
            layout="prev, pager, next, total"
            :total="warningData.count"
            style="margin-top: 12px"
            @current-change="() => onTabChange('warnings')"
          />
        </el-tab-pane>
      </el-tabs>
    </div>
  </el-drawer>
</template>

<style scoped>
.elitech-realtime-grid {
  max-width: 720px;
}

.elitech-curve-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.elitech-curve-chart {
  width: 100%;
  height: 360px;
}

.elitech-history-stats-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: #94a3b8;
}
</style>
