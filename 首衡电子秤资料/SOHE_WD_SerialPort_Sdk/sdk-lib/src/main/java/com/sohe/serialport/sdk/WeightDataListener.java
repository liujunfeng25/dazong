package com.sohe.serialport.sdk;

/**
 * 重量数据监听器接口
 * 用于接收解析后的重量数据和状态通知
 */
public interface WeightDataListener {
    
    /**
     * 接收到新的重量数据
     * @param weightData 解析后的重量数据
     */
    void onWeightDataReceived(WeightData weightData);
    
    /**
     * 接收到原始数据（未解析或解析失败的数据）
     * @param rawData 原始字节数据
     */
    void onRawDataReceived(byte[] rawData);
    
    /**
     * 连接状态变化
     * @param isConnected 是否已连接
     * @param portPath 串口路径
     */
    void onConnectionStatusChanged(boolean isConnected, String portPath);
    
    /**
     * 发生错误
     * @param errorCode 错误代码
     * @param errorMessage 错误消息
     */
    void onError(int errorCode, String errorMessage);
    
    /**
     * 命令执行结果
     * @param command 执行的命令类型
     * @param success 是否执行成功
     */
    void onCommandResult(CommandType command, boolean success);
    
    /**
     * 命令类型枚举
     */
    enum CommandType {
        ZERO,       // 置零命令
        TARE,       // 去皮命令
        XDRE,       // XDRE命令
        YARE,       // YARE命令
        ZERO_TARE,  // 一键置零去皮命令
        PRESET_TARE,// 预制皮重命令
        CUSTOM      // 自定义命令
    }
    
    /**
     * 错误代码常量
     */
    class ErrorCode {
        public static final int UNKNOWN_ERROR = -1;
        public static final int CONNECTION_FAILED = 1001;
        public static final int PARSE_DATA_FAILED = 1002;
        public static final int SEND_COMMAND_FAILED = 1003;
        public static final int SERIAL_PORT_NOT_FOUND = 1004;
        public static final int PERMISSION_DENIED = 1005;
        public static final int DEVICE_BUSY = 1006;
        public static final int TIMEOUT = 1007;
        public static final int INVALID_PARAMETER = 1008;
        public static final int SDK_NOT_INITIALIZED = 1009;
        public static final int DATA_PARSE_ERROR = 1010;
    }
}