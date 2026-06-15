import http from './index'

// 中农价格网行情：聚合接口涉及大表 DISTINCT / GROUP BY，给更宽松的超时
const SLOW_AGG_TIMEOUT = 45000
// 测试登录：后端线程池硬超时 75s，前端略放宽
const CREDENTIAL_TEST_TIMEOUT = 90000

// 剔除空值键：整型参数（district_id/cate_id）留空时若发送 '' 会被后端按 int 解析报 422，
// 字符串参数留空后端也有默认值，统一不发送即可。
const prune = (obj) =>
  Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== '' && v !== null && v !== undefined))

export const getZgFilters = () => http.get('/zgncpjgw/analytics/filters', { timeout: SLOW_AGG_TIMEOUT })

export const getZgOverview = (params = {}) =>
  http.get('/zgncpjgw/analytics/overview', {
    timeout: SLOW_AGG_TIMEOUT,
    params: prune({
      date: params.date || '',
      district_id: params.district_id ?? '',
      cate_id: params.cate_id ?? '',
      scate: params.scate || '',
    }),
  })

export const getZgProductHints = (params = {}) =>
  http.get('/zgncpjgw/analytics/products', {
    timeout: SLOW_AGG_TIMEOUT,
    params: { q: params.q || '', limit: params.limit || 50 },
  })

export const getZgTimeseries = (params = {}) =>
  http.get('/zgncpjgw/analytics/timeseries', {
    timeout: SLOW_AGG_TIMEOUT,
    params: prune({
      sku_keys: Array.isArray(params.sku_keys) ? params.sku_keys.join('\n') : params.sku_keys || '',
      district_id: params.district_id ?? '',
      start_date: params.start_date || '',
      end_date: params.end_date || '',
      days: params.days || 30,
    }),
  })

export const getZgCompare = (params = {}) =>
  http.get('/zgncpjgw/analytics/compare', {
    timeout: SLOW_AGG_TIMEOUT,
    params: { sku_key: params.sku_key || '', date: params.date || '' },
  })

export const getZgIndex = () => http.get('/zgncpjgw/analytics/index', { timeout: SLOW_AGG_TIMEOUT })

export const getZgQuality = () => http.get('/zgncpjgw/analytics/quality', { timeout: SLOW_AGG_TIMEOUT })

export const getZgSuspiciousSkus = (params = {}) =>
  http.get('/zgncpjgw/analytics/quality/suspicious-skus', {
    timeout: SLOW_AGG_TIMEOUT,
    params: prune({ date: params.date || '', limit: params.limit || 500 }),
  })

export const getZgQualityFlags = (params = {}) =>
  http.get('/zgncpjgw/analytics/quality/flags', {
    timeout: SLOW_AGG_TIMEOUT,
    params: prune({
      date: params.date || '',
      severity: params.severity || '',
      status: params.status || '',
      cate_id: params.cate_id ?? '',
      q: params.q || '',
      limit: params.limit || 200,
    }),
  })

export const postZgQualityFlagAction = (id, payload) =>
  http.post(`/zgncpjgw/analytics/quality/flags/${id}/action`, payload, { timeout: SLOW_AGG_TIMEOUT })

export const postZgQualityFlagVerifyRecrawl = (id) =>
  http.post(`/zgncpjgw/analytics/quality/flags/${id}/verify-recrawl`, {}, { timeout: SLOW_AGG_TIMEOUT })

export const getZgMap = (params = {}) =>
  http.get('/zgncpjgw/analytics/map', {
    timeout: SLOW_AGG_TIMEOUT,
    params: prune({
      sku_key: params.sku_key || '',
      cate_id: params.cate_id ?? '',
      metric: params.metric || 'level',
      date: params.date || '',
    }),
  })

export const getZgMovers = (params = {}) =>
  http.get('/zgncpjgw/analytics/movers', {
    timeout: SLOW_AGG_TIMEOUT,
    params: prune({
      window: params.window || 7,
      limit: params.limit || 12,
      cate_id: params.cate_id ?? '',
      scate: params.scate || '',
      district_id: params.district_id ?? '',
      quality_policy: params.quality_policy || 'strict',
    }),
  })

export const getZgChangeRatio = (params = {}) =>
  http.get('/zgncpjgw/analytics/change-ratio', {
    timeout: SLOW_AGG_TIMEOUT,
    params: prune({
      district_id: params.district_id ?? '',
      cate_id: params.cate_id ?? '',
      scate: params.scate || '',
      baseline_days: params.baseline_days ?? '',
    }),
  })

export const getZgChangeRanking = (params = {}) =>
  http.get('/zgncpjgw/analytics/change-ranking', {
    timeout: SLOW_AGG_TIMEOUT,
    params: prune({
      district_id: params.district_id ?? '',
      cate_id: params.cate_id ?? '',
      scate: params.scate || '',
      baseline_days: params.baseline_days || 3,
      limit: params.limit || 10,
    }),
  })

export const getZgSpread = (params = {}) =>
  http.get('/zgncpjgw/analytics/spread', {
    timeout: SLOW_AGG_TIMEOUT,
    params: prune({
      cate_id: params.cate_id ?? '',
      scate: params.scate || '',
      date: params.date || '',
      limit: params.limit || 12,
      quality_policy: params.quality_policy || 'strict',
      transport_cost_pct: params.transport_cost_pct ?? 8,
    }),
  })

export const getZgForecast = (params = {}) =>
  http.get('/zgncpjgw/analytics/forecast', {
    timeout: SLOW_AGG_TIMEOUT,
    params: prune({ sku_key: params.sku_key || '', district_id: params.district_id ?? '', days: params.days || 14 }),
  })

export const getZgForecastStatus = () => http.get('/zgncpjgw/analytics/forecast/status')

export const getZgHotSkus = () => http.get('/zgncpjgw/analytics/hot-skus', { timeout: SLOW_AGG_TIMEOUT })

export const putZgHotSkus = (body) => http.put('/zgncpjgw/analytics/hot-skus', body, { timeout: SLOW_AGG_TIMEOUT })

export const postZgForecastTrain = (params = {}) =>
  http.post('/zgncpjgw/analytics/forecast/train', null, {
    params: prune({
      sku_key: params.sku_key || '',
      district_id: params.district_id ?? '',
      scope_mode: params.scope_mode || params.scope || 'single_current',
    }),
  })

export const postZgBriefing = () => http.post('/zgncpjgw/analytics/briefing', null, { timeout: 90000 })

const DAILY_REPORT_TIMEOUT = 120000

export const postZgDailyReportJson = (body = {}) =>
  http.post('/zgncpjgw/analytics/daily-report', { format: 'json', ...body }, { timeout: DAILY_REPORT_TIMEOUT })

export const postZgDailyReportPdf = (body = {}) =>
  http.post(
    '/zgncpjgw/analytics/daily-report',
    { format: 'pdf', ...body },
    { timeout: DAILY_REPORT_TIMEOUT, responseType: 'blob' },
  )

export const postZgRebuild = () => http.post('/zgncpjgw/analytics/rebuild', null)

export const getZgRebuildStatus = () => http.get('/zgncpjgw/analytics/rebuild/status')

export const getZgBackfillPreview = (params = {}) =>
  http.get('/zgncpjgw/backfill/preview', {
    params: prune({ end_date: params.end_date || '' }),
  })

export const postZgBackfill = (body) => http.post('/zgncpjgw/backfill', body)

export const getZgBackfillStatus = () => http.get('/zgncpjgw/backfill/status')

export const getZgCredentials = () => http.get('/zgncpjgw/credentials')

export const putZgCredentials = (body) => http.put('/zgncpjgw/credentials', body)

export const postZgCredentialsTest = (body) =>
  http.post('/zgncpjgw/credentials/test', body || null, { timeout: CREDENTIAL_TEST_TIMEOUT })

export const getZgPrices = (params = {}) =>
  http.get('/zgncpjgw/prices', {
    timeout: SLOW_AGG_TIMEOUT,
    params: prune({
      date: params.date || '',
      start_date: params.start_date || '',
      end_date: params.end_date || '',
      district_id: params.district_id ?? '',
      cate_id: params.cate_id ?? '',
      scate: params.scate || '',
      goods_name: params.goods_name || '',
      sku_key: params.sku_key || '',
      page: params.page || 1,
      page_size: params.page_size || 20,
    }),
  })
