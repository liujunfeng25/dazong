#!/usr/bin/env bash
# 解决：从 /Volumes/HBuilderX 启动时，提示 update/plugins「打开权限不足」
# 用法：在「终端.app」里执行（会提示输入本机密码）：
#   bash /Users/Admin/Project/dazong/smart-scale-uniapp/scripts/fix-hbuilderx-volume-permissions.sh

set -euo pipefail
VOL_APP="/Volumes/HBuilderX/HBuilderX.app"
UPD="${VOL_APP}/Contents/HBuilderX/update"

if [[ ! -d "$VOL_APP" ]]; then
  echo "未找到外置路径: $VOL_APP（可能盘符不同，请自行改脚本里的路径）" >&2
  exit 1
fi

echo ">>> 尝试创建可写目录并授权（需管理员密码）"
sudo mkdir -p "${UPD}/plugins"
sudo chown -R "$(whoami):staff" "${VOL_APP}/Contents/HBuilderX"
sudo chmod -R u+rwX "${VOL_APP}/Contents/HBuilderX/update" 2>/dev/null || true

if touch "${UPD}/plugins/.write_test" 2>/dev/null; then
  rm -f "${UPD}/plugins/.write_test"
  echo ">>> 已可写，请重启 HBuilderX 后再试「发行」或云打包。"
  exit 0
fi

echo ""
echo ">>> 仍无法写入：多半是 **DMG/只读卷**。请改用下面任一方式（二选一）："
echo "    A) 把 HBuilderX.app 拖到「应用程序」文件夹，以后只从应用程序里打开；"
echo "    B) 从 DCloud 官网重新下载 .dmg，安装进应用程序（不要长期从镜像卷里运行）。"
echo ""
exit 1
