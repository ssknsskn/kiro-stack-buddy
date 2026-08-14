#!/bin/bash
# M5Stack Basicにファームウェアをデプロイするスクリプト
# 使い方: ./scripts/deploy.sh /dev/cu.usbserial-XXXX

set -e

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
    echo "エラー: シリアルポートを指定してください"
    echo "使い方: ./scripts/deploy.sh /dev/cu.usbserial-XXXX"
    echo "例（Linux）: ./scripts/deploy.sh /dev/ttyACM0"
    exit 1
fi

PORT="$1"
ASSET_DIR="firmware/assets"
RIGHT_ASSET="$ASSET_DIR/kiro_bw_96x96.bmp"
LEFT_ASSET="$ASSET_DIR/kiro_bw_96x96_left.bmp"

if [ -z "$PORT" ]; then
    echo "エラー: シリアルポートを指定してください"
    echo "使い方: ./scripts/deploy.sh /dev/cu.usbserial-XXXX"
    exit 1
fi

for asset in "$RIGHT_ASSET" "$LEFT_ASSET"; do
    if [ ! -f "$asset" ]; then
        echo "エラー: 画像アセットがありません: $asset"
        echo "先に次のコマンドでユーザー提供画像から生成してください:"
        echo "  uv run python scripts/prepare_assets.py --input /path/to/your-image.png"
        exit 1
    fi
done

echo "=== Kiro Buddy ファームウェアデプロイ ==="
echo "ポート: $PORT"
echo ""

# ファイル転送
echo "[1/3] ili9342c.py を転送中..."
uv run mpremote connect "$PORT" cp firmware/ili9342c.py :ili9342c.py

echo "[2/3] Kiroキャラクターを転送中..."
uv run mpremote connect "$PORT" cp "$RIGHT_ASSET" :/kiro_bw_96x96.bmp
uv run mpremote connect "$PORT" cp "$LEFT_ASSET" :/kiro_bw_96x96_left.bmp

echo "[3/3] main.py を転送中..."
uv run mpremote connect "$PORT" cp firmware/main.py :main.py

echo ""
echo "リセット中..."
uv run mpremote connect "$PORT" reset

echo ""
echo "✓ デプロイ完了！M5Stackが再起動します。"
