#!/usr/bin/env bash
# 将分检 PDA Android APK 复制到 apk-share，文件名带时间戳，并更新 sorter-pda-latest 软链。
# 用法：bash scripts/publish-sorter-pda-apk.sh /Users/Admin/Project/sorter-pda-android/app/build/outputs/apk/debug/app-debug.apk
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/apk-share"
SRC="${1:-}"

if [[ -z "$SRC" || ! -f "$SRC" ]]; then
  echo "用法: $0 <分检端.apk路径>" >&2
  exit 1
fi

TS="$(date +%Y%m%d%H%M%S)"
mkdir -p "$DEST"
name="sorter-pda-${TS}.apk"
cp -f "$SRC" "$DEST/$name"
ln -sf "$name" "$DEST/sorter-pda-latest.apk"

echo "已发布: $DEST/$name"
echo "软链:   $DEST/sorter-pda-latest.apk -> $name"
echo "固定下载 URL 使用 .../sorter-pda-latest.apk"
