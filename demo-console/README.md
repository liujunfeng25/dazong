# 演示数据 API 控制台（demo-console）

与主站 `frontend/` 平级的独立 **Vite + Vue 3 + Element Plus** 小应用，手机单列优先，用于演示环境批量登录、校验合约、`POST /orders` 造数，以及（在 `DEMO_MODE=true` 下）调用监管端演示辅助接口清场或推进分单状态。

**履约食堂（与主站下单一致）**：后端 `POST /orders` 要求采购方 JWT 已绑定食堂（`require_client_with_canteen`）。本控制台在**每个采购账号**登录后会自动请求 `GET /client/canteens`，再 `POST /client/canteen-session`：优先选用名为「默认食堂」的启用记录，否则取列表中第一个启用食堂，用返回的新 token 再调商品搜索与下单。若账号下无任何食堂，会提示先在运营端「客户食堂」维护。

## 启动

```bash
cd demo-console
npm install
npm run dev
```

默认开发服务：**http://127.0.0.1:15175**（见 `vite.config.js`）。

## Docker（与主站同端口，推荐）

根目录执行 `docker compose up -d --build` 后，演示控制台与主站共用 **80** 端口，访问：

- **http://127.0.0.1/demo-console/**（末尾建议带 `/`）

镜像在构建 `frontend` 时会顺带 `npm run build` 本目录，并设置 `VITE_BASE_PATH=/demo-console/`，由 `frontend/nginx.conf` 的 `location /demo-console/` 提供静态资源；**API 仍走同源 `/api`**，与主站一致，由 Nginx 反代到 `backend:8000`。

生产构建：

```bash
npm run build
# 静态文件在 dist/，可由任意静态服务器或 Nginx 托管
```

## 连接后端：代理（推荐）与 CORS

### 方式 A：Vite 代理（本地开发推荐）

`vite.config.js` 已将 `/api` 代理到后端，默认目标：

- `http://127.0.0.1:8000`（与仓库 `docker compose` 中 backend 映射一致）

若你的后端端口不同，可在启动前设置：

```bash
export VITE_API_PROXY=http://127.0.0.1:18000
npm run dev
```

页面上在 **「接口连到哪里」** 里选「跟当前打开的网站一套」时，请求走同源 `/api`，由 Vite 转发到上述目标，**无需改后端 CORS**。

### 方式 B：浏览器直连后端

在页面「API 根路径」填写完整根路径，例如 `http://127.0.0.1:8000/api`。

此时浏览器会跨域，需把演示页来源加入后端 `CORS_ORIGINS`（逗号分隔）。仓库已在 `backend/config.py` 默认加入：

- `http://localhost:15175`、`http://127.0.0.1:15175`

生产环境请在 `.env` 中覆盖并补充你的域名。

## 默认账号与推荐参数

与种子数据一致（`backend/database.py`）：

- 客户：`client001`～`client006`（种子自动建用户并为 `delivery001` 补演示合约），密码 `demo123`
- 配送商：`delivery001`（用于解析 `delivery_id`）
- 监管（演示辅助接口）：`monitor001` / `demo123`
- 智能分单专用演示供货商（`backend/database.py` 种子，后端 `seed_on_start=true` 启动时写入；密码均为 `demo123`）：
  - **`supplier_jingmuxian`**：京牧鲜冷鲜牛羊肉有限公司（演示）— 仅对一级分类 **「肉禽蛋」** 下商品维护报价（小幅波动）。
  - **`supplier_hanhua`**：瀚华副食商贸中心（演示）— 对 **除肉禽蛋、蔬菜以外** 的商品报价，且按商品 id 交替 **极低价 / 极高价**，便于观察分单引擎价格权重。

**推荐造数规模（喂饱智能分单 / 排线演示）**：

- 每客户订单数：3～8
- 每笔行数：5～12（与 `GET /orders/products/search` 的 `page_size` 上限配合）；**同一客户多笔**时会多页合并商品池，能分时用等距窗口错开 SKU，池子不够分时用「客户名+序号」种子打乱，并加大数量差异，避免 `%` 小模数导致的克隆单。
- 每行数量：1～3（体积/重量累计更明显时可略增）

页面默认 **每笔随机配送时段**（24 个整点一小时段之一，含 `23:00-24:00`）；关闭「每笔随机」后，固定时段须符合后端整点一小时格式（如 `09:00-10:00`）。合约须为「已中标」且同时覆盖 **今日** 与所选 **期望配送日**（与 `create_order` / `order_meta` 逻辑一致）。

## 演示相关 API

**客户列表（仅 `demo_mode`，无需登录）**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/demo/client-accounts` | 返回库中 `role=client` 且 `status=active` 的用户（公司名、地址、经纬度），演示控制台页面自动调用 |
| `GET` | `/api/demo/supplier-accounts` | 同上，返回 `role=supplier`；含 `supplier_delivery_id` 便于核对「多供货商绑定同一配送商」 |
| `POST` | `/api/demo/orders/supplier-ship-bulk` | body: `{ "order_ids": [...], "supplier_username": "supplier001" }`；**monitor**；将该供货商在上述订单中的分单行标为 **已出库**（演示跳过打印门禁，等同供货商端发货） |
| `POST` | `/api/demo/orders/supplier-ship-all` | body: `{ "order_ids": [...] }`；**monitor**；对订单所属配送商下**全部挂靠供货商**各执行一遍分单行→**已出库**（无需切换账号） |
| `POST` | `/api/demo/orders/mock-print-allocation-labels` | body: `{ "order_ids": [...] }`；**monitor**；为每条 `OrderItemAllocation` 写入与真接口一致的行级标签打印 **AuditLog**（演示用，不触发真实打印） |

**清场 / 改状态（`demo_mode` + 角色 `monitor`）**

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/demo/orders/delete` | body: `{ "order_ids": [1,2] }`，按依赖顺序级联删单 |
| `POST` | `/api/demo/orders/clear-all` | 无 body；删除库中 **全部** 订单及关联分单行、收货行、账单、配送、通知等（与脚本清场顺序对齐） |
| `POST` | `/api/demo/orders/mark-allocations-shipped` | body 同上，将订单下全部分单行 `status` 置为 **已出库** |

删单、标已出库需先在页面「监管登录」获取 token。按 ID 删单需二次确认并输入 `DELETE`；一键清空全部订单需输入 `CLEAR ALL`。

自测（选品+数量不撞单）：`npm run verify:order-diversity`

## 与主站下单 / 智能分单的关系

- 批量下单走真实 `POST /orders`；对每个采购账号会先完成**食堂会话**（见上文），再带食堂 JWT 造数。页面默认开启「仅合约内一级分类商品」时，会带 `contract_categories_only` + `expected_delivery_date` 调用 `GET /orders/products/search`，与下单时的合约校验一致，一般无需再开 `force`。
- **智能分单**、**智能排线**在主站配送商端（`/delivery/smart-split`、`/delivery/smart-routing`），不在本控制台；控制台负责造数、清库与演示发货。
- 智能分单要求行上商品至少有一家「挂靠该配送商」的供货商维护报价（指定厂家商品除外）；否则请在运营端或种子数据补报价。

## 技术说明

- Element Plus 固定为 **2.8.8**（避免个别环境下包体不完整导致 Vite 无法解析入口）。
- 经纬度在种子坐标上做微小累加偏移，避免多笔订单完全同点。
