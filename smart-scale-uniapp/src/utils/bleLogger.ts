/** 真机蓝牙调试：收集带时间戳的日志，便于复制发给开发排查 */

const MAX_LINES = 300;
const lines: string[] = [];

function now(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${String(d.getMilliseconds()).padStart(3, "0")}`;
}

export type BleLogListener = () => void;
const listeners = new Set<BleLogListener>();

export function onBleLog(listener: BleLogListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notify() {
  listeners.forEach((fn) => {
    try {
      fn();
    } catch {
      /* ignore */
    }
  });
}

export function bleLog(tag: string, msg: string, extra?: unknown): void {
  let line = `[${now()}] [${tag}] ${msg}`;
  if (extra !== undefined) {
    try {
      if (typeof extra === "object" && extra !== null && "errMsg" in extra) {
        line += ` | ${JSON.stringify(extra)}`;
      } else if (typeof extra === "object") {
        line += ` | ${JSON.stringify(extra)}`;
      } else {
        line += ` | ${String(extra)}`;
      }
    } catch {
      line += ` | [无法序列化]`;
    }
  }
  lines.push(line);
  while (lines.length > MAX_LINES) lines.shift();
  console.log(line);
  notify();
}

export function bleLogError(tag: string, msg: string, err: unknown): void {
  let detail = "";
  if (err && typeof err === "object") {
    const o = err as Record<string, unknown>;
    detail = o.errMsg != null ? String(o.errMsg) : JSON.stringify(o);
  } else {
    detail = String(err);
  }
  bleLog(tag, `${msg} → ${detail}`, err);
}

export function getBleLogText(): string {
  return lines.join("\n");
}

export function clearBleLog(): void {
  lines.length = 0;
  notify();
}

export function getBleLogLineCount(): number {
  return lines.length;
}
