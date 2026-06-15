#!/bin/sh
set -e

echo ">>> demo-console: npm install + build (base=/demo-console/)"
cd /demo-console
npm install --no-audit --no-fund
VITE_BASE_PATH=/demo-console/ npm run build

echo ">>> frontend: npm install + vite dev"
cd /app
npm install
exec npm run dev -- --host 0.0.0.0 --port 80
