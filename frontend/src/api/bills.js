import http from './index'

export const listBillsApi = () => http.get('/bills')
export const listBillingCyclesApi = () => http.get('/bills/cycles')
export const listBillingStatementsApi = () => http.get('/bills/statements')
export const generateDemoBillingStatementsApi = () => http.post('/bills/demo/generate')
export const createBillingCycleApi = (payload) => http.post('/bills/cycles', payload)
export const confirmBillingCycleApi = (id) => http.post(`/bills/cycles/${id}/confirm`)
export const clearBillingTestingApi = () => http.delete('/bills/testing/clear')
export const confirmBillingStatementApi = (id, payload = {}) => http.post(`/bills/statements/${id}/confirm`, payload)
export const settleBillingStatementApi = (id, payload) => http.post(`/bills/statements/${id}/settle`, payload)
