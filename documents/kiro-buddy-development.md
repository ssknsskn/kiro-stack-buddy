# M5StackでKiroの作業状態を表示するデスクペットを作る

## プロジェクト概要

Kiro IDEの作業状態をデスク上で確認できるように、M5Stack BasicへKiroキャラクターを表示するプロジェクトです。

今回の区切りでは、通信連携よりも、次の表示機能を優先して実装しました。

- Kiro画像の表示
- 黒背景と白黒キャラクターの調整
- 右向き・左向き画像の切り替え
- 状態別アニメーション
- M5Stack実機へのデプロイ
- 中央ボタンによるアニメーションテスト

## 使用機材と構成

- M5Stack Basic
- ESP32
- 320×240 ILI9342C LCD
- MicroPython v1.25.0
- macOS
- Python 3.13以上
- `uv`、`mpremote`

将来的な通信構成は次のとおりです。

```text
Kiro IDE Hook
     │ HTTP POST
     ▼
Bridge Server（macOS）
     │ BLE / Nordic UART Service
     ▼
M5Stack Basic
```

`bridge/server.py`と`.kiro/hooks/`は準備済みですが、現時点の`firmware/main.py`は表示・アニメーションの実機確認を優先しています。BLEで受信した状態をファームウェアへ反映する処理は次の段階です。

## キャラクター画像を使うまで

最初はPillowで円や矩形を組み合わせ、Kiroキャラクターをコードから生成していました。しかし、輪郭や目の位置が元画像に似ず、単純な図形では自然なキャラクターになりませんでした。

そこで、元画像を加工して使用する方針へ変更しました。

```text
firmware/assets/kiro.png
```

元画像はパレット形式だったため、RGBへ変換してからグレースケール化しました。ピクセル値を確認すると、キャラクターと背景の主な値は次のとおりでした。

- `0`：キャラクター側
- `97`：背景側

このため、閾値50で二値化しました。

```python
from PIL import Image

img = Image.open("firmware/assets/kiro.png").convert("RGBA")
gray = img.convert("L")
black_and_white = gray.point(
    lambda value: 0 if value < 50 else 255,
    "1",
).convert("RGB")
```

M5Stack上で扱いやすいように96×96ピクセルへ変換し、RGB565 BMPとして保存しました。実際に使用するファイルは次の2つです。

```text
firmware/assets/kiro_bw_96x96.bmp
firmware/assets/kiro_bw_96x96_left.bmp
```

左向き画像は、白黒化した画像を左右反転して作成しました。過去に作成した比較用BMP、PNG、SVGなどの古い画像素材は、検証履歴として`firmware/assets/`に残しています。

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
│ State: idle                    │
│ Anim: idle                     │
│                                │
│  時刻                 BLE: Ready│
└────────────────────────────────┘
```

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

```bash
uv sync
./scripts/deploy.sh /dev/cu.usbserial-XXXX
```

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
│   └── server.py                         # HTTP + BLEブリッジ
├── documents/
│   └── kiro-buddy-development.md        # この開発記録
├── firmware/
│   ├── main.py                           # 表示・アニメーション
│   ├── ili9342c.py                       # ILI9342Cドライバ
│   └── assets/                            # 現行・過去の画像素材
├── scripts/
│   ├── deploy.sh                         # M5Stackデプロイ
│   └── run_bridge.sh                     # ブリッジ起動
├── pyproject.toml
├── uv.lock
└── README.md
```

## 検証

```bash
python3 -m py_compile firmware/main.py
python3 -m py_compile bridge/server.py
bash -n scripts/deploy.sh
```

実機では、LCD初期化、BMPロード、メインループ、Bボタン入力、各アニメーションの切り替えを確認しています。

## 今後の課題

- BLE受信処理を`firmware/main.py`へ追加
- Kiro Hookのセッション状態とアニメーションを接続
- LCD描画のちらつきをさらに低減
- BLEブリッジの接続・再接続テスト
