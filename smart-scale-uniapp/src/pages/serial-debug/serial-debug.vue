<template>
  <view class="page">
    <view class="toolbar">
      <button size="mini" class="link" @click="goBack">返回</button>
    </view>
    <scroll-view scroll-y class="form-scroll">
      <view class="card">
        <text class="cap">串口参数</text>
        <view class="field">
          <text class="lab">设备路径</text>
          <input v-model="path" class="inp" type="text" />
        </view>
        <view class="field">
          <text class="lab">波特率</text>
          <input v-model="baud" class="inp" type="number" />
        </view>
      </view>
      <view class="card">
        <text class="cap">读原始数据</text>
        <view class="field row2">
          <view class="half">
            <text class="lab">maxWaitMs</text>
            <input v-model="maxWaitMs" class="inp" type="number" />
          </view>
          <view class="half">
            <text class="lab">maxBytes</text>
            <input v-model="maxBytes" class="inp" type="number" />
          </view>
        </view>
        <view class="chk">
          <switch :checked="untilCrlf" @change="onUntilCrlfChange" />
          <text>遇 CRLF 提前结束 (untilCrlf)</text>
        </view>
      </view>
      <view class="card">
        <text class="cap">操作</text>
        <view class="btn-grid">
          <button class="btn secondary" @click="doStatus">查询状态</button>
          <button class="btn primary" @click="doOpen">打开串口</button>
          <button class="btn ghost" @click="doClose">关闭串口</button>
        </view>
        <text class="subcap">首衡快捷发（十六进制）</text>
        <view class="btn-grid">
          <button class="btn secondary sm" @click="sendQuick('52')">52 (R 读数)</button>
          <button class="btn secondary sm" @click="sendQuick('54')">54 (T 去皮)</button>
          <button class="btn secondary sm" @click="sendQuick('5A')">5A (Z 置零)</button>
        </view>
        <view class="field">
          <text class="lab">自定义 HEX</text>
          <input v-model="customHex" class="inp mono" placeholder="如 52 或 5A0D0A" />
        </view>
        <button class="btn secondary" @click="sendCustom">发送自定义 HEX</button>
        <button class="btn primary" @click="doReadRaw">读原始数据</button>
      </view>
      <view class="card">
        <text class="cap">日志</text>
        <view class="log-actions">
          <button size="mini" class="link" @click="copyReport">复制报告</button>
          <button size="mini" class="link" @click="clearLog">清空流水</button>
          <button size="mini" class="link" @click="refreshLog">刷新显示</button>
        </view>
        <text class="hint">
          与「称重作业台」不要同时占串口；离开本页会自动关串口。首衡「指令发送」模式需先发 52 再点读原始数据。
        </text>
      </view>
    </scroll-view>
    <scroll-view scroll-y class="log-scroll">
      <text selectable class="log-pre">{{ logText }}</text>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import {
  SCALE_SERIAL_BAUD,
  SCALE_SERIAL_DEVICE_PATH,
} from "../../config/scaleSerial";
import {
  appendSerialDebugLog,
  buildSerialDebugReport,
  clearSerialDebugLog,
  getSerialDebugLogText,
  nativeClosePort,
  nativeDebugReadRaw,
  nativeDebugStatus,
  nativeDebugWriteHex,
  nativeOpen,
} from "../../utils/serialDebugNative";

const path = ref(SCALE_SERIAL_DEVICE_PATH);
const baud = ref(String(SCALE_SERIAL_BAUD));
const maxWaitMs = ref("3000");
const maxBytes = ref("512");
const untilCrlf = ref(false);
const customHex = ref("");
const logText = ref("");

function onUntilCrlfChange(e: unknown) {
  const d = e as { detail?: { value?: boolean } };
  untilCrlf.value = !!d.detail?.value;
}

function refreshLog() {
  logText.value = getSerialDebugLogText();
}

function goBack() {
  uni.navigateBack();
}

function parseBaud(): number {
  const n = parseInt(String(baud.value), 10);
  return Number.isFinite(n) && n > 0 ? n : 9600;
}

function parseMaxWait(): number {
  const n = parseInt(String(maxWaitMs.value), 10);
  return Number.isFinite(n) ? Math.min(30000, Math.max(100, n)) : 3000;
}

function parseMaxBytes(): number {
  const n = parseInt(String(maxBytes.value), 10);
  return Number.isFinite(n) ? Math.min(4096, Math.max(1, n)) : 512;
}

async function doStatus() {
  try {
    appendSerialDebugLog("操作: 查询状态");
    await nativeDebugStatus();
  } catch (e) {
    appendSerialDebugLog("失败", String(e));
    uni.showToast({ title: String(e), icon: "none" });
  }
  refreshLog();
}

async function doOpen() {
  try {
    appendSerialDebugLog("操作: 打开串口", { path: path.value, baud: parseBaud() });
    const r = await nativeOpen(path.value.trim(), parseBaud());
    if (!r?.ok) {
      uni.showToast({ title: r?.err || "打开失败", icon: "none" });
    } else {
      uni.showToast({ title: "已打开", icon: "none" });
    }
  } catch (e) {
    appendSerialDebugLog("打开失败", String(e));
    uni.showToast({ title: String(e), icon: "none" });
  }
  refreshLog();
}

async function doClose() {
  try {
    appendSerialDebugLog("操作: 关闭串口");
    await nativeClosePort();
    uni.showToast({ title: "已关闭", icon: "none" });
  } catch (e) {
    appendSerialDebugLog("关闭失败", String(e));
    uni.showToast({ title: String(e), icon: "none" });
  }
  refreshLog();
}

async function sendQuick(hex: string) {
  try {
    appendSerialDebugLog("操作: 快捷发送", { hex });
    const r = await nativeDebugWriteHex(hex);
    if (!r?.ok) {
      uni.showToast({ title: r?.err || "发送失败", icon: "none" });
    }
  } catch (e) {
    appendSerialDebugLog("发送失败", String(e));
    uni.showToast({ title: String(e), icon: "none" });
  }
  refreshLog();
}

async function sendCustom() {
  const h = customHex.value.trim();
  if (!h) {
    uni.showToast({ title: "请输入 HEX", icon: "none" });
    return;
  }
  await sendQuick(h.replace(/\s+/g, " "));
}

async function doReadRaw() {
  try {
    appendSerialDebugLog("操作: 读原始数据", {
      maxWaitMs: parseMaxWait(),
      maxBytes: parseMaxBytes(),
      untilCrlf: untilCrlf.value,
    });
    const r = await nativeDebugReadRaw({
      maxWaitMs: parseMaxWait(),
      maxBytes: parseMaxBytes(),
      untilCrlf: untilCrlf.value,
    });
    if (r && r.ok === false) {
      uni.showToast({ title: r.err || "读失败", icon: "none" });
    }
  } catch (e) {
    appendSerialDebugLog("读失败", String(e));
    uni.showToast({ title: String(e), icon: "none" });
  }
  refreshLog();
}

function clearLog() {
  clearSerialDebugLog();
  refreshLog();
}

function copyReport() {
  const text = buildSerialDebugReport(path.value.trim(), parseBaud());
  uni.setClipboardData({
    data: text,
    success() {
      uni.showToast({ title: "已复制报告", icon: "none" });
    },
  });
}

onMounted(async () => {
  appendSerialDebugLog("进入串口调试页：先关串口，避免与称重页抢口");
  try {
    await nativeClosePort();
  } catch (e) {
    appendSerialDebugLog("关串口(可忽略)", String(e));
  }
  try {
    await nativeDebugStatus();
  } catch (e) {
    appendSerialDebugLog("初始状态查询失败", String(e));
  }
  refreshLog();
});

onUnmounted(async () => {
  try {
    await nativeClosePort();
  } catch {
    /* ignore */
  }
});
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f4f7f5;
  box-sizing: border-box;
}
.toolbar {
  padding: 12rpx 24rpx;
  background: #fff;
  border-bottom: 1rpx solid #e1e3df;
}
.link {
  color: #1b5e3a;
}
.form-scroll {
  flex: 0 0 auto;
  max-height: 52vh;
  padding: 16rpx 20rpx;
  box-sizing: border-box;
}
.card {
  background: #fff;
  border-radius: 16rpx;
  padding: 20rpx 24rpx;
  margin-bottom: 16rpx;
  border: 1rpx solid #e8ebe8;
}
.cap {
  font-size: 28rpx;
  font-weight: 700;
  color: #143d2a;
  display: block;
  margin-bottom: 16rpx;
}
.subcap {
  font-size: 24rpx;
  color: #5a6f66;
  display: block;
  margin: 16rpx 0 12rpx;
}
.field {
  margin-bottom: 16rpx;
}
.row2 {
  display: flex;
  flex-direction: row;
  gap: 16rpx;
}
.half {
  flex: 1;
}
.lab {
  font-size: 22rpx;
  color: #6b7c73;
  display: block;
  margin-bottom: 6rpx;
}
.inp {
  border: 1rpx solid #c0c9c2;
  border-radius: 10rpx;
  padding: 12rpx 16rpx;
  font-size: 26rpx;
  background: #fafbf9;
}
.inp.mono {
  font-family: ui-monospace, monospace;
}
.chk {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 12rpx;
  font-size: 24rpx;
  color: #143d2a;
  margin-top: 8rpx;
}
.btn-grid {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: 12rpx;
  margin-bottom: 12rpx;
}
.btn {
  margin: 0;
  font-size: 26rpx;
  border-radius: 12rpx;
}
.btn.sm {
  font-size: 24rpx;
  padding: 0 12rpx;
}
.primary {
  background: #1b5e3a;
  color: #fff;
}
.secondary {
  background: #e3f0e8;
  color: #143d2a;
}
.ghost {
  background: transparent;
  color: #5a6f66;
  border: 1rpx solid #c0c9c2;
}
.log-actions {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: 16rpx;
  margin-bottom: 12rpx;
}
.hint {
  font-size: 22rpx;
  color: #6b7c73;
  line-height: 1.5;
}
.log-scroll {
  flex: 1;
  min-height: 200rpx;
  padding: 0 20rpx 24rpx;
  box-sizing: border-box;
}
.log-pre {
  display: block;
  font-size: 22rpx;
  line-height: 1.45;
  color: #1a1a1a;
  white-space: pre-wrap;
  word-break: break-all;
  background: #fff;
  border-radius: 12rpx;
  padding: 16rpx;
  border: 1rpx solid #e1e3df;
}
</style>
