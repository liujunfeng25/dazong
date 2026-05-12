<template>
  <view class="page">
    <text class="tip">
      电子秤多为 BLE：蓝牙打开 → 系统定位页里「使用位置信息」打开，且「WLAN 和蓝牙扫描」里打开蓝牙扫描 →
      再搜索。若仍报 Location services are turned off（10016），点下面「打开系统定位设置」逐项检查。协议见
      `src/config/scaleBle.ts`。
    </text>
    <button class="btn" @click="openAdapter">打开蓝牙适配器</button>
    <button class="btn" :disabled="!adapterReady" @click="startScan">
      {{ scanning ? "搜索中…" : "搜索附近 BLE 设备" }}
    </button>
    <button class="btn secondary" @click="openSystemLocationSettings">打开系统定位设置（修 10016）</button>
    <button v-if="scanning" class="btn secondary" @click="stopScan">停止搜索</button>
    <button
      v-if="connectedId"
      class="btn ghost"
      @click="disconnect"
    >
      断开连接
    </button>

    <view v-if="devices.length" class="list-cap">设备列表（点击连接）</view>
    <scroll-view v-if="devices.length" scroll-y class="list">
      <view
        v-for="d in devices"
        :key="d.deviceId"
        class="row"
        :class="{ active: d.deviceId === connectedId }"
        @click="connect(d)"
      >
        <view class="row-top">
          <text class="name">{{ d.name || "（无名称）" }}</text>
          <text class="rssi">{{ d.RSSI }} dBm</text>
        </view>
        <text class="id">{{ d.deviceId }}</text>
      </view>
    </scroll-view>

    <view v-if="lastHex || weightLine" class="panel">
      <text v-if="weightLine" class="weight">{{ weightLine }}</text>
      <text v-if="lastHex" class="hex">原始 notify：{{ lastHex }}</text>
    </view>
    <view v-if="log" class="msg">{{ log }}</view>

    <view class="log-box">
      <view class="log-toolbar">
        <text class="log-title">调试日志（真机操作后点「复制日志」发给我）</text>
        <view class="log-btns">
          <button size="mini" class="log-btn" @click="copyDebugLog">复制日志</button>
          <button size="mini" class="log-btn ghost" @click="clearDebugLog">清空</button>
        </view>
      </view>
      <scroll-view scroll-y class="log-scroll" :scroll-top="logScrollTop">
        <text class="log-body" selectable>{{ debugLogText }}</text>
      </scroll-view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import {
  bleLog,
  bleLogError,
  clearBleLog,
  getBleLogText,
  onBleLog,
} from "../../utils/bleLogger";
import {
  SCALE_BLE_CANDIDATES,
  SCALE_BLE_NOTIFY_CHAR_UUID,
  SCALE_BLE_POLL_HEX,
  SCALE_BLE_SCAN_SERVICE_UUIDS,
  SCALE_BLE_SERVICE_UUID,
  SCALE_BLE_WRITE_CHAR_UUID,
  hexStringToArrayBuffer,
  matchBleUuid,
  tryParseWeightKg,
} from "../../config/scaleBle";

type BleRow = { deviceId: string; name: string; RSSI: number };

const adapterReady = ref(false);
const scanning = ref(false);
const devices = ref<BleRow[]>([]);
const deviceMap = new Map<string, BleRow>();
const connectedId = ref("");
const lastHex = ref("");
const weightLine = ref("");
const log = ref("");
const debugLogText = ref("");
const logScrollTop = ref(0);
let unsubsBleLog: (() => void) | null = null;

let foundHandler: ((res: UniApp.OnBluetoothDeviceFoundResult) => void) | null = null;
let notifyHandler: ((res: UniNamespace.OnBLECharacteristicValueChangeSuccess) => void) | null = null;

function setLog(s: string) {
  log.value = s;
  bleLog("界面", s);
}

function copyDebugLog() {
  const t = getBleLogText();
  if (!t) {
    uni.showToast({ title: "暂无日志", icon: "none" });
    return;
  }
  uni.setClipboardData({
    data: t,
    success: () => uni.showToast({ title: "已复制", icon: "none" }),
  });
}

function clearDebugLog() {
  clearBleLog();
  debugLogText.value = "";
  bleLog("界面", "日志已清空");
}

function syncDebugLog() {
  debugLogText.value = getBleLogText();
  logScrollTop.value = debugLogText.value.length + Date.now();
}

function ab2hex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join(" ")
    .toUpperCase();
}

/** App 端 value 多为 ArrayBuffer；类型声明为 any[]，这里统一转成 ArrayBuffer */
function bleValueToBuffer(value: unknown): ArrayBuffer | null {
  if (value == null) return null;
  if (value instanceof ArrayBuffer) return value;
  if (Array.isArray(value)) {
    const u8 = new Uint8Array(value.length);
    for (let i = 0; i < value.length; i++) u8[i] = Number(value[i]) & 0xff;
    return u8.buffer;
  }
  return null;
}

/** 跳转系统「定位」页：解决部分 ROM 上「应用已授权定位」但 BLE 仍报 Location services are turned off */
function openSystemLocationSettings() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const p = typeof plus !== "undefined" ? (plus as any) : null;
  if (!p?.android) {
    uni.showToast({ title: "仅 App 端可用", icon: "none" });
    return;
  }
  try {
    const main = p.android.runtimeMainActivity();
    const Intent = p.android.importClass("android.content.Intent");
    const Settings = p.android.importClass("android.provider.Settings");
    const intent = new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS);
    main.startActivity(intent);
    setLog(
      "已打开系统定位页。请确认：①「使用位置信息」为开；②点进「WLAN 和蓝牙扫描」打开「蓝牙扫描」；③定位模式若有「高精度/高准确度」请选中。完成后返回本页再搜。"
    );
    bleLog("界面", "ACTION_LOCATION_SOURCE_SETTINGS");
  } catch (e) {
    bleLogError("界面", "打开系统定位设置失败", e);
    uni.showToast({ title: "请手动进入：设置 → 位置信息", icon: "none" });
  }
}

function openAdapter() {
  bleLog("步骤", "openBluetoothAdapter 调用");
  uni.openBluetoothAdapter({
    success: () => {
      adapterReady.value = true;
      setLog("蓝牙适配器已就绪，可开始搜索。");
    },
    fail: (e) => {
      bleLogError("openAdapter", "openBluetoothAdapter 失败", e);
      setLog(`打开失败：${e.errMsg || "未知"}。请打开手机蓝牙，并确认已在 manifest 勾选 Bluetooth 模块后重新打包。`);
    },
  });
}

function flushDeviceList() {
  devices.value = Array.from(deviceMap.values()).sort((a, b) => b.RSSI - a.RSSI);
}

function startScan() {
  loggedDeviceIds.clear();
  deviceMap.clear();
  flushDeviceList();
  lastHex.value = "";
  weightLine.value = "";
  const services =
    SCALE_BLE_SCAN_SERVICE_UUIDS.map((u) => u.trim()).filter(Boolean);
  bleLog("步骤", `startBluetoothDevicesDiscovery services=${services.length ? services.join(",") : "全部"}`);
  uni.startBluetoothDevicesDiscovery({
    allowDuplicatesKey: false,
    services: services.length ? services : undefined,
    success: () => {
      scanning.value = true;
      setLog(services.length ? `正在搜索（限定服务 ${services.length} 个）…` : "正在搜索附近 BLE…");
    },
    fail: (e) => {
      bleLogError("scan", "startBluetoothDevicesDiscovery 失败", e);
      const msg = String(e.errMsg || "");
      let hint =
        "Android 12+ 需「附近设备/蓝牙」权限；部分机型还需在系统设置里打开「定位服务」总开关（与 GPS 无关，是系统对 BLE 扫描的要求）。";
      if (/location services are turned off/i.test(msg) || e.code === 10016) {
        hint =
          "这是系统判定「定位源未开」，与「应用定位权限」不同。请点上方「打开系统定位设置」，在同一页打开「使用位置信息」，并进入「WLAN 和蓝牙扫描」打开蓝牙扫描；若有「定位模式」选高精度。仍不行则可能是单位策略或 ROM 限制。";
      }
      setLog(`开始搜索失败：${msg || "未知"}。${hint}`);
    },
  });
}

function stopScan() {
  bleLog("步骤", "stopBluetoothDevicesDiscovery");
  uni.stopBluetoothDevicesDiscovery({
    complete: () => {
      scanning.value = false;
    },
  });
}

function connect(row: BleRow) {
  if (!adapterReady.value) return;
  stopScan();
  if (connectedId.value && connectedId.value !== row.deviceId) {
    uni.closeBLEConnection({ deviceId: connectedId.value });
  }
  lastHex.value = "";
  weightLine.value = "";
  bleLog("步骤", `createBLEConnection deviceId=${row.deviceId} name=${row.name || "-"}`);
  setLog(`正在连接 ${row.name || row.deviceId}…`);
  uni.createBLEConnection({
    deviceId: row.deviceId,
    success: () => {
      connectedId.value = row.deviceId;
      setLog("已连接，正在发现服务…");
      setTimeout(() => void discoverAndSubscribe(row.deviceId), 600);
    },
    fail: (e) => {
      bleLogError("connect", "createBLEConnection 失败", e);
      setLog(`连接失败：${e.errMsg || "未知"}`);
    },
  });
}

function disconnect() {
  const id = connectedId.value;
  if (!id) return;
  bleLog("步骤", `closeBLEConnection deviceId=${id}`);
  uni.closeBLEConnection({
    deviceId: id,
    complete: () => {
      connectedId.value = "";
      lastHex.value = "";
      weightLine.value = "";
      setLog("已断开。");
    },
  });
}

async function getCharacteristics(
  deviceId: string,
  serviceId: string
): Promise<UniApp.GetBLEDeviceCharacteristicsSuccess> {
  return new Promise((resolve, reject) => {
    uni.getBLEDeviceCharacteristics({
      deviceId,
      serviceId,
      success: resolve,
      fail: reject,
    });
  });
}

async function enableNotify(
  deviceId: string,
  serviceId: string,
  characteristicId: string
): Promise<void> {
  bleLog(
    "notify",
    `notifyBLECharacteristicValueChange 开启 deviceId=${deviceId} serviceId=${serviceId} charId=${characteristicId}`
  );
  await new Promise<void>((resolve, reject) => {
    uni.notifyBLECharacteristicValueChange({
      deviceId,
      serviceId,
      characteristicId,
      state: true,
      success: () => resolve(),
      fail: reject,
    });
  });
}

/** 按指定服务+通知 UUID 订阅（UUID 支持 16 位别名匹配） */
async function trySubscribePair(
  deviceId: string,
  svcs: UniApp.GetBLEDeviceServicesSuccess,
  serviceUuid: string,
  notifyUuid: string
): Promise<string | null> {
  const svc = svcs.services.find((s) => matchBleUuid(s.uuid, serviceUuid));
  if (!svc) {
    bleLog("订阅", `未匹配服务：期望 ${serviceUuid}`);
    return null;
  }
  let chRes: UniApp.GetBLEDeviceCharacteristicsSuccess;
  try {
    chRes = await getCharacteristics(deviceId, svc.uuid);
  } catch (e) {
    bleLogError("GATT", `getBLEDeviceCharacteristics 失败 service=${svc.uuid}`, e);
    return null;
  }
  const picked = chRes.characteristics.find(
    (c) =>
      matchBleUuid(c.uuid, notifyUuid) && (c.properties.notify || c.properties.indicate)
  );
  if (!picked) {
    bleLog(
      "订阅",
      `服务 ${svc.uuid} 下无匹配通知特征 ${notifyUuid}；特性: ${chRes.characteristics
        .map(
          (c) =>
            `${c.uuid}(notify=${!!c.properties.notify} indicate=${!!c.properties.indicate} write=${!!c.properties.write})`
        )
        .join("; ")}`
    );
    return null;
  }
  await new Promise((r) => setTimeout(r, 300));
  try {
    await enableNotify(deviceId, svc.uuid, picked.uuid);
    bleLog("订阅", `成功 service=${svc.uuid} notifyChar=${picked.uuid}`);
  } catch (e) {
    bleLogError("notify", "notifyBLECharacteristicValueChange 失败", e);
    throw e;
  }
  return svc.uuid;
}

/** 配置的手动 UUID 或内置候选都失败时，订阅任意服务上第一个 notify */
async function subscribeFirstNotify(
  deviceId: string,
  svcs: UniApp.GetBLEDeviceServicesSuccess
): Promise<boolean> {
  for (const svc of svcs.services) {
    let chRes: UniApp.GetBLEDeviceCharacteristicsSuccess;
    try {
      chRes = await getCharacteristics(deviceId, svc.uuid);
    } catch (e) {
      bleLogError("GATT", `getBLEDeviceCharacteristics 失败 service=${svc.uuid}`, e);
      continue;
    }
    const picked = chRes.characteristics.find((c) => c.properties.notify || c.properties.indicate);
    if (!picked) continue;
    await new Promise((r) => setTimeout(r, 300));
    try {
      await enableNotify(deviceId, svc.uuid, picked.uuid);
      bleLog("订阅", `首个 notify 成功 service=${svc.uuid} char=${picked.uuid}`);
    } catch (e) {
      bleLogError("订阅", `首个 notify 失败 service=${svc.uuid}`, e);
      continue;
    }
    setLog(
      `已订阅（自动首个 notify）：服务 ${svc.uuid} / 特征 ${picked.uuid}。若重量不对，请看 hex 并在 scaleBle.ts 调整。`
    );
    await maybeSendPoll(deviceId, svc.uuid);
    return true;
  }
  return false;
}

async function maybeSendPoll(deviceId: string, serviceId: string): Promise<void> {
  const hex = SCALE_BLE_POLL_HEX.trim();
  const wu = SCALE_BLE_WRITE_CHAR_UUID.trim();
  if (!hex || !wu) return;
  try {
    const chRes = await getCharacteristics(deviceId, serviceId);
    const wc = chRes.characteristics.find(
      (c) =>
        matchBleUuid(c.uuid, wu) && (c.properties.write || c.properties.writeNoResponse)
    );
    if (!wc) {
      setLog("已配置 SCALE_BLE_POLL_HEX，但未找到可写特征，请核对 SCALE_BLE_WRITE_CHAR_UUID。");
      return;
    }
    const buf = hexStringToArrayBuffer(hex);
    const value = Array.from(new Uint8Array(buf));
    bleLog("write", `writeBLECharacteristicValue char=${wc.uuid} hex=${hex} bytes=${value.length}`);
    await new Promise((r) => setTimeout(r, 500));
    await new Promise<void>((resolve, reject) => {
      uni.writeBLECharacteristicValue({
        deviceId,
        serviceId,
        characteristicId: wc.uuid,
        value,
        success: () => resolve(),
        fail: reject,
      });
    });
    bleLog("write", "writeBLECharacteristicValue 成功");
    setLog(`${log.value} 已发送轮询指令。`);
  } catch (e) {
    bleLogError("write", "writeBLECharacteristicValue 失败", e);
    const msg = e && typeof e === "object" && "errMsg" in e ? String((e as { errMsg?: string }).errMsg) : String(e);
    setLog(`轮询写入失败：${msg}`);
  }
}

async function discoverAndSubscribe(deviceId: string): Promise<void> {
  try {
    bleLog("GATT", "getBLEDeviceServices 请求中…");
    const svcs = await new Promise<UniApp.GetBLEDeviceServicesSuccess>((resolve, reject) => {
      uni.getBLEDeviceServices({
        deviceId,
        success: resolve,
        fail: (err) => {
          bleLogError("GATT", "getBLEDeviceServices 失败", err);
          reject(err);
        },
      });
    });

    bleLog("GATT", `服务数量=${svcs.services.length}`);
    svcs.services.forEach((s, i) => {
      bleLog("GATT", `  [${i}] ${s.uuid}`);
    });

    const wantService = SCALE_BLE_SERVICE_UUID.trim();
    const wantNotify = SCALE_BLE_NOTIFY_CHAR_UUID.trim();

    if (wantService && wantNotify) {
      bleLog("订阅", `尝试手动配置 service=${wantService} notify=${wantNotify}`);
      const sid = await trySubscribePair(deviceId, svcs, wantService, wantNotify);
      if (sid) {
        setLog(`已按手动配置订阅：服务 ${wantService} / 通知 ${wantNotify}`);
        await maybeSendPoll(deviceId, sid);
        return;
      }
      setLog("手动配置的 UUID 订阅失败，尝试内置首衡/透传候选…");
    }

    for (const c of SCALE_BLE_CANDIDATES) {
      bleLog("订阅", `尝试候选「${c.label}」`);
      try {
        const sid = await trySubscribePair(deviceId, svcs, c.service, c.notify);
        if (sid) {
          setLog(`已订阅「${c.label}」。请放重物试称；请看解析重量或原始 hex。`);
          await maybeSendPoll(deviceId, sid);
          return;
        }
      } catch (e) {
        bleLogError("订阅", `候选「${c.label}」notify 失败`, e);
      }
    }

    bleLog("订阅", "尝试订阅任意首个 notify 特征");
    if (await subscribeFirstNotify(deviceId, svcs)) return;

    setLog(
      `未找到 notify 特征。当前服务：${svcs.services.map((s) => s.uuid).join(", ") || "无"}。请联系首衡索取 BLE UUID 与数据格式。`
    );
  } catch (e) {
    bleLogError("GATT", "discoverAndSubscribe 异常", e);
    const msg = e && typeof e === "object" && "errMsg" in e ? String((e as { errMsg?: string }).errMsg) : String(e);
    setLog(`发现服务失败：${msg}`);
  }
}

const loggedDeviceIds = new Set<string>();
let lastNotifyLogHex = "";
let lastNotifyLogAt = 0;

onMounted(() => {
  unsubsBleLog = onBleLog(() => {
    syncDebugLog();
  });
  bleLog("页面", "蓝牙调试页就绪；请：打开适配器 → 搜索 → 点设备连接。完成后点「复制日志」。");
  syncDebugLog();

  foundHandler = (res) => {
    for (const d of res.devices || []) {
      if (!d.deviceId) continue;
      if (!loggedDeviceIds.has(d.deviceId)) {
        loggedDeviceIds.add(d.deviceId);
        bleLog(
          "发现",
          `deviceId=${d.deviceId} name=${d.name || "-"} RSSI=${typeof d.RSSI === "number" ? d.RSSI : "?"}`
        );
      }
      const prev = deviceMap.get(d.deviceId);
      const name = d.name || prev?.name || "";
      const RSSI = typeof d.RSSI === "number" ? d.RSSI : prev?.RSSI ?? -100;
      deviceMap.set(d.deviceId, { deviceId: d.deviceId, name, RSSI });
    }
    flushDeviceList();
  };
  notifyHandler = (res) => {
    bleLog(
      "notify回调",
      `deviceId=${res.deviceId} serviceId=${res.serviceId} characteristicId=${res.characteristicId}`
    );
    const buf = bleValueToBuffer(res.value as unknown);
    if (!buf) {
      bleLog("notify数据", "value 为空或无法解析为 ArrayBuffer");
      return;
    }
    const hex = ab2hex(buf);
    lastHex.value = hex;
    const parsed = tryParseWeightKg(buf);
    weightLine.value = parsed != null ? `解析重量：${parsed} kg` : "";
    const now = Date.now();
    if (hex !== lastNotifyLogHex || now - lastNotifyLogAt > 1500) {
      lastNotifyLogHex = hex;
      lastNotifyLogAt = now;
      bleLog("notify数据", `len=${buf.byteLength} hex=${hex} 解析=${parsed ?? "—"}`);
    }
  };
  uni.onBluetoothDeviceFound(foundHandler);
  uni.onBLECharacteristicValueChange(notifyHandler);
});

onBeforeUnmount(() => {
  if (unsubsBleLog) {
    unsubsBleLog();
    unsubsBleLog = null;
  }
  uni.offBluetoothDeviceFound();
  uni.offBLECharacteristicValueChange();
  stopScan();
  if (connectedId.value) {
    uni.closeBLEConnection({ deviceId: connectedId.value });
  }
});
</script>

<style scoped lang="scss">
@import "@/uni.scss";

.page {
  min-height: 100vh;
  background: $c-bg;
  padding: 28rpx 28rpx 48rpx;
  box-sizing: border-box;
}

.tip {
  display: block;
  font-size: 24rpx;
  color: $c-text-m;
  line-height: 1.6;
  margin-bottom: 24rpx;
  background: $c-bg-card;
  border-radius: $r-card;
  padding: 20rpx 24rpx;
  border: 1rpx solid $c-border;
  box-shadow: $shadow-card;
}

.btn {
  margin-bottom: 16rpx;
  border-radius: $r-btn;
  background: linear-gradient(160deg, #27794d 0%, $c-primary 100%);
  color: #fff;
  font-size: 28rpx;
  font-weight: 600;
  box-shadow: 0 4rpx 12rpx rgba(27, 94, 58, 0.18);
}

.btn.secondary {
  background: $c-done-bg;
  color: $c-text-h;
  box-shadow: none;
  border: 1rpx solid rgba(0, 136, 90, 0.2);
}

.btn.ghost {
  background: $c-bg-card;
  color: $c-primary;
  border: 1rpx solid $c-border-med;
  box-shadow: none;
}

.list-cap {
  font-size: 26rpx;
  font-weight: 700;
  color: $c-text-h;
  margin: 16rpx 0 12rpx;
}

.list {
  max-height: 420rpx;
  margin-bottom: 20rpx;
}

.row {
  background: $c-bg-card;
  border-radius: $r-card;
  padding: 20rpx 24rpx;
  margin-bottom: 14rpx;
  border: 1rpx solid $c-border;
  box-shadow: $shadow-card;
}

.row.active {
  border-color: $c-border-med;
  background: #f4fbf6;
}

.row-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16rpx;
}

.name {
  font-size: 28rpx;
  font-weight: 600;
  color: $c-text-h;
  flex: 1;
}

.rssi {
  font-size: 22rpx;
  color: $c-text-m;
}

.id {
  display: block;
  margin-top: 8rpx;
  font-size: 20rpx;
  color: $c-text-hint;
  word-break: break-all;
}

.panel {
  background: $c-bg-card;
  border-radius: $r-card;
  padding: 24rpx;
  margin-bottom: 16rpx;
  border: 1rpx solid $c-border;
  box-shadow: $shadow-card;
}

.weight {
  display: block;
  font-size: 36rpx;
  font-weight: 800;
  color: $c-primary;
  margin-bottom: 10rpx;
}

.hex {
  display: block;
  font-size: 22rpx;
  color: $c-text-b;
  line-height: 1.5;
  word-break: break-all;
  font-family: ui-monospace, monospace;
}

.msg {
  font-size: 24rpx;
  color: $c-text-b;
  line-height: 1.55;
  background: $c-bg-card;
  padding: 20rpx 24rpx;
  border-radius: $r-card;
  border: 1rpx solid $c-border;
  margin-bottom: 16rpx;
  box-shadow: $shadow-card;
}

.log-box {
  margin-top: 24rpx;
  background: #151b18;
  border-radius: 20rpx;
  padding: 20rpx;
  border: 1rpx solid #27312c;
}

.log-toolbar {
  margin-bottom: 12rpx;
}

.log-title {
  display: block;
  font-size: 22rpx;
  color: #8aab9c;
  margin-bottom: 12rpx;
  line-height: 1.4;
}

.log-btns {
  display: flex;
  flex-direction: row;
  gap: 16rpx;
}

.log-btn {
  font-size: 22rpx;
  background: #1e7a50;
  color: #fff;
  border-radius: 10rpx;
}

.log-btn.ghost {
  background: transparent;
  color: #8aab9c;
  border: 1rpx solid #374a3f;
}

.log-scroll {
  max-height: 480rpx;
  background: #0d1210;
  border-radius: 12rpx;
  padding: 16rpx;
}

.log-body {
  font-size: 20rpx;
  color: #a8cfbe;
  font-family: ui-monospace, monospace;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
