import http from './index'

export const demoNewOrderApi = () => http.post('/demo/new-order')
export const demoTriggerTempAlertApi = () => http.post('/demo/trigger-temperature-alert')
export const demoSimulateDeliveryApi = () => http.post('/demo/simulate-delivery')
export const demoResetApi = () => http.post('/demo/reset')
