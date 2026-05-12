import {
  SCALE_SERIAL_BAUD,
  SCALE_SERIAL_DEVICE_PATH,
  SCALE_SERIAL_HTTP_URL,
  SCALE_SERIAL_NATIVE_PLUGIN_ID,
  SCALE_SERIAL_NATIVE_READ_HARD_CAP_MS,
  SCALE_SERIAL_NATIVE_READ_WAIT_MS,
  SCALE_SERIAL_OPEN_TIMEOUT_MS,
  SCALE_SERIAL_POLL_HEX,
  SCALE_SERIAL_READ_TIMEOUT_MS,
} from "../config/scaleSerial";
import { tryParseWeightKg } from "../config/scaleBle";

const TAG = "[ScaleSerial]";

const MAX_DIAG_LINES = 120;
const diagLines: string[] = [];

function safeStringify(v: unknown, maxLen: number): string {
  if (v === undefined) return "undefined";
  if (v === null) return "null";
  if (typeof v === "string") {
    return v.length > maxLen ? `${v.slice(0, maxLen)}…(截断)` : v;
  }
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    const s = JSON.stringify(v);
    return s.length > maxLen ? `${s.slice(0, maxLen)}…(截断)` : s;
  } catch {
    return String(v).slice(0, maxLen);
  }
}

function pushDiag(line: string) {
  const ts = new Date().toLocaleString("zh-CN", { hour12: false });
  diagLines.push(`${ts} ${line}`);
  while (diagLines.length > MAX_DIAG_LINES) diagLines.shift();
}

/** 页面按钮写入备注，会出现在「串口诊断」报告里 */
export function noteScaleSerialDiag(text: string) {
  pushDiag(`[手动备注] ${text}`);
}

function log(...args: unknown[]) {
  console.log(TAG, ...args);
  pushDiag(args.map((a) => safeStringify(a, 900)).join(" "));
}

function logWarn(...args: unknown[]) {
  console.warn(TAG, ...args);
  pushDiag(`[WARN] ${args.map((a) => safeStringify(a, 900)).join(" ")}`);
}

function logErr(...args: unknown[]) {
  console.error(TAG, ...args);
  pushDiag(`[ERR] ${args.map((a) => safeStringify(a, 900)).join(" ")}`);
}

function parseHttpPayload(data: unknown): number | null {
  if (data == null) return null;
  if (typeof data === "number" && Number.isFinite(data)) return data;
  if (typeof data === "object" && data !== null && "kg" in data) {
    const v = Number((data as { kg?: unknown }).kg);
    return Number.isFinite(v) ? v : null;
  }
  const text = typeof data === "string" ? data : JSON.stringify(data);
  const lines = text.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i];
    const enc = new TextEncoder().encode(line);
    const parsed = tryParseWeightKg(enc.buffer);
    if (parsed) {
      const n = parseFloat(parsed);
      if (Number.isFinite(n)) return n;
    }
    const m = line.match(/([-+]?\d+\.?\d*)/);
    if (m) {
      const n = parseFloat(m[1]);
      if (Number.isFinite(n) && Math.abs(n) < 1e6) return n;
    }
  }
  return null;
}

/** 原生插件 SerialScaleModule.readKg 返回 { ok, kg, err?, raw? } */
function parseNativePluginKg(ret: unknown): number | null {
  if (ret != null && typeof ret === "object" && "ok" in ret) {
    const o = ret as {
      ok?: boolean;
      kg?: unknown;
      err?: string;
      raw?: string;
      hint?: string;
    };
    if (o.ok === true && typeof o.kg === "number" && Number.isFinite(o.kg)) {
      return o.kg;
    }
    if (o.ok === false) {
      logWarn("readKg 回调未解析出重量", {
        err: o.err,
        hint: o.hint,
        rawPreview: o.raw?.slice?.(0, 200),
      });
    }
  }
  return parseHttpPayload(ret);
}

let nativeSerialOpened = false;

/**
 * 供现场截图发研发：含设备信息、当前配置、与 [ScaleSerial] 同源的控制台流水。
 */
export function getScaleSerialDiagnosticsText(): string {
  const out: string[] = [];
  out.push("=== 大综智能秤 · 串口诊断（请整屏截图或点「复制全文」发研发）===");
  out.push(`报告生成: ${new Date().toLocaleString("zh-CN", { hour12: false })}`);
  try {
    const si = uni.getSystemInfoSync();
    out.push("--- 设备 / 运行环境 ---");
    out.push(
      safeStringify(
        {
          brand: si.brand,
          model: si.model,
          platform: si.platform,
          system: si.system,
          appName: si.appName,
          appVersion: si.appVersion,
          appVersionCode: si.appVersionCode,
          uniPlatform: si.uniPlatform,
          osName: si.osName,
          osVersion: si.osVersion,
          deviceId: si.deviceId,
        },
        2500
      )
    );
  } catch (e) {
    out.push(`(获取系统信息失败: ${String(e)})`);
  }
  out.push("--- 当前串口配置（与 scaleSerial.ts 一致）---");
  out.push(`原生插件 ID: ${SCALE_SERIAL_NATIVE_PLUGIN_ID.trim() || "(空，不走原生)"}`);
  out.push(`串口路径: ${SCALE_SERIAL_DEVICE_PATH}`);
  out.push(`波特率: ${SCALE_SERIAL_BAUD}`);
  out.push(`open 超时(ms): ${SCALE_SERIAL_OPEN_TIMEOUT_MS}`);
  out.push(`read 回调超时(ms): ${SCALE_SERIAL_READ_TIMEOUT_MS}`);
  out.push(`原生读等待 maxWaitMs: ${SCALE_SERIAL_NATIVE_READ_WAIT_MS}`);
  out.push(`原生读硬上限 hardCapMs: ${SCALE_SERIAL_NATIVE_READ_HARD_CAP_MS}`);
  out.push(`读前 pollHex: ${SCALE_SERIAL_POLL_HEX.trim() || "(空)"}`);
  out.push(`HTTP 回退 URL: ${SCALE_SERIAL_HTTP_URL.trim() || "(空)"}`);
  out.push(`JS 缓存「串口已打开」: ${nativeSerialOpened ? "是" : "否"}`);
  out.push("--- 最近流水（旧 → 新，与控制台 [ScaleSerial] 同条）---");
  if (diagLines.length === 0) out.push("(尚无流水：请先点一次「读秤」再打开本报告)");
  else out.push(...diagLines);
  return out.join("\n");
}

/** 超时或失败后尽量关串口，避免底层阻塞后状态错乱 */
function tryCloseNativeSerial(reason: string) {
  nativeSerialOpened = false;
  const id = SCALE_SERIAL_NATIVE_PLUGIN_ID.trim();
  if (!id) return;
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const mod = uni.requireNativePlugin(id) as any;
    if (mod && typeof mod.closePort === "function") {
      log("tryCloseNativeSerial", reason);
      mod.closePort(() => {
        log("closePort 已回调");
      });
    }
  } catch (e) {
    logWarn("closePort 异常（可忽略）", e);
  }
}

function ensureNativePluginOpen(): Promise<boolean> {
  const id = SCALE_SERIAL_NATIVE_PLUGIN_ID.trim();
  if (!id) return Promise.resolve(false);
  if (nativeSerialOpened) {
    log("串口已打开（缓存），跳过 open");
    return Promise.resolve(true);
  }
  const ms = Math.max(3000, SCALE_SERIAL_OPEN_TIMEOUT_MS);
  return new Promise((resolve) => {
    let settled = false;
    const finish = (ok: boolean) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      nativeSerialOpened = ok;
      if (!ok) tryCloseNativeSerial("open 失败或超时");
      resolve(ok);
    };
    const timer = setTimeout(() => {
      logErr(`open 超过 ${ms}ms 仍未回调，放弃等待`);
      finish(false);
    }, ms);
    try {
      log("requireNativePlugin", id);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const mod = uni.requireNativePlugin(id) as any;
      if (!mod || typeof mod.open !== "function") {
        logErr("插件对象无效或没有 open 方法", { hasMod: !!mod });
        finish(false);
        return;
      }
      log("open 串口", { path: SCALE_SERIAL_DEVICE_PATH, baudRate: SCALE_SERIAL_BAUD });
      mod.open(
        { path: SCALE_SERIAL_DEVICE_PATH, baudRate: SCALE_SERIAL_BAUD },
        (r: { ok?: boolean; err?: string }) => {
          if (settled) {
            logWarn("open 迟到回调已忽略", r);
            return;
          }
          const ok = !!r?.ok;
          if (ok) {
            log("open 成功", r);
          } else {
            logErr("open 失败", r);
          }
          finish(ok);
        }
      );
    } catch (e) {
      logErr("open 异常", e);
      finish(false);
    }
  });
}

function tryNativePluginRead(): Promise<number | null> {
  const id = SCALE_SERIAL_NATIVE_PLUGIN_ID.trim();
  if (!id) return Promise.resolve(null);
  const ms = Math.max(
    3000,
    SCALE_SERIAL_READ_TIMEOUT_MS,
    SCALE_SERIAL_NATIVE_READ_HARD_CAP_MS + 5000
  );
  return new Promise((resolve) => {
    let settled = false;
    const settle = (kg: number | null) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(kg);
    };
    const timer = setTimeout(() => {
      logErr(`readKg 超过 ${ms}ms 仍未回调，放弃等待并尝试关串口`);
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      tryCloseNativeSerial("readKg 回调超时");
      resolve(null);
    }, ms);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const mod = uni.requireNativePlugin(id) as any;
      if (!mod || typeof mod.readKg !== "function") {
        logErr("readKg 方法不存在");
        settle(null);
        return;
      }
      const readOpts = {
        path: SCALE_SERIAL_DEVICE_PATH,
        baudRate: SCALE_SERIAL_BAUD,
        maxWaitMs: SCALE_SERIAL_NATIVE_READ_WAIT_MS,
        hardCapMs: SCALE_SERIAL_NATIVE_READ_HARD_CAP_MS,
        pollHex: SCALE_SERIAL_POLL_HEX.trim(),
      };
      log("调用 readKg …", readOpts);
      mod.readKg(readOpts, (ret: unknown) => {
        if (settled) {
          logWarn("readKg 迟到回调已忽略", ret);
          return;
        }
        try {
          log("readKg 原始回调", typeof ret === "object" && ret !== null ? JSON.stringify(ret) : String(ret));
        } catch {
          log("readKg 原始回调(无法 JSON 化)", ret);
        }
        const kg = parseNativePluginKg(ret);
        if (kg != null) {
          log("解析成功 kg =", kg);
        } else {
          logWarn("解析后 kg 为 null，请对照上面 raw/err");
        }
        settle(kg);
      });
    } catch (e) {
      logErr("readKg 调用异常", e);
      settle(null);
    }
  });
}

/**
 * 从串口侧取当前重量（kg）。优先原生插件，其次 HTTP。
 */
export async function readScaleWeightKg(): Promise<number | null> {
  const id = SCALE_SERIAL_NATIVE_PLUGIN_ID.trim();
  log("readScaleWeightKg 开始", {
    pluginId: id || "(空)",
    httpUrl: SCALE_SERIAL_HTTP_URL.trim() || "(空)",
  });

  if (id) {
    const ok = await ensureNativePluginOpen();
    if (!ok) {
      logErr("串口未打开，终止");
      log("[结果] readScaleWeightKg 结束", { kg: null, step: "open_failed" });
      return null;
    }
    const kg = await tryNativePluginRead();
    if (kg != null) {
      log("[结果] readScaleWeightKg 结束", { kg, step: "native_ok" });
      return kg;
    }
    logWarn("原生读数无有效 kg，若配置了 HTTP 将回退");
  }

  const url = SCALE_SERIAL_HTTP_URL.trim();
  if (!url) {
    logErr("无 HTTP 回退地址且原生未读出重量");
    log("[结果] readScaleWeightKg 结束", { kg: null, step: "no_http_fallback" });
    return null;
  }

  try {
    log("HTTP GET", url);
    const res = await uni.request({
      url,
      method: "GET",
      timeout: 4000,
    });
    log("HTTP 响应", { statusCode: res.statusCode, dataType: typeof res.data });
    if (res.statusCode !== 200) {
      log("[结果] readScaleWeightKg 结束", {
        kg: null,
        step: "http_bad_status",
        statusCode: res.statusCode,
      });
      return null;
    }
    const kg = parseHttpPayload(res.data);
    if (kg != null) log("HTTP 解析 kg =", kg);
    else logWarn("HTTP 载荷未能解析为 kg", res.data);
    log("[结果] readScaleWeightKg 结束", {
      kg,
      step: kg != null ? "http_ok" : "http_parse_fail",
    });
    return kg;
  } catch (e) {
    logErr("HTTP 请求失败", e);
    log("[结果] readScaleWeightKg 结束", { kg: null, step: "http_exception" });
    return null;
  }
}
