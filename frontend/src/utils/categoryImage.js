/**
 * 分类图片解析：把分类的 image_url + 名称解析成可直接渲染的图标。
 *
 * - image_url 为图片地址（http/https 或 / 开头）→ 真实图片
 * - image_url 为 "emoji:🥬" → 指定 emoji
 * - 否则按分类名关键词自动映射食材 emoji + 柔和色块（零维护、即刻好看）
 *
 * 运营端「分类管理」与客户端移动「新建订单」分类栏共用同一套解析，保证一致。
 */

// 柔和色块底（鲜活食材风）
const TONES = {
  green: '#dff1e7',
  amber: '#fcebd2',
  meat: '#fbe2de',
  blue: '#d9ebf5',
  fruit: '#fce0e6',
  grain: '#f1ead4',
  egg: '#fdf1d6',
  season: '#ece4d2',
  brown: '#ece0d2',
  default: '#e9ece4',
}

// 关键词 → { glyph, tone }；按顺序匹配（具体在前）
const KEYWORD_MAP = [
  [['叶菜', '青菜', '生菜', '白菜'], '🥬', 'green'],
  [['根茎', '萝卜', '土豆', '薯', '姜', '蒜', '葱'], '🥔', 'amber'],
  [['番茄', '西红柿', '茄'], '🍅', 'meat'],
  [['辣椒', '椒'], '🌶️', 'meat'],
  [['玉米'], '🌽', 'amber'],
  [['瓜'], '🥒', 'green'],
  [['菌', '菇'], '🍄', 'brown'],
  [['蔬', '菜'], '🥬', 'green'],
  [['猪'], '🥩', 'meat'],
  [['牛'], '🥩', 'meat'],
  [['羊'], '🍖', 'meat'],
  [['鸡', '禽'], '🍗', 'meat'],
  [['鸭', '鹅'], '🍗', 'meat'],
  [['肉'], '🥩', 'meat'],
  [['蛋'], '🥚', 'egg'],
  [['虾'], '🦐', 'blue'],
  [['蟹'], '🦀', 'blue'],
  [['贝', '螺'], '🦪', 'blue'],
  [['鱼'], '🐟', 'blue'],
  [['海鲜', '水产'], '🐟', 'blue'],
  [['豆腐', '豆制品', '豆'], '🫛', 'green'],
  [['米', '粮', '谷', '杂粮'], '🍚', 'grain'],
  [['面', '粉', '馒头', '包子'], '🍜', 'grain'],
  [['油'], '🫗', 'grain'],
  [['盐', '调味', '酱', '醋', '料'], '🧂', 'season'],
  [['奶', '乳'], '🥛', 'default'],
  [['水果', '果'], '🍎', 'fruit'],
  [['饮', '水'], '🥤', 'blue'],
  [['冻', '速冻'], '🧊', 'blue'],
]

const DEFAULT_GLYPH = '🧺'

function autoByName(name) {
  const n = String(name || '')
  for (const [keys, glyph, tone] of KEYWORD_MAP) {
    if (keys.some((k) => n.includes(k))) return { glyph, tone }
  }
  return { glyph: DEFAULT_GLYPH, tone: 'default' }
}

/**
 * @returns {{ type:'photo', src:string } | { type:'emoji', glyph:string, tone:string, bg:string }}
 */
export function resolveCategoryImage(name, imageUrl) {
  const v = (imageUrl || '').trim()
  if (v && (v.startsWith('http') || v.startsWith('/'))) {
    return { type: 'photo', src: v }
  }
  if (v.startsWith('emoji:')) {
    const glyph = v.slice('emoji:'.length) || DEFAULT_GLYPH
    const tone = autoByName(name).tone
    return { type: 'emoji', glyph, tone, bg: TONES[tone] || TONES.default }
  }
  const { glyph, tone } = autoByName(name)
  return { type: 'emoji', glyph, tone, bg: TONES[tone] || TONES.default }
}

/** 运营端手选 emoji 用的食材调色板 */
export const CATEGORY_EMOJI_PALETTE = [
  '🥬', '🥔', '🍅', '🌶️', '🌽', '🥒', '🍆', '🥕', '🧄', '🧅',
  '🍄', '🥦', '🥩', '🍖', '🍗', '🥚', '🐟', '🦐', '🦀', '🦪',
  '🫛', '🍚', '🍜', '🫗', '🧂', '🥛', '🍎', '🍊', '🍇', '🍄‍🟫',
  '🧊', '🥤', '🧺',
]
