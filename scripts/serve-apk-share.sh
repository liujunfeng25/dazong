#!/usr/bin/env bash
# 在仓库根目录的 apk-share/ 起静态服务，默认端口 18080（与 backend/.env.example 中 ngrok 示例一致）。
# 用法：终端 A: bash scripts/serve-apk-share.sh
#       终端 B: ngrok http 18080
# 然后访问 ngrok 给出的 https 地址打开下载页；固定 APK 地址包括：
#   /smart-scale-android-latest.apk
#   /sorter-pda-latest.apk
#   /driver-android-latest.apk
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/apk-share"
PORT="${1:-18080}"
echo "apk-share 目录: $ROOT/apk-share"
echo "监听: http://0.0.0.0:$PORT"
echo "下载页: http://127.0.0.1:$PORT/"
echo "智能秤: http://127.0.0.1:$PORT/smart-scale-android-latest.apk"
echo "分检端: http://127.0.0.1:$PORT/sorter-pda-latest.apk"
echo "司机端: http://127.0.0.1:$PORT/driver-android-latest.apk"
exec python3 -m http.server "$PORT"
