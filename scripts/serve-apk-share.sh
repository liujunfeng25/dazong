#!/usr/bin/env bash
# 在仓库根目录的 apk-share/ 起静态服务，默认端口 18080（与 backend/.env.example 中 ngrok 示例一致）。
# 用法：终端 A: bash scripts/serve-apk-share.sh
#       终端 B: ngrok http 18080
# 然后把 ngrok 给出的 https 地址 + /smart-scale-latest.apk 填到 backend .env 的 SMART_SCALE_APP_APK_URL。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/apk-share"
PORT="${1:-18080}"
echo "apk-share 目录: $ROOT/apk-share"
echo "监听: http://0.0.0.0:$PORT （本机: http://127.0.0.1:$PORT/smart-scale-latest.apk）"
exec python3 -m http.server "$PORT"
