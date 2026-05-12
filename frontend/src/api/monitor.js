import http from './index'

export const monitorDashboardApi = () => http.get('/monitor/dashboard')
export const monitorNeuralOverviewApi = () => http.get('/monitor/neural/overview')
export const monitorNeuralLogisticsApi = () => http.get('/monitor/neural/logistics')
export const monitorNeuralMiningApi = () => http.get('/monitor/neural/mining')
export const monitorOrdersApi = (params) => http.get('/monitor/orders', { params })
export const monitorLogisticsApi = () => http.get('/monitor/logistics')
export const monitorAlertsApi = (params) => http.get('/monitor/alerts', { params })
export const closeMonitorAlertApi = (id) => http.put(`/monitor/alerts/${id}/close`)
export const monitorReportsApi = (params) => http.get('/monitor/reports', { params })
export const monitorRoutePlanningShowcaseApi = () => http.get('/monitor/route-planning-showcase')
