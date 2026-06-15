/** 与运营端 Products.vue 一致：standard=标品，non_standard=非标品 */
export function productStandardTypeLabel(value) {
  return ({ standard: '标品', non_standard: '非标品' })[value] || null
}

export function productStandardTypeTagType(value) {
  if (value === 'standard') return 'success'
  if (value === 'non_standard') return 'warning'
  return 'info'
}

export function productStandardTypeCardClass(value) {
  if (value === 'non_standard') return 'non-standard'
  if (value === 'standard') return 'standard'
  return ''
}
