package io.dazong.serialscale;

import android.app.Activity;
import android.content.Context;
import android.util.Log;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import io.dcloud.feature.uniapp.annotation.UniJSMethod;
import io.dcloud.feature.uniapp.bridge.UniJSCallback;
import io.dcloud.feature.uniapp.common.UniModule;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import android.serialport.SerialPort;

/**
 * 有线串口电子秤：默认 /dev/ttyS3 @ 9600（可通过 open / readKg 的 options 覆盖）。
 */
public class SerialScaleModule extends UniModule {

    private static final String TAG = "DazongSerialScale";
    private static SerialPort sPort;
    private static InputStream sIn;
    private static OutputStream sOut;
    /** 最近一次成功 open 的参数，供 debugStatus 展示 */
    private static String sLastPath;
    private static int sLastBaud;

    private static synchronized void closeQuiet() {
        try {
            if (sIn != null) {
                sIn.close();
            }
        } catch (Exception ignored) {
        }
        sIn = null;
        try {
            if (sOut != null) {
                sOut.close();
            }
        } catch (Exception ignored) {
        }
        sOut = null;
        try {
            if (sPort != null) {
                sPort.close();
            }
        } catch (Exception ignored) {
        }
        sPort = null;
        sLastPath = null;
        sLastBaud = 0;
    }

    private static synchronized boolean doOpen(String path, int baud) {
        closeQuiet();
        try {
            sPort = new SerialPort(new File(path), baud);
            sIn = sPort.getInputStream();
            sOut = sPort.getOutputStream();
            sLastPath = path;
            sLastBaud = baud;
            return true;
        } catch (Throwable e) {
            Log.e(TAG, "SerialPort open failed: " + path + "@" + baud, e);
            closeQuiet();
            return false;
        }
    }

    private static void writePollHex(String hex) throws IOException {
        if (hex == null || hex.trim().isEmpty()) {
            return;
        }
        if (sOut == null) {
            Log.w(TAG, "writePollHex: sOut null");
            return;
        }
        String s = hex.replaceAll("\\s+", "");
        if (s.length() < 2 || (s.length() % 2) != 0) {
            Log.w(TAG, "writePollHex: invalid hex length");
            return;
        }
        int len = s.length() / 2;
        byte[] buf = new byte[len];
        for (int i = 0; i < len; i++) {
            buf[i] = (byte) Integer.parseInt(s.substring(i * 2, i * 2 + 2), 16);
        }
        sOut.write(buf);
        sOut.flush();
        Log.i(TAG, "pollHex sent, len=" + len);
    }

    /**
     * 丢弃输入缓冲里积压的旧 ASCII 帧。秤若「连续发送」，不 drain 时 read 会先拿到几秒前的行。
     * 在发 poll（如 52=R）之前调用；有时间与字节上限，避免卡死。
     */
    private static void drainInputStale(long wallMsMax, int byteMax) throws IOException, InterruptedException {
        if (sIn == null) {
            return;
        }
        long deadline = System.currentTimeMillis() + wallMsMax;
        byte[] buf = new byte[512];
        int total = 0;
        int idleSpins = 0;
        while (System.currentTimeMillis() < deadline && total < byteMax) {
            int av = sIn.available();
            if (av > 0) {
                idleSpins = 0;
                int n = sIn.read(buf, 0, Math.min(av, buf.length));
                if (n > 0) {
                    total += n;
                } else {
                    break;
                }
            } else {
                idleSpins++;
                if (idleSpins >= 4) {
                    break;
                }
                Thread.sleep(3);
            }
        }
        if (total > 0) {
            Log.i(TAG, "drainInputStale discarded=" + total + "B");
        }
    }

    @UniJSMethod(uiThread = false)
    public void open(JSONObject options, UniJSCallback cb) {
        String path = "/dev/ttyS3";
        int baud = 9600;
        if (options != null) {
            String p = options.getString("path");
            if (p != null && !p.isEmpty()) {
                path = p;
            }
            if (options.containsKey("baudRate")) {
                baud = options.getIntValue("baudRate");
            }
        }
        JSONObject ret = new JSONObject();
        ret.put("ok", doOpen(path, baud));
        if (!ret.getBoolean("ok")) {
            ret.put("err", "open_failed");
        }
        if (cb != null) {
            cb.invoke(ret);
        }
    }

    @UniJSMethod(uiThread = false)
    public void closePort(UniJSCallback cb) {
        closeQuiet();
        JSONObject ret = new JSONObject();
        ret.put("ok", true);
        if (cb != null) {
            cb.invoke(ret);
        }
    }

    /**
     * options：path、baudRate（未 open 时隐式 open）、maxWaitMs、hardCapMs、pollHex（读前下发的十六进制）
     */
    @UniJSMethod(uiThread = false)
    public void readKg(JSONObject options, UniJSCallback cb) {
        if (cb == null) {
            return;
        }
        if (options == null) {
            options = new JSONObject();
        }
        String path = "/dev/ttyS3";
        int baud = 9600;
        String p = options.getString("path");
        if (p != null && !p.isEmpty()) {
            path = p;
        }
        if (options.containsKey("baudRate")) {
            baud = options.getIntValue("baudRate");
        }
        int maxWaitMs = options.containsKey("maxWaitMs") ? options.getIntValue("maxWaitMs") : 5000;
        if (maxWaitMs < 400) {
            maxWaitMs = 5000;
        }
        int hardCapMs = options.containsKey("hardCapMs") ? options.getIntValue("hardCapMs") : (maxWaitMs + 4000);
        if (hardCapMs < maxWaitMs + 500) {
            hardCapMs = maxWaitMs + 500;
        }
        if (hardCapMs > 20000) {
            hardCapMs = 20000;
        }
        String pollHex = options.getString("pollHex");

        JSONObject ret = new JSONObject();
        if (sIn == null) {
            if (!doOpen(path, baud)) {
                ret.put("ok", false);
                ret.put("err", "not_opened");
                cb.invoke(ret);
                return;
            }
        }
        try {
            if (pollHex != null && !pollHex.trim().isEmpty()) {
                // 先抽干旧帧，再发 R，否则读到的是缓冲里积压的旧重量
                drainInputStale(150, 32768);
                writePollHex(pollHex.trim());
                // 首衡等 MCU 在收到 R 后需一小段时间再出帧
                Thread.sleep(120);
            }
            String chunk = readChunkTimeoutAsync(maxWaitMs, hardCapMs);
            Double kg = parseToKg(chunk);
            if (kg != null) {
                ret.put("ok", true);
                ret.put("kg", kg);
            } else if (chunk == null || chunk.isEmpty()) {
                ret.put("ok", false);
                ret.put("raw", "");
                ret.put("err", "no_data");
                ret.put("hint", "等待窗口内未收到字节：查接线/串口节点/波特率；首衡「指令发送」须在 pollHex 发 52(R)；或增大 maxWaitMs");
            } else {
                ret.put("ok", false);
                ret.put("raw", chunk);
                ret.put("err", "parse_failed");
            }
        } catch (Exception e) {
            Log.e(TAG, "readKg", e);
            ret.put("ok", false);
            ret.put("err", e.getMessage() != null ? e.getMessage() : "read_error");
        }
        cb.invoke(ret);
    }

    /**
     * 在独立线程读串口，主逻辑最多等 maxWaitMs；若底层 read 阻塞，hardCapMs 后取消任务并返回空串。
     */
    private String readChunkTimeoutAsync(final int maxWaitMs, final int hardCapMs)
            throws ExecutionException, InterruptedException {
        ExecutorService ex = Executors.newSingleThreadExecutor(r -> {
            Thread t = new Thread(r, "DazongSerialRead");
            t.setDaemon(true);
            return t;
        });
        Future<String> fut = ex.submit(new Callable<String>() {
            @Override
            public String call() throws Exception {
                return readChunkTimeout(maxWaitMs);
            }
        });
        try {
            return fut.get(hardCapMs, TimeUnit.MILLISECONDS);
        } catch (TimeoutException te) {
            fut.cancel(true);
            Log.w(TAG, "read serial hard timeout " + hardCapMs + "ms");
            return "";
        } finally {
            ex.shutdownNow();
        }
    }

    private String readChunkTimeout(int maxWaitMs) throws IOException, InterruptedException {
        long end = System.currentTimeMillis() + maxWaitMs;
        StringBuilder sb = new StringBuilder();
        byte[] buf = new byte[256];
        while (System.currentTimeMillis() < end) {
            int av = sIn.available();
            if (av > 0) {
                int n = sIn.read(buf, 0, Math.min(av, buf.length));
                if (n > 0) {
                    sb.append(new String(buf, 0, n, StandardCharsets.UTF_8));
                    String s = sb.toString();
                    if (s.contains("\n") || s.contains("\r")) {
                        break;
                    }
                }
            } else {
                if (sb.length() > 0) {
                    break;
                }
                Thread.sleep(20);
            }
        }
        return sb.toString().trim();
    }

    private Double parseToKg(String text) {
        if (text == null || text.isEmpty()) {
            return null;
        }
        // 首衡串行协议：sn/sw/gn/gw + 7 位重量 ASCII + kg，例 sn0001.23kg
        Matcher sh = Pattern.compile("(?i)(sn|sw|gn|gw)([\\-+0-9\\.]+)\\s*kg").matcher(text);
        if (sh.find()) {
            return Double.parseDouble(sh.group(2));
        }
        Matcher jin = Pattern.compile("([-+]?\\d+\\.?\\d*)\\s*斤").matcher(text);
        if (jin.find()) {
            return Double.parseDouble(jin.group(1)) * 0.5;
        }
        Matcher kg = Pattern.compile("([-+]?\\d+\\.?\\d*)\\s*kg", Pattern.CASE_INSENSITIVE).matcher(text);
        if (kg.find()) {
            return Double.parseDouble(kg.group(1));
        }
        Matcher num = Pattern.compile("([-+]?\\d+\\.?\\d*)").matcher(text);
        if (num.find()) {
            return Double.parseDouble(num.group(1));
        }
        return null;
    }

    @UniJSMethod(uiThread = false)
    public void debugStatus(JSONObject options, UniJSCallback cb) {
        if (cb == null) {
            return;
        }
        JSONObject ret = new JSONObject();
        boolean opened = sIn != null && sPort != null;
        ret.put("opened", opened);
        ret.put("lastPath", sLastPath != null ? sLastPath : "");
        ret.put("lastBaud", sLastBaud);
        int avail = 0;
        try {
            if (sIn != null) {
                avail = sIn.available();
            }
        } catch (IOException e) {
            Log.w(TAG, "debugStatus available", e);
        }
        ret.put("inAvailable", avail);
        Log.i(TAG, "debugStatus opened=" + opened + " path=" + sLastPath + " baud=" + sLastBaud + " avail=" + avail);
        cb.invoke(ret);
    }

    /**
     * options.hex：空格分隔十六进制，写入串口（须已 open）。
     */
    @UniJSMethod(uiThread = false)
    public void debugWriteHex(JSONObject options, UniJSCallback cb) {
        if (cb == null) {
            return;
        }
        JSONObject ret = new JSONObject();
        if (options == null) {
            ret.put("ok", false);
            ret.put("err", "no_options");
            cb.invoke(ret);
            return;
        }
        if (sOut == null) {
            ret.put("ok", false);
            ret.put("err", "not_opened");
            cb.invoke(ret);
            return;
        }
        String hex = options.getString("hex");
        if (hex == null || hex.trim().isEmpty()) {
            ret.put("ok", false);
            ret.put("err", "empty_hex");
            cb.invoke(ret);
            return;
        }
        String s = hex.replaceAll("\\s+", "");
        if (s.length() < 2 || (s.length() % 2) != 0) {
            ret.put("ok", false);
            ret.put("err", "invalid_hex_length");
            cb.invoke(ret);
            return;
        }
        try {
            int len = s.length() / 2;
            byte[] buf = new byte[len];
            for (int i = 0; i < len; i++) {
                buf[i] = (byte) Integer.parseInt(s.substring(i * 2, i * 2 + 2), 16);
            }
            sOut.write(buf);
            sOut.flush();
            String sentHex = bytesToHexSpaced(buf);
            ret.put("ok", true);
            ret.put("sentLen", len);
            ret.put("sentHex", sentHex);
            Log.i(TAG, "debugWriteHex ok len=" + len + " hex=" + sentHex);
        } catch (Exception e) {
            Log.e(TAG, "debugWriteHex", e);
            ret.put("ok", false);
            ret.put("err", e.getMessage() != null ? e.getMessage() : "write_error");
        }
        cb.invoke(ret);
    }

    /**
     * options：maxWaitMs（默认 3000）、maxBytes（默认 512）、untilCrlf（遇 \\r\\n 提前结束，默认 false）
     */
    @UniJSMethod(uiThread = false)
    public void debugReadRaw(JSONObject options, UniJSCallback cb) {
        if (cb == null) {
            return;
        }
        JSONObject ret = new JSONObject();
        if (sIn == null) {
            ret.put("ok", false);
            ret.put("err", "not_opened");
            cb.invoke(ret);
            return;
        }
        if (options == null) {
            options = new JSONObject();
        }
        int maxWaitMs = options.containsKey("maxWaitMs") ? options.getIntValue("maxWaitMs") : 3000;
        if (maxWaitMs < 100) {
            maxWaitMs = 100;
        }
        if (maxWaitMs > 30000) {
            maxWaitMs = 30000;
        }
        int maxBytes = options.containsKey("maxBytes") ? options.getIntValue("maxBytes") : 512;
        if (maxBytes < 1) {
            maxBytes = 1;
        }
        if (maxBytes > 4096) {
            maxBytes = 4096;
        }
        boolean untilCrlf = options.getBooleanValue("untilCrlf");
        int hardCapMs = Math.min(35000, maxWaitMs + 3000);
        final int fw = maxWaitMs;
        final int fb = maxBytes;
        final boolean uc = untilCrlf;

        ExecutorService ex = Executors.newSingleThreadExecutor(r -> {
            Thread t = new Thread(r, "DazongSerialDebugRead");
            t.setDaemon(true);
            return t;
        });
        Future<JSONObject> fut = ex.submit(new Callable<JSONObject>() {
            @Override
            public JSONObject call() throws Exception {
                return debugReadRawImpl(fw, fb, uc);
            }
        });
        try {
            JSONObject inner = fut.get(hardCapMs, TimeUnit.MILLISECONDS);
            for (String key : inner.keySet()) {
                ret.put(key, inner.get(key));
            }
            ret.put("ok", true);
            Log.i(TAG, "debugReadRaw byteLen=" + inner.getIntValue("byteLen"));
        } catch (TimeoutException te) {
            fut.cancel(true);
            Log.w(TAG, "debugReadRaw hard timeout " + hardCapMs + "ms");
            ret.put("ok", false);
            ret.put("err", "read_hard_timeout");
        } catch (Exception e) {
            Log.e(TAG, "debugReadRaw", e);
            ret.put("ok", false);
            ret.put("err", e.getMessage() != null ? e.getMessage() : "read_error");
        } finally {
            ex.shutdownNow();
        }
        cb.invoke(ret);
    }

    private static JSONObject debugReadRawImpl(int maxWaitMs, int maxBytes, boolean untilCrlf)
            throws IOException, InterruptedException {
        JSONArray ticks = new JSONArray();
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        long start = System.currentTimeMillis();
        long end = start + maxWaitMs;
        long nextTick = start;
        byte[] buf = new byte[256];
        while (System.currentTimeMillis() < end && baos.size() < maxBytes) {
            long now = System.currentTimeMillis();
            if (now >= nextTick) {
                JSONObject t = new JSONObject();
                t.put("tRelMs", now - start);
                t.put("avail", sIn.available());
                t.put("totalRead", baos.size());
                ticks.add(t);
                nextTick += 100;
            }
            int av = sIn.available();
            if (av > 0) {
                int toRead = Math.min(av, Math.min(buf.length, maxBytes - baos.size()));
                if (toRead > 0) {
                    int n = sIn.read(buf, 0, toRead);
                    if (n > 0) {
                        baos.write(buf, 0, n);
                        if (untilCrlf && containsCrLf(baos.toByteArray())) {
                            break;
                        }
                    }
                }
            } else {
                Thread.sleep(15);
            }
        }
        byte[] all = baos.toByteArray();
        JSONObject out = new JSONObject();
        out.put("byteLen", all.length);
        out.put("hex", bytesToHexSpaced(all));
        out.put("asciiEscaped", bytesToAsciiEscaped(all));
        out.put("ticks", ticks);
        out.put("maxWaitMs", maxWaitMs);
        out.put("untilCrlf", untilCrlf);
        return out;
    }

    private static boolean containsCrLf(byte[] data) {
        for (byte b : data) {
            if (b == 0x0d || b == 0x0a) {
                return true;
            }
        }
        return false;
    }

    private static String bytesToHexSpaced(byte[] b) {
        if (b == null || b.length == 0) {
            return "";
        }
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < b.length; i++) {
            if (i > 0) {
                sb.append(' ');
            }
            sb.append(String.format("%02X", b[i] & 0xff));
        }
        return sb.toString();
    }

    private static String bytesToAsciiEscaped(byte[] b) {
        if (b == null || b.length == 0) {
            return "";
        }
        StringBuilder sb = new StringBuilder();
        for (byte value : b) {
            int c = value & 0xff;
            if (c >= 0x20 && c < 0x7f && c != '\\' && c != '"') {
                sb.append((char) c);
            } else {
                sb.append(String.format("\\x%02X", c));
            }
        }
        return sb.toString();
    }

    /** 供 {@link UvcCameraRuntime} 使用（同包可见）。 */
    Activity uvcRequireActivity() {
        Context c = mUniSDKInstance.getContext();
        if (c instanceof Activity) {
            return (Activity) c;
        }
        throw new IllegalStateException("context_not_activity");
    }

    /** 供 {@link UvcCameraRuntime} 使用（同包可见）。 */
    Context uvcAppContext() {
        return mUniSDKInstance.getContext();
    }

    @UniJSMethod(uiThread = false)
    public void uvcGetLog(JSONObject options, UniJSCallback cb) {
        UvcCameraRuntime.uvcGetLog(options, cb);
    }

    @UniJSMethod(uiThread = false)
    public void uvcClearLog(JSONObject options, UniJSCallback cb) {
        UvcCameraRuntime.uvcClearLog(options, cb);
    }

    @UniJSMethod(uiThread = false)
    public void uvcListDevices(JSONObject options, UniJSCallback cb) {
        UvcCameraRuntime.uvcListDevices(this, options, cb);
    }

    @UniJSMethod(uiThread = false)
    public void uvcOpen(JSONObject options, UniJSCallback cb) {
        UvcCameraRuntime.uvcOpen(this, options, cb);
    }

    @UniJSMethod(uiThread = false)
    public void uvcClose(JSONObject options, UniJSCallback cb) {
        UvcCameraRuntime.uvcClose(options, cb);
    }

    @UniJSMethod(uiThread = false)
    public void uvcCapture(JSONObject options, UniJSCallback cb) {
        UvcCameraRuntime.uvcCapture(this, options, cb);
    }

    @UniJSMethod(uiThread = false)
    public void uvcProbeImage(JSONObject options, UniJSCallback cb) {
        UvcCameraRuntime.uvcProbeImage(options, cb);
    }

    @UniJSMethod(uiThread = false)
    public void uvcPreviewStatus(JSONObject options, UniJSCallback cb) {
        UvcCameraRuntime.uvcPreviewStatus(this, options, cb);
    }
}
