import http from './index'

export const listBillsApi = () => http.get('/bills')
export const listBillingCyclesApi = () => http.get('/bills/cycles')
export const listBillingStatementsApi = (params = {}) => http.get('/bills/statements', { params })
export const listBillingStatementsGroupedApi = (params = {}) => http.get('/bills/statements-grouped', { params })
export const getBillingOverviewApi = () => http.get('/bills/overview')
export const generateDemoBillingStatementsApi = () => http.post('/bills/demo/generate')
export const createBillingCycleApi = (payload) => http.post('/bills/cycles', payload)
export const confirmBillingCycleApi = (id) => http.post(`/bills/cycles/${id}/confirm`)
export const clearBillingTestingApi = () => http.delete('/bills/testing/clear')
export const confirmBillingStatementApi = (id, payload = {}) => http.post(`/bills/statements/${id}/confirm`, payload)
export const settleBillingStatementApi = (id, payload) => http.post(`/bills/statements/${id}/settle`, payload)
export const getOperationBillingStatementsApi = (params = {}) =>
  http.get('/bills/operation/statements', { params })
export const getOperationBillingStatementDetailApi = (id) =>
  http.get(`/bills/operation/statements/${id}/detail`)
export const previewBillingCycleApi = (payload) =>
  http.post('/bills/cycles/preview', payload)

// 定向账期规则（按 学校×食堂×配送商 / 配送商×供货商 颗粒化）
export const listTargetedCyclesApi = (params = {}) => http.get('/bills/cycles/targeted', { params })
export const createTargetedCycleApi = (payload) => http.post('/bills/cycles/targeted', payload)
export const updateTargetedCycleApi = (id, payload) => http.put(`/bills/cycles/targeted/${id}`, payload)
export const followGlobalTargetedCycleApi = (id) => http.post(`/bills/cycles/targeted/${id}/follow-global`)

// 对账单（月结合并单：按 对手方×账期 聚合）
export const listReconciliationsApi = (params = {}) => http.get('/bills/reconciliations', { params })
export const getReconciliationApi = (id) => http.get(`/bills/reconciliations/${id}`)
export const confirmReconciliationApi = (id, payload = {}) =>
  http.post(`/bills/reconciliations/${id}/confirm`, payload)
export const settleReconciliationApi = (id, payload = {}) =>
  http.post(`/bills/reconciliations/${id}/settle`, payload)
export const exportReconciliationApi = (id) =>
  http.get(`/bills/reconciliations/${id}/export`, { responseType: 'blob' })
