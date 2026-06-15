import http from './index'

export const operationDashboardApi = () => http.get('/operation/dashboard')

export const listCategoriesApi = () => http.get('/operation/categories')
export const createCategoryApi = (payload) => http.post('/operation/categories', payload)
export const updateCategoryApi = (id, payload) => http.put(`/operation/categories/${id}`, payload)
export const deleteCategoryApi = (id) => http.delete(`/operation/categories/${id}`)
export const uploadCategoryImageApi = (formData) =>
  http.post('/operation/categories/upload-image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

export const listProductsApi = (params) => http.get('/operation/products', { params })
export const createProductApi = (payload) => http.post('/operation/products', payload)
export const updateProductApi = (id, payload) => http.put(`/operation/products/${id}`, payload)
export const deleteProductApi = (id) => http.delete(`/operation/products/${id}`)
export const uploadProductImageApi = (formData) =>
  http.post('/operation/products/upload-image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

export const listAccountsApi = (params) => http.get('/operation/accounts', { params })
export const searchOperationAccountAddressTipsApi = (params) =>
  http.get('/operation/accounts/address-tips', { params })
export const createAccountApi = (payload) => http.post('/operation/accounts', payload)
export const updateAccountApi = (id, payload) => http.put(`/operation/accounts/${id}`, payload)
export const deleteAccountApi = (id) => http.delete(`/operation/accounts/${id}`)

export const listOperationClientCanteensApi = (params) =>
  http.get('/operation/client-canteens', { params })
export const createOperationClientCanteenApi = (payload) =>
  http.post('/operation/client-canteens', payload)
export const updateOperationClientCanteenApi = (id, payload) =>
  http.put(`/operation/client-canteens/${id}`, payload)
export const deleteOperationClientCanteenApi = (id) => http.delete(`/operation/client-canteens/${id}`)

export const listOperationContractsApi = (params) => http.get('/operation/contracts', { params })
export const getOperationContractApi = (contractId) => http.get(`/operation/contracts/${contractId}`)
export const listOperationContractOrdersApi = (contractId, params) =>
  http.get(`/operation/contracts/${contractId}/orders`, { params })

export const listOperationOrdersApi = (params) => http.get('/operation/orders', { params })
export const operationOrderDetailApi = (orderId) => http.get(`/operation/orders/${orderId}`)
export const operationFleetMonitorVehiclesApi = () => http.get('/operation/fleet-monitor/vehicles')
export const operationFleetMonitorWarehousesApi = () => http.get('/operation/fleet-monitor/warehouses')
export const operationFleetMonitorCameraLiveUrlApi = (id) =>
  http.get(`/operation/fleet-monitor/cameras/${id}/live-url`)
export const operationFleetMonitorCameraPtzApi = (id, payload) =>
  http.post(`/operation/fleet-monitor/cameras/${id}/camera-ptz`, payload)
export const operationFleetMonitorVehicleHistoryTrackApi = (vehicleId, payload) =>
  http.post(`/operation/fleet-monitor/vehicles/${vehicleId}/beidou-history-track`, payload)
export const listTicketsApi = (params) => http.get('/operation/tickets', { params })
export const createTicketApi = (payload) => http.post('/operation/tickets', payload)
export const updateTicketApi = (id, payload) => http.put(`/operation/tickets/${id}`, payload)
export const resolveComplaintTicketApi = (id, payload) =>
  http.post(`/operation/tickets/${id}/resolve`, payload)
export const deleteTicketApi = (id) => http.delete(`/operation/tickets/${id}`)

export const listSmartScaleRecognitionCategoriesApi = () =>
  http.get('/smart-scale-recognition/categories')
export const createSmartScaleRecognitionCategoryApi = (payload) =>
  http.post('/smart-scale-recognition/categories', payload)
export const updateSmartScaleRecognitionCategoryApi = (id, payload) =>
  http.put(`/smart-scale-recognition/categories/${id}`, payload)
export const deleteSmartScaleRecognitionCategoryApi = (id) =>
  http.delete(`/smart-scale-recognition/categories/${id}`)
export const listSmartScaleRecognitionSamplesApi = (categoryId, params) =>
  http.get(`/smart-scale-recognition/categories/${categoryId}/samples`, { params })
export const uploadSmartScaleRecognitionSampleApi = (categoryId, formData) =>
  http.post(`/smart-scale-recognition/categories/${categoryId}/samples`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
export const deleteSmartScaleRecognitionSampleApi = (id) =>
  http.delete(`/smart-scale-recognition/samples/${id}`)
export const reviewSmartScaleRecognitionSamplesApi = (payload) =>
  http.post('/smart-scale-recognition/samples/review', payload)
export const recropSmartScaleRecognitionSamplesApi = (payload) =>
  http.post('/smart-scale-recognition/samples/recrop', payload)
export const listSmartScaleRecognitionDevicesApi = () =>
  http.get('/smart-scale-recognition/devices')
export const listSmartScaleRecognitionRoiProfilesApi = (params) =>
  http.get('/smart-scale-recognition/roi-profiles', { params })
export const createSmartScaleRecognitionRoiProfileApi = (payload) =>
  http.post('/smart-scale-recognition/roi-profiles', payload)
export const publishSmartScaleRecognitionApi = () => http.post('/smart-scale-recognition/publish')

// —— 真模型训练（PyTorch MobileNetV2）相关接口 ——
export const importReceivingRecognitionSamplesApi = (payload) =>
  http.post('/smart-scale-recognition/import-receiving', payload)
export const trainSmartScaleRecognitionApi = (payload) =>
  http.post('/smart-scale-recognition/train', payload)
export const getSmartScaleRecognitionTrainStatusApi = (taskId) =>
  http.get(`/smart-scale-recognition/train/${taskId}`)
export const cancelSmartScaleRecognitionTrainApi = (taskId) =>
  http.post(`/smart-scale-recognition/train/${taskId}/cancel`)
export const listSmartScaleRecognitionModelsApi = () =>
  http.get('/smart-scale-recognition/models')
export const deploySmartScaleRecognitionModelApi = (taskId) =>
  http.post(`/smart-scale-recognition/models/${taskId}/deploy`)
export const recognizeSmartScaleApi = (formData) =>
  http.post('/smart-scale-recognition/recognize', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
