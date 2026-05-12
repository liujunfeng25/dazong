import { SCALE_SERIAL_NATIVE_PLUGIN_ID } from "./scaleSerial";

/**
 * USB UVC 与串口读重共用同一原生 module（dazong-serial-scale），避免双 module 云打包未注册。
 * 双头秤：两路设备枚举为 index 0、1，按需改默认索引。
 */
export const UVC_NATIVE_PLUGIN_ID = SCALE_SERIAL_NATIVE_PLUGIN_ID;

/** 默认使用的 UVC 设备序号（与 uvcListDevices 返回顺序一致） */
export const UVC_DEFAULT_DEVICE_INDEX = 0;

/** 打开摄像头（含 USB 授权）最长等待毫秒 */
export const UVC_OPEN_TIMEOUT_MS = 48000;
