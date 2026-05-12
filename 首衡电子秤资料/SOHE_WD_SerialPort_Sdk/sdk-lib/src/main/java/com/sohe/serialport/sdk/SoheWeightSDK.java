package com.sohe.serialport.sdk;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 首衡重量SDK主入口类
 * 整合串口通信和数据解析功能，提供完整的SDK API
 */
public class SoheWeightSDK {
    private static final String TAG = "SoheWeightSDK";
    private static final String SDK_VERSION = "1.0.0";
    
    private SerialPortManager mSerialPortManager;
    private DataParser mDataParser;
    private WeightDataListener mWeightDataListener;
    private ExecutorService mExecutorService;
    private boolean mIsInitialized = false;
    
    /**
     * SDK初始化配置
     */
    public static class Config {
        private int baudRate = SerialPortManager.BAUD_RATE_9600;
        private boolean autoConnect = true;
        private String preferredPort = null;
        
        public Config setBaudRate(int baudRate) {
            this.baudRate = baudRate;
            return this;
        }
        
        public Config setAutoConnect(boolean autoConnect) {
            this.autoConnect = autoConnect;
            return this;
        }
        
        public Config setPreferredPort(String port) {
            this.preferredPort = port;
            return this;
        }
        
        public int getBaudRate() {
            return baudRate;
        }
        
        public boolean isAutoConnect() {
            return autoConnect;
        }
        
        public String getPreferredPort() {
            return preferredPort;
        }
    }
    
    /**
     * 构造函数
     */
    public SoheWeightSDK() {
        mExecutorService = Executors.newCachedThreadPool();
    }
    
    /**
     * 初始化SDK
     * @param config 初始化配置
     * @return 初始化是否成功
     */
    public boolean initialize(Config config) {
        try {
            if (mIsInitialized) {
                return true;
            }
            
            // 创建串口管理器
            mSerialPortManager = new SerialPortManager(config.getBaudRate());
            
            // 创建数据解析器
            mDataParser = new DataParser();
            
            // 设置串口数据接收监听器
            mSerialPortManager.setOnDataReceivedListener(new SerialPortManager.OnDataReceivedListener() {
                @Override
                public void onDataReceived(byte[] data) {
                    handleReceivedData(data);
                }
                
                @Override
                public void onError(String error) {
                    if (mWeightDataListener != null) {
                mWeightDataListener.onError(WeightDataListener.ErrorCode.CONNECTION_FAILED, error);
            }
                }
            });
            
            mIsInitialized = true;
            
            // 自动连接
            if (config.isAutoConnect()) {
                if (config.getPreferredPort() != null) {
                    connect(config.getPreferredPort());
                } else {
                    connect();
                }
            }
            
            return true;
        } catch (Exception e) {
            if (mWeightDataListener != null) {
                mWeightDataListener.onError(WeightDataListener.ErrorCode.SDK_NOT_INITIALIZED, 
                    "SDK初始化失败: " + e.getMessage());
            }
            return false;
        }
    }
    
    /**
     * 使用默认配置初始化SDK
     * @return 初始化是否成功
     */
    public boolean initialize() {
        return initialize(new Config());
    }
    
    /**
     * 设置重量数据监听器
     * @param listener 监听器
     */
    public void setWeightDataListener(WeightDataListener listener) {
        this.mWeightDataListener = listener;
    }
    
    /**
     * 自动检测并连接串口
     * @return 连接是否成功
     */
    public boolean connect() {
        if (!mIsInitialized) {
            if (mWeightDataListener != null) {
                mWeightDataListener.onError(WeightDataListener.ErrorCode.SDK_NOT_INITIALIZED, "SDK未初始化");
            }
            return false;
        }
        
        boolean connected = mSerialPortManager.connect();
        if (connected && mWeightDataListener != null) {
            mWeightDataListener.onConnectionStatusChanged(true, mSerialPortManager.getSerialPortPath());
        }
        return connected;
    }
    
    /**
     * 连接指定串口
     * @param portPath 串口路径
     * @return 连接是否成功
     */
    public boolean connect(String portPath) {
        if (!mIsInitialized) {
            if (mWeightDataListener != null) {
                mWeightDataListener.onError(WeightDataListener.ErrorCode.SDK_NOT_INITIALIZED, "SDK未初始化");
            }
            return false;
        }
        
        boolean connected = mSerialPortManager.connect(portPath);
        if (connected && mWeightDataListener != null) {
            mWeightDataListener.onConnectionStatusChanged(true, portPath);
        }
        return connected;
    }
    
    /**
     * 断开连接
     */
    public void disconnect() {
        if (mSerialPortManager != null) {
            String portPath = mSerialPortManager.getSerialPortPath();
            mSerialPortManager.disconnect();
            
            if (mWeightDataListener != null) {
                mWeightDataListener.onConnectionStatusChanged(false, portPath);
            }
        }
    }
    
    /**
     * 检查连接状态
     * @return 是否已连接
     */
    public boolean isConnected() {
        return mSerialPortManager != null && mSerialPortManager.isConnected();
    }
    
    /**
     * 获取当前连接的串口路径
     * @return 串口路径，未连接时返回null
     */
    public String getCurrentPortName() {
        return getCurrentPortPath();
    }
    
    /**
     * 获取当前连接的串口路径
     * @return 串口路径，未连接时返回null
     */
    public String getCurrentPortPath() {
        return mSerialPortManager != null ? mSerialPortManager.getSerialPortPath() : null;
    }
    
    /**
     * 获取可用串口列表
     * @return 串口路径列表
     */
    public List<String> getAvailablePorts() {
        return getAvailableSerialPorts();
    }
    
    /**
     * 获取可用串口列表
     * @return 串口路径列表
     */
    public List<String> getAvailableSerialPorts() {
        if (mSerialPortManager != null) {
            return mSerialPortManager.getAvailableSerialPorts();
        }
        return null;
    }
    
    /**
     * 获取所有可用的串口信息列表
     * @return 可用串口信息列表
     */
    public List<SerialPortManager.SerialPortInfo> getAvailableSerialPortInfos() {
        if (mSerialPortManager != null) {
            return mSerialPortManager.getAvailableSerialPortInfos();
        }
        return null;
    }
    
    /**
     * 发送置零指令
     * @return 发送是否成功
     */
    public boolean sendZeroCommand() {
        if (!isConnected()) {
            if (mWeightDataListener != null) {
                mWeightDataListener.onError(WeightDataListener.ErrorCode.CONNECTION_FAILED, "设备未连接");
            }
            return false;
        }
        
        boolean success = mSerialPortManager.sendZeroCommand();
        if (mWeightDataListener != null) {
            mWeightDataListener.onCommandResult(WeightDataListener.CommandType.ZERO, success);
        }
        return success;
    }
    
    /**
     * 发送去皮指令
     * @return 发送是否成功
     */
    public boolean sendTareCommand() {
        if (!isConnected()) {
            if (mWeightDataListener != null) {
                mWeightDataListener.onError(WeightDataListener.ErrorCode.CONNECTION_FAILED, "设备未连接");
            }
            return false;
        }
        
        boolean success = mSerialPortManager.sendTareCommand();
        if (mWeightDataListener != null) {
            mWeightDataListener.onCommandResult(WeightDataListener.CommandType.TARE, success);
        }
        return success;
    }
    
    /**
     * 发送XDRE指令
     * @return 发送是否成功
     */
    public boolean sendXDRECommand() {
        if (!isConnected()) {
            if (mWeightDataListener != null) {
                mWeightDataListener.onError(WeightDataListener.ErrorCode.CONNECTION_FAILED, "设备未连接");
            }
            return false;
        }
        
        boolean success = mSerialPortManager.sendXDRECommand();
        if (mWeightDataListener != null) {
            mWeightDataListener.onCommandResult(WeightDataListener.CommandType.XDRE, success);
        }
        return success;
    }
    
    /**
     * 发送YARE指令
     * @return 发送是否成功
     */
    public boolean sendYARECommand() {
        if (!isConnected()) {
            if (mWeightDataListener != null) {
                mWeightDataListener.onError(WeightDataListener.ErrorCode.CONNECTION_FAILED, "设备未连接");
            }
            return false;
        }
        
        boolean success = mSerialPortManager.sendYARECommand();
        if (mWeightDataListener != null) {
            mWeightDataListener.onCommandResult(WeightDataListener.CommandType.YARE, success);
        }
        return success;
    }
    
    /**
     * 发送一键置零去皮指令
     */
    public boolean sendZeroTareCommand() {
        return mSerialPortManager.sendZeroTareCommand();
    }
    
    /**
     * 发送预制皮重指令
     * @param tareValue 皮重值，格式如"0012.34"
     */
    public boolean sendPresetTareCommand(String tareValue) {
        return mSerialPortManager.sendPresetTareCommand(tareValue);
    }
    
    /**
     * 发送自定义指令
     * @param command 指令字节数组
     * @return 发送是否成功
     */
    public boolean sendCustomCommand(byte[] command) {
        if (!isConnected()) {
            if (mWeightDataListener != null) {
                mWeightDataListener.onError(WeightDataListener.ErrorCode.CONNECTION_FAILED, "设备未连接");
            }
            return false;
        }
        
        boolean success = mSerialPortManager.sendData(command);
        if (mWeightDataListener != null) {
            mWeightDataListener.onCommandResult(WeightDataListener.CommandType.CUSTOM, success);
        }
        return success;
    }
    
    /**
     * 发送自定义字符串指令
     * @param command 指令字符串
     * @return 发送是否成功
     */
    public boolean sendCustomCommand(String command) {
        return sendCustomCommand(command.getBytes());
    }
    
    /**
     * 获取SDK版本
     * @return SDK版本号
     */
    public String getVersion() {
        return SDK_VERSION;
    }
    
    /**
     * 获取当前波特率
     * @return 波特率
     */
    public int getBaudRate() {
        return mSerialPortManager != null ? mSerialPortManager.getBaudRate() : 0;
    }
    
    /**
     * 检查SDK是否已初始化
     * @return 是否已初始化
     */
    public boolean isInitialized() {
        return mIsInitialized;
    }
    
    /**
     * 释放SDK资源
     */
    public void release() {
        disconnect();
        
        if (mSerialPortManager != null) {
            mSerialPortManager.release();
            mSerialPortManager = null;
        }
        
        if (mExecutorService != null && !mExecutorService.isShutdown()) {
            mExecutorService.shutdown();
        }
        
        mDataParser = null;
        mWeightDataListener = null;
        mIsInitialized = false;
    }
    
    /**
     * 处理接收到的原始数据
     * @param data 原始字节数据
     */
    private void handleReceivedData(final byte[] data) {
        if (mExecutorService != null && !mExecutorService.isShutdown()) {
            mExecutorService.execute(new Runnable() {
                @Override
                public void run() {
                    try {
                        // 通知原始数据接收
                        if (mWeightDataListener != null) {
                            mWeightDataListener.onRawDataReceived(data);
                        }
                        
                        // 解析数据
                        if (mDataParser != null) {
                            WeightData weightData = mDataParser.parseData(data);
                            if (weightData != null && mWeightDataListener != null) {
                                mWeightDataListener.onWeightDataReceived(weightData);
                            }
                        }
                    } catch (Exception e) {
                        if (mWeightDataListener != null) {
                            mWeightDataListener.onError(WeightDataListener.ErrorCode.PARSE_DATA_FAILED, 
                                "数据解析失败: " + e.getMessage());
                        }
                    }
                }
            });
        }
    }
    
    /**
     * 创建默认配置的SDK实例
     * @return SDK实例
     */
    public static SoheWeightSDK createDefault() {
        SoheWeightSDK sdk = new SoheWeightSDK();
        sdk.initialize();
        return sdk;
    }
    
    /**
     * 创建指定配置的SDK实例
     * @param config 配置
     * @return SDK实例
     */
    public static SoheWeightSDK create(Config config) {
        SoheWeightSDK sdk = new SoheWeightSDK();
        sdk.initialize(config);
        return sdk;
    }
}