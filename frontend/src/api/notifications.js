import http from './index'

export const listNotificationsApi = (params) => http.get('/notifications', { params })
export const markNotificationsReadApi = (payload) => http.post('/notifications/read', payload)
export const markNotificationReadApi = (id) => http.post(`/notifications/read/${id}`)
