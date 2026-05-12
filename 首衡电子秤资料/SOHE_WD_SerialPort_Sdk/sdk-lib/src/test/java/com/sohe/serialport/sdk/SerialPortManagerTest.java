package com.sohe.serialport.sdk;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/**
 * SerialPortManager类的单元测试
 */
public class SerialPortManagerTest {
    
    private SerialPortManager manager;
    private TestDataReceivedListener listener;
    
    @BeforeEach
    public void setUp() {
        manager = new SerialPortManager();
        listener = new TestDataReceivedListener();
    }
    
    @AfterEach
    public void tearDown() {
        if (manager != null && manager.isConnected()) {
            manager.disconnect();
        }
    }
    
    @Test
    public void testGetAvailablePorts() {
        // 测试获取可用串口列表
        List<SerialPortManager.SerialPortInfo> ports = manager.getAvailablePorts();
        
        assertNotNull(ports);
        // 模拟环境应该至少有一个端口
        assertTrue(ports.size() > 0);
        
        // 验证端口信息的完整性
        for (SerialPortManager.SerialPortInfo port : ports) {
            assertNotNull(port.getPortName());
            assertNotNull(port.getDescription());
            assertFalse(port.getPortName().isEmpty());
        }
    }
    
    @Test
    public void testConnectToValidPort() {
        // 测试连接到有效端口
        List<SerialPortManager.SerialPortInfo> ports = manager.getAvailablePorts();
        assertFalse(ports.isEmpty());
        
        String portName = ports.get(0).getPortName();
        boolean result = manager.connect(portName, 9600);
        
        assertTrue(result);
        assertTrue(manager.isConnected());
        assertEquals(portName, manager.getCurrentPortName());
        assertEquals(9600, manager.getCurrentBaudRate());
    }
    
    @Test
    public void testConnectToInvalidPort() {
        // 测试连接到无效端口
        boolean result = manager.connect("INVALID_PORT", 9600);
        
        assertFalse(result);
        assertFalse(manager.isConnected());
        assertNull(manager.getCurrentPortName());
        assertEquals(0, manager.getCurrentBaudRate());
    }
    
    @Test
    public void testConnectWithInvalidBaudRate() {
        // 测试使用无效波特率连接
        List<SerialPortManager.SerialPortInfo> ports = manager.getAvailablePorts();
        assertFalse(ports.isEmpty());
        
        String portName = ports.get(0).getPortName();
        boolean result = manager.connect(portName, -1);
        
        assertFalse(result);
        assertFalse(manager.isConnected());
    }
    
    @Test
    public void testDisconnect() {
        // 测试断开连接
        List<SerialPortManager.SerialPortInfo> ports = manager.getAvailablePorts();
        String portName = ports.get(0).getPortName();
        
        // 先连接
        assertTrue(manager.connect(portName, 9600));
        assertTrue(manager.isConnected());
        
        // 然后断开
        manager.disconnect();
        assertFalse(manager.isConnected());
        assertNull(manager.getCurrentPortName());
        assertEquals(0, manager.getCurrentBaudRate());
    }
    
    @Test
    public void testDisconnectWhenNotConnected() {
        // 测试在未连接状态下断开连接
        assertFalse(manager.isConnected());
        
        // 应该不会抛出异常
        assertDoesNotThrow(() -> manager.disconnect());
        
        assertFalse(manager.isConnected());
    }
    
    @Test
    public void testSendDataWhenConnected() throws InterruptedException {
        // 测试在连接状态下发送数据
        List<SerialPortManager.SerialPortInfo> ports = manager.getAvailablePorts();
        String portName = ports.get(0).getPortName();
        
        assertTrue(manager.connect(portName, 9600));
        manager.setOnDataReceivedListener(listener);
        
        String testData = "TEST_COMMAND\r\n";
        boolean result = manager.sendData(testData.getBytes());
        
        assertTrue(result);
        
        // 等待一段时间，看是否有回显数据
        Thread.sleep(100);
    }
    
    @Test
    public void testSendDataWhenNotConnected() {
        // 测试在未连接状态下发送数据
        assertFalse(manager.isConnected());
        
        String testData = "TEST_COMMAND\r\n";
        boolean result = manager.sendData(testData.getBytes());
        
        assertFalse(result);
    }
    
    @Test
    public void testSendNullData() {
        // 测试发送null数据
        List<SerialPortManager.SerialPortInfo> ports = manager.getAvailablePorts();
        String portName = ports.get(0).getPortName();
        
        assertTrue(manager.connect(portName, 9600));
        
        boolean result = manager.sendData(null);
        assertFalse(result);
    }
    
    @Test
    public void testSendEmptyData() {
        // 测试发送空数据
        List<SerialPortManager.SerialPortInfo> ports = manager.getAvailablePorts();
        String portName = ports.get(0).getPortName();
        
        assertTrue(manager.connect(portName, 9600));
        
        boolean result = manager.sendData(new byte[0]);
        assertFalse(result);
    }
    
    @Test
    public void testDataReceivedListener() throws InterruptedException {
        // 测试数据接收监听器
        List<SerialPortManager.SerialPortInfo> ports = manager.getAvailablePorts();
        String portName = ports.get(0).getPortName();
        
        assertTrue(manager.connect(portName, 9600));
        manager.setOnDataReceivedListener(listener);
        
        // 发送数据触发模拟接收
        String testData = "sn0001.234kg\r\n";
        manager.sendData(testData.getBytes());
        
        // 等待数据接收
        boolean received = listener.waitForData(1000);
        assertTrue(received, "Should receive data within timeout");
        
        byte[] receivedData = listener.getLastReceivedData();
        assertNotNull(receivedData);
        assertTrue(receivedData.length > 0);
    }
    
    @Test
    public void testMultipleConnections() {
        // 测试多次连接
        List<SerialPortManager.SerialPortInfo> ports = manager.getAvailablePorts();
        String portName = ports.get(0).getPortName();
        
        // 第一次连接
        assertTrue(manager.connect(portName, 9600));
        assertTrue(manager.isConnected());
        
        // 再次连接同一个端口（应该先断开再连接）
        assertTrue(manager.connect(portName, 19200));
        assertTrue(manager.isConnected());
        assertEquals(19200, manager.getCurrentBaudRate());
    }
    
    @Test
    public void testConnectionWithDifferentBaudRates() {
        // 测试不同波特率的连接
        List<SerialPortManager.SerialPortInfo> ports = manager.getAvailablePorts();
        String portName = ports.get(0).getPortName();
        
        int[] baudRates = {9600, 19200, 38400, 57600, 115200};
        
        for (int baudRate : baudRates) {
            assertTrue(manager.connect(portName, baudRate), 
                      "Failed to connect with baud rate: " + baudRate);
            assertTrue(manager.isConnected());
            assertEquals(baudRate, manager.getCurrentBaudRate());
            
            manager.disconnect();
            assertFalse(manager.isConnected());
        }
    }
    
    @Test
    public void testSerialPortInfo() {
        // 测试SerialPortInfo类
        List<SerialPortManager.SerialPortInfo> ports = manager.getAvailablePorts();
        assertFalse(ports.isEmpty());
        
        SerialPortManager.SerialPortInfo port = ports.get(0);
        
        // 测试getter方法
        assertNotNull(port.getPortName());
        assertNotNull(port.getDescription());
        assertFalse(port.getPortName().isEmpty());
        
        // 测试toString方法
        String portString = port.toString();
        assertNotNull(portString);
        assertTrue(portString.contains(port.getPortName()));
    }
    
    @Test
    public void testConcurrentOperations() throws InterruptedException {
        // 测试并发操作
        List<SerialPortManager.SerialPortInfo> ports = manager.getAvailablePorts();
        String portName = ports.get(0).getPortName();
        
        assertTrue(manager.connect(portName, 9600));
        manager.setOnDataReceivedListener(listener);
        
        // 创建多个线程同时发送数据
        int threadCount = 5;
        CountDownLatch latch = new CountDownLatch(threadCount);
        
        for (int i = 0; i < threadCount; i++) {
            final int threadId = i;
            new Thread(() -> {
                try {
                    String data = "Thread" + threadId + "\r\n";
                    manager.sendData(data.getBytes());
                } finally {
                    latch.countDown();
                }
            }).start();
        }
        
        // 等待所有线程完成
        assertTrue(latch.await(5, TimeUnit.SECONDS));
        
        // 等待一段时间让数据处理完成
        Thread.sleep(200);
    }
    
    @Test
    public void testResourceCleanup() {
        // 测试资源清理
        List<SerialPortManager.SerialPortInfo> ports = manager.getAvailablePorts();
        String portName = ports.get(0).getPortName();
        
        assertTrue(manager.connect(portName, 9600));
        assertTrue(manager.isConnected());
        
        // 模拟程序退出时的清理
        manager.disconnect();
        assertFalse(manager.isConnected());
        
        // 再次尝试操作应该失败
        assertFalse(manager.sendData("test".getBytes()));
    }
    
    @Test
    public void testListenerRemoval() {
        // 测试监听器移除
        List<SerialPortManager.SerialPortInfo> ports = manager.getAvailablePorts();
        String portName = ports.get(0).getPortName();
        
        assertTrue(manager.connect(portName, 9600));
        
        // 设置监听器
        manager.setOnDataReceivedListener(listener);
        
        // 移除监听器
        manager.setOnDataReceivedListener(null);
        
        // 发送数据，不应该触发监听器
        manager.sendData("test\r\n".getBytes());
        
        // 等待一段时间
        assertFalse(listener.waitForData(100));
    }
    
    /**
     * 测试用的数据接收监听器
     */
    private static class TestDataReceivedListener implements SerialPortManager.OnDataReceivedListener {
        private final AtomicReference<byte[]> lastReceivedData = new AtomicReference<>();
        private final CountDownLatch dataLatch = new CountDownLatch(1);
        
        @Override
        public void onDataReceived(byte[] data) {
            lastReceivedData.set(data);
            dataLatch.countDown();
        }
        
        public byte[] getLastReceivedData() {
            return lastReceivedData.get();
        }
        
        public boolean waitForData(long timeoutMs) {
            try {
                return dataLatch.await(timeoutMs, TimeUnit.MILLISECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
    }
}