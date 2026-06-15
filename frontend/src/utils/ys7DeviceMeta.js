/** 从设备行或萤石 raw 缓存解析供电类型与型号（与后端 _ys7_device_meta 口径一致） */
export function ys7MetaFromRow(row) {
  if (row?.ys7_power_label) {
    return {
      powerLabel: row.ys7_power_label,
      powerKind: row.ys7_power_kind || 'unknown',
      model: row.ys7_model || '',
    }
  }
  const raw = row?.raw_payload_json
  const device =
    raw && typeof raw === 'object' && raw.device && typeof raw.device === 'object'
      ? raw.device
      : raw && typeof raw === 'object' && raw.parentCategory
        ? raw
        : {}
  const parent = String(device.parentCategory || '').trim()
  const model = String(device.model || device.deviceType || '').trim()
  if (parent === 'BatteryCamera') {
    return { powerLabel: '电池机', powerKind: 'battery', model }
  }
  if (['IPC', 'NVR', 'DVR', 'HCVR', 'SD'].includes(parent)) {
    return { powerLabel: '有线机', powerKind: 'wired', model }
  }
  if (parent) {
    return { powerLabel: parent, powerKind: 'other', model }
  }
  return { powerLabel: '', powerKind: 'unknown', model }
}

export function ys7PowerTagType(powerKind) {
  if (powerKind === 'battery') return 'warning'
  if (powerKind === 'wired') return 'success'
  return 'info'
}

/** 仅有线萤石 IPC 等支持云台；电池机不支持 */
export function ys7SupportsPtz(row) {
  if (row?.ys7_supports_ptz === true) return true
  if (row?.ys7_supports_ptz === false) return false
  return ys7MetaFromRow(row).powerKind === 'wired'
}

/** 电池机电量 0–100；同步萤石后由后端 ys7_status 写入 */
export function ys7BatteryFromRow(row) {
  if (row?.ys7_battery_percent != null && row?.ys7_battery_percent !== '') {
    const n = Number(row.ys7_battery_percent)
    if (Number.isFinite(n) && n >= 0 && n <= 100) return Math.round(n)
  }
  const st = row?.raw_payload_json?.ys7_status
  if (st?.battery_percent != null) {
    const n = Number(st.battery_percent)
    if (Number.isFinite(n) && n >= 0 && n <= 100) return Math.round(n)
  }
  return null
}

/** low | medium | high */
export function ys7BatteryLevel(percent) {
  if (percent == null) return null
  if (percent <= 20) return 'low'
  if (percent <= 40) return 'medium'
  return 'high'
}

export function ys7BatteryTagType(percent) {
  const lv = ys7BatteryLevel(percent)
  if (lv === 'low') return 'danger'
  if (lv === 'medium') return 'warning'
  if (lv === 'high') return 'success'
  return 'info'
}
