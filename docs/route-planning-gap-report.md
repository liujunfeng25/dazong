# 路线规划数据底座缺口报告（P0/P1）

## 一、现有可用数据

- 订单体量：`orders.total_volume_m3`、`orders.total_weight_kg`
- 车辆能力：`delivery_vehicles.capacity_weight_kg`、`delivery_vehicles.capacity_volume_m3`
- 车辆实时位置快照：`deliveries.current_lng`、`deliveries.current_lat`
- 设备绑定与定位来源：`delivery_vehicle_device_bindings` + `delivery_devices.raw_payload_json`
- IoT 原始点：`iot_data`（可承载 GPS 点）

## 二、关键缺口

### P0（演示升级后、生产可用前的最小必须补齐）

1. 订单级收货地理信息不足
   - 缺：订单自己的收货地址、经纬度、联系人、服务时长
   - 现状：主要依赖用户账号地址，难以支持精细路径

2. 时间窗未形成结构化可规划字段
   - 缺：`expected_delivery_date/slot` 的稳定落库与可查询索引
   - 现状：创建时有参数校验，但路线规划侧仍以示例数据为主

3. 路线计划实体缺失
   - 缺：`route_plans`、`route_plan_stops` 等结构化计划表
   - 现状：`/delivery/route-plan` 返回演示结果，`deliveries.route_json` 仅作弱结构承载

4. 围栏实体与事件缺失
   - 缺：`geofences`、`geofence_events`
   - 现状：无“进围栏/出围栏/越界”事件链路

### P1（生产增强）

1. 轨迹明细实体
   - 建议：`vehicle_tracks`（车辆、时间、经纬度、速度、关联计划/订单）

2. ETA 偏差分析字段
   - 建议在 stop 层补：`planned_arrive_at`、`actual_arrive_at`、`delay_minutes`

3. 绑定历史生命周期
   - 建议补：`bound_at`、`unbound_at`、`unbind_reason`（替代纯删除）

## 三、分阶段落地建议

- 阶段A（本轮）：不改大表，先增强 `route-plan` 返回字段并前端可解释化
- 阶段B：补订单地理+时窗、路线计划表、围栏表
- 阶段C：补轨迹/ETA 偏差分析，形成持续优化闭环

## 四、验收口径（数据侧）

- 能解释每个停靠点“为何排在这里”
- 能给出总里程/总时长/装载率/风险提示
- 能标记“估算模式”与“真实数据模式”，避免汇报误导

## 五、生产化字段蓝图（建议）

### 1) `orders` 建议补充字段（P0）

- `delivery_address`：订单收货地址文本
- `delivery_lng` / `delivery_lat`：订单级收货经纬度
- `receiver_name` / `receiver_phone`：收货联系人信息
- `expected_delivery_date`：期望送达日期
- `expected_delivery_slot`：期望送达时间段（如 `09:00-11:00`）
- `service_duration_min`：站点服务时长（分钟）

### 2) 新增表建议（P0/P1）

- `route_plans`（P0）
  - 核心：`delivery_id`、`vehicle_id`、`plan_date`、`status`、`optimizer_version`
  - 结果：`baseline_distance_km`、`optimized_distance_km`、`baseline_duration_minutes`、`optimized_duration_minutes`
- `route_plan_stops`（P0）
  - 核心：`plan_id`、`sequence`、`order_id`、`address`、`lng/lat`
  - 时效：`planned_arrive_at`、`planned_depart_at`、`time_window_start/end`
  - 解释：`constraints_hit_json`、`risk_flags_json`
- `geofences`（P0）
  - 核心：`name`、`fence_type`、`center_lng/center_lat`、`radius_m`、`polygon_json`
- `geofence_events`（P0）
  - 核心：`fence_id`、`vehicle_id`、`event_type(in|out|cross)`、`event_at`、`source_device_id`
- `vehicle_tracks`（P1）
  - 核心：`vehicle_id`、`recorded_at`、`lng/lat`、`speed_kmh`、`heading`、`plan_id/order_id`

## 六、迁移优先级（可执行）

1. `2026Q2_P0_orders_geo_window`
   - 先补 `orders` 的地理与时窗字段
2. `2026Q2_P0_route_plan_tables`
   - 新增 `route_plans` 与 `route_plan_stops`
3. `2026Q2_P0_geofence_tables`
   - 新增 `geofences` 与 `geofence_events`
4. `2026Q3_P1_vehicle_tracks`
   - 新增轨迹明细与 ETA 偏差分析支撑

## 七、mock/real 一键切换约定

- 前端统一 `localStorage` 键：`route-planning-data-mode`
- 模式值：`mock` / `real`
- 后端接口入参：
  - `/delivery/route-plan`：`data_mode`
  - `/monitor/route-planning-showcase`：`data_mode`
- 约束：两种模式返回同构 JSON，字段保持一致，避免前端分支爆炸
