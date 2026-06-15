#!/bin/sh
set -e

if [ -n "${MYSQL_HOST:-}" ]; then
  echo ">>> waiting for MySQL at ${MYSQL_HOST}:${MYSQL_PORT:-3306} ..."
  i=0
  while [ "$i" -lt 60 ]; do
    if python -c "
import socket, os, sys
h = os.environ.get('MYSQL_HOST', 'mysql')
p = int(os.environ.get('MYSQL_PORT', '3306'))
s = socket.socket()
s.settimeout(2)
try:
    s.connect((h, p))
    sys.exit(0)
except OSError:
    sys.exit(1)
finally:
    s.close()
" 2>/dev/null; then
      echo ">>> MySQL is up"
      break
    fi
    i=$((i + 1))
    sleep 2
  done
fi

# 开发镜像可能较旧，缺 playwright 时自动补齐（中农价格网 WAF 引导）
if ! python -c "import playwright" 2>/dev/null; then
  echo ">>> installing playwright (zgncpjgw crawl) ..."
  pip install --default-timeout=600 -q \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    'playwright>=1.40' || true
fi
if python -c "import playwright" 2>/dev/null; then
  if [ ! -d /root/.cache/ms-playwright ] || [ -z "$(ls -A /root/.cache/ms-playwright 2>/dev/null)" ]; then
    echo ">>> installing playwright chromium ..."
    PLAYWRIGHT_DOWNLOAD_HOST="${PLAYWRIGHT_DOWNLOAD_HOST:-https://npmmirror.com/mirrors/playwright}" \
      python -m playwright install-deps chromium 2>/dev/null || true
    PLAYWRIGHT_DOWNLOAD_HOST="${PLAYWRIGHT_DOWNLOAD_HOST:-https://npmmirror.com/mirrors/playwright}" \
      python -m playwright install chromium 2>/dev/null || true
  fi
fi

exec "$@"
