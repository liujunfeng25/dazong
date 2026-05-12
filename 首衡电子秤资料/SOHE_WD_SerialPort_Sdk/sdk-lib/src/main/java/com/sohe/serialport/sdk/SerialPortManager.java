package com.sohe.serialport.sdk;

import java.io.*;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/**
 * 串口通信管理类
 * 支持真实串口通信，使用JNI调用底层串口库
 */
public class SerialPortManager {
    
    private static final String TAG = "SerialPortManager";
    
    // 支持的串口路径前缀（Linux/Android）
    private static final List<String> LINUX_SERIAL_PORT_PREFIXES = Arrays.asList(
        "/dev/ttyZC",
        "/dev/ttyS",
        "/dev/ttyUSB",
        "/dev/ttyACM"
    );
    
    // Windows串口前缀
    private static final List<String> WINDOWS_SERIAL_PORT_PREFIXES = Arrays.asList(
        "COM"
    );
    
    // 常用波特率
    public static final int BAUD_RATE_9600 = 9600;
    public static final int BAUD_RATE_115200 = 115200;
    public static final int BAUD_RATE_38400 = 38400;
    public static final int BAUD_RATE_57600 = 57600;
    
    private String mSerialPortPath;
    private int mBaudRate;
    private boolean mIsConnected = false;
    private ExecutorService mExecutorService;
    private Future<?> mReadTask;
    private boolean mIsReading = false;
    private OnDataReceivedListener mDataListener;
    
    // 串口输入输出流
    private InputStream mInputStream;
    private OutputStream mOutputStream;
    
    // JNI native方法声明
    private native Object nativeOpenSerialPort(String path, int baudRate);
    private native void nativeCloseSerialPort(Object serialPort);
    private native int nativeReadSerialPort(Object serialPort, byte[] buffer);
    private native boolean nativeWriteSerialPort(Object serialPort, byte[] data);
    
    // 串口对象引用
    private Object mSerialPortObject;
    
    // JNI库加载状态
    private static boolean sJniLibraryLoaded = false;
    
    static {
        try {
            System.loadLibrary("serialport");
            sJniLibraryLoaded = true;
            System.out.println("JNI串口库加载成功");
        } catch (UnsatisfiedLinkError e) {
            sJniLibraryLoaded = false;
            System.err.println("无法加载串口JNI库: " + e.getMessage());
            System.err.println("将使用模拟模式运行");
        }
    }
    
    /**
     * 数据接收监听器
     */
    public interface OnDataReceivedListener {
        /**
         * 接收到数据
         * @param data 接收到的字节数据
         */
        void onDataReceived(byte[] data);
        
        /**
         * 发生错误
         * @param error 错误信息
         */
        void onError(String error);
    }
    
    /**
     * 串口信息类
     */
    public static class SerialPortInfo {
        private String path;
        private String displayName;
        
        public SerialPortInfo(String path) {
            this.path = path;
            this.displayName = generateDisplayName(path);
        }
        
        private String generateDisplayName(String path) {
            if (path.startsWith("/dev/ttyZC")) {
                return "ZC串口 (" + path + ")";
            } else if (path.startsWith("/dev/ttyS")) {
                return "标准串口 (" + path + ")";
            } else if (path.startsWith("/dev/ttyUSB")) {
                return "USB串口 (" + path + ")";
            } else if (path.startsWith("/dev/ttyACM")) {
                return "ACM串口 (" + path + ")";
            } else if (path.startsWith("COM")) {
                return "Windows串口 (" + path + ")";
            } else {
                return path;
            }
        }
        
        public String getPath() {
            return path;
        }
        
        public String getDisplayName() {
            return displayName;
        }
        
        @Override
        public String toString() {
            return displayName;
        }
    }
    
    /**
     * 构造函数
     * @param baudRate 波特率
     */
    public SerialPortManager(int baudRate) {
        this.mBaudRate = baudRate;
        this.mExecutorService = Executors.newSingleThreadExecutor();
    }
    
    /**
     * 设置数据接收监听器
     */
    public void setOnDataReceivedListener(OnDataReceivedListener listener) {
        this.mDataListener = listener;
    }
    
    /**
     * 自动检测并连接串口
     * @return 连接是否成功
     */
    public boolean connect() {
        String detectedPort = detectSerialPort();
        if (detectedPort != null) {
            return connect(detectedPort);
        }
        return false;
    }
    
    /**
     * 连接指定串口
     * @param portPath 串口路径
     * @return 连接是否成功
     */
    public boolean connect(String portPath) {
        try {
            // 检查串口是否可用
            if (!isPortAvailable(portPath)) {
                if (mDataListener != null) {
                    mDataListener.onError("串口不可用: " + portPath);
                }
                return false;
            }
            
            // 模拟打开串口（实际实现需要使用具体的串口库）
            boolean opened = openSerialPort(portPath, mBaudRate);
            if (!opened) {
                if (mDataListener != null) {
                    mDataListener.onError("无法打开串口: " + portPath);
                }
                return false;
            }
            
            mSerialPortPath = portPath;
            mIsConnected = true;
            
            // 启动数据读取线程
            startReadThread();
            
            return true;
        } catch (Exception e) {
            if (mDataListener != null) {
                mDataListener.onError("连接串口失败: " + e.getMessage());
            }
            return false;
        }
    }
    
    /**
     * 获取所有可用的串口列表
     * @return 可用串口路径列表
     */
    public List<String> getAvailableSerialPorts() {
        List<String> availablePorts = new ArrayList<>();
        
        // 根据操作系统选择不同的串口前缀
        List<String> prefixes = getSerialPortPrefixes();
        
        for (String prefix : prefixes) {
            if (prefix.equals("COM")) {
                // Windows COM端口
                for (int i = 1; i <= 20; i++) {
                    String portPath = prefix + i;
                    if (isPortAvailable(portPath)) {
                        availablePorts.add(portPath);
                    }
                }
            } else {
                // Linux/Unix设备文件
                for (int i = 0; i <= 10; i++) {
                    String portPath = prefix + i;
                    if (isPortAvailable(portPath)) {
                        availablePorts.add(portPath);
                    }
                }
            }
        }
        
        return availablePorts;
    }
    
    /**
     * 获取所有可用的串口信息列表
     * @return 可用串口信息列表
     */
    public List<SerialPortInfo> getAvailableSerialPortInfos() {
        List<SerialPortInfo> availablePortInfos = new ArrayList<>();
        List<String> availablePorts = getAvailableSerialPorts();
        
        for (String port : availablePorts) {
            availablePortInfos.add(new SerialPortInfo(port));
        }
        
        return availablePortInfos;
    }
    
    /**
     * 发送数据
     * @param data 要发送的字节数据
     * @return 发送是否成功
     */
    public boolean sendData(byte[] data) {
        if (!mIsConnected || mOutputStream == null) {
            if (mDataListener != null) {
                mDataListener.onError("串口未连接");
            }
            return false;
        }
        
        try {
            mOutputStream.write(data);
            mOutputStream.flush();
            return true;
        } catch (IOException e) {
            if (mDataListener != null) {
                mDataListener.onError("发送数据失败: " + e.getMessage());
            }
            return false;
        }
    }
    
    /**
     * 发送字符串数据
     * @param data 要发送的字符串
     * @return 发送是否成功
     */
    public boolean sendData(String data) {
        return sendData(data.getBytes());
    }
    
    /**
     * 发送置零指令
     */
    public boolean sendZeroCommand() {
        return sendData("ZERO\r\n".getBytes());
    }

    /**
     * 发送去皮指令
     */
    public boolean sendTareCommand() {
        return sendData("TARE\r\n".getBytes());
    }
    
    /**
     * 发送XDRE指令
     */
    public boolean sendXDRECommand() {
        return sendData("XDRE\r\n".getBytes());
    }
    
    /**
     * 发送YARE指令
     */
    public boolean sendYARECommand() {
        return sendData("YARE\r\n".getBytes());
    }
    
    /**
     * 发送一键置零去皮指令
     */
    public boolean sendZeroTareCommand() {
        return sendData("XDRE\r\n".getBytes());
    }
    
    /**
     * 发送预制皮重指令
     * @param tareValue 皮重值，格式如"0012.34"
     */
    public boolean sendPresetTareCommand(String tareValue) {
        String command = "YARE=" + tareValue + "\r\n";
        return sendData(command.getBytes());
    }
    
    /**
     * 断开串口连接
     */
    public void disconnect() {
        mIsReading = false;
        mIsConnected = false;
        
        // 停止读取线程
        if (mReadTask != null && !mReadTask.isDone()) {
            mReadTask.cancel(true);
        }
        
        try {
            if (mInputStream != null) {
                mInputStream.close();
                mInputStream = null;
            }
            
            if (mOutputStream != null) {
                mOutputStream.close();
                mOutputStream = null;
            }
            
            // 关闭串口（模拟实现）
            closeSerialPort();
            
        } catch (IOException e) {
            if (mDataListener != null) {
                mDataListener.onError("关闭串口失败: " + e.getMessage());
            }
        }
    }
    
    /**
     * 检查连接状态
     */
    public boolean isConnected() {
        return mIsConnected;
    }
    
    /**
     * 获取当前串口路径
     */
    public String getSerialPortPath() {
        return mSerialPortPath;
    }
    
    /**
     * 获取波特率
     */
    public int getBaudRate() {
        return mBaudRate;
    }
    
    /**
     * 释放资源
     */
    public void release() {
        disconnect();
        if (mExecutorService != null && !mExecutorService.isShutdown()) {
            mExecutorService.shutdown();
        }
    }
    
    // 私有方法
    
    /**
     * 自动检测可用的串口
     * @return 检测到的串口路径，如果没有则返回null
     */
    private String detectSerialPort() {
        List<String> availablePorts = getAvailableSerialPorts();
        return availablePorts.isEmpty() ? null : availablePorts.get(0);
    }
    
    /**
     * 根据操作系统获取串口前缀
     * @return 串口前缀列表
     */
    private List<String> getSerialPortPrefixes() {
        String osName = System.getProperty("os.name").toLowerCase();
        if (osName.contains("win")) {
            return WINDOWS_SERIAL_PORT_PREFIXES;
        } else {
            return LINUX_SERIAL_PORT_PREFIXES;
        }
    }
    
    /**
     * 检查串口是否可用
     * @param portPath 串口路径
     * @return 是否可用
     */
    private boolean isPortAvailable(String portPath) {
        // 模拟实现：检查串口文件是否存在
        // 实际实现需要使用具体的串口库来检测
        
        String osName = System.getProperty("os.name").toLowerCase();
        if (osName.contains("win")) {
            // Windows系统：模拟COM端口检测
            return portPath.matches("COM[1-9][0-9]?");
        } else {
            // Linux/Unix系统：检查设备文件
            File serialPortFile = new File(portPath);
            return serialPortFile.exists() && serialPortFile.canRead() && serialPortFile.canWrite();
        }
    }
    
    /**
     * 打开串口
     * @param portPath 串口路径
     * @param baudRate 波特率
     * @return 是否成功打开
     */
    private boolean openSerialPort(String portPath, int baudRate) {
        try {
            if (sJniLibraryLoaded) {
                // 使用JNI实现打开真实串口
                mSerialPortObject = nativeOpenSerialPort(portPath, baudRate);
                if (mSerialPortObject != null) {
                    System.out.println("真实串口打开成功: " + portPath);
                    // 创建真实的串口输入输出流
                    mInputStream = new SerialPortInputStream();
                    mOutputStream = new SerialPortOutputStream();
                    return true;
                } else {
                    System.err.println("JNI串口打开失败: " + portPath);
                    return false;
                }
            } else {
                // 回退到模拟实现
                System.out.println("使用模拟串口模式: " + portPath);
                mInputStream = new ByteArrayInputStream(generateTestData());
                mOutputStream = new ByteArrayOutputStream();
                return true;
            }
        } catch (Exception e) {
            System.err.println("打开串口异常: " + e.getMessage());
            return false;
        }
    }
    
    /**
     * 关闭串口
     */
    private void closeSerialPort() {
        if (sJniLibraryLoaded && mSerialPortObject != null) {
            // 使用JNI关闭真实串口
            nativeCloseSerialPort(mSerialPortObject);
            System.out.println("真实串口已关闭: " + mSerialPortPath);
            mSerialPortObject = null;
        } else {
            System.out.println("模拟串口已关闭: " + mSerialPortPath);
        }
        mSerialPortPath = null;
    }
    
    /**
     * 启动数据读取线程
     */
    private void startReadThread() {
        mIsReading = true;
        mReadTask = mExecutorService.submit(new Runnable() {
            @Override
            public void run() {
                byte[] buffer = new byte[1024];
                while (mIsReading && mIsConnected) {
                    try {
                        if (mInputStream != null && mInputStream.available() > 0) {
                            int bytesRead = mInputStream.read(buffer);
                            if (bytesRead > 0) {
                                byte[] data = new byte[bytesRead];
                                System.arraycopy(buffer, 0, data, 0, bytesRead);
                                
                                // 直接发送完整数据包（JNI层已确保数据完整性）
                                if (mDataListener != null) {
                                    mDataListener.onDataReceived(data);
                                }
                            }
                        }
                        
                        // 避免CPU占用过高
                        Thread.sleep(10);
                        
                    } catch (IOException e) {
                        if (mIsReading && mDataListener != null) {
                            mDataListener.onError("读取数据失败: " + e.getMessage());
                        }
                        break;
                    } catch (InterruptedException e) {
                        // Thread interrupted, exit loop
                        break;
                    }
                }
            }
        });
    }
    
    /**
     * 处理接收到的数据，支持数据拼接
     */
    /**
     * 生成测试数据（模拟串口数据）
     * @return 测试数据字节数组
     */
    private byte[] generateTestData() {
        // 模拟一些测试数据
        String[] testData = {
            "sn0001.234kg\r\n",
            "VA,01,19,S,N,+ 1.568 kg\r\n",
            "sw0002.100kg\r\n",
            "VA,01,19,U,G,- 0.125 kg\r\n"
        };
        
        StringBuilder sb = new StringBuilder();
        for (String data : testData) {
            sb.append(data);
        }
        
        return sb.toString().getBytes();
    }
    
    /**
     * 串口输入流实现
     */
    private class SerialPortInputStream extends InputStream {
        @Override
        public int read() throws IOException {
            byte[] buffer = new byte[1];
            int result = read(buffer, 0, 1);
            return result == 1 ? (buffer[0] & 0xFF) : -1;
        }
        
        @Override
        public int read(byte[] buffer, int offset, int length) throws IOException {
            if (mSerialPortObject == null) {
                return -1;
            }
            
            byte[] tempBuffer = new byte[length];
            int bytesRead = nativeReadSerialPort(mSerialPortObject, tempBuffer);
            if (bytesRead > 0) {
                System.arraycopy(tempBuffer, 0, buffer, offset, bytesRead);
            }
            return bytesRead;
        }
        
        @Override
        public int available() throws IOException {
            // 简化实现，假设总是有数据可读
            return mSerialPortObject != null ? 1 : 0;
        }
    }
    
    /**
     * 串口输出流实现
     */
    private class SerialPortOutputStream extends OutputStream {
        @Override
        public void write(int b) throws IOException {
            write(new byte[]{(byte) b});
        }
        
        @Override
        public void write(byte[] data) throws IOException {
            if (mSerialPortObject == null) {
                throw new IOException("串口未打开");
            }
            
            boolean success = nativeWriteSerialPort(mSerialPortObject, data);
            if (!success) {
                throw new IOException("串口写入失败");
            }
        }
        
        @Override
        public void flush() throws IOException {
            // JNI实现中处理flush
        }
    }
}