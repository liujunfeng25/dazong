import { elitechFormatValue } from './elitechDeviceMeta'

export function warehouseElitechBriefText(warehouse) {
  if (!warehouse?.elitech_bound) return ''
  const temp = elitechFormatValue(warehouse.elitech_temperature, '℃')
  const hum = elitechFormatValue(warehouse.elitech_humidity, '%RH')
  return `${temp} / ${hum}`
}

const _esc = (s) =>
  String(s || '').replace(/[<>&"']/g, (c) =>
    ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' }[c] || c),
  )

/** 高德地图仓库标注 HTML（含温湿度一行） */
export function warehouseMapMarkerHtml(warehouse) {
  const escName = _esc(warehouse?.name || '仓库')
  const camCount = Array.isArray(warehouse?.cameras) ? warehouse.cameras.length : 0
  const elitechLine = warehouseElitechBriefText(warehouse)
  const elitechHtml = elitechLine
    ? `<em class="warehouse-marker-elitech">${_esc(elitechLine)}</em>`
    : ''
  const extraClass = elitechLine ? ' warehouse-marker--elitech' : ''
  return `<div class="warehouse-marker${extraClass}"><div class="warehouse-marker-row"><i>仓</i><span>${escName}</span></div>${elitechHtml}<b>${camCount}</b></div>`
}
