"""
Kiro Buddy Bridge - ローカルHTTPサーバー + BLE Central
Kiro Hookからイベントを受信し、最新のKiro状態をM5Stackへ送信する。
"""

import asyncio
import json
import time
from typing import Optional

from aiohttp import web
from bleak import BleakClient, BleakScanner

# Nordic UART Service UUIDs
NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Mac → M5Stack
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # M5Stack → Mac

HTTP_HOST = "127.0.0.1"
HTTP_PORT = 9876
DEVICE_NAME_PREFIX = "KiroBuddy"
DEVICE_NAME_FALLBACK = "MPY ESP32"
HEARTBEAT_INTERVAL = 10

STATE_IDLE = "idle"
STATE_IN_PROGRESS = "in_progress"
STATE_WAITING_ON_USER = "waiting_on_user"
STATE_COMPLETED = "completed"
STATE_ERROR = "error"


class BuddyBridge:
    """Kiro状態を保持し、BLE経由でM5Stackへ配信するブリッジ"""

    def __init__(self):
        self.client: Optional[BleakClient] = None
        self.connected = False
        self.sequence = 0
        self.state = {
            "state": STATE_IDLE,
            "message": "Ready",
            "sequence": 0,
            "timestamp": int(time.time()),
            "last_event": "",
        }
        self._rx_buffer = ""
        self._send_lock: Optional[asyncio.Lock] = None
        self._reconnect_task: Optional[asyncio.Task] = None

    def _get_send_lock(self) -> asyncio.Lock:
        """現在のイベントループ用の送信ロックを取得する"""
        if self._send_lock is None:
            self._send_lock = asyncio.Lock()
        return self._send_lock

    def _set_state(self, state: str, message: str, event_type: str):
        """イベントをM5Stack向けの正規化状態へ変換する"""
        self.sequence += 1
        self.state = {
            "state": state,
            "message": message,
            "sequence": self.sequence,
            "timestamp": int(time.time()),
            "last_event": event_type,
        }

    def _apply_event(self, data: dict):
        """Hookイベントを状態へ反映する"""
        event_type = data.get("event", "unknown")
        explicit_state = data.get("state") or data.get("session_status")

        if explicit_state:
            state = explicit_state
            if state not in {
                STATE_IDLE,
                STATE_IN_PROGRESS,
                STATE_WAITING_ON_USER,
                STATE_COMPLETED,
                STATE_ERROR,
            }:
                state = STATE_IDLE
            message = data.get("message") or data.get("msg") or state
            self._set_state(state, str(message)[:80], event_type)
            return

        event_states = {
            "session_start": (STATE_IDLE, "Ready"),
            "prompt_submit": (STATE_IN_PROGRESS, "Working"),
            "stop": (STATE_COMPLETED, "Done"),
            "session_end": (STATE_COMPLETED, "Done"),
            "tool_start": (STATE_IN_PROGRESS, "Working"),
            "tool_use": (STATE_IDLE, "Ready"),
            "file_save": (STATE_IDLE, "Saved"),
            "tool_done": (STATE_IDLE, "Ready"),
            "waiting": (STATE_WAITING_ON_USER, "Waiting"),
            "approved": (STATE_IN_PROGRESS, "Working"),
            "error": (STATE_ERROR, "Error"),
        }
        state, message = event_states.get(event_type, (STATE_IDLE, "Ready"))
        self._set_state(state, message, event_type)

    def _snapshot(self) -> dict:
        """BLE送信用の状態スナップショットを作成する"""
        return {
            "v": 1,
            "type": "state",
            "state": self.state["state"],
            "message": self.state["message"],
            "sequence": self.state["sequence"],
            "timestamp": self.state["timestamp"],
        }

    async def scan_and_connect(self):
        """M5Stack Basicをスキャンして接続する"""
        while True:
            print(f"[BLE] スキャン開始... (prefix: {DEVICE_NAME_PREFIX})")
            device = None
            try:
                devices = await BleakScanner.discover(timeout=5.0)
                for candidate in devices:
                    if candidate.name and (
                        candidate.name.startswith(DEVICE_NAME_PREFIX)
                        or candidate.name.startswith(DEVICE_NAME_FALLBACK)
                    ):
                        device = candidate
                        break

                if device is None:
                    print("[BLE] デバイスが見つかりません。再スキャンします...")
                    await asyncio.sleep(2)
                    continue

                print(f"[BLE] 発見: {device.name} ({device.address})")
                self.client = BleakClient(
                    device.address,
                    disconnected_callback=self._on_disconnect,
                    timeout=30.0,
                )
                await self.client.connect()
                self.connected = True
                print(f"[BLE] 接続完了: {device.name}")

                try:
                    await self.client.start_notify(NUS_TX_UUID, self._on_notify)
                    print("[BLE] Notify購読開始")
                except Exception as error:
                    print(f"[BLE] Notify購読失敗: {error}")

                await asyncio.sleep(0.5)
                await self._send_time_sync()
                await self.send_state()
                print("[BLE] 初期化完了 - 通信準備OK")
                return
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.connected = False
                self.client = None
                print(f"[BLE] 接続失敗: {error}")
                await asyncio.sleep(5)

    def _on_disconnect(self, client: BleakClient):
        """切断コールバック"""
        print("[BLE] 切断されました。再接続を試みます...")
        self.connected = False
        self.client = None
        if self._reconnect_task is None or self._reconnect_task.done():
            try:
                self._reconnect_task = asyncio.create_task(self.scan_and_connect())
            except RuntimeError:
                pass

    def _on_notify(self, sender, data: bytearray):
        """M5Stackからのnotify受信"""
        self._rx_buffer += data.decode("utf-8", errors="replace")
        while "\n" in self._rx_buffer:
            line, self._rx_buffer = self._rx_buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                self._handle_device_message(json.loads(line))
            except json.JSONDecodeError:
                print(f"[BLE RX] パースエラー: {line}")

    def _handle_device_message(self, message: dict):
        """M5StackからのACKや状態通知を処理する"""
        if message.get("type") == "ack":
            print(
                f"[BLE RX] ACK sequence={message.get('sequence')} "
                f"ok={message.get('ok')}"
            )
        elif "ack" in message:
            print(f"[BLE RX] ACK {message['ack']} ok={message.get('ok')}")

    async def send_to_device(self, data: dict):
        """JSONを改行付きでM5Stackへ送信する"""
        if not self.connected or not self.client:
            print("[BLE] 未接続のため送信スキップ")
            return False

        payload = (json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        lock = self._get_send_lock()
        async with lock:
            print(f"[BLE TX] 送信: {payload.decode().strip()}")
            for index in range(0, len(payload), 20):
                try:
                    await self.client.write_gatt_char(
                        NUS_RX_UUID,
                        payload[index : index + 20],
                        response=False,
                    )
                except Exception as error:
                    self.connected = False
                    print(f"[BLE TX] 送信エラー: {error}")
                    return False
        return True

    async def send_state(self):
        """最新状態をM5Stackへ送信する"""
        return await self.send_to_device(self._snapshot())

    async def _send_time_sync(self):
        """時刻同期メッセージを送信する"""
        utc_offset = -(time.timezone if not time.daylight else time.altzone)
        await self.send_to_device({"type": "time", "time": [int(time.time()), utc_offset]})

    async def heartbeat_loop(self):
        """定期的に最新状態を再送する"""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if self.connected:
                await self.send_state()


bridge = BuddyBridge()


async def handle_event(request: web.Request) -> web.Response:
    """Kiro Hookからイベントを受信する"""
    try:
        data = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"error": "invalid json"}, status=400)

    event_type = data.get("event", "unknown")
    print(f"[HTTP] イベント受信: {event_type} @ {time.strftime('%H:%M:%S')}")
    bridge._apply_event(data)
    await bridge.send_state()
    return web.json_response({"ok": True, "state": bridge.state})


async def handle_status(request: web.Request) -> web.Response:
    """ブリッジの接続状態と最新状態を返す"""
    return web.json_response({"connected": bridge.connected, "state": bridge.state})


async def handle_send(request: web.Request) -> web.Response:
    """デバッグ用に任意のJSONを送信する"""
    try:
        data = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"error": "invalid json"}, status=400)
    return web.json_response({"ok": await bridge.send_to_device(data)})


async def start_ble(app):
    """BLE接続とハートビートを開始する"""
    app["ble_task"] = asyncio.create_task(bridge.scan_and_connect())
    app["heartbeat_task"] = asyncio.create_task(bridge.heartbeat_loop())


async def cleanup(app):
    """終了時にBLEとタスクを停止する"""
    for key in ("ble_task", "heartbeat_task"):
        task = app.get(key)
        if task:
            task.cancel()
    if bridge.client and bridge.connected:
        await bridge.client.disconnect()


def main():
    """エントリポイント"""
    app = web.Application()
    app.router.add_post("/event", handle_event)
    app.router.add_get("/status", handle_status)
    app.router.add_post("/send", handle_send)
    app.on_startup.append(start_ble)
    app.on_cleanup.append(cleanup)

    print(f"[Bridge] 起動中... http://{HTTP_HOST}:{HTTP_PORT}")
    print(f"[Bridge] M5Stackデバイス名prefix: {DEVICE_NAME_PREFIX}")
    web.run_app(app, host=HTTP_HOST, port=HTTP_PORT, print=None)


if __name__ == "__main__":
    main()
