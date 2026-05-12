/**
 * 有线串口秤（如 rk3568 平板 /dev/ttyS3 @ 9600）
 *
 * 首衡 SH2100 等《串行通讯协议》：ASCII 帧如 `sn0001.23kg\\r\\n`；秤若设为「指令发送」，
 * 上位机须先发 **R（0x52）** 才回一帧（见资料包「首衡协议详细协议」第三节）。
 * 连续发送模式可不先发 R；默认仍发 52 一般兼容，若异常可把 SCALE_SERIAL_POLL_HEX 改为 ""。
 *
 * UniApp 业务层无法直接 open 串口并设波特率，需二选一：
 * 1) 本机跑「串口→HTTP」小服务（同事现成 App 若可改成只暴露 127.0.0.1 接口也可），把 SCALE_SERIAL_HTTP_URL 指过去；
 * 2) 云打包集成 DCloud 原生插件（Java 打开 SerialPort），再在 scaleSerialRead 里 requireNativePlugin。
 */
export const SCALE_SERIAL_DEVICE_PATH = "/dev/ttyS3";
export const SCALE_SERIAL_BAUD = 9600;

/** 原生 open / readKg 若永不回调，避免「读秤中…」永久转圈 */
export const SCALE_SERIAL_OPEN_TIMEOUT_MS = 10000;
/** JS 等原生 readKg 回调的最长时间，应大于下方 NATIVE_READ_HARD_CAP_MS + 余量 */
export const SCALE_SERIAL_READ_TIMEOUT_MS = 22000;

/**
 * 原生在串口上等待出现数据的最长时间（毫秒）。过短会出现 raw 空、err=no_data。
 * 许多秤连续发帧间隔 200ms～1s，建议 ≥4000。
 */
export const SCALE_SERIAL_NATIVE_READ_WAIT_MS = 6000;

/** 原生读线程硬上限（防驱动阻塞卡死），须 ≥ NATIVE_READ_WAIT_MS + 余量 */
export const SCALE_SERIAL_NATIVE_READ_HARD_CAP_MS = 12000;

/**
 * 读秤前下发的十六进制（可含空格）。首衡「指令发送」：发 **52** = 字母 R 索要重量；
 * 「去皮」54、「置零」5A（勿与读数混用）。非首衡或纯连续发帧可改为 ""。
 * 原生在发 poll 前会先 **短暂清空串口读缓冲**，避免连续发帧时读到几秒前的旧行。
 */
export const SCALE_SERIAL_POLL_HEX = "52";

/** 非空则称重页「读秤」走 HTTP GET；示例 http://127.0.0.1:9133/weight */
export const SCALE_SERIAL_HTTP_URL = "";

/**
 * 已按仓库 nativeplugins/dazong-serial-scale 编译 aar 并勾选本地插件后，填：
 * "dazong-serial-scale"
 * 留空则不走原生串口（可用 SCALE_SERIAL_HTTP_URL 或仅演示读数）。
 */
export const SCALE_SERIAL_NATIVE_PLUGIN_ID = "dazong-serial-scale";
