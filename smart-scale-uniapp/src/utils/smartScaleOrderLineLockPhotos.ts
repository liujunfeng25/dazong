/**
 * 正式单：按订单维度持久化「锁定读数」留痕图路径，便于二次进入作业台仍显示。
 * 演示单（无数字 orderId）用 order_no / id 生成 bucket，与 demoReceivingStorage 并存。
 */

const STORAGE_KEY = "smart_scale_order_line_lock_photos";

export type LineLockPhotoSource = "uvc" | "system";

export type LineLockPhotoPersistEntry = {
  uri: string;
  source: LineLockPhotoSource;
  ts: number;
};

/** orderId 为数字 API id，或 ono:order_no / oid:brief.id */
export type OrderLineLockPhotoRoot = Record<string, Record<string, LineLockPhotoPersistEntry>>;

function readRoot(): OrderLineLockPhotoRoot {
  try {
    const v = uni.getStorageSync(STORAGE_KEY) as unknown;
    if (!v || typeof v !== "object") return {};
    return v as OrderLineLockPhotoRoot;
  } catch {
    return {};
  }
}

function writeRoot(root: OrderLineLockPhotoRoot): void {
  try {
    uni.setStorageSync(STORAGE_KEY, root);
  } catch {
    /* ignore */
  }
}

/** 路由上的数字订单 id；否则用 order_no / OrderBrief.id 避免冲突 */
export function persistBucketForLineLockPhotos(
  orderIdFromRoute: string | null,
  order: { id?: string; order_no?: string } | null
): string | null {
  if (!order) return null;
  if (orderIdFromRoute && /^\d+$/.test(orderIdFromRoute)) return orderIdFromRoute;
  if (order.order_no) return `ono:${String(order.order_no)}`;
  if (order.id) return `oid:${String(order.id)}`;
  return null;
}

/** 尽量把临时路径转为 uni 本地保存路径，降低清缓存后失效概率 */
export async function stabilizeLockPhotoUriForStorage(uri: string): Promise<string> {
  if (!uri) return uri;
  const raw = uri.startsWith("file://") ? uri.slice(7) : uri;
  if (!raw || /^(https?:|blob:|data:)/i.test(uri)) return uri;
  if (typeof uni.saveFile !== "function") return uri;
  return new Promise((resolve) => {
    try {
      uni.saveFile({
        tempFilePath: raw,
        success(res) {
          const p = typeof res.savedFilePath === "string" ? res.savedFilePath : raw;
          resolve(p.startsWith("file:") ? p : `file://${p}`);
        },
        fail() {
          resolve(uri);
        },
      });
    } catch {
      resolve(uri);
    }
  });
}

export function loadLineLockPhotosMap(
  bucket: string,
  validLineIds: string[] | null
): Record<string, { uri: string; source: LineLockPhotoSource }> {
  const root = readRoot();
  const m = root[bucket];
  if (!m || typeof m !== "object") return {};
  const allow = validLineIds?.length ? new Set(validLineIds) : null;
  const out: Record<string, { uri: string; source: LineLockPhotoSource }> = {};
  for (const [lineId, entry] of Object.entries(m)) {
    if (!entry || typeof entry.uri !== "string" || !entry.uri) continue;
    if (allow && !allow.has(lineId)) continue;
    out[lineId] = {
      uri: entry.uri,
      source: entry.source === "system" ? "system" : "uvc",
    };
  }
  return out;
}

export function saveLineLockPhoto(
  bucket: string,
  lineId: string,
  uri: string,
  source: LineLockPhotoSource
): void {
  if (!bucket || !lineId || !uri) return;
  const root = readRoot();
  if (!root[bucket]) root[bucket] = {};
  root[bucket][lineId] = { uri, source, ts: Date.now() };
  writeRoot(root);
}

export function removeLineLockPhoto(bucket: string, lineId: string): void {
  if (!bucket || !lineId) return;
  const root = readRoot();
  const m = root[bucket];
  if (!m || typeof m !== "object") return;
  if (!(lineId in m)) return;
  delete m[lineId];
  if (Object.keys(m).length === 0) delete root[bucket];
  writeRoot(root);
}

/** 删除当前订单明细中已不存在的行键，避免存储无限膨胀 */
export function pruneLineLockPhotosToOrderLines(bucket: string, validLineIds: string[]): void {
  if (!bucket || !validLineIds.length) return;
  const allow = new Set(validLineIds);
  const root = readRoot();
  const m = root[bucket];
  if (!m || typeof m !== "object") return;
  let changed = false;
  for (const k of Object.keys(m)) {
    if (!allow.has(k)) {
      delete m[k];
      changed = true;
    }
  }
  if (changed) {
    if (Object.keys(m).length === 0) delete root[bucket];
    writeRoot(root);
  }
}
