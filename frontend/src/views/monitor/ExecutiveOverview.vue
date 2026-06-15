<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { monitorExecutiveOverviewApi } from '../../api/monitor'

const emit = defineEmits(['navigate'])
const loading = ref(true)
const loadError = ref('')
const data = ref({})
const periodDays = ref(7)
const deliveryMetric = ref('orders')
const trendRef = ref(null)
const mixRef = ref(null)
const deliveryRef = ref(null)
const supplierRef = ref(null)
const categoryRef = ref(null)
const clientRef = ref(null)
const matrixRef = ref(null)
const schoolDrawerVisible = ref(false)
const activeSchoolId = ref(null)
let trendChart = null
let mixChart = null
let deliveryChart = null
let supplierChart = null
let categoryChart = null
let clientChart = null
let matrixChart = null
let resizeObserver = null

const summary = computed(() => data.value.summary || {})
const lifecycle = computed(() => data.value.lifecycle || [])
const topRisks = computed(() => data.value.top_risks || [])
const regions = computed(() => data.value.regions || [])
const suppliers = computed(() => data.value.supplier_risks || [])
const quality = computed(() => data.value.quality || {})
const settlement = computed(() => data.value.settlement || {})
const deliveryRankings = computed(() => data.value.delivery_rankings || [])
const supplierPerformance = computed(() => data.value.supplier_performance || [])
const categoryMix = computed(() => data.value.category_mix || [])
const clientRankings = computed(() => data.value.client_rankings || [])
const activeSchool = computed(() => clientRankings.value.find((row) => row.id === activeSchoolId.value) || null)
const activeCanteens = computed(() => activeSchool.value?.canteens || [])
const activeCanteenCount = computed(() => activeCanteens.value.filter((row) => row.canteen_id != null).length)
const deliveryClientMatrix = computed(() => data.value.delivery_client_matrix || { deliveries: [], clients: [], cells: [] })
const matrixUsesHeatmap = computed(() => deliveryClientMatrix.value.deliveries.length >= 2 && deliveryClientMatrix.value.clients.length >= 3)
const conclusion = computed(() => data.value.conclusion || { status: '数据汇聚中', tone: 'stable', text: '正在计算监管态势' })
const trendRows = computed(() => data.value.trends || [])

const fmtNumber = (value, digits = 0) => Number(value || 0).toLocaleString('zh-CN', {
  minimumFractionDigits: digits,
  maximumFractionDigits: digits,
})
const fmtMoney = (value) => {
  const n = Number(value || 0)
  if (Math.abs(n) >= 10000) return `¥${fmtNumber(n / 10000, 1)}万`
  return `¥${fmtNumber(n)}`
}
const fmtPct = (value) => `${fmtNumber(value, 1)}%`
const fmtDuration = (hours) => {
  const value = Number(hours || 0)
  return value >= 24 ? `${Math.floor(value / 24)}天${value % 24}小时` : `${value}小时`
}
const shortDate = (value) => String(value || '').slice(5).replace('-', '/')
const schoolNameParts = (value) => {
  const full = String(value || '')
  return {
    full,
    name: full.replace(/[（(]\s*演示\s*[）)]/g, '').trim(),
    demo: /[（(]\s*演示\s*[）)]/.test(full),
  }
}
const wrapSchoolName = (value, charsPerLine = 10) => {
  const name = schoolNameParts(value).name
  return name.length <= charsPerLine
    ? [name]
    : [name.slice(0, charsPerLine), name.slice(charsPerLine, charsPerLine * 2)]
}
const schoolAxisLabel = (value, charsPerLine = 10) => {
  const parts = schoolNameParts(value)
  const lines = wrapSchoolName(value, charsPerLine)
  const demo = parts.demo ? ' {demo|演示}' : ''
  return lines.length > 1
    ? `{school|${lines[0]}}\n{school|${lines[1]}}${demo}`
    : `{school|${lines[0]}}${demo}`
}
const schoolLabelMargin = (rows, min = 148, max = 226) => {
  const longest = Math.max(0, ...rows.map((row) => schoolNameParts(row.name).name.length))
  return Math.min(max, Math.max(min, 42 + Math.min(longest, 20) * 9))
}
const generatedTime = computed(() => {
  const value = data.value.generated_at
  if (!value) return '--'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
})

const kpis = computed(() => [
  { key: 'orders', label: '今日订单', value: fmtNumber(summary.value.today_orders), unit: '单', note: '北京时间自然日', tone: 'cyan', module: 'audit' },
  { key: 'gmv', label: '今日采购额', value: fmtMoney(summary.value.today_gmv), unit: '', note: '订单金额汇总', tone: 'mint', module: 'audit' },
  { key: 'delivery', label: `近${periodDays.value}日送达率`, value: fmtPct(summary.value.fulfillment_rate), unit: '', note: '已送达 / 有效订单', tone: Number(summary.value.fulfillment_rate) < 90 ? 'warn' : 'mint', module: 'logistics' },
  { key: 'audit', label: '审计覆盖率', value: fmtPct(summary.value.audit_coverage_rate), unit: '', note: '具备操作或状态留痕', tone: 'cyan', module: 'audit' },
  { key: 'risk', label: '待处置风险', value: fmtNumber(summary.value.pending_risks), unit: '项', note: '预警、工单、质检、账务', tone: Number(summary.value.pending_risks) ? 'risk' : 'mint', module: 'alerts' },
  { key: 'settlement', label: '未结算金额', value: fmtMoney(summary.value.unsettled_amount), unit: '', note: `${fmtNumber(settlement.value.pending)} 笔账单`, tone: Number(summary.value.unsettled_amount) ? 'warn' : 'mint', module: 'audit' },
])

const navItems = [
  { code: 'AUD', label: '全链审计', module: 'audit', text: '订单证据与监管闭环' },
  { code: 'LOG', label: '履约监控', module: 'logistics', text: '车辆、站点与阻塞' },
  { code: 'ALT', label: '预警处置', module: 'alerts', text: '风险与工单中心' },
  { code: 'MAP', label: '全域地图', module: 'beijing-map', text: '区域与物流态势' },
  { code: 'CMD', label: '指挥广播', module: 'broadcast', text: '跨角色指令下达' },
]

const navigate = (module) => emit('navigate', module)
const openSchoolDrawer = (schoolId) => {
  const school = clientRankings.value.find((row) => row.id === schoolId)
  if (!school) return
  activeSchoolId.value = school.id
  schoolDrawerVisible.value = true
}
const openSchoolAudit = () => {
  schoolDrawerVisible.value = false
  navigate('audit')
}
const chartText = '#7896a6'
const chartGrid = 'rgba(0,229,255,.065)'
const tooltip = {
  backgroundColor: 'rgba(4,16,27,.97)',
  borderColor: 'rgba(0,229,255,.3)',
  textStyle: { color: '#e8fbff' },
}
const observeChartRefs = () => {
  if (!resizeObserver) return
  ;[trendRef, mixRef, deliveryRef, supplierRef, categoryRef, clientRef, matrixRef].forEach((chartRef) => {
    if (chartRef.value) resizeObserver.observe(chartRef.value)
  })
}

const renderCharts = () => {
  if (trendRef.value) {
    trendChart ||= echarts.init(trendRef.value)
    const rows = trendRows.value
    trendChart.setOption({
      animationDuration: 700,
      color: ['#00e5ff', '#68fadd', '#ffbd59'],
      tooltip: {
        trigger: 'axis',
        ...tooltip,
      },
      legend: {
        right: 6,
        top: 0,
        itemWidth: 16,
        itemHeight: 3,
        textStyle: { color: '#7896a6', fontSize: 10 },
        data: ['订单量', '送达率', '风险'],
      },
      grid: { left: 38, right: 42, top: 36, bottom: 26 },
      xAxis: {
        type: 'category',
        data: rows.map((row) => shortDate(row.date)),
        boundaryGap: false,
        axisLine: { lineStyle: { color: 'rgba(0,229,255,.14)' } },
        axisTick: { show: false },
        axisLabel: { color: '#688695', fontSize: 10 },
      },
      yAxis: [
        {
          type: 'value',
          axisLabel: { color: '#688695', fontSize: 10 },
          splitLine: { lineStyle: { color: 'rgba(0,229,255,.06)', type: 'dashed' } },
        },
        {
          type: 'value',
          min: 0,
          max: 100,
          axisLabel: { color: '#688695', fontSize: 10, formatter: '{value}%' },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: '订单量',
          type: 'line',
          smooth: true,
          showSymbol: false,
          data: rows.map((row) => row.orders),
          lineStyle: { width: 2.5, shadowBlur: 10, shadowColor: '#00e5ff' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(0,229,255,.24)' },
              { offset: 1, color: 'rgba(0,229,255,0)' },
            ]),
          },
        },
        {
          name: '送达率',
          type: 'line',
          yAxisIndex: 1,
          smooth: true,
          showSymbol: false,
          data: rows.map((row) => row.fulfillment_rate),
          lineStyle: { width: 2, color: '#68fadd' },
        },
        {
          name: '风险',
          type: 'bar',
          barWidth: periodDays.value === 7 ? 10 : 5,
          data: rows.map((row) => row.risks),
          itemStyle: { color: 'rgba(255,189,89,.72)', borderRadius: [4, 4, 0, 0] },
        },
      ],
    }, true)
  }
  if (mixRef.value) {
    mixChart ||= echarts.init(mixRef.value)
    mixChart.setOption({
      animationDuration: 700,
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(4,16,27,.96)',
        borderColor: 'rgba(0,229,255,.3)',
        textStyle: { color: '#e8fbff' },
      },
      series: [{
        type: 'pie',
        radius: ['58%', '78%'],
        center: ['50%', '50%'],
        label: { show: false },
        itemStyle: { borderColor: '#07121f', borderWidth: 4, borderRadius: 8 },
        data: [
          { name: '质检已覆盖', value: quality.value.covered || 0, itemStyle: { color: '#68fadd' } },
          { name: '已出库缺报告', value: quality.value.missing || 0, itemStyle: { color: '#ffbd59' } },
          { name: '账单已结', value: settlement.value.settled || 0, itemStyle: { color: '#00e5ff' } },
          { name: '账单待结', value: settlement.value.pending || 0, itemStyle: { color: '#ff7188' } },
        ],
      }],
    }, true)
  }

  if (deliveryRef.value) {
    deliveryChart ||= echarts.init(deliveryRef.value)
    const rows = [...deliveryRankings.value].reverse()
    const metric = deliveryMetric.value
    deliveryChart.setOption({
      animationDuration: 650,
      tooltip: {
        ...tooltip,
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params) => {
          const row = rows[params[0]?.dataIndex] || {}
          return `${row.name || ''}<br/>订单 ${fmtNumber(row.orders)} 单<br/>采购额 ${fmtMoney(row.gmv)}<br/>送达率 ${fmtPct(row.fulfillment_rate)}<br/>异常率 ${fmtPct(row.abnormal_rate)}`
        },
      },
      grid: { left: 118, right: 58, top: 12, bottom: 26 },
      xAxis: {
        type: 'value',
        axisLabel: { color: chartText, fontSize: 9, formatter: metric === 'gmv' ? (v) => fmtMoney(v) : '{value}' },
        splitLine: { lineStyle: { color: chartGrid, type: 'dashed' } },
      },
      yAxis: {
        type: 'category',
        data: rows.map((row) => row.name),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#b9d9df', fontSize: 10, width: 105, overflow: 'truncate' },
      },
      series: [{
        type: 'bar',
        barWidth: 8,
        data: rows.map((row) => row[metric]),
        itemStyle: {
          borderRadius: 8,
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: 'rgba(0,229,255,.18)' },
            { offset: 1, color: '#68fadd' },
          ]),
        },
        label: {
          show: true,
          position: 'right',
          color: '#68fadd',
          fontSize: 9,
          formatter: ({ dataIndex }) => `${fmtPct(rows[dataIndex]?.fulfillment_rate)}`,
        },
      }],
    }, true)
    deliveryChart.off('click')
    deliveryChart.on('click', () => navigate('logistics'))
  }

  if (supplierRef.value) {
    supplierChart ||= echarts.init(supplierRef.value)
    const rows = supplierPerformance.value
    const enoughForScatter = rows.length >= 8
    supplierChart.setOption(enoughForScatter ? {
      animationDuration: 650,
      tooltip: {
        ...tooltip,
        formatter: ({ data }) => `${data[4]}<br/>采购额 ${fmtMoney(data[0])}<br/>履约率 ${fmtPct(data[1])}<br/>分单 ${data[2]} 条<br/>风险 ${data[3]} 项`,
      },
      grid: { left: 46, right: 24, top: 18, bottom: 34 },
      xAxis: { type: 'value', name: '采购额', nameTextStyle: { color: chartText }, axisLabel: { color: chartText, formatter: (v) => fmtMoney(v) }, splitLine: { lineStyle: { color: chartGrid } } },
      yAxis: { type: 'value', min: 0, max: 100, name: '履约率', nameTextStyle: { color: chartText }, axisLabel: { color: chartText, formatter: '{value}%' }, splitLine: { lineStyle: { color: chartGrid } } },
      series: [{
        type: 'scatter',
        data: rows.map((row) => [row.gmv, row.fulfillment_rate, row.allocations, row.risks, row.name]),
        symbolSize: (value) => Math.max(13, Math.min(42, 10 + Math.sqrt(value[2] || 0) * 3)),
        itemStyle: { color: ({ data }) => data[3] ? '#ff7188' : '#68fadd', shadowBlur: 12, shadowColor: 'rgba(0,229,255,.25)' },
      }],
    } : {
      animationDuration: 650,
      tooltip: { ...tooltip, trigger: 'axis' },
      grid: { left: 118, right: 34, top: 12, bottom: 28 },
      xAxis: { type: 'value', axisLabel: { color: chartText }, splitLine: { lineStyle: { color: chartGrid } } },
      yAxis: { type: 'category', data: [...rows].reverse().map((row) => row.name), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#b9d9df', width: 104, overflow: 'truncate' } },
      series: [{
        type: 'bar',
        barWidth: 7,
        data: [...rows].reverse().map((row) => ({ value: row.risks, itemStyle: { color: row.risks ? '#ff7188' : '#68fadd', borderRadius: 6 } })),
        label: { show: true, position: 'right', color: '#8eabb5', formatter: ({ dataIndex }) => `${fmtPct([...rows].reverse()[dataIndex]?.fulfillment_rate)} 履约` },
      }],
    }, true)
    supplierChart.off('click')
    supplierChart.on('click', () => navigate('audit'))
  }

  if (categoryRef.value) {
    categoryChart ||= echarts.init(categoryRef.value)
    const dominantCategory = categoryMix.value.some((row) => Number(row.share || 0) >= 72)
    const categoryRows = categoryMix.value.slice(0, 6)
    categoryChart.setOption({
      animationDuration: 650,
      tooltip: { ...tooltip, formatter: ({ data }) => `${data.name}<br/>采购额 ${fmtMoney(data.gmv ?? data.value)}<br/>占比 ${fmtPct(data.share)}<br/>数量 ${fmtNumber(data.quantity, 1)}` },
      ...(dominantCategory ? {
        grid: { left: 76, right: 48, top: 16, bottom: 24 },
        xAxis: { type: 'value', max: 100, axisLabel: { color: chartText, formatter: '{value}%' }, splitLine: { lineStyle: { color: chartGrid, type: 'dashed' } } },
        yAxis: { type: 'category', data: [...categoryRows].reverse().map((row) => row.name), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#b9d9df', width: 62, overflow: 'truncate' } },
        series: [{
          type: 'bar',
          barWidth: 14,
          data: [...categoryRows].reverse().map((row, index) => ({
            name: row.name,
            value: row.share,
            gmv: row.gmv,
            share: row.share,
            quantity: row.quantity,
            itemStyle: {
              borderRadius: 8,
              color: index === categoryRows.length - 1
                ? new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: '#087f8c' }, { offset: 1, color: '#68fadd' }])
                : 'rgba(0,229,255,.32)',
            },
          })),
          label: { show: true, position: 'right', color: '#bffcff', formatter: ({ value }) => fmtPct(value) },
        }],
      } : {
        series: [{
          type: 'treemap',
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          label: { show: true, color: '#e6fbff', fontSize: 11, formatter: ({ data }) => `${data.name}\n${fmtPct(data.share)}` },
          upperLabel: { show: false },
          itemStyle: { borderColor: '#071522', borderWidth: 4, gapWidth: 3 },
          levels: [{ color: ['#087f8c', '#0a6979', '#0b5368', '#0c4258', '#123949', '#17323e'], colorMappingBy: 'value', itemStyle: { borderRadius: 8 } }],
          data: categoryRows.map((row) => ({ name: row.name, value: row.gmv, gmv: row.gmv, share: row.share, quantity: row.quantity })),
        }],
      }),
    }, true)
    categoryChart.off('click')
    categoryChart.on('click', () => navigate('audit'))
  }

  if (clientRef.value) {
    clientChart ||= echarts.init(clientRef.value)
    const rows = [...clientRankings.value].reverse()
    const left = schoolLabelMargin(rows)
    clientChart.setOption({
      animationDuration: 650,
      tooltip: {
        ...tooltip,
        formatter: ({ dataIndex }) => {
          const row = rows[dataIndex] || {}
          return `${row.name}<br/>订单 ${row.orders} 单<br/>采购额 ${fmtMoney(row.gmv)}<br/>送达率 ${fmtPct(row.fulfillment_rate)}<br/>异常率 ${fmtPct(row.abnormal_rate)}`
        },
      },
      grid: { left, right: 54, top: 12, bottom: 26 },
      xAxis: { type: 'value', axisLabel: { color: chartText, formatter: (v) => fmtMoney(v) }, splitLine: { lineStyle: { color: chartGrid, type: 'dashed' } } },
      yAxis: {
        type: 'category',
        data: rows.map((row) => row.name),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          width: left - 34,
          lineHeight: 15,
          formatter: (value) => schoolAxisLabel(value),
          rich: {
            school: { color: '#b9d9df', fontSize: 10, lineHeight: 15, align: 'right' },
            demo: { color: '#4f7b88', fontSize: 8, lineHeight: 13, align: 'right' },
          },
        },
      },
      series: [{
        type: 'bar',
        barWidth: 4,
        data: rows.map((row) => ({ value: row.gmv, schoolId: row.id })),
        showBackground: true,
        backgroundStyle: { color: 'rgba(0,229,255,.035)', borderRadius: 4 },
        itemStyle: { color: '#00e5ff', borderRadius: 4, shadowBlur: 9, shadowColor: 'rgba(0,229,255,.45)' },
        label: { show: true, position: 'right', color: '#68fadd', fontSize: 9, formatter: ({ dataIndex }) => `${rows[dataIndex]?.orders || 0} 单` },
        markPoint: {
          symbol: 'circle',
          symbolSize: 10,
          label: { show: false },
          itemStyle: { color: '#bffcff', shadowBlur: 12, shadowColor: '#00e5ff' },
          data: rows.map((row, index) => ({ coord: [row.gmv, index] })),
        },
      }],
    }, true)
    clientChart.off('click')
    clientChart.on('click', ({ dataIndex }) => openSchoolDrawer(rows[dataIndex]?.id))
  }

  if (matrixRef.value) {
    matrixChart ||= echarts.init(matrixRef.value)
    const matrix = deliveryClientMatrix.value
    const deliveryIndex = new Map(matrix.deliveries.map((row, index) => [row.id, index]))
    const clientIndex = new Map(matrix.clients.map((row, index) => [row.id, index]))
    const cells = matrix.cells.map((row) => [clientIndex.get(row.client_id), deliveryIndex.get(row.delivery_id), row.orders, row.gmv, row.risks, row.client_id])
    const maxOrders = Math.max(1, ...matrix.cells.map((row) => row.orders || 0))
    const useHeatmap = matrix.deliveries.length >= 2 && matrix.clients.length >= 3
    const singleDeliveryRows = matrix.cells
      .filter((row) => row.delivery_id === matrix.deliveries[0]?.id)
      .sort((a, b) => a.orders - b.orders)
    const singleDeliverySchools = singleDeliveryRows.map((row) => (
      matrix.clients.find((client) => client.id === row.client_id)?.name || `学校#${row.client_id}`
    ))
    const singleDeliveryLeft = schoolLabelMargin(singleDeliverySchools.map((name) => ({ name })), 160, 238)
    matrixChart.setOption(useHeatmap ? {
      animationDuration: 650,
      tooltip: {
        ...tooltip,
        formatter: ({ data }) => `${matrix.deliveries[data[1]]?.name || ''} × ${matrix.clients[data[0]]?.name || ''}<br/>订单 ${data[2]} 单<br/>采购额 ${fmtMoney(data[3])}<br/>风险 ${data[4]} 项`,
      },
      grid: { left: 116, right: 28, top: 18, bottom: 82 },
      xAxis: { type: 'category', data: matrix.clients.map((row) => schoolNameParts(row.name).name), axisLine: { lineStyle: { color: chartGrid } }, axisTick: { show: false }, axisLabel: { color: chartText, fontSize: 9, rotate: 28, width: 108, overflow: 'break', lineHeight: 13 } },
      yAxis: { type: 'category', data: matrix.deliveries.map((row) => row.name), axisLine: { lineStyle: { color: chartGrid } }, axisTick: { show: false }, axisLabel: { color: chartText, fontSize: 9, width: 106, overflow: 'truncate' } },
      visualMap: { min: 0, max: maxOrders, show: false, inRange: { color: ['rgba(0,229,255,.025)', '#07596a', '#00bfd6', '#68fadd'] } },
      series: [{
        type: 'heatmap',
        data: cells,
        label: { show: true, color: '#e9fbff', fontSize: 9, formatter: ({ data }) => data[2] || '' },
        itemStyle: { borderColor: '#071522', borderWidth: 3, borderRadius: 5 },
        emphasis: { itemStyle: { shadowBlur: 16, shadowColor: 'rgba(0,229,255,.45)' } },
      }],
    } : {
      animationDuration: 650,
      tooltip: {
        ...tooltip,
        formatter: ({ data }) => `${data.name}<br/>订单 ${data.orders} 单<br/>采购额 ${fmtMoney(data.gmv)}<br/>风险 ${data.risks} 项`,
      },
      grid: { left: singleDeliveryLeft, right: 68, top: 18, bottom: 34 },
      xAxis: { type: 'value', axisLabel: { color: chartText }, splitLine: { lineStyle: { color: chartGrid, type: 'dashed' } } },
      yAxis: {
        type: 'category',
        data: singleDeliverySchools,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          width: singleDeliveryLeft - 34,
          lineHeight: 15,
          formatter: (value) => schoolAxisLabel(value),
          rich: {
            school: { color: '#b9d9df', fontSize: 10, lineHeight: 15, align: 'right' },
            demo: { color: '#4f7b88', fontSize: 8, lineHeight: 13, align: 'right' },
          },
        },
      },
      series: [{
        type: 'bar',
        barWidth: 12,
        data: singleDeliveryRows.map((row) => ({
          name: matrix.clients.find((client) => client.id === row.client_id)?.name || `客户#${row.client_id}`,
          schoolId: row.client_id,
          value: row.orders,
          orders: row.orders,
          gmv: row.gmv,
          risks: row.risks,
          itemStyle: {
            borderRadius: 8,
            color: row.risks
              ? new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: 'rgba(255,113,136,.2)' }, { offset: 1, color: '#ff7188' }])
              : new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: 'rgba(0,229,255,.16)' }, { offset: 1, color: '#68fadd' }]),
          },
        })),
        label: { show: true, position: 'right', color: '#dffcff', formatter: '{c} 单' },
      }],
    }, true)
    matrixChart.off('click')
    matrixChart.on('click', ({ data, dataIndex }) => {
      const schoolId = useHeatmap ? data?.[5] : (data?.schoolId || singleDeliveryRows[dataIndex]?.client_id)
      openSchoolDrawer(schoolId)
    })
  }
}

const load = async () => {
  loading.value = true
  loadError.value = ''
  try {
    data.value = await monitorExecutiveOverviewApi({ days: periodDays.value }) || {}
    if (schoolDrawerVisible.value && !activeSchool.value) {
      schoolDrawerVisible.value = false
      activeSchoolId.value = null
    }
    await nextTick()
    renderCharts()
    observeChartRefs()
  } catch (error) {
    loadError.value = error?.response?.data?.detail || error?.message || '监管总览加载失败'
  } finally {
    loading.value = false
  }
}

const switchPeriod = async (days) => {
  if (periodDays.value === days) return
  periodDays.value = days
  await load()
}

const switchDeliveryMetric = async (metric) => {
  deliveryMetric.value = metric
  await nextTick()
  renderCharts()
}

onMounted(() => {
  load()
  resizeObserver = new ResizeObserver(() => {
    trendChart?.resize()
    mixChart?.resize()
    deliveryChart?.resize()
    supplierChart?.resize()
    categoryChart?.resize()
    clientChart?.resize()
    matrixChart?.resize()
  })
  observeChartRefs()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  trendChart?.dispose()
  mixChart?.dispose()
  deliveryChart?.dispose()
  supplierChart?.dispose()
  categoryChart?.dispose()
  clientChart?.dispose()
  matrixChart?.dispose()
})
</script>

<template>
  <main class="executive-overview" v-loading="loading" element-loading-text="正在汇聚全域监管态势…">
    <div class="ambient ambient-a"></div>
    <div class="ambient ambient-b"></div>
    <div class="grid-field"></div>

    <header class="overview-header">
      <div>
        <p class="eyebrow"><i></i> REGULATORY INTELLIGENCE / ONLINE</p>
        <h1>全域监管</h1>
        <p class="subtitle">订单、履约、质检与结算的全局健康视图</p>
      </div>
      <div class="sync-block">
        <span>BEIJING BUSINESS DAY</span>
        <strong>{{ data.period?.today || '--' }}</strong>
        <em>LAST SYNCHRONIZED · {{ generatedTime }}</em>
        <button type="button" @click="load">刷新数据</button>
        <div class="global-period" aria-label="统计周期">
          <button type="button" :class="{ active: periodDays === 7 }" @click="switchPeriod(7)">7D</button>
          <button type="button" :class="{ active: periodDays === 30 }" @click="switchPeriod(30)">30D</button>
        </div>
      </div>
    </header>

    <section v-if="loadError" class="error-state">
      <strong>监管态势暂不可用</strong>
      <span>{{ loadError }}</span>
      <button type="button" @click="load">重新加载</button>
    </section>

    <template v-else>
      <section class="conclusion" :class="`tone-${conclusion.tone}`">
        <div class="conclusion-signal">
          <span></span><i></i><b></b>
        </div>
        <div>
          <p>AI RULE-BASED BRIEFING · 今日监管结论</p>
          <h2>{{ conclusion.text }}</h2>
        </div>
        <strong>{{ conclusion.status }}</strong>
      </section>

      <section class="telemetry">
        <button
          v-for="item in kpis"
          :key="item.key"
          type="button"
          class="telemetry-item"
          :class="`tone-${item.tone}`"
          @click="navigate(item.module)"
        >
          <span>{{ item.label }}</span>
          <div><strong>{{ item.value }}</strong><em>{{ item.unit }}</em></div>
          <small>{{ item.note }}</small>
          <i></i>
        </button>
      </section>

      <section class="primary-grid">
        <article class="panel lifecycle-panel">
          <div class="panel-heading">
            <div><p>BUSINESS HEALTH PULSE</p><h2>业务健康脉冲</h2></div>
            <span>近 {{ periodDays }} 日订单生命周期</span>
          </div>
          <div class="pulse-canvas">
            <div class="pulse-line"><i></i></div>
            <button
              v-for="(stage, index) in lifecycle"
              :key="stage.key"
              type="button"
              class="pulse-stage"
              :class="{ risk: stage.risk_count > 0 }"
              @click="navigate(stage.key === 'transit' ? 'logistics' : 'audit')"
            >
              <div class="stage-orbit">
                <span>{{ String(index + 1).padStart(2, '0') }}</span>
              </div>
              <strong>{{ stage.name }}</strong>
              <b>{{ fmtNumber(stage.count) }}</b>
              <em>{{ fmtPct(stage.conversion_rate) }}</em>
              <small v-if="stage.risk_count">{{ stage.risk_count }} 项关注</small>
              <small v-else>节点稳定</small>
            </button>
          </div>
          <div class="pulse-foot">
            <span><i class="stable"></i> 正常流转</span>
            <span><i class="risk"></i> 存在阻塞或待办</span>
            <button type="button" @click="navigate('audit')">查看完整证据链 →</button>
          </div>
        </article>

        <aside class="panel risk-panel">
          <div class="panel-heading">
            <div><p>REGULATORY FOCUS</p><h2>监管关注</h2></div>
            <button type="button" @click="navigate('alerts')">全部风险</button>
          </div>
          <div v-if="topRisks.length" class="risk-list">
            <button
              v-for="(risk, index) in topRisks"
              :key="risk.key"
              type="button"
              :class="`level-${risk.level}`"
              @click="navigate(risk.module)"
            >
              <span class="risk-rank">0{{ index + 1 }}</span>
              <div>
                <p><strong>{{ risk.label }}</strong><em>{{ risk.level_label }}</em></p>
                <span>{{ risk.affected }}</span>
                <small>最长持续 {{ fmtDuration(risk.duration_hours) }}</small>
              </div>
              <b>{{ fmtNumber(risk.count) }}</b>
            </button>
          </div>
          <div v-else class="all-clear">
            <span>ALL CLEAR</span>
            <strong>当前无待处置事项</strong>
          </div>
        </aside>
      </section>

      <section class="analytics-grid">
        <article class="panel trend-panel">
          <div class="panel-heading">
            <div><p>OPERATING SIGNAL</p><h2>运行趋势</h2></div>
            <span>全局周期 · {{ periodDays }}D</span>
          </div>
          <div ref="trendRef" class="trend-chart"></div>
        </article>

        <article class="panel region-panel">
          <div class="panel-heading">
            <div><p>REGIONAL EXPOSURE</p><h2>区域运行排名</h2></div>
            <button type="button" @click="navigate('beijing-map')">地图视图</button>
          </div>
          <div class="ranking-list">
            <button v-for="(region, index) in regions" :key="region.name" type="button" @click="navigate('beijing-map')">
              <span>{{ index + 1 }}</span>
              <div><strong>{{ region.name }}</strong><i :style="{ width: `${Math.max(8, region.orders / Math.max(...regions.map((r) => r.orders), 1) * 100)}%` }"></i></div>
              <em>{{ region.orders }} 单</em>
              <b :class="{ risk: region.risks }">{{ region.risks ? `${region.risks} 风险` : '稳定' }}</b>
            </button>
            <div v-if="!regions.length" class="empty-inline">暂无区域数据</div>
          </div>
        </article>

        <article class="panel mix-panel">
          <div class="panel-heading">
            <div><p>QUALITY & SETTLEMENT</p><h2>质检与结算</h2></div>
          </div>
          <div class="mix-body">
            <div class="mix-chart-wrap">
              <div ref="mixRef" class="mix-chart"></div>
              <div><strong>{{ fmtPct((Number(quality.coverage_rate ?? quality.approval_rate ?? 0) + Number(settlement.settlement_rate || 0)) / 2) }}</strong><span>综合完成</span></div>
            </div>
            <div class="mix-stats">
              <button type="button" @click="navigate('audit')"><span>质检覆盖率</span><strong>{{ fmtPct(quality.coverage_rate ?? quality.approval_rate) }}</strong><em>{{ quality.missing ?? quality.pending ?? 0 }} 缺报告</em></button>
              <button type="button" @click="navigate('audit')"><span>账单结算率</span><strong>{{ fmtPct(settlement.settlement_rate) }}</strong><em>{{ settlement.pending || 0 }} 待结</em></button>
            </div>
          </div>
        </article>
      </section>

      <section class="section-intro">
        <div><p>SUBJECT OPERATING GRAPH</p><h2>主体运营图谱</h2></div>
        <span>配送商与供货商的规模、履约和风险对照</span>
      </section>

      <section class="subject-grid">
        <article class="panel subject-panel delivery-panel">
          <div class="panel-heading">
            <div><p>DELIVERY PERFORMANCE</p><h2>配送商综合排名</h2></div>
            <div class="metric-switch">
              <button type="button" :class="{ active: deliveryMetric === 'orders' }" @click="switchDeliveryMetric('orders')">订单量</button>
              <button type="button" :class="{ active: deliveryMetric === 'gmv' }" @click="switchDeliveryMetric('gmv')">采购额</button>
            </div>
          </div>
          <div v-if="deliveryRankings.length" ref="deliveryRef" class="insight-chart"></div>
          <div v-else class="chart-empty">当前周期暂无配送商数据</div>
        </article>

        <article class="panel subject-panel">
          <div class="panel-heading">
            <div><p>SUPPLIER QUADRANT</p><h2>供货商履约象限</h2></div>
            <span>{{ supplierPerformance.length >= 8 ? '规模 × 履约 × 风险' : '主体较少，按风险排序' }}</span>
          </div>
          <div v-if="supplierPerformance.length" ref="supplierRef" class="insight-chart"></div>
          <div v-else class="chart-empty">当前周期暂无供货商数据</div>
        </article>
      </section>

      <section class="section-intro">
        <div><p>SUPPLY & DEMAND INTELLIGENCE</p><h2>供需结构洞察</h2></div>
        <span>商品结构、学校贡献与主体协作集中度</span>
      </section>

      <section class="structure-grid">
        <article class="panel structure-panel">
          <div class="panel-heading">
            <div><p>CATEGORY COMPOSITION</p><h2>商品分类结构</h2></div>
            <span>面积代表采购额</span>
          </div>
          <div v-if="categoryMix.length" ref="categoryRef" class="structure-chart"></div>
          <div v-else class="chart-empty">当前周期暂无商品分类数据</div>
        </article>

        <article class="panel structure-panel">
          <div class="panel-heading">
            <div><p>SCHOOL CONTRIBUTION</p><h2>学校采购排名</h2></div>
            <span>学校汇总 · 点击查看食堂</span>
          </div>
          <div
            v-if="clientRankings.length"
            ref="clientRef"
            class="structure-chart school-ranking-chart"
            :style="{ height: `${Math.max(330, clientRankings.length * 48 + 36)}px` }"
          ></div>
          <div v-else class="chart-empty">当前周期暂无学校数据</div>
        </article>

        <article class="panel matrix-panel">
          <div class="panel-heading">
            <div>
              <p>{{ matrixUsesHeatmap ? 'DELIVERY × SCHOOL MATRIX' : 'SCHOOL CONCENTRATION' }}</p>
              <h2>{{ matrixUsesHeatmap ? '配送商与学校协作热力' : '学校订单集中度' }}</h2>
            </div>
            <span>学校汇总 · 点击查看食堂</span>
          </div>
          <div
            v-if="deliveryClientMatrix.deliveries.length && deliveryClientMatrix.clients.length"
            ref="matrixRef"
            class="matrix-chart"
          ></div>
          <div v-else class="chart-empty">当前周期暂无可构建的协作矩阵</div>
        </article>
      </section>

      <section class="bottom-grid">
        <article class="panel supplier-panel">
          <div class="panel-heading">
            <div><p>SUPPLIER WATCH</p><h2>供应商风险观察</h2></div>
            <span>按异常与缺质检报告排序</span>
          </div>
          <div class="supplier-stream">
            <button v-for="supplier in suppliers" :key="supplier.supplier_id" type="button" @click="navigate('audit')">
              <i :class="{ active: supplier.risks }"></i>
              <div><strong>{{ supplier.name }}</strong><span>{{ supplier.allocations }} 条分单 · {{ supplier.pending_quality }} 条已出库待补传</span></div>
              <b :class="{ risk: supplier.risks }">{{ supplier.risks ? `${supplier.risks} 项` : '稳定' }}</b>
            </button>
            <div v-if="!suppliers.length" class="empty-inline">暂无供应商风险数据</div>
          </div>
        </article>

        <nav class="panel action-panel" aria-label="监管业务模块">
          <div class="panel-heading">
            <div><p>COMMAND ROUTES</p><h2>监管行动入口</h2></div>
            <span>从总览进入业务现场</span>
          </div>
          <div class="action-grid">
            <button v-for="item in navItems" :key="item.module" type="button" @click="navigate(item.module)">
              <span>{{ item.code }}</span>
              <div><strong>{{ item.label }}</strong><em>{{ item.text }}</em></div>
              <b>↗</b>
            </button>
          </div>
        </nav>
      </section>
    </template>

    <el-drawer
      v-model="schoolDrawerVisible"
      direction="rtl"
      size="min(760px, 94vw)"
      :with-header="false"
      modal-class="school-detail-overlay"
      class="school-detail-drawer"
    >
      <div v-if="activeSchool" class="school-detail">
        <header class="school-detail-header">
          <div>
            <p>SCHOOL PROCUREMENT DETAIL</p>
            <div class="school-title-line">
              <h2>{{ schoolNameParts(activeSchool.name).name }}</h2>
              <span v-if="schoolNameParts(activeSchool.name).demo">演示</span>
            </div>
            <small>学校汇总 · 食堂为实际下单与履约主体 · {{ periodDays }}D</small>
          </div>
          <button type="button" aria-label="关闭学校采购详情" @click="schoolDrawerVisible = false">×</button>
        </header>

        <section class="school-summary">
          <div><span>订单量</span><strong>{{ fmtNumber(activeSchool.orders) }}</strong><em>单</em></div>
          <div><span>采购额</span><strong>{{ fmtMoney(activeSchool.gmv) }}</strong></div>
          <div><span>送达率</span><strong>{{ fmtPct(activeSchool.fulfillment_rate) }}</strong></div>
          <div :class="{ risk: activeSchool.risks }"><span>异常数</span><strong>{{ fmtNumber(activeSchool.risks) }}</strong><em>项</em></div>
          <div><span>食堂数量</span><strong>{{ fmtNumber(activeCanteenCount) }}</strong><em>个</em></div>
        </section>

        <section class="canteen-section">
          <div class="canteen-heading">
            <div><p>CANTEEN FULFILLMENT</p><h3>下属食堂履约</h3></div>
            <span>按采购额排序</span>
          </div>
          <div v-if="activeCanteens.length" class="canteen-list">
            <article v-for="(canteen, index) in activeCanteens" :key="canteen.canteen_id ?? 'unassigned'">
              <span class="canteen-rank">{{ String(index + 1).padStart(2, '0') }}</span>
              <div class="canteen-main">
                <div class="canteen-name">
                  <strong>{{ canteen.name }}</strong>
                  <i v-if="canteen.canteen_id == null">历史归档</i>
                </div>
                <p :title="canteen.address || '暂无地址'">{{ canteen.address || '暂无地址信息' }}</p>
                <div class="canteen-metrics">
                  <span>订单 <b>{{ fmtNumber(canteen.orders) }}</b></span>
                  <span>采购额 <b>{{ fmtMoney(canteen.gmv) }}</b></span>
                  <span>送达率 <b>{{ fmtPct(canteen.fulfillment_rate) }}</b></span>
                  <span :class="{ risk: canteen.risks }">异常率 <b>{{ fmtPct(canteen.abnormal_rate) }}</b></span>
                </div>
              </div>
              <i class="canteen-signal" :class="{ risk: canteen.risks }"></i>
            </article>
          </div>
          <div v-else class="canteen-empty">当前周期暂无食堂订单</div>
        </section>

        <footer class="school-detail-footer">
          <span>数据与首页学校汇总使用相同北京时间口径</span>
          <button type="button" @click="openSchoolAudit">查看审计详情 ↗</button>
        </footer>
      </div>
    </el-drawer>
  </main>
</template>

<style scoped>
.executive-overview {
  --cyan: #00e5ff;
  --mint: #68fadd;
  --amber: #ffbd59;
  --coral: #ff7188;
  position: relative;
  min-height: 100vh;
  padding: 44px 32px 112px 50px;
  overflow: hidden;
  color: #e9fbff;
  background: #06101c;
  box-sizing: border-box;
}
.grid-field, .ambient { position: absolute; pointer-events: none; }
.grid-field { inset: 0; opacity: .28; background-image: linear-gradient(rgba(0,229,255,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(0,229,255,.035) 1px, transparent 1px); background-size: 48px 48px; mask-image: linear-gradient(to bottom, black, transparent 82%); }
.ambient { width: 760px; height: 760px; border-radius: 50%; filter: blur(90px); opacity: .12; }
.ambient-a { top: -420px; left: 12%; background: var(--cyan); }
.ambient-b { top: 30%; right: -520px; background: var(--mint); }
.overview-header, .conclusion, .telemetry, .primary-grid, .analytics-grid, .section-intro, .subject-grid, .structure-grid, .bottom-grid { position: relative; z-index: 1; max-width: 1920px; margin-left: auto; margin-right: auto; }
.overview-header { display: flex; justify-content: space-between; align-items: flex-end; min-height: 108px; padding: 0 8px 24px; border-bottom: 1px solid rgba(0,229,255,.15); }
.eyebrow, .panel-heading p, .conclusion p { margin: 0 0 8px; color: #4e9eb0; font: 800 10px/1.2 "JetBrains Mono", monospace; letter-spacing: .2em; }
.eyebrow i { display: inline-block; width: 6px; height: 6px; margin-right: 8px; border-radius: 50%; background: var(--mint); box-shadow: 0 0 12px var(--mint); }
h1 { margin: 0; font-size: clamp(34px, 3vw, 58px); line-height: 1; letter-spacing: -.04em; }
h1 span { margin-left: 10px; color: transparent; -webkit-text-stroke: 1px rgba(104,250,221,.72); }
.subtitle { margin: 12px 0 0; color: #66808f; font-size: 13px; }
.sync-block { display: grid; grid-template-columns: auto auto; gap: 5px 20px; align-items: center; min-width: 410px; padding-right: 120px; }
.sync-block span, .sync-block em { color: #456c7b; font: 700 9px/1 "JetBrains Mono", monospace; letter-spacing: .12em; }
.sync-block strong { grid-row: 2; color: #bfeef4; font: 500 18px/1 "JetBrains Mono", monospace; }
.sync-block em { grid-column: 2; grid-row: 2; font-style: normal; }
.sync-block button, .panel-heading button { border: 0; color: #80cbd5; background: transparent; cursor: pointer; font-size: 11px; }
.sync-block button { grid-column: 2; grid-row: 1; justify-self: end; }
.global-period { grid-column: 1 / -1; display: flex; justify-content: flex-end; gap: 5px; margin-top: 6px; }
.global-period button, .metric-switch button { padding: 6px 10px; border: 1px solid rgba(0,229,255,.16); border-radius: 6px; color: #5f8491; background: rgba(0,229,255,.025); font: 700 10px/1 "JetBrains Mono", monospace; }
.global-period button.active, .metric-switch button.active { color: #001b1e; border-color: var(--cyan); background: var(--cyan); box-shadow: 0 0 16px rgba(0,229,255,.16); }
.conclusion { display: grid; grid-template-columns: 52px 1fr auto; align-items: center; gap: 18px; margin-top: 20px; padding: 17px 20px; border: 1px solid rgba(0,229,255,.16); border-radius: 12px; background: linear-gradient(90deg, rgba(0,229,255,.09), rgba(7,21,34,.68) 46%, rgba(104,250,221,.04)); box-shadow: inset 0 1px rgba(255,255,255,.03); }
.conclusion h2 { margin: 0; font-size: clamp(15px, 1.25vw, 21px); font-weight: 600; }
.conclusion > strong { padding: 8px 14px; border: 1px solid currentColor; border-radius: 999px; color: var(--mint); font-size: 12px; }
.conclusion.tone-watch > strong { color: var(--amber); }
.conclusion.tone-risk > strong { color: var(--coral); }
.conclusion-signal { position: relative; width: 42px; height: 42px; display: grid; place-items: center; }
.conclusion-signal span, .conclusion-signal i, .conclusion-signal b { position: absolute; border: 1px solid rgba(104,250,221,.42); border-radius: 50%; animation: breathe 2.8s ease-in-out infinite; }
.conclusion-signal span { width: 38px; height: 38px; }.conclusion-signal i { width: 24px; height: 24px; animation-delay: -.7s; }.conclusion-signal b { width: 8px; height: 8px; border: 0; background: var(--mint); box-shadow: 0 0 14px var(--mint); }
.telemetry { display: grid; grid-template-columns: repeat(6, 1fr); margin-top: 18px; border-top: 1px solid rgba(0,229,255,.14); border-bottom: 1px solid rgba(0,229,255,.14); }
.telemetry-item { position: relative; min-width: 0; padding: 18px 18px 16px; text-align: left; border: 0; border-right: 1px solid rgba(0,229,255,.11); color: inherit; background: rgba(8,24,38,.36); cursor: pointer; overflow: hidden; }
.telemetry-item:last-child { border-right: 0; }
.telemetry-item > span, .telemetry-item small { display: block; color: #617d8b; font-size: 11px; }
.telemetry-item div { margin: 7px 0; white-space: nowrap; }
.telemetry-item strong { color: var(--cyan); font: 500 clamp(22px, 2vw, 34px)/1 "JetBrains Mono", monospace; }
.telemetry-item em { margin-left: 5px; color: #75909c; font-style: normal; font-size: 11px; }
.telemetry-item > i { position: absolute; right: 16px; top: 18px; width: 5px; height: 5px; border-radius: 50%; background: var(--cyan); box-shadow: 0 0 10px var(--cyan); }
.telemetry-item.tone-mint strong { color: var(--mint); }
.telemetry-item.tone-mint > i { background: var(--mint); }
.telemetry-item.tone-warn strong { color: var(--amber); }
.telemetry-item.tone-warn > i { background: var(--amber); }
.telemetry-item.tone-risk strong { color: var(--coral); }
.telemetry-item.tone-risk > i { background: var(--coral); }
.primary-grid { display: grid; grid-template-columns: minmax(0, 2.15fr) minmax(320px, .85fr); gap: 18px; margin-top: 20px; }
.analytics-grid { display: grid; grid-template-columns: 1.6fr .9fr .85fr; gap: 18px; margin-top: 18px; }
.bottom-grid { display: grid; grid-template-columns: 1fr 1.5fr; gap: 18px; margin-top: 18px; }
.section-intro { display: flex; justify-content: space-between; align-items: flex-end; margin-top: 28px; padding: 0 8px 10px; border-bottom: 1px solid rgba(0,229,255,.11); }
.section-intro p { margin: 0 0 7px; color: #4e9eb0; font: 800 9px/1 "JetBrains Mono", monospace; letter-spacing: .2em; }
.section-intro h2 { margin: 0; font-size: 21px; }
.section-intro > span { color: #506f7d; font-size: 10px; }
.subject-grid { display: grid; grid-template-columns: 1.08fr .92fr; gap: 18px; margin-top: 14px; }
.structure-grid { display: grid; grid-template-columns: .82fr 1.18fr; gap: 18px; margin-top: 14px; }
.matrix-panel { grid-column: 1 / -1; }
.subject-panel, .structure-panel { min-height: 390px; }
.metric-switch { display: flex; gap: 5px; }
.insight-chart, .structure-chart { width: 100%; height: 310px; }
.matrix-chart { width: 100%; height: 360px; }
.chart-empty { min-height: 285px; display: grid; place-items: center; color: #4f6e7b; font-size: 11px; }
.panel { border: 1px solid rgba(0,229,255,.16); border-radius: 16px; background: linear-gradient(145deg, rgba(10,27,42,.78), rgba(5,15,27,.88)); box-shadow: 0 18px 55px rgba(0,0,0,.22), inset 0 1px rgba(255,255,255,.025); overflow: hidden; }
.panel-heading { display: flex; justify-content: space-between; align-items: center; padding: 20px 24px 10px; }
.panel-heading h2 { margin: 0; font-size: 19px; }
.panel-heading > span { color: #526f7d; font-size: 10px; }
.lifecycle-panel { min-height: 370px; }
.pulse-canvas { position: relative; display: grid; grid-template-columns: repeat(7, 1fr); align-items: center; min-height: 245px; padding: 24px 28px 8px; }
.pulse-line { position: absolute; left: 8%; right: 8%; top: 91px; height: 1px; background: linear-gradient(90deg, transparent, var(--cyan) 15%, var(--mint) 78%, transparent); box-shadow: 0 0 12px rgba(0,229,255,.48); }
.pulse-line i { position: absolute; top: -3px; width: 42px; height: 7px; border-radius: 50%; background: #dffcff; filter: blur(3px); box-shadow: 0 0 20px var(--cyan); animation: pulseTravel 5s linear infinite; }
.pulse-stage { position: relative; z-index: 1; display: flex; flex-direction: column; align-items: center; border: 0; color: inherit; background: transparent; cursor: pointer; }
.stage-orbit { width: 54px; height: 54px; display: grid; place-items: center; margin-bottom: 15px; border: 1px solid rgba(0,229,255,.42); border-radius: 50%; background: #071827; box-shadow: 0 0 0 7px rgba(0,229,255,.035), 0 0 22px rgba(0,229,255,.12); }
.stage-orbit span { color: var(--cyan); font: 700 11px/1 "JetBrains Mono", monospace; }
.pulse-stage.risk .stage-orbit { border-color: rgba(255,113,136,.65); box-shadow: 0 0 0 7px rgba(255,113,136,.04), 0 0 22px rgba(255,113,136,.16); }
.pulse-stage.risk .stage-orbit span { color: var(--coral); }
.pulse-stage > strong { font-size: 13px; }.pulse-stage > b { margin: 8px 0 2px; font: 500 23px/1 "JetBrains Mono", monospace; }.pulse-stage > em { color: #5baec0; font: 700 10px/1 "JetBrains Mono", monospace; font-style: normal; }.pulse-stage > small { margin-top: 13px; color: #526f7d; font-size: 9px; }.pulse-stage.risk > small { color: #ff8398; }
.pulse-foot { display: flex; align-items: center; gap: 20px; padding: 0 24px 18px; color: #587583; font-size: 10px; }
.pulse-foot i { display: inline-block; width: 6px; height: 6px; margin-right: 5px; border-radius: 50%; }.pulse-foot i.stable { background: var(--mint); }.pulse-foot i.risk { background: var(--coral); }.pulse-foot button { margin-left: auto; border: 0; color: #7edfea; background: transparent; cursor: pointer; }
.risk-panel { min-height: 370px; }
.risk-list { padding: 4px 18px 18px; }
.risk-list > button { width: 100%; display: grid; grid-template-columns: 35px 1fr auto; gap: 12px; align-items: center; padding: 17px 8px; text-align: left; border: 0; border-bottom: 1px solid rgba(0,229,255,.09); color: inherit; background: transparent; cursor: pointer; }
.risk-rank { color: #335565; font: 700 11px/1 "JetBrains Mono", monospace; }
.risk-list p { display: flex; align-items: center; gap: 8px; margin: 0 0 5px; }.risk-list p strong { font-size: 14px; }.risk-list p em { padding: 3px 6px; border-radius: 4px; color: var(--amber); background: rgba(255,189,89,.1); font-size: 9px; font-style: normal; }.risk-list > button.level-high p em { color: var(--coral); background: rgba(255,113,136,.1); }
.risk-list div > span, .risk-list small { display: block; color: #66818e; font-size: 10px; line-height: 1.5; }.risk-list small { margin-top: 4px; color: #405d6b; }.risk-list > button > b { color: var(--amber); font: 500 27px/1 "JetBrains Mono", monospace; }.risk-list > button.level-high > b { color: var(--coral); }
.all-clear { min-height: 260px; display: grid; place-content: center; text-align: center; color: var(--mint); }.all-clear span { font: 800 11px/1 "JetBrains Mono", monospace; letter-spacing: .2em; }.all-clear strong { margin-top: 12px; font-size: 18px; }
.trend-chart { height: 245px; }
.period-switch { display: flex; gap: 4px; }.period-switch button { padding: 5px 8px; border: 1px solid rgba(0,229,255,.12); border-radius: 5px; color: #567785; background: transparent; }.period-switch button.active { color: #001b1e; background: var(--cyan); }
.ranking-list { padding: 5px 20px 18px; }
.ranking-list button { width: 100%; display: grid; grid-template-columns: 20px 1fr 42px 50px; gap: 8px; align-items: center; padding: 10px 0; border: 0; color: inherit; background: transparent; cursor: pointer; }
.ranking-list button > span { color: #395d6c; font: 700 10px/1 "JetBrains Mono", monospace; }.ranking-list button div strong { display: block; margin-bottom: 5px; text-align: left; font-size: 11px; }.ranking-list button div i { display: block; height: 2px; background: linear-gradient(90deg, var(--cyan), var(--mint)); box-shadow: 0 0 8px rgba(0,229,255,.4); }.ranking-list em { color: #70909d; font-size: 9px; font-style: normal; }.ranking-list b { color: var(--mint); font-size: 9px; }.ranking-list b.risk { color: var(--coral); }
.mix-body { display: grid; grid-template-columns: 1.1fr .9fr; align-items: center; padding: 0 18px 16px; }
.mix-chart-wrap { position: relative; height: 190px; }.mix-chart { width: 100%; height: 100%; }.mix-chart-wrap > div:last-child { position: absolute; inset: 0; display: grid; place-content: center; text-align: center; pointer-events: none; }.mix-chart-wrap strong { font: 500 20px/1 "JetBrains Mono", monospace; }.mix-chart-wrap span { margin-top: 5px; color: #567482; font-size: 9px; }
.mix-stats { display: grid; gap: 8px; }.mix-stats button { padding: 10px; text-align: left; border: 1px solid rgba(0,229,255,.1); border-radius: 8px; color: inherit; background: rgba(0,229,255,.025); cursor: pointer; }.mix-stats span, .mix-stats em { display: block; color: #5d7b88; font-size: 9px; font-style: normal; }.mix-stats strong { display: block; margin: 4px 0; color: var(--mint); font: 500 17px/1 "JetBrains Mono", monospace; }
.supplier-stream { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0 18px; padding: 4px 22px 18px; }
.supplier-stream button { display: grid; grid-template-columns: 9px 1fr auto; gap: 10px; align-items: center; min-width: 0; padding: 12px 0; text-align: left; border: 0; border-bottom: 1px solid rgba(0,229,255,.08); color: inherit; background: transparent; cursor: pointer; }.supplier-stream i { width: 5px; height: 5px; border-radius: 50%; background: var(--mint); box-shadow: 0 0 8px var(--mint); }.supplier-stream i.active { background: var(--coral); box-shadow: 0 0 8px var(--coral); }.supplier-stream strong, .supplier-stream span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.supplier-stream strong { font-size: 11px; }.supplier-stream span { margin-top: 4px; color: #557381; font-size: 9px; }.supplier-stream b { color: var(--mint); font-size: 10px; }.supplier-stream b.risk { color: var(--coral); }
.action-grid { display: grid; grid-template-columns: repeat(5, 1fr); padding: 5px 18px 18px; }
.action-grid button { display: grid; grid-template-columns: 38px 1fr auto; gap: 10px; align-items: center; min-width: 0; padding: 15px 12px; text-align: left; border: 0; border-right: 1px solid rgba(0,229,255,.1); color: inherit; background: rgba(0,229,255,.02); cursor: pointer; }.action-grid button:last-child { border-right: 0; }.action-grid > button > span { width: 34px; height: 34px; display: grid; place-items: center; border: 1px solid rgba(0,229,255,.28); border-radius: 8px; color: var(--cyan); font: 800 9px/1 "JetBrains Mono", monospace; }.action-grid strong, .action-grid em { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.action-grid strong { font-size: 11px; }.action-grid em { margin-top: 4px; color: #4f6c79; font-size: 8px; font-style: normal; }.action-grid b { color: #4d8d99; }
.empty-inline { padding: 30px 0; text-align: center; color: #4d6975; font-size: 11px; }
.error-state { position: relative; z-index: 2; min-height: 420px; display: grid; place-content: center; gap: 12px; text-align: center; }.error-state span { color: #78909b; }.error-state button { justify-self: center; padding: 8px 18px; border: 1px solid rgba(0,229,255,.4); border-radius: 999px; color: var(--cyan); background: transparent; cursor: pointer; }
:global(.school-detail-drawer.el-drawer) { z-index: 2500 !important; border-left: 1px solid rgba(0,229,255,.28); color: #e9fbff; background: #06101c; box-shadow: -24px 0 80px rgba(0,0,0,.55), -1px 0 28px rgba(0,229,255,.08); }
:global(.school-detail-overlay.el-overlay) { z-index: 2500 !important; }
:global(.school-detail-drawer .el-drawer__body) { padding: 0; overflow: hidden; }
.school-detail { height: 100%; display: grid; grid-template-rows: auto auto 1fr auto; overflow: hidden; background: radial-gradient(circle at 85% 8%, rgba(0,229,255,.11), transparent 30%), linear-gradient(145deg, rgba(10,29,44,.98), rgba(4,14,25,.99)); }
.school-detail-header { display: flex; justify-content: space-between; gap: 24px; padding: 30px 32px 23px; border-bottom: 1px solid rgba(0,229,255,.13); }
.school-detail-header p, .canteen-heading p { margin: 0 0 9px; color: #4e9eb0; font: 800 9px/1 "JetBrains Mono", monospace; letter-spacing: .2em; }
.school-title-line { display: flex; align-items: center; gap: 10px; }
.school-title-line h2 { margin: 0; font-size: 25px; line-height: 1.3; }
.school-title-line span, .canteen-name i { padding: 3px 7px; border: 1px solid rgba(104,250,221,.18); border-radius: 4px; color: #5e9ca5; background: rgba(104,250,221,.05); font-size: 9px; font-style: normal; white-space: nowrap; }
.school-detail-header small { display: block; margin-top: 10px; color: #587583; font-size: 10px; }
.school-detail-header > button { flex: 0 0 auto; width: 34px; height: 34px; border: 1px solid rgba(0,229,255,.17); border-radius: 50%; color: #75aab5; background: rgba(0,229,255,.035); cursor: pointer; font-size: 24px; line-height: 1; }
.school-summary { display: grid; grid-template-columns: repeat(5, 1fr); border-bottom: 1px solid rgba(0,229,255,.12); background: rgba(0,229,255,.025); }
.school-summary > div { min-width: 0; padding: 18px 16px; border-right: 1px solid rgba(0,229,255,.09); }
.school-summary > div:last-child { border-right: 0; }
.school-summary span { display: block; margin-bottom: 8px; color: #5c7b89; font-size: 9px; }
.school-summary strong { color: #68fadd; font: 500 18px/1 "JetBrains Mono", monospace; }
.school-summary em { margin-left: 4px; color: #668692; font-size: 9px; font-style: normal; }
.school-summary .risk strong { color: #ff7188; }
.canteen-section { min-height: 0; display: grid; grid-template-rows: auto 1fr; padding: 24px 28px 8px; overflow: hidden; }
.canteen-heading { display: flex; justify-content: space-between; align-items: flex-end; padding: 0 4px 14px; }
.canteen-heading h3 { margin: 0; font-size: 18px; }
.canteen-heading > span { color: #4f6e7b; font-size: 9px; }
.canteen-list { overflow-y: auto; padding-right: 6px; scrollbar-width: thin; scrollbar-color: rgba(0,229,255,.2) transparent; }
.canteen-list article { position: relative; display: grid; grid-template-columns: 38px 1fr 12px; gap: 12px; align-items: start; padding: 18px 8px; border-top: 1px solid rgba(0,229,255,.09); }
.canteen-rank { padding-top: 3px; color: #355c6b; font: 700 10px/1 "JetBrains Mono", monospace; }
.canteen-main { min-width: 0; }
.canteen-name { display: flex; align-items: flex-start; gap: 8px; }
.canteen-name strong { color: #dff8fb; font-size: 14px; line-height: 1.45; overflow-wrap: anywhere; }
.canteen-name i { margin-top: 1px; color: #ffbd59; border-color: rgba(255,189,89,.2); background: rgba(255,189,89,.06); }
.canteen-main > p { max-width: 560px; display: -webkit-box; margin: 6px 0 13px; overflow: hidden; color: #577482; font-size: 10px; line-height: 1.55; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.canteen-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.canteen-metrics span { padding: 8px 9px; border: 1px solid rgba(0,229,255,.08); border-radius: 6px; color: #587784; background: rgba(0,229,255,.02); font-size: 9px; white-space: nowrap; }
.canteen-metrics b { display: block; margin-top: 5px; color: #aeeef2; font: 600 11px/1 "JetBrains Mono", monospace; }
.canteen-metrics span.risk b { color: #ff7188; }
.canteen-signal { width: 6px; height: 6px; margin-top: 7px; border-radius: 50%; background: #68fadd; box-shadow: 0 0 10px #68fadd; }
.canteen-signal.risk { background: #ff7188; box-shadow: 0 0 10px #ff7188; }
.canteen-empty { display: grid; place-items: center; color: #4d6975; font-size: 11px; }
.school-detail-footer { display: flex; justify-content: space-between; align-items: center; gap: 20px; padding: 17px 32px 22px; border-top: 1px solid rgba(0,229,255,.12); background: rgba(3,12,21,.72); }
.school-detail-footer span { color: #4c6976; font-size: 9px; }
.school-detail-footer button { padding: 10px 16px; border: 1px solid rgba(0,229,255,.35); border-radius: 7px; color: #bffcff; background: linear-gradient(90deg, rgba(0,229,255,.12), rgba(104,250,221,.08)); cursor: pointer; font-size: 11px; }
@keyframes pulseTravel { from { left: 0; } to { left: calc(100% - 42px); } }
@keyframes breathe { 50% { transform: scale(1.12); opacity: .5; } }
@media (max-width: 1366px) {
  .executive-overview { padding: 34px 24px 105px 36px; }
  .telemetry-item { padding-left: 12px; padding-right: 10px; }
  .primary-grid { grid-template-columns: minmax(0, 1.8fr) minmax(290px, .8fr); }
  .analytics-grid { grid-template-columns: 1.35fr .85fr; }
  .subject-grid, .structure-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .mix-panel { grid-column: 1 / -1; }
  .mix-body { grid-template-columns: 220px 1fr; }
  .mix-stats { grid-template-columns: repeat(2, 1fr); }
  .action-grid { grid-template-columns: repeat(3, 1fr); }
  .action-grid button:nth-child(3) { border-right: 0; }
}
@media (max-width: 980px) {
  .overview-header { align-items: flex-start; }.sync-block { min-width: 0; padding-right: 0; }
  .telemetry { grid-template-columns: repeat(3, 1fr); }.telemetry-item:nth-child(3) { border-right: 0; }
  .primary-grid, .subject-grid, .structure-grid, .bottom-grid { grid-template-columns: 1fr; }
  .matrix-panel { grid-column: auto; }
  .pulse-canvas { overflow-x: auto; grid-template-columns: repeat(7, minmax(110px, 1fr)); }
  .analytics-grid { grid-template-columns: 1fr; }.mix-panel { grid-column: auto; }
}
@media (max-width: 720px) {
  .overview-header, .section-intro { display: grid; gap: 18px; }
  .sync-block { width: 100%; grid-template-columns: 1fr auto; }
  .section-intro > span { line-height: 1.5; }
  .insight-chart, .structure-chart, .matrix-chart { height: 300px; }
  .school-summary { grid-template-columns: repeat(2, 1fr); }
  .school-summary > div { border-bottom: 1px solid rgba(0,229,255,.09); }
  .canteen-metrics { grid-template-columns: repeat(2, 1fr); }
  .school-detail-header, .school-detail-footer { padding-left: 20px; padding-right: 20px; }
  .canteen-section { padding-left: 16px; padding-right: 16px; }
}
@media (prefers-reduced-motion: reduce) {
  .pulse-line i, .conclusion-signal span, .conclusion-signal i { animation: none; }
}
</style>
