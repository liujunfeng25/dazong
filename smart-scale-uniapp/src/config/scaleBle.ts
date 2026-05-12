/**
 * 首衡 SHOUHENG TCS-300A 等工业台秤：多数内嵌「串口转 BLE」模块，无统一公开文档。
 * 本文件提供：常见透传 UUID 候选 + 多策略重量解析；若仍不对，请对照界面「原始 notify」十六进制联系
 * 0553-2297956 / 厂商索取正式协议后改 tryParseWeightKg。
 */

/** 手动指定时优先（完全匹配服务 + 通知特征） */
export const SCALE_BLE_SERVICE_UUID = "";
export const SCALE_BLE_NOTIFY_CHAR_UUID = "";
/** 若仪表需先发读数指令，填写可 write 的特征 UUID，并配 SCALE_BLE_POLL_HEX */
export const SCALE_BLE_WRITE_CHAR_UUID = "";
/** 连接并订阅成功后，向 write 特征发送的十六进制指令（空格可选），空则不发送 */
export const SCALE_BLE_POLL_HEX = "";

export const SCALE_BLE_SCAN_SERVICE_UUIDS: string[] = [];

/** 常见 BLE 串口模块 / 工业秤透传（按顺序尝试订阅） */
export const SCALE_BLE_CANDIDATES: { label: string; service: string; notify: string }[] = [
  {
    label: "透传 FFE0/FFE1（HC/JDY 等常见）",
    service: "0000FFE0-0000-1000-8000-00805F9B34FB",
    notify: "0000FFE1-0000-1000-8000-00805F9B34FB",
  },
  {
    label: "FFF0/FFF1",
    service: "0000FFF0-0000-1000-8000-00805F9B34FB",
    notify: "0000FFF1-0000-1000-8000-00805F9B34FB",
  },
  {
    label: "Nordic UART（部分 nRF 透传）",
    service: "6E400001-B5A3-F393-E0A9-E50E24DCCA9E",
    notify: "6E400003-B5A3-F393-E0A9-E50E24DCCA9E",
  },
  {
    label: "网传 2603/CA01（仅供参考）",
    service: "00002603-0000-1000-8000-00805F9B34FB",
    notify: "0000CA01-0000-1000-8000-00805F9B34FB",
  },
];

const BASE_SIG = "00001000800000805f9b34fb";

export function normalizeBleUuid(u: string): string {
  return u.replace(/-/g, "").toLowerCase();
}

/** 比较两个 BLE UUID（支持 128 位与 16 位别名） */
export function matchBleUuid(a: string, b: string): boolean {
  const na = normalizeBleUuid(a);
  const nb = normalizeBleUuid(b);
  if (na === nb) return true;
  const sa = na.length >= 8 ? na.slice(4, 8) : "";
  const sb = nb.length >= 8 ? nb.slice(4, 8) : "";
  if (
    sa &&
    sb &&
    na.endsWith(BASE_SIG) &&
    nb.endsWith(BASE_SIG) &&
    na.startsWith("0000") &&
    nb.startsWith("0000") &&
    sa === sb
  ) {
    return true;
  }
  return false;
}

function formatWeightKg(v: number): string {
  if (!Number.isFinite(v) || Math.abs(v) > 1e6) return "";
  const x = Math.round(v * 1000) / 1000;
  if (Number.isInteger(x)) return String(x);
  return x.toFixed(3).replace(/\.?0+$/, "");
}

function decodeAsciiPrintable(u8: Uint8Array): string {
  let s = "";
  for (let i = 0; i < u8.length; i++) {
    const c = u8[i];
    if (c === 9 || c === 10 || c === 13) {
      s += " ";
      continue;
    }
    if (c >= 32 && c < 127) s += String.fromCharCode(c);
    else s += " ";
  }
  return s.replace(/\s+/g, " ").trim();
}

/**
 * 从 notify 数据中解析 kg；多策略按序尝试，误解析时以 hex 为准联系厂商定帧格式。
 */
export function tryParseWeightKg(buffer: ArrayBuffer): string | null {
  const u8 = new Uint8Array(buffer);
  if (!u8.length) return null;

  const text = decodeAsciiPrintable(u8);
  if (text.length >= 1) {
    const asciiRules: RegExp[] = [
      /NT\s*,\s*([-+]?\d+\.?\d*)/i,
      /ST\s*,\s*([-+]?\d+\.?\d*)/i,
      /w(?:eight)?\s*[:=]\s*([-+]?\d+\.?\d*)/i,
      /([-+]?\d+\.?\d*)\s*kg/i,
      /([-+]?\d+\.?\d*)\s*k\s*g/i,
    ];
    for (const re of asciiRules) {
      const m = text.match(re);
      if (m) {
        const v = parseFloat(m[1]);
        if (Number.isFinite(v) && Math.abs(v) < 1e6) return formatWeightKg(v);
      }
    }
    const nums = text.match(/[-+]?\d+\.?\d*/g);
    if (nums) {
      for (const n of nums) {
        const v = parseFloat(n);
        if (Number.isFinite(v) && Math.abs(v) <= 500000 && !(Math.abs(v) < 1e-6)) {
          return formatWeightKg(v);
        }
      }
    }
  }

  // 0x02 ... 0x03 连续协议里夹 ASCII
  const i0 = u8.indexOf(0x02);
  if (i0 >= 0) {
    const sub = u8.slice(i0 + 1);
    const t2 = decodeAsciiPrintable(sub);
    const m2 = t2.match(/([-+]?\d+\.?\d*)/);
    if (m2) {
      const v = parseFloat(m2[1]);
      if (Number.isFinite(v) && Math.abs(v) < 1e6) return formatWeightKg(v);
    }
  }

  const tryFloat = (le: boolean) => {
    for (let off = 0; off <= u8.length - 4; off++) {
      const dv = new DataView(buffer, off, 4);
      const f = dv.getFloat32(0, le);
      if (Number.isFinite(f) && f > -1e4 && f < 1e6 && Math.abs(f) > 1e-3) return f;
    }
    return null;
  };
  let fv = tryFloat(true);
  if (fv != null) return formatWeightKg(fv);
  fv = tryFloat(false);
  if (fv != null) return formatWeightKg(fv);

  // 4 字节有符号整数，按 g 或 0.1kg 缩放试探（易误判，仅短包）
  if (u8.length === 4 || u8.length === 8) {
    const dv = new DataView(buffer);
    for (const le of [true, false]) {
      const n = dv.getInt32(0, le);
      if (!Number.isFinite(n)) continue;
      for (const div of [1000, 100, 10, 1]) {
        const kg = n / div;
        if (Math.abs(kg) <= 500000 && Math.abs(kg) >= 1e-6) return formatWeightKg(kg);
      }
    }
  }

  return null;
}

export function hexStringToArrayBuffer(hex: string): ArrayBuffer {
  const clean = hex.replace(/\s+/g, "");
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i++) {
    out[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16) || 0;
  }
  return out.buffer;
}
