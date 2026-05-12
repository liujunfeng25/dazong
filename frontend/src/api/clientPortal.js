import http from './index'

export const listClientCanteensApi = () => http.get('/client/canteens')
export const setClientCanteenSessionApi = (canteen_id) =>
  http.post('/client/canteen-session', { canteen_id })
