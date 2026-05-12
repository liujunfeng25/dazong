/*
 * @Descripttion:
 * @version: 1.0.0
 * @Author: htang
 * @Date: 2024-07-15 16:33:33
 * @LastEditors: htang
 * @LastEditTime: 2024-08-24 14:38:23
 */
import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";
import path from "path";

const TimeStamp = new Date().getTime();

function resolve(url) {
  return path.resolve(__dirname, url);
}
// https://vitejs.dev/config/
export default ({ mode }) => {
  // 获取环境变量
  const env = loadEnv(mode, process.cwd());
  const isProd = mode === "production";
  return defineConfig({
    base: isProd ? "/tianshu/" : "./",
    assetsInclude: [
      "**/*.glb",
      "**/*.gltf",
      "**/*.fbx",
      "**/*.hdr",
      "**/*.json",
      "**/*.mp4",
      "**/*.mov",
    ],
    resolve: {
      alias: {
        "@": resolve("./src"),
        "~@": resolve("./src"),
      },
      // 省略文件后缀
      extensions: [".mjs", ".js", ".jsx", ".json"],
    },
    build: {
      minify: 'esbuild',
      target: 'es2015',
      cssTarget: 'chrome80',
      outDir: "../public/tianshu",
      emptyOutDir: true,
      terserOptions: {
        compress: {
          // keep_infinity: true,
          // // Used to delete console in production environment
          // drop_console: VITE_DROP_CONSOLE,
          // drop_debugger: true,
        },
      },
      // Turning off brotliSize display can slightly reduce packaging time
      reportCompressedSize: false,
      chunkSizeWarningLimit: 2000,
      rollupOptions: {
        // 参考：https://blog.cinob.cn/archives/393
        output: {
          // 入口文件名
          entryFileNames: `assets/[name]-${TimeStamp}.js`,
          // 块文件名
          chunkFileNames: `assets/[name]-[hash]-${TimeStamp}.js`,
          // 资源文件名 css 图片等等
          assetFileNames: `assets/[name]-[hash]-balabala-${TimeStamp}.[ext]`,
        }
      }
    },
    envDir: 'env',
    plugins: [vue()],
    // 天枢请求同源 `/api/insights/business/*`；独立 `vite dev` 时须转发到主站 FastAPI，否则会 404，
    // 订单光柱拉取失败，场上只剩模板 createFocus（flyLineCenter 在东城附近）易被误认为「demo 柱」。
    server: {
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
          ws: true,
        },
      },
    },
  });
};
