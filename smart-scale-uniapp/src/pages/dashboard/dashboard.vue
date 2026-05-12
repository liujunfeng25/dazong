<template>
  <view class="page">
    <view class="toolbar">
      <button size="mini" class="link" @click="goHistory">历史订单</button>
      <button size="mini" class="link" @click="goDevices">蓝牙设备</button>
      <button size="mini" class="link" @click="goSerialDebug">串口调试</button>
      <button size="mini" class="link" @click="goUvcDebug">UVC 拍照</button>
      <button size="mini" class="link" @click="logout">退出</button>
    </view>
    <view v-if="lastLockPhoto" class="last-lock-card" @click="openLastLockPreview">
      <image class="last-lock-thumb" :src="lastLockPhoto.uri" mode="aspectFill" />
      <view class="last-lock-meta">
        <text class="last-lock-title">上次称重留痕</text>
        <text class="last-lock-sub">{{ lastLockPhotoLine }}</text>
        <text class="last-lock-time">{{ lastLockPhotoTime }}</text>
      </view>
    </view>

    <view
      v-if="lastLockPreviewOpen && lastLockPhoto"
      class="ll-mask"
      @tap="lastLockPreviewOpen = false"
    >
      <view class="ll-panel" @tap.stop>
        <text class="ll-title">留痕预览</text>
        <text class="ll-sub">{{ lastLockPhotoLine }}</text>
        <image class="ll-img" :src="lastLockPhoto.uri" mode="widthFix" />
        <button class="ll-close" @tap="lastLockPreviewOpen = false">关闭</button>
      </view>
    </view>

    <view v-if="loading" class="center"><text>加载中…</text></view>
    <view v-else-if="orders.length === 0" class="center empty">
      <text>暂无可处理订单</text>
      <text class="sub">展示近 30 天内尚未确认收货的订单（已「收货确认」「已结算」的不在此列表）。</text>
    </view>
    <scroll-view v-else scroll-y class="list">
      <view v-for="item in orders" :key="item.id" class="row">
        <view class="row-main" @click="openOrder(item)">
          <view class="row-top">
            <text class="no">{{ item.title }}</text>
            <text class="tag">{{ item.status || "—" }}</text>
          </view>
          <text class="meta">共 {{ item.lines.length }} 行货品</text>
          <view class="progress-row">
            <text class="prog-label">称重进度</text>
            <view class="prog-bar">
              <view
                class="prog-fill"
                :style="{
                  width:
                    (item.receivingTotalLines || item.lines.length)
                      ? `${
                          (100 *
                            (item.receivingConfirmedCount || 0)) /
                          (item.receivingTotalLines || item.lines.length || 1)
                        }%`
                      : '0%',
                }"
              />
            </view>
            <text class="prog-text">
              {{ item.receivingConfirmedCount ?? 0 }} /
              {{ item.receivingTotalLines ?? item.lines.length }} 行已确认
            </text>
          </view>
        </view>
        <view class="row-actions" @click.stop>
          <button class="btn-row secondary" @click.stop="openOrder(item)">去称重</button>
          <button
            class="btn-row primary"
            :disabled="!canReceiveOrder(item)"
            @click.stop="startReceive(item)"
          >
            确认收货
          </button>
        </view>
      </view>
    </scroll-view>
    <ReceiveSignModal
      v-if="receiveOrder"
      :order="receiveOrder"
      :is-demo="receiveIsDemo"
      @close="receiveOrder = null"
      @success="onReceiveDone"
    />
  </view>
</template>

<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import ReceiveSignModal from "../../components/ReceiveSignModal.vue";
import type { OrderBrief } from "../../types/order";
import { countDemoConfirmedForOrder } from "../../utils/demoReceivingStorage";
import { clearToken, getToken, request } from "../../utils/request";
import {
  readSmartScaleLastLockPhoto,
  type SmartScaleLastLockPhoto,
} from "../../utils/smartScaleLastLockPhoto";

const loading = ref(false);
const orders = ref<OrderBrief[]>([]);
const receiveOrder = ref<OrderBrief | null>(null);
const lastLockPhoto = ref<SmartScaleLastLockPhoto | null>(null);
const lastLockPreviewOpen = ref(false);

const lastLockPhotoLine = computed(() => {
  const p = lastLockPhoto.value;
  if (!p) return "";
  const line = p.lineNo != null ? `第 ${p.lineNo} 行 · ${p.lineName}` : p.lineName;
  return `${p.orderTitle || p.order_no || "订单"} · ${line}`;
});

const lastLockPhotoTime = computed(() => {
  const p = lastLockPhoto.value;
  if (!p) return "";
  try {
    return new Date(p.ts).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return "";
  }
});

function refreshLastLockPhoto() {
  lastLockPhoto.value = readSmartScaleLastLockPhoto();
}

function openLastLockPreview() {
  if (lastLockPhoto.value) lastLockPreviewOpen.value = true;
}

const receiveIsDemo = computed(() =>
  receiveOrder.value ? !/^\d+$/.test(String(receiveOrder.value.id)) : false
);

function mockOrders(): OrderBrief[] {
  return [
    {
      id: "demo-1",
      order_no: "DZ-20260506-001",
      status: "收货",
      title: "演示订单 DZ-20260506-001",
      receivingConfirmedCount: 0,
      receivingTotalLines: 2,
      lines: [
        { id: "1", name: "土豆（一级）", qty: "500", unit: "kg", lineNo: 1 },
        { id: "2", name: "胡萝卜", qty: "120", unit: "kg", lineNo: 2 },
      ],
    },
  ];
}

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

/** 未确认收货：排除已入账完成的两态；已取消的不展示 */
function isNotReceiveConfirmed(o: OrderBrief): boolean {
  const st = o.status || "";
  if (st === "收货确认" || st === "已结算" || st === "取消") return false;
  return true;
}

async function load() {
  const token = getToken();
  if (!token || token === "demo") {
    orders.value = mockOrders().map(applyDemoProgress);
    return;
  }
  loading.value = true;
  try {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 30);
    const startDay = `${start.getFullYear()}-${pad2(start.getMonth() + 1)}-${pad2(start.getDate())}`;
    const endDay = `${end.getFullYear()}-${pad2(end.getMonth() + 1)}-${pad2(end.getDate())}`;
    const data = await request<unknown>(
      `/orders?created_date_start=${startDay}&created_date_end=${endDay}`
    );
    const raw = Array.isArray(data) ? data : [];
    orders.value = (raw as Record<string, unknown>[])
      .map(normalizeListOrder)
      .map(applyDemoProgress)
      .filter(isNotReceiveConfirmed);
  } catch {
    orders.value = mockOrders().map(applyDemoProgress);
    uni.showToast({ title: "已使用演示数据", icon: "none" });
  } finally {
    loading.value = false;
  }
}

/** 对齐 backend GET /orders：返回 Order 对象数组，行在 items_json + items_snapshot_json */
function normalizeListOrder(o: Record<string, unknown>): OrderBrief {
  const id = String(o.id ?? "");
  const order_no = String(o.order_no ?? "");
  const status = String(o.status ?? "");
  const items = (o.items_json || []) as Record<string, unknown>[];
  const snaps = (o.items_snapshot_json || []) as Record<string, unknown>[];
  const lines = items.map((item, i) => {
    const snap = (snaps[i] || {}) as Record<string, unknown>;
    const name = String(
      snap.product_name || item.product_name || `商品#${item.product_id ?? i}`
    );
    const qty = String(item.quantity ?? "—");
    const unit = String(snap.unit || item.unit || "kg");
    const lineNo = i + 1;
    return { id: String(lineNo), name, qty, unit, lineNo };
  });
  const totalLines =
    Number(o.receiving_total_lines) >= 0 ? Number(o.receiving_total_lines) : lines.length;
  const confirmedCount =
    Number(o.receiving_confirmed_count) >= 0 ? Number(o.receiving_confirmed_count) : 0;
  return {
    id,
    order_no,
    status,
    title: order_no || `订单 #${id}`,
    lines: lines.length ? lines : [{ id: "0", name: "（无行明细）", qty: "—", unit: "", lineNo: 0 }],
    receivingTotalLines: totalLines,
    receivingConfirmedCount: confirmedCount,
  };
}

/** 演示数据：用本地存储覆盖已称行数，便于列表「确认收货」与作业台同步 */
function applyDemoProgress(o: OrderBrief): OrderBrief {
  const token = getToken();
  if (token && token !== "demo") return o;
  const no = o.order_no || "";
  if (!no) return o;
  const cnt = countDemoConfirmedForOrder(
    no,
    o.lines.map((l) => l.id)
  );
  const total = o.receivingTotalLines ?? o.lines.length;
  return { ...o, receivingConfirmedCount: cnt, receivingTotalLines: total };
}

function canReceiveOrder(item: OrderBrief): boolean {
  if (item.status !== "收货") return false;
  const total = item.receivingTotalLines ?? item.lines.length ?? 0;
  if (total <= 0) return false;
  return (item.receivingConfirmedCount ?? 0) >= total;
}

function startReceive(item: OrderBrief) {
  if (!canReceiveOrder(item)) {
    uni.showToast({
      title: "请先完成全部明细的称重确认",
      icon: "none",
    });
    return;
  }
  receiveOrder.value = item;
}

function onReceiveDone() {
  receiveOrder.value = null;
  load();
}

function openOrder(item: OrderBrief) {
  const token = getToken();
  const numericId = /^\d+$/.test(String(item.id));
  if (numericId && token && token !== "demo") {
    uni.navigateTo({ url: `/pages/terminal/terminal?id=${item.id}` });
    return;
  }
  uni.navigateTo({
    url: `/pages/terminal/terminal?payload=${encodeURIComponent(JSON.stringify(item))}`,
  });
}

function goHistory() {
  uni.navigateTo({ url: "/pages/history/history" });
}

function goDevices() {
  uni.navigateTo({ url: "/pages/devices/devices" });
}

function goSerialDebug() {
  uni.navigateTo({ url: "/pages/serial-debug/serial-debug" });
}

function goUvcDebug() {
  uni.navigateTo({ url: "/pages/uvc-debug/uvc-debug" });
}

function logout() {
  clearToken();
  uni.reLaunch({ url: "/pages/login/login" });
}

onShow(() => {
  refreshLastLockPhoto();
  load();
});
</script>

<style scoped lang="scss">
@import "@/uni.scss";

.page {
  min-height: 100vh;
  background: $c-bg;
  padding: 24rpx;
  box-sizing: border-box;
}

/* 顶部导航栏 */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20rpx;
  gap: 12rpx;
}
.toolbar-title {
  font-size: 30rpx;
  font-weight: 700;
  color: $c-text-h;
  letter-spacing: 1rpx;
}
.toolbar-actions {
  display: flex;
  gap: 12rpx;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.link {
  background: $c-bg-card;
  color: $c-primary;
  border: 1rpx solid $c-border-med;
  border-radius: 999rpx;
  font-size: 24rpx;
  padding: 0 22rpx;
  height: 60rpx;
  line-height: 60rpx;
}
.link.danger {
  color: #b94040;
  border-color: rgba(185, 64, 64, 0.25);
}

/* 留痕卡片 */
.last-lock-card {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 24rpx;
  background: $c-bg-card;
  border-radius: $r-card;
  padding: 20rpx 24rpx;
  margin-bottom: 20rpx;
  box-shadow: $shadow-card;
  border: 1rpx solid $c-border;
  position: relative;
  overflow: hidden;
}
.last-lock-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6rpx;
  background: linear-gradient(180deg, #27794d, $c-primary);
  border-radius: 4rpx 0 0 4rpx;
}
.last-lock-thumb {
  width: 110rpx;
  height: 110rpx;
  border-radius: 16rpx;
  flex-shrink: 0;
  background: #e8f0ec;
}
.last-lock-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}
.last-lock-title {
  font-size: 26rpx;
  font-weight: 700;
  color: $c-text-h;
  letter-spacing: 1rpx;
}
.last-lock-sub {
  font-size: 24rpx;
  color: $c-text-b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.last-lock-time {
  font-size: 22rpx;
  color: $c-text-hint;
}

/* 留痕预览弹窗 */
.ll-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32rpx;
  box-sizing: border-box;
}
.ll-panel {
  width: 100%;
  max-width: 720px;
  max-height: 88vh;
  overflow: auto;
  background: $c-bg-card;
  border-radius: $r-card;
  padding: 28rpx 32rpx;
  box-sizing: border-box;
}
.ll-title {
  font-size: 32rpx;
  font-weight: 700;
  color: $c-text-h;
  display: block;
  margin-bottom: 8rpx;
}
.ll-sub {
  font-size: 24rpx;
  color: $c-text-m;
  display: block;
  margin-bottom: 20rpx;
}
.ll-img {
  width: 100%;
  border-radius: 16rpx;
  background: #eef3f0;
}
.ll-close {
  margin-top: 24rpx;
  width: 100%;
  background: $c-primary;
  color: #fff;
  border-radius: $r-btn;
  font-size: 28rpx;
  font-weight: 600;
}

/* 订单列表 */
.list {
  max-height: calc(100vh - 130rpx);
}
.row {
  background: $c-bg-card;
  border-radius: $r-card;
  margin-bottom: 20rpx;
  box-shadow: $shadow-card;
  border: 1rpx solid $c-border;
  overflow: hidden;
}
.row-main {
  padding: 28rpx 32rpx 18rpx;
}
.row-actions {
  display: flex;
  flex-direction: row;
  gap: 16rpx;
  padding: 16rpx 32rpx 24rpx;
  border-top: 1rpx solid $c-border;
  background: $c-bg-sub;
}
.btn-row {
  flex: 1;
  font-size: 26rpx;
  border-radius: $r-btn;
  height: 76rpx;
  line-height: 76rpx;
  font-weight: 600;
}
.btn-row.secondary {
  background: $c-bg-card;
  color: $c-primary;
  border: 1rpx solid $c-border-med;
}
.btn-row.primary {
  background: $c-primary;
  color: #fff;
  box-shadow: 0 4rpx 14rpx rgba(27, 94, 58, 0.22);
}
.btn-row.primary[disabled] {
  background: #b5d4c3;
  color: #fff;
  box-shadow: none;
}
.row-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16rpx;
}
.no {
  font-size: 30rpx;
  font-weight: 700;
  color: $c-text-h;
  flex: 1;
}
.tag {
  font-size: 22rpx;
  font-weight: 600;
  color: $c-primary;
  background: $c-done-bg;
  padding: 6rpx 18rpx;
  border-radius: $r-tag;
  flex-shrink: 0;
}
.meta {
  display: block;
  margin-top: 10rpx;
  font-size: 24rpx;
  color: $c-text-m;
}
.progress-row {
  margin-top: 18rpx;
  padding-top: 14rpx;
  border-top: 1rpx solid $c-border;
}
.prog-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10rpx;
}
.prog-label-text {
  font-size: 22rpx;
  color: $c-text-m;
}
.prog-text {
  font-size: 22rpx;
  font-weight: 600;
  color: $c-accent;
}
.prog-bar {
  height: 10rpx;
  border-radius: $r-tag;
  background: #d8ece0;
  overflow: hidden;
}
.prog-fill {
  height: 100%;
  border-radius: $r-tag;
  background: linear-gradient(90deg, $c-accent, $c-primary);
  transition: width 0.3s ease;
}
.center {
  padding: 120rpx 0;
  text-align: center;
  color: $c-text-m;
  font-size: 28rpx;
}
.empty .sub {
  display: block;
  margin-top: 16rpx;
  font-size: 24rpx;
  color: $c-text-hint;
  line-height: 1.6;
}

@media screen and (min-width: 960px) {
  .page { padding: 24rpx 36rpx; }
  .list { max-height: calc(100vh - 144rpx); }
  .row {
    display: flex;
    flex-direction: row;
    align-items: stretch;
  }
  .row-main { flex: 1; padding: 28rpx 32rpx; }
  .row-actions {
    width: 272rpx;
    border-top: none;
    border-left: 1rpx solid $c-border;
    padding: 20rpx;
    flex-direction: column;
    justify-content: center;
  }
  .btn-row { width: 100%; }
}
</style>
