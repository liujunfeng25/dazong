package io.dazong.serialscale;

import android.app.Activity;
import android.content.Context;
import android.graphics.BitmapFactory;
import android.hardware.usb.UsbConstants;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbManager;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.os.Build;
import android.util.Log;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.Surface;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;

import androidx.annotation.NonNull;

import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.herohan.uvcapp.CameraHelper;
import com.herohan.uvcapp.ICameraHelper;
import com.herohan.uvcapp.IImageCapture;
import com.herohan.uvcapp.IImageCapture.OutputFileResults;
import com.serenegiant.widget.CameraViewInterface;
import com.serenegiant.widget.UVCCameraTextureView;

import java.io.File;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

import io.dcloud.feature.uniapp.bridge.UniJSCallback;

/**
 * USB UVC 摄像头逻辑（由 {@link SerialScaleModule} 暴露同名 JS 方法，避免双 module 注册问题）。
 */
final class UvcCameraRuntime {

    private static final String TAG = "DazongUvcCamera";
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final int LOG_MAX = 8000;
    private static final StringBuilder LOG_BUF = new StringBuilder();
    private static final Object LOCK = new Object();

    private static CameraHelper sHelper;
    private static UVCCameraTextureView sTextureView;
    private static Surface sPreviewSurface;
    private static volatile Activity sHostActivity;
    private static UsbDevice sOpenedDevice;
    private static UniJSCallback sPendingOpenCb;
    private static UniJSCallback sPendingCaptureCb;
    private static int sAttachRetryCount = 0;
    /** {@link #tryAttachPreviewAndStart()} 内 startPreview 成功后置 true，关闭/detach 时置 false */
    private static volatile boolean sPreviewRunning = false;

    private UvcCameraRuntime() {
    }

    private static int dp(Activity act, int dpVal) {
        return (int) TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP, dpVal, act.getResources().getDisplayMetrics());
    }

    private static final class PreviewOpts {
        boolean visible;
        int heightDp;
        int gravity;

        static PreviewOpts parse(JSONObject options) {
            PreviewOpts o = new PreviewOpts();
            o.visible = options != null && options.getBooleanValue("previewVisible");
            int h = 180;
            if (options != null && options.containsKey("previewHeightDp")) {
                h = options.getIntValue("previewHeightDp");
            }
            if (h < 80) {
                h = 80;
            }
            if (h > 480) {
                h = 480;
            }
            o.heightDp = h;
            String g = options != null ? options.getString("previewGravity") : null;
            if (g != null && "top".equalsIgnoreCase(g.trim())) {
                o.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL;
            } else {
                o.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
            }
            return o;
        }
    }

    private static void applyTextureLayout(Activity act, PreviewOpts opts) {
        if (sTextureView == null || act == null) {
            return;
        }
        FrameLayout.LayoutParams lp;
        if (opts.visible) {
            lp = new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(act, opts.heightDp));
            lp.gravity = opts.gravity;
            sTextureView.setVisibility(View.VISIBLE);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                sTextureView.setElevation(dp(act, 12));
            }
            try {
                sTextureView.bringToFront();
                ViewGroup parent = (ViewGroup) sTextureView.getParent();
                if (parent != null) {
                    parent.requestLayout();
                }
            } catch (Exception ignored) {
            }
            logLine("uvc preview layout visible=true heightDp=" + opts.heightDp + " gravity=" + opts.gravity);
        } else {
            lp = new FrameLayout.LayoutParams(2, 2);
            lp.gravity = Gravity.TOP | Gravity.START;
            sTextureView.setVisibility(View.INVISIBLE);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                sTextureView.setElevation(0f);
            }
            logLine("uvc preview layout visible=false (minimal surface)");
        }
        sTextureView.setLayoutParams(lp);
    }

    /**
     * 与公司 SmartReceiv {@code CameraSDK.isUvcDevice} 一致：设备类或接口类为 USB_CLASS_VIDEO(14)。
     */
    private static boolean isUvcVideoClass(UsbDevice d) {
        if (d == null) {
            return false;
        }
        if (d.getDeviceClass() == UsbConstants.USB_CLASS_VIDEO) {
            return true;
        }
        for (int i = 0; i < d.getInterfaceCount(); i++) {
            if (d.getInterface(i).getInterfaceClass() == UsbConstants.USB_CLASS_VIDEO) {
                return true;
            }
        }
        return false;
    }

    /** 与 {@code UsbManager.deviceList} 过滤视频设备一致（公司收货端枚举方式）。 */
    private static List<UsbDevice> listUvcFromUsbManager(Context ctx) {
        if (ctx == null) {
            return Collections.emptyList();
        }
        UsbManager um = (UsbManager) ctx.getSystemService(Context.USB_SERVICE);
        if (um == null) {
            return Collections.emptyList();
        }
        List<UsbDevice> out = new ArrayList<>();
        for (UsbDevice d : um.getDeviceList().values()) {
            if (isUvcVideoClass(d)) {
                out.add(d);
            }
        }
        Collections.sort(out, (a, b) -> Integer.compare(a.getDeviceId(), b.getDeviceId()));
        return out;
    }

    /**
     * 优先 UsbManager 视频类设备；若为空再回退 herohan {@link CameraHelper#getDeviceList()}，兼容旧行为。
     */
    private static List<UsbDevice> resolveUvcDeviceList(Context ctx) {
        List<UsbDevice> usb = listUvcFromUsbManager(ctx);
        if (!usb.isEmpty()) {
            logLine("resolveUvcDeviceList UsbManager count=" + usb.size());
            return usb;
        }
        List<UsbDevice> h = helper().getDeviceList();
        if (h == null || h.isEmpty()) {
            logLine("resolveUvcDeviceList herohan empty");
            return Collections.emptyList();
        }
        logLine("resolveUvcDeviceList herohan count=" + h.size());
        return h;
    }

    static void logLine(String line) {
        Log.i(TAG, line);
        synchronized (LOG_BUF) {
            if (LOG_BUF.length() > 0) {
                LOG_BUF.append('\n');
            }
            LOG_BUF.append(System.currentTimeMillis()).append(' ').append(line);
            if (LOG_BUF.length() > LOG_MAX) {
                LOG_BUF.delete(0, LOG_BUF.length() - LOG_MAX + 1);
            }
        }
    }

    private static void rememberHost(SerialScaleModule host) {
        try {
            Activity a = host.uvcRequireActivity();
            sHostActivity = a;
        } catch (Exception e) {
            logLine("rememberHost skip: " + e.getMessage());
        }
    }

    private static CameraHelper helper() {
        synchronized (LOCK) {
            if (sHelper == null) {
                sHelper = new CameraHelper();
                sHelper.setStateCallback(STATE_CB);
            }
            return sHelper;
        }
    }

    private static final ICameraHelper.StateCallback STATE_CB = new ICameraHelper.StateCallback() {
        @Override
        public void onAttach(UsbDevice device) {
            logLine("uvc onAttach vid=" + device.getVendorId() + " pid=" + device.getProductId());
        }

        @Override
        public void onDeviceOpen(UsbDevice device, boolean isFirstOpen) {
            logLine("uvc onDeviceOpen firstOpen=" + isFirstOpen);
            try {
                helper().openCamera();
            } catch (Throwable e) {
                logLine("uvc openCamera ex: " + e.getMessage());
                failOpen("open_camera_failed", e.getMessage());
            }
        }

        @Override
        public void onCameraOpen(UsbDevice device) {
            logLine("uvc onCameraOpen");
            MAIN.post(() -> {
                synchronized (LOCK) {
                    sOpenedDevice = device;
                    tryAttachPreviewAndStart();
                }
                invokeOpenOk();
            });
        }

        @Override
        public void onCameraClose(UsbDevice device) {
            logLine("uvc onCameraClose");
            MAIN.post(
                    () -> {
                        synchronized (LOCK) {
                            detachSurfaceLocked();
                            sOpenedDevice = null;
                        }
                    });
        }

        @Override
        public void onDeviceClose(UsbDevice device) {
            logLine("uvc onDeviceClose");
        }

        @Override
        public void onDetach(UsbDevice device) {
            logLine("uvc onDetach");
            MAIN.post(
                    () -> {
                        synchronized (LOCK) {
                            sPreviewRunning = false;
                            detachSurfaceLocked();
                            try {
                                helper().stopPreview();
                            } catch (Exception ignored) {
                            }
                            try {
                                helper().closeCamera();
                            } catch (Exception ignored) {
                            }
                            sOpenedDevice = null;
                        }
                    });
        }

        @Override
        public void onCancel(UsbDevice device) {
            logLine("uvc onCancel");
            failOpen("usb_cancel", "user_denied_usb_or_cancel");
        }
    };

    private static void tryAttachPreviewAndStart() {
        if (sHelper == null) {
            return;
        }
        if (sPreviewSurface != null) {
            sAttachRetryCount = 0;
            try {
                sHelper.removeSurface(sPreviewSurface);
            } catch (Exception ignored) {
            }
            try {
                sHelper.addSurface(sPreviewSurface, false);
                sHelper.startPreview();
                sPreviewRunning = true;
                logLine("uvc preview started (surface ready)");
            } catch (Exception e) {
                sPreviewRunning = false;
                logLine("uvc addSurface/startPreview: " + e.getMessage());
            }
        } else {
            if (sAttachRetryCount >= 45) {
                logLine("uvc surface wait timeout, give up attach");
                return;
            }
            sAttachRetryCount++;
            logLine("uvc surface not ready, retry " + sAttachRetryCount);
            MAIN.postDelayed(
                    () -> {
                        synchronized (LOCK) {
                            tryAttachPreviewAndStart();
                        }
                    },
                    120);
        }
    }

    private static void detachSurfaceLocked() {
        if (sHelper == null || sPreviewSurface == null) {
            return;
        }
        sPreviewRunning = false;
        try {
            sHelper.removeSurface(sPreviewSurface);
        } catch (Exception ignored) {
        }
    }

    private static void invokeOpenOk() {
        UniJSCallback cb;
        synchronized (LOCK) {
            cb = sPendingOpenCb;
            sPendingOpenCb = null;
        }
        if (cb != null) {
            JSONObject ret = new JSONObject();
            ret.put("ok", true);
            synchronized (LOCK) {
                ret.put("previewStarted", sPreviewRunning);
            }
            cb.invoke(ret);
        }
    }

    private static void failOpen(String err, String hint) {
        UniJSCallback cb;
        synchronized (LOCK) {
            cb = sPendingOpenCb;
            sPendingOpenCb = null;
        }
        if (cb != null) {
            JSONObject ret = new JSONObject();
            ret.put("ok", false);
            ret.put("err", err);
            ret.put("hint", hint != null ? hint : "");
            cb.invoke(ret);
        }
    }

    private static final CameraViewInterface.Callback SURFACE_CB =
            new CameraViewInterface.Callback() {
                @Override
                public void onSurfaceCreated(CameraViewInterface view, Surface surface) {
                    logLine("uvc surfaceCreated");
                    synchronized (LOCK) {
                        sPreviewSurface = surface;
                        if (sOpenedDevice != null) {
                            tryAttachPreviewAndStart();
                        }
                    }
                }

                @Override
                public void onSurfaceChanged(CameraViewInterface view, Surface surface, int width, int height) {
                }

                @Override
                public void onSurfaceDestroy(CameraViewInterface view, Surface surface) {
                    logLine("uvc surfaceDestroy");
                    synchronized (LOCK) {
                        sPreviewRunning = false;
                        detachSurfaceLocked();
                        if (Objects.equals(surface, sPreviewSurface)) {
                            sPreviewSurface = null;
                        }
                    }
                }
            };

    static void uvcGetLog(JSONObject options, UniJSCallback cb) {
        if (cb == null) {
            return;
        }
        String s;
        synchronized (LOG_BUF) {
            s = LOG_BUF.toString();
        }
        JSONObject ret = new JSONObject();
        ret.put("ok", true);
        ret.put("text", s);
        cb.invoke(ret);
    }

    static void uvcClearLog(JSONObject options, UniJSCallback cb) {
        synchronized (LOG_BUF) {
            LOG_BUF.setLength(0);
        }
        logLine("uvc log cleared");
        if (cb != null) {
            JSONObject o = new JSONObject();
            o.put("ok", true);
            cb.invoke(o);
        }
    }

    static void uvcListDevices(SerialScaleModule host, JSONObject options, UniJSCallback cb) {
        if (cb == null) {
            return;
        }
        rememberHost(host);
        JSONObject ret = new JSONObject();
        try {
            List<UsbDevice> list = resolveUvcDeviceList(host.uvcAppContext());
            JSONArray arr = new JSONArray();
            for (int i = 0; i < list.size(); i++) {
                UsbDevice d = list.get(i);
                JSONObject o = new JSONObject();
                o.put("index", i);
                o.put("deviceId", d.getDeviceId());
                o.put("vendorId", d.getVendorId());
                o.put("productId", d.getProductId());
                String name = d.getProductName();
                if (name == null || name.isEmpty()) {
                    name = String.format(Locale.US, "USB_%d", d.getDeviceId());
                }
                o.put("label", name);
                arr.add(o);
            }
            ret.put("ok", true);
            ret.put("devices", arr);
            logLine("uvcListDevices count=" + list.size());
        } catch (Throwable t) {
            logLine("uvcListDevices err " + t.getMessage());
            ret.put("ok", false);
            ret.put("err", t.getMessage() != null ? t.getMessage() : "list_error");
        }
        cb.invoke(ret);
    }

    private static void ensureTextureOnUiThread(SerialScaleModule host, PreviewOpts previewOpts) {
        Activity act = sHostActivity != null ? sHostActivity : host.uvcRequireActivity();
        FrameLayout root = act.findViewById(android.R.id.content);
        if (root == null) {
            logLine("uvc ensureTexture: no content");
            return;
        }
        synchronized (LOCK) {
            if (sTextureView != null && sTextureView.getParent() == root) {
                applyTextureLayout(act, previewOpts);
                return;
            }
            if (sTextureView != null) {
                try {
                    ViewGroup p = (ViewGroup) sTextureView.getParent();
                    if (p != null) {
                        p.removeView(sTextureView);
                    }
                } catch (Exception ignored) {
                }
            }
            sTextureView = new UVCCameraTextureView(act);
            sTextureView.setCallback(SURFACE_CB);
            root.addView(sTextureView);
            applyTextureLayout(act, previewOpts);
            logLine("uvc texture attached to content");
        }
    }

    static void uvcOpen(SerialScaleModule host, JSONObject options, UniJSCallback cb) {
        if (cb == null) {
            return;
        }
        final PreviewOpts previewOpts = PreviewOpts.parse(options);
        int deviceIndex = 0;
        if (options != null && options.containsKey("deviceIndex")) {
            deviceIndex = options.getIntValue("deviceIndex");
        }
        final int idx = deviceIndex;
        final int deviceIdOpt =
                options != null && options.containsKey("deviceId") ? options.getIntValue("deviceId") : -1;
        rememberHost(host);
        MAIN.post(
                () -> {
                    try {
                        ensureTextureOnUiThread(host, previewOpts);
                    } catch (Exception e) {
                        logLine("uvcOpen ensureTexture ex: " + e.getMessage());
                        JSONObject ret = new JSONObject();
                        ret.put("ok", false);
                        ret.put("err", "ensure_texture_failed");
                        ret.put("hint", e.getMessage());
                        cb.invoke(ret);
                        return;
                    }
                    synchronized (LOCK) {
                        if (sPendingOpenCb != null || sPendingCaptureCb != null) {
                            JSONObject ret = new JSONObject();
                            ret.put("ok", false);
                            ret.put("err", "busy_pending_operation");
                            cb.invoke(ret);
                            return;
                        }
                        List<UsbDevice> list = resolveUvcDeviceList(host.uvcAppContext());
                        if (list.isEmpty()) {
                            JSONObject ret = new JSONObject();
                            ret.put("ok", false);
                            ret.put("err", "no_usb_camera");
                            ret.put("hint", "未检测到 UVC（UsbManager 视频类 + herohan 均为空）；检查 USB/OTG");
                            cb.invoke(ret);
                            logLine("uvcOpen no devices");
                            return;
                        }
                        UsbDevice dev = null;
                        if (deviceIdOpt >= 0) {
                            for (UsbDevice d : list) {
                                if (d.getDeviceId() == deviceIdOpt) {
                                    dev = d;
                                    break;
                                }
                            }
                            if (dev == null) {
                                JSONObject ret = new JSONObject();
                                ret.put("ok", false);
                                ret.put("err", "bad_device_id");
                                ret.put("hint", "deviceId=" + deviceIdOpt + " 不在列表中，请先 uvcListDevices");
                                cb.invoke(ret);
                                return;
                            }
                        } else {
                            if (idx < 0 || idx >= list.size()) {
                                JSONObject ret = new JSONObject();
                                ret.put("ok", false);
                                ret.put("err", "bad_device_index");
                                ret.put("hint", "0.." + (list.size() - 1));
                                cb.invoke(ret);
                                return;
                            }
                            dev = list.get(idx);
                        }
                        if (sOpenedDevice != null && sOpenedDevice.equals(dev)) {
                            Activity act = sHostActivity != null ? sHostActivity : host.uvcRequireActivity();
                            applyTextureLayout(act, previewOpts);
                            JSONObject ret = new JSONObject();
                            ret.put("ok", true);
                            ret.put("already", true);
                            ret.put("previewStarted", sPreviewRunning);
                            cb.invoke(ret);
                            logLine("uvcOpen already same device previewStarted=" + sPreviewRunning);
                            return;
                        }
                        if (sOpenedDevice != null) {
                            try {
                                helper().stopPreview();
                            } catch (Exception ignored) {
                            }
                            try {
                                helper().closeCamera();
                            } catch (Exception ignored) {
                            }
                            sOpenedDevice = null;
                        }
                        sPendingOpenCb = cb;
                        logLine(
                                "uvcOpen selectDevice id="
                                        + dev.getDeviceId()
                                        + " index="
                                        + (deviceIdOpt >= 0 ? "by_deviceId" : String.valueOf(idx))
                                        + " vid="
                                        + dev.getVendorId()
                                        + " pid="
                                        + dev.getProductId());
                        helper().selectDevice(dev);
                    }
                });
    }

    static void uvcClose(JSONObject options, UniJSCallback cb) {
        MAIN.post(
                () -> {
                    JSONObject ret = new JSONObject();
                    try {
                        synchronized (LOCK) {
                            sPendingOpenCb = null;
                            sPendingCaptureCb = null;
                            detachSurfaceLocked();
                            try {
                                helper().stopPreview();
                            } catch (Exception ignored) {
                            }
                            try {
                                helper().closeCamera();
                            } catch (Exception ignored) {
                            }
                            sOpenedDevice = null;
                            if (sTextureView != null) {
                                try {
                                    ViewGroup p = (ViewGroup) sTextureView.getParent();
                                    if (p != null) {
                                        p.removeView(sTextureView);
                                    }
                                } catch (Exception ignored) {
                                }
                                sTextureView = null;
                            }
                            sPreviewSurface = null;
                            sAttachRetryCount = 0;
                            sPreviewRunning = false;
                        }
                        ret.put("ok", true);
                        logLine("uvcClose done");
                    } catch (Throwable t) {
                        ret.put("ok", false);
                        ret.put("err", t.getMessage());
                    }
                    if (cb != null) {
                        cb.invoke(ret);
                    }
                });
    }

    static void uvcCapture(SerialScaleModule host, JSONObject options, UniJSCallback cb) {
        if (cb == null) {
            return;
        }
        MAIN.post(
                () -> {
                    JSONObject ret = new JSONObject();
                    synchronized (LOCK) {
                        if (sPendingCaptureCb != null) {
                            ret.put("ok", false);
                            ret.put("err", "capture_busy");
                            cb.invoke(ret);
                            return;
                        }
                        if (sOpenedDevice == null) {
                            ret.put("ok", false);
                            ret.put("err", "camera_not_opened");
                            cb.invoke(ret);
                            return;
                        }
                        File out = createOutputFile(host);
                        if (out == null) {
                            ret.put("ok", false);
                            ret.put("err", "cannot_create_file");
                            cb.invoke(ret);
                            return;
                        }
                        sPendingCaptureCb = cb;
                        IImageCapture.OutputFileOptions opts =
                                new IImageCapture.OutputFileOptions.Builder(out).build();
                        logLine("uvcCapture -> " + out.getAbsolutePath());
                        helper()
                                .takePicture(
                                        opts,
                                        new IImageCapture.OnImageCaptureCallback() {
                                            @Override
                                            public void onImageSaved(@NonNull OutputFileResults outputFileResults) {
                                                MAIN.post(() -> finishCaptureOk(out));
                                            }

                                            @Override
                                            public void onError(
                                                    int error,
                                                    @NonNull String message,
                                                    @NonNull Throwable cause) {
                                                MAIN.post(
                                                        () ->
                                                                finishCaptureFail(
                                                                        message
                                                                                + " / "
                                                                                + cause.getClass()
                                                                                        .getSimpleName()));
                                            }
                                        });
                    }
                });
    }

    private static File createOutputFile(SerialScaleModule host) {
        try {
            Context ctx = host.uvcAppContext();
            File base = ctx.getExternalFilesDir(Environment.DIRECTORY_PICTURES);
            if (base == null) {
                base = ctx.getFilesDir();
            }
            File dir = new File(base, "dazong_uvc");
            if (!dir.exists() && !dir.mkdirs()) {
                return null;
            }
            String ts = new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(new Date());
            return new File(dir, "lock_" + ts + ".jpg");
        } catch (Exception e) {
            logLine("createOutputFile ex " + e.getMessage());
            return null;
        }
    }

    private static void finishCaptureOk(File out) {
        UniJSCallback cb;
        synchronized (LOCK) {
            cb = sPendingCaptureCb;
            sPendingCaptureCb = null;
        }
        if (cb == null) {
            return;
        }
        JSONObject ret = new JSONObject();
        String path = out.getAbsolutePath();
        ret.put("ok", true);
        ret.put("path", path);
        ret.put("uri", "file://" + path);
        logLine("uvcCapture ok len=" + out.length());
        cb.invoke(ret);
    }

    private static void finishCaptureFail(String msg) {
        UniJSCallback cb;
        synchronized (LOCK) {
            cb = sPendingCaptureCb;
            sPendingCaptureCb = null;
        }
        if (cb == null) {
            return;
        }
        JSONObject ret = new JSONObject();
        ret.put("ok", false);
        ret.put("err", "capture_failed");
        ret.put("hint", msg);
        logLine("uvcCapture fail " + msg);
        cb.invoke(ret);
    }

    static void uvcProbeImage(JSONObject options, UniJSCallback cb) {
        if (cb == null || options == null) {
            return;
        }
        String path = options.getString("path");
        JSONObject ret = new JSONObject();
        if (path == null || path.isEmpty()) {
            ret.put("ok", false);
            ret.put("err", "no_path");
            cb.invoke(ret);
            return;
        }
        String p = path.replace("file://", "");
        try {
            BitmapFactory.Options opt = new BitmapFactory.Options();
            opt.inJustDecodeBounds = true;
            BitmapFactory.decodeFile(p, opt);
            ret.put("ok", true);
            ret.put("w", opt.outWidth);
            ret.put("h", opt.outHeight);
            logLine("uvcProbeImage " + p + " " + opt.outWidth + "x" + opt.outHeight);
        } catch (Throwable t) {
            ret.put("ok", false);
            ret.put("err", t.getMessage());
        }
        cb.invoke(ret);
    }

    static void uvcPreviewStatus(SerialScaleModule host, JSONObject options, UniJSCallback cb) {
        if (cb == null) {
            return;
        }
        rememberHost(host);
        JSONObject ret = new JSONObject();
        ret.put("ok", true);
        try {
            List<UsbDevice> list = resolveUvcDeviceList(host.uvcAppContext());
            ret.put("deviceCount", list.size());
            ret.put("hasDevice", !list.isEmpty());
            synchronized (LOCK) {
                ret.put("opened", sOpenedDevice != null);
                ret.put("previewSurfaceReady", sPreviewSurface != null);
                ret.put("previewStarted", sPreviewRunning);
            }
        } catch (Throwable t) {
            ret.put("ok", false);
            ret.put("err", t.getMessage() != null ? t.getMessage() : "status_error");
        }
        cb.invoke(ret);
    }
}
