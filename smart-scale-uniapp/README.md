# 大综 · 智能收货（UniApp）

位于 `dazong` 仓库内的 **独立子工程**，与根目录 `frontend/`（Vue 运营/客户端 Web）并行，用于 **Android Pad APK**。

## 目录说明


| 路径                                    | 说明                                 |
| ------------------------------------- | ---------------------------------- |
| `../design-reference-scaletrack-pro/` | AI Studio 的 React 原型，仅对照样式与流程      |
| `src/config.ts`                       | 配置 `API_BASE`，真机请改为电脑局域网 IP 或服务器域名 |
| `src/utils/request.ts`                | 请求封装，Bearer Token 存 `dazong_token` |


## 本地运行

```bash
cd smart-scale-uniapp
npm install
# 页面使用 <style lang="scss">，需 devDependency「sass」（已写入 package.json）
npm run dev:h5          # 浏览器快速看界面；H5 默认走 .env.development 的 /api + Vite 代理，避免 CORS
# 或
npm run dev:app-android # 需本机 Android SDK / HBuilderX 真机运行环境
```

## 与后端对接

- 登录：`POST /api/auth/login`（字段 `username` / `password`）
- 订单列表：`GET /api/orders?created_date_start=...&created_date_end=...`（`client` 角色）

## 自更新（仅 App，不上架商店）

- 启动时请求：`GET /api/system/smart-scale-app/version`（与 `API_BASE` 同源，内网/外网由 `VITE_API_BASE` 决定）。
- 当 `**version_code` > 本机 `manifest` 的 `versionCode**`，且配置了 `**apk_url` 或 `wgt_url**` 时，弹窗提示下载；**优先 wgt**（热更），否则整包 **apk**。
- 后端在 `**backend/.env`**（或部署环境变量）中配置：`SMART_SCALE_APP_VERSION_CODE`、`SMART_SCALE_APP_VERSION_NAME`、`SMART_SCALE_APP_APK_URL` / `SMART_SCALE_APP_WGT_URL`、`SMART_SCALE_APP_FORCE_UPDATE`、`SMART_SCALE_APP_NOTES`。发版时：**递增 `versionCode`（与 manifest 一致）+ 上传新包到可访问 URL + 改环境变量**，Pad 联网启动即可收到提示。
- **外网上线**：把 `VITE_API_BASE` 改为 `https://域名/api`，并把 `**SMART_SCALE_APP_*` 里的下载地址改为 https**；同时在后端 `**CORS_ORIGINS`** 中加入 Pad/Web 来源（若需要）。

**H5 在浏览器里登录失败时**：页面源是 `http://localhost:5173`，若后端 `CORS_ORIGINS` 未包含该带端口地址，浏览器会拦截跨域请求（与账号密码是否正确无关）。仓库已在 `backend/config.py` 默认加入 `:5173`；若你改过 `.env`，请自行追加 `http://localhost:5173`，并**重启后端**。

## 打包 APK

### 方式 A：云打包（推荐，无需本机 Android SDK）

1. **HBuilderX** 打开目录：`smart-scale-uniapp`（或终端执行：`open -a "HBuilderX" "/Users/Admin/Project/dazong/smart-scale-uniapp"`）。
2. 菜单 **发行 → 原生 App-云打包** → 勾选 **Android**、格式 **apk** → 使用与控制台一致的 DCloud 账号登录。
3. **证书**：先试「公共测试证书」；正式环境再换自有证书。
4. 等待队列完成 → **下载 APK** → 拷到 Pad 安装。

#### 方式 A'：命令行触发云打包（无需点「发行」菜单）

已提供脚本（与菜单云打包等价，使用**公共测试证书**、包名 `io.dazong.smartscale`）：

```bash
cd /Users/Admin/Project/dazong/smart-scale-uniapp
./scripts/cloud-pack-android.sh
```

若输出 **「正在下载依赖插件，请稍后重试」**：请先打开 **HBuilderX**，等右下角/控制台相关插件下载完成，或先手动打开一次 **发行 → 原生 App-云打包** 让环境就绪，再重跑脚本。

**说明**：任何工具都**无法替你完成 DCloud 网页登录、短信验证、阅读打包队列结果**；CLI 只能代替「点发行」这一步。

**若曾提示「cli 与正在运行的 HBuilderX 不匹配」**：说明你混用了 **不同路径的两份 HBuilderX**（常见：`/Volumes/...` 外置版 vs `/Applications/...`）。请**只保留一种用法**：要么始终从外置盘启动并只用外置盘里的 `cli`，要么把 HBuilderX 安装进「应用程序」并只用 `/Applications/.../cli`。

**若提示 `update/plugins`「打开权限不足」**（无法下载 **uni-app (vue3) 编译器**）：常见原因是 **从 DMG/只读卷运行 HBuilderX**。优先方案：**把 `HBuilderX.app` 复制到「应用程序」再打开**。也可在本机「终端」执行（需输入密码）：`bash scripts/fix-hbuilderx-volume-permissions.sh`（脚本在 `smart-scale-uniapp/scripts/`）。

### 方式 B：命令行先打资源包（已在仓库验证可过）

在项目根执行：

```bash
cd smart-scale-uniapp && npm run build:app-android
```

成功后产物在 `**dist/build/app/**`。若走 DCloud **离线 SDK** 打包，按官方说明在 HBuilderX 中 **导入该目录** 再继续（见构建结束日志提示）。

### `appid` 是什么？（必须你本人登录 DCloud 一次）

- **AppID** 是 DCloud 开发者中心给每个应用发的唯一标识（一般形如 `__UNI__` + 一串字符），**云打包、部分统计能力依赖它**。
- **我无法替你生成有效 AppID**（需要你的 DCloud 账号在 [dev.dcloud.net.cn](https://dev.dcloud.net.cn) 里「创建应用」）。
- 仓库里 `src/manifest.json` 的 `appid` 已与 DCloud 控制台一致（如更换应用请在控制台创建后同步修改）。

### 真机后端地址（已写入 `.env.production`）

- 已按本机检测填为：`VITE_API_BASE=http://192.168.5.3:8000/api`（与 Docker `backend` 映射 `8000` 一致，Pad 与电脑需同一局域网）。
- 换 WiFi / 换电脑后，请改 IP；若上公网，改为 `https://你的域名/api` 后重新打 release 包。

