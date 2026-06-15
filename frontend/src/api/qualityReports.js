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

/** 在已有报告后追加图片/PDF（仅 multipart files，字段名 files） */
export const appendQualityReportByAllocationApi = (allocationId, formData) =>
  http.post(`/quality-reports/by-allocation/${allocationId}/append`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

export const replaceQualityReportAttachmentApi = (allocationId, index, formData) =>
  http.patch(`/quality-reports/by-allocation/${allocationId}/attachments/${index}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

export const listQualityReportsByOrderApi = (orderId) =>
  http.get(`/quality-reports/by-order/${orderId}`)
