"""
Kiro Buddy - M5Stack Basic ファームウェア
画面表示、アニメーション、BLE基本機能のテスト
"""

import time
import gc
import json
import struct
from machine import Pin

try:
    import bluetooth
except ImportError:
    bluetooth = None

try:
    from ili9342c import ILI9342C, BLACK, WHITE, RED, GREEN, YELLOW, CYAN, MAGENTA, GRAY, DARK_GRAY
    print("[LCD] ili9342c.py ロード成功")
except ImportError as e:
    print(f"[ERROR] ili9342c.py ロード失敗: {e}")
    raise

# M5Stack Basic ボタン
BTN_A = Pin(39, Pin.IN, Pin.PULL_UP)
BTN_B = Pin(38, Pin.IN, Pin.PULL_UP)
BTN_C = Pin(37, Pin.IN, Pin.PULL_UP)

# 状態定義
STATE_IDLE = "idle"
STATE_IN_PROGRESS = "in_progress"
STATE_WAITING_ON_USER = "waiting_on_user"
STATE_COMPLETED = "completed"
STATE_ERROR = "error"
STATE_OFFLINE = "offline"

# Nordic UART Service UUIDs
NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# BLE IRQイベント（MicroPython bluetooth API）
_IRQ_CENTRAL_CONNECT = 1
_IRQ_CENTRAL_DISCONNECT = 2
_IRQ_GATTS_WRITE = 3

# 状態ごとの色
STATE_COLORS = {
    STATE_IDLE: GREEN,
    STATE_IN_PROGRESS: YELLOW,
    STATE_WAITING_ON_USER: RED,
    STATE_COMPLETED: MAGENTA,
    STATE_ERROR: RED,
    STATE_OFFLINE: GRAY,
}

STATE_LABELS = {
    STATE_IDLE: "IDLE",
    STATE_IN_PROGRESS: "WORKING",
    STATE_WAITING_ON_USER: "WAITING",
    STATE_COMPLETED: "DONE",
    STATE_ERROR: "ERROR",
    STATE_OFFLINE: "IDLE",
}

# テスト用アニメーションパターン
ANIM_IDLE = "idle"
ANIM_WALK = "walk"
ANIM_LOOK = "look"
ANIM_COMPLETED = "completed"
ANIMATION_PATTERNS = [ANIM_IDLE, ANIM_WALK, ANIM_LOOK, ANIM_COMPLETED]
ANIMATION_LABELS = {
    ANIM_IDLE: "Idle sway",
    ANIM_WALK: "Working",
    ANIM_LOOK: "Looking",
    ANIM_COMPLETED: "Completed",
}


class KiroBuddy:
    """Kiroキャラクターの表示とアニメーションを管理するアプリケーション"""

    def __init__(self):
        print("[init] LCD初期化...")
        self.lcd = ILI9342C()
        self.lcd.fill(BLACK)
        print("[init] LCD初期化完了")

        # 状態管理
        self.pet_state = STATE_OFFLINE
        self.msg = "Waiting for BLE"
        self.last_update = time.ticks_ms()
        self.frame_count = 0
        self._btn_prev = [1, 1, 1]
        self.pending_state = None
        self.current_sequence = -1
        self.completed_until = None

        # BLE状態
        self.ble = None
        self.ble_rx_handle = None
        self.ble_tx_handle = None
        self.ble_conn_handle = None
        self.ble_rx_buffer = bytearray()
        self.ble_discard_until_newline = False
        self.ble_link_connected = False

        # アニメーション管理
        self.anim_x = 112
        self.anim_y = 30
        self.anim_x_prev = 112
        self.anim_y_prev = 30
        self.anim_frame = 0
        self.facing_left = False
        self.animation_index = 0
        self.animation_pattern = ANIMATION_PATTERNS[self.animation_index]

        # BMPデータを事前にメモリへロード
        print("[init] BMP ロード中...")
        self.bmp_right = self._load_bmp("/kiro_bw_96x96.bmp")
        self.bmp_left = self._load_bmp("/kiro_bw_96x96_left.bmp")
        # 旧フレームを残さず描画するための小さな1行バッファ
        self.transition_row = bytearray(160 * 2)
        self.transition_row_view = memoryview(self.transition_row)
        print("[init] BMP ロード完了")
        gc.collect()

        self._init_ble()
        print("[init] 準備完了")

    def _init_ble(self):
        """Nordic UART ServiceのBLE Peripheralを初期化"""
        if bluetooth is None:
            print("[BLE] bluetoothモジュールなし。オフラインで起動")
            return

        try:
            self.ble = bluetooth.BLE()
            self.ble.active(True)
            self.ble.irq(self._ble_irq)

            service_uuid = bluetooth.UUID(NUS_SERVICE_UUID)
            rx_uuid = bluetooth.UUID(NUS_RX_UUID)
            tx_uuid = bluetooth.UUID(NUS_TX_UUID)
            rx = (rx_uuid, bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE)
            tx = (tx_uuid, bluetooth.FLAG_NOTIFY)
            ((self.ble_rx_handle, self.ble_tx_handle),) = (
                self.ble.gatts_register_services(((service_uuid, (rx, tx)),))
            )
            self._start_ble_advertising()
            print("[BLE] KiroBuddy advertising開始")
        except Exception as error:
            self.ble = None
            print(f"[BLE] 初期化失敗: {error}")

    def _advertising_payload(self, name):
        """BLE広告パケットを作成"""
        name_bytes = name.encode("utf-8")
        return bytearray(
            bytes([2, 1, 6]) + bytes([len(name_bytes) + 1, 0x09]) + name_bytes
        )

    def _start_ble_advertising(self):
        """KiroBuddyという名前でBLE広告を開始"""
        if self.ble:
            self.ble.gap_advertise(
                100_000,
                adv_data=self._advertising_payload("KiroBuddy"),
            )

    def _ble_irq(self, event, data):
        """BLEイベントを受け取り、描画処理はメインループへ渡す"""
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            self.ble_conn_handle = conn_handle
            self.ble_link_connected = True
            print("[BLE] Central接続")
        elif event == _IRQ_CENTRAL_DISCONNECT:
            self.ble_conn_handle = None
            self.ble_link_connected = False
            print("[BLE] Central切断")
            self._start_ble_advertising()
        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            if value_handle == self.ble_rx_handle and self.ble:
                received = self.ble.gatts_read(self.ble_rx_handle)
                if len(self.ble_rx_buffer) + len(received) > 1024:
                    self.ble_rx_buffer = bytearray()
                    self.ble_discard_until_newline = True
                if not self.ble_discard_until_newline:
                    self.ble_rx_buffer.extend(received)
                if bytes([10]) in received:
                    self.ble_discard_until_newline = False

    def _ble_notify(self, message):
        """BLE接続中のBridgeへJSONを通知"""
        if not self.ble or self.ble_conn_handle is None:
            return
        try:
            payload = json.dumps(message, separators=(",", ":")).encode() + bytes([10])
            self.ble.gatts_notify(self.ble_conn_handle, self.ble_tx_handle, payload)
        except Exception as error:
            print(f"[BLE] notify失敗: {error}")

    def _process_ble_messages(self):
        """受信バッファから改行区切りJSONを処理"""
        while bytes([10]) in self.ble_rx_buffer:
            line_end = self.ble_rx_buffer.index(bytes([10]))
            line = bytes(self.ble_rx_buffer[:line_end])
            self.ble_rx_buffer = self.ble_rx_buffer[line_end + 1 :]
            if not line:
                continue
            try:
                message = json.loads(line.decode("utf-8"))
                self._handle_ble_message(message)
            except (ValueError, UnicodeError) as error:
                print(f"[BLE] JSON受信エラー: {error}")
                self._ble_notify({"type": "error", "message": "invalid_json"})

    def _handle_ble_message(self, message):
        """受信した状態を次のフレームで適用する"""
        if not isinstance(message, dict):
            return

        state = message.get("state") or message.get("session_status")
        if state not in {
            STATE_IDLE,
            STATE_IN_PROGRESS,
            STATE_WAITING_ON_USER,
            STATE_COMPLETED,
            STATE_ERROR,
        }:
            return

        try:
            sequence = int(message.get("sequence", self.current_sequence + 1))
        except (TypeError, ValueError):
            self._ble_notify({"type": "error", "message": "invalid_sequence"})
            return
        if sequence <= self.current_sequence:
            return

        self.pending_state = (sequence, state, str(message.get("message", state))[:40])
        self._ble_notify({"type": "ack", "sequence": sequence, "ok": True})

    def _apply_pending_state(self):
        """受信状態を描画フレーム境界で適用"""
        if self.pending_state is None:
            return

        sequence, state, message = self.pending_state
        self.pending_state = None
        if sequence <= self.current_sequence:
            return

        self.current_sequence = sequence
        self.pet_state = state
        self.msg = message
        self._set_animation_for_state(state)
        if state == STATE_COMPLETED:
            self.completed_until = time.ticks_add(time.ticks_ms(), 2000)
        else:
            self.completed_until = None
        print(f"[STATE] BLE状態: {state} ({message})")

    def _set_animation_for_state(self, state):
        """Kiro状態をアニメーションへ変換"""
        if state == STATE_IN_PROGRESS:
            pattern = ANIM_WALK
        elif state == STATE_WAITING_ON_USER or state == STATE_ERROR:
            pattern = ANIM_LOOK
        elif state == STATE_COMPLETED:
            pattern = ANIM_COMPLETED
        else:
            pattern = ANIM_IDLE
        self._set_animation_pattern_by_name(pattern)

    def _update_ble_state(self):
        """BLE接続状態の変化を画面状態へ反映"""
        if self.ble_link_connected:
            return
        if self.pet_state != STATE_OFFLINE:
            self.pet_state = STATE_OFFLINE
            self.msg = "Waiting for BLE"
            self._set_animation_pattern_by_name(ANIM_LOOK)

    def _load_bmp(self, filename):
        """BMPファイルをRGB565バイト列としてメモリにロード"""
        import struct as st

        with open(filename, "rb") as f:
            header = f.read(54)
            offset = st.unpack("<I", header[10:14])[0]
            width = st.unpack("<i", header[18:22])[0]
            height = st.unpack("<i", header[22:26])[0]
            f.seek(offset)

            # BMPのbottom-upをLCD用のtop-downへ変換
            row_bytes = width * 2
            rows = []
            for row in range(abs(height) - 1, -1, -1):
                f.seek(offset + row * row_bytes)
                rows.append(f.read(row_bytes))

            data = bytearray(width * abs(height) * 2)
            index = 0
            for row_data in rows:
                data[index:index + row_bytes] = row_data
                index += row_bytes

            return data

    def _set_animation_pattern_by_name(self, pattern):
        """名前でアニメーションパターンを変更"""
        if pattern in ANIMATION_PATTERNS:
            self.animation_index = ANIMATION_PATTERNS.index(pattern)
            self.animation_pattern = pattern
            self.anim_frame = 0
            self.anim_x = 112
            self.anim_y = 30
            self.facing_left = False

    def _set_animation_pattern(self, index):
        """アニメーションパターンを変更"""
        self.animation_index = index % len(ANIMATION_PATTERNS)
        self.animation_pattern = ANIMATION_PATTERNS[self.animation_index]
        self.anim_frame = 0
        self.anim_x = 112
        self.anim_y = 30
        self.facing_left = False
        self.msg = ANIMATION_LABELS[self.animation_pattern]
        print(f"[ANIMATION] パターン変更: {self.animation_pattern}")

    def _next_animation_pattern(self):
        """中央ボタン用。次のアニメーションパターンへ切り替え"""
        self._set_animation_pattern(self.animation_index + 1)

    def _animate_idle(self, frame):
        """待機中：中央で小さく左右に揺れる"""
        phase = frame % 12
        if phase < 6:
            self.anim_x = 112 + phase * 2
            self.facing_left = False
        else:
            self.anim_x = 122 - (phase - 6) * 2
            self.facing_left = True
        self.anim_y = 30

    def _animate_walk(self, frame):
        """作業中：小刻みに動きながら、画面内を広く左右へ移動"""
        # 1フレーム4px、60フレームで往復する三角波。
        # x=52〜172、画像右端は268pxで画面外に出ない。
        frame_in_cycle = frame % 60
        if frame_in_cycle < 15:
            offset = frame_in_cycle * 4
        elif frame_in_cycle < 45:
            offset = 60 - (frame_in_cycle - 15) * 4
        else:
            offset = -60 + (frame_in_cycle - 45) * 4

        self.anim_x = 112 + offset
        self.anim_y = 30
        # frame 15〜44は右端から左端へ移動中なので左向き
        self.facing_left = 15 <= frame_in_cycle < 45

    def _animate_look(self, frame):
        """確認中：その場で左右を向く"""
        self.anim_x = 112
        self.anim_y = 30
        self.facing_left = (frame // 10) % 2 == 1

    def _animate_completed(self, frame):
        """完了：中央ですばやく跳ねる"""
        phase = frame % 6
        self.anim_x = 112
        self.facing_left = False

        if phase == 1:
            self.anim_y = 24
        elif phase == 2:
            self.anim_y = 22
        elif phase == 3:
            self.anim_y = 24
        else:
            self.anim_y = 30

    def _update_animation(self):
        """現在のアニメーションパターンを1フレーム進める"""
        if (
            self.pet_state == STATE_COMPLETED
            and self.completed_until is not None
            and time.ticks_diff(time.ticks_ms(), self.completed_until) >= 0
        ):
            self.pet_state = STATE_IDLE
            self.msg = "Ready"
            self._set_animation_pattern_by_name(ANIM_IDLE)
            self.completed_until = None

        frame = self.anim_frame

        if self.animation_pattern == ANIM_IDLE:
            self._animate_idle(frame)
        elif self.animation_pattern == ANIM_WALK:
            self._animate_walk(frame)
        elif self.animation_pattern == ANIM_LOOK:
            self._animate_look(frame)
        elif self.animation_pattern == ANIM_COMPLETED:
            self._animate_completed(frame)

    def _draw_kiro(self):
        """Kiroをメモリから直接描画"""
        lcd = self.lcd
        x = int(self.anim_x)
        y = int(self.anim_y)
        bmp_data = self.bmp_left if self.facing_left else self.bmp_right

        lcd._set_window(x, y, x + 95, y + 95)
        lcd.cs.value(0)
        lcd.dc.value(1)
        lcd.spi.write(bmp_data)
        lcd.cs.value(1)

    def _clear_exposed_previous_kiro(self):
        """新しい画像に覆われていない旧画像の領域だけをクリア"""
        old_left = int(self.anim_x_prev)
        old_top = int(self.anim_y_prev)
        old_right = old_left + 96
        old_bottom = old_top + 96
        new_left = int(self.anim_x)
        new_top = int(self.anim_y)
        new_right = new_left + 96
        new_bottom = new_top + 96

        overlap_left = max(old_left, new_left)
        overlap_top = max(old_top, new_top)
        overlap_right = min(old_right, new_right)
        overlap_bottom = min(old_bottom, new_bottom)

        if overlap_left >= overlap_right or overlap_top >= overlap_bottom:
            self.lcd.fill_rect(old_left, old_top, 96, 96, BLACK)
            return

        if old_top < overlap_top:
            self.lcd.fill_rect(old_left, old_top, 96, overlap_top - old_top, BLACK)
        if overlap_bottom < old_bottom:
            self.lcd.fill_rect(old_left, overlap_bottom, 96, old_bottom - overlap_bottom, BLACK)

        middle_top = overlap_top
        middle_height = overlap_bottom - overlap_top
        if old_left < overlap_left:
            self.lcd.fill_rect(old_left, middle_top, overlap_left - old_left, middle_height, BLACK)
        if overlap_right < old_right:
            self.lcd.fill_rect(overlap_right, middle_top, old_right - overlap_right, middle_height, BLACK)

    def _draw_kiro_transition(self):
        """黒背景と新Kiroを小さな1行バッファで一括更新"""
        old_left = int(self.anim_x_prev)
        old_top = int(self.anim_y_prev)
        new_left = int(self.anim_x)
        new_top = int(self.anim_y)

        # 旧位置と新位置を含む最小領域だけを更新する
        left = min(old_left, new_left)
        top = min(old_top, new_top)
        right = max(old_left + 96, new_left + 96)
        bottom = max(old_top + 96, new_top + 96)
        region_width = right - left
        region_height = bottom - top
        x_offset = new_left - left
        y_offset = new_top - top

        # 新しいKiroの画像データ
        bmp_data = self.bmp_left if self.facing_left else self.bmp_right
        row_bytes = 96 * 2
        output_row_bytes = region_width * 2

        lcd = self.lcd
        lcd._set_window(left, top, right - 1, bottom - 1)
        lcd.cs.value(0)
        lcd.dc.value(1)

        for row in range(region_height):
            # 行全体を黒にする。旧フレームの白はここで確実に消える。
            for index in range(output_row_bytes):
                self.transition_row[index] = 0

            source_row = row - y_offset
            if 0 <= source_row < 96:
                source_start = source_row * row_bytes
                target_start = x_offset * 2
                self.transition_row[target_start:target_start + row_bytes] = (
                    bmp_data[source_start:source_start + row_bytes]
                )

            lcd.spi.write(self.transition_row_view[:output_row_bytes])

        lcd.cs.value(1)

    def _draw(self):
        """LCD描画"""
        lcd = self.lcd

        if self.frame_count == 0:
            lcd.fill(BLACK)
            self._draw_kiro()
        elif self.animation_pattern == ANIM_WALK:
            # walkだけは広い描画領域を黒背景ごと更新して残像を抑える
            self._draw_kiro_transition()
        else:
            # idle/look/completedは従来の軽い差分描画に戻す
            self._draw_kiro()
            self._clear_exposed_previous_kiro()

        self.anim_x_prev = self.anim_x
        self.anim_y_prev = self.anim_y

        # 最小限の状態表示。詳細なログやcredit/tokenは表示しない。
        color = STATE_COLORS.get(self.pet_state, WHITE)
        status_text = (STATE_LABELS.get(self.pet_state, "IDLE") + "       ")[:7]
        lcd.text_bg(status_text, 10, 150, color, BLACK, 2)

        bridge_text = (("BRIDGE CONNECTED" if self.ble_link_connected else "BRIDGE OFFLINE") + "                ")[:16]
        bridge_color = GREEN if self.ble_link_connected else GRAY
        lcd.text_bg(bridge_text, 10, 215, bridge_color, DARK_GRAY, 1)

        ble_text = (("BLE: ON" if self.ble_link_connected else "BLE: OFF") + "        ")[:8]
        lcd.text_bg(ble_text, 250, 215, bridge_color, DARK_GRAY, 1)


    def _check_buttons(self):
        """ボタン入力チェック"""
        buttons = [BTN_A.value(), BTN_B.value(), BTN_C.value()]
        btn_names = ["A", "B", "C"]
        states = [STATE_IDLE, STATE_IN_PROGRESS, STATE_WAITING_ON_USER, STATE_COMPLETED]

        for index, button in enumerate(buttons):
            if self._btn_prev[index] == 1 and button == 0:
                print(f"[BTN] ボタン{btn_names[index]}押下")

                if index == 1:
                    # 中央ボタンBはテスト用アニメーション切り替え
                    self._next_animation_pattern()
                else:
                    # A/Cは手動テスト用の状態切り替え
                    state_index = states.index(self.pet_state) if self.pet_state in states else 0
                    self.pet_state = states[(state_index + 1) % len(states)]
                    self._set_animation_for_state(self.pet_state)
                    self.msg = f"Button {btn_names[index]} - {self.pet_state}"
                    print(f"[STATE] 手動状態変更: {self.pet_state}")

            self._btn_prev[index] = button

    def run(self):
        """メインループ"""
        print("[run] メインループ開始")
        self._draw()

        loop_count = 0
        while True:
            self._process_ble_messages()
            self._apply_pending_state()
            self._update_ble_state()
            self._check_buttons()

            # 50msごとにアニメーションと描画を更新
            now = time.ticks_ms()
            if time.ticks_diff(now, self.last_update) > 50:
                self.last_update = now
                self.anim_frame += 1
                self._update_animation()
                self.frame_count += 1
                self._draw()

            loop_count += 1
            if loop_count % 100 == 0:
                print(f"[heartbeat] Loop count: {loop_count}")
                gc.collect()

            time.sleep_ms(10)


# エントリポイント
if __name__ == "__main__":
    try:
        print("=" * 40)
        print("Kiro Buddy - M5Stack Basic")
        print("=" * 40)

        buddy = KiroBuddy()
        buddy.run()

    except Exception as e:
        print(f"[FATAL] エラー: {e}")
        import traceback
        traceback.print_exc()

        try:
            lcd = ILI9342C()
            lcd.fill(RED)
            lcd.text_bg("ERROR", 50, 100, WHITE, RED, 3)
            print(str(e)[:30])
        except:
            pass
