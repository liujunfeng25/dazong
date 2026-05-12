import http from './index'

export const operationDashboardApi = () => http.get('/operation/dashboard')

export const listCategoriesApi = () => http.get('/operation/categories')
export const createCategoryApi = (payload) => http.post('/operation/categories', payload)
export const updateCategoryApi = (id, payload) => http.put(`/operation/categories/${id}`, payload)
export const deleteCategoryApi = (id) => http.delete(`/operation/categories/${id}`)

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
export const listTicketsApi = (params) => http.get('/operation/tickets', { params })
export const createTicketApi = (payload) => http.post('/operation/tickets', payload)
export const updateTicketApi = (id, payload) => http.put(`/operation/tickets/${id}`, payload)
export const resolveComplaintTicketApi = (id, payload) =>
  http.post(`/operation/tickets/${id}/resolve`, payload)
export const deleteTicketApi = (id) => http.delete(`/operation/tickets/${id}`)
