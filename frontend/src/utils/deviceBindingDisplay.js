/** 设备绑定展示：车辆或仓库（互斥，每设备仅一处） */
export function deviceBindingDisplay(row) {
  if (!row) return null
  if (row.bound_target_type === 'warehouse' || row.bound_warehouse_id) {
    return {
      kind: 'warehouse',
      tag: '仓库',
      primary: row.bound_warehouse_name || `仓库#${row.bound_warehouse_id}`,
      secondary: '',
    }
  }
  if (row.bound_target_type === 'vehicle' || row.bound_vehicle_id) {
    return {
      kind: 'vehicle',
      tag: '车辆',
      primary: row.bound_vehicle_no || `车辆#${row.bound_vehicle_id}`,
      secondary: row.bound_vehicle_driver || '',
    }
  }
  return null
}

export function deviceBindingTagType(kind) {
  if (kind === 'warehouse') return 'success'
  if (kind === 'vehicle') return 'primary'
  return 'info'
}
