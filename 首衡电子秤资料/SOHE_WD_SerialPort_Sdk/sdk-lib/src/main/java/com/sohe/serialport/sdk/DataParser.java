package com.sohe.serialport.sdk;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 数据解析器类
 * 支持自动识别和解析两种数据格式：首衡串行通讯协议和VA协议
 */
public class DataParser {
    private static final String TAG = "DataParser";
    
    // 首衡协议正则表达式：稳定标志 + 净重标志 + 重量数据 + 单位
    // 例如：sn0001.23kg 或 sn-001.23kg
    private static final Pattern SHOUHENG_PATTERN = Pattern.compile(
        "^([sw])([ng])([0-9\\-\\.]+)(kg)\\r?\\n?$", Pattern.CASE_INSENSITIVE
    );
    
    // VA协议正则表达式：VA,地址,数据长度,稳定标志,皮重标志,符号,称重值,皮重值,单位
    // 新格式：VA,01,28,S,N,-   1.800,   0.000 kg
    // 修复：支持符号后多个空格的情况
    private static final Pattern VA_PATTERN = Pattern.compile(
        "^VA,([0-9]{1,3}),([0-9]{2}),([SUO]),([NG]),([\\+\\-])\\s+([0-9\\.]+),\\s+([0-9\\.]+)\\s+(kg|g|lb|oz)\\s*\\r?\\n?$", 
        Pattern.CASE_INSENSITIVE
    );
    
    /**
     * 解析串口接收到的数据
     * @param data 原始字节数据
     * @return 解析后的重量数据，如果解析失败返回null
     */
    public static WeightData parseData(byte[] data) {
        if (data == null || data.length == 0) {
            return null;
        }
        
        // 将字节数组转换为字符串
        String dataString = new String(data).trim();
        
        // 如果数据包含多条VA协议数据，先分割处理
        if (dataString.contains("VA,") && dataString.indexOf("VA,") != dataString.lastIndexOf("VA,")) {
            // 多条VA数据，取最后一条进行解析（通常最后一条是最新的稳定数据）
            String[] vaEntries = dataString.split("(?=VA,)");
            for (int i = vaEntries.length - 1; i >= 0; i--) {
                String entry = vaEntries[i].trim();
                if (!entry.isEmpty()) {
                    WeightData result = parseVAProtocol(entry);
                    if (result != null) {
                        return result;
                    }
                }
            }
        }
        
        // 尝试解析首衡协议
        WeightData shouhengResult = parseShouhengProtocol(dataString);
        if (shouhengResult != null) {
            return shouhengResult;
        }
        
        // 尝试解析VA协议
        WeightData vaResult = parseVAProtocol(dataString);
        if (vaResult != null) {
            return vaResult;
        }
        
        return null;
    }
    
    /**
     * 解析首衡串行通讯协议
     * 格式：稳定标志(s/w) + 净重标志(n/g) + 重量数据 + 单位(kg) + 换行符
     * 例如：sn0001.23kg\r\n
     */
    private static WeightData parseShouhengProtocol(String data) {
        Matcher matcher = SHOUHENG_PATTERN.matcher(data);
        if (!matcher.matches()) {
            return null;
        }
        
        try {
            WeightData weightData = new WeightData();
            weightData.setProtocolType(WeightData.ProtocolType.SHOUHENG);
            weightData.setRawData(data);
            
            // 解析稳定标志
            String stabilityFlag = matcher.group(1).toLowerCase();
            if ("s".equals(stabilityFlag)) {
                weightData.setStability(WeightData.StabilityStatus.STABLE);
            } else {
                weightData.setStability(WeightData.StabilityStatus.UNSTABLE);
            }
            
            // 解析净重标志
            String weightTypeFlag = matcher.group(2).toLowerCase();
            if ("n".equals(weightTypeFlag)) {
                weightData.setWeightType(WeightData.WeightType.NET);
            } else {
                weightData.setWeightType(WeightData.WeightType.GROSS);
            }
            
            // 解析重量数据
            String weightString = matcher.group(3);
            double weight;
            boolean isPositive = true;
            
            if (weightString.startsWith("-")) {
                isPositive = false;
                weight = Double.parseDouble(weightString.substring(1));
            } else if (weightString.startsWith("0")) {
                // 处理0开头的情况，如0001.23
                weight = Double.parseDouble(weightString);
            } else {
                weight = Double.parseDouble(weightString);
            }
            
            weightData.setWeight(weight);
            weightData.setPositive(isPositive);
            
            // 解析单位
            String unit = matcher.group(4).toLowerCase();
            weightData.setUnit(unit);
            
            return weightData;
            
        } catch (NumberFormatException e) {
            return null;
        }
    }
    
    /**
     * 解析VA协议
     * 格式：VA,地址,数据长度,稳定标志,皮重标志,符号,称重值,皮重值,单位
     * 新格式：VA,01,28,S,N,+   0.000,   0.000 kg
     */
    private static WeightData parseVAProtocol(String data) {
        Matcher matcher = VA_PATTERN.matcher(data);
        if (!matcher.matches()) {
            return null;
        }
        
        try {
            WeightData weightData = new WeightData();
            weightData.setProtocolType(WeightData.ProtocolType.VA);
            weightData.setRawData(data);
            
            // 解析地址 (支持1-990，99为广播地址)
            String address = matcher.group(1);
            weightData.setAddress(address);
            
            // 解析数据长度 (固定28)
            int dataLength = Integer.parseInt(matcher.group(2));
            weightData.setDataLength(dataLength);
            
            // 解析稳定标志
            String stabilityFlag = matcher.group(3).toUpperCase();
            switch (stabilityFlag) {
                case "S":
                    weightData.setStability(WeightData.StabilityStatus.STABLE);
                    break;
                case "U":
                    weightData.setStability(WeightData.StabilityStatus.UNSTABLE);
                    break;
                case "O":
                    weightData.setStability(WeightData.StabilityStatus.OVERLOAD);
                    break;
                default:
                    weightData.setStability(WeightData.StabilityStatus.UNSTABLE);
                    break;
            }
            
            // 解析皮重标志
            String tareFlag = matcher.group(4).toUpperCase();
            switch (tareFlag) {
                case "N":
                    weightData.setWeightType(WeightData.WeightType.NET);
                    weightData.setHasTare(false);
                    break;
                case "G":
                    weightData.setWeightType(WeightData.WeightType.GROSS);
                    weightData.setHasTare(true);
                    break;
                default:
                    weightData.setWeightType(WeightData.WeightType.NET);
                    weightData.setHasTare(false);
                    break;
            }
            
            // 解析符号
            String sign = matcher.group(5);
            boolean isPositive = "+".equals(sign);
            weightData.setPositive(isPositive);
            
            // 解析称重值
            double weight = Double.parseDouble(matcher.group(6));
            if (!isPositive) {
                weight = -weight;
            }
            weightData.setWeight(weight);
            
            // 解析皮重值
            double tareWeight = Double.parseDouble(matcher.group(7));
            weightData.setTareWeight(tareWeight);
            
            // 解析单位
            String unit = matcher.group(8).toLowerCase();
            weightData.setUnit(unit);
            
            return weightData;
            
        } catch (NumberFormatException e) {
            return null;
        }
    }
    
    /**
     * 检测数据格式类型
     * @param data 原始数据字符串
     * @return 协议类型，如果无法识别返回null
     */
    public static WeightData.ProtocolType detectProtocolType(String data) {
        if (data == null || data.trim().isEmpty()) {
            return null;
        }
        
        String trimmedData = data.trim();
        
        // 检查是否为VA协议（以VA开头）
        if (trimmedData.startsWith("VA,")) {
            return WeightData.ProtocolType.VA;
        }
        
        // 检查是否为首衡协议（符合首衡格式）
        if (SHOUHENG_PATTERN.matcher(trimmedData).matches()) {
            return WeightData.ProtocolType.SHOUHENG;
        }
        
        return null;
    }
    
    /**
     * 验证数据格式是否有效
     * @param data 原始数据字符串
     * @return 是否为有效格式
     */
    public static boolean isValidFormat(String data) {
        return detectProtocolType(data) != null;
    }
    
    /**
     * 格式化重量数据为可读字符串
     * @param weightData 重量数据对象
     * @return 格式化后的字符串
     */
    public static String formatWeightData(WeightData weightData) {
        if (weightData == null) {
            return "无效数据";
        }
        
        StringBuilder sb = new StringBuilder();
        sb.append("协议: ").append(weightData.getProtocolType().name()).append(", ");
        sb.append("状态: ").append(getStabilityText(weightData.getStability())).append(", ");
        sb.append("类型: ").append(getWeightTypeText(weightData.getWeightType())).append(", ");
        sb.append("重量: ").append(weightData.getFormattedWeight());
        
        if (weightData.getProtocolType() == WeightData.ProtocolType.VA) {
            sb.append(", 地址: ").append(weightData.getAddress());
            sb.append(", 皮重: ").append(weightData.isHasTare() ? "有" : "无");
        }
        
        return sb.toString();
    }
    
    /**
     * 获取稳定状态的中文描述
     * @param stability 稳定状态
     * @return 中文描述
     */
    private static String getStabilityText(WeightData.StabilityStatus stability) {
        switch (stability) {
            case STABLE: return "稳定";
            case UNSTABLE: return "不稳定";
            case OVERLOAD: return "超载";
            default: return "未知";
        }
    }
    
    /**
     * 获取重量类型的中文描述
     * @param weightType 重量类型
     * @return 中文描述
     */
    private static String getWeightTypeText(WeightData.WeightType weightType) {
        switch (weightType) {
            case NET: return "净重";
            case GROSS: return "毛重";
            default: return "未知";
        }
    }
    
    /**
     * 解析字节数据为字符串（支持多种编码）
     * @param data 字节数据
     * @param encoding 编码格式，如果为null则使用默认编码
     * @return 解析后的字符串
     */
    public static String parseToString(byte[] data, String encoding) {
        if (data == null || data.length == 0) {
            return "";
        }
        
        try {
            if (encoding != null && !encoding.isEmpty()) {
                return new String(data, encoding).trim();
            } else {
                return new String(data).trim();
            }
        } catch (Exception e) {
            // 如果指定编码失败，使用默认编码
            return new String(data).trim();
        }
    }
}