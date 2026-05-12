import http from './index'

/** 路线规划/分单用订单池：须传创建日期范围，否则后端默认仅查 UTC「当天」会经常出现无数据 */
const _localYmd = (d) => {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/**
 * 配送端订单池（智能分单 / 智能排线共用）。
 * @param recentDays 未指定 expectedDeliveryYmd 时按创建日回溯天数
 * @param expectedDeliveryYmd 指定则按客户配送日筛选（YYYY-MM-DD）
 * @param options.statuses 状态列表；默认 ['下单']（与智能分单一致）；智能排线传 ['下单','配货']
 */
export const deliveryOrderPoolApi = (recentDays = 120, expectedDeliveryYmd = null, options = {}) => {
  const statuses = Array.isArray(options.statuses) && options.statuses.length ? options.statuses : ['下单']
  const params = {}
  if (statuses.length === 1) {
    params.status = statuses[0]
  } else {
    params.status_in = statuses.join(',')
  }
  if (expectedDeliveryYmd) {
    params.expected_delivery_date = expectedDeliveryYmd
  } else {
    const end = new Date()
    const start = new Date()
    start.setDate(start.getDate() - (recentDays - 1))
    params.created_date_start = _localYmd(start)
    params.created_date_end = _localYmd(end)
  }
  return http.get('/delivery/orders', { params })
}
export const smartSplitApi = (payload) => http.post('/delivery/smart-split', payload)
export const smartSplitPreviewApi = (payload) => http.post('/delivery/smart-split/preview', payload)
export const smartSplitCommitApi = (payload) => http.post('/delivery/smart-split/commit', payload)
export const smartSplitDetailApi = (orderId) => http.get(`/delivery/smart-split/${orderId}`)
export const routePlanApi = (payload) => http.post('/delivery/route-plan', payload)

export const listDeliveryGeofencesApi = () => http.get('/delivery/geofences')
export const createDeliveryGeofenceApi = (payload) => http.post('/delivery/geofences', payload)
export const updateDeliveryGeofenceApi = (id, payload) => http.put(`/delivery/geofences/${id}`, payload)
export const deleteDeliveryGeofenceApi = (id) => http.delete(`/delivery/geofences/${id}`)
export const seedReceivingGeofencesApi = (payload) =>
  http.post('/delivery/geofences/seed-receiving-from-contracts', payload ?? {})
export const listDeliverySuppliersApi = () => http.get('/delivery/suppliers')
export const listDeliverySupplierQuotesApi = (supplierId, params) =>
  http.get(`/delivery/suppliers/${supplierId}/product-quotes`, { params })
export const listDeliverySupplierQuoteFilterCategoriesApi = () =>
  http.get('/delivery/suppliers/quote-filter-categories')
export const searchSupplierAddressTipsApi = (params) => http.get('/delivery/suppliers/address-tips', { params })
export const createDeliverySupplierApi = (payload) => http.post('/delivery/suppliers', payload)
export const updateDeliverySupplierApi = (id, payload) => http.put(`/delivery/suppliers/${id}`, payload)
export const deleteDeliverySupplierApi = (id) => http.delete(`/delivery/suppliers/${id}`)

export const listDeliveryVehiclesApi = () => http.get('/delivery/vehicles')
export const getBeijingVehicleRestrictionApi = (planDateYmd) =>
  http.get('/delivery/vehicles/restriction/beijing', {
    params: planDateYmd ? { plan_date: planDateYmd } : {},
  })
export const getBeijingWeatherApi = () => http.get('/delivery/weather/beijing')
export const createDeliveryVehicleApi = (payload) => http.post('/delivery/vehicles', payload)
export const updateDeliveryVehicleApi = (id, payload) => http.put(`/delivery/vehicles/${id}`, payload)
export const deleteDeliveryVehicleApi = (id) => http.delete(`/delivery/vehicles/${id}`)
export const getVehicleLocationApi = (vehicleId) => http.get(`/delivery/vehicles/${vehicleId}/location`)

export const listDeliveryDevicesApi = (params) => http.get('/delivery/devices', { params })
export const createDeliveryDeviceApi = (payload) => http.post('/delivery/devices', payload)
export const updateDeliveryDeviceApi = (id, payload) => http.put(`/delivery/devices/${id}`, payload)
export const deleteDeliveryDeviceApi = (id) => http.delete(`/delivery/devices/${id}`)
export const refreshBeidouDevicesApi = () => http.post('/delivery/devices/refresh/beidou')
export const refreshYs7DevicesApi = () => http.post('/delivery/devices/refresh/ys7')
export const getDeliveryCameraLiveUrlApi = (id) => http.get(`/delivery/devices/${id}/camera-live-url`)

export const listVehicleBindingsApi = (vehicleId) => http.get(`/delivery/vehicles/${vehicleId}/bindings`)
export const createVehicleBindingApi = (vehicleId, payload) =>
  http.post(`/delivery/vehicles/${vehicleId}/bindings`, payload)
export const deleteVehicleBindingApi = (vehicleId, bindingId) =>
  http.delete(`/delivery/vehicles/${vehicleId}/bindings/${bindingId}`)

export const listDeliveryComplaintsApi = (params) => http.get('/delivery/complaints', { params })
export const respondDeliveryComplaintApi = (ticketId, payload) =>
  http.post(`/delivery/complaints/${ticketId}/respond`, payload)
