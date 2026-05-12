#!/usr/bin/env bash
# 使用 HBuilderX 自带 CLI 触发 Android 云打包（公共测试证书）。
#
# 重要：「正在运行的 HBuilderX」与「本脚本调用的 cli」必须来自同一个 .app。
# - 若你从 /Volumes/HBuilderX 打开 HBX，请保持下面 CLI 优先用 Volumes 路径；
# - 若你从「应用程序」打开 HBX，请改用 /Applications/.../cli（或把 HBX 拷到应用程序里用一份）。

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

pick_cli() {
  # 优先与「应用程序」里的 HBuilderX 一致，避免与 /Volumes 下另一份 CLI 混用导致云打包失败
  for c in \
    "/Applications/HBuilderX.app/Contents/MacOS/cli" \
    "/Volumes/HBuilderX/HBuilderX.app/Contents/MacOS/cli"
  do
    if [[ -x "$c" ]]; then
      echo "$c"
      return 0
    fi
  done
  return 1
}

CLI="$(pick_cli)" || {
  echo "未找到 HBuilderX 的 cli。" >&2
  exit 1
}

echo "使用 CLI: $CLI"
"$CLI" open >/dev/null 2>&1 || true
sleep 3

# 云打包常用依赖（已在你环境验证可装成功；其余若失败可忽略）
for p in uniapp-basic uniapp-extension launcher launcher-tools; do
  echo ">>> installPlugin $p"
  "$CLI" installPlugin --name "$p" --force true 2>&1 || true
  sleep 1
done

echo ">>> pack android (公共测试证书)"
exec "$CLI" pack \
  --project "$ROOT" \
  --platform android \
  --android.packagename "io.dazong.smartscale" \
  --android.androidpacktype 1
