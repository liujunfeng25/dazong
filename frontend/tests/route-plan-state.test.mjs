import test from 'node:test'
import assert from 'node:assert/strict'

import {
  createEmptyRoutePlan,
  hasGeneratedRoutePlan,
} from '../src/utils/routePlanState.js'


test('empty route plan has no savable result', () => {
  assert.equal(hasGeneratedRoutePlan(createEmptyRoutePlan()), false)
})


test('generated route is detected and can be invalidated after inputs change', () => {
  let plan = {
    ...createEmptyRoutePlan(),
    stops: [{ order_id: 101 }],
    vehicle_routes: [{ vehicle_id: 7, stops: [{ order_id: 101 }] }],
  }
  assert.equal(hasGeneratedRoutePlan(plan), true)

  plan = createEmptyRoutePlan()
  assert.equal(hasGeneratedRoutePlan(plan), false)
  assert.deepEqual(plan.vehicle_routes, [])
  assert.deepEqual(plan.stops, [])
})


test('empty route plan instances do not share arrays', () => {
  const first = createEmptyRoutePlan()
  const second = createEmptyRoutePlan()
  first.stops.push({ order_id: 1 })
  assert.deepEqual(second.stops, [])
})
