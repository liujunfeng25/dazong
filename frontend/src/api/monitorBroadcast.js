import http from './index'

export const monitorBroadcastOverviewApi = () => http.get('/monitor/neural/broadcast')
export const monitorBroadcastTargetsApi = (params = {}) =>
  http.get('/monitor/broadcast/targets', { params })
export const createMonitorBroadcastApi = (payload) => http.post('/monitor/broadcasts', payload)
export const listMonitorBroadcastsApi = (params = {}) => http.get('/monitor/broadcasts', { params })
export const listMonitorBroadcastRecipientsApi = (id) =>
  http.get(`/monitor/broadcasts/${id}/recipients`)
