import http from './index'

export const factoryOrdersApi = (params) => http.get('/factory/orders', { params })
export const factoryOrderDetailApi = (id) => http.get(`/factory/orders/${id}`)
