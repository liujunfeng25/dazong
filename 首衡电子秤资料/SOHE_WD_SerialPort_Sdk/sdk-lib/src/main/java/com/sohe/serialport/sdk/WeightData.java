package com.sohe.serialport.sdk;

/**
 * 重量数据模型类
 * 用于封装解析后的重量数据
 */
public class WeightData {
    
    /**
     * 数据协议类型
     */
    public enum ProtocolType {
        SHOUHENG,  // 首衡串行通讯协议
        VA         // VA协议
    }
    
    /**
     * 稳定状态
     */
    public enum StabilityStatus {
        STABLE,    // 稳定
        UNSTABLE,  // 不稳定
        OVERLOAD   // 超载
    }
    
    /**
     * 重量类型
     */
    public enum WeightType {
        NET,       // 净重
        GROSS      // 毛重
    }
    
    private ProtocolType protocolType;     // 协议类型
    private StabilityStatus stability;     // 稳定状态
    private WeightType weightType;         // 重量类型
    private double weight;                 // 重量值
    private String unit;                   // 单位
    private boolean isPositive;            // 是否为正数
    private String rawData;                // 原始数据
    private long timestamp;                // 时间戳
    
    // VA协议特有字段
    private String address;                // 地址
    private int dataLength;                // 数据长度
    private boolean hasTare;               // 是否有皮重
    private double tareWeight;             // 皮重值
    
    public WeightData() {
        this.timestamp = System.currentTimeMillis();
    }
    
    // Getter和Setter方法
    public ProtocolType getProtocolType() {
        return protocolType;
    }
    
    public void setProtocolType(ProtocolType protocolType) {
        this.protocolType = protocolType;
    }
    
    public StabilityStatus getStability() {
        return stability;
    }
    
    public void setStability(StabilityStatus stability) {
        this.stability = stability;
    }
    
    public WeightType getWeightType() {
        return weightType;
    }
    
    public void setWeightType(WeightType weightType) {
        this.weightType = weightType;
    }
    
    public double getWeight() {
        return weight;
    }
    
    public void setWeight(double weight) {
        this.weight = weight;
    }
    
    public String getUnit() {
        return unit;
    }
    
    public void setUnit(String unit) {
        this.unit = unit;
    }
    
    public boolean isPositive() {
        return isPositive;
    }
    
    public void setPositive(boolean positive) {
        isPositive = positive;
    }
    
    public String getRawData() {
        return rawData;
    }
    
    public void setRawData(String rawData) {
        this.rawData = rawData;
    }
    
    public long getTimestamp() {
        return timestamp;
    }
    
    public void setTimestamp(long timestamp) {
        this.timestamp = timestamp;
    }
    
    public String getAddress() {
        return address;
    }
    
    public void setAddress(String address) {
        this.address = address;
    }
    
    public int getDataLength() {
        return dataLength;
    }
    
    public void setDataLength(int dataLength) {
        this.dataLength = dataLength;
    }
    
    public boolean isHasTare() {
        return hasTare;
    }
    
    public void setHasTare(boolean hasTare) {
        this.hasTare = hasTare;
    }
    
    public double getTareWeight() {
        return tareWeight;
    }
    
    public void setTareWeight(double tareWeight) {
        this.tareWeight = tareWeight;
    }
    
    /**
     * 获取格式化的重量字符串
     * @return 格式化后的重量字符串，包含符号
     */
    public String getFormattedWeight() {
        String sign = isPositive ? "+" : "-";
        return String.format("%s%.3f %s", sign, weight, unit != null ? unit : "kg");
    }
    
    /**
     * 获取不带符号的重量字符串
     * @return 不带符号的重量字符串
     */
    public String getWeightString() {
        return String.format("%.3f %s", weight, unit != null ? unit : "kg");
    }
    
    /**
     * 获取稳定状态
     * @return 稳定状态
     */
    public StabilityStatus getStabilityStatus() {
        return stability;
    }
    
    /**
     * 检查重量是否有效
     * @return 是否有效
     */
    public boolean isValidWeight() {
        return stability != StabilityStatus.OVERLOAD;
    }
    
    /**
     * 检查是否有皮重
     * @return 是否有皮重
     */
    public boolean hasTareWeight() {
        return hasTare;
    }
    
    /**
     * 检查数据是否稳定
     * @return 是否稳定
     */
    public boolean isStable() {
        return stability == StabilityStatus.STABLE;
    }
    
    /**
     * 检查是否为净重
     * @return 是否为净重
     */
    public boolean isNetWeight() {
        return weightType == WeightType.NET;
    }
    
    /**
     * 检查是否超载
     * @return 是否超载
     */
    public boolean isOverload() {
        return stability == StabilityStatus.OVERLOAD;
    }
    
    @Override
    public String toString() {
        return "WeightData{" +
                "protocolType=" + protocolType +
                ", stability=" + stability +
                ", weightType=" + weightType +
                ", weight=" + weight +
                ", unit='" + unit + '\'' +
                ", isPositive=" + isPositive +
                ", address='" + address + '\'' +
                ", dataLength=" + dataLength +
                ", hasTare=" + hasTare +
                ", timestamp=" + timestamp +
                '}';
    }
    
    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (obj == null || getClass() != obj.getClass()) return false;
        
        WeightData that = (WeightData) obj;
        
        return Double.compare(that.weight, weight) == 0 &&
               isPositive == that.isPositive &&
               dataLength == that.dataLength &&
               hasTare == that.hasTare &&
               protocolType == that.protocolType &&
               stability == that.stability &&
               weightType == that.weightType &&
               (unit != null ? unit.equals(that.unit) : that.unit == null) &&
               (address != null ? address.equals(that.address) : that.address == null);
    }
    
    @Override
    public int hashCode() {
        int result;
        long temp;
        result = protocolType != null ? protocolType.hashCode() : 0;
        result = 31 * result + (stability != null ? stability.hashCode() : 0);
        result = 31 * result + (weightType != null ? weightType.hashCode() : 0);
        temp = Double.doubleToLongBits(weight);
        result = 31 * result + (int) (temp ^ (temp >>> 32));
        result = 31 * result + (unit != null ? unit.hashCode() : 0);
        result = 31 * result + (isPositive ? 1 : 0);
        result = 31 * result + (address != null ? address.hashCode() : 0);
        result = 31 * result + dataLength;
        result = 31 * result + (hasTare ? 1 : 0);
        return result;
    }
}