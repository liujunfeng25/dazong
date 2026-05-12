import { defineConfig } from "vite";
import uni from "@dcloudio/vite-plugin-uni";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [uni()],
  server: {
    /** H5 开发：浏览器访问 /api → 本机 Docker backend，避免 localhost:5173 ↔ 127.0.0.1:8000 跨域 */
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
