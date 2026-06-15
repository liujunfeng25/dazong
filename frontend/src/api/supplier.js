import http from './index'

export const supplierHomeApi = () => http.get('/supplier/home')
export const supplierOrdersApi = (params) => http.get('/supplier/orders', { params })
export const listSupplierProductQuotesApi = (params) => http.get('/supplier/product-quotes', { params })
export const saveSupplierProductQuotesApi = (payload) => http.put('/supplier/product-quotes', payload)
export const withdrawSupplierProductQuoteApi = (productId) => http.delete(`/supplier/product-quotes/${productId}`)
