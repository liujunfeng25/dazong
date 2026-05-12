/**
 * UVC 原生封装 + 测试日志（与串口 [ScaleSerial] 类似，便于云打包一次排障）。
 */
import { SCALE_SERIAL_NATIVE_PLUGIN_ID } from "../config/scaleSerial";
import { UVC_DEFAULT_DEVICE_INDEX, UVC_OPEN_TIMEOUT_MS } from "../config/uvcCamera";

const TAG = "[UvcCamera]";
const MEM_LINES = 420;
const memLines: string[] = [];

function push(line: string) {
  const ts = new Date().toLocaleString("zh-CN", { hour12: false });
  const row = `${ts} ${line}`;
  console.log(TAG, line);
  memLines.push(row);
  while (memLines.length > MEM_LINES) memLines.shift();
}

/** 单行摘要原生回调，便于一眼判断卡在哪一步 */
function summarizeNativeJson(o: Record<string, unknown> | null | undefined): string {
  if (!o || typeof o !== "object") return "(回调非对象)";
  const parts: string[] = [];
  if ("ok" in o) parts.push(`ok=${String(o.ok)}`);
  if (typeof o.err === "string" && o.err) parts.push(`err=${o.err}`);
  if (typeof o.hint === "string" && o.hint) parts.push(`hint=${(o.hint as string).slice(0, 120)}`);
  if (o.already === true) parts.push("already=true");
  if (typeof o.path === "string" && o.path) {
    const p = o.path as string;
    parts.push(`path=${p.length > 64 ? `${p.slice(0, 32)}…${p.slice(-24)}` : p}`);
  }
  if (typeof o.uri === "string" && o.uri) parts.push(`uri.len=${(o.uri as string).length}`);
  if (Array.isArray(o.devices)) parts.push(`devices.len=${o.devices.length}`);
  if (typeof o.text === "string" && o.text) parts.push(`text.len=${(o.text as string).length}`);
  if (parts.length) return parts.join(" | ");
  return `keys=${Object.keys(o).join(",")}`;
}

function diagRuntimeHead(): string {
  let extra = "";
  // #ifdef APP-PLUS
  try {
    const si = uni.getSystemInfoSync() as Record<string, unknown>;
    const model = String(si.model ?? "");
    const os = String(si.osName ?? si.platform ?? "");
    const ver = String(si.osVersion ?? "");
    const uniVer = String(si.uniCompilerVersion ?? si.uniRuntimeVersion ?? "");
    extra = `机型: ${model} | 系统: ${os} ${ver}${uniVer ? ` | uni: ${uniVer}` : ""}\n`;
  } catch (e) {
    extra = `getSystemInfoSync: ${String(e)}\n`;
  }
  // #endif
  return extra;
}

export function getUvcCameraDiagText(): string {
  const head =
    "=== 大综智能收货 · UVC/锁定留痕 诊断（复制整段发研发）===\n" +
    diagRuntimeHead() +
    `原生 module: ${SCALE_SERIAL_NATIVE_PLUGIN_ID}（UVC 与串口同源）\n` +
    `默认设备 index: ${UVC_DEFAULT_DEVICE_INDEX}\n` +
    `open 超时(ms): ${UVC_OPEN_TIMEOUT_MS}\n` +
    "说明：搜索 [LCK] 可看一次「锁定读数」完整决策链；搜索 invoke 可看每次原生入参/超时。\n" +
    "--- JS 侧流水（旧 → 新）---\n";
  return head + (memLines.length ? memLines.join("\n") : "(尚无流水)");
}

export function clearUvcCameraDiag() {
  memLines.length = 0;
  push("日志已清空");
}

function listModFunctionKeys(mod: Record<string, unknown>): string {
  try {
    return Object.keys(mod)
      .filter((k) => typeof mod[k] === "function")
      .sort()
      .join(", ");
  } catch {
    return "(无法枚举)";
  }
}

function getMod(): Record<string, unknown> | null {
  // #ifdef APP-PLUS
  try {
    const m = uni.requireNativePlugin(SCALE_SERIAL_NATIVE_PLUGIN_ID) as Record<string, unknown> | null;
    if (m && typeof m === "object" && typeof m.uvcListDevices === "function") {
      return m;
    }
    if (m && typeof m === "object") {
      push(
        `getMod: 插件对象已返回但无 uvcListDevices → 请更新含 UVC 的 dazong-serial-scale.aar 并重打基座。可调方法: ${listModFunctionKeys(m)}`
      );
    } else {
      push(`getMod: requireNativePlugin 返回空或非对象（检查 manifest 是否勾选本地插件、插件 id 是否为 ${SCALE_SERIAL_NATIVE_PLUGIN_ID}）`);
    }
  } catch (e) {
    push(`getMod: requireNativePlugin 抛错 ${String(e)}`);
  }
  // #endif
  return null;
}

export function isUvcNativeAvailable(): boolean {
  return getMod() != null;
}

export type UvcDeviceInfo = {
  index: number;
  /** Android UsbDevice.getDeviceId()，与公司 SmartReceiv uvc_${id} 一致，可传给 uvcOpen({ deviceId }) */
  deviceId?: number;
  vendorId: number;
  productId: number;
  label: string;
};

export async function uvcListDevices(): Promise<UvcDeviceInfo[]> {
  push("uvcListDevices 调用");
  const o = await invokeJson("uvcListDevices", {}, 12000);
  if (!o || o.ok !== true) {
    push(`uvcListDevices 失败 | ${summarizeNativeJson(o)} | raw=${JSON.stringify(o).slice(0, 600)}`);
    return [];
  }
  const arr = (o.devices as Record<string, unknown>[]) || [];
  const list: UvcDeviceInfo[] = arr.map((d) => ({
    index: Number(d.index),
    deviceId: typeof d.deviceId === "number" ? Number(d.deviceId) : undefined,
    vendorId: Number(d.vendorId),
    productId: Number(d.productId),
    label: String(d.label || ""),
  }));
  const brief =
    list.length === 0
      ? "[]"
      : list
          .map((d) => `[#${d.index} id=${d.deviceId ?? "?"} vid=${d.vendorId} pid=${d.productId}]`)
          .join(" ");
  push(`uvcListDevices 成功 count=${list.length} ${brief}`);
  return list;
}

function invokeJson(
  method: string,
  opts: Record<string, unknown>,
  timeoutMs: number
): Promise<Record<string, unknown>> {
  const tReq = Date.now();
  const mod = getMod();
  if (!mod || typeof mod[method] !== "function") {
    const has = mod && typeof mod === "object" ? listModFunctionKeys(mod as Record<string, unknown>) : "(无 mod)";
    push(
      `invokeJson 跳过: method=${method} 不存在 | mod可调: ${has.slice(0, 500)}${has.length > 500 ? "…" : ""}`
    );
    return Promise.resolve({ ok: false, err: "native_plugin_missing", hint: SCALE_SERIAL_NATIVE_PLUGIN_ID });
  }
  push(`invokeJson → ${method} opts=${JSON.stringify(opts)} 超时=${timeoutMs}ms`);
  return new Promise((resolve) => {
    let done = false;
    const timer = setTimeout(() => {
      if (done) return;
      done = true;
      push(
        `invokeJson ✖ ${method} 在 ${timeoutMs}ms 内无回调（常见：USB 授权弹窗被遮罩挡住、原生死锁、未打新 AAR）已耗时=${Date.now() - tReq}ms`
      );
      resolve({ ok: false, err: "timeout", hint: method });
    }, timeoutMs);
    try {
      (mod[method] as (o: Record<string, unknown>, cb: (r: unknown) => void) => void)(opts, (ret: unknown) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        const elapsed = Date.now() - tReq;
        const o = (ret && typeof ret === "object" ? ret : {}) as Record<string, unknown>;
        const raw = JSON.stringify(o);
        const sum = summarizeNativeJson(o);
        push(`invokeJson ← ${method} 耗时=${elapsed}ms | ${sum}`);
        if (raw.length > 700) {
          push(`invokeJson ← ${method} raw=${raw.slice(0, 700)}…(共${raw.length}字)`);
        } else {
          push(`invokeJson ← ${method} raw=${raw}`);
        }
        resolve(o);
      });
    } catch (e) {
      if (!done) {
        done = true;
        clearTimeout(timer);
        push(`invokeJson ✖ ${method} 同步抛错 ${String(e)}`);
        resolve({ ok: false, err: "invoke_error", hint: String(e) });
      }
    }
  });
}

/** 与原生 uvcOpen options 对齐：底部可见预览条等 */
export type UvcOpenExtraOptions = {
  previewVisible?: boolean;
  previewHeightDp?: number;
  previewGravity?: "bottom" | "top";
  /** 优先于 deviceIndex，与原生 uvcListDevices 返回的 deviceId 对应 */
  deviceId?: number;
};

export async function uvcOpen(
  deviceIndex: number = UVC_DEFAULT_DEVICE_INDEX,
  extra?: UvcOpenExtraOptions
): Promise<boolean> {
  const opts: Record<string, unknown> = { deviceIndex };
  if (extra?.deviceId != null && extra.deviceId >= 0) {
    opts.deviceId = extra.deviceId;
  }
  if (extra?.previewVisible === true) {
    opts.previewVisible = true;
  }
  if (extra?.previewHeightDp != null) {
    opts.previewHeightDp = extra.previewHeightDp;
  }
  if (extra?.previewGravity) {
    opts.previewGravity = extra.previewGravity;
  }
  push(`uvcOpen 入参 ${JSON.stringify(opts)}`);
  const ret = await invokeJson("uvcOpen", opts, UVC_OPEN_TIMEOUT_MS);
  const ok = ret.ok === true;
  push(`uvcOpen 判定 opened=${ok} | ${summarizeNativeJson(ret)}`);
  return ok;
}

export type UvcPreviewStatus = {
  ok: boolean;
  deviceCount: number;
  hasDevice: boolean;
  opened: boolean;
  previewSurfaceReady: boolean;
  previewStarted: boolean;
};

/** 查询 UVC 是否已开流（用于锁定瞬间跳过重复 open）。旧 AAR 无此方法时返回 null。 */
export async function uvcFetchPreviewStatus(): Promise<UvcPreviewStatus | null> {
  const mod = getMod();
  if (!mod || typeof mod.uvcPreviewStatus !== "function") {
    return null;
  }
  const o = await invokeJson("uvcPreviewStatus", {}, 6000);
  if (o.ok !== true) {
    push(`uvcPreviewStatus 失败 ${summarizeNativeJson(o)}`);
    return null;
  }
  return {
    ok: true,
    deviceCount: Number(o.deviceCount ?? 0),
    hasDevice: o.hasDevice === true,
    opened: o.opened === true,
    previewSurfaceReady: o.previewSurfaceReady === true,
    previewStarted: o.previewStarted === true,
  };
}

/** 称重作业台进入后预热：底部常驻 UVC 预览（无设备则仅打日志，不调 open） */
export async function uvcWarmTerminalPreview(deviceIndex: number): Promise<{
  ok: boolean;
  noDevices?: boolean;
}> {
  push("uvcWarmTerminalPreview 开始");
  if (!isUvcNativeAvailable()) {
    return { ok: false };
  }
  const devices = await uvcListDevices();
  if (devices.length === 0) {
    push("uvcWarmTerminalPreview：设备数 0，跳过 open");
    return { ok: false, noDevices: true };
  }
  const idx = Math.min(Math.max(0, deviceIndex), devices.length - 1);
  const chosen = devices[idx];
  const openExtra: UvcOpenExtraOptions = {
    previewVisible: true,
    previewHeightDp: 200,
    previewGravity: "bottom",
  };
  if (chosen.deviceId != null && chosen.deviceId >= 0) {
    openExtra.deviceId = chosen.deviceId;
  }
  const opened = await uvcOpen(idx, openExtra);
  push(`uvcWarmTerminalPreview 结束 opened=${opened}`);
  return { ok: opened };
}

export async function uvcCapture(): Promise<{ path: string; uri: string } | null> {
  push("uvcCapture 入参 {}");
  const ret = await invokeJson("uvcCapture", {}, 25000);
  if (ret.ok === true && typeof ret.path === "string") {
    const path = ret.path as string;
    const uri = typeof ret.uri === "string" ? (ret.uri as string) : `file://${path}`;
    push(`uvcCapture 成功 path.len=${path.length}`);
    return { path, uri };
  }
  push(`uvcCapture 失败 | ${summarizeNativeJson(ret)}`);
  return null;
}

export async function uvcClose(): Promise<void> {
  push("uvcClose 调用");
  await invokeJson("uvcClose", {}, 15000);
}

export async function uvcFetchNativeLog(): Promise<string> {
  const mod = getMod();
  if (!mod || typeof mod.uvcGetLog !== "function") return "(无 uvcGetLog)";
  const uvcGetLog = mod.uvcGetLog as (
    opts: Record<string, unknown>,
    cb: (ret: unknown) => void
  ) => void;
  return new Promise((resolve) => {
    try {
      uvcGetLog({}, (ret: unknown) => {
        const o = ret as Record<string, unknown>;
        resolve(typeof o.text === "string" ? (o.text as string) : JSON.stringify(ret));
      });
    } catch (e) {
      resolve(String(e));
    }
  });
}

export async function uvcClearNativeLog(): Promise<void> {
  const mod = getMod();
  if (!mod || typeof mod.uvcClearLog !== "function") return;
  const uvcClearLog = mod.uvcClearLog as (
    opts: Record<string, unknown>,
    cb: (ret: unknown) => void
  ) => void;
  uvcClearLog({}, () => {});
}

/** 无 UVC 或失败时：系统相机拍一张 */
export function captureWithSystemCamera(): Promise<string | null> {
  push("chooseImage 即将调起 sourceType=camera count=1（若卡住：检查是否仍有 showLoading mask 或权限）");
  return new Promise((resolve) => {
    uni.chooseImage({
      count: 1,
      sourceType: ["camera"],
      success(res) {
        const p = res.tempFilePaths && res.tempFilePaths[0];
        const n = (res.tempFilePaths && res.tempFilePaths.length) || 0;
        push(
          `chooseImage success tempFilePaths=${n} first=${p ? (p.length > 56 ? `${p.slice(0, 40)}…${p.slice(-12)}` : p) : "empty"}`
        );
        resolve(p || null);
      },
      fail(err) {
        const e = err as Record<string, unknown> | undefined;
        const msg = e && typeof e.errMsg === "string" ? e.errMsg : JSON.stringify(err);
        push(`chooseImage fail errMsg=${msg}`);
        resolve(null);
      },
    });
  });
}

/** 关闭外层可能存在的 showLoading(mask)，否则 chooseImage 被挡住会一直卡住 */
function dismissBlockingLoading() {
  try {
    uni.hideLoading();
    push("[LCK] 已调用 uni.hideLoading()（降级系统相机前，避免 mask 挡相机）");
  } catch (e) {
    push(`[LCK] uni.hideLoading 异常 ${String(e)}`);
  }
}

/**
 * 锁定用：优先 UVC（有设备且 open 成功则直接拍），失败则系统相机。
 * 注意：调用方若使用了 showLoading({ mask: true })，降级系统相机前必须先关遮罩，否则界面会卡在「留痕拍照」。
 */
export async function captureLockPhotoBestEffort(deviceIndex: number): Promise<{
  uri: string;
  source: "uvc" | "system";
} | null> {
  const cid = `LCK-${Date.now().toString(36)}`;
  const t0 = Date.now();
  const lap = (msg: string) => push(`[${cid}] +${Date.now() - t0}ms ${msg}`);

  lap(`开始 captureLockPhotoBestEffort 请求 deviceIndex=${deviceIndex}`);

  const pluginOk = isUvcNativeAvailable();
  lap(`isUvcNativeAvailable=${pluginOk}（false=未集成/旧 AAR；true 才会枚举 USB）`);

  if (pluginOk) {
    const devices = await uvcListDevices();
    lap(`枚举结束 devices.length=${devices.length}`);
    if (devices.length > 0) {
      const idx = Math.min(Math.max(0, deviceIndex), devices.length - 1);
      if (idx !== deviceIndex) {
        lap(`index 钳位 ${deviceIndex} -> ${idx}（共 ${devices.length} 路）`);
      }
      const chosen = devices[idx];
      const openExtra: UvcOpenExtraOptions = {
        previewVisible: true,
        previewHeightDp: 200,
        previewGravity: "bottom",
      };
      if (chosen.deviceId != null && chosen.deviceId >= 0) {
        openExtra.deviceId = chosen.deviceId;
      }
      const st = await uvcFetchPreviewStatus();
      lap(
        `previewStatus ${st ? `opened=${st.opened} previewStarted=${st.previewStarted}` : "null(旧AAR或未就绪)"}`
      );
      let readyToCapture = st?.opened === true && st.previewStarted === true;
      if (!readyToCapture) {
        const opened = await uvcOpen(idx, openExtra);
        lap(`uvcOpen 结束 opened=${opened}`);
        readyToCapture = opened;
      } else {
        lap("已预热预览，跳过重复 uvcOpen");
      }
      if (readyToCapture) {
        const cap = await uvcCapture();
        lap(`uvcCapture 结束 cap=${cap ? "有文件" : "null"}`);
        if (cap) {
          lap(`返回 UVC 成功 uri.len=${cap.uri.length}`);
          return { uri: cap.uri, source: "uvc" };
        }
        lap("决策：UVC 拍照失败 → 降级系统相机");
      } else {
        lap("决策：uvcOpen 未 ok（无授权/设备忙/索引错等）→ 降级系统相机");
      }
    } else {
      lap("决策：设备数 0（未接 UVC 或内核未枚举）→ 跳过 open/capture，直接系统相机");
    }
  } else {
    lap("决策：原生无 uvcListDevices → 直接系统相机");
  }

  dismissBlockingLoading();
  lap("已 dismissLoading，80ms 后 chooseImage");
  await new Promise<void>((resolve) => setTimeout(resolve, 80));
  const sys = await captureWithSystemCamera();
  lap(`chooseImage 结束 sys=${sys ? `有路径 len=${sys.length}` : "null"}`);
  if (sys) {
    lap(`返回 SYSTEM 成功 total=${Date.now() - t0}ms`);
    return { uri: sys, source: "system" };
  }
  lap(`返回 null（全程 ${Date.now() - t0}ms）`);
  return null;
}
