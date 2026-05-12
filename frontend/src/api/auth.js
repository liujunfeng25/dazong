import http from './index'

export const loginApi = (payload) => http.post('/auth/login', payload)
export const meApi = () => http.get('/auth/me')
export const changePasswordApi = (payload) => http.post('/auth/change-password', payload)
