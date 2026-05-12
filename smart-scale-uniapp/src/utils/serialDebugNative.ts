import {
  SCALE_SERIAL_BAUD,
  SCALE_SERIAL_DEVICE_PATH,
  SCALE_SERIAL_NATIVE_PLUGIN_ID,
} from "../config/scaleSerial";

const TAG = "[SerialDebug]";
const MAX_LINES = 220;
const logLines: string[] = [];

function nowStr(): string {
  return new Date().toLocaleString("zh-CN", { hour12: false });
}

export function appendSerialDebugLog(msg: string, extra?: unknown) {
  let tail = "";
  if (extra !== undefined) {
    try {
      tail =
        typeof extra === "object" && extra !== null
          ? ` ${JSON.stringify(extra)}`
          : ` ${String(extra)}`;
    } catch {
      tail = ` ${String(extra)}`;
    }
  }
  const full = `[${nowStr()}] ${msg}${tail}`;
  logLines.push(full);
  while (logLines.length > MAX_LINES) logLines.shift();
  console.log(TAG, full);
}

export function clearSerialDebugLog() {
  logLines.length = 0;
}

export function getSerialDebugLogText(): string {
  return logLines.join("\n");
}

export function buildSerialDebugReport(path: string, baud: number): string {
  const parts: string[] = [];
  parts.push("=== 大综智能收货 · 串口调试报告（可复制发研发）===");
  parts.push(`生成: ${nowStr()}`);
  parts.push(`配置 path=${path} baud=${baud}`);
  parts.push(`插件 ID: ${SCALE_SERIAL_NATIVE_PLUGIN_ID}`);
  try {
    const si = uni.getSystemInfoSync();
    parts.push(
      `设备: ${si.brand ?? ""} ${si.model ?? ""} | ${si.system ?? ""} | App ${si.appVersion ?? ""}`
    );
  } catch {
    parts.push("(系统信息不可用)");
  }
  parts.push("--- 操作流水 ---");
  parts.push(logLines.length ? logLines.join("\n") : "(尚无流水)");
  return parts.join("\n");
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function requireMod(): any {
  const id = SCALE_SERIAL_NATIVE_PLUGIN_ID.trim();
  if (!id) throw new Error("未配置 SCALE_SERIAL_NATIVE_PLUGIN_ID");
  const mod = uni.requireNativePlugin(id);
  if (!mod) throw new Error("requireNativePlugin 返回空");
  return mod;
}

function invoke<T>(
  method: string,
  options: Record<string, unknown>,
  timeoutMs: number
): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => {
      reject(new Error(`${method} 超时 ${timeoutMs}ms`));
    }, timeoutMs);
    try {
      const mod = requireMod();
      const fn = mod[method];
      if (typeof fn !== "function") {
        clearTimeout(t);
        reject(new Error(`原生无方法: ${method}`));
        return;
      }
      fn.call(mod, options || {}, (ret: T) => {
        clearTimeout(t);
        resolve(ret);
      });
    } catch (e) {
      clearTimeout(t);
      reject(e);
    }
  });
}

export type DebugStatusRet = {
  opened?: boolean;
  lastPath?: string;
  lastBaud?: number;
  inAvailable?: number;
};

export async function nativeDebugStatus(): Promise<DebugStatusRet> {
  const r = await invoke<DebugStatusRet>("debugStatus", {}, 5000);
  appendSerialDebugLog("debugStatus 回调", r);
  return r;
}

export type DebugWriteRet = {
  ok?: boolean;
  sentLen?: number;
  sentHex?: string;
  err?: string;
};

export async function nativeDebugWriteHex(hex: string): Promise<DebugWriteRet> {
  const r = await invoke<DebugWriteRet>("debugWriteHex", { hex }, 8000);
  appendSerialDebugLog("debugWriteHex 回调", r);
  return r;
}

export type DebugReadRet = {
  ok?: boolean;
  err?: string;
  byteLen?: number;
  hex?: string;
  asciiEscaped?: string;
  ticks?: unknown[];
  maxWaitMs?: number;
  untilCrlf?: boolean;
};

export async function nativeDebugReadRaw(opts: {
  maxWaitMs: number;
  maxBytes: number;
  untilCrlf: boolean;
}): Promise<DebugReadRet> {
  const r = await invoke<DebugReadRet>(
    "debugReadRaw",
    {
      maxWaitMs: opts.maxWaitMs,
      maxBytes: opts.maxBytes,
      untilCrlf: opts.untilCrlf,
    },
    Math.min(40000, opts.maxWaitMs + 8000)
  );
  appendSerialDebugLog("debugReadRaw 回调", r);
  return r;
}

export async function nativeOpen(path: string, baud: number): Promise<{ ok?: boolean; err?: string }> {
  const r = await invoke<{ ok?: boolean; err?: string }>(
    "open",
    { path, baudRate: baud },
    12000
  );
  appendSerialDebugLog("open 回调", r);
  return r;
}

export async function nativeClosePort(): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("closePort 超时")), 8000);
    try {
      const mod = requireMod();
      if (typeof mod.closePort !== "function") {
        clearTimeout(t);
        resolve();
        return;
      }
      mod.closePort(() => {
        clearTimeout(t);
        appendSerialDebugLog("closePort 已回调");
        resolve();
      });
    } catch (e) {
      clearTimeout(t);
      reject(e);
    }
  });
}
