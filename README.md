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
- 画面下部に`BRIDGE CONNECTED` / `BRIDGE OFFLINE`と`BLE: ON` / `BLE: OFF`を表示
- 作業中の状態名は`WORKING`と表示
- Bridge未接続時は、その場で左右を見る`look`アニメーションを表示

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

`bridge/server.py`は、Kiro HookからHTTPでイベントを受け取り、最新のKiro状態をNordic UART Service（NUS）経由でM5Stackへ送るローカルブリッジです。`.kiro/hooks/`には、SessionStart、Stop、PreToolUse、PostToolUse、PostFileSave用のHook設定があります。

```bash
./scripts/run_bridge.sh
```

Bridgeは`KiroBuddy`という名前のM5Stackを自動検索し、接続後は最新状態を自動送信します。切断時は再接続を試み、再接続後に最新状態を再送します。

Hookイベントは次の状態へ変換されます。

| Hookイベント | 状態 | アニメーション |
|---|---|---|
| `SessionStart` | `idle` | `idle` |
| `PreToolUse` | `in_progress` | `walk` |
| `PostToolUse` / `PostFileSave` | `idle` | `idle` |
| `Stop` | `completed` | `completed`（約2秒後にidle） |

HTTPエンドポイントは次のとおりです。

```bash
curl http://127.0.0.1:9876/status

curl -X POST http://127.0.0.1:9876/event \\
  -H "Content-Type: application/json" \\
  -d '{"event":"tool_start"}'
```

BridgeとM5Stackの通信は、改行区切りのUTF-8 JSONです。現在の状態メッセージは次の形式です。

```json
{
  "v": 1,
  "type": "state",
  "state": "in_progress",
  "message": "Working",
  "sequence": 3,
  "timestamp": 1720000000
}
```

M5StackはBLE受信、JSON解析、ACK送信を行います。credit、token、ファイル内容、コマンド本文などは送信・表示しません。

> 注意：初回接続時は、macOSのBluetooth権限が必要になる場合があります。Bridge起動後にM5Stackの電源を入れると自動検索されます。

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
python3 -m py_compile scripts/ble_test_client.py
bash -n scripts/deploy.sh
```

Hook JSON検証：

```bash
python3 -c 'import json, pathlib; [json.loads(p.read_text()) for p in pathlib.Path(".kiro/hooks").glob("*.json")]; print("hooks: ok")'
```

BLE実機テスト：

```bash
uv run python scripts/ble_test_client.py
```

M5Stackでは、LCD初期化、BMPロード、BLE advertising、Bridgeからの状態受信、ACK、各アニメーションの切り替えを確認します。

## 今後の課題

- BLEの暗号化ペアリングを検討
- Kiro Hookのpermission情報が取得できる場合の`waiting_on_user`判定
- Windows / Linuxでの導入確認
- 必要になった場合のみ利用量表示を検討
