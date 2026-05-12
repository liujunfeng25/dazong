import http from './index'

export const listQualityReportsApi = () => http.get('/quality-reports')

export const uploadQualityReportApi = (formData) =>
  http.post('/quality-reports', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

export const uploadQualityReportByAllocationApi = (formData) =>
  http.post('/quality-reports/by-allocation', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

export const listQualityReportsByOrderApi = (orderId) =>
  http.get(`/quality-reports/by-order/${orderId}`)
