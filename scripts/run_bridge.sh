#!/bin/bash
# BLEブリッジサーバーを起動するスクリプト
cd "$(dirname "$0")/.."
echo "=== Kiro Buddy BLE Bridge ==="
echo "HTTPサーバー: http://127.0.0.1:9876"
echo "Ctrl+C で停止"
echo ""
uv run python -m bridge.server
