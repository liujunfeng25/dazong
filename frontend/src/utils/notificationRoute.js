export const billingRouteForRole = (role) => {
  if (['client', 'delivery', 'supplier', 'factory'].includes(role)) return `/${role}/bills`
  if (role === 'operation' || role === 'monitor') return '/operation/billing-overview'
  return '/login'
}

export const notificationCenterRouteForRole = (role) => {
  if (['client', 'delivery', 'supplier', 'factory', 'operation', 'monitor'].includes(role)) {
    return `/${role}/notifications`
  }
  return '/login'
}

export const resolveNotificationRoute = (router, role, rawRoute) => {
  const fallback = notificationCenterRouteForRole(role)
  const original = String(rawRoute || '').trim()
  if (!original) return { path: fallback, query: {} }
  const normalized = original === '/bills' ? billingRouteForRole(role) : original
  const resolved = router.resolve(normalized)
  if (!resolved.matched?.length) return { path: fallback, query: {} }
  return { path: resolved.path, query: { ...resolved.query } }
}
