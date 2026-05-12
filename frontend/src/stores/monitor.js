import { defineStore } from 'pinia'
import { createReconnectingWS } from '../services/ws'
import { useUserStore } from './user'

export const useMonitorStore = defineStore('monitor', {
  state: () => ({
    kpi: { today_orders: 0, today_gmv: 0, active_vehicles: 0, pending_alerts: 0 },
    vehicles: [],
    alerts: [],
    latestOrders: [],
    sensor: { temperature: 0, humidity: 0, warning: false },
    _ws: null,
    _sensorTimer: null,
  }),
  actions: {
    connectMonitor() {
      if (this._ws) return
      const userStore = useUserStore()
      const base = import.meta.env.VITE_WS_BASE_URL || 'ws://127.0.0.1:8000'
      this._ws = createReconnectingWS(`${base}/ws/monitor?token=${userStore.token}`, {
        reconnectMs: 3000,
        onMessage: (msg) => this.handleMessage(msg),
      })
    },
    disconnectMonitor() {
      if (this._ws) this._ws.close()
      this._ws = null
    },
    handleMessage(msg) {
      if (msg.type === 'snapshot') {
        this.kpi = msg.data.kpi || this.kpi
        this.alerts = msg.data.alerts || []
        this.sensor = msg.data.sensor || this.sensor
      } else if (msg.type === 'kpi_tick') {
        this.kpi = msg.data
      } else if (msg.type === 'vehicle_move') {
        this.vehicles = msg.data || []
      } else if (msg.type === 'new_alert') {
        this.alerts.unshift(msg.data)
        this.alerts = this.alerts.slice(0, 50)
      } else if (msg.type === 'order_status_change') {
        this.latestOrders.unshift(msg.data)
        this.latestOrders = this.latestOrders.slice(0, 20)
      } else if (msg.type === 'sensor_warning') {
        this.sensor = { ...msg.data, warning: true }
        if (this._sensorTimer) clearTimeout(this._sensorTimer)
        this._sensorTimer = setTimeout(() => {
          this.sensor = { ...this.sensor, warning: false }
        }, 10000)
      }
    },
  },
})
