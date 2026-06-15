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
 * @param options.excludeActiveDispatch 是否排除已在「同计划日」未完成车次中的订单
 * @param options.includeDispatchReadiness 是否返回调度保存门禁与分检/出库进度
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
  if (options.excludeActiveDispatch) params.exclude_active_dispatch = true
  if (options.includeDispatchReadiness) params.include_dispatch_readiness = true
  return http.get('/delivery/orders', { params })
}
export const deliveryWorkbenchApi = () => http.get('/delivery/workbench')
export const deliveryDashboardApi = () => http.get('/delivery/dashboard')
export const smartSplitApi = (payload) => http.post('/delivery/smart-split', payload)
export const smartSplitPreviewApi = (payload) => http.post('/delivery/smart-split/preview', payload)
export const smartSplitCommitApi = (payload) => http.post('/delivery/smart-split/commit', payload)
export const smartSplitDetailApi = (orderId) => http.get(`/delivery/smart-split/${orderId}`)
export const routePlanApi = (payload) => http.post('/delivery/route-plan', payload)
export const commitRoutePlanApi = (payload) => http.post('/delivery/route-plan/commit', payload)
export const dispatchPlanningSummaryApi = (planningDate) =>
  http.get('/delivery/dispatch-planning/summary', { params: { planning_date: planningDate } })
export const listDispatchTripsApi = (params) => http.get('/delivery/dispatch-trips', { params })
export const getDispatchTripApi = (id) => http.get(`/delivery/dispatch-trips/${id}`)
export const appendDispatchTripStopsApi = (tripId, payload) =>
  http.post(`/delivery/dispatch-trips/${tripId}/append-stops`, payload)
export const updateDispatchTripApi = (tripId, payload) =>
  http.patch(`/delivery/dispatch-trips/${tripId}`, payload)
export const departDispatchTripApi = (id) => http.post(`/delivery/dispatch-trips/${id}/depart`)
export const exceptionDepartDispatchTripApi = (id, payload) =>
  http.post(`/delivery/dispatch-trips/${id}/exception-depart`, payload)
export const cancelDispatchTripApi = (id, payload) => http.post(`/delivery/dispatch-trips/${id}/cancel`, payload)
export const markDispatchItemLoadedApi = (tripId, itemId, payload) =>
  http.post(`/delivery/dispatch-trips/${tripId}/items/${itemId}/load`, payload)
export const uploadDispatchExceptionPhotoApi = (tripId, formData) =>
  http.post(`/delivery/dispatch-trips/${tripId}/exception-photo`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
export const listDriverTripsTodayApi = (params) => http.get('/delivery/driver-trips/today', { params })
export const getDriverLoadingListApi = (tripId) => http.get(`/delivery/driver-trips/${tripId}/loading-list`)

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
export const postVehicleBeidouLocationApi = (vehicleId, payload) =>
  http.post(`/delivery/vehicles/${vehicleId}/beidou-location`, payload)
export const postVehicleBeidouHistoryTrackApi = (vehicleId, payload) =>
  http.post(`/delivery/vehicles/${vehicleId}/beidou-history-track`, payload)
export const deliveryFleetMonitorVehiclesApi = () => http.get('/delivery/fleet-monitor/vehicles')
export const deliveryFleetMonitorCameraLiveUrlApi = (id) =>
  http.get(`/delivery/fleet-monitor/cameras/${id}/live-url`)

export const listDeliveryDevicesApi = (params) => http.get('/delivery/devices', { params })
export const createDeliveryDeviceApi = (payload) => http.post('/delivery/devices', payload)
export const updateDeliveryDeviceApi = (id, payload) => http.put(`/delivery/devices/${id}`, payload)
export const deleteDeliveryDeviceApi = (id) => http.delete(`/delivery/devices/${id}`)
export const refreshBeidouDevicesApi = () => http.post('/delivery/devices/refresh/beidou')
export const refreshYs7DevicesApi = () => http.post('/delivery/devices/refresh/ys7')
export const getDeliveryCameraLiveUrlApi = (id) => http.get(`/delivery/devices/${id}/camera-live-url`)
export const postDeliveryCameraPtzApi = (id, payload) =>
  http.post(`/delivery/devices/${id}/camera-ptz`, payload)
export const postDeliveryFleetCameraPtzApi = (id, payload) =>
  http.post(`/delivery/fleet-monitor/cameras/${id}/camera-ptz`, payload)
export const postDeviceBeidouHistoryTrackApi = (deviceId, payload) =>
  http.post(`/delivery/devices/${deviceId}/beidou-history-track`, payload)
export const getDeviceBeidouLiveApi = (deviceId) =>
  http.get(`/delivery/devices/${deviceId}/beidou-live`)

export const listVehicleBindingsApi = (vehicleId) => http.get(`/delivery/vehicles/${vehicleId}/bindings`)
export const createVehicleBindingApi = (vehicleId, payload) =>
  http.post(`/delivery/vehicles/${vehicleId}/bindings`, payload)
export const deleteVehicleBindingApi = (vehicleId, bindingId) =>
  http.delete(`/delivery/vehicles/${vehicleId}/bindings/${bindingId}`)

export const listDeliveryComplaintsApi = (params) => http.get('/delivery/complaints', { params })
export const respondDeliveryComplaintApi = (ticketId, payload) =>
  http.post(`/delivery/complaints/${ticketId}/respond`, payload)

export const listDeliveryWarehousesApi = (params) => http.get('/delivery/warehouses', { params })
export const createDeliveryWarehouseApi = (payload) => http.post('/delivery/warehouses', payload)
export const updateDeliveryWarehouseApi = (id, payload) => http.put(`/delivery/warehouses/${id}`, payload)
export const deleteDeliveryWarehouseApi = (id) => http.delete(`/delivery/warehouses/${id}`)
export const searchDeliveryWarehouseAddressTipsApi = (params) =>
  http.get('/delivery/warehouses/address-tips', { params })
export const listDeliveryWarehouseBindingsApi = (warehouseId) =>
  http.get(`/delivery/warehouses/${warehouseId}/bindings`)
export const createDeliveryWarehouseBindingApi = (warehouseId, payload) =>
  http.post(`/delivery/warehouses/${warehouseId}/bindings`, payload)
export const deleteDeliveryWarehouseBindingApi = (warehouseId, bindingId) =>
  http.delete(`/delivery/warehouses/${warehouseId}/bindings/${bindingId}`)
export const deliveryFleetMonitorWarehousesApi = () => http.get('/delivery/fleet-monitor/warehouses')

export const listElitechDevicesApi = () => http.get('/delivery/warehouses/elitech/devices')
export const getWarehouseElitechApi = (warehouseId) => http.get(`/delivery/warehouses/${warehouseId}/elitech`)
export const bindWarehouseElitechApi = (warehouseId, payload) =>
  http.post(`/delivery/warehouses/${warehouseId}/elitech`, payload)
export const unbindWarehouseElitechApi = (warehouseId) =>
  http.delete(`/delivery/warehouses/${warehouseId}/elitech`)
export const getWarehouseElitechRealtimeApi = (warehouseId) =>
  http.get(`/delivery/warehouses/${warehouseId}/elitech/realtime`)
export const getWarehouseElitechRealtimeCurveApi = (warehouseId, params) =>
  http.get(`/delivery/warehouses/${warehouseId}/elitech/realtime-curve`, { params, timeout: 30000 })
export const getWarehouseElitechHistoryApi = (warehouseId, params) =>
  http.get(`/delivery/warehouses/${warehouseId}/elitech/history`, { params, timeout: 30000 })
export const getWarehouseElitechHistoryCurveApi = (warehouseId, params) =>
  http.get(`/delivery/warehouses/${warehouseId}/elitech/history-curve`, { params, timeout: 30000 })
export const getWarehouseElitechHistoryStatsApi = (warehouseId, params) =>
  http.get(`/delivery/warehouses/${warehouseId}/elitech/history-stats`, { params })
export const getWarehouseElitechWarningsApi = (warehouseId, params) =>
  http.get(`/delivery/warehouses/${warehouseId}/elitech/warnings`, { params })
