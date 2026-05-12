# SOHE Weight SerialPort SDK

## 概述

SOHE Weight SerialPort SDK 是一个纯Java实现的串口通信SDK，专门用于与重量传感器设备进行通信。SDK支持首衡串行通讯协议和VA协议，提供了完整的串口管理、数据解析和重量数据处理功能。

## 特性

- **纯Java实现**：无Android依赖，可在任何Java环境中运行
- **多协议支持**：支持首衡串行通讯协议和VA协议
- **自动协议识别**：能够自动识别和解析不同的协议格式
- **完整的串口管理**：支持串口连接、断开、数据收发等操作
- **实时数据监听**：提供数据接收、连接状态变化、错误处理等事件回调
- **线程安全**：支持多线程环境下的并发操作
- **易于集成**：简单的API设计，易于集成到现有项目中

## 系统要求

- Java 8 或更高版本
- 支持串口通信的操作系统（Windows、Linux、macOS）

## 快速开始

### 1. 引入SDK

将生成的JAR文件添加到项目的classpath中：

```bash
# 将sohe-serialport-sdk-1.0.0.jar添加到项目依赖
```

### 2. 基本使用示例

```java
import com.sohe.serialport.sdk.*;

public class WeightSDKExample {
    private SoheWeightSDK sdk;
    private WeightDataListener listener;
    
    public void initializeSDK() {
        // 创建SDK实例
        sdk = SoheWeightSDK.createInstance();
        
        // 创建数据监听器
        listener = new WeightDataListener() {
            @Override
            public void onWeightDataReceived(WeightData data) {
                System.out.println("接收到重量数据: " + data.getFormattedWeight());
                System.out.println("重量值: " + data.getWeight() + " " + data.getUnit());
                System.out.println("状态: " + (data.isStable() ? "稳定" : "不稳定"));
            }
            
            @Override
            public void onRawDataReceived(byte[] data) {
                System.out.println("接收到原始数据: " + new String(data));
            }
            
            @Override
            public void onConnectionStatusChanged(boolean connected) {
                System.out.println("连接状态变化: " + (connected ? "已连接" : "已断开"));
            }
            
            @Override
            public void onError(String errorCode) {
                System.err.println("发生错误: " + errorCode);
            }
            
            @Override
            public void onCommandResult(WeightDataListener.CommandType command, boolean success) {
                System.out.println("命令执行结果: " + command + " - " + (success ? "成功" : "失败"));
            }
        };
        
        // 初始化SDK
        if (sdk.initialize(listener)) {
            System.out.println("SDK初始化成功");
        } else {
            System.err.println("SDK初始化失败");
        }
    }
    
    public void connectToDevice() {
        // 获取可用串口列表
        List<String> ports = sdk.getAvailablePorts();
        if (ports.isEmpty()) {
            System.err.println("未找到可用串口");
            return;
        }
        
        // 连接到第一个可用串口
        String portName = ports.get(0);
        if (sdk.connect(portName)) {
            System.out.println("成功连接到串口: " + portName);
        } else {
            System.err.println("连接串口失败: " + portName);
        }
    }
    
    public void sendCommands() {
        // 发送置零命令
        if (sdk.sendZeroCommand()) {
            System.out.println("置零命令发送成功");
        }
        
        // 发送去皮命令
        if (sdk.sendTareCommand()) {
            System.out.println("去皮命令发送成功");
        }
        
        // 发送自定义命令
        String customCommand = "CUSTOM_CMD\r\n";
        if (sdk.sendCustomCommand(customCommand.getBytes())) {
            System.out.println("自定义命令发送成功");
        }
    }
    
    public void cleanup() {
        // 释放资源
        if (sdk != null) {
            sdk.release();
        }
    }
}
```

### 3. 高级配置示例

```java
public void initializeWithCustomConfig() {
    // 创建自定义配置
    SoheWeightSDK.Config config = new SoheWeightSDK.Config();
    config.setBaudRate(19200);           // 设置波特率
    config.setAutoConnect(true);         // 启用自动连接
    config.setPreferredPort("COM3");     // 设置首选端口
    
    // 使用自定义配置初始化
    if (sdk.initialize(listener, config)) {
        System.out.println("SDK初始化成功，使用自定义配置");
    }
}
```

## API 参考

### SoheWeightSDK 类

#### 静态方法

- `createInstance()`: 创建SDK实例

#### 实例方法

- `initialize(WeightDataListener listener)`: 使用默认配置初始化SDK
- `initialize(WeightDataListener listener, Config config)`: 使用自定义配置初始化SDK
- `isInitialized()`: 检查SDK是否已初始化
- `connect(String portName)`: 连接到指定串口
- `disconnect()`: 断开串口连接
- `isConnected()`: 检查是否已连接
- `getCurrentPortName()`: 获取当前连接的串口名称
- `getAvailablePorts()`: 获取可用串口列表
- `sendZeroCommand()`: 发送置零命令
- `sendTareCommand()`: 发送去皮命令
- `sendCustomCommand(byte[] command)`: 发送自定义命令
- `getVersion()`: 获取SDK版本信息
- `release()`: 释放SDK资源

### WeightDataListener 接口

#### 回调方法

- `onWeightDataReceived(WeightData data)`: 接收到解析后的重量数据
- `onRawDataReceived(byte[] data)`: 接收到原始数据
- `onConnectionStatusChanged(boolean connected)`: 连接状态发生变化
- `onError(String errorCode)`: 发生错误
- `onCommandResult(CommandType command, boolean success)`: 命令执行结果

#### 枚举类型

**CommandType**:
- `ZERO`: 置零命令
- `TARE`: 去皮命令
- `CUSTOM`: 自定义命令

**ErrorCode**:
- `UNKNOWN_ERROR`: 未知错误
- `CONNECTION_FAILED`: 连接失败
- `PARSE_DATA_FAILED`: 数据解析失败
- `SEND_COMMAND_FAILED`: 命令发送失败
- `SERIAL_PORT_NOT_FOUND`: 串口未找到
- `PERMISSION_DENIED`: 权限被拒绝
- `DEVICE_BUSY`: 设备忙碌
- `TIMEOUT`: 超时
- `INVALID_PARAMETER`: 无效参数
- `SDK_NOT_INITIALIZED`: SDK未初始化
- `DATA_PARSE_ERROR`: 数据解析错误

### WeightData 类

#### 属性方法

- `getWeight()`: 获取重量值
- `getUnit()`: 获取重量单位
- `getStatus()`: 获取状态（稳定/不稳定）
- `getWeightType()`: 获取重量类型（净重/毛重）
- `getProtocolType()`: 获取协议类型
- `getTimestamp()`: 获取时间戳
- `getRawData()`: 获取原始数据
- `isStable()`: 是否稳定
- `isValidWeight()`: 是否有效重量
- `getFormattedWeight()`: 获取格式化的重量字符串

#### 常量

**协议类型**:
- `PROTOCOL_SHOUHENG`: 首衡协议
- `PROTOCOL_VA`: VA协议
- `PROTOCOL_UNKNOWN`: 未知协议

**状态**:
- `STATUS_STABLE`: 稳定
- `STATUS_UNSTABLE`: 不稳定
- `STATUS_UNKNOWN`: 未知状态

**重量类型**:
- `TYPE_NET`: 净重
- `TYPE_GROSS`: 毛重
- `TYPE_UNKNOWN`: 未知类型

**单位**:
- `UNIT_KG`: 千克
- `UNIT_G`: 克
- `UNIT_LB`: 磅
- `UNIT_OZ`: 盎司
- `UNIT_UNKNOWN`: 未知单位

### Config 类

#### 配置方法

- `setBaudRate(int baudRate)`: 设置波特率（默认：9600）
- `getBaudRate()`: 获取波特率
- `setAutoConnect(boolean autoConnect)`: 设置是否自动连接（默认：true）
- `isAutoConnect()`: 是否自动连接
- `setPreferredPort(String port)`: 设置首选端口（默认：null）
- `getPreferredPort()`: 获取首选端口

## 支持的协议

### 1. 首衡串行通讯协议

**格式**: `[状态][重量值][单位][\r\n]`

**示例**:
- `sn0001.234kg\r\n` - 稳定净重 1.234kg
- `sw0002.500g\r\n` - 不稳定净重 2.500g
- `gn0003.750lb\r\n` - 稳定毛重 3.750lb

**状态标识**:
- `sn`: 稳定净重
- `sw`: 不稳定净重
- `gn`: 稳定毛重
- `gw`: 不稳定毛重

### 2. VA协议

**格式**: `VA,[地址],[状态码],[稳定性],[重量类型],[符号] [重量值] [单位][\r\n]`

**示例**:
- `VA,01,19,S,N,+ 1.234 kg\r\n` - 稳定净重 +1.234kg
- `VA,01,19,U,G,- 0.125 lb\r\n` - 不稳定毛重 -0.125lb

**参数说明**:
- 地址: 设备地址（01-99）
- 状态码: 设备状态码
- 稳定性: S=稳定, U=不稳定
- 重量类型: N=净重, G=毛重
- 符号: +/- 表示正负

## 错误处理

### 常见错误及解决方案

1. **CONNECTION_FAILED**: 串口连接失败
   - 检查串口是否被其他程序占用
   - 确认串口名称是否正确
   - 检查设备是否正确连接

2. **PARSE_DATA_FAILED**: 数据解析失败
   - 检查设备发送的数据格式是否正确
   - 确认协议类型是否匹配

3. **SERIAL_PORT_NOT_FOUND**: 串口未找到
   - 检查设备是否正确连接
   - 刷新串口列表

4. **SDK_NOT_INITIALIZED**: SDK未初始化
   - 确保在使用前调用initialize()方法

## 最佳实践

### 1. 资源管理

```java
// 使用try-with-resources或确保在finally块中释放资源
try {
    sdk = SoheWeightSDK.createInstance();
    sdk.initialize(listener);
    // 使用SDK...
} finally {
    if (sdk != null) {
        sdk.release();
    }
}
```

### 2. 错误处理

```java
@Override
public void onError(String errorCode) {
    switch (errorCode) {
        case WeightDataListener.ErrorCode.CONNECTION_FAILED:
            // 处理连接失败
            handleConnectionError();
            break;
        case WeightDataListener.ErrorCode.PARSE_DATA_FAILED:
            // 处理数据解析失败
            handleParseError();
            break;
        default:
            // 处理其他错误
            handleGenericError(errorCode);
            break;
    }
}
```

### 3. 线程安全

```java
// SDK的所有方法都是线程安全的，可以在多线程环境中使用
ExecutorService executor = Executors.newFixedThreadPool(2);

executor.submit(() -> {
    // 线程1：发送命令
    sdk.sendZeroCommand();
});

executor.submit(() -> {
    // 线程2：发送其他命令
    sdk.sendTareCommand();
});
```

## 示例项目

完整的示例项目请参考SDK包中的test目录，其中包含了各种使用场景的单元测试。

## 版本历史

### v1.0.0
- 初始版本发布
- 支持首衡串行通讯协议和VA协议
- 提供完整的串口管理功能
- 纯Java实现，无Android依赖

## 技术支持

如有问题或建议，请联系技术支持团队。

## 许可证

本SDK遵循相应的许可证协议，具体请参考LICENSE文件。