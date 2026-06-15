import http from './index'

// 这些聚合接口涉及 DISTINCT / GROUP BY 全扫，慢补正在写入时尤其慢，给单独的更宽松超时
const SLOW_AGG_TIMEOUT = 45000

export const getAnalyticsDates = () => http.get('/xinfadi/analytics/dates', { timeout: SLOW_AGG_TIMEOUT })

export const getMarketSentiment = () => http.get('/xinfadi/analytics/sentiment', { timeout: SLOW_AGG_TIMEOUT })

export const getProductHints = (params = {}) =>
  http.get('/xinfadi/analytics/products', { params, timeout: SLOW_AGG_TIMEOUT })

export const getTimeseries = (params = {}) =>
  http.get('/xinfadi/analytics/timeseries', {
    timeout: SLOW_AGG_TIMEOUT,
    params: {
      start_date: params.start_date || '',
      end_date: params.end_date || '',
      prod_names: Array.isArray(params.prod_names) ? params.prod_names.join(',') : params.prod_names || '',
      cat1: params.cat1 || '',
      days: params.days || 30,
    },
  })

export const postBackfill = (body) => http.post('/xinfadi/backfill', body)

export const getBackfillStatus = () => http.get('/xinfadi/backfill/status')

export const postBackfillDismiss = () => http.post('/xinfadi/backfill/dismiss')

export const getForecastOverview = (params = {}) =>
  http.get('/xinfadi/predict/overview', {
    params: {
      q: params.q || '',
      page: params.page || 1,
      page_size: params.page_size ?? 50,
      sort_by: params.sort_by || 'updated_at',
      sort_order: params.sort_order || 'desc',
      only_trainable: !!params.only_trainable,
      only_usable: !!params.only_usable,
    },
  })

export const getForecastPredict = (params = {}) =>
  http.get('/xinfadi/predict', {
    params: {
      product: params.product,
      days: params.days || 30,
    },
  })

export const getForecastTrainStatus = (product) => http.get('/xinfadi/predict/train-status', { params: { product } })

export const postForecastRetrain = (product) =>
  http.post('/xinfadi/predict/retrain', null, {
    params: { product },
    timeout: 15000,
  })

export const postBatchRetrainAll = (body = {}) =>
  http.post('/xinfadi/predict/retrain-all', body, { timeout: 20000 })

export const getBatchRetrainStatus = () => http.get('/xinfadi/predict/retrain-all/status')

export const getForecastFactors = (product) => http.get('/xinfadi/predict/factors', { params: { product } })

export const getForecastAnalysis = (product) => http.get('/xinfadi/predict/analysis', { params: { product } })

export const getForecastAccuracy = (product) => http.get('/xinfadi/predict/accuracy', { params: { product } })
