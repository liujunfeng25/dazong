/** 称重锁定成功后的本机留痕（供 dashboard 展示） */
export const SMART_SCALE_LAST_LOCK_PHOTO_KEY = "smart_scale_last_lock_photo";

export type SmartScaleLastLockPhoto = {
  uri: string;
  orderTitle: string;
  order_no: string;
  lineName: string;
  lineNo: number | null;
  ts: number;
  source: "uvc" | "system";
};

export function saveSmartScaleLastLockPhoto(p: SmartScaleLastLockPhoto): void {
  try {
    uni.setStorageSync(SMART_SCALE_LAST_LOCK_PHOTO_KEY, p);
  } catch {
    /* ignore */
  }
}

export function readSmartScaleLastLockPhoto(): SmartScaleLastLockPhoto | null {
  try {
    const v = uni.getStorageSync(SMART_SCALE_LAST_LOCK_PHOTO_KEY) as unknown;
    if (!v || typeof v !== "object") return null;
    const o = v as Record<string, unknown>;
    const uri = typeof o.uri === "string" ? o.uri : "";
    if (!uri) return null;
    const source = o.source === "system" ? "system" : "uvc";
    return {
      uri,
      orderTitle: typeof o.orderTitle === "string" ? o.orderTitle : "",
      order_no: typeof o.order_no === "string" ? o.order_no : "",
      lineName: typeof o.lineName === "string" ? o.lineName : "",
      lineNo: typeof o.lineNo === "number" && Number.isFinite(o.lineNo) ? o.lineNo : null,
      ts: typeof o.ts === "number" && Number.isFinite(o.ts) ? o.ts : Date.now(),
      source,
    };
  } catch {
    return null;
  }
}
