import http from './index'

export const uploadComplaintImageApi = (formData) =>
  http.post('/complaints/upload-image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

export const createComplaintApi = (payload) => http.post('/complaints', payload)

export const getOpenComplaintApi = (orderId) =>
  http.get(`/complaints/order/${orderId}/open`)
