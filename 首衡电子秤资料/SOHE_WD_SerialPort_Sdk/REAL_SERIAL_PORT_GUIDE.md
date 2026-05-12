# 真实串口连接指南

## 问题解决

### 之前的问题
您之前遇到的问题是SDK使用的是**模拟实现**，接收到的是预设的测试数据而不是真实的串口数据。

### 解决方案
我们已经对SDK进行了以下关键修改：

#### 1. 添加了JNI支持
- 在 `SerialPortManager.java` 中添加了JNI库加载
- 声明了native方法用于真实串口操作
- 实现了自动回退机制：JNI库不可用时使用模拟模式

#### 2. 真实串口实现
```java
// 新增的JNI方法
private native Object nativeOpenSerialPort(String path, int baudRate);
private native void nativeCloseSerialPort(Object serialPort);
private native int nativeReadSerialPort(Object serialPort, byte[] buffer);
private native boolean nativeWriteSerialPort(Object serialPort, byte[] data);
```

#### 3. 智能模式切换
- **JNI库可用**：使用真实串口通信
- **JNI库不可用**：自动回退到模拟模式
- 控制台会显示当前使用的模式

## 使用真实串口的步骤

### 1. 确保JNI库编译
项目已配置CMake来编译C++串口库：
```bash
# 编译整个项目（包括JNI库）
./gradlew build
```

### 2. 检查串口设备
- **Windows**: 确保串口设备显示为 `COM1`, `COM2` 等
- **Linux/Android**: 确保设备路径如 `/dev/ttyUSB0`, `/dev/ttyACM0` 等存在

### 3. 运行应用
启动应用后，查看控制台输出：

**成功加载JNI库**：
```
JNI串口库加载成功
真实串口打开成功: COM3
```

**回退到模拟模式**：
```
无法加载串口JNI库: java.lang.UnsatisfiedLinkError: ...
将使用模拟模式运行
使用模拟串口模式: COM3
```

## 调试信息

### 控制台输出说明
1. **JNI库状态**：显示是否成功加载native库
2. **串口模式**：显示当前使用真实串口还是模拟模式
3. **连接状态**：显示串口打开/关闭的详细信息
4. **数据接收**：显示接收到的原始数据（十六进制和ASCII）

### 验证真实数据
当使用真实串口时，您会看到：
- 数据内容随硬件设备的实际状态变化
- 没有数据时不会有固定的测试数据输出
- 数据格式符合您的硬件设备协议

## 常见问题

### Q1: 如何确认使用的是真实串口？
**A**: 查看控制台输出，如果看到"真实串口打开成功"则表示使用真实串口。

### Q2: JNI库加载失败怎么办？
**A**: 
1. 确保项目完整编译：`./gradlew build`
2. 检查 `app/src/main/cpp/` 目录下的C++文件
3. 验证CMakeLists.txt配置正确

### Q3: 真实串口无数据怎么办？
**A**:
1. 检查硬件设备是否正常工作
2. 确认串口参数（波特率、数据位等）匹配
3. 验证串口权限和设备连接

### Q4: 如何强制使用模拟模式测试？
**A**: 可以临时重命名JNI库文件，使其加载失败，系统会自动回退到模拟模式。

## 技术细节

### JNI实现位置
- **Java接口**: `sdk-lib/src/main/java/com/sohe/serialport/sdk/SerialPortManager.java`
- **C++实现**: `app/src/main/cpp/serial_port.cpp`
- **CMake配置**: `app/src/main/cpp/CMakeLists.txt`

### 编译输出
- **JAR包**: `sdk-lib/build/libs/sohe-serialport-sdk-1.0.0.jar`
- **JNI库**: `app/build/intermediates/cmake/debug/obj/`

现在您的SDK已经支持真实串口通信，不再局限于模拟数据！