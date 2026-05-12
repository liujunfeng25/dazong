import { defineStore } from 'pinia'
import { listNotificationsApi, markNotificationReadApi, markNotificationsReadApi } from '../api/notifications'
import { createReconnectingWS } from '../services/ws'
import { formatChinaDateTime, parseBackendDate } from '../utils/datetime'
import { useUserStore } from './user'

export const useNotificationStore = defineStore('notifications', {
  state: () => ({
    items: [],
    unread: 0,
    loading: false,
    _ws: null,
  }),
  getters: {
    eventTypeLabelMap: () => ({
      tender_shortlisted: '入围通知',
      tender_bid_created: '报价通知',
      tender_bid_updated: '报价更新',
      tender_award_win: '中标通知',
      tender_award_lose: '结果通知',
      tender_awarded_done: '定标完成',
      supplier_quote_updated: '供货报价更新',
      order_status_change: '订单通知',
      bill_created: '账单生成',
      bill_settled: '账单结算',
      bill_update: '账单结算',
      general: '系统通知',
    }),
    eventMetaMap: () => ({
      order_status_change: { tone: 'fulfillment', icon: '履' },
      bill_created: { tone: 'bill-create', icon: '生' },
      bill_settled: { tone: 'bill-settle', icon: '结' },
      bill_update: { tone: 'bill-settle', icon: '结' },
      tender_shortlisted: { tone: 'procurement', icon: '招' },
      tender_bid_created: { tone: 'procurement', icon: '招' },
      tender_bid_updated: { tone: 'procurement', icon: '招' },
      tender_award_win: { tone: 'important', icon: '中' },
      tender_award_lose: { tone: 'important', icon: '失' },
      tender_awarded_done: { tone: 'procurement', icon: '定' },
      supplier_quote_updated: { tone: 'procurement', icon: '报' },
      general: { tone: 'general', icon: '系' },
    }),
    sortedItems: (state) =>
      [...state.items].sort(
        (a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime(),
      ),
    viewItems() {
      return this.sortedItems.map((item) => ({
        ...item,
        event_label: this.eventTypeLabelMap[item.event_type] || '系统通知',
        event_meta: this.eventMetaMap[item.event_type] || this.eventMetaMap.general,
        time_text: formatTime(item.created_at),
      }))
    },
  },
  actions: {
    async refresh() {
      this.loading = true
      try {
        const history = await listNotificationsApi()
        this.items = history || []
        this.unread = this.items.filter((item) => !item.is_read).length
      } finally {
        this.loading = false
      }
    },
    async connect() {
      const userStore = useUserStore()
      if (!userStore.token || !userStore.role || this._ws) return
      await this.refresh()
      const base = import.meta.env.VITE_WS_BASE_URL || 'ws://127.0.0.1:8000'
      this._ws = createReconnectingWS(`${base}/ws/notifications/${userStore.role}?token=${userStore.token}`, {
        reconnectMs: 3000,
        onMessage: (msg) => {
          const me = Number(userStore.userInfo?.id || 0)
          if (!_acceptClientWsCanteen(userStore, msg)) return
          if (msg.type === 'order_update') {
            const targetIds = msg.target_user_ids || []
            if (targetIds.length && !targetIds.includes(me)) return
            this.items.unshift({
              type: 'order_update',
              event_type: 'order_status_change',
              title: `[履约] 订单${msg.order_no || ''}状态更新`,
              content: msg.message || '',
              route: msg.order_id ? `/${userStore.role}/orders/${msg.order_id}` : '',
              object_type: 'order',
              object_id: msg.order_id || 0,
              created_at: new Date().toISOString(),
              is_read: false,
            })
            this.items = this.items.slice(0, 30)
            this.unread += 1
          }
          if (msg.type === 'notification') {
            const targetIds = msg.target_user_ids || []
            if (targetIds.length && !targetIds.includes(me)) return
            this.items.unshift({
              type: 'notification',
              event_type: msg.event_type || 'general',
              title: msg.title || '系统通知',
              content: msg.content || '',
              route: msg.route || '',
              object_type: msg.object_type || '',
              object_id: msg.object_id || 0,
              created_at: new Date().toISOString(),
              is_read: false,
            })
            this.items = this.items.slice(0, 30)
            this.unread += 1
          }
        },
      })
    },
    getFilteredItems({ unreadOnly = false, eventType = '', keyword = '' } = {}) {
      const kw = String(keyword || '').trim().toLowerCase()
      return this.viewItems.filter((item) => {
        if (unreadOnly && item.is_read) return false
        if (eventType && item.event_type !== eventType) return false
        if (!kw) return true
        return (
          String(item.title || '').toLowerCase().includes(kw) ||
          String(item.content || '').toLowerCase().includes(kw)
        )
      })
    },
    async markAllRead() {
      this.unread = 0
      this.items = this.items.map((item) => ({ ...item, is_read: true }))
      await markNotificationsReadApi({ ids: [] })
    },
    async markReadOne(id) {
      if (!id) return
      const idx = this.items.findIndex((item) => item.id === id)
      if (idx >= 0 && !this.items[idx].is_read) {
        this.items[idx].is_read = true
        this.unread = Math.max(0, this.unread - 1)
      }
      await markNotificationReadApi(id)
    },
    disconnect() {
      if (this._ws) this._ws.close()
      this._ws = null
      this.unread = 0
    },
  },
})

/** 采购端：未选食堂时不展示带食堂维度的履约推送；已选食堂则丢弃非当前食堂的推送。学校级 payload 无 canteen_id。 */
function _acceptClientWsCanteen(userStore, msg) {
  if (userStore.role !== 'client') return true
  const wid = msg.canteen_id
  if (wid == null || wid === undefined) return true
  const jwtCid = userStore.userInfo?.canteen_id
  if (jwtCid == null || jwtCid === undefined) return false
  return Number(wid) === Number(jwtCid)
}

function formatTime(input) {
  const dt = parseBackendDate(input)
  if (Number.isNaN(dt.getTime())) return ''
  const now = Date.now()
  const diff = now - dt.getTime()
  if (diff < 60 * 1000) return '刚刚'
  if (diff < 60 * 60 * 1000) return `${Math.floor(diff / (60 * 1000))}分钟前`
  if (diff < 24 * 60 * 60 * 1000) return `${Math.floor(diff / (60 * 60 * 1000))}小时前`
  return formatChinaDateTime(input)
}
