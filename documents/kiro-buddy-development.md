# M5StackでKiroの作業状態を表示するデスクペットを作る

## プロジェクト概要

Kiro IDEの作業状態をデスク上で確認できるように、M5Stack BasicへKiroキャラクターを表示するプロジェクトです。

今回の区切りでは、Kiro IDEのイベントをBLEでM5Stackへ送り、Kiroの状態に応じてアニメーションを切り替える最小構成まで実装しました。

- Kiro画像の表示
- 黒背景と白黒キャラクターの調整
- 右向き・左向き画像の切り替え
- `idle`、`walk`、`look`、`completed`のアニメーション
- Kiro Hookからの状態イベント受信
- M5StackのBLE NUS受信とACK
- M5Stack実機へのデプロイ

Wi-Fi、credit/token表示、ファイル内容、コマンド本文、セッション履歴は対象外です。M5Stackは、Kiroが待機中・作業中・ユーザー待ち・完了のどの状態かを素早く確認するためのデバイスとします。

## 使用機材と構成

- M5Stack Basic
- ESP32
- 320×240 ILI9342C LCD
- MicroPython v1.25.0
- macOS
- Python 3.13以上
- `uv`、`mpremote`

Kiro IDE Hook
```text
     │ HTTP POST
     ▼
Bridge Server（macOS）
     │ BLE / Nordic UART Service
     ▼
M5Stack Basic
```

HookイベントはBridgeで次の状態へ変換します。

| Hookイベント | 状態 | アニメーション |
|---|---|---|
| `SessionStart` | `idle` | `idle` |
| `UserPromptSubmit` | `in_progress` | `walk` |
| `Stop` | `completed` | `completed`（約2秒後にidle） |

BridgeとM5Stackは改行区切りJSONで通信します。

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

M5Stack側ではBLE IRQで受信データをバッファへ追加し、メインループのフレーム境界でJSONを解析・適用します。BLE IRQからLCDを直接描画しないことで、アニメーションの描画周期を維持します。

## キャラクター画像を使うまで

画像の権利を明確にしたままGitHubで公開できるよう、Kiro画像はリポジトリへ同梱しない方針にしました。利用者が権利を確認して用意したローカル画像を、ホスト側でM5Stack用の形式へ変換します。外部URLやCDNからの自動取得は行いません。

画像変換には`Pillow==12.3.0`を使用し、`uv sync`で依存関係をインストールします。入力画像はPNG、JPGなどPillowが読み込める形式を利用できます。

## 画像アセットの準備

リポジトリのルートから、利用者が用意した画像を指定して実行します。

```bash
uv run python scripts/prepare_assets.py \
  --input /path/to/your-image.png
```

スクリプトは次の処理を行います。

1. 入力画像を96×96ピクセルへリサイズする
2. グレースケール化して2値化する（既定の閾値は`128`）
3. 白黒画像をRGB565の16-bit BMPとして保存する
4. 同じ画像を左右反転し、左向き用BMPも生成する

生成されるファイルは次の2つです。出力サイズはファームウェアが前提とする96×96に固定しています。

```text
firmware/assets/kiro_bw_96x96.bmp
firmware/assets/kiro_bw_96x96_left.bmp
```

入力画像の明るさに合わない場合は、閾値を0〜255の範囲で調整できます。

```bash
uv run python scripts/prepare_assets.py \
  --input /path/to/your-image.png \
  --threshold 100
```

生成BMPは利用者のローカル環境だけで使う画像アセットです。`firmware/assets/`は生成ファイルをGitで追跡しない設定になっているため、権利を確認していない画像をcommit・再配布しないでください。

## PNG/JPGではなくBMPを使う理由

MicroPythonには標準の汎用PNG/JPGデコーダーがありません。追加モジュールを組み込む方法もありますが、ファームウェアやメモリ構成に依存します。

今回はPC側で画像をRGB565 BMPへ変換し、M5Stack側ではバイト列として読み込む方式を選びました。

- PC側：Pillowで画像を加工
- M5Stack側：RGB565 BMPを読み込み
- M5Stack側に画像デコーダーを追加しない
- 起動時に左右2枚をメモリへロード

## 画面構成

M5Stackの画面は320×240ピクセルです。Kiroは96×96ピクセルで、上部の`x=112、y=30`付近を基準に表示します。

```text
┌────────────────────────────────┐
│                                │
│          Kiro 96×96            │
│                                │
│           WORKING              │
│                                │
│  BRIDGE CONNECTED      BLE: ON │
└────────────────────────────────┘
```

画面には、主役のKiro、短い状態名、Bridge接続状態、BLE状態だけを表示します。Bridge未接続時は、状態欄は`IDLE`のまま、下部に`BRIDGE OFFLINE`と表示します。これにより、Kiroの状態とBridgeの接続状態を混同しないようにします。

| 状態 | 表示 | アニメーション |
|---|---|---|
| `offline` | `IDLE` + `BRIDGE OFFLINE` | look（その場で左右を見る） |
| `idle` | `IDLE` | idle |
| `in_progress` | `WORKING` | walk |
| `waiting_on_user` | `WAITING` | look |
| `completed` | `DONE` | completed（約2秒） |
| `error` | `ERROR` | look |

credit、token、ファイル名、コマンド本文、プロンプト本文、セッションID、詳細ログは表示しません。これらはM5Stackで常時確認する情報ではなく、画面の狭さやプライバシーの観点からも対象外としています。

`KIRO BUDDY`というヘッダーは削除し、キャラクターを大きく表示する構成にしました。背景はRGB565の完全な黒`0x0000`です。

## アニメーションパターン

中央ボタンBを押すたびに、次の順でテストパターンを切り替えます。

```text
idle → walk → look → completed → idle
```

| パターン | 動き |
|---|---|
| `idle` | 中央付近で小さく左右に揺れる |
| `walk` | 画面内を左右に移動し、移動方向に合わせて向きを変える |
| `look` | その場で右向き・左向きを切り替える |
| `completed` | 中央で素早く上下に跳ねる |

### walkの軌道

`walk`は1フレーム4ピクセル、60フレーム周期の三角波です。

- 左端：`x=52`
- 中央基準：`x=112`
- 右端：`x=172`
- Kiro画像の右端：最大268px

画面幅320pxに対して余白を残しているため、Kiroが画面外へ切れることはありません。

また、移動方向で向きを決めています。

- フレーム0〜14：右向き
- フレーム15〜44：左向き
- フレーム45〜59：右向き

以前は現在位置が中央より左かどうかで向きを判定していたため、右端から中央へ戻る途中に右向きのまま左へ移動する問題がありました。現在は移動区間に基づいて切り替えています。

## ちらつき対策

最初は毎フレーム画面全体を黒で塗りつぶしていました。

```python
lcd.fill(BLACK)
```

これでは「全画面クリア → Kiro描画」の間に黒いちらつきが発生します。

その後、次の対策を段階的に実装しました。

1. BMPを起動時にメモリへロードし、毎フレームのファイルI/Oをなくす
2. Kiroの旧位置と新位置を比較し、移動範囲だけを更新する
3. `idle`、`look`、`completed`は軽い差分描画を使用する
4. `walk`だけは旧位置・新位置の最小外接領域を、黒背景＋新Kiroとして1行ずつ送る
5. walkの1フレーム移動量を抑え、更新領域を小さくする

大容量の全画面フレームバッファは、M5Stackの空きメモリを圧迫するため採用していません。過去に大きな合成バッファを使った際には、約18KBのメモリ確保に失敗してメインループが停止したため、小さな行バッファへ戻しました。

## M5Stackへのデプロイ

依存関係をインストールした後、デプロイ前に利用者の画像からBMPを生成します。

```bash
uv sync
uv run python scripts/prepare_assets.py \
  --input /path/to/your-image.png
./scripts/deploy.sh /dev/cu.usbserial-XXXX
```

`firmware/assets/`に生成済みBMPがない場合、`deploy.sh`は転送せずに停止します。

デプロイスクリプトは次の4ファイルをM5Stackへ転送します。

```text
firmware/ili9342c.py
firmware/main.py
firmware/assets/kiro_bw_96x96.bmp
firmware/assets/kiro_bw_96x96_left.bmp
```

手動転送の場合は次のとおりです。

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

## 現在のファイル構成

```text
kiroStack/
├── .kiro/hooks/                         # Kiro IDE Hook設定
├── bridge/
│   ├── __init__.py
│   └── server.py                         # HTTP + BLEブリッジ
├── documents/
│   └── kiro-buddy-development.md        # この開発記録
├── firmware/
│   ├── main.py                           # 表示・アニメーション
│   ├── ili9342c.py                       # ILI9342Cドライバ
│   └── assets/                            # Git管理外のローカル生成画像
├── scripts/
│   ├── ble_test_client.py                # BLE単体テスト
│   ├── deploy.sh                         # M5Stackデプロイ
│   ├── prepare_assets.py                 # ローカル画像からBMPを生成
│   └── run_bridge.sh                     # ブリッジ起動
├── pyproject.toml
├── uv.lock
└── README.md
```

## 検証

```bash
python3 -m py_compile firmware/main.py
python3 -m py_compile bridge/server.py
python3 -m py_compile scripts/ble_test_client.py
python3 -m py_compile scripts/prepare_assets.py
bash -n scripts/deploy.sh scripts/run_bridge.sh
python3 -c 'import json, pathlib; p=pathlib.Path(".kiro/hooks/buddy-state.json"); d=json.loads(p.read_text()); assert [h["trigger"] for h in d["hooks"]] == ["SessionStart", "UserPromptSubmit", "Stop"]; print("hooks: ok")'
git diff --check
```

BLEテストクライアントは、M5Stackを検出してNUSへ状態JSONを送信します。

```bash
uv run python scripts/ble_test_client.py
```

実機では、LCD初期化、BMPロード、BLE advertising、Bridge接続、状態JSON受信、ACK、状態別アニメーション切り替えを確認します。

## 今後の課題

- BLEの暗号化ペアリングを検討
- Kiro Hookのpermission情報が取得できる場合の`waiting_on_user`判定
- Windows / Linuxでの導入確認
- 必要になった場合のみ利用量表示を検討
