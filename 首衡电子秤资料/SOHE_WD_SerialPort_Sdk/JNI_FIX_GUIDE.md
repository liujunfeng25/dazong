# JNI方法签名修复指南

## 问题分析

### 崩溃原因
您遇到的崩溃问题是由于**JNI方法签名不匹配**导致的：

```
java.lang.UnsatisfiedLinkError: No implementation found for java.lang.Object 
com.sohe.serialport.sdk.SerialPortManager.nativeOpenSerialPort(java.lang.String, int)
```

### 根本原因
1. **Java端声明**：`nativeOpenSerialPort`, `nativeCloseSerialPort` 等
2. **C++端实现**：`openSerialPort`, `closeSerialPort` 等
3. **包名不匹配**：C++中使用了错误的包名路径

## 修复内容

### 1. 修正JNI方法签名

**修复前（C++）**：
```cpp
Java_com_example_sohe_1wd_1serialport_1sdk_SerialPortManager_openSerialPort
Java_com_example_sohe_1wd_1serialport_1sdk_SerialPortManager_closeSerialPort
```

**修复后（C++）**：
```cpp
Java_com_sohe_serialport_sdk_SerialPortManager_nativeOpenSerialPort
Java_com_sohe_serialport_sdk_SerialPortManager_nativeCloseSerialPort
Java_com_sohe_serialport_sdk_SerialPortManager_nativeReadSerialPort
Java_com_sohe_serialport_sdk_SerialPortManager_nativeWriteSerialPort
```

### 2. 添加缺失的JNI方法

新增了完整的串口读写方法实现：

#### nativeReadSerialPort
- 从串口文件描述符读取数据
- 返回实际读取的字节数
- 包含完整的错误处理

#### nativeWriteSerialPort
- 向串口文件描述符写入数据
- 返回写入是否成功
- 验证写入字节数的完整性

### 3. 包名路径修正

**正确的包名映射**：
- Java包名：`com.sohe.serialport.sdk`
- JNI方法前缀：`Java_com_sohe_serialport_sdk_`

## 技术细节

### JNI方法签名规则

1. **前缀**：`Java_`
2. **包名**：用下划线替换点号
3. **类名**：`SerialPortManager`
4. **方法名**：与Java中声明的native方法名完全一致

### 参数类型映射

| Java类型 | JNI类型 | C++类型 |
|---------|---------|----------|
| String | jstring | jstring |
| int | jint | jint |
| Object | jobject | jobject |
| byte[] | jbyteArray | jbyteArray |
| boolean | jboolean | jboolean |

## 验证修复效果

### 1. 编译验证
```bash
# 重新编译项目
./gradlew :app:build

# 检查JNI库是否正确生成
ls app/build/intermediates/cmake/debug/obj/
```

### 2. 运行时验证

启动应用后，查看日志输出：

**成功情况**：
```
JNI串口库加载成功
真实串口打开成功: /dev/ttyS1
```

**权限问题**（需要root权限）：
```
type=1400 audit: avc: denied { read } for name="ttyS1"
```

### 3. 权限解决方案

在Android设备上访问串口需要特殊权限：

#### 方法1：添加权限声明
在 `AndroidManifest.xml` 中添加：
```xml
<uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />
<uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />
```

#### 方法2：Root权限（开发测试）
```bash
# 获取root权限
adb shell su

# 修改串口设备权限
chmod 666 /dev/ttyS1
```

#### 方法3：SELinux策略（生产环境）
需要自定义SELinux策略允许应用访问串口设备。

## 常见问题

### Q1: 仍然出现UnsatisfiedLinkError？
**A**: 
1. 确认JNI库是否正确编译
2. 检查方法签名是否完全匹配
3. 验证包名路径是否正确

### Q2: 串口权限被拒绝？
**A**: 
1. 检查设备是否有root权限
2. 确认串口设备文件存在
3. 验证SELinux策略设置

### Q3: 如何调试JNI方法？
**A**: 
1. 使用 `__android_log_print` 添加日志
2. 检查 `adb logcat` 输出
3. 验证参数传递是否正确

## 文件修改清单

1. **serial_port.cpp**：修正所有JNI方法签名和实现
2. **SerialPortManager.java**：已包含正确的native方法声明
3. **sohe-serialport-sdk-1.0.0.jar**：重新编译的SDK包

现在您的应用应该能够正确加载JNI库并尝试连接真实串口设备了！