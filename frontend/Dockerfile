# 构建上下文为仓库根目录（docker-compose build.context: .），以便同时打包主站与 demo-console

FROM node:20-alpine AS demo-console-builder
WORKDIR /demo
COPY demo-console/package*.json ./
RUN npm install
COPY demo-console/ ./
ENV VITE_BASE_PATH=/demo-console/
RUN npm run build

FROM node:20-alpine AS frontend-builder
WORKDIR /app

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build

FROM nginx:alpine

COPY --from=frontend-builder /app/dist /usr/share/nginx/html
COPY --from=demo-console-builder /demo/dist /usr/share/nginx/html/demo-console
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
