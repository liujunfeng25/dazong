// 自动从真实 OpenAPI 规范烘焙(请求侧);响应示例见 CORE_RESPONSES
export const ENDPOINT_DETAIL = {
  "POST /api/auth/login": {
    "auth": false,
    "summary": "Login",
    "params": [
      {
        "name": "username",
        "in": "body",
        "required": true,
        "type": "string",
        "desc": "Username"
      },
      {
        "name": "password",
        "in": "body",
        "required": true,
        "type": "string",
        "desc": "Password"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"username\": \"client001\",\n  \"password\": \"demo123\"\n}"
  },
  "GET /api/auth/me": {
    "auth": true,
    "summary": "Me",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "POST /api/auth/change-password": {
    "auth": true,
    "summary": "Change Password",
    "params": [
      {
        "name": "old_password",
        "in": "body",
        "required": true,
        "type": "string",
        "desc": "Old Password"
      },
      {
        "name": "new_password",
        "in": "body",
        "required": true,
        "type": "string",
        "desc": "New Password"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"old_password\": \"...\",\n  \"new_password\": \"...\"\n}"
  },
  "POST /api/client/canteen-session": {
    "auth": true,
    "summary": "Set Client Canteen Session",
    "params": [
      {
        "name": "canteen_id",
        "in": "body",
        "required": true,
        "type": "integer",
        "desc": "Canteen Id"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"canteen_id\": 51\n}"
  },
  "GET /api/client/dashboard": {
    "auth": true,
    "summary": "Client Dashboard",
    "params": [
      {
        "name": "scope",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      }
    ],
    "resNote": "返回列表 / 数组"
  },
  "GET /api/client/canteens": {
    "auth": true,
    "summary": "List Client Canteens",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "GET /api/orders/products/search": {
    "auth": true,
    "summary": "Search Order Products",
    "params": [
      {
        "name": "keyword",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "page",
        "in": "query",
        "required": false,
        "type": "integer",
        "desc": ""
      },
      {
        "name": "page_size",
        "in": "query",
        "required": false,
        "type": "integer",
        "desc": ""
      },
      {
        "name": "delivery_id",
        "in": "query",
        "required": false,
        "type": "integer",
        "desc": ""
      },
      {
        "name": "contract_categories_only",
        "in": "query",
        "required": false,
        "type": "boolean",
        "desc": "为 true 时仅返回当前客户对该配送商已生效合约中的一级分类下的商品；须同时传 delivery_id 与 expected_delivery_date"
      },
      {
        "name": "expected_delivery_date",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": "期望配送日；contract_categories_only 为 true 时必填，且须落在合约有效期内"
      }
    ],
    "resNote": "返回列表 / 数组"
  },
  "POST /api/ocr/parse-order": {
    "auth": true,
    "summary": "Parse Order By Ocr",
    "params": [],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "POST /api/voice/parse-order": {
    "auth": true,
    "summary": "Parse Order By Voice",
    "params": [
      {
        "name": "text",
        "in": "body",
        "required": true,
        "type": "string",
        "desc": "Text"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"text\": \"...\"\n}"
  },
  "GET /api/client/bills": {
    "auth": true,
    "summary": "Client Bills",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "POST /api/orders": {
    "auth": true,
    "summary": "Create Order",
    "params": [
      {
        "name": "delivery_id",
        "in": "body",
        "required": true,
        "type": "integer",
        "desc": "Delivery Id"
      },
      {
        "name": "items",
        "in": "body",
        "required": true,
        "type": "OrderItemIn[]",
        "desc": "Items"
      },
      {
        "name": "delivery_address",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Delivery Address"
      },
      {
        "name": "delivery_lng",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Delivery Lng"
      },
      {
        "name": "delivery_lat",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Delivery Lat"
      },
      {
        "name": "expected_delivery_date",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Expected Delivery Date"
      },
      {
        "name": "expected_delivery_slot",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Expected Delivery Slot"
      },
      {
        "name": "service_duration_min",
        "in": "body",
        "required": false,
        "type": "integer",
        "desc": "Service Duration Min"
      },
      {
        "name": "force",
        "in": "body",
        "required": false,
        "type": "boolean",
        "desc": "Force"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"delivery_id\": 3,\n  \"items\": [\n    {\n      \"product_id\": 2041,\n      \"quantity\": 20,\n      \"unit_price\": 6.8\n    }\n  ],\n  \"delivery_address\": \"北京市海淀区 XX 学校\",\n  \"expected_delivery_date\": \"2026-06-04\",\n  \"expected_delivery_slot\": \"09:00-10:00\"\n}"
  },
  "GET /api/orders/{id}": {
    "auth": true,
    "summary": "Order Detail",
    "params": [
      {
        "name": "order_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      }
    ],
    "resNote": "返回该资源的详情对象"
  },
  "POST /api/orders/{id}/print-allocation-labels": {
    "auth": true,
    "summary": "Print Allocation Labels",
    "params": [
      {
        "name": "order_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      },
      {
        "name": "allocation_ids",
        "in": "body",
        "required": false,
        "type": "integer[]",
        "desc": "Allocation Ids"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "POST /api/orders/{id}/ship": {
    "auth": true,
    "summary": "Ship Order",
    "params": [
      {
        "name": "order_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "POST /api/orders/{id}/pickup": {
    "auth": true,
    "summary": "Pickup Order",
    "params": [
      {
        "name": "order_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "POST /api/orders/{id}/deliver": {
    "auth": true,
    "summary": "Deliver Order",
    "params": [
      {
        "name": "order_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "POST /api/orders/{id}/receive": {
    "auth": true,
    "summary": "Receive Order",
    "params": [
      {
        "name": "order_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "POST /api/orders/{id}/settle": {
    "auth": true,
    "summary": "Settle Order",
    "params": [
      {
        "name": "order_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "PUT /api/orders/{id}/cancel": {
    "auth": true,
    "summary": "Cancel Order",
    "params": [
      {
        "name": "order_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "GET /api/orders/{id}/logistics-tracking": {
    "auth": true,
    "summary": "Order Logistics Tracking",
    "params": [
      {
        "name": "order_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      }
    ],
    "resNote": "返回列表 / 数组"
  },
  "POST /api/delivery/smart-split/preview": {
    "auth": true,
    "summary": "Smart Split Preview",
    "params": [
      {
        "name": "order_ids",
        "in": "body",
        "required": true,
        "type": "integer[]",
        "desc": "Order Ids"
      },
      {
        "name": "mode",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Mode"
      },
      {
        "name": "quota_window",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Quota Window"
      },
      {
        "name": "allow_split",
        "in": "body",
        "required": false,
        "type": "boolean",
        "desc": "Allow Split"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"order_ids\": [\n    2536,\n    2537\n  ],\n  \"mode\": \"normal\"\n}"
  },
  "POST /api/delivery/smart-split/commit": {
    "auth": true,
    "summary": "Smart Split Commit",
    "params": [
      {
        "name": "allocations",
        "in": "body",
        "required": true,
        "type": "SmartSplitAllocationIn[]",
        "desc": "Allocations"
      },
      {
        "name": "mode",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Mode"
      },
      {
        "name": "quota_window",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Quota Window"
      },
      {
        "name": "allow_split",
        "in": "body",
        "required": false,
        "type": "boolean",
        "desc": "Allow Split"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"allocations\": [],\n  \"mode\": \"normal\"\n}"
  },
  "POST /api/delivery/route-plan": {
    "auth": true,
    "summary": "Route Plan",
    "params": [
      {
        "name": "driver_id",
        "in": "body",
        "required": true,
        "type": "integer",
        "desc": "Driver Id"
      },
      {
        "name": "order_ids",
        "in": "body",
        "required": true,
        "type": "integer[]",
        "desc": "Order Ids"
      },
      {
        "name": "planning_date",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Planning Date"
      },
      {
        "name": "departure_time",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Departure Time"
      },
      {
        "name": "departure_time_by_vehicle_no",
        "in": "body",
        "required": false,
        "type": "object",
        "desc": "Departure Time By Vehicle No"
      },
      {
        "name": "service_minutes_default",
        "in": "body",
        "required": false,
        "type": "integer",
        "desc": "Service Minutes Default"
      },
      {
        "name": "service_minutes_by_order",
        "in": "body",
        "required": false,
        "type": "object",
        "desc": "Service Minutes By Order"
      },
      {
        "name": "user_disabled_vehicle_nos",
        "in": "body",
        "required": false,
        "type": "string[]",
        "desc": "User Disabled Vehicle Nos"
      },
      {
        "name": "geofence_policy",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Geofence Policy"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"driver_id\": 0,\n  \"order_ids\": [\n    2536,\n    2537\n  ]\n}"
  },
  "GET /api/delivery/vehicles/restriction/beijing": {
    "auth": true,
    "summary": "Beijing Vehicle Restriction Today",
    "params": [
      {
        "name": "plan_date",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": "限行规则参照的自然日（YYYY-MM-DD）；不传则按今日（北京时间）"
      }
    ],
    "resNote": "返回列表 / 数组"
  },
  "POST /api/delivery/vehicles/{id}/beidou-location": {
    "auth": true,
    "summary": "Post Vehicle Beidou Location",
    "params": [
      {
        "name": "vehicle_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      },
      {
        "name": "lng",
        "in": "body",
        "required": true,
        "type": "number",
        "desc": "Lng"
      },
      {
        "name": "lat",
        "in": "body",
        "required": true,
        "type": "number",
        "desc": "Lat"
      },
      {
        "name": "speed",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Speed"
      },
      {
        "name": "course",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Course"
      },
      {
        "name": "reported_at",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Reported At"
      },
      {
        "name": "device_code",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Device Code"
      },
      {
        "name": "device_name",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Device Name"
      },
      {
        "name": "raw_payload_json",
        "in": "body",
        "required": false,
        "type": "object",
        "desc": "Raw Payload Json"
      },
      {
        "name": "bind_if_missing",
        "in": "body",
        "required": false,
        "type": "boolean",
        "desc": "Bind If Missing"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"lng\": 0,\n  \"lat\": 0\n}"
  },
  "GET /api/delivery/geofences": {
    "auth": true,
    "summary": "List Delivery Geofences",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "GET /api/delivery/warehouses/{id}/elitech/realtime": {
    "auth": true,
    "summary": "Get Delivery Warehouse Elitech Realtime",
    "params": [
      {
        "name": "warehouse_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      }
    ],
    "resNote": "返回列表 / 数组"
  },
  "GET /api/delivery/workbench": {
    "auth": true,
    "summary": "Delivery Workbench",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "GET /api/supplier/home": {
    "auth": true,
    "summary": "Supplier Home",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "GET /api/supplier/orders": {
    "auth": true,
    "summary": "Supplier Orders",
    "params": [
      {
        "name": "status",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "order_no",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "created_date_start",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "created_date_end",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "expected_delivery_date_start",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "expected_delivery_date_end",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      }
    ],
    "resNote": "返回列表 / 数组"
  },
  "PUT /api/supplier/product-quotes": {
    "auth": true,
    "summary": "Save Supplier Product Quotes",
    "params": [],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "GET /api/factory/orders": {
    "auth": true,
    "summary": "Factory Orders",
    "params": [
      {
        "name": "status",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "order_no",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "created_date_start",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "created_date_end",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "expected_delivery_date_start",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "expected_delivery_date_end",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      }
    ],
    "resNote": "返回列表 / 数组"
  },
  "POST /api/quality-reports/by-allocation": {
    "auth": true,
    "summary": "Upload Report By Allocation",
    "params": [],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "GET /api/quality-reports/by-order/{id}": {
    "auth": true,
    "summary": "List Reports By Order",
    "params": [
      {
        "name": "order_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      }
    ],
    "resNote": "返回该资源的详情对象"
  },
  "POST /api/contracts/tender": {
    "auth": true,
    "summary": "Create Tender",
    "params": [
      {
        "name": "delivery_ids",
        "in": "body",
        "required": true,
        "type": "integer[]",
        "desc": "Delivery Ids"
      },
      {
        "name": "category_ids",
        "in": "body",
        "required": false,
        "type": "integer[]",
        "desc": "Category Ids"
      },
      {
        "name": "period_start",
        "in": "body",
        "required": true,
        "type": "string",
        "desc": "Period Start"
      },
      {
        "name": "period_end",
        "in": "body",
        "required": true,
        "type": "string",
        "desc": "Period End"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"delivery_ids\": [],\n  \"period_start\": \"...\",\n  \"period_end\": \"...\"\n}"
  },
  "POST /api/contracts/tender/{id}/bid": {
    "auth": true,
    "summary": "Bid Tender",
    "params": [
      {
        "name": "tender_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      },
      {
        "name": "category_rates",
        "in": "body",
        "required": true,
        "type": "BidCategoryRateIn[]",
        "desc": "Category Rates"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"category_rates\": []\n}"
  },
  "POST /api/contracts/tender/{id}/award": {
    "auth": true,
    "summary": "Award Tender",
    "params": [
      {
        "name": "tender_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      },
      {
        "name": "delivery_id",
        "in": "body",
        "required": true,
        "type": "integer",
        "desc": "Delivery Id"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"delivery_id\": 3\n}"
  },
  "GET /api/contracts/list": {
    "auth": true,
    "summary": "List My Contracts",
    "params": [
      {
        "name": "lifecycle",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": "待生效|生效中|已过期|招标中|已中标，空为全部"
      },
      {
        "name": "keyword",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": "合约号/客户名称/地址模糊筛选"
      }
    ],
    "resNote": "返回列表 / 数组"
  },
  "GET /api/bills/statements": {
    "auth": true,
    "summary": "List Statements",
    "params": [
      {
        "name": "statement_scope",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": "仅采购端 client 生效：current_canteen=仅当前 JWT 食堂；school_merged=本校全部食堂合并。缺省按 current_canteen。"
      },
      {
        "name": "direction",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "status",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "period_label",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "counterparty_keyword",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "keyword",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "overdue",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      }
    ],
    "resNote": "返回列表 / 数组"
  },
  "POST /api/bills/statements/{id}/confirm": {
    "auth": true,
    "summary": "Confirm Statement",
    "params": [
      {
        "name": "statement_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      },
      {
        "name": "remark",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Remark"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "POST /api/bills/statements/{id}/settle": {
    "auth": true,
    "summary": "Settle Statement",
    "params": [
      {
        "name": "statement_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      },
      {
        "name": "amount",
        "in": "body",
        "required": true,
        "type": "number",
        "desc": "Amount"
      },
      {
        "name": "remark",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Remark"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"amount\": 206.6\n}"
  },
  "GET /api/bills/cycles": {
    "auth": true,
    "summary": "List Cycles",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "GET /api/bills/overview": {
    "auth": true,
    "summary": "Billing Overview",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "GET /api/operation/dashboard": {
    "auth": true,
    "summary": "Operation Dashboard",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "POST /api/operation/products": {
    "auth": true,
    "summary": "Create Product",
    "params": [
      {
        "name": "goods_sn",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Goods Sn"
      },
      {
        "name": "name",
        "in": "body",
        "required": true,
        "type": "string",
        "desc": "Name"
      },
      {
        "name": "category1_id",
        "in": "body",
        "required": true,
        "type": "integer",
        "desc": "Category1 Id"
      },
      {
        "name": "category2_id",
        "in": "body",
        "required": true,
        "type": "integer",
        "desc": "Category2 Id"
      },
      {
        "name": "unit",
        "in": "body",
        "required": true,
        "type": "string",
        "desc": "Unit"
      },
      {
        "name": "reference_price",
        "in": "body",
        "required": true,
        "type": "number",
        "desc": "Reference Price"
      },
      {
        "name": "spec",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Spec"
      },
      {
        "name": "origin",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Origin"
      },
      {
        "name": "standard_type",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Standard Type"
      },
      {
        "name": "length_cm",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Length Cm"
      },
      {
        "name": "width_cm",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Width Cm"
      },
      {
        "name": "height_cm",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Height Cm"
      },
      {
        "name": "unit_weight_kg",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Unit Weight Kg"
      },
      {
        "name": "volume_adjust_factor",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Volume Adjust Factor"
      },
      {
        "name": "is_designated_factory",
        "in": "body",
        "required": false,
        "type": "boolean",
        "desc": "Is Designated Factory"
      },
      {
        "name": "designated_factory_id",
        "in": "body",
        "required": false,
        "type": "integer",
        "desc": "Designated Factory Id"
      },
      {
        "name": "quality_report_mode",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Quality Report Mode"
      },
      {
        "name": "status",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Status"
      },
      {
        "name": "brand",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Brand"
      },
      {
        "name": "expire_date",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Expire Date"
      },
      {
        "name": "manufacturer",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Manufacturer"
      },
      {
        "name": "model",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Model"
      },
      {
        "name": "source",
        "in": "body",
        "required": false,
        "type": "integer",
        "desc": "Source"
      },
      {
        "name": "attr",
        "in": "body",
        "required": false,
        "type": "integer",
        "desc": "Attr"
      },
      {
        "name": "level",
        "in": "body",
        "required": false,
        "type": "integer",
        "desc": "Level"
      },
      {
        "name": "limit_price",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Limit Price"
      },
      {
        "name": "discount_rate",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Discount Rate"
      },
      {
        "name": "float_rate_max",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Float Rate Max"
      },
      {
        "name": "float_rate_min",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Float Rate Min"
      },
      {
        "name": "supplier_id",
        "in": "body",
        "required": false,
        "type": "integer",
        "desc": "Supplier Id"
      },
      {
        "name": "supplier_name",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Supplier Name"
      },
      {
        "name": "goods_channel",
        "in": "body",
        "required": false,
        "type": "integer",
        "desc": "Goods Channel"
      },
      {
        "name": "finance_code",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Finance Code"
      },
      {
        "name": "finance_rate",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Finance Rate"
      },
      {
        "name": "number",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Number"
      },
      {
        "name": "weight",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Weight"
      },
      {
        "name": "remark",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Remark"
      },
      {
        "name": "logo",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Logo"
      },
      {
        "name": "slogo",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Slogo"
      },
      {
        "name": "detail_images_json",
        "in": "body",
        "required": false,
        "type": "string[]",
        "desc": "Detail Images Json"
      },
      {
        "name": "image_list_json",
        "in": "body",
        "required": false,
        "type": "string[]",
        "desc": "Image List Json"
      },
      {
        "name": "external_url",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "External Url"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"name\": \"...\",\n  \"category1_id\": 0,\n  \"category2_id\": 0,\n  \"unit\": \"...\",\n  \"reference_price\": 0,\n  \"status\": \"下单\",\n  \"supplier_id\": 61\n}"
  },
  "POST /api/operation/client-canteens": {
    "auth": true,
    "summary": "Create Client Canteen Operation",
    "params": [
      {
        "name": "school_client_id",
        "in": "body",
        "required": true,
        "type": "integer",
        "desc": "School Client Id"
      },
      {
        "name": "name",
        "in": "body",
        "required": true,
        "type": "string",
        "desc": "Name"
      },
      {
        "name": "address",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Address"
      },
      {
        "name": "lng",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Lng"
      },
      {
        "name": "lat",
        "in": "body",
        "required": false,
        "type": "number",
        "desc": "Lat"
      },
      {
        "name": "status",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Status"
      },
      {
        "name": "sort_order",
        "in": "body",
        "required": false,
        "type": "integer",
        "desc": "Sort Order"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"school_client_id\": 0,\n  \"name\": \"...\",\n  \"status\": \"下单\"\n}"
  },
  "GET /api/operation/tickets": {
    "auth": true,
    "summary": "List Tickets",
    "params": [
      {
        "name": "status",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "type",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      }
    ],
    "resNote": "返回列表 / 数组"
  },
  "POST /api/operation/tickets/{id}/resolve": {
    "auth": true,
    "summary": "Resolve Complaint Ticket",
    "params": [
      {
        "name": "ticket_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      },
      {
        "name": "resolution",
        "in": "body",
        "required": true,
        "type": "string",
        "desc": "Resolution"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"resolution\": \"...\"\n}"
  },
  "GET /api/monitor/neural/overview": {
    "auth": true,
    "summary": "Monitor Neural Overview",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "GET /api/monitor/neural/audit-chain": {
    "auth": true,
    "summary": "Monitor Neural Audit Chain",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "GET /api/monitor/neural/mining": {
    "auth": true,
    "summary": "Monitor Neural Mining",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "GET /api/monitor/alerts": {
    "auth": true,
    "summary": "Monitor Alerts",
    "params": [
      {
        "name": "level",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "status",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "page",
        "in": "query",
        "required": false,
        "type": "integer",
        "desc": ""
      },
      {
        "name": "page_size",
        "in": "query",
        "required": false,
        "type": "integer",
        "desc": ""
      }
    ],
    "resNote": "返回列表 / 数组"
  },
  "PUT /api/monitor/alerts/{id}/close": {
    "auth": true,
    "summary": "Close Alert",
    "params": [
      {
        "name": "alert_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "GET /api/monitor/audit-logs": {
    "auth": true,
    "summary": "Monitor Audit Logs",
    "params": [
      {
        "name": "category",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "action",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      }
    ],
    "resNote": "返回列表 / 数组"
  },
  "POST /api/monitor/broadcasts": {
    "auth": true,
    "summary": "Create Monitor Broadcast",
    "params": [
      {
        "name": "title",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Title"
      },
      {
        "name": "content",
        "in": "body",
        "required": true,
        "type": "string",
        "desc": "Content"
      },
      {
        "name": "priority",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Priority"
      },
      {
        "name": "target_type",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Target Type"
      },
      {
        "name": "roles",
        "in": "body",
        "required": false,
        "type": "string[]",
        "desc": "Roles"
      },
      {
        "name": "user_ids",
        "in": "body",
        "required": false,
        "type": "integer[]",
        "desc": "User Ids"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"content\": \"...\"\n}"
  },
  "POST /api/chat/stream": {
    "auth": true,
    "summary": "Chat Stream",
    "params": [
      {
        "name": "session_id",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Session Id"
      },
      {
        "name": "message",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Message"
      },
      {
        "name": "messages",
        "in": "body",
        "required": false,
        "type": "ChatMessage[]",
        "desc": "Messages"
      },
      {
        "name": "stream",
        "in": "body",
        "required": false,
        "type": "boolean",
        "desc": "Stream"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "POST /api/zgncpjgw/analytics/briefing": {
    "auth": true,
    "summary": "Analytics Briefing",
    "params": [],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "GET /api/zgncpjgw/analytics/forecast/status": {
    "auth": true,
    "summary": "Analytics Forecast Status",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "POST /api/xinfadi/crawl": {
    "auth": true,
    "summary": "Crawl",
    "params": [
      {
        "name": "date",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "POST /api/xinfadi/predict/retrain": {
    "auth": true,
    "summary": "Retrain",
    "params": [
      {
        "name": "product_name",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      },
      {
        "name": "product",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "POST /api/smart-scale-recognition/recognize": {
    "auth": true,
    "summary": "Recognize Image",
    "params": [],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "POST /api/smart-scale-recognition/train": {
    "auth": true,
    "summary": "Start Training",
    "params": [
      {
        "name": "epochs",
        "in": "body",
        "required": false,
        "type": "integer",
        "desc": "Epochs"
      },
      {
        "name": "batch_size",
        "in": "body",
        "required": false,
        "type": "integer",
        "desc": "Batch Size"
      },
      {
        "name": "min_samples_per_class",
        "in": "body",
        "required": false,
        "type": "integer",
        "desc": "Min Samples Per Class"
      },
      {
        "name": "notes",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Notes"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "GET /api/delivery-sort/today": {
    "auth": true,
    "summary": "Delivery Sort Today",
    "params": [
      {
        "name": "delivery_date",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      }
    ],
    "resNote": "返回列表 / 数组"
  },
  "POST /api/delivery-sort/scan": {
    "auth": true,
    "summary": "Delivery Sort Scan",
    "params": [
      {
        "name": "barcode_value",
        "in": "body",
        "required": true,
        "type": "string",
        "desc": "Barcode Value"
      },
      {
        "name": "device_code",
        "in": "body",
        "required": false,
        "type": "string",
        "desc": "Device Code"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"barcode_value\": \"...\"\n}"
  },
  "POST /api/driver/login": {
    "auth": false,
    "summary": "Driver Login",
    "params": [
      {
        "name": "vehicle_no",
        "in": "body",
        "required": true,
        "type": "string",
        "desc": "Vehicle No"
      },
      {
        "name": "password",
        "in": "body",
        "required": true,
        "type": "string",
        "desc": "Password"
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）",
    "reqExample": "{\n  \"vehicle_no\": \"...\",\n  \"password\": \"demo123\"\n}"
  },
  "GET /api/driver/trips/today": {
    "auth": true,
    "summary": "Driver Today Trips",
    "params": [
      {
        "name": "planning_date",
        "in": "query",
        "required": false,
        "type": "string",
        "desc": ""
      }
    ],
    "resNote": "返回列表 / 数组"
  },
  "POST /api/driver/trips/{id}/start": {
    "auth": true,
    "summary": "Driver Start Trip",
    "params": [
      {
        "name": "trip_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "POST /api/driver/stops/{id}/deliver": {
    "auth": true,
    "summary": "Driver Deliver Stop",
    "params": [
      {
        "name": "stop_id",
        "in": "path",
        "required": true,
        "type": "integer",
        "desc": ""
      }
    ],
    "resNote": "返回操作结果对象（含更新计数 / 状态）"
  },
  "GET /api/system/healthz": {
    "auth": false,
    "summary": "Healthz",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "GET /api/system/readyz": {
    "auth": false,
    "summary": "Readyz",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "GET /api/system/downloads/manifest": {
    "auth": false,
    "summary": "Download Manifest",
    "params": [],
    "resNote": "返回列表 / 数组"
  },
  "GET /api/system/files/minio/{name}": {
    "auth": false,
    "summary": "Download Minio File",
    "params": [
      {
        "name": "object_name",
        "in": "path",
        "required": true,
        "type": "string",
        "desc": ""
      }
    ],
    "resNote": "返回该资源的详情对象"
  }
}

export const CORE_RESPONSES = {
  "POST /api/auth/login": "{\n  \"token\": \"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...\",\n  \"role\": \"client\"\n}",
  "POST /api/orders": "{\n  \"id\": 2536,\n  \"order_no\": \"OD03075442959998\",\n  \"status\": \"下单\",\n  \"total_amount\": 136.00,\n  \"version\": 1\n}",
  "POST /api/orders/{id}/ship": "{ \"message\": \"分包发货已登记\" }",
  "POST /api/orders/{id}/pickup": "{ \"message\": \"确认取货\" }",
  "POST /api/orders/{id}/receive": "{ \"message\": \"收货完成并已入账\" }",
  "POST /api/orders/{id}/settle": "{\n  \"id\": 2536,\n  \"order_no\": \"OD03075442959998\",\n  \"status\": \"已结算\",\n  \"version\": 6\n}",
  "GET /api/supplier/home": "{\n  \"message\": \"ok\",\n  \"module\": \"supplier\",\n  \"todo\": {\n    \"pending_ship_orders\": 2,\n    \"in_progress_orders\": 107,\n    \"receivable_unsettled\": 713.04\n  }\n}",
  "GET /api/supplier/orders": "[\n  {\n    \"id\": 2540,\n    \"order_no\": \"OD0401...\",\n    \"client_name\": \"北京第一实验小学\",\n    \"delivery_name\": \"中农食运物流\",\n    \"supply_portion_amount\": 118.41,\n    \"expected_delivery_date\": \"2026-06-04\",\n    \"supplier_status\": \"pending_ship\",\n    \"supplier_status_text\": \"待发货\",\n    \"has_abnormal\": false\n  }\n]",
  "POST /api/delivery/smart-split/commit": "{\n  \"message\": \"ok\",\n  \"created\": 6,\n  \"order_ids\": [2540, 2541]\n}",
  "POST /api/bills/statements/{id}/settle": "{\n  \"message\": \"已结清\",\n  \"settled_amount\": 206.60,\n  \"status\": \"已结清\"\n}",
  "PUT /api/monitor/alerts/{id}/close": "{ \"message\": \"ok\" }"
}
