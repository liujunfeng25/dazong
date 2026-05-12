package com.example.sohe_uvc;

import android.Manifest;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.hardware.usb.UsbDevice;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.view.Surface;
import android.view.View;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.herohan.uvcapp.CameraException;
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

public class MainActivity extends AppCompatActivity {
    private static final String TAG = "MainActivity";
    private static final int REQUEST_PERMISSION = 1001;

    private UVCCameraTextureView mCameraView;
    private ImageView mCapturedImage;
    private Spinner mCameraSpinner;
    private Button mBtnOpenCamera;
    private Button mBtnCloseCamera;
    private Button mBtnCapture;
    private Button mBtnRefresh;
    private TextView mTvNoCamera;

    private final Handler mMainHandler = new Handler(Looper.getMainLooper());

    private CameraHelper mCameraHelper;
    private Surface mPreviewSurface;

    private final List<UsbDevice> mDeviceList = new ArrayList<>();
    private ArrayAdapter<String> mAdapter;
    private UsbDevice mSelectedDevice;
    private UsbDevice mOpenedDevice;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        initViews();
        checkAndRequestPermissions();
        setupCameraHelper();
        refreshDeviceList();
    }

    private void initViews() {
        mCameraView = findViewById(R.id.cameraView);
        mCapturedImage = findViewById(R.id.capturedImage);
        mCameraSpinner = findViewById(R.id.cameraSpinner);
        mBtnOpenCamera = findViewById(R.id.btnOpenCamera);
        mBtnCloseCamera = findViewById(R.id.btnCloseCamera);
        mBtnCapture = findViewById(R.id.btnCapture);
        mBtnRefresh = findViewById(R.id.btnRefresh);
        mTvNoCamera = findViewById(R.id.tvNoCamera);

        mBtnOpenCamera.setOnClickListener(v -> openSelectedCamera());
        mBtnCloseCamera.setOnClickListener(v -> closeCurrentCamera());
        mBtnCapture.setOnClickListener(v -> captureImage());
        mBtnRefresh.setOnClickListener(v -> refreshDeviceList());

        mCameraSpinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                if (position >= 0 && position < mDeviceList.size()) {
                    mSelectedDevice = mDeviceList.get(position);
                } else {
                    mSelectedDevice = null;
                }
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) {
                mSelectedDevice = null;
            }
        });

        List<String> placeholder = new ArrayList<>();
        placeholder.add("未检测到USB摄像头");
        mAdapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, placeholder);
        mAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        mCameraSpinner.setAdapter(mAdapter);

        mCameraView.setCallback(mSurfaceCallback);
        updateUiCameraClosed();
    }

    private void setupCameraHelper() {
        mCameraHelper = new CameraHelper();
        mCameraHelper.setStateCallback(mStateCallback);
    }

    private void checkAndRequestPermissions() {
        List<String> permissionsNeeded = new ArrayList<>();
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            permissionsNeeded.add(Manifest.permission.CAMERA);
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_MEDIA_IMAGES) != PackageManager.PERMISSION_GRANTED) {
                permissionsNeeded.add(Manifest.permission.READ_MEDIA_IMAGES);
            }
        } else {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
                permissionsNeeded.add(Manifest.permission.WRITE_EXTERNAL_STORAGE);
            }
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
                permissionsNeeded.add(Manifest.permission.READ_EXTERNAL_STORAGE);
            }
        }

        if (!permissionsNeeded.isEmpty()) {
            ActivityCompat.requestPermissions(this, permissionsNeeded.toArray(new String[0]), REQUEST_PERMISSION);
        }
    }

    private void refreshDeviceList() {
        List<UsbDevice> devices = mCameraHelper != null ? mCameraHelper.getDeviceList() : Collections.emptyList();
        mDeviceList.clear();
        if (devices != null) {
            mDeviceList.addAll(devices);
        }

        List<String> items = new ArrayList<>();
        for (int i = 0; i < mDeviceList.size(); i++) {
            UsbDevice device = mDeviceList.get(i);
            items.add(String.format(Locale.getDefault(), "摄像头 %d (%04X:%04X)", i + 1, device.getVendorId(), device.getProductId()));
        }

        runOnUiThread(() -> {
            mAdapter.clear();
            if (items.isEmpty()) {
                mAdapter.add("未检测到USB摄像头");
                mTvNoCamera.setVisibility(View.VISIBLE);
                mSelectedDevice = null;
            } else {
                mAdapter.addAll(items);
                mTvNoCamera.setVisibility(View.GONE);
                if (mSelectedDevice == null || !mDeviceList.contains(mSelectedDevice)) {
                    mCameraSpinner.setSelection(0, true);
                    mSelectedDevice = mDeviceList.get(0);
                } else {
                    int index = mDeviceList.indexOf(mSelectedDevice);
                    mCameraSpinner.setSelection(index, true);
                }
            }
            mAdapter.notifyDataSetChanged();
        });
    }

    private void openSelectedCamera() {
        if (mCameraHelper == null) {
            showToast("初始化失败，无法打开摄像头");
            return;
        }
        if (mSelectedDevice == null) {
            showToast("请先选择一个摄像头");
            return;
        }
        showToast("请求USB权限...");
        mCameraHelper.selectDevice(mSelectedDevice);
    }

    private void closeCurrentCamera() {
        if (mCameraHelper == null) {
            return;
        }
        if (mPreviewSurface != null) {
            mCameraHelper.removeSurface(mPreviewSurface);
        }
        mCameraHelper.stopPreview();
        mCameraHelper.closeCamera();
        mOpenedDevice = null;
        updateUiCameraClosed();
    }

    private void captureImage() {
        if (mCameraHelper == null || mOpenedDevice == null) {
            showToast("请先打开摄像头");
            return;
        }

        final File outputFile = createImageFile();
        if (outputFile == null) {
            showToast("无法创建图片文件");
            return;
        }

        IImageCapture.OutputFileOptions options = new IImageCapture.OutputFileOptions.Builder(outputFile).build();
        mCameraHelper.takePicture(options, new IImageCapture.OnImageCaptureCallback() {
            @Override
            public void onImageSaved(@NonNull OutputFileResults outputFileResults) {
                mMainHandler.post(() -> {
                    Bitmap bitmap = BitmapFactory.decodeFile(outputFile.getAbsolutePath());
                    if (bitmap != null) {
                        mCapturedImage.setImageBitmap(bitmap);
                    }
                    showToast("拍照成功: " + outputFile.getName());
                });
            }

            @Override
            public void onError(int error, @NonNull String message, @NonNull Throwable cause) {
                mMainHandler.post(() -> showToast("拍照失败: " + message));
            }
        });
    }

    private File createImageFile() {
        try {
            File picturesDir = getExternalFilesDir(Environment.DIRECTORY_PICTURES);
            if (picturesDir == null) {
                return null;
            }
            File appDir = new File(picturesDir, "SOHE_UVC");
            if (!appDir.exists() && !appDir.mkdirs()) {
                return null;
            }
            String timeStamp = new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(new Date());
            return new File(appDir, "UVC_" + timeStamp + ".jpg");
        } catch (Exception e) {
            return null;
        }
    }

    private final CameraViewInterface.Callback mSurfaceCallback = new CameraViewInterface.Callback() {
        @Override
        public void onSurfaceCreated(CameraViewInterface view, Surface surface) {
            mPreviewSurface = surface;
            if (mCameraHelper != null && mOpenedDevice != null) {
                mCameraHelper.removeSurface(surface);
                mCameraHelper.addSurface(surface, false);
                mCameraHelper.startPreview();
            }
        }

        @Override
        public void onSurfaceChanged(CameraViewInterface view, Surface surface, int width, int height) {
            // no-op
        }

        @Override
        public void onSurfaceDestroy(CameraViewInterface view, Surface surface) {
            if (mCameraHelper != null) {
                mCameraHelper.removeSurface(surface);
            }
            if (Objects.equals(surface, mPreviewSurface)) {
                mPreviewSurface = null;
            }
        }
    };

    private final ICameraHelper.StateCallback mStateCallback = new ICameraHelper.StateCallback() {
        @Override
        public void onAttach(UsbDevice device) {
            refreshDeviceList();
            showToast("检测到新的USB摄像头");
        }

        @Override
        public void onDeviceOpen(UsbDevice device, boolean b) {
            if (device.equals(mSelectedDevice)) {
                showToast("USB权限已授予，正在打开摄像头...");
                mCameraHelper.openCamera();
            }
        }

        @Override
        public void onCameraOpen(UsbDevice device) {
            if (device.equals(mSelectedDevice)) {
                mOpenedDevice = device;
                attachPreviewSurface();
                mCameraHelper.startPreview();
                updateUiCameraOpened();
                showToast("摄像头已打开");
            }
        }

        @Override
        public void onCameraClose(UsbDevice device) {
            if (device.equals(mOpenedDevice)) {
                if (mPreviewSurface != null) {
                    mCameraHelper.removeSurface(mPreviewSurface);
                }
                mOpenedDevice = null;
                updateUiCameraClosed();
                showToast("摄像头已关闭");
            }
        }

        @Override
        public void onDeviceClose(UsbDevice device) {
            if (device.equals(mOpenedDevice)) {
                mOpenedDevice = null;
                updateUiCameraClosed();
            }
        }

        @Override
        public void onDetach(UsbDevice device) {
            if (device.equals(mOpenedDevice)) {
                mCameraHelper.stopPreview();
                mCameraHelper.closeCamera();
                mOpenedDevice = null;
            }
            refreshDeviceList();
            showToast("USB设备已断开");
        }

        @Override
        public void onCancel(UsbDevice device) {
            showToast("USB权限被拒绝");
        }

        @Override
        public void onError(UsbDevice device, CameraException e) {
            showToast("摄像头错误: " + e.getMessage());
        }
    };

    private void updateUiCameraOpened() {
        runOnUiThread(() -> {
            mBtnOpenCamera.setEnabled(false);
            mBtnCloseCamera.setEnabled(true);
            mBtnCapture.setEnabled(true);
            mTvNoCamera.setVisibility(View.GONE);
        });
    }

    private void updateUiCameraClosed() {
        runOnUiThread(() -> {
            mBtnOpenCamera.setEnabled(true);
            mBtnCloseCamera.setEnabled(false);
            mBtnCapture.setEnabled(false);
            if (mDeviceList.isEmpty()) {
                mTvNoCamera.setVisibility(View.VISIBLE);
            }
        });
    }

    private void showToast(String message) {
        mMainHandler.post(() -> Toast.makeText(MainActivity.this, message, Toast.LENGTH_SHORT).show());
    }

    private void attachPreviewSurface() {
        if (mCameraHelper == null || mPreviewSurface == null) {
            return;
        }
        mCameraHelper.removeSurface(mPreviewSurface);
        mCameraHelper.addSurface(mPreviewSurface, false);
    }

    @Override
    protected void onDestroy() {
        if (mCameraHelper != null) {
            mCameraHelper.releaseAll();
            mCameraHelper = null;
        }
        mPreviewSurface = null;
        super.onDestroy();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_PERMISSION) {
            boolean granted = true;
            for (int result : grantResults) {
                if (result != PackageManager.PERMISSION_GRANTED) {
                    granted = false;
                    break;
                }
            }
            if (granted) {
                showToast("权限已授予");
            } else {
                showToast("缺少必要权限，功能可能受限");
            }
        }
    }
}

