// 商品单位枚举（与后端 services/units.py 保持一致；仅清单，无换算）
// 非标品计量单位用 'kg' / '斤'（不用「公斤」，避免历史 `"斤" in unit` 子串误判）。
export const WEIGHT_UNITS = ['kg', '斤']

export const COUNT_UNITS = [
  '件', '袋', '箱', '盒', '包', '桶', '瓶', '杯', '提', '排',
  '卷', '只', '块', '托', '组', '把', '份', '条', '罐', '听',
]

export function allowedUnitsFor(standardType) {
  return standardType === 'non_standard' ? WEIGHT_UNITS : COUNT_UNITS
}
