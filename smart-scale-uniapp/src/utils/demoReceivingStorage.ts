/** 演示模式：每行已确认实收 kg + 可选少收原因，供列表与作业台同步 */
const KEY = "smart_scale_demo_receiving_line_kg";

export type DemoLinePack = {
  kg: number;
  shortage?: { code: string; detail?: string };
  /** 锁定读数时拍摄的留痕图（本机 file:// 或临时路径） */
  lockPhotoUri?: string;
  lockPhotoSource?: "uvc" | "system";
};
type RawEntry = number | DemoLinePack;

function normalizeEntry(e: RawEntry | undefined): DemoLinePack | null {
  if (e == null) return null;
  if (typeof e === "number") return { kg: e };
  if (typeof e === "object" && typeof (e as DemoLinePack).kg === "number") {
    const p = e as DemoLinePack;
    const out: DemoLinePack = { kg: p.kg };
    if (p.shortage) out.shortage = p.shortage;
    if (typeof p.lockPhotoUri === "string" && p.lockPhotoUri.length > 0) {
      out.lockPhotoUri = p.lockPhotoUri;
    }
    if (p.lockPhotoSource === "system" || p.lockPhotoSource === "uvc") {
      out.lockPhotoSource = p.lockPhotoSource;
    }
    return out;
  }
  return null;
}

export function loadDemoOrderMap(orderNo: string): Record<string, DemoLinePack> {
  try {
    const all = uni.getStorageSync(KEY) as Record<string, Record<string, RawEntry>> | null;
    if (!all || typeof all !== "object") return {};
    const row = all[orderNo];
    if (!row || typeof row !== "object") return {};
    const out: Record<string, DemoLinePack> = {};
    Object.entries(row).forEach(([k, v]) => {
      const p = normalizeEntry(v);
      if (p) out[k] = p;
    });
    return out;
  } catch {
    return {};
  }
}

export function saveDemoLinePack(orderNo: string, lineId: string, pack: DemoLinePack) {
  const all = (uni.getStorageSync(KEY) as Record<string, Record<string, RawEntry>>) || {};
  if (!all[orderNo]) all[orderNo] = {};
  all[orderNo][lineId] = pack;
  uni.setStorageSync(KEY, all);
}

export function removeDemoConfirmedLine(orderNo: string, lineId: string) {
  const all = (uni.getStorageSync(KEY) as Record<string, Record<string, RawEntry>>) || {};
  if (!all[orderNo]) return;
  delete all[orderNo][lineId];
  if (Object.keys(all[orderNo]).length === 0) delete all[orderNo];
  uni.setStorageSync(KEY, all);
}

export function clearDemoOrder(orderNo: string) {
  const all = (uni.getStorageSync(KEY) as Record<string, Record<string, RawEntry>>) || {};
  delete all[orderNo];
  uni.setStorageSync(KEY, all);
}

export function countDemoConfirmedForOrder(orderNo: string, lineIds: string[]): number {
  const map = loadDemoOrderMap(orderNo);
  return lineIds.filter((id) => map[id] != null).length;
}
