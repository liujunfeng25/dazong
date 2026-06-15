export const createEmptyRoutePlan = () => ({
  driver: '',
  total_distance: '-',
  estimated_time: '-',
  stops: [],
  optimization_compare: {},
  capacity_usage: {},
  data_quality: {},
  capability_badges: [],
  risk_alerts: [],
  vehicle: {},
  route_path: [],
  vehicle_routes: [],
  vehicle_count: 0,
  vehicles_used_in_plan: 0,
  vehicles_available_today: 0,
  vehicles_active_total: 0,
  vehicles_excluded_from_planning: [],
  vehicle_limit_today: null,
  planning_inputs_echo: null,
  total_distance_km: undefined,
  estimated_duration_minutes: undefined,
})

export const hasGeneratedRoutePlan = (plan) =>
  (Array.isArray(plan?.vehicle_routes) && plan.vehicle_routes.length > 0) ||
  (Array.isArray(plan?.stops) && plan.stops.length > 0)
