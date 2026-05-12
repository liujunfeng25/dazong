<template>
  <view class="page">
    <text class="title">UVC 拍照调试</text>
    <text class="sub">
      与称重页可共用 USB 摄像头；双头请改「设备序号」后点打开。离开本页会自动尝试关闭 UVC。
      若「可用 UVC 插件: 否」：请在 HBuilderX 勾选本地插件 dazong-serial-scale 后重新云打包/自定义基座，并确认已用最新 dazong-serial-scale.aar。
      若弹窗「未添加 camera 模块」：manifest 已勾选 Camera 模块后需重新打包。
      【说明】「列出设备」优先走系统 UsbManager 视频类(14)枚举（与公司 SmartReceiv CameraSDK 一致），再回退库内枚举；返回含 deviceId 可与原生 uvcOpen 对齐。设备数 0 表示无视频类 USB 设备；与平板「系统相机」无关。
    </text>

    <view class="row">
      <text class="lab">设备序号 index</text>
      <input class="inp" type="number" v-model="deviceIndexStr" />
    </view>

    <view class="btn-row">
      <button class="btn ghost" @click="clearJsLog">清空 JS 日志</button>
      <button class="btn ghost" @click="clearNativeLog">清空原生日志</button>
      <button class="btn secondary" @click="doList">列出设备</button>
    </view>
    <view class="btn-row">
      <button class="btn secondary" @click="doOpen">打开</button>
      <button class="btn secondary" @click="doCapture">拍照</button>
      <button class="btn ghost" @click="doClose">关闭</button>
    </view>
    <view class="btn-row">
      <button class="btn primary" @click="doSystemCameraManual">
        系统相机（手动拍照）
      </button>
    </view>
    <text class="hint-manual">
      调起的是设备内置相机（非 USB）。与称重页「锁定读数」无 UVC 时的降级一致：由您按快门。即使上面「设备数 0」，这里通常仍能打开。
    </text>
    <view class="btn-row">
      <button class="btn secondary" @click="copyAll">复制 JS+原生日志</button>
    </view>

    <text class="cap">拍照预览</text>
    <image v-if="previewUri" class="preview" :src="previewUri" mode="aspectFit" />
    <text v-else class="muted">尚无预览</text>

    <text class="cap">JS 日志</text>
    <scroll-view scroll-y class="logbox">
      <text selectable class="logpre">{{ jsLogText }}</text>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { onUnload } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { UVC_DEFAULT_DEVICE_INDEX } from "../../config/uvcCamera";
import {
  captureWithSystemCamera,
  getUvcCameraDiagText,
  isUvcNativeAvailable,
  uvcCapture,
  uvcClearNativeLog,
  uvcClose,
  uvcFetchNativeLog,
  uvcListDevices,
  uvcOpen,
} from "../../utils/uvcCameraNative";

const deviceIndexStr = ref(String(UVC_DEFAULT_DEVICE_INDEX));
const previewUri = ref("");
const jsLines = ref<string[]>([]);

const jsLogText = computed(() =>
  jsLines.value.length ? jsLines.value.join("\n") : "(空)"
);

function jlog(msg: string) {
  const row = `${new Date().toLocaleString("zh-CN", { hour12: false })} ${msg}`;
  jsLines.value = [...jsLines.value, row].slice(-200);
  console.log("[UvcDebug]", msg);
}

function clearJsLog() {
  jsLines.value = [];
  jlog("JS 日志已清空");
}

async function clearNativeLog() {
  await uvcClearNativeLog();
  jlog("已请求清空原生 uvc 日志");
}

function deviceIndex(): number {
  const n = parseInt(deviceIndexStr.value, 10);
  return Number.isFinite(n) && n >= 0 ? n : UVC_DEFAULT_DEVICE_INDEX;
}

async function doList() {
  jlog(`可用 UVC 插件: ${isUvcNativeAvailable() ? "是" : "否"}`);
  const list = await uvcListDevices();
  jlog(`设备数 ${list.length}: ${JSON.stringify(list)}`);
}

async function doOpen() {
  jlog(`打开 index=${deviceIndex()}`);
  const ok = await uvcOpen(deviceIndex());
  jlog(ok ? "打开成功(回调 ok)" : "打开失败或超时");
}

async function doCapture() {
  jlog("拍照…");
  const cap = await uvcCapture();
  if (cap) {
    previewUri.value = cap.uri;
    jlog(`拍照成功 path=${cap.path}`);
    const nat = await uvcFetchNativeLog();
    jlog(`原生日志尾部: ${nat.slice(-400)}`);
  } else {
    jlog("拍照失败");
  }
}

async function doClose() {
  await uvcClose();
  jlog("已关闭");
}

/** 上一版锁定流程常用的系统相机路径：不调 UVC、不自动拍照 */
async function doSystemCameraManual() {
  jlog("系统相机（手动）…");
  const p = await captureWithSystemCamera();
  if (p) {
    previewUri.value = p;
    jlog(`已拍照 path=${p}`);
  } else {
    jlog("未选图或已取消");
  }
}

async function copyAll() {
  const nat = await uvcFetchNativeLog();
  const block =
    getUvcCameraDiagText() +
    "\n\n--- 原生 SerialScaleModule(UVC) 环形日志 ---\n" +
    nat;
  uni.setClipboardData({
    data: block,
    success() {
      uni.showToast({ title: "已复制", icon: "none" });
    },
  });
}

onUnload(() => {
  void uvcClose();
});
</script>

<style scoped lang="scss">
.page {
  min-height: 100vh;
  padding: 24rpx;
  box-sizing: border-box;
  background: #f4f7f5;
}
.title {
  font-size: 32rpx;
  font-weight: 700;
  color: #143d2a;
  display: block;
}
.sub {
  display: block;
  margin-top: 10rpx;
  font-size: 22rpx;
  color: #6b7c73;
  line-height: 1.5;
  margin-bottom: 24rpx;
}
.row {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 16rpx;
  margin-bottom: 16rpx;
}
.lab {
  font-size: 26rpx;
  color: #5a6f66;
  width: 220rpx;
}
.inp {
  flex: 1;
  background: #fff;
  border: 1rpx solid #d5ddd7;
  border-radius: 10rpx;
  padding: 12rpx 16rpx;
  font-size: 28rpx;
}
.btn-row {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: 12rpx;
  margin-bottom: 16rpx;
}
.btn {
  font-size: 24rpx;
  padding: 0 20rpx;
  border-radius: 10rpx;
}
.secondary {
  background: #e3f0e8;
  color: #143d2a;
}
.ghost {
  background: #fff;
  color: #5a6f66;
  border: 1rpx solid #d5ddd7;
}
.primary {
  background: #1b5e3a;
  color: #fff;
  border: none;
}
.hint-manual {
  display: block;
  font-size: 22rpx;
  color: #6b7c73;
  line-height: 1.45;
  margin-bottom: 16rpx;
}
.cap {
  display: block;
  font-size: 26rpx;
  font-weight: 600;
  color: #143d2a;
  margin: 20rpx 0 10rpx;
}
.preview {
  width: 100%;
  height: 360rpx;
  background: #fff;
  border-radius: 12rpx;
  border: 1rpx solid #e1e3df;
}
.muted {
  font-size: 24rpx;
  color: #9aa89f;
}
.logbox {
  max-height: 40vh;
  background: #fff;
  border: 1rpx solid #e1e3df;
  border-radius: 12rpx;
  padding: 12rpx;
}
.logpre {
  font-size: 22rpx;
  line-height: 1.45;
  color: #1a1a1a;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
