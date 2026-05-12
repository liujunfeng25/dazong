# 调试指南

## 问题解决方案

### 1. 导入语句爆红问题

如果你看到以下导入语句出现红色错误标记：
```java
import com.sohe.serialport.sdk.SoheWeightSDK;
import com.sohe.serialport.sdk.WeightData;
import com.sohe.serialport.sdk.WeightDataListener;
import com.sohe.serialport.sdk.SerialPortManager;
import com.sohe.serialport.sdk.DataParser;
```

**解决方法：**

1. **清理并重新构建项目**
   - 在Android Studio中选择 `Build` -> `Clean Project`
   - 等待清理完成后，选择 `Build` -> `Rebuild Project`

2. **检查JAR包依赖**
   - 确认 `app/libs/sohe-serialport-sdk-1.0.0.jar` 文件存在
   - 检查 `app/build.gradle` 中是否有正确的依赖配置：
     ```gradle
     dependencies {
         implementation files('libs/sohe-serialport-sdk-1.0.0.jar')
         // ... 其他依赖
     }
     ```

3. **同步Gradle**
   - 点击Android Studio顶部的 "Sync Now" 按钮
   - 或者选择 `File` -> `Sync Project with Gradle Files`

4. **重启Android Studio**
   - 如果上述方法无效，尝试重启Android Studio

### 2. 串口连接成功但没有重量数据的调试

现在代码中已经添加了详细的调试日志输出，包括：

#### 控制台日志输出位置

1. **Android Studio Logcat窗口**
   - 打开 `View` -> `Tool Windows` -> `Logcat`
   - 选择你的设备和应用包名
   - 查看System.out.println输出的调试信息

2. **应用内日志显示**
   - 应用界面底部的日志文本框会显示详细的调试信息

#### 调试信息说明

**SDK初始化日志：**
```
=== SDK初始化开始 ===
正在加载SOHE重量SDK...
检查SDK类加载状态:
✓ SoheWeightSDK 类加载成功
✓ WeightData 类加载成功
...
SDK初始化成功，版本: x.x.x
===================
```

**串口连接日志：**
```
*** 串口连接状态变更 ***
连接状态: 已连接
串口路径: /dev/ttyUSB0
连接时间: 14:30:25.123
等待接收重量数据...
*************************
```

**原始数据接收日志：**
```
>>> 串口原始数据接收 <<<
字符串形式: 's n 123.45 kg'
数据长度: 12 字节
十六进制: 73 20 6E 20 31 32 33 2E 34 35 20 6B 67
ASCII码: s   n   1 2 3 . 4 5   k g
检测协议: SHOUHENG
接收时间: 14:30:25.456
<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
```

**重量数据解析日志：**
```
=== 重量数据详情 ===
重量值: 123.45 kg
协议类型: SHOUHENG
稳定状态: 稳定
重量类型: 净重
是否稳定: true
是否超载: false
时间戳: 14:30:25.456
===================
```

### 3. 常见问题排查

#### 问题1：串口连接成功但没有数据
**可能原因：**
- 串口波特率不匹配
- 数据格式不符合协议规范
- 硬件设备没有发送数据

**排查步骤：**
1. 检查控制台是否有 ">>> 串口原始数据接收 <<<" 日志
2. 如果没有原始数据，检查硬件连接和设备状态
3. 如果有原始数据但没有重量数据，检查数据格式是否符合协议

#### 问题2：协议检测为"未知"
**可能原因：**
- 数据格式不符合首衡协议或VA协议规范
- 数据中包含异常字符

**解决方法：**
1. 查看原始数据的十六进制和ASCII码输出
2. 确认数据格式符合以下规范：
   - 首衡协议：`[s/w][n/g][重量数据][kg]`
   - VA协议：按VA协议规范格式

#### 问题3：数据接收不稳定
**可能原因：**
- 串口通信干扰
- 波特率设置错误
- 硬件连接不稳定

**解决方法：**
1. 尝试不同的波特率设置
2. 检查串口线缆连接
3. 查看原始数据是否完整

## 技术支持

如果问题仍然存在，请提供以下信息：
1. Android Studio版本
2. 设备型号和Android版本
3. 完整的错误日志
4. 串口设备型号和规格
5. 控制台输出的调试信息