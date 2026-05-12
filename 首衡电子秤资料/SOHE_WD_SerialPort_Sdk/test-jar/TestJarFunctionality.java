import com.sohe.serialport.sdk.*;
import java.util.List;

/**
 * JAR包功能验证测试
 * 
 * 这个测试程序用于验证生成的JAR包是否包含所有必要的类，
 * 以及这些类是否能够正确实例化和使用。
 */
public class TestJarFunctionality {
    
    public static void main(String[] args) {
        System.out.println("=== SOHE SerialPort SDK JAR包功能验证 ===");
        
        TestJarFunctionality test = new TestJarFunctionality();
        
        boolean allTestsPassed = true;
        
        // 测试各个类的实例化
        allTestsPassed &= test.testSoheWeightSDK();
        allTestsPassed &= test.testWeightData();
        allTestsPassed &= test.testDataParser();
        allTestsPassed &= test.testSerialPortManager();
        allTestsPassed &= test.testWeightDataListener();
        
        // 输出测试结果
        System.out.println("\n=== 测试结果 ===");
        if (allTestsPassed) {
            System.out.println("✓ 所有测试通过！JAR包功能正常。");
        } else {
            System.err.println("✗ 部分测试失败！JAR包可能存在问题。");
        }
    }
    
    /**
     * 测试SoheWeightSDK类
     */
    private boolean testSoheWeightSDK() {
        System.out.println("\n--- 测试 SoheWeightSDK 类 ---");
        
        try {
            // 测试创建实例
            SoheWeightSDK sdk = SoheWeightSDK.createDefault();
            if (sdk == null) {
                System.err.println("✗ 无法创建SoheWeightSDK实例");
                return false;
            }
            System.out.println("✓ SoheWeightSDK实例创建成功");
            
            // 测试获取版本
            String version = sdk.getVersion();
            if (version == null || version.isEmpty()) {
                System.err.println("✗ 无法获取SDK版本");
                return false;
            }
            System.out.println("✓ SDK版本: " + version);
            
            // 测试配置类
            SoheWeightSDK.Config config = new SoheWeightSDK.Config();
            config.setBaudRate(9600);
            config.setAutoConnect(false);
            config.setPreferredPort("COM1");
            
            if (config.getBaudRate() != 9600) {
                System.err.println("✗ Config类setBaudRate/getBaudRate方法异常");
                return false;
            }
            System.out.println("✓ Config类功能正常");
            
            // 测试初始化状态
            if (sdk.isInitialized()) {
                System.out.println("✓ SDK已初始化");
            } else {
                System.out.println("✓ SDK未初始化");
            }
            
            // 测试连接状态
            if (sdk.isConnected()) {
                System.out.println("✓ SDK已连接");
            } else {
                System.out.println("✓ SDK未连接");
            }
            
            // 测试获取可用端口（未初始化时应返回空列表）
            List<String> ports = sdk.getAvailableSerialPorts();
            if (ports == null) {
                System.err.println("✗ getAvailableSerialPorts返回null");
                return false;
            }
            System.out.println("✓ getAvailableSerialPorts方法正常");
            
            // 清理资源
            sdk.release();
            System.out.println("✓ SDK资源释放成功");
            
            return true;
            
        } catch (Exception e) {
            System.err.println("✗ SoheWeightSDK测试异常: " + e.getMessage());
            e.printStackTrace();
            return false;
        }
    }
    
    /**
     * 测试WeightData类
     */
    private boolean testWeightData() {
        System.out.println("\n--- 测试 WeightData 类 ---");
        
        try {
            // 测试创建WeightData实例
            WeightData data = new WeightData();
            data.setWeight(1.234);
            data.setUnit("kg");
            data.setStability(WeightData.StabilityStatus.STABLE);
            data.setWeightType(WeightData.WeightType.NET);
            data.setProtocolType(WeightData.ProtocolType.SHOUHENG);
            data.setRawData("sn0001.234kg\r\n");
            data.setPositive(true);
            
            if (data == null) {
                System.err.println("✗ 无法创建WeightData实例");
                return false;
            }
            System.out.println("✓ WeightData实例创建成功");
            
            // 测试getter方法
            if (Math.abs(data.getWeight() - 1.234) > 0.001) {
                System.err.println("✗ getWeight方法异常");
                return false;
            }
            System.out.println("✓ getWeight方法正常: " + data.getWeight());
            
            if (!"kg".equals(data.getUnit())) {
                System.err.println("✗ getUnit方法异常");
                return false;
            }
            System.out.println("✓ getUnit方法正常: " + data.getUnit());
            
            if (!data.isStable()) {
                System.err.println("✗ isStable方法异常");
                return false;
            }
            System.out.println("✓ isStable方法正常: " + data.isStable());
            
            // 测试稳定性检查
            if (!data.isStable()) {
                System.err.println("✗ isStable方法异常");
                return false;
            }
            System.out.println("✓ isStable方法正常: " + data.isStable());
            
            // 测试格式化方法
            String formatted = data.getFormattedWeight();
            if (formatted == null || formatted.isEmpty()) {
                System.err.println("✗ getFormattedWeight方法异常");
                return false;
            }
            System.out.println("✓ getFormattedWeight方法正常: " + formatted);
            
            // 测试toString方法
            String toString = data.toString();
            if (toString == null || toString.isEmpty()) {
                System.err.println("✗ toString方法异常");
                return false;
            }
            System.out.println("✓ toString方法正常");
            
            return true;
            
        } catch (Exception e) {
            System.err.println("✗ WeightData测试异常: " + e.getMessage());
            e.printStackTrace();
            return false;
        }
    }
    
    /**
     * 测试DataParser类
     */
    private boolean testDataParser() {
        System.out.println("\n--- 测试 DataParser 类 ---");
        
        try {
            // 测试创建DataParser实例
            DataParser parser = new DataParser();
            if (parser == null) {
                System.err.println("✗ 无法创建DataParser实例");
                return false;
            }
            System.out.println("✓ DataParser实例创建成功");
            
            // 测试解析首衡协议数据
            String shouhengData = "sn0001.234kg\r\n";
            WeightData result1 = parser.parseData(shouhengData.getBytes());
            if (result1 == null) {
                System.err.println("✗ 首衡协议数据解析失败");
                return false;
            }
            System.out.println("✓ 首衡协议数据解析成功: " + result1.getFormattedWeight());
            
            // 测试解析VA协议数据
            String vaData = "VA,01,19,S,N,+ 2.567 kg\r\n";
            WeightData result2 = parser.parseData(vaData.getBytes());
            if (result2 == null) {
                System.err.println("✗ VA协议数据解析失败");
                return false;
            }
            System.out.println("✓ VA协议数据解析成功: " + result2.getFormattedWeight());
            
            // 测试解析无效数据
            String invalidData = "invalid data format";
            WeightData result3 = parser.parseData(invalidData.getBytes());
            if (result3 != null) {
                System.err.println("✗ 无效数据解析应该返回null");
                return false;
            }
            System.out.println("✓ 无效数据处理正常");
            
            // 测试null数据
            WeightData result4 = parser.parseData(null);
            if (result4 != null) {
                System.err.println("✗ null数据解析应该返回null");
                return false;
            }
            System.out.println("✓ null数据处理正常");
            
            return true;
            
        } catch (Exception e) {
            System.err.println("✗ DataParser测试异常: " + e.getMessage());
            e.printStackTrace();
            return false;
        }
    }
    
    /**
     * 测试SerialPortManager类
     */
    private boolean testSerialPortManager() {
        System.out.println("\n--- 测试 SerialPortManager 类 ---");
        
        try {
            // 测试创建SerialPortManager实例
            SerialPortManager manager = new SerialPortManager(9600);
            if (manager == null) {
                System.err.println("✗ 无法创建SerialPortManager实例");
                return false;
            }
            System.out.println("✓ SerialPortManager实例创建成功");
            
            // 测试获取可用端口
            List<SerialPortManager.SerialPortInfo> ports = manager.getAvailableSerialPortInfos();
            if (ports == null) {
                System.err.println("✗ getAvailableSerialPortInfos返回null");
                return false;
            }
            System.out.println("✓ getAvailableSerialPortInfos方法正常，找到 " + ports.size() + " 个端口");
            
            // 测试连接状态
            if (manager.isConnected()) {
                System.err.println("✗ 初始连接状态应该为false");
                return false;
            }
            System.out.println("✓ 初始连接状态正常");
            
            // 测试端口信息
            if (!ports.isEmpty()) {
                SerialPortManager.SerialPortInfo portInfo = ports.get(0);
                String portPath = portInfo.getPath();
                String displayName = portInfo.getDisplayName();
                
                if (portPath == null || portPath.isEmpty()) {
                    System.err.println("✗ 端口路径为空");
                    return false;
                }
                
                if (displayName == null) {
                    System.err.println("✗ 端口显示名称为null");
                    return false;
                }
                
                System.out.println("✓ 端口信息正常: " + portPath + " - " + displayName);
                
                // 测试toString方法
                String toString = portInfo.toString();
                if (toString == null || toString.isEmpty()) {
                    System.err.println("✗ SerialPortInfo.toString方法异常");
                    return false;
                }
                System.out.println("✓ SerialPortInfo.toString方法正常");
            }
            
            return true;
            
        } catch (Exception e) {
            System.err.println("✗ SerialPortManager测试异常: " + e.getMessage());
            e.printStackTrace();
            return false;
        }
    }
    
    /**
     * 测试WeightDataListener接口
     */
    private boolean testWeightDataListener() {
        System.out.println("\n--- 测试 WeightDataListener 接口 ---");
        
        try {
            // 测试创建监听器实现
            WeightDataListener listener = new TestListener();
            if (listener == null) {
                System.err.println("✗ 无法创建WeightDataListener实现");
                return false;
            }
            System.out.println("✓ WeightDataListener实现创建成功");
            
            // 测试枚举类型
            WeightDataListener.CommandType[] commands = WeightDataListener.CommandType.values();
            if (commands.length < 3) {
                System.err.println("✗ CommandType枚举值不完整");
                return false;
            }
            System.out.println("✓ CommandType枚举正常，包含 " + commands.length + " 个值");
            
            // 测试错误代码常量
            int[] errorCodes = {
                WeightDataListener.ErrorCode.UNKNOWN_ERROR,
                WeightDataListener.ErrorCode.CONNECTION_FAILED,
                WeightDataListener.ErrorCode.PARSE_DATA_FAILED,
                WeightDataListener.ErrorCode.SDK_NOT_INITIALIZED
            };
            
            for (int errorCode : errorCodes) {
                // 错误代码应该是有效的整数
            }
            System.out.println("✓ ErrorCode常量正常");
            
            // 测试回调方法（不会抛出异常）
            WeightData testData = new WeightData();
            testData.setWeight(1.0);
            testData.setUnit("kg");
            testData.setStability(WeightData.StabilityStatus.STABLE);
            testData.setWeightType(WeightData.WeightType.NET);
            testData.setProtocolType(WeightData.ProtocolType.SHOUHENG);
            testData.setRawData("test");
            
            listener.onWeightDataReceived(testData);
            listener.onRawDataReceived("test".getBytes());
            listener.onConnectionStatusChanged(true, "COM1");
            listener.onError(WeightDataListener.ErrorCode.UNKNOWN_ERROR, "Test error");
            listener.onCommandResult(WeightDataListener.CommandType.ZERO, true);
            
            System.out.println("✓ 所有回调方法调用正常");
            
            return true;
            
        } catch (Exception e) {
            System.err.println("✗ WeightDataListener测试异常: " + e.getMessage());
            e.printStackTrace();
            return false;
        }
    }
    
    /**
     * 测试用的监听器实现
     */
    private static class TestListener implements WeightDataListener {
        @Override
        public void onWeightDataReceived(WeightData data) {
            // 测试实现，不做任何操作
        }
        
        @Override
        public void onRawDataReceived(byte[] data) {
            // 测试实现，不做任何操作
        }
        
        @Override
        public void onConnectionStatusChanged(boolean connected, String portPath) {
            // 测试实现，不做任何操作
        }
        
        @Override
        public void onError(int errorCode, String errorMessage) {
            // 测试实现，不做任何操作
        }
        
        @Override
        public void onCommandResult(CommandType command, boolean success) {
            // 测试实现，不做任何操作
        }
    }
}