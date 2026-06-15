export const buildFulfillmentActual = (detail = {}) => {
  const trip = detail.dispatch_trip || {}
  const record = detail.delivery_record || {}
  const tracking = detail.logistics_tracking || {}
  const trackingDelivery = tracking.delivery || {}
  const trackingVehicle = tracking.vehicle || {}
  return {
    routeNo: trip.route_no || trackingDelivery.route_no || '',
    vehicleNo: record.vehicle_no || trip.vehicle_no || trackingVehicle.vehicle_no || '',
    driverName: record.driver_name || trip.driver_name || trackingVehicle.driver_name || '',
    plannedDeparture: trip.departure_time || '',
    departedAt: record.departed_at || trip.departed_at || trackingDelivery.departed_at || '',
    arrivedAt: record.arrived_at || trackingDelivery.arrived_at || '',
    deliveryStatus: record.status || tracking.status_label || trip.status || '',
  }
}

export const dash = (value) => {
  const s = String(value ?? '').trim()
  return s || '—'
}
