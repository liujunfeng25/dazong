/** 32-bit FNV-1a */
export function hash32(str) {
  let h = 2166136261 >>> 0;
  const s = String(str || "");
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

export function shuffleWithSeed(arr, seed) {
  const a = arr.slice();
  let s = seed >>> 0;
  const rnd = () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 0xffffffff;
  };
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/**
 * @param {Array<{ id: number }>} pool
 * @param {number} linesPerOrder
 * @param {number} orderIndex
 * @param {number} ordersPerClient
 * @param {string} clientKey
 * @param {Set<number>} usedProductIds
 */
export function pickProductsForOrder(pool, linesPerOrder, orderIndex, ordersPerClient, clientKey, usedProductIds) {
  const pid = (p) => Number(p.id);
  const lines = Math.min(linesPerOrder, pool.length);
  if (!lines) return [];
  const unused = pool.filter((p) => !usedProductIds.has(pid(p)));
  const base = unused.length >= lines ? unused : pool.slice();
  const lines2 = Math.min(linesPerOrder, base.length);
  const maxStart = Math.max(0, base.length - lines2);
  const seedBase = hash32(String(clientKey || ""));
  if (maxStart === 0) {
    return shuffleWithSeed(base, seedBase ^ (orderIndex * 2654435761)).slice(0, lines2);
  }
  if (ordersPerClient > maxStart + 1) {
    const seed = seedBase ^ (orderIndex * 0x9e3779b9) ^ (orderIndex << 17);
    return shuffleWithSeed(base, seed).slice(0, lines2);
  }
  const denom = Math.max(ordersPerClient - 1, 1);
  const start = Math.min(Math.round((orderIndex * maxStart) / denom), maxStart);
  return base.slice(start, start + lines2);
}

/** 与 App.vue 批量下单中数量公式一致（用于自测） */
export function lineQuantityForDemo(baseQty, oi, li, clientKey) {
  const clientHash = hash32(clientKey) % 13;
  const bump = (oi * 17 + li * 5 + ((oi * li) % 11) + clientHash) % 19;
  return Math.max(1, Math.min(120, baseQty + bump));
}
