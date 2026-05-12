#!/usr/bin/env bash
# 启动横屏平板模拟器（需已通过 Homebrew 安装 android-commandlinetools + 系统镜像，并创建 AVD：DazongPad_Landscape）
set -euo pipefail
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
exec "$ANDROID_HOME/emulator/emulator" -avd DazongPad_Landscape -netdelay none -netspeed full "$@"
