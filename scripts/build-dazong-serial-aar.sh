#!/usr/bin/env bash
# 编译「大综串口读秤」DCloud 原生插件 AAR（需本机已装 JDK8+、Android SDK）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJ="$ROOT/smart-scale-uniapp/nativeplugins/dazong-serial-scale/android-library"
LIBS="$PROJ/serialplugin/libs"
OUT="$ROOT/smart-scale-uniapp/nativeplugins/dazong-serial-scale/android"

if [[ ! -f "$LIBS/uniapp-v8-release.aar" ]] && ! ls "$LIBS"/uniapp*.aar >/dev/null 2>&1; then
  echo "请先将 DCloud Android 离线 SDK 中 SDK/libs/uniapp-v8-release.aar 复制到：" >&2
  echo "  $LIBS" >&2
  exit 1
fi

if [[ -n "${ANDROID_HOME:-}" ]] && [[ ! -f "$PROJ/local.properties" ]]; then
  echo "sdk.dir=$ANDROID_HOME" >"$PROJ/local.properties"
fi

cd "$PROJ"
if [[ -x ./gradlew ]]; then
  ./gradlew :serialport:assembleRelease :serialplugin:assembleRelease
else
  gradle :serialport:assembleRelease :serialplugin:assembleRelease
fi

A1="$PROJ/serialport-lib/serialport/build/outputs/aar/serialport-release.aar"
A2="$PROJ/serialplugin/build/outputs/aar/serialplugin-release.aar"
if [[ ! -f "$A1" || ! -f "$A2" ]]; then
  echo "未找到编译输出" >&2
  exit 1
fi
cp -f "$A1" "$OUT/serialport-lib-release.aar"
cp -f "$A2" "$OUT/dazong-serial-scale.aar"
echo "已复制: $OUT/serialport-lib-release.aar（串口 JNI，云打包会合并）"
echo "已复制: $OUT/dazong-serial-scale.aar（业务 Module）"
echo "下一步：HBuilderX manifest → App 原生插件 → 勾选本地插件 dazong-serial-scale → 云打包"
