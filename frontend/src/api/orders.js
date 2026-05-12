import http from './index'

export const createOrderApi = (payload) => http.post('/orders', payload)
export const orderMetaApi = (params) => http.get('/orders/meta', { params })
export const searchOrderProductsApi = (params) => http.get('/orders/products/search', { params })
export const orderProductsByIdsApi = (params) => http.get('/orders/products/by-ids', { params })
export const parseOrderByOcrApi = (formData) =>
  http.post('/ocr/parse-order', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
export const ocrEngineStatusApi = () => http.get('/ocr/engine')
export const parseOrderByVoiceApi = (payload) => http.post('/voice/parse-order', payload)
export const listOrdersApi = (params) => http.get('/orders', { params })
export const orderDetailApi = (id) => http.get(`/orders/${id}`)
export const cancelOrderApi = (id) => http.put(`/orders/${id}/cancel`)

export const sortStartApi = (id) => http.post(`/orders/${id}/sort-start`)
export const sortDoneApi = (id) => http.post(`/orders/${id}/sort-done`)
export const printLabelApi = (id) => http.post(`/orders/${id}/print-label`)
export const printAllocationLabelApi = (id, allocationId) =>
  http.post(`/orders/${id}/print-allocation-label/${allocationId}`)
export const shipOrderApi = (id) => http.post(`/orders/${id}/ship`)
export const pickupOrderApi = (id) => http.post(`/orders/${id}/pickup`)
export const deliverOrderApi = (id) => http.post(`/orders/${id}/deliver`)
export const receiveOrderApi = (id) => http.post(`/orders/${id}/receive`)
export const reviewOrderApi = (id, payload) => http.post(`/orders/${id}/review`, payload)
export const settleOrderApi = (id) => http.post(`/orders/${id}/settle`)
