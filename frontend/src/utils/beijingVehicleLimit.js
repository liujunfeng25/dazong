/** 北京尾号限行展示逻辑（与后端 beijing_vehicle_plate_limit 规则对齐） */

export const parsePlateTailDigit = (plateNo) => {
  const text = String(plateNo || '').trim().toUpperCase()
  if (!text) return null
  const last = text[text.length - 1]
  if (/[0-9]/.test(last)) return Number(last)
  if (/[A-Z]/.test(last)) return 0
  return null
}

export const isBeijingPlate = (plateNo) => String(plateNo || '').trim().toUpperCase().startsWith('京')

export const isBeijingPureElectricPlate = (plateNo) => {
  const p = String(plateNo || '').trim().toUpperCase()
  return p.startsWith('京AA') || p.startsWith('京AB') || p.startsWith('京AC') || p.startsWith('京AD')
}

export const isPureElectricExempt = (row) => isBeijingPureElectricPlate(row?.vehicle_no)

/**
 * @param {object} row 含 vehicle_no
 * @param {object} restrictionInfo { available, digits[], raw_text, city, message }
 * @returns {string} 限行 | 不限行 | - | 待补充车牌 | 待识别
 */
export const vehicleLimitTag = (row, restrictionInfo) => {
  const plate = String(row?.vehicle_no || '')
  if (!isBeijingPlate(plate)) return '限行'
  if (isPureElectricExempt(row)) return '-'
  const digits = Array.isArray(restrictionInfo?.digits)
    ? restrictionInfo.digits.map((x) => Number(x)).filter((n) => !Number.isNaN(n))
    : []
  if (!restrictionInfo?.available) return '待识别'
  if (!digits.length) return '不限行'
  const tail = parsePlateTailDigit(row?.vehicle_no)
  if (tail == null) return '待补充车牌'
  return digits.includes(tail) ? '限行' : '不限行'
}

export const vehicleLimitReason = (row, restrictionInfo) => {
  const plate = String(row?.vehicle_no || '')
  const tail = parsePlateTailDigit(row?.vehicle_no)
  if (!isBeijingPlate(plate)) {
    return `外地牌照（${plate}）默认按未办进京证处理：北京限行；如办理进京证，仍需继续遵守尾号限行`
  }
  if (isPureElectricExempt(row)) return `车牌前缀 ${plate.slice(0, 4)} 识别为纯电车型，不受限号管制`
  const digits = Array.isArray(restrictionInfo?.digits)
    ? restrictionInfo.digits.map((x) => Number(x)).filter((n) => !Number.isNaN(n))
    : []
  if (!restrictionInfo?.available) return restrictionInfo?.message || '限行接口不可用'
  if (!digits.length) return restrictionInfo?.raw_text || '今日接口返回不限行'
  if (tail == null) return '车牌尾号无法识别，请检查录入'
  if (digits.includes(tail)) {
    return `车牌尾号 ${tail} 命中今日限号 ${digits.join('/')}，因此标红`
  }
  return `车牌尾号 ${tail} 未命中今日限号 ${digits.join('/')}`
}

/** 路线规划总览：后端 limit_status -> 展示短标签 */
export const limitStatusDisplay = (limitStatus) => {
  const m = {
    限行: '限行',
    不限行: '不限',
    纯电不限: '纯电',
    外地限行: '外地',
    待识别: '待核',
    用户禁用: '已禁',
  }
  return m[limitStatus] || limitStatus || '-'
}
