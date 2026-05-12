<template>
  <view class="page">
    <view class="toolbar">
      <text class="hint">默认展示近 30 天订单，可改日期后查询</text>
    </view>
    <view class="filters">
      <picker mode="date" :value="startDay" @change="onStart">
        <view class="pick">开始：{{ startDay }}</view>
      </picker>
      <picker mode="date" :value="endDay" @change="onEnd">
        <view class="pick">结束：{{ endDay }}</view>
      </picker>
      <button size="mini" class="btn-go" @click="load">查询</button>
    </view>
    <view v-if="loading" class="center"><text>加载中…</text></view>
    <view v-else-if="orders.length === 0" class="center empty">
      <text>该时段无订单</text>
    </view>
    <scroll-view v-else scroll-y class="list">
      <view
        v-for="item in orders"
        :key="item.id"
        class="row"
        @click="openDetail(item)"
      >
        <view class="row-top">
          <text class="no">{{ item.title }}</text>
          <text class="tag">{{ item.status || "—" }}</text>
        </view>
        <text class="meta">{{ item.order_no }}</text>
        <view class="progress-row">
          <text class="prog-label">称重进度</text>
          <text class="prog-text">
            {{ item.receivingConfirmedCount ?? 0 }} / {{ item.receivingTotalLines ?? item.lines.length }} 行已确认
          </text>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { onLoad, onShow } from "@dcloudio/uni-app";
import { ref } from "vue";
import type { OrderBrief } from "../../types/order";
import { getToken, request } from "../../utils/request";

const loading = ref(false);
const orders = ref<OrderBrief[]>([]);
const startDay = ref("");
const endDay = ref("");

function pad(n: number) {
  return String(n).padStart(2, "0");
}

function defaultRange() {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 30);
  const ys = `${start.getFullYear()}-${pad(start.getMonth() + 1)}-${pad(start.getDate())}`;
  const ye = `${end.getFullYear()}-${pad(end.getMonth() + 1)}-${pad(end.getDate())}`;
  startDay.value = ys;
  endDay.value = ye;
}

function onStart(e: { detail: { value: string } }) {
  startDay.value = e.detail.value;
}
function onEnd(e: { detail: { value: string } }) {
  endDay.value = e.detail.value;
}

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
  const rtl = o.receiving_total_lines;
  const totalLines =
    rtl != null && rtl !== "" && !Number.isNaN(Number(rtl)) ? Number(rtl) : lines.length;
  const confirmedCount =
    o.receiving_confirmed_count != null && !Number.isNaN(Number(o.receiving_confirmed_count))
      ? Number(o.receiving_confirmed_count)
      : 0;
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

async function load() {
  const token = getToken();
  if (!token || token === "demo") {
    orders.value = [];
    uni.showToast({ title: "请登录后查看历史", icon: "none" });
    return;
  }
  loading.value = true;
  try {
    const data = await request<unknown>(
      `/orders?created_date_start=${startDay.value}&created_date_end=${endDay.value}`
    );
    const raw = Array.isArray(data) ? data : [];
    const mapped = (raw as Record<string, unknown>[]).map(normalizeListOrder);
    orders.value = mapped.filter((o) =>
      ["收货", "收货确认", "已结算", "发货"].includes(o.status || "")
    );
  } catch {
    uni.showToast({ title: "加载失败", icon: "none" });
    orders.value = [];
  } finally {
    loading.value = false;
  }
}

function openDetail(item: OrderBrief) {
  if (!/^\d+$/.test(String(item.id))) return;
  const ro = item.status !== "收货" ? "&readonly=1" : "";
  uni.navigateTo({ url: `/pages/terminal/terminal?id=${item.id}${ro}` });
}

onLoad(() => {
  defaultRange();
});

onShow(() => {
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

.toolbar {
  margin-bottom: 14rpx;
}

.hint {
  font-size: 22rpx;
  color: $c-text-m;
}

.filters {
  background: $c-bg-card;
  border-radius: $r-card;
  padding: 20rpx 24rpx;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14rpx;
  margin-bottom: 20rpx;
  box-shadow: $shadow-card;
  border: 1rpx solid $c-border;
}

.pick {
  background: $c-bg-sub;
  padding: 12rpx 24rpx;
  border-radius: $r-btn;
  font-size: 24rpx;
  color: $c-text-h;
  border: 1rpx solid $c-border-med;
}

.btn-go {
  background: linear-gradient(160deg, #27794d 0%, $c-primary 100%);
  color: #fff;
  border-radius: $r-btn;
  font-size: 24rpx;
  border: none;
  box-shadow: 0 4rpx 12rpx rgba(27, 94, 58, 0.22);
}

.list {
  max-height: calc(100vh - 260rpx);
}

.row {
  background: $c-bg-card;
  border-radius: $r-card;
  padding: 28rpx 28rpx 28rpx 34rpx;
  margin-bottom: 16rpx;
  box-shadow: $shadow-card;
  border: 1rpx solid $c-border;
  position: relative;
}

.row::before {
  content: "";
  position: absolute;
  left: 0;
  top: 16rpx;
  bottom: 16rpx;
  width: 6rpx;
  border-radius: 999rpx;
  background: $c-border-med;
}

.row-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.no {
  font-size: 30rpx;
  font-weight: 700;
  color: $c-text-h;
}

.tag {
  font-size: 22rpx;
  color: $c-done-text;
  background: $c-done-bg;
  padding: 6rpx 16rpx;
  border-radius: $r-tag;
  font-weight: 600;
}

.meta {
  display: block;
  margin-top: 8rpx;
  font-size: 24rpx;
  color: $c-text-m;
}

.progress-row {
  margin-top: 16rpx;
  padding-top: 14rpx;
  border-top: 1rpx solid $c-border;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.prog-label {
  font-size: 22rpx;
  color: $c-text-m;
}

.prog-text {
  font-size: 26rpx;
  font-weight: 700;
  color: $c-primary;
}

.center {
  padding: 80rpx 0;
  text-align: center;
  color: $c-text-m;
}
</style>
