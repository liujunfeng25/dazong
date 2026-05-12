<template>
  <view v-if="order" class="modal-mask" @click.self="emitClose">
    <view class="modal-card" @click.stop>
      <view class="modal-head">
        <text class="modal-title">确认收货并签字</text>
        <text class="modal-close" @click="emitClose">×</text>
      </view>
      <view class="modal-body">
        <text class="order-hint">{{ order.title }}</text>
        <view class="sign-col">
          <text class="sign-label">收货方签字</text>
          <view class="sig-preview-box" :style="{ height: canvasCssH + 'px' }" @click="openSignPad('wh')">
            <image v-if="previewWh" class="sig-preview-img" :src="previewWh" mode="aspectFit" />
            <text v-else class="sig-preview-placeholder">点击此处签字</text>
          </view>
          <button size="mini" class="mini-clear" :disabled="!previewWh" @click.stop="clearPreview('wh')">清除</button>
        </view>
        <view class="sign-col">
          <text class="sign-label">送货方签字</text>
          <view class="sig-preview-box" :style="{ height: canvasCssH + 'px' }" @click="openSignPad('cr')">
            <image v-if="previewCr" class="sig-preview-img" :src="previewCr" mode="aspectFit" />
            <text v-else class="sig-preview-placeholder">点击此处签字</text>
          </view>
          <button size="mini" class="mini-clear" :disabled="!previewCr" @click.stop="clearPreview('cr')">清除</button>
        </view>
      </view>
      <view class="modal-foot">
        <button class="btn ghost" @click="emitClose">取消</button>
        <button class="btn primary" :disabled="submitting" @click="submit">
          {{ submitting ? "提交中…" : "提交并完成收货" }}
        </button>
      </view>
    </view>

    <!-- 二级签字弹窗：签完后点确认再回填主弹窗预览 -->
    <view v-if="padOpen && padKey" class="sub-mask" @click.self="cancelSignPad">
      <view class="sub-card" @click.stop>
        <text class="sub-title">{{ padKey === "wh" ? "收货方签字" : "送货方签字" }}</text>
        <canvas
          :key="'pad-' + padCanvasKey"
          id="sigPadCanvas"
          canvas-id="sigPadCanvas"
          class="sig-pad-canvas"
          :style="{ width: padCssW + 'px', height: padCssH + 'px' }"
          :width="padPxW"
          :height="padPxH"
          disable-scroll
          @touchstart="onPadTouchStart"
          @touchmove="onPadTouchMove"
          @touchend="onPadTouchEnd"
        />
        <view class="sub-actions">
          <button size="mini" class="mini-clear" @click="clearPadCanvas">清除画布</button>
        </view>
        <view class="sub-foot">
          <button class="btn ghost" @click="cancelSignPad">取消</button>
          <button class="btn primary" @click="confirmSignPad">确认</button>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { getCurrentInstance, nextTick, reactive, ref, watch } from "vue";
import type { OrderBrief } from "../types/order";
import { request } from "../utils/request";
import { clearDemoOrder } from "../utils/demoReceivingStorage";
import { tempFilePathToDataUrl } from "../utils/tempFileToDataUrl";

const props = defineProps<{
  order: OrderBrief | null;
  /** 演示单（无后端收货接口） */
  isDemo: boolean;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "success"): void;
}>();

const submitting = ref(false);
const idemKey = ref("");

const _sigOwnerInst = getCurrentInstance();
const canvasOwner: any = _sigOwnerInst?.proxy ?? _sigOwnerInst ?? null;

const sys = uni.getSystemInfoSync();
const dpr = Math.min(Number(sys.pixelRatio) || 2, 3);

/** 主弹窗内预览框尺寸（与原先签字区一致） */
const canvasCssW = Math.min(Number(sys.windowWidth || 375) - 48, 620);
const canvasCssH = 200;

/** 二级弹窗内画布（略大，便于书写） */
const padCssW = Math.min(Number(sys.windowWidth || 375) - 80, 680);
const padCssH = 240;
const padPxW = Math.floor(padCssW * dpr);
const padPxH = Math.floor(padCssH * dpr);

const previewWh = ref("");
const previewCr = ref("");

const sigState = reactive({
  wh: { dirty: false },
  cr: { dirty: false },
});

const padOpen = ref(false);
const padKey = ref<"wh" | "cr" | null>(null);
const padCanvasKey = ref(0);

const rectPad = ref({ left: 0, top: 0, width: padCssW, height: padCssH });

const padDraw = reactive({
  lastX: 0,
  lastY: 0,
  drawing: false,
  dirty: false,
});

function emitClose() {
  if (!submitting.value && !padOpen.value) emit("close");
}

function updatePadRect() {
  if (!canvasOwner) return;
  nextTick(() => {
    uni
      .createSelectorQuery()
      .in(canvasOwner as object)
      .select("#sigPadCanvas")
      .boundingClientRect()
      .exec((res: unknown[]) => {
        const a = res?.[0] as { left?: number; top?: number; width?: number; height?: number } | null;
        if (a && typeof a.left === "number") {
          rectPad.value = {
            left: a.left,
            top: a.top ?? 0,
            width: a.width ?? padCssW,
            height: a.height ?? padCssH,
          };
        }
      });
  });
}

watch(
  () => props.order,
  (o) => {
    if (o) {
      idemKey.value = `rcv-${o.id}-${Date.now()}`;
      previewWh.value = "";
      previewCr.value = "";
      sigState.wh.dirty = false;
      sigState.cr.dirty = false;
      padOpen.value = false;
      padKey.value = null;
    }
  },
  { immediate: true }
);

function openSignPad(key: "wh" | "cr") {
  padKey.value = key;
  padOpen.value = true;
  padCanvasKey.value += 1;
  padDraw.lastX = 0;
  padDraw.lastY = 0;
  padDraw.drawing = false;
  padDraw.dirty = false;
  nextTick(() => {
    nextTick(() => {
      initPadCanvas();
      updatePadRect();
    });
  });
}

function cancelSignPad() {
  padOpen.value = false;
  padKey.value = null;
}

function initPadCanvas() {
  if (!canvasOwner) return;
  try {
    const c = uni.createCanvasContext("sigPadCanvas", canvasOwner);
    c.setFillStyle("#ffffff");
    c.fillRect(0, 0, padPxW, padPxH);
    c.draw();
    padDraw.dirty = false;
  } catch (err) {
    console.error("[ReceiveSignModal] initPadCanvas", err);
  }
}

function clearPadCanvas() {
  initPadCanvas();
}

function touchPadXY(e: Record<string, unknown>): { x: number; y: number } {
  const ch = e.changedTouches as { length?: number; [i: number]: unknown } | undefined;
  const ts = e.touches as { length?: number; [i: number]: unknown } | undefined;
  const t = (ch && ch[0]) || (ts && ts[0]);
  if (!t) return { x: 0, y: 0 };
  const tx = t as unknown as { x?: number; y?: number; pageX?: number; pageY?: number; clientX?: number; clientY?: number };
  if (typeof tx.x === "number" && typeof tx.y === "number") {
    return {
      x: tx.x * (padPxW / padCssW),
      y: tx.y * (padPxH / padCssH),
    };
  }
  const pageX = Number(tx.pageX ?? tx.clientX ?? 0);
  const pageY = Number(tx.pageY ?? tx.clientY ?? 0);
  const r = rectPad.value;
  const lx = pageX - r.left;
  const ly = pageY - r.top;
  const scaleX = padPxW / (r.width || padCssW);
  const scaleY = padPxH / (r.height || padCssH);
  return { x: lx * scaleX, y: ly * scaleY };
}

function onPadTouchStart(e: unknown) {
  try {
    updatePadRect();
    const { x, y } = touchPadXY(e as Record<string, unknown>);
    padDraw.drawing = true;
    padDraw.lastX = x;
    padDraw.lastY = y;
    padDraw.dirty = true;
  } catch (err) {
    console.error("[ReceiveSignModal] pad touchstart", err);
  }
}

function onPadTouchMove(e: unknown) {
  try {
    if (!padDraw.drawing || !canvasOwner) return;
    const { x, y } = touchPadXY(e as Record<string, unknown>);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    const c = uni.createCanvasContext("sigPadCanvas", canvasOwner);
    c.setStrokeStyle("#111827");
    c.setLineWidth(3 * dpr);
    c.setLineCap("round");
    c.beginPath();
    c.moveTo(padDraw.lastX, padDraw.lastY);
    c.lineTo(x, y);
    c.stroke();
    c.draw(true);
    padDraw.lastX = x;
    padDraw.lastY = y;
    padDraw.dirty = true;
  } catch (err) {
    console.error("[ReceiveSignModal] pad touchmove", err);
  }
}

function onPadTouchEnd() {
  padDraw.drawing = false;
}

function canvasToDataUrl(canvasId: string, destW: number, destH: number): Promise<string> {
  return new Promise((resolve, reject) => {
    uni.canvasToTempFilePath(
      {
        canvasId,
        destWidth: destW,
        destHeight: destH,
        success: async (res) => {
          try {
            const dataUrl = await tempFilePathToDataUrl(res.tempFilePath, "image/png");
            resolve(dataUrl);
          } catch (e) {
            reject(e);
          }
        },
        fail: reject,
      },
      canvasOwner
    );
  });
}

async function confirmSignPad() {
  const key = padKey.value;
  if (!key || !padDraw.dirty) {
    uni.showToast({ title: "请先签名", icon: "none" });
    return;
  }
  try {
    const dataUrl = await canvasToDataUrl("sigPadCanvas", padPxW, padPxH);
    if (dataUrl.length < 80) {
      uni.showToast({ title: "签字过短，请重新签署", icon: "none" });
      return;
    }
    if (key === "wh") {
      previewWh.value = dataUrl;
      sigState.wh.dirty = true;
    } else {
      previewCr.value = dataUrl;
      sigState.cr.dirty = true;
    }
    cancelSignPad();
  } catch (err) {
    console.error("[ReceiveSignModal] confirmSignPad", err);
    uni.showToast({ title: "导出签字失败", icon: "none" });
  }
}

function clearPreview(key: "wh" | "cr") {
  if (key === "wh") {
    previewWh.value = "";
    sigState.wh.dirty = false;
  } else {
    previewCr.value = "";
    sigState.cr.dirty = false;
  }
}

async function submit() {
  if (!props.order) return;
  if (!sigState.wh.dirty || !sigState.cr.dirty) {
    uni.showToast({ title: "请双方在签字区签名", icon: "none" });
    return;
  }
  const warehouse_signature = previewWh.value;
  const carrier_signature = previewCr.value;
  if (warehouse_signature.length < 80 || carrier_signature.length < 80) {
    uni.showToast({ title: "签字过短，请重新签署", icon: "none" });
    return;
  }
  submitting.value = true;
  try {
    if (props.isDemo) {
      const no = props.order.order_no || "";
      if (no) clearDemoOrder(no);
      emit("success");
      emit("close");
      uni.redirectTo({ url: "/pages/success/success" });
      return;
    }
    const oid = String(props.order.id);
    await request<{ message?: string }>(`/orders/${oid}/receive`, {
      method: "POST",
      data: { warehouse_signature, carrier_signature },
      header: { "Idempotency-Key": idemKey.value },
    });
    emit("success");
    emit("close");
    uni.redirectTo({ url: "/pages/success/success" });
  } catch (err) {
    console.error("[ReceiveSignModal] submit", err);
    uni.showToast({ title: "收货提交失败", icon: "none" });
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped lang="scss">
@import "@/uni.scss";

.modal-mask {
  position: fixed;
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
  background: rgba(13, 43, 29, 0.45);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24rpx;
}

.modal-card {
  width: 100%;
  max-width: 720px;
  background: $c-bg-card;
  border-radius: $r-card;
  overflow: hidden;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: $shadow-up;
}

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 28rpx;
  border-bottom: 1rpx solid $c-border;
  background: linear-gradient(90deg, #f2f8f4 0%, $c-bg-sub 100%);
}

.modal-title {
  font-size: 30rpx;
  font-weight: 800;
  color: $c-text-h;
}

.modal-close {
  font-size: 44rpx;
  color: $c-text-hint;
  padding: 0 12rpx;
  line-height: 1;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  max-height: 70vh;
  padding: 24rpx;
  box-sizing: border-box;
}

.order-hint {
  display: block;
  font-size: 24rpx;
  color: $c-text-m;
  margin-bottom: 24rpx;
  padding: 14rpx 18rpx;
  background: $c-bg-sub;
  border-radius: 12rpx;
  border: 1rpx solid $c-border;
}

.sign-col {
  margin-bottom: 28rpx;
}

.sign-label {
  display: block;
  font-size: 24rpx;
  font-weight: 700;
  color: $c-text-b;
  margin-bottom: 12rpx;
  letter-spacing: 1rpx;
}

.sig-preview-box {
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  background: #fafcfb;
  border: 2rpx dashed $c-border-med;
  border-radius: 16rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.sig-preview-img {
  width: 100%;
  height: 100%;
}

.sig-preview-placeholder {
  font-size: 26rpx;
  color: $c-text-hint;
}

.sig-pad-canvas {
  display: block;
  background: #fff;
  border: 1rpx solid $c-border-med;
  border-radius: 16rpx;
  touch-action: none;
  margin: 0 auto;
}

.sub-mask {
  position: fixed;
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
  background: rgba(13, 43, 29, 0.55);
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24rpx;
}

.sub-card {
  width: 100%;
  max-width: 720px;
  background: $c-bg-card;
  border-radius: $r-card;
  padding: 28rpx 24rpx 24rpx;
  box-sizing: border-box;
  box-shadow: $shadow-up;
}

.sub-title {
  display: block;
  font-size: 30rpx;
  font-weight: 800;
  color: $c-text-h;
  text-align: center;
  margin-bottom: 20rpx;
}

.sub-actions {
  margin-top: 16rpx;
}

.sub-foot {
  display: flex;
  justify-content: flex-end;
  gap: 16rpx;
  margin-top: 24rpx;
  padding-top: 20rpx;
  border-top: 1rpx solid $c-border;
}

.mini-clear {
  margin-top: 12rpx;
  background: transparent;
  color: $c-text-m;
  border: 1rpx solid $c-border-med;
  border-radius: 10rpx;
  font-size: 22rpx;
}

.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 16rpx;
  padding: 20rpx 24rpx;
  border-top: 1rpx solid $c-border;
  background: linear-gradient(90deg, #f2f8f4 0%, $c-bg-sub 100%);
  flex-shrink: 0;
}

.btn {
  padding: 0 32rpx;
  height: 80rpx;
  line-height: 80rpx;
  border-radius: $r-btn;
  font-size: 28rpx;
  font-weight: 600;
}

.primary {
  background: linear-gradient(160deg, #27794d 0%, $c-primary 100%);
  color: #fff;
  border: none;
  box-shadow: 0 4rpx 14rpx rgba(27, 94, 58, 0.22);
}

.ghost {
  background: transparent;
  color: $c-text-m;
  border: 1rpx solid $c-border-med;
}
</style>
