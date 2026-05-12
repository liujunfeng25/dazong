package com.sohe.serialport.sdk;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import static org.junit.jupiter.api.Assertions.*;

/**
 * DataParser类的单元测试
 */
public class DataParserTest {
    
    private DataParser parser;
    
    @BeforeEach
    public void setUp() {
        parser = new DataParser();
    }
    
    @Test
    public void testParseValidShouhengData() {
        // 测试有效的首衡协议数据
        String testData = "sn0001.234kg\r\n";
        byte[] data = testData.getBytes();
        
        WeightData result = parser.parseData(data);
        
        assertNotNull(result);
        assertEquals(WeightData.ProtocolType.SHOUHENG, result.getProtocolType());
        assertEquals(WeightData.StabilityStatus.STABLE, result.getStability());
        assertEquals(WeightData.WeightType.NET, result.getWeightType());
        assertEquals(1.234, result.getWeight(), 0.001);
        assertEquals("kg", result.getUnit());
        assertEquals(testData, result.getRawData());
    }
    
    @Test
    public void testParseValidVAData() {
        // 测试有效的VA协议数据 - 使用新格式
        String testData = "VA,01,28,S,N,+   1.568,   0.000 kg\r\n";
        byte[] data = testData.getBytes();
        
        WeightData result = parser.parseData(data);
        
        assertNotNull(result);
        assertEquals(WeightData.ProtocolType.VA, result.getProtocolType());
        assertEquals(WeightData.StabilityStatus.STABLE, result.getStability());
        assertEquals(WeightData.WeightType.NET, result.getWeightType());
        assertEquals(1.568, result.getWeight(), 0.001);
        assertEquals("kg", result.getUnit());
        assertEquals(testData, result.getRawData());
        assertEquals("01", result.getAddress());
        assertEquals(28, result.getDataLength());
        assertFalse(result.isHasTare());
        assertEquals(0.000, result.getTareWeight(), 0.001);
    }
    
    @Test
    public void testParseShouhengUnstableData() {
        // 测试首衡协议不稳定数据
        String testData = "un0002.456kg\r\n";
        byte[] data = testData.getBytes();
        
        WeightData result = parser.parseData(data);
        
        assertNotNull(result);
        assertEquals(WeightData.ProtocolType.SHOUHENG, result.getProtocolType());
        assertEquals(WeightData.StabilityStatus.UNSTABLE, result.getStability());
        assertEquals(WeightData.WeightType.NET, result.getWeightType());
        assertEquals(2.456, result.getWeight(), 0.001);
        assertEquals("kg", result.getUnit());
    }
    
    @Test
    public void testParseVAUnstableData() {
        // 测试VA协议不稳定数据 - 使用新格式
        String testData = "VA,02,28,U,G,+   3.456,   1.200 kg\r\n";
        byte[] data = testData.getBytes();
        
        WeightData result = parser.parseData(data);
        
        assertNotNull(result);
        assertEquals(WeightData.ProtocolType.VA, result.getProtocolType());
        assertEquals(WeightData.StabilityStatus.UNSTABLE, result.getStability());
        assertEquals(WeightData.WeightType.GROSS, result.getWeightType());
        assertEquals(3.456, result.getWeight(), 0.001);
        assertEquals("kg", result.getUnit());
        assertEquals("02", result.getAddress());
        assertEquals(28, result.getDataLength());
        assertTrue(result.isHasTare());
        assertEquals(1.200, result.getTareWeight(), 0.001);
    }
    
    @Test
    public void testParseInvalidData() {
        // 测试无效数据
        String testData = "invalid data format";
        byte[] data = testData.getBytes();
        
        WeightData result = parser.parseData(data);
        
        assertNull(result);
    }
    
    @Test
    public void testParseNullData() {
        // 测试null数据
        WeightData result = parser.parseData(null);
        assertNull(result);
    }
    
    @Test
    public void testParseEmptyData() {
        // 测试空数据
        byte[] data = new byte[0];
        WeightData result = parser.parseData(data);
        assertNull(result);
    }
    
    @Test
    public void testParseShouhengWithDifferentUnits() {
        // 测试首衡协议不同单位
        String[] testUnits = {
            "kg",
            "g",
            "lb",
            "oz"
        };
        
        for (String unit : testUnits) {
            String testData = "sn0001.234" + unit + "\r\n";
            byte[] data = testData.getBytes();
            
            WeightData result = parser.parseData(data);
            
            assertNotNull(result, "Failed to parse data with unit: " + unit);
            assertEquals(WeightData.ProtocolType.SHOUHENG, result.getProtocolType());
            assertEquals(1.234, result.getWeight(), 0.001);
            assertEquals(unit, result.getUnit());
        }
    }
    
    @Test
    public void testParseVAWithDifferentUnits() {
        // 测试VA协议不同单位 - 使用新格式
        String[] testUnits = {
            "kg",
            "g",
            "lb",
            "oz"
        };
        
        for (String unit : testUnits) {
            String testData = "VA,01,28,S,N,+   1.234,   0.000 " + unit + "\r\n";
            byte[] data = testData.getBytes();
            
            WeightData result = parser.parseData(data);
            
            assertNotNull(result, "Failed to parse data with unit: " + unit);
            assertEquals(WeightData.ProtocolType.VA, result.getProtocolType());
            assertEquals(1.234, result.getWeight(), 0.001);
            assertEquals(unit, result.getUnit());
        }
    }
    
    @Test
    public void testParseDataWithoutLineEnding() {
        // 测试没有行结束符的数据
        String testData = "sn0001.234kg";
        byte[] data = testData.getBytes();
        
        WeightData result = parser.parseData(data);
        
        assertNotNull(result);
        assertEquals(WeightData.ProtocolType.SHOUHENG, result.getProtocolType());
        assertEquals(1.234, result.getWeight(), 0.001);
    }
    
    @Test
    public void testParseDataWithExtraSpaces() {
        // 测试带有额外空格的数据
        String testData = "  sn0001.234kg  \r\n";
        byte[] data = testData.getBytes();
        
        WeightData result = parser.parseData(data);
        
        assertNotNull(result);
        assertEquals(WeightData.ProtocolType.SHOUHENG, result.getProtocolType());
        assertEquals(1.234, result.getWeight(), 0.001);
    }
    
    @Test
    public void testParseNegativeWeight() {
        // 测试负重量
        String testData = "sn-001.234kg\r\n";
        byte[] data = testData.getBytes();
        
        WeightData result = parser.parseData(data);
        
        assertNotNull(result);
        assertEquals(WeightData.ProtocolType.SHOUHENG, result.getProtocolType());
        assertEquals(-1.234, result.getWeight(), 0.001);
    }
    
    @Test
    public void testParseZeroWeight() {
        // 测试零重量
        String testData = "sn0000.000kg\r\n";
        byte[] data = testData.getBytes();
        
        WeightData result = parser.parseData(data);
        
        assertNotNull(result);
        assertEquals(WeightData.ProtocolType.SHOUHENG, result.getProtocolType());
        assertEquals(0.0, result.getWeight(), 0.001);
    }
    
    @Test
    public void testParseLargeWeight() {
        // 测试大重量值
        String testData = "sn9999.999kg\r\n";
        byte[] data = testData.getBytes();
        
        WeightData result = parser.parseData(data);
        
        assertNotNull(result);
        assertEquals(WeightData.ProtocolType.SHOUHENG, result.getProtocolType());
        assertEquals(9999.999, result.getWeight(), 0.001);
    }
    
    @Test
    public void testParseCorruptedData() {
        // 测试损坏的数据
        String[] corruptedData = {
            "sn\0\0\0\r\n",  // 包含null字符
            "VA,01,19,S,N,abc kg\r\n",  // 无效数字
            "sn001.234\r\n",  // 缺少单位
            "VA,01\r\n",  // 不完整的VA数据
            "random text\r\n"  // 随机文本
        };
        
        for (String corrupt : corruptedData) {
            byte[] data = corrupt.getBytes();
            WeightData result = parser.parseData(data);
            
            // 损坏的数据应该返回null或者包含默认值
            if (result != null) {
                // 如果返回了结果，至少应该有协议类型
                assertNotNull(result.getProtocolType());
            }
        }
    }
    
    @Test
    public void testParseMultipleDataInSingleBuffer() {
        // 测试单个缓冲区中的多个数据
        String testData = "sn0001.234kg\r\nsn0002.456kg\r\n";
        byte[] data = testData.getBytes();
        
        WeightData result = parser.parseData(data);
        
        // 应该只解析第一个数据
        assertNotNull(result);
        assertEquals(WeightData.ProtocolType.SHOUHENG, result.getProtocolType());
        assertEquals(1.234, result.getWeight(), 0.001);
    }
    
    @Test
    public void testParseDataWithDifferentEncodings() {
        // 测试不同编码的数据
        String testData = "sn0001.234kg\r\n";
        
        // UTF-8编码
        byte[] utf8Data = testData.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        WeightData result1 = parser.parseData(utf8Data);
        assertNotNull(result1);
        
        // ASCII编码
        byte[] asciiData = testData.getBytes(java.nio.charset.StandardCharsets.US_ASCII);
        WeightData result2 = parser.parseData(asciiData);
        assertNotNull(result2);
        
        // 结果应该相同
        assertEquals(result1.getWeight(), result2.getWeight(), 0.001);
        assertEquals(result1.getProtocolType(), result2.getProtocolType());
    }
    
    @Test
    public void testParseTimestamp() {
        // 测试时间戳设置
        String testData = "sn0001.234kg\r\n";
        byte[] data = testData.getBytes();
        
        long beforeParse = System.currentTimeMillis();
        WeightData result = parser.parseData(data);
        long afterParse = System.currentTimeMillis();
        
        assertNotNull(result);
        assertTrue(result.getTimestamp() >= beforeParse);
        assertTrue(result.getTimestamp() <= afterParse);
    }
}