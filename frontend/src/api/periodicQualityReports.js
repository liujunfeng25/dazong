import http from './index'

export const listPeriodicReportProductsApi = () => http.get('/periodic-quality-reports/products')
export const listPeriodicQualityReportsApi = (params) =>
  http.get('/periodic-quality-reports', { params })
export const uploadPeriodicQualityReportApi = (formData) =>
  http.post('/periodic-quality-reports', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
export const createPeriodicQualityReportRevisionApi = (id, formData) =>
  http.post(`/periodic-quality-reports/${id}/revisions`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
export const appendPeriodicQualityReportApi = (id, formData) =>
  http.post(`/periodic-quality-reports/${id}/append`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
export const replacePeriodicQualityReportAttachmentApi = (id, index, formData) =>
  http.patch(`/periodic-quality-reports/${id}/attachments/${index}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
export const reviewPeriodicQualityReportApi = (id, payload) =>
  http.post(`/periodic-quality-reports/${id}/review`, payload)
