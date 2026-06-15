import http from './index'

export const monitorDashboardApi = () => http.get('/monitor/dashboard')
export const monitorNeuralOverviewApi = () => http.get('/monitor/neural/overview')
export const monitorExecutiveOverviewApi = (params) => http.get('/monitor/neural/executive-overview', { params })
export const monitorAuditChainApi = () => http.get('/monitor/neural/audit-chain')
export const monitorOrderAuditApi = (orderId) => http.get(`/monitor/neural/order-audit/${orderId}`)
export const monitorNeuralLogisticsApi = () => http.get('/monitor/neural/logistics')
export const monitorDispatchTripApi = (tripId) => http.get(`/monitor/dispatch-trips/${tripId}`)
export const monitorBeijingDemoVehiclesApi = () => http.get('/monitor/neural/beijing-demo/vehicles')
export const monitorNeuralMiningApi = () => http.get('/monitor/neural/mining')
export const monitorOrdersApi = (params) => http.get('/monitor/orders', { params })
export const monitorLogisticsApi = () => http.get('/monitor/logistics')
export const monitorAlertsApi = (params) => http.get('/monitor/alerts', { params })
export const closeMonitorAlertApi = (id) => http.put(`/monitor/alerts/${id}/close`)
export const monitorReportsApi = (params) => http.get('/monitor/reports', { params })
export const monitorRoutePlanningShowcaseApi = () => http.get('/monitor/route-planning-showcase')

export const monitorFleetMonitorVehiclesApi = () => http.get('/monitor/fleet-monitor/vehicles')
export const monitorFleetMonitorWarehousesApi = () => http.get('/monitor/fleet-monitor/warehouses')
export const monitorFleetMonitorCameraLiveUrlApi = (id) =>
  http.get(`/monitor/fleet-monitor/cameras/${id}/live-url`)
export const monitorFleetMonitorCameraPtzApi = (id, payload) =>
  http.post(`/monitor/fleet-monitor/cameras/${id}/camera-ptz`, payload)
export const monitorFleetMonitorVehicleHistoryTrackApi = (vehicleId, payload) =>
  http.post(`/monitor/fleet-monitor/vehicles/${vehicleId}/beidou-history-track`, payload)
