#!/bin/bash
# M5Stack Basicにファームウェアをデプロイするスクリプト
# 使い方: ./scripts/deploy.sh [シリアルポート]

PORT="${1:-/dev/cu.usbserial-01BB96F8}"

if [ -z "$PORT" ]; then
    echo "エラー: シリアルポートを指定してください"
    echo "使い方: ./scripts/deploy.sh /dev/cu.usbserial-XXXX"
    exit 1
fi

echo "=== Kiro Buddy ファームウェアデプロイ ==="
echo "ポート: $PORT"
echo ""

# ファイル転送
echo "[1/3] ili9342c.py を転送中..."
uv run mpremote connect "$PORT" cp firmware/ili9342c.py :ili9342c.py

echo "[2/3] Kiroキャラクターを転送中..."
uv run mpremote connect "$PORT" cp firmware/assets/kiro_bw_96x96.bmp :/kiro_bw_96x96.bmp
uv run mpremote connect "$PORT" cp firmware/assets/kiro_bw_96x96_left.bmp :/kiro_bw_96x96_left.bmp

echo "[3/3] main.py を転送中..."
uv run mpremote connect "$PORT" cp firmware/main.py :main.py

echo ""
echo "リセット中..."
uv run mpremote connect "$PORT" reset

echo ""
echo "✓ デプロイ完了！M5Stackが再起動します。"
