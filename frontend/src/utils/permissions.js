const roleCapabilities = {
  operation: ['account:create', 'account:update', 'account:delete', 'ticket:handle'],
  monitor: ['alert:handle', 'report:view'],
  client: ['order:create', 'contract:create'],
  supplier: ['order:fulfill'],
  delivery: ['order:deliver', 'route:plan'],
  factory: ['report:upload'],
}

export function can(role, capability) {
  const caps = roleCapabilities[role] || []
  return caps.includes(capability)
}
