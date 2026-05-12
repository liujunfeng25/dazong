<template>
  <view class="page">
    <view v-if="loading" class="center"><text>加载中…</text></view>
    <view v-else-if="order">
      <view class="head">
        <text class="title">{{ order.title }}</text>
        <text class="sub">
          选中待称行后自动读秤；读数稳定后点「锁定读数」→「确认本行」。可随时点「读秤」立即刷新。全部行确认后返回列表「确认收货」并签字。
        </text>
        <view v-if="!readonly" class="hint-bar">
          <text class="hint-strong">剩余未确认：{{ remainingUnconfirmed }} 行</text>
          <text class="hint-muted">已确认 {{ confirmedCount }} / {{ totalLines }} 行</text>
        </view>
        <view v-else class="hint-bar readonly">
          <text class="readonly-title">{{ readonlyBannerTitle }}</text>
          <text v-if="readonlyBannerSub" class="readonly-sub">{{ readonlyBannerSub }}</text>
        </view>
        <view v-if="uvcNoDeviceBanner && !readonly" class="uvc-banner">
          <text class="uvc-banner-text">
            未检测到 USB（UVC）摄像头：底部不会有 USB 预览（多为接线/OTG/供电）。留痕仍可走「平板自带相机」或「无照片锁定」——自带相机与 USB 枚举无关。
          </text>
        </view>
      </view>
      <view class="split">
        <scroll-view scroll-y class="left">
          <view
            v-for="line in order.lines"
            :key="line.id"
            class="line"
            :class="{
              active: activeId === line.id,
              done: effectiveStatus(line) === 'confirmed',
            }"
            @click="activeId = line.id"
          >
            <view class="line-top">
              <text class="ln">{{ line.name }}</text>
              <text v-if="effectiveStatus(line) === 'confirmed'" class="badge">已称</text>
              <text v-else class="badge pending">待称</text>
            </view>
            <view v-if="lineLockThumbUri(line)" class="line-photo-row">
              <image
                class="line-thumb"
                :src="lineLockThumbUri(line)"
                mode="aspectFill"
              />
              <text class="line-photo-cap">锁定留痕</text>
            </view>
            <text class="lq">下单量 {{ line.qty }} {{ line.unit }}</text>
            <text v-if="effectiveStatus(line) === 'confirmed'" class="lck">
              实收 {{ (line.receivingConfirmedKg ?? demoPackKg(line))?.toFixed(2) ?? "—" }} kg
            </text>
            <text v-if="shortageLabel(line)" class="lsh">少收：{{ shortageLabel(line) }}</text>
          </view>
        </scroll-view>
        <view class="right">
          <view class="whead">
            <text class="wlabel">当前读数（kg）</text>
            <text v-if="autoPollActive" class="poll-badge">自动更新</text>
          </view>
          <view class="weight-card">
            <text class="weight">{{ displayWeight }}</text>
            <text class="delta" :class="{ warn: deltaBad }">与下单差：{{ deltaText }}</text>
          </view>
          <view v-if="!readonly" class="btn-main-group">
            <button class="btn secondary" :disabled="!canLock" @click="startLockDraftFlow">锁定读数</button>
            <button class="btn primary confirm-btn" :disabled="!canConfirmLine" @click="doConfirmLine">确认本行</button>
          </view>
          <view v-if="!readonly" class="btn-row">
            <button class="btn ghost" @click="readFromScale">读秤（立即）</button>
            <button class="btn ghost" @click="simulateRead">演示读数</button>
          </view>
          <view class="btn-utils">
            <button
              v-if="!readonly && activeLine && effectiveStatus(activeLine) === 'confirmed'"
              class="btn ghost"
              @click="doReopenLine"
            >撤销本行确认</button>
            <button class="btn ghost" @click="back">返回列表</button>
            <button class="btn ghost diag-entry" @click="openSerialDiag">串口诊断</button>
          </view>
        </view>
      </view>
      <view
        v-if="readonly && order.receiveSignaturesJson"
        class="sig-readonly"
      >
        <text class="sr-title">收货签字存档</text>
        <view class="sr-grid">
          <view class="sr-item">
            <text class="sr-cap">收货方</text>
            <image
              v-if="sigUrl('warehouse_signature')"
              class="sr-img"
              mode="aspectFit"
              :src="sigUrl('warehouse_signature')!"
            />
          </view>
          <view class="sr-item">
            <text class="sr-cap">送货方</text>
            <image
              v-if="sigUrl('carrier_signature')"
              class="sr-img"
              mode="aspectFit"
              :src="sigUrl('carrier_signature')!"
            />
          </view>
        </view>
      </view>
    </view>

    <view v-if="diagVisible" class="diag-mask" @tap="closeSerialDiag">
      <view class="diag-panel" @tap.stop>
        <text class="diag-title">串口诊断</text>
        <text class="diag-hint">可滚动查看；内容过长可多张截图或点「复制全文」。</text>
        <scroll-view scroll-y class="diag-scroll" :show-scrollbar="true">
          <text selectable class="diag-pre">{{ diagText }}</text>
        </scroll-view>
        <view class="diag-actions">
          <button class="btn secondary" @tap.stop="copySerialDiag">复制全文</button>
          <button class="btn ghost" @tap.stop="closeSerialDiag">关闭</button>
        </view>
      </view>
    </view>

    <view v-if="lockPreviewVisible" class="diag-mask" @tap.self="cancelLockPreview">
      <view class="diag-panel lock-preview-panel" @tap.stop>
        <text class="diag-title">确认称重留痕</text>
        <text class="diag-hint">
          请核对照片；确认后将提交锁定草稿。来源：{{
            lockPreviewSource === "uvc" ? "USB 摄像头(UVC)" : "系统相机"
          }}
        </text>
        <image class="lock-preview-img" :src="lockPreviewUri" mode="aspectFit" />
        <view class="diag-actions">
          <button class="btn secondary" @tap.stop="retakeLockPreview">重拍</button>
          <button class="btn ghost" @tap.stop="cancelLockPreview">取消</button>
          <button class="btn primary" @tap.stop="confirmLockPreview">确认锁定</button>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { onLoad, onShow, onHide, onUnload } from "@dcloudio/uni-app";
import type { OrderBrief, OrderRow } from "../../types/order";
import { request } from "../../utils/request";
import type { DemoLinePack } from "../../utils/demoReceivingStorage";
import {
  loadDemoOrderMap,
  removeDemoConfirmedLine,
  saveDemoLinePack,
} from "../../utils/demoReceivingStorage";
import {
  getScaleSerialDiagnosticsText,
  noteScaleSerialDiag,
  readScaleWeightKg,
} from "../../utils/scaleSerialRead";
import { SCALE_SERIAL_HTTP_URL, SCALE_SERIAL_NATIVE_PLUGIN_ID } from "../../config/scaleSerial";
import { UVC_DEFAULT_DEVICE_INDEX } from "../../config/uvcCamera";
import { saveSmartScaleLastLockPhoto } from "../../utils/smartScaleLastLockPhoto";
import {
  loadLineLockPhotosMap,
  persistBucketForLineLockPhotos,
  pruneLineLockPhotosToOrderLines,
  removeLineLockPhoto,
  saveLineLockPhoto,
  stabilizeLockPhotoUriForStorage,
} from "../../utils/smartScaleOrderLineLockPhotos";
import {
  captureLockPhotoBestEffort,
  uvcClose,
  uvcWarmTerminalPreview,
} from "../../utils/uvcCameraNative";

const loading = ref(false);
const order = ref<OrderBrief | null>(null);
const orderId = ref<string | null>(null);
const isDemo = ref(false);
const activeId = ref("");
const weight = ref<number | null>(null);
const locked = ref(false);
const demoPacks = ref<Record<string, DemoLinePack>>({});
const viewerReadonly = ref(false);
const diagVisible = ref(false);
const diagText = ref("");
const lockPreviewVisible = ref(false);
const lockPreviewUri = ref("");
const lockPreviewSource = ref<"uvc" | "system" | "">("");
/** 页面在后台时暂停自动读秤（避免与串口调试页等抢资源） */
const pageVisible = ref(true);
/** 进入作业台后尝试预热 UVC；无设备时提示 */
const uvcNoDeviceBanner = ref(false);
const lastUvcWarmOrderKey = ref("");
/** 每行「锁定读数」确认后的留痕图（本会话；演示已确认行另存于 DemoLinePack.lockPhotoUri） */
const lineLockPhotos = ref<Record<string, { uri: string; source: "uvc" | "system" }>>({});

const readonly = computed(() => {
  if (viewerReadonly.value) return true;
  const st = order.value?.status || "";
  return st !== "收货";
});

/** 非「收货」：操作按钮有意隐藏，避免误操作（与演示模式无关） */
const statusNotReceive = computed(
  () => !viewerReadonly.value && (order.value?.status || "") !== "收货"
);

const readonlyBannerTitle = computed(() => {
  if (viewerReadonly.value) {
    return `只读查看（当前状态：${order.value?.status || "—"}）`;
  }
  if (statusNotReceive.value) {
    return `当前为「${order.value?.status || "—"}」，无法进行称重`;
  }
  return "只读查看";
});

const readonlyBannerSub = computed(() => {
  if (viewerReadonly.value) return "";
  if (statusNotReceive.value) {
    return "称重与确认收货仅适用于状态为「收货」（已送达、待签收）的订单。请返回待收货列表，或等待配送将订单送达后再操作。";
  }
  return "";
});

const activeLine = computed<OrderRow | null>(() => {
  if (!order.value) return null;
  return order.value.lines.find((l) => l.id === activeId.value) || null;
});

function effectiveStatus(line: OrderRow): string | null {
  if (isDemo.value) {
    return demoPacks.value[line.id] != null ? "confirmed" : null;
  }
  return (line.receivingStatus as string | null) || null;
}

function demoPackKg(line: OrderRow): number | undefined {
  return demoPacks.value[line.id]?.kg;
}

/** 左侧明细列表缩略图：已确认演示行读持久化包；否则读本会话锁定留痕 */
function lineLockThumbUri(line: OrderRow): string {
  if (isDemo.value) {
    const u = demoPacks.value[line.id]?.lockPhotoUri;
    if (u) return u;
  }
  return lineLockPhotos.value[line.id]?.uri ?? "";
}

const reasonText: Record<string, string> = {
  lack: "缺货",
  quality: "质量问题",
  other: "其他",
};

function shortageLabel(line: OrderRow): string {
  if (isDemo.value) {
    const s = demoPacks.value[line.id]?.shortage;
    if (!s) return "";
    const base = reasonText[s.code] || s.code;
    return s.detail ? `${base}（${s.detail}）` : base;
  }
  const c = line.shortageReasonCode;
  if (!c) return "";
  const base = reasonText[c] || c;
  const d = line.shortageReasonDetail;
  return d ? `${base}（${d}）` : base;
}

const totalLines = computed(() => order.value?.lines.length || 0);

const confirmedCount = computed(() => {
  if (!order.value) return 0;
  if (isDemo.value) {
    return order.value.lines.filter((l) => demoPacks.value[l.id] != null).length;
  }
  return order.value.receivingConfirmedCount ?? 0;
});

const remainingUnconfirmed = computed(() =>
  Math.max(0, totalLines.value - confirmedCount.value)
);

const displayWeight = computed(() =>
  weight.value == null ? "—" : weight.value.toFixed(2)
);

function orderedQtyKg(line: OrderRow): number {
  const q = parseFloat(String(line.qty).replace(/[^\d.-]/g, "")) || 0;
  const u = (line.unit || "kg").toLowerCase();
  if (u.includes("斤")) return q * 0.5;
  return q;
}

const deltaText = computed(() => {
  if (!activeLine.value || weight.value == null) return "—";
  const q = orderedQtyKg(activeLine.value);
  if (Number.isNaN(q) || q <= 0) return "—";
  const d = weight.value - q;
  return (d >= 0 ? "+" : "") + d.toFixed(2) + " kg";
});

const deltaBad = computed(() => {
  if (!activeLine.value || weight.value == null) return false;
  const q = orderedQtyKg(activeLine.value);
  if (Number.isNaN(q) || q <= 0) return false;
  return Math.abs(weight.value - q) > q * 0.02;
});

const canLock = computed(
  () =>
    !readonly.value &&
    !!activeLine.value &&
    effectiveStatus(activeLine.value) !== "confirmed" &&
    weight.value != null &&
    !locked.value
);

const canConfirmLine = computed(
  () =>
    !readonly.value &&
    !!activeLine.value &&
    effectiveStatus(activeLine.value) !== "confirmed" &&
    locked.value &&
    weight.value != null
);

const scaleConfigured = computed(
  () =>
    SCALE_SERIAL_HTTP_URL.trim().length > 0 ||
    SCALE_SERIAL_NATIVE_PLUGIN_ID.trim().length > 0
);

/** 与模板「自动更新」角标一致：可自动轮询串口时 */
const autoPollActive = computed(() => {
  if (!scaleConfigured.value) return false;
  if (readonly.value || loading.value || !order.value || !activeLine.value) return false;
  if (effectiveStatus(activeLine.value) === "confirmed") return false;
  if (locked.value || diagVisible.value || !pageVisible.value) return false;
  return true;
});

/** 自动轮询与手动「读秤」串行，避免并发 readKg */
let scaleGateChain: Promise<void> = Promise.resolve();
function withScaleGate<T>(fn: () => Promise<T>): Promise<T> {
  const p = scaleGateChain.then(() => fn());
  scaleGateChain = p.then(() => {}).catch(() => {});
  return p;
}

let pollGeneration = 0;
let pollTimer: ReturnType<typeof setTimeout> | null = null;

function stopScaleAutoPoll() {
  pollGeneration += 1;
  if (pollTimer != null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function eligibleForScalePoll(): boolean {
  return !!(
    pageVisible.value &&
    !readonly.value &&
    !loading.value &&
    order.value &&
    activeLine.value &&
    effectiveStatus(activeLine.value) !== "confirmed" &&
    !locked.value &&
    scaleConfigured.value &&
    !diagVisible.value
  );
}

async function runScalePollCycle(gen: number) {
  if (gen !== pollGeneration) return;
  if (!eligibleForScalePoll()) return;

  const lineId = activeLine.value!.id;
  try {
    const kg = await withScaleGate(() => readScaleWeightKg());
    if (gen !== pollGeneration) return;
    if (!activeLine.value || activeLine.value.id !== lineId) return;
    if (locked.value || effectiveStatus(activeLine.value) === "confirmed") return;
    if (kg != null && Number.isFinite(kg)) {
      weight.value = Math.round(kg * 100) / 100;
    }
  } catch {
    /* 静默；异常见控制台与串口诊断 */
  }

  if (gen !== pollGeneration) return;
  if (!eligibleForScalePoll()) return;
  pollTimer = setTimeout(() => {
    pollTimer = null;
    void runScalePollCycle(gen);
  }, 450);
}

function startScaleAutoPoll() {
  stopScaleAutoPoll();
  const gen = pollGeneration;
  void runScalePollCycle(gen);
}

watch(
  autoPollActive,
  (on) => {
    if (on) startScaleAutoPoll();
    else stopScaleAutoPoll();
  },
  { immediate: true }
);

watch(activeId, () => {
  locked.value = false;
  weight.value = null;
  lockPreviewVisible.value = false;
  lockPreviewUri.value = "";
  lockPreviewSource.value = "";
  void uvcClose();
});

onUnmounted(() => {
  stopScaleAutoPoll();
});

function sigUrl(key: string): string | undefined {
  const j = order.value?.receiveSignaturesJson;
  if (!j || typeof j !== "object") return undefined;
  const v = (j as Record<string, unknown>)[key];
  return typeof v === "string" && v.length > 20 ? v : undefined;
}

function mapDetailToBrief(d: Record<string, unknown>): OrderBrief {
  const id = String(d.id ?? "");
  const order_no = String(d.order_no ?? "");
  const status = String(d.status ?? "");
  const items = (d.order_items || []) as Record<string, unknown>[];
  const lines: OrderRow[] = items.map((row) => {
    const line_no = Number(row.line_no ?? 0);
    return {
      id: String(line_no || row.product_id || 0),
      name: String(row.product_name ?? ""),
      qty: String(row.quantity ?? "—"),
      unit: String(row.unit ?? "kg"),
      receivingStatus: row.receiving_status as string | null,
      receivingConfirmedKg: row.receiving_confirmed_kg as number | undefined,
      receivingDraftKg: row.receiving_draft_kg as number | undefined,
      shortageReasonCode: (row.shortage_reason_code as string) || undefined,
      shortageReasonDetail: (row.shortage_reason_detail as string) || undefined,
      lineNo: line_no,
    };
  });
  const oraw = d.order_return as Record<string, unknown> | null | undefined;
  let orderReturn: OrderBrief["orderReturn"] = null;
  if (oraw && typeof oraw === "object" && oraw.return_no) {
    const lns = (oraw.lines as Record<string, unknown>[]) || [];
    orderReturn = {
      return_no: String(oraw.return_no),
      lines: lns.map((x) => ({
        line_index: Number(x.line_index),
        reason_code: String(x.reason_code || ""),
        reason_detail: (x.reason_detail as string) || null,
        delta_kg: Number(x.delta_kg ?? 0),
      })),
    };
  }
  return {
    id,
    order_no,
    status,
    title: order_no || `订单 #${id}`,
    lines,
    receivingConfirmedCount: Number(d.receiving_confirmed_count ?? 0),
    receivingTotalLines: Number(d.receiving_total_lines ?? lines.length),
    receiveSignaturesJson: (d.receive_signatures_json as Record<string, unknown>) || null,
    orderReturn,
  };
}

async function fetchOrder(id: string) {
  loading.value = true;
  try {
    const d = await request<Record<string, unknown>>(`/orders/${id}`);
    order.value = mapDetailToBrief(d);
    if (order.value.lines.length) {
      if (!activeId.value || !order.value.lines.some((l) => l.id === activeId.value)) {
        activeId.value = order.value.lines[0].id;
      }
    }
    hydrateLineLockPhotosFromPersist();
  } catch {
    uni.showToast({ title: "加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

/** 从本地存储恢复本会话「锁定留痕」缩略图（二次进入作业台） */
function hydrateLineLockPhotosFromPersist() {
  const o = order.value;
  if (!o?.lines?.length) return;
  const bucket = persistBucketForLineLockPhotos(orderId.value, o);
  if (!bucket) return;
  const ids = o.lines.map((l) => l.id);
  pruneLineLockPhotosToOrderLines(bucket, ids);
  const fromStore = loadLineLockPhotosMap(bucket, ids);
  lineLockPhotos.value = { ...fromStore, ...lineLockPhotos.value };
}

onLoad((q) => {
  if (q?.readonly === "1" || q?.readonly === 1) {
    viewerReadonly.value = true;
  }
  const id = q?.id != null ? String(q.id) : "";
  if (id && /^\d+$/.test(id)) {
    orderId.value = id;
    isDemo.value = false;
    fetchOrder(id);
    return;
  }
  try {
    const raw = q?.payload ? decodeURIComponent(String(q.payload)) : "";
    if (raw) {
      order.value = JSON.parse(raw) as OrderBrief;
      isDemo.value = true;
      orderId.value = /^\d+$/.test(String(order.value.id)) ? String(order.value.id) : null;
      if (order.value?.lines?.length) {
        order.value.lines = order.value.lines.map((l, i) => ({
          ...l,
          lineNo: l.lineNo ?? i + 1,
        }));
        activeId.value = order.value.lines[0].id;
      }
      if (isDemo.value && order.value?.order_no) {
        demoPacks.value = { ...loadDemoOrderMap(order.value.order_no) };
      }
      hydrateLineLockPhotosFromPersist();
    }
  } catch {
    uni.showToast({ title: "参数错误", icon: "none" });
  }
});

onShow(() => {
  pageVisible.value = true;
  if (orderId.value && !isDemo.value) {
    void fetchOrder(orderId.value);
  }
});

onHide(() => {
  pageVisible.value = false;
});

onUnload(() => {
  pageVisible.value = false;
  stopScaleAutoPoll();
  lastUvcWarmOrderKey.value = "";
  void uvcClose();
});

watch(
  () => ({
    o: order.value,
    ro: readonly.value,
    ld: loading.value,
  }),
  async ({ o, ro, ld }) => {
    // #ifdef APP-PLUS
    if (!o || ro || ld) {
      if (!o || ro) {
        uvcNoDeviceBanner.value = false;
      }
      return;
    }
    const key = String(o.id);
    if (lastUvcWarmOrderKey.value === key) {
      return;
    }
    lastUvcWarmOrderKey.value = key;
    const r = await uvcWarmTerminalPreview(UVC_DEFAULT_DEVICE_INDEX);
    uvcNoDeviceBanner.value = r.noDevices === true;
    // #endif
  },
  { flush: "post" }
);

async function readFromScale() {
  if (!activeLine.value) {
    uni.showToast({ title: "请先选择一行", icon: "none" });
    return;
  }
  if (effectiveStatus(activeLine.value) === "confirmed") {
    uni.showToast({ title: "该行已确认", icon: "none" });
    return;
  }
  if (!SCALE_SERIAL_HTTP_URL.trim() && !SCALE_SERIAL_NATIVE_PLUGIN_ID.trim()) {
    uni.showModal({
      title: "尚未配置串口",
      content:
        "有线秤请二选一：① 在 scaleSerial.ts 设置 SCALE_SERIAL_NATIVE_PLUGIN_ID 为 dazong-serial-scale，并按仓库 nativeplugins/dazong-serial-scale 编译 aar 后云打包；② 配置 SCALE_SERIAL_HTTP_URL 指向本机串口转 HTTP 服务。可先点「演示读数」走流程。",
      showCancel: false,
    });
    return;
  }
  console.log(
    "[ScaleSerial] readFromScale 开始",
    activeLine.value ? { lineId: activeLine.value.id } : {}
  );
  uni.showLoading({ title: "读秤中…", mask: true });
  try {
    const kg = await withScaleGate(() => readScaleWeightKg());
    if (kg == null || !Number.isFinite(kg)) {
      console.warn("[ScaleSerial] readFromScale 无有效重量", { kg });
      uni.showToast({ title: "未读到有效重量", icon: "none" });
      return;
    }
    const rounded = Math.round(kg * 100) / 100;
    console.log("[ScaleSerial] readFromScale 成功", { kg: rounded });
    weight.value = rounded;
    locked.value = false;
    uni.showToast({ title: "已更新读数", icon: "none" });
  } catch (e) {
    console.error("[ScaleSerial] readFromScale 异常", e);
    uni.showToast({ title: "读秤异常", icon: "none" });
  } finally {
    uni.hideLoading();
  }
}

function openSerialDiag() {
  noteScaleSerialDiag("打开面板（含当下配置与最近流水）");
  diagText.value = getScaleSerialDiagnosticsText();
  diagVisible.value = true;
}

function closeSerialDiag() {
  diagVisible.value = false;
}

function copySerialDiag() {
  uni.setClipboardData({
    data: diagText.value,
    success() {
      uni.showToast({ title: "已复制全文", icon: "none" });
    },
  });
}

function simulateRead() {
  if (!activeLine.value) {
    uni.showToast({ title: "请先选择一行", icon: "none" });
    return;
  }
  if (effectiveStatus(activeLine.value) === "confirmed") {
    uni.showToast({ title: "该行已确认", icon: "none" });
    return;
  }
  const q = orderedQtyKg(activeLine.value) || 1;
  weight.value = Math.round(q * (0.97 + Math.random() * 0.06) * 100) / 100;
  locked.value = false;
}

type ShortageCode = "lack" | "quality" | "other";
type ShortagePick = { code: ShortageCode; detail?: string };

function pickShortageReason(): Promise<ShortagePick | null> {
  return new Promise((resolve) => {
    uni.showActionSheet({
      itemList: ["缺货", "质量问题", "其他"],
      success(res) {
        const codes: ShortageCode[] = ["lack", "quality", "other"];
        const code = codes[res.tapIndex];
        if (!code) {
          resolve(null);
          return;
        }
        if (code === "other") {
          uni.showModal({
            title: "请填写其他原因",
            editable: true,
            placeholderText: "至少 2 个字",
            success(r) {
              const d = String(r.content || "").trim();
              if (d.length < 2) {
                uni.showToast({ title: "说明太短", icon: "none" });
                resolve(null);
                return;
              }
              resolve({ code, detail: d });
            },
            fail: () => resolve(null),
          });
        } else {
          resolve({ code });
        }
      },
      fail: () => resolve(null),
    });
  });
}

function persistLastLockPhoto(uri: string, source: "uvc" | "system") {
  const o = order.value;
  const line = activeLine.value;
  if (!o || !line || !uri) return;
  saveSmartScaleLastLockPhoto({
    uri,
    orderTitle: o.title || o.order_no || "",
    order_no: o.order_no || "",
    lineName: line.name,
    lineNo: line.lineNo ?? null,
    ts: Date.now(),
    source,
  });
}

/** 提交锁定草稿（无照片字段，照片仅本机留痕） */
async function postDraftCore(): Promise<boolean> {
  if (!activeLine.value || weight.value == null) return false;
  if (isDemo.value) {
    locked.value = true;
    uni.showToast({ title: "已锁定（演示）", icon: "none" });
    return true;
  }
  if (!orderId.value) return false;
  const ln = activeLine.value.lineNo ?? Number(activeLine.value.id);
  try {
    await request(`/orders/${orderId.value}/receiving/lines/${ln}/draft`, {
      method: "POST",
      data: { net_kg: weight.value },
    });
    locked.value = true;
    uni.showToast({ title: "已锁定", icon: "none" });
    return true;
  } catch {
    uni.showToast({ title: "锁定失败", icon: "none" });
    return false;
  }
}

async function startLockDraftFlow() {
  if (!activeLine.value || weight.value == null) return;
  if (readonly.value) return;
  if (effectiveStatus(activeLine.value) === "confirmed") {
    uni.showToast({ title: "该行已确认", icon: "none" });
    return;
  }
  try {
    const shot = await captureLockPhotoBestEffort(UVC_DEFAULT_DEVICE_INDEX);
    if (!shot) {
      uni.showModal({
        title: "未拍到照片",
        content: "是否仍锁定当前重量？（无照片留痕）",
        cancelText: "取消",
        confirmText: "仅锁定",
        success: async (res) => {
          if (res.confirm) {
            await postDraftCore();
            void uvcClose();
          }
        },
      });
      return;
    }
    lockPreviewUri.value = shot.uri;
    lockPreviewSource.value = shot.source;
    lockPreviewVisible.value = true;
  } catch (e) {
    console.error("[terminal] startLockDraftFlow", e);
    uni.showToast({ title: "拍照异常", icon: "none" });
  }
}

async function confirmLockPreview() {
  const uri = lockPreviewUri.value;
  const src = lockPreviewSource.value === "uvc" ? "uvc" : "system";
  lockPreviewVisible.value = false;
  const ok = await postDraftCore();
  const lid = activeLine.value?.id;
  if (ok && uri && lid) {
    const stableUri = await stabilizeLockPhotoUriForStorage(uri);
    const bucket = persistBucketForLineLockPhotos(orderId.value, order.value);
    if (bucket) {
      saveLineLockPhoto(bucket, lid, stableUri, src);
    }
    lineLockPhotos.value = { ...lineLockPhotos.value, [lid]: { uri: stableUri, source: src } };
    persistLastLockPhoto(stableUri, src);
  }
  lockPreviewUri.value = "";
  lockPreviewSource.value = "";
  try {
    await uvcClose();
  } catch {
    /* ignore */
  }
}

async function retakeLockPreview() {
  try {
    const shot = await captureLockPhotoBestEffort(UVC_DEFAULT_DEVICE_INDEX);
    if (shot) {
      lockPreviewUri.value = shot.uri;
      lockPreviewSource.value = shot.source;
    } else {
      uni.showToast({ title: "仍未拍到", icon: "none" });
    }
  } catch (e) {
    console.error("[terminal] retakeLockPreview", e);
    uni.showToast({ title: "重拍失败", icon: "none" });
  }
}

function cancelLockPreview() {
  lockPreviewVisible.value = false;
  lockPreviewUri.value = "";
  lockPreviewSource.value = "";
  void uvcClose();
}

async function doConfirmLine() {
  if (!activeLine.value || weight.value == null) return;
  const ordered = orderedQtyKg(activeLine.value);
  const eps = 1e-3;
  const needReason =
    !Number.isNaN(ordered) && ordered > 0 && weight.value + eps < ordered;
  let shortage: ShortagePick | undefined;
  if (needReason) {
    const r = await pickShortageReason();
    if (!r) return;
    shortage = r;
  }
  if (isDemo.value) {
    const pack: DemoLinePack = { kg: weight.value };
    if (shortage) {
      pack.shortage =
        shortage.code === "other"
          ? { code: shortage.code, detail: shortage.detail }
          : { code: shortage.code };
    }
    const snap = lineLockPhotos.value[activeLine.value.id];
    if (snap?.uri) {
      pack.lockPhotoUri = await stabilizeLockPhotoUriForStorage(snap.uri);
      pack.lockPhotoSource = snap.source;
    }
    demoPacks.value = { ...demoPacks.value, [activeLine.value.id]: pack };
    if (order.value?.order_no) {
      saveDemoLinePack(order.value.order_no, activeLine.value.id, pack);
    }
    const b = persistBucketForLineLockPhotos(orderId.value, order.value);
    if (b) {
      removeLineLockPhoto(b, activeLine.value.id);
    }
    const nextPhotos = { ...lineLockPhotos.value };
    delete nextPhotos[activeLine.value.id];
    lineLockPhotos.value = nextPhotos;
    locked.value = false;
    weight.value = null;
    uni.showToast({ title: "演示：本行已确认", icon: "none" });
    return;
  }
  if (!orderId.value) return;
  const ln = activeLine.value.lineNo ?? Number(activeLine.value.id);
  const data: Record<string, unknown> = { net_kg: weight.value };
  if (shortage) {
    data.shortage_reason =
      shortage.code === "other"
        ? { code: shortage.code, detail: shortage.detail }
        : { code: shortage.code };
  }
  try {
    await request(`/orders/${orderId.value}/receiving/lines/${ln}/confirm`, {
      method: "POST",
      data,
    });
    locked.value = false;
    weight.value = null;
    await fetchOrder(orderId.value);
    /* 留痕图仍挂在 lineLockPhotos，列表继续展示 */
    uni.showToast({ title: "本行已确认", icon: "none" });
  } catch {
    uni.showToast({ title: "确认失败", icon: "none" });
  }
}

async function doReopenLine() {
  if (!activeLine.value) return;
  if (isDemo.value) {
    const next = { ...demoPacks.value };
    delete next[activeLine.value.id];
    demoPacks.value = next;
    if (order.value?.order_no) {
      removeDemoConfirmedLine(order.value.order_no, activeLine.value.id);
    }
    const b = persistBucketForLineLockPhotos(orderId.value, order.value);
    if (b) {
      removeLineLockPhoto(b, activeLine.value.id);
    }
    const nextPhotos = { ...lineLockPhotos.value };
    delete nextPhotos[activeLine.value.id];
    lineLockPhotos.value = nextPhotos;
    uni.showToast({ title: "已撤销（演示）", icon: "none" });
    return;
  }
  if (!orderId.value) return;
  const ln = activeLine.value.lineNo ?? Number(activeLine.value.id);
  const lineId = activeLine.value.id;
  try {
    await request(`/orders/${orderId.value}/receiving/lines/${ln}/reopen`, {
      method: "POST",
    });
    const b = persistBucketForLineLockPhotos(orderId.value, order.value);
    if (b) {
      removeLineLockPhoto(b, lineId);
    }
    const nextPhotos = { ...lineLockPhotos.value };
    delete nextPhotos[lineId];
    lineLockPhotos.value = nextPhotos;
    await fetchOrder(orderId.value);
    uni.showToast({ title: "已撤销本行确认", icon: "none" });
  } catch {
    uni.showToast({ title: "操作失败", icon: "none" });
  }
}

function back() {
  uni.navigateBack({ delta: 1 });
}
</script>

<style scoped lang="scss">
@import "@/uni.scss";

.page {
  min-height: 100vh;
  background: $c-bg;
  padding: 24rpx;
  box-sizing: border-box;
}

// ── Head ──────────────────────────────────
.head {
  background: $c-bg-card;
  border-radius: $r-card;
  padding: 28rpx 28rpx 24rpx;
  margin-bottom: 20rpx;
  box-shadow: $shadow-card;
  border: 1rpx solid $c-border;
}

.title {
  display: block;
  font-size: 34rpx;
  font-weight: 800;
  color: $c-text-h;
  letter-spacing: 1rpx;
}

.sub {
  display: block;
  margin-top: 10rpx;
  font-size: 22rpx;
  color: $c-text-m;
  line-height: 1.55;
}

.hint-bar {
  margin-top: 16rpx;
  padding: 16rpx 20rpx;
  background: $c-done-bg;
  border-radius: 12rpx;
  border: 1rpx solid rgba(0, 136, 90, 0.18);
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}

.hint-bar.readonly {
  background: #f3f4f2;
  border-color: rgba(0, 0, 0, 0.07);
}

.hint-strong {
  font-size: 28rpx;
  font-weight: 800;
  color: $c-primary;
}

.hint-muted {
  font-size: 24rpx;
  color: $c-text-b;
}

.readonly-title {
  font-size: 26rpx;
  font-weight: 700;
  color: #5c4033;
  line-height: 1.4;
}

.readonly-sub {
  display: block;
  margin-top: 10rpx;
  font-size: 22rpx;
  color: $c-text-m;
  line-height: 1.55;
}

.uvc-banner {
  margin-top: 12rpx;
  padding: 14rpx 18rpx;
  background: $c-pending-bg;
  border-radius: 12rpx;
  border: 1rpx solid rgba(240, 173, 78, 0.4);
}

.uvc-banner-text {
  font-size: 22rpx;
  color: $c-warn-text;
  line-height: 1.5;
}

// ── Split layout ──────────────────────────
.split {
  display: flex;
  flex-direction: row;
  gap: 20rpx;
  min-height: calc(100vh - 300rpx);
}

// ── Left: item list ───────────────────────
.left {
  flex: 1.1;
  max-height: calc(100vh - 300rpx);
}

.line {
  background: $c-bg-card;
  border-radius: $r-card;
  padding: 24rpx 24rpx 24rpx 30rpx;
  margin-bottom: 16rpx;
  border: 1rpx solid $c-border;
  position: relative;
}

.line::before {
  content: "";
  position: absolute;
  left: 0;
  top: 16rpx;
  bottom: 16rpx;
  width: 6rpx;
  border-radius: 999rpx;
  background: transparent;
}

.line.active {
  border-color: $c-border-med;
  background: #f4fbf6;
}

.line.active::before {
  background: $c-primary;
}

.line.done::before {
  background: $c-accent;
  opacity: 0.55;
}

.line.done {
  border-color: rgba(0, 166, 90, 0.18);
}

.line-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12rpx;
}

.ln {
  flex: 1;
  font-size: 28rpx;
  font-weight: 600;
  color: $c-text-h;
}

.badge {
  font-size: 20rpx;
  padding: 4rpx 14rpx;
  border-radius: $r-tag;
  background: $c-done-bg;
  color: $c-done-text;
  font-weight: 600;
}

.badge.pending {
  background: $c-pending-bg;
  color: $c-pending-text;
}

.lq {
  display: block;
  font-size: 22rpx;
  color: $c-text-m;
  margin-top: 8rpx;
}

.lck {
  display: block;
  font-size: 22rpx;
  color: $c-done-text;
  font-weight: 600;
  margin-top: 6rpx;
}

.lsh {
  display: block;
  font-size: 20rpx;
  color: $c-pending-text;
  margin-top: 4rpx;
}

.line-photo-row {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 16rpx;
  margin-top: 12rpx;
}

.line-thumb {
  width: 120rpx;
  height: 120rpx;
  border-radius: 12rpx;
  background: #eef1ee;
  flex-shrink: 0;
  border: 1rpx solid $c-border;
}

.line-photo-cap {
  font-size: 20rpx;
  color: $c-text-m;
}

// ── Right: weight console ─────────────────
.right {
  flex: 1;
  background: $c-bg-card;
  border-radius: $r-card;
  padding: 28rpx 24rpx 20rpx;
  box-shadow: $shadow-card;
  border: 1rpx solid $c-border;
  display: flex;
  flex-direction: column;
}

.whead {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 16rpx;
  margin-bottom: 14rpx;
}

.wlabel {
  font-size: 22rpx;
  font-weight: 600;
  color: $c-text-m;
  letter-spacing: 1rpx;
}

.poll-badge {
  font-size: 20rpx;
  padding: 4rpx 14rpx;
  border-radius: $r-tag;
  background: $c-done-bg;
  color: $c-done-text;
  flex-shrink: 0;
}

.weight-card {
  background: linear-gradient(135deg, #f0faf4 0%, #e8f6ee 100%);
  border-radius: 20rpx;
  border: 1rpx solid rgba(0, 166, 90, 0.16);
  padding: 24rpx 24rpx 20rpx;
  margin-bottom: 24rpx;
  text-align: center;
}

.weight {
  display: block;
  font-size: 82rpx;
  font-weight: 800;
  color: $c-primary;
  line-height: 1;
  letter-spacing: -2rpx;
}

.delta {
  display: block;
  font-size: 24rpx;
  color: $c-done-text;
  margin-top: 10rpx;
}

.delta.warn {
  color: $c-warn-text;
}

// Button groups
.btn-main-group {
  display: flex;
  flex-direction: column;
  gap: 14rpx;
  margin-bottom: 16rpx;
}

.btn-row {
  display: flex;
  flex-direction: row;
  gap: 14rpx;
  margin-bottom: 16rpx;
}

.btn-row .btn {
  flex: 1;
}

.btn-utils {
  display: flex;
  flex-direction: column;
  gap: 10rpx;
  border-top: 1rpx solid $c-border;
  padding-top: 16rpx;
  margin-top: auto;
}

.btn {
  border-radius: $r-btn;
  font-size: 28rpx;
  font-weight: 600;
  height: 88rpx;
  line-height: 88rpx;
}

.confirm-btn {
  height: 100rpx;
  line-height: 100rpx;
  font-size: 32rpx;
  letter-spacing: 4rpx;
}

.btn-utils .btn {
  height: 76rpx;
  line-height: 76rpx;
  font-size: 26rpx;
  font-weight: 500;
}

.primary {
  background: linear-gradient(160deg, #27794d 0%, $c-primary 100%);
  color: #fff;
  border: none;
  box-shadow: 0 6rpx 20rpx rgba(27, 94, 58, 0.22);
}

.secondary {
  background: $c-done-bg;
  color: $c-text-h;
  border: 1rpx solid rgba(0, 136, 90, 0.2);
}

.ghost {
  background: transparent;
  color: $c-text-m;
  border: 1rpx solid $c-border-med;
}

.diag-entry {
  color: $c-text-hint;
  font-size: 22rpx;
  border-color: $c-border;
}

.center {
  padding: 120rpx 0;
  text-align: center;
  color: $c-text-m;
}

// ── Signature readonly ────────────────────
.sig-readonly {
  margin-top: 20rpx;
  padding: 24rpx;
  background: $c-bg-card;
  border-radius: $r-card;
  border: 1rpx solid $c-border;
  box-shadow: $shadow-card;
}

.sr-title {
  font-size: 28rpx;
  font-weight: 700;
  color: $c-text-h;
  display: block;
  margin-bottom: 20rpx;
}

.sr-grid {
  display: flex;
  flex-direction: row;
  gap: 20rpx;
  flex-wrap: wrap;
}

.sr-item {
  flex: 1;
  min-width: 280rpx;
}

.sr-cap {
  font-size: 22rpx;
  color: $c-text-m;
  display: block;
  margin-bottom: 12rpx;
}

.sr-img {
  width: 100%;
  height: 200rpx;
  background: $c-bg-sub;
  border-radius: 12rpx;
  border: 1rpx dashed $c-border-med;
}

// ── Diagnostics / Lock Preview Modals ─────
.diag-mask {
  position: fixed;
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
  background: rgba(13, 43, 29, 0.45);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 28rpx;
  box-sizing: border-box;
}

.diag-panel {
  width: 100%;
  max-width: 720px;
  max-height: 88vh;
  background: $c-bg-card;
  border-radius: $r-card;
  padding: 28rpx 28rpx 24rpx;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  box-shadow: $shadow-up;
}

.diag-title {
  font-size: 32rpx;
  font-weight: 800;
  color: $c-text-h;
  margin-bottom: 8rpx;
}

.diag-hint {
  font-size: 22rpx;
  color: $c-text-m;
  margin-bottom: 16rpx;
}

.diag-scroll {
  flex: 1;
  max-height: 58vh;
  min-height: 240rpx;
  border: 1rpx solid $c-border-med;
  border-radius: 12rpx;
  padding: 16rpx;
  background: $c-bg-sub;
  box-sizing: border-box;
}

.diag-pre {
  display: block;
  font-size: 22rpx;
  line-height: 1.55;
  color: $c-text-b;
  white-space: pre-wrap;
  word-break: break-all;
}

.lock-preview-panel {
  max-width: 820px;
}

.lock-preview-img {
  width: 100%;
  height: 420rpx;
  background: $c-bg-sub;
  border-radius: 12rpx;
  border: 1rpx solid $c-border-med;
  margin-bottom: 16rpx;
}

.diag-actions {
  display: flex;
  flex-direction: row;
  gap: 16rpx;
  margin-top: 20rpx;
}

.diag-actions .btn {
  flex: 1;
  height: 88rpx;
  line-height: 88rpx;
}

@media screen and (min-width: 960px) {
  .page {
    padding: 22rpx 34rpx;
  }
  .split {
    min-height: calc(100vh - 260rpx);
    gap: 26rpx;
  }
  .left {
    flex: 1.2;
    max-height: calc(100vh - 260rpx);
  }
  .right {
    flex: 0.95;
    min-width: 420rpx;
  }
  .weight {
    font-size: 96rpx;
  }
  .confirm-btn {
    height: 108rpx;
    line-height: 108rpx;
  }
}
</style>
