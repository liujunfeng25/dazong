import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import UnoCSS from 'unocss/vite'
import { createReadStream, existsSync, statSync } from 'node:fs'
import { join, extname } from 'node:path'

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript',
  '.css':  'text/css',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
  '.woff2':'font/woff2',
  '.woff': 'font/woff',
  '.json': 'application/json',
}

// Docker 挂载 ./demo-console → /demo-console；本地开发时可通过环境变量覆盖
const DEMO_DIST = process.env.DEMO_CONSOLE_DIST ?? '/demo-console/dist'
// tianshu 子项目构建输出：./frontend/public/tianshu → 容器内 /app/public/tianshu
const TIANSHU_DIST = join(new URL('.', import.meta.url).pathname, 'public/tianshu')
const DOWNLOADS_DIST = join(new URL('.', import.meta.url).pathname, 'public/downloads')

export default defineConfig({
  plugins: [
    vue(),
    UnoCSS(),
    {
      name: 'serve-demo-console',
      configureServer(server) {
        server.middlewares.use('/demo-console', (req, res, next) => {
          let urlPath = req.url ?? '/'
          // 先去掉 query/hash，再判空；解码 percent-encoded（中文等非 ASCII 文件名）
          urlPath = urlPath.split('?')[0].split('#')[0]
          if (urlPath === '' || urlPath === '/') urlPath = '/index.html'
          try { urlPath = decodeURIComponent(urlPath) } catch { /* keep raw */ }
          let filePath = join(DEMO_DIST, urlPath)
          if (!existsSync(filePath) || !statSync(filePath).isFile()) filePath = join(DEMO_DIST, 'index.html')
          if (!existsSync(filePath) || !statSync(filePath).isFile()) return next()
          res.setHeader('Content-Type', MIME[extname(filePath)] ?? 'application/octet-stream')
          // 避免浏览器长期缓存旧 bundle，演示页文案更新后「看起来没变化」
          res.setHeader('Cache-Control', 'no-store, must-revalidate')
          createReadStream(filePath).pipe(res)
        })
      },
    },
    {
      name: 'serve-downloads-index',
      configureServer(server) {
        server.middlewares.use('/downloads', (req, res, next) => {
          let urlPath = req.url ?? '/'
          urlPath = urlPath.split('?')[0].split('#')[0]
          if (urlPath === '' || urlPath === '/') urlPath = '/index.html'
          try { urlPath = decodeURIComponent(urlPath) } catch { /* keep raw */ }
          const filePath = join(DOWNLOADS_DIST, urlPath)
          if (!existsSync(filePath) || !statSync(filePath).isFile()) return next()
          res.setHeader('Content-Type', MIME[extname(filePath)] ?? 'application/octet-stream')
          res.setHeader('Cache-Control', 'no-store')
          createReadStream(filePath).pipe(res)
        })
      },
    },
    {
      name: 'serve-tianshu',
      configureServer(server) {
        server.middlewares.use('/tianshu', (req, res, next) => {
          let urlPath = req.url ?? '/'
          urlPath = urlPath.split('?')[0].split('#')[0]
          if (urlPath === '' || urlPath === '/') urlPath = '/index.html'
          try { urlPath = decodeURIComponent(urlPath) } catch { /* keep raw */ }
          const filePath = join(TIANSHU_DIST, urlPath)
          if (!existsSync(filePath) || !statSync(filePath).isFile()) return next()
          const ct = MIME[extname(filePath)] ?? 'application/octet-stream'
          res.setHeader('Content-Type', ct)
          res.setHeader('Cache-Control', 'no-store')
          createReadStream(filePath).pipe(res)
        })
      },
    },
  ],
  server: {
    host: '0.0.0.0',
    allowedHosts: ['unavailed-arie-monohydroxy.ngrok-free.dev', 'staleness-catalyze-starting.ngrok-free.dev'],
    port: 15173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://backend:8000',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
    },
  },
})
