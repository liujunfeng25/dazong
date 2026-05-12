package example;

import com.sohe.serialport.sdk.*;
import java.util.List;
import java.util.Scanner;

/**
 * SOHE Weight SerialPort SDK 使用示例
 * 
 * 这个示例展示了如何使用SDK进行串口通信和重量数据处理
 */
public class WeightSDKExample {
    
    private SoheWeightSDK sdk;
    private WeightDataListener listener;
    private boolean isRunning = false;
    
    public static void main(String[] args) {
        WeightSDKExample example = new WeightSDKExample();
        example.run();
    }
    
    public void run() {
        System.out.println("=== SOHE Weight SerialPort SDK 示例程序 ===");
        
        // 初始化SDK
        if (!initializeSDK()) {
            System.err.println("SDK初始化失败，程序退出");
            return;
        }
        
        // 显示可用串口
        showAvailablePorts();
        
        // 连接设备
        if (!connectToDevice()) {
            System.err.println("设备连接失败，程序退出");
            cleanup();
            return;
        }
        
        // 启动交互式命令行界面
        startInteractiveMode();
        
        // 清理资源
        cleanup();
        
        System.out.println("程序结束");
    }
    
    /**
     * 初始化SDK
     */
    private boolean initializeSDK() {
        try {
            // 创建SDK实例
            sdk = new SoheWeightSDK();
            System.out.println("SDK版本: " + sdk.getVersion());
            
            // 创建数据监听器
            listener = new WeightDataListenerImpl();
            
            // 创建自定义配置
            SoheWeightSDK.Config config = new SoheWeightSDK.Config();
            config.setBaudRate(9600);        // 设置波特率
            config.setAutoConnect(false);    // 禁用自动连接
            config.setPreferredPort(null);   // 不设置首选端口
            
            // 设置监听器
            sdk.setWeightDataListener(listener);
            
            // 初始化SDK
            boolean result = sdk.initialize(config);
            
            if (result) {
                System.out.println("SDK初始化成功");
            } else {
                System.err.println("SDK初始化失败");
            }
            
            return result;
            
        } catch (Exception e) {
            System.err.println("SDK初始化异常: " + e.getMessage());
            e.printStackTrace();
            return false;
        }
    }
    
    /**
     * 显示可用串口列表
     */
    private void showAvailablePorts() {
        System.out.println("\n=== 可用串口列表 ===");
        
        List<String> ports = sdk.getAvailablePorts();
        
        if (ports.isEmpty()) {
            System.out.println("未找到可用串口");
        } else {
            for (int i = 0; i < ports.size(); i++) {
                System.out.println((i + 1) + ". " + ports.get(i));
            }
        }
    }
    
    /**
     * 连接到设备
     */
    private boolean connectToDevice() {
        List<String> ports = sdk.getAvailablePorts();
        
        if (ports.isEmpty()) {
            System.err.println("未找到可用串口");
            return false;
        }
        
        Scanner scanner = new Scanner(System.in);
        
        while (true) {
            System.out.print("\n请选择要连接的串口 (1-" + ports.size() + ", 0=退出): ");
            
            try {
                int choice = scanner.nextInt();
                
                if (choice == 0) {
                    return false;
                }
                
                if (choice < 1 || choice > ports.size()) {
                    System.err.println("无效选择，请重新输入");
                    continue;
                }
                
                String selectedPort = ports.get(choice - 1);
                System.out.println("正在连接到: " + selectedPort);
                
                if (sdk.connect(selectedPort)) {
                    System.out.println("连接成功!");
                    return true;
                } else {
                    System.err.println("连接失败，请重试");
                }
                
            } catch (Exception e) {
                System.err.println("输入错误，请输入数字");
                scanner.nextLine(); // 清除无效输入
            }
        }
    }
    
    /**
     * 启动交互式命令行界面
     */
    private void startInteractiveMode() {
        Scanner scanner = new Scanner(System.in);
        isRunning = true;
        
        System.out.println("\n=== 交互式命令界面 ===");
        showHelp();
        
        while (isRunning) {
            System.out.print("\n请输入命令 (h=帮助): ");
            String input = scanner.nextLine().trim().toLowerCase();
            
            switch (input) {
                case "h":
                case "help":
                    showHelp();
                    break;
                    
                case "z":
                case "zero":
                    sendZeroCommand();
                    break;
                    
                case "t":
                case "tare":
                    sendTareCommand();
                    break;
                    
                case "x":
                case "xdre":
                    sendXDRECommand();
                    break;
                    
                case "y":
                case "yare":
                    sendYARECommand();
                    break;
                    
                case "pt":
                case "preset":
                    sendPresetTareCommand(scanner);
                    break;
                    
                case "c":
                case "custom":
                    sendCustomCommand(scanner);
                    break;
                    
                case "s":
                case "status":
                    showStatus();
                    break;
                    
                case "p":
                case "ports":
                    showAvailablePorts();
                    break;
                    
                case "r":
                case "reconnect":
                    reconnectDevice();
                    break;
                    
                case "q":
                case "quit":
                case "exit":
                    isRunning = false;
                    break;
                    
                default:
                    System.err.println("未知命令: " + input + "，输入 'h' 查看帮助");
                    break;
            }
        }
    }
    
    /**
     * 显示帮助信息
     */
    private void showHelp() {
        System.out.println("\n可用命令:");
        System.out.println("  h, help     - 显示帮助信息");
        System.out.println("  z, zero     - 发送置零命令");
        System.out.println("  t, tare     - 发送去皮命令");
        System.out.println("  x, xdre     - 发送XDRE命令");
        System.out.println("  y, yare     - 发送YARE命令");
        System.out.println("  pt, preset  - 发送预制皮重命令 (可输入自定义皮重值或使用默认值 0012.34)");
        System.out.println("  c, custom   - 发送自定义命令");
        System.out.println("  s, status   - 显示连接状态");
        System.out.println("  p, ports    - 显示可用串口");
        System.out.println("  r, reconnect- 重新连接设备");
        System.out.println("  q, quit     - 退出程序");
    }
    
    /**
     * 发送置零命令
     */
    private void sendZeroCommand() {
        System.out.println("发送置零命令...");
        
        if (sdk.sendZeroCommand()) {
            System.out.println("置零命令发送成功");
        } else {
            System.err.println("置零命令发送失败");
        }
    }
    
    /**
     * 发送去皮命令
     */
    private void sendTareCommand() {
        System.out.println("发送去皮命令...");
        
        if (sdk.sendTareCommand()) {
            System.out.println("去皮命令发送成功");
        } else {
            System.err.println("去皮命令发送失败");
        }
    }
    
    /**
     * 发送XDRE命令
     */
    private void sendXDRECommand() {
        System.out.println("发送XDRE命令...");
        
        if (sdk.sendXDRECommand()) {
            System.out.println("XDRE命令发送成功");
        } else {
            System.err.println("XDRE命令发送失败");
        }
    }
    
    /**
     * 发送YARE命令
     */
    private void sendYARECommand() {
        System.out.println("发送YARE命令...");
        
        if (sdk.sendYARECommand()) {
            System.out.println("YARE命令发送成功");
        } else {
            System.err.println("YARE命令发送失败");
        }
    }
    
    /**
     * 发送预制皮重命令
     */
    private void sendPresetTareCommand(Scanner scanner) {
        System.out.println("发送预制皮重命令...");
        
        // 提示用户输入皮重值
        System.out.print("请输入皮重值 (格式如: 12.34 或直接回车使用默认值 0012.34): ");
        String input = scanner.nextLine().trim();
        
        String tareValue;
        if (input.isEmpty()) {
            // 使用默认值
            tareValue = "0012.34";
            System.out.println("使用默认皮重值: " + tareValue);
        } else {
            // 验证并格式化用户输入
            tareValue = formatTareValue(input);
            if (tareValue == null) {
                System.err.println("皮重值格式错误，请输入有效的数字 (如: 12.34)");
                return;
            }
            System.out.println("使用输入的皮重值: " + tareValue);
        }
        
        String command = "YARE=" + tareValue + " \r\n";
        
        System.out.println("发送命令: " + command.replace("\r\n", "[CRLF]"));
        
        if (sdk.sendCustomCommand(command.getBytes())) {
            System.out.println("预制皮重命令发送成功");
        } else {
            System.err.println("预制皮重命令发送失败");
        }
    }
    
    /**
     * 格式化皮重值为标准格式 (如: 12.34 -> 0012.34)
     */
    private String formatTareValue(String input) {
        try {
            // 解析输入的数字
            double value = Double.parseDouble(input);
            
            // 检查范围 (0-9999.99)
            if (value < 0 || value > 9999.99) {
                return null;
            }
            
            // 格式化为 XXXX.XX 格式
            return String.format("%07.2f", value);
            
        } catch (NumberFormatException e) {
            return null;
        }
    }
    
    /**
     * 发送自定义命令
     */
    private void sendCustomCommand(Scanner scanner) {
        System.out.print("请输入自定义命令: ");
        String command = scanner.nextLine();
        
        if (command.trim().isEmpty()) {
            System.err.println("命令不能为空");
            return;
        }
        
        // 如果命令没有以\r\n结尾，自动添加
        if (!command.endsWith("\r\n")) {
            command += "\r\n";
        }
        
        System.out.println("发送自定义命令: " + command.replace("\r\n", "[CRLF]"));
        
        if (sdk.sendCustomCommand(command.getBytes())) {
            System.out.println("自定义命令发送成功");
        } else {
            System.err.println("自定义命令发送失败");
        }
    }
    
    /**
     * 显示连接状态
     */
    private void showStatus() {
        System.out.println("\n=== 连接状态 ===");
        System.out.println("SDK初始化状态: " + (sdk.isInitialized() ? "已初始化" : "未初始化"));
        System.out.println("连接状态: " + (sdk.isConnected() ? "已连接" : "未连接"));
        
        String currentPort = sdk.getCurrentPortName();
        if (currentPort != null) {
            System.out.println("当前端口: " + currentPort);
        } else {
            System.out.println("当前端口: 无");
        }
        
        System.out.println("SDK版本: " + sdk.getVersion());
    }
    
    /**
     * 重新连接设备
     */
    private void reconnectDevice() {
        System.out.println("断开当前连接...");
        sdk.disconnect();
        
        System.out.println("重新连接设备...");
        connectToDevice();
    }
    
    /**
     * 清理资源
     */
    private void cleanup() {
        System.out.println("\n正在清理资源...");
        
        if (sdk != null) {
            sdk.release();
            System.out.println("SDK资源已释放");
        }
    }
    
    /**
     * 重量数据监听器实现
     */
    private static class WeightDataListenerImpl implements WeightDataListener {
        
        @Override
        public void onWeightDataReceived(WeightData data) {
            System.out.println("\n[重量数据] " + formatTimestamp(data.getTimestamp()));
            System.out.println("  重量值: " + data.getFormattedWeight());
            System.out.println("  数值: " + data.getWeight() + " " + data.getUnit());
            System.out.println("  状态: " + (data.getStabilityStatus() == WeightData.StabilityStatus.STABLE ? "稳定" : "不稳定"));
            System.out.println("  类型: " + getWeightTypeString(data.getWeightType()));
            System.out.println("  协议: " + getProtocolTypeString(data.getProtocolType()));
            System.out.println("  有效性: " + (data.isValidWeight() ? "有效" : "无效"));
            
            // 如果是VA协议，显示额外信息
            if (data.getProtocolType() == WeightData.ProtocolType.VA) {
                System.out.println("  地址: " + data.getAddress());
                System.out.println("  数据长度: " + data.getDataLength());
                if (data.hasTareWeight()) {
                    System.out.println("  皮重值: " + data.getTareWeight());
                }
            }
        }
        
        @Override
        public void onRawDataReceived(byte[] data) {
            String rawString = new String(data).replace("\r", "[CR]").replace("\n", "[LF]");
            System.out.println("\n[原始数据] " + rawString);
        }
        
        @Override
        public void onConnectionStatusChanged(boolean connected, String portPath) {
            System.out.println("\n[连接状态] " + (connected ? "设备已连接" : "设备已断开") + " - " + portPath);
        }
        
        @Override
        public void onError(int errorCode, String errorMessage) {
            System.err.println("\n[错误] " + getErrorDescription(errorCode) + " - " + errorMessage);
        }
        
        @Override
        public void onCommandResult(CommandType command, boolean success) {
            String commandName = getCommandTypeString(command);
            String result = success ? "成功" : "失败";
            System.out.println("\n[命令结果] " + commandName + " - " + result);
        }
        
        private String formatTimestamp(long timestamp) {
            return new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS")
                    .format(new java.util.Date(timestamp));
        }
        
        private String getWeightTypeString(WeightData.WeightType type) {
            switch (type) {
                case NET: return "净重";
                case GROSS: return "毛重";
                default: return "未知";
            }
        }
        
        private String getProtocolTypeString(WeightData.ProtocolType protocol) {
            switch (protocol) {
                case SHOUHENG: return "首衡协议";
                case VA: return "VA协议";
                default: return "未知协议";
            }
        }
        
        private String getCommandTypeString(CommandType command) {
            switch (command) {
                case ZERO: return "置零命令";
                case TARE: return "去皮命令";
                case XDRE: return "XDRE命令";
                case YARE: return "YARE命令";
                case PRESET_TARE: return "预制皮重命令";
                case CUSTOM: return "自定义命令";
                default: return "未知命令";
            }
        }
        
        private String getErrorDescription(int errorCode) {
            switch (errorCode) {
                case WeightDataListener.ErrorCode.CONNECTION_FAILED:
                    return "连接失败 - 请检查设备连接和串口设置";
                case WeightDataListener.ErrorCode.PARSE_DATA_FAILED:
                    return "数据解析失败 - 接收到的数据格式不正确";
                case WeightDataListener.ErrorCode.SEND_COMMAND_FAILED:
                    return "命令发送失败 - 请检查设备连接";
                case WeightDataListener.ErrorCode.SERIAL_PORT_NOT_FOUND:
                    return "串口未找到 - 请检查设备是否正确连接";
                case WeightDataListener.ErrorCode.PERMISSION_DENIED:
                    return "权限被拒绝 - 请检查串口访问权限";
                case WeightDataListener.ErrorCode.DEVICE_BUSY:
                    return "设备忙碌 - 设备正在被其他程序使用";
                case WeightDataListener.ErrorCode.TIMEOUT:
                    return "操作超时 - 设备响应超时";
                case WeightDataListener.ErrorCode.INVALID_PARAMETER:
                    return "无效参数 - 请检查输入参数";
                case WeightDataListener.ErrorCode.SDK_NOT_INITIALIZED:
                    return "SDK未初始化 - 请先调用initialize()方法";
                case WeightDataListener.ErrorCode.DATA_PARSE_ERROR:
                    return "数据解析错误 - 数据格式不符合协议规范";
                default:
                    return "未知错误: " + errorCode;
            }
        }
    }
}