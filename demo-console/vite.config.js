import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const proxyTarget = process.env.VITE_API_PROXY || "http://127.0.0.1:8000";

export default defineConfig({
  // Docker 下挂到 http://127.0.0.1/demo-console/ 时由构建参数 VITE_BASE_PATH=/demo-console/ 注入
  base: process.env.VITE_BASE_PATH || "/",
  plugins: [vue()],
  server: {
    port: 15175,
    strictPort: true,
    proxy: {
      "/api": {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
});
