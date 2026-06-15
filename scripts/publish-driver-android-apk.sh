#!/usr/bin/env bash
# 将司机端 Android APK 复制到 apk-share，文件名带时间戳，并更新 driver-android-latest 软链。
# 用法：bash scripts/publish-driver-android-apk.sh /Users/Admin/Project/driver-android/app/build/outputs/apk/debug/app-debug.apk
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/apk-share"
mkdir -p "$DEST"

if [[ $# -lt 1 || ! -f "$1" ]]; then
  echo "用法: $0 <司机端.apk路径>" >&2
  exit 1
fi

TS="$(date +%Y%m%d%H%M%S)"
name="driver-android-${TS}.apk"
cp "$1" "$DEST/$name"
ln -sf "$name" "$DEST/driver-android-latest.apk"
echo "已发布: $DEST/$name"
echo "软链:   $DEST/driver-android-latest.apk -> $name"
echo "固定下载 URL 使用 .../driver-android-latest.apk"
