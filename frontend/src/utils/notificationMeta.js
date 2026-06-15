/** 账单类通知：按当前端视角展示「收 / 付」，不再用「生 / 账」。 */

const BILLING_EVENT_TYPES = new Set([
  'billing',
  'billing_confirmed',
  'billing_confirmed_by_peer',
  'billing_settled',
  'billing_settled_by_peer',
  'bill_created',
  'bill_settled',
  'bill_update',
])

const META_RECEIVE = { tone: 'bill-receive', icon: '收' }
const META_PAY = { tone: 'bill-pay', icon: '付' }

function textOf(item) {
  return `${item?.title || ''} ${item?.content || ''}`
}

/** 标题/正文中的应收、应付（相对账单归属方） */
function directionFromTitleContent(item) {
  const title = String(item?.title || '')
  const content = String(item?.content || '')
  if (title.includes('应收') || /\b应收\b/.test(content)) return 'receive'
  if (title.includes('应付') || /\b应付\b/.test(content)) return 'pay'
  if (content.includes('等待对方付款')) return 'receive'
  if (content.includes('安排付款')) return 'pay'
  return null
}

/** 收货入账 bill_created：同一事件类型，不同端含义不同 */
function directionForBillCreated(item, role) {
  const title = String(item?.title || '')
  const content = String(item?.content || '')
  const r = String(role || '')

  if (r === 'client') {
    return 'pay'
  }
  if (r === 'delivery') {
    if (title.includes('供货商') || title.includes('厂家') || content.includes('配送商应付')) {
      return 'pay'
    }
    if (title.includes('客户') || title.includes('食堂') || content.includes('客户（食堂）应付')) {
      return 'receive'
    }
  }
  if (r === 'supplier' || r === 'factory') {
    return 'receive'
  }
  return directionFromTitleContent(item)
}

function directionForBillingEvent(item, role) {
  const eventType = item?.event_type || ''
  if (eventType === 'bill_created') {
    return directionForBillCreated(item, role)
  }
  const fromText = directionFromTitleContent(item)
  if (fromText) return fromText

  if (eventType === 'billing_settled' || eventType === 'billing_settled_by_peer') {
    const title = String(item?.title || '')
    if (title.includes('对方已结清') || title.includes('对方已部分付款')) {
      return 'receive'
    }
    if (title.includes('已结清') || title.includes('已部分付款')) {
      return 'pay'
    }
  }
  return null
}

export function resolveNotificationEventMeta(item, role, baseMetaMap = {}) {
  const eventType = item?.event_type || 'general'
  const base = baseMetaMap[eventType] || baseMetaMap.general || { tone: 'general', icon: '系' }

  if (!BILLING_EVENT_TYPES.has(eventType)) {
    return base
  }

  const direction = directionForBillingEvent(item, role)
  if (direction === 'receive') return META_RECEIVE
  if (direction === 'pay') return META_PAY

  if (eventType === 'bill_settled' || eventType === 'bill_update') {
    return { tone: 'bill-settle', icon: '结' }
  }

  return base
}
