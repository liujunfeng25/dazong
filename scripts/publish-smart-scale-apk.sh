#!/usr/bin/env bash
# 将云打包产物复制到 apk-share，文件名带打包时间戳，并更新 smart-scale-latest 软链（供 ngrok 固定 URL 下载）。
# 用法：bash scripts/publish-smart-scale-apk.sh path/to/__UNI__4049F04__20260507102630.apk
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/apk-share"
SRC="${1:-}"

if [[ -z "$SRC" || ! -f "$SRC" ]]; then
  echo "用法: $0 <云打包生成的.apk路径>" >&2
  exit 1
fi

base="$(basename "$SRC")"
# 从 __UNI__4049F04__20260507102630.apk 取 14 位时间戳
if [[ "$base" =~ __([0-9]{14})\.apk$ ]]; then
  TS="${BASH_REMATCH[1]}"
else
  TS="$(date +%Y%m%d%H%M%S)"
fi

mkdir -p "$DEST"
name="smart-scale-${TS}.apk"
cp -f "$SRC" "$DEST/$name"
ln -sf "$name" "$DEST/smart-scale-latest.apk"

echo "已发布: $DEST/$name"
echo "软链:   $DEST/smart-scale-latest.apk -> $name"
echo "固定下载 URL 仍用 .../smart-scale-latest.apk 即可。"
