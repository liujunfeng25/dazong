/** 与 dazong backend 对齐：开发时在 HBuilderX / manifest 配置里改真机可访问的基址 */
/**
 * - H5 开发：`.env.development` 里 `VITE_API_BASE=/api`，走 Vite 代理到 Docker `8000`，同源无 CORS。
 * - 真机 APK：在 `.env.production` 写完整 `https://域名/api` 或局域网 `http://IP:8000/api`。
 */
export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ||
  "http://127.0.0.1:8000/api";
