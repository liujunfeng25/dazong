import http from './index'

export const factoryHomeApi = () => http.get('/factory/home')
export const factoryOrdersApi = (params) => http.get('/factory/orders', { params })
export const factoryOrderDetailApi = (id) => http.get(`/factory/orders/${id}`)
