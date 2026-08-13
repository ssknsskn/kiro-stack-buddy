"""
ILI9342C LCD ドライバ (M5Stack Basic用)
320x240, SPI接続, フレームバッファベース
最小限の実装: 文字描画とfill
"""

from machine import Pin, SPI
import time
import struct
import framebuf


class ILI9342C:
    """M5Stack Basic用 ILI9342C LCDドライバ"""

    # M5Stack Basic ピン定義
    PIN_CS = 14
    PIN_DC = 27
    PIN_RST = 33
    PIN_BL = 32
    PIN_SCK = 18
    PIN_MOSI = 23

    WIDTH = 320
    HEIGHT = 240

    def __init__(self):
        self.bl = Pin(self.PIN_BL, Pin.OUT)
        self.cs = Pin(self.PIN_CS, Pin.OUT)
        self.dc = Pin(self.PIN_DC, Pin.OUT)
        self.rst = Pin(self.PIN_RST, Pin.OUT)

        self.spi = SPI(
            2,
            baudrate=40_000_000,
            polarity=0,
            phase=0,
            sck=Pin(self.PIN_SCK),
            mosi=Pin(self.PIN_MOSI),
        )

        self.cs.value(1)
        self._reset()
        self._init_display()
        self.bl.value(1)

        # フレームバッファ (RGB565, 行バッファ方式 - メモリ節約)
        # 全画面バッファは320*240*2=153600バイトで大きいので
        # テキスト描画用に部分バッファを使う
        self._line_buf = bytearray(self.WIDTH * 2)

    def _reset(self):
        """ハードウェアリセット"""
        self.rst.value(0)
        time.sleep_ms(50)
        self.rst.value(1)
        time.sleep_ms(150)

    def _write_cmd(self, cmd):
        """コマンド送信"""
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(bytes([cmd]))
        self.cs.value(1)

    def _write_data(self, data):
        """データ送信"""
        self.cs.value(0)
        self.dc.value(1)
        if isinstance(data, int):
            self.spi.write(bytes([data]))
        else:
            self.spi.write(data)
        self.cs.value(1)

    def _write_cmd_data(self, cmd, data):
        """コマンド+データ"""
        self._write_cmd(cmd)
        self._write_data(data)

    def _init_display(self):
        """ディスプレイ初期化シーケンス (ILI9342C)"""
        # Software Reset
        self._write_cmd(0x01)
        time.sleep_ms(150)

        # Sleep Out
        self._write_cmd(0x11)
        time.sleep_ms(150)

        # Memory Access Control (landscape, BGR)
        # ILI9342Cは元々landscape。0x08=BGR のみでUSB下向き正位置
        self._write_cmd_data(0x36, bytes([0x08]))

        # Pixel Format: 16bit/pixel (RGB565)
        self._write_cmd_data(0x3A, bytes([0x55]))

        # Display ON
        self._write_cmd(0x29)
        time.sleep_ms(50)

    def _set_window(self, x0, y0, x1, y1):
        """描画ウィンドウ設定"""
        self._write_cmd(0x2A)  # Column Address Set
        self._write_data(struct.pack(">HH", x0, x1))
        self._write_cmd(0x2B)  # Row Address Set
        self._write_data(struct.pack(">HH", y0, y1))
        self._write_cmd(0x2C)  # Memory Write

    def fill(self, color):
        """画面全体を指定色で塗りつぶし"""
        hi = (color >> 8) & 0xFF
        lo = color & 0xFF
        line = bytearray([hi, lo] * self.WIDTH)
        self._set_window(0, 0, self.WIDTH - 1, self.HEIGHT - 1)
        self.cs.value(0)
        self.dc.value(1)
        for _ in range(self.HEIGHT):
            self.spi.write(line)
        self.cs.value(1)

    def fill_rect(self, x, y, w, h, color):
        """矩形塗りつぶし"""
        if x >= self.WIDTH or y >= self.HEIGHT:
            return
        if x + w > self.WIDTH:
            w = self.WIDTH - x
        if y + h > self.HEIGHT:
            h = self.HEIGHT - y

        hi = (color >> 8) & 0xFF
        lo = color & 0xFF
        line = bytearray([hi, lo] * w)
        self._set_window(x, y, x + w - 1, y + h - 1)
        self.cs.value(0)
        self.dc.value(1)
        for _ in range(h):
            self.spi.write(line)
        self.cs.value(1)

    def text(self, s, x, y, color=0xFFFF, scale=1):
        """テキスト描画 (framebuf内蔵8x8フォント使用)"""
        # 1文字ずつ framebuf で描画してLCDに転送
        char_w = 8 * scale
        char_h = 8 * scale

        for i, ch in enumerate(s):
            cx = x + i * char_w
            if cx + char_w > self.WIDTH:
                break
            self._draw_char(ch, cx, y, color, scale)

    def _draw_char(self, ch, x, y, color, scale):
        """1文字描画"""
        # 8x8ピクセルのframebufで文字をレンダリング
        buf = bytearray(8)
        fb = framebuf.FrameBuffer(buf, 8, 8, framebuf.MONO_HLSB)
        fb.fill(0)
        fb.text(ch, 0, 0, 1)

        w = 8 * scale
        h = 8 * scale

        if x + w > self.WIDTH or y + h > self.HEIGHT:
            return

        # RGB565ピクセルデータ生成
        hi = (color >> 8) & 0xFF
        lo = color & 0xFF
        bg_hi = 0
        bg_lo = 0

        pixel_data = bytearray(w * h * 2)
        idx = 0
        for row in range(8):
            for sy in range(scale):
                for col in range(8):
                    pixel_on = buf[row] & (0x80 >> col)
                    for sx in range(scale):
                        if pixel_on:
                            pixel_data[idx] = hi
                            pixel_data[idx + 1] = lo
                        else:
                            pixel_data[idx] = bg_hi
                            pixel_data[idx + 1] = bg_lo
                        idx += 2

        self._set_window(x, y, x + w - 1, y + h - 1)
        self.cs.value(0)
        self.dc.value(1)
        self.spi.write(pixel_data)
        self.cs.value(1)

    def text_bg(self, s, x, y, color=0xFFFF, bg=0x0000, scale=1):
        """背景色付きテキスト描画"""
        char_w = 8 * scale
        char_h = 8 * scale

        for i, ch in enumerate(s):
            cx = x + i * char_w
            if cx + char_w > self.WIDTH:
                break
            self._draw_char_bg(ch, cx, y, color, bg, scale)

    def _draw_char_bg(self, ch, x, y, color, bg, scale):
        """1文字描画 (背景色指定)"""
        buf = bytearray(8)
        fb = framebuf.FrameBuffer(buf, 8, 8, framebuf.MONO_HLSB)
        fb.fill(0)
        fb.text(ch, 0, 0, 1)

        w = 8 * scale
        h = 8 * scale

        if x + w > self.WIDTH or y + h > self.HEIGHT:
            return

        hi = (color >> 8) & 0xFF
        lo = color & 0xFF
        bg_hi = (bg >> 8) & 0xFF
        bg_lo = bg & 0xFF

        pixel_data = bytearray(w * h * 2)
        idx = 0
        for row in range(8):
            for sy in range(scale):
                for col in range(8):
                    pixel_on = buf[row] & (0x80 >> col)
                    for sx in range(scale):
                        if pixel_on:
                            pixel_data[idx] = hi
                            pixel_data[idx + 1] = lo
                        else:
                            pixel_data[idx] = bg_hi
                            pixel_data[idx + 1] = bg_lo
                        idx += 2

        self._set_window(x, y, x + w - 1, y + h - 1)
        self.cs.value(0)
        self.dc.value(1)
        self.spi.write(pixel_data)
        self.cs.value(1)

    def backlight(self, on=True):
        """バックライトのON/OFF"""
        self.bl.value(1 if on else 0)

    def draw_image(self, x, y, filename):
        """画像描画 (BMP, PNG, JPG対応)

        Args:
            x, y: 描画位置
            filename: 画像ファイルパス
        """
        # ファイル形式判定
        if filename.lower().endswith('.bmp'):
            return self.draw_bmp(x, y, filename)
        elif filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            return self.draw_png_jpg(x, y, filename)
        else:
            print(f"エラー: {filename} は非対応形式です")
            return False

    def draw_bmp(self, x, y, filename):
        """BMP画像描画 (RGB565形式のみ対応)

        Args:
            x, y: 描画位置
            filename: BMPファイルパス
        """
        try:
            with open(filename, 'rb') as f:
                # BMP ヘッダ解析
                header = f.read(54)

                # ファイルシグネチャ確認
                if header[0:2] != b'BM':
                    print(f"エラー: {filename} はBMP形式ではありません")
                    return

                # オフセット取得
                offset = struct.unpack('<I', header[10:14])[0]

                # 画像情報取得
                width = struct.unpack('<i', header[18:22])[0]
                height = struct.unpack('<i', header[22:26])[0]
                bits_per_pixel = struct.unpack('<H', header[28:30])[0]

                # RGB565 (16bit) のみ対応
                if bits_per_pixel != 16:
                    print(f"エラー: {bits_per_pixel}bit BMPは非対応です")
                    return

                # ピクセルデータまでスキップ
                f.seek(offset)

                # 画像サイズチェック
                img_width = min(width, self.WIDTH - x)
                img_height = min(abs(height), self.HEIGHT - y)

                if img_width <= 0 or img_height <= 0:
                    return

                # BMP は bottom-up が標準
                is_bottom_up = height > 0

                # ウィンドウ設定
                self._set_window(x, y, x + img_width - 1, y + img_height - 1)
                self.cs.value(0)
                self.dc.value(1)

                # ピクセルデータ転送
                row_bytes = width * 2
                for row in range(abs(height)):
                    if row >= img_height:
                        break

                    # Bottom-up の場合は逆順で読む
                    if is_bottom_up:
                        f.seek(offset + (abs(height) - 1 - row) * row_bytes)

                    row_data = f.read(row_bytes)
                    # 画像幅分だけ送信
                    self.spi.write(row_data[:img_width * 2])

                self.cs.value(1)
                print(f"✅ BMP描画完了: {filename} ({width}×{height})")

        except OSError as e:
            print(f"エラー: {filename} が見つかりません - {e}")
        except Exception as e:
            print(f"エラー: BMP描画失敗 - {e}")

    def draw_png_jpg(self, x, y, filename):
        """PNG/JPG画像描画

        MicroPython で画像を直接読み込んで LCD に描画
        Note: M5Stack では jpegmodule が使用可能な場合がある
        """
        try:
            # 簡易実装: ファイルを開いてヘッダを確認するだけ
            # 実際のデコードには jpegmodule や pngmodule が必要
            with open(filename, 'rb') as f:
                header = f.read(4)

                if header[:3] == b'\x89PN':  # PNG
                    print(f"PNG 検出: {filename}")
                    # PNG デコード (jpegmodule 非対応のため未実装)
                    print("⚠️ PNG描画は MicroPython 標準では非対応です")
                    print("代わりに BMP 形式を使用してください")
                    return False

                elif header[:2] == b'\xFF\xD8':  # JPG
                    print(f"JPG 検出: {filename}")
                    # JPG デコード (M5Stack では jpegmodule 利用可能な場合がある)
                    try:
                        import jpeg
                        # JPG をデコード
                        with open(filename, 'rb') as img_f:
                            jpeg_data = img_f.read()

                        # JPEG をRGB565に変換
                        # 注: これは M5Stack の jpegmodule の使用を想定
                        print("JPG デコード実装予定")
                        return False
                    except ImportError:
                        print("⚠️ jpeg モジュールがありません")
                        return False
                else:
                    print(f"不明な形式: {filename}")
                    return False

        except Exception as e:
            print(f"エラー: PNG/JPG 描画失敗 - {e}")
            return False


# --- 色定数 (RGB565) ---
BLACK = 0x0000
WHITE = 0xFFFF
RED = 0xF800
GREEN = 0x07E0
BLUE = 0x001F
YELLOW = 0xFFE0
CYAN = 0x07FF
MAGENTA = 0xF81F
ORANGE = 0xFD20
PURPLE = 0x8010
GRAY = 0x8410
DARK_GRAY = 0x4208
