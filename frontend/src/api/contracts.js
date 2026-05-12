import http from './index'

export const createTenderApi = (payload) => http.post('/contracts/tender', payload)
export const tenderMetaApi = () => http.get('/contracts/meta')
export const listTenderApi = () => http.get('/contracts/tender/list')
export const listMyTendersApi = () => http.get('/contracts/tender/my')
export const tenderDetailApi = (id) => http.get(`/contracts/tender/${id}`)
export const bidTenderApi = (id, payload) => http.post(`/contracts/tender/${id}/bid`, payload)
export const listTenderBidsApi = (id) => http.get(`/contracts/tender/${id}/bids`)
export const awardTenderApi = (id, payload) => http.post(`/contracts/tender/${id}/award`, payload)
export const listContractsApi = (params) => http.get('/contracts/list', { params: params || {} })
export const contractDetailApi = (id) => http.get(`/contracts/${id}`)
