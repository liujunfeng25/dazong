/**
 * 自测：同一客户多笔订单在「未用 SKU 优先」+ 数量公式下，模拟总额应两两不同。
 * 运行：cd demo-console && node scripts/verify-order-diversity.mjs
 */
import {
  pickProductsForOrder,
  lineQuantityForDemo,
} from "../src/lib/orderPick.js";

function mockTotal(subset, baseQty, oi, clientKey, unitById) {
  let t = 0;
  subset.forEach((p, li) => {
    const q = lineQuantityForDemo(baseQty, oi, li, clientKey);
    const u = unitById.get(Number(p.id)) ?? 1;
    t += q * u;
  });
  return Math.round(t * 100) / 100;
}

function runCase(poolSize, lines, ordersPerClient, baseQty, clientKey) {
  const pool = [];
  for (let i = 1; i <= poolSize; i++) {
    pool.push({ id: i, name: `p${i}` });
  }
  const unitById = new Map(pool.map((p) => [p.id, 10 + (p.id % 7) * 0.37]));
  const used = new Set();
  const totals = [];
  for (let oi = 0; oi < ordersPerClient; oi++) {
    const subset = pickProductsForOrder(pool, lines, oi, ordersPerClient, clientKey, used);
    totals.push(mockTotal(subset, baseQty, oi, clientKey, unitById));
    for (const p of subset) used.add(Number(p.id));
  }
  const uniq = new Set(totals.map((x) => String(x)));
  return { totals, allDistinct: uniq.size === totals.length };
}

const cases = [
  { pool: 8, lines: 5, orders: 3, name: "小池 8SKU×5行×3笔" },
  { pool: 15, lines: 5, orders: 3, name: "中池 15×5×3" },
  { pool: 40, lines: 5, orders: 5, name: "大池 40×5×5" },
];

let failed = false;
for (const c of cases) {
  const r = runCase(c.pool, c.lines, c.orders, 2, "client003");
  if (!r.allDistinct) {
    console.error("FAIL", c.name, "totals=", r.totals);
    failed = true;
  } else {
    console.log("OK ", c.name, "totals=", r.totals.join(", "));
  }
}

if (failed) process.exit(1);
console.log("verify-order-diversity: all cases passed.");
