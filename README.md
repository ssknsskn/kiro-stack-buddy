# Kiro Stack Buddy

M5Stack BasicにKiroキャラクターを表示するデスクペットプロジェクトです。現在は、Kiro画像の表示とアニメーションを実機で確認する段階まで実装しています。

## 現在できること

- M5Stack Basic（320×240、ILI9342C）へのKiro表示
- `kiro.png`を加工した96×96 RGB565 BMPの表示
- 右向き・左向き画像の切り替え
- 4種類のテストアニメーション
- 中央ボタンBによるアニメーション切り替え
- 黒背景での差分描画と、walk専用の最小領域更新
- M5Stackへの自動デプロイ

アニメーションは中央ボタンBを押すたびに次の順で切り替わります。

```text
idle → walk → look → completed → idle
```

| パターン | 動き |
|---|---|
| `idle` | 中央付近で小さく左右に揺れる |
| `walk` | 画面内を左右に移動し、移動方向に応じて向きを変える |
| `look` | その場で左右を向く |
| `completed` | 中央で素早く上下に跳ねる |

## ハードウェアと環境

- M5Stack Basic / ESP32
- 320×240 ILI9342C LCD
- MicroPython v1.25.0
- macOS
- Python 3.13以上
- `uv`
- `mpremote`

## セットアップ

```bash
uv sync
```

M5StackへMicroPython v1.25.0を書き込んだ後、USB接続してデプロイします。

```bash
./scripts/deploy.sh /dev/cu.usbserial-XXXX
```

デプロイスクリプトは次のファイルを転送します。

- `firmware/ili9342c.py`
- `firmware/main.py`
- `firmware/assets/kiro_bw_96x96.bmp`
- `firmware/assets/kiro_bw_96x96_left.bmp`

## 手動デプロイ

```bash
uv run mpremote connect /dev/cu.usbserial-XXXX \
  cp firmware/ili9342c.py :ili9342c.py

uv run mpremote connect /dev/cu.usbserial-XXXX \
  cp firmware/assets/kiro_bw_96x96.bmp :/kiro_bw_96x96.bmp

uv run mpremote connect /dev/cu.usbserial-XXXX \
  cp firmware/assets/kiro_bw_96x96_left.bmp :/kiro_bw_96x96_left.bmp

uv run mpremote connect /dev/cu.usbserial-XXXX \
  cp firmware/main.py :main.py

uv run mpremote connect /dev/cu.usbserial-XXXX reset
```

## BLEブリッジとKiro Hook

`bridge/server.py` は、Kiro HookからHTTPでイベントを受け取り、Nordic UART Service経由でM5Stackへ送るためのブリッジです。`.kiro/hooks/`には、SessionStart、Stop、PreToolUse、PostToolUse、PostFileSave用のHook設定があります。

```bash
./scripts/run_bridge.sh
```

HTTPエンドポイントは次のとおりです。

```bash
curl http://127.0.0.1:9876/status

curl -X POST http://127.0.0.1:9876/event \
  -H "Content-Type: application/json" \
  -d '{"session_status":"in_progress","msg":"working..."}'
```

> 注意：現時点の`firmware/main.py`は表示・ボタン・アニメーションの実機確認を優先した構成です。BLEから受信したセッション状態をファームウェアへ反映する処理は次の実装課題です。

## 画像素材

元画像と、これまでの検証で作成した画像は`firmware/assets/`に残しています。現在M5Stackが使用する素材は次の2つです。

```text
firmware/assets/kiro_bw_96x96.bmp
firmware/assets/kiro_bw_96x96_left.bmp
```

画像はPC側で白黒化・左右反転し、RGB565のBMPへ変換しています。MicroPython側にPNG/JPGデコーダーを追加せず、単純なファイル形式で表示する方針です。

## プロジェクト構成

```text
kiroStack/
├── .kiro/hooks/                         # Kiro IDE Hook設定
├── bridge/
│   └── server.py                         # HTTP + BLEブリッジ
├── documents/
│   └── kiro-buddy-development.md        # 開発記録・ブログ用記事
├── firmware/
│   ├── main.py                           # 表示・ボタン・アニメーション
│   ├── ili9342c.py                       # LCDドライバ
│   └── assets/                            # Kiro画像素材
├── scripts/
│   ├── deploy.sh                         # M5Stackデプロイ
│   └── run_bridge.sh                     # ブリッジ起動
├── pyproject.toml
├── uv.lock
└── README.md
```

## 検証

ホスト側の構文チェック：

```bash
python3 -m py_compile firmware/main.py
python3 -m py_compile bridge/server.py
bash -n scripts/deploy.sh
```

M5Stackでは、LCD初期化、BMPロード、メインループ、中央ボタン入力をシリアルログで確認しています。

## 今後の課題

- BLE受信処理を`firmware/main.py`へ追加
- 受信したセッション状態とアニメーションを接続
- LCD更新のちらつきをさらに低減
- BLEブリッジの接続・再接続テスト
