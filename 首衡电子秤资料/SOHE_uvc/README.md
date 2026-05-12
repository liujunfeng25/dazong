# SOHE UVC Camera App

这是一个使用UVC（USB Video Class）库实现的安卓USB摄像头应用。

## 功能特性

1. **自动检测USB摄像头** - 应用会自动检测连接到安卓设备的USB摄像头
2. **摄像头列表** - 在下拉列表中显示所有已连接的USB摄像头
3. **实时预览** - 打开摄像头后可以看到实时视频流
4. **拍照功能** - 可以拍摄照片并保存到设备
5. **照片预览** - 拍摄的照片会立即显示在界面上

## 技术栈

- **语言**: Java
- **最小SDK**: 24 (Android 7.0)
- **目标SDK**: 36
- **主要依赖**:
  - UVCCamera 2.3.7 (saki4510t)
  - libcommon 8.4.0
  - AndroidX AppCompat
  - Material Design Components

## 使用说明

### 准备工作

1. 确保您的安卓设备支持USB OTG功能
2. 准备一个USB摄像头（需要支持UVC协议）
3. 准备OTG转接线（如果需要）

### 使用步骤

1. **启动应用** - 打开SOHE UVC Camera应用
2. **连接摄像头** - 使用USB线（或OTG线）连接USB摄像头到安卓设备
3. **授予权限** - 首次使用时，应用会请求必要的权限（相机、存储等），请全部允许
4. **选择摄像头** - 在顶部的下拉列表中选择要使用的摄像头
5. **打开摄像头** - 点击"打开摄像头"按钮
6. **授予USB权限** - 系统会弹出USB权限请求，点击"确定"
7. **查看预览** - 摄像头成功打开后，会在中间区域显示实时预览
8. **拍照** - 点击"拍照"按钮进行拍摄
9. **查看照片** - 拍摄的照片会显示在底部的预览区域
10. **关闭摄像头** - 使用完毕后点击"关闭摄像头"按钮

### 照片保存位置

拍摄的照片会自动保存到：
```
/Pictures/SOHE_UVC/UVC_yyyyMMdd_HHmmss.jpg
```

## 权限说明

应用需要以下权限：

- **CAMERA** - 用于访问相机硬件
- **WRITE_EXTERNAL_STORAGE** - 用于保存拍摄的照片（Android 12及以下）
- **READ_EXTERNAL_STORAGE** - 用于读取存储（Android 12及以下）
- **READ_MEDIA_IMAGES** - 用于读取媒体图片（Android 13及以上）

## 注意事项

1. **USB权限** - 每次连接新的USB设备时都需要授予USB权限
2. **设备兼容性** - 不是所有的USB摄像头都支持UVC协议，请确认您的摄像头支持
3. **电源供应** - 某些USB摄像头可能需要额外的电源供应
4. **多摄像头** - 如果连接了多个USB摄像头，可以在下拉列表中切换
5. **断开重连** - 如果摄像头断开连接，应用会自动关闭当前会话

## 故障排除

### 检测不到USB摄像头
- 确认摄像头已正确连接
- 点击"刷新设备列表"按钮
- 尝试拔下并重新连接摄像头
- 检查OTG功能是否正常工作

### 无法打开摄像头
- 确认已授予USB权限
- 检查摄像头是否被其他应用占用
- 尝试重启应用
- 确认摄像头支持UVC协议

### 拍照失败
- 确保摄像头已成功打开并显示预览
- 检查存储权限是否已授予
- 确认设备有足够的存储空间

## 开发信息

### 构建项目

```bash
# 克隆项目
git clone <repository-url>

# 打开项目
# 使用Android Studio打开项目文件夹

# 同步Gradle
# Android Studio会自动同步Gradle依赖

# 运行应用
# 连接设备或启动模拟器，点击Run按钮
```

### 项目结构

```
app/
├── src/
│   └── main/
│       ├── java/com/example/sohe_uvc/
│       │   └── MainActivity.java          # 主Activity
│       ├── res/
│       │   ├── layout/
│       │   │   └── activity_main.xml     # 主界面布局
│       │   └── xml/
│       │       └── device_filter.xml     # USB设备过滤器
│       └── AndroidManifest.xml           # 应用清单
└── build.gradle                          # 应用级构建配置
```

## UVC库说明

本项目使用saki4510t的UVCCamera库，这是一个优秀的Android USB摄像头库：
- GitHub: https://github.com/saki4510t/UVCCamera
- 支持标准UVC协议的USB摄像头
- 提供预览、拍照、录像等功能
- 支持多种视频格式

## 许可证

本项目仅供学习和参考使用。

## 联系方式

如有问题或建议，请联系开发者。

