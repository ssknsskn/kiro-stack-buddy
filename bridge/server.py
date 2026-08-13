"""
Kiro Buddy Bridge - ローカルHTTPサーバー + BLE Central
Kiro HookからHTTPでイベントを受信し、BLE経由でM5Stack Basicに転送する
"""

import asyncio
import json
import signal
import sys
import time
from typing import Optional

from aiohttp import web
from bleak import BleakClient, BleakScanner

# Nordic UART Service UUIDs
NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Mac → M5Stack (write)
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # M5Stack → Mac (notify)

# ブリッジサーバー設定
HTTP_HOST = "127.0.0.1"
HTTP_PORT = 9876
DEVICE_NAME_PREFIX = "KiroBuddy"
DEVICE_NAME_FALLBACK = "MPY ESP32"
HEARTBEAT_INTERVAL = 10  # 秒


class BuddyBridge:
    """BLE接続管理とHTTPサーバーを統合するブリッジ"""

    def __init__(self):
        self.client: Optional[BleakClient] = None
        self.connected = False
        self.state = {
            "total": 0,
            "running": 0,
            "waiting": 0,
            "msg": "idle",
            "tokens": 0,
            "last_event": "",
            "last_event_time": 0,
        }
        self._rx_buffer = ""

    async def scan_and_connect(self):
        """M5Stack Basicをスキャンして接続する"""
        print(f"[BLE] スキャン開始... (prefix: {DEVICE_NAME_PREFIX})")
        device = None

        while device is None:
            devices = await BleakScanner.discover(timeout=5.0)
            for d in devices:
                if d.name and (
                    d.name.startswith(DEVICE_NAME_PREFIX)
                    or d.name.startswith(DEVICE_NAME_FALLBACK)
                ):
                    device = d
                    break
            if device is None:
                print("[BLE] デバイスが見つかりません。再スキャンします...")
                await asyncio.sleep(2)

        print(f"[BLE] 発見: {device.name} ({device.address})")
        self.client = BleakClient(
            device.address,
            disconnected_callback=self._on_disconnect,
            timeout=30.0,
        )
        await self.client.connect()
        self.connected = True
        print(f"[BLE] 接続完了: {device.name}")

        # サービス検出を待つ
        await asyncio.sleep(2)

        # 利用可能なサービスを確認
        services = self.client.services
        print(f"[BLE] サービス数: {len(services.services)}")
        for service in services:
            print(f"  サービス: {service.uuid}")
            for char in service.characteristics:
                print(f"    特性: {char.uuid} props={char.properties}")

        # Notify購読 (M5Stack → Mac)
        try:
            await self.client.start_notify(NUS_TX_UUID, self._on_notify)
            print("[BLE] Notify購読開始")
        except Exception as e:
            print(f"[BLE] Notify購読失敗: {e}")

        # 初回接続時に時刻同期を送信
        await asyncio.sleep(0.5)
        await self._send_time_sync()
        print("[BLE] 初期化完了 - 通信準備OK")

    def _on_disconnect(self, client: BleakClient):
        """切断コールバック"""
        print("[BLE] 切断されました。再接続を試みます...")
        self.connected = False
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._reconnect())
        except RuntimeError:
            pass

    async def _reconnect(self):
        """再接続ループ"""
        await asyncio.sleep(3)
        try:
            await self.scan_and_connect()
        except Exception as e:
            print(f"[BLE] 再接続失敗: {e}")
            await asyncio.sleep(5)
            asyncio.get_event_loop().create_task(self._reconnect())

    def _on_notify(self, sender, data: bytearray):
        """M5Stackからのnotify受信"""
        text = data.decode("utf-8", errors="replace")
        self._rx_buffer += text

        while "\n" in self._rx_buffer:
            line, self._rx_buffer = self._rx_buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                self._handle_device_message(msg)
            except json.JSONDecodeError:
                print(f"[BLE RX] パースエラー: {line}")

    def _handle_device_message(self, msg: dict):
        """M5Stackからのメッセージ処理"""
        if "cmd" in msg:
            cmd = msg["cmd"]
            if cmd == "permission":
                print(f"[デバイス] Permission応答: {msg.get('decision')}")
                # TODO: Kiro IDEに結果を返す仕組み（将来拡張）
            elif cmd == "button":
                print(f"[デバイス] ボタン押下: {msg.get('id')}")
        elif "ack" in msg:
            print(f"[デバイス] ACK: {msg['ack']} ok={msg.get('ok')}")

    async def send_to_device(self, data: dict):
        """M5Stackにデータを送信する"""
        if not self.connected or not self.client:
            print("[BLE] 未接続のため送信スキップ")
            return False

        payload = json.dumps(data, ensure_ascii=False) + "\n"
        payload_bytes = payload.encode("utf-8")

        # デバッグ: 送信内容を表示
        print(f"[BLE TX] 送信: {payload.strip()}")

        # BLE MTUに合わせて分割送信 (20バイトが安全)
        mtu_size = 20
        for i in range(0, len(payload_bytes), mtu_size):
            chunk = payload_bytes[i : i + mtu_size]
            try:
                await self.client.write_gatt_char(NUS_RX_UUID, chunk)
            except Exception as e:
                print(f"[BLE TX] 送信エラー: {e}")
                return False

        return True

    async def send_heartbeat(self):
        """現在のステートをハートビートとして送信"""
        ok = await self.send_to_device(self.state)
        if not ok:
            print("[BLE] ハートビート送信失敗")

    async def _send_time_sync(self):
        """時刻同期メッセージを送信"""
        import calendar

        epoch = int(time.time())
        # タイムゾーンオフセット (秒)
        utc_offset = -(time.timezone if time.daylight == 0 else time.altzone)
        await self.send_to_device({"time": [epoch, utc_offset]})

    async def heartbeat_loop(self):
        """定期ハートビート送信ループ"""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if self.connected:
                await self.send_heartbeat()


# グローバルブリッジインスタンス
bridge = BuddyBridge()


# --- HTTP ハンドラ ---


async def handle_event(request: web.Request) -> web.Response:
    """Kiro Hookからのイベント受信エンドポイント"""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid json"}, status=400)

    event_type = data.get("event", "unknown")
    print(f"[HTTP] イベント受信: {event_type} @ {time.strftime('%H:%M:%S')}")

    # ステート更新
    bridge.state["last_event"] = event_type
    bridge.state["last_event_time"] = int(time.time())

    # Kiro セッションステータスに基づいてデバイスに送信
    session_status = data.get("session_status", None)
    if session_status:
        # 新しい形式: Kiroセッションステータスを直接転送
        await bridge.send_to_device({
            "session_status": session_status,
            "msg": data.get("msg", "")
        })
        print(f"  → session_status={session_status}")
        return web.json_response({"ok": True})

    # 従来のイベント形式のサポート (後方互換性)
    if event_type == "session_start":
        bridge.state["total"] += 1
        bridge.state["running"] = 1
        bridge.state["msg"] = "session started"
        print(f"  → running={bridge.state['running']}")

    elif event_type == "session_end":
        bridge.state["running"] = 0
        bridge.state["msg"] = "idle"
        print(f"  → running={bridge.state['running']}")

    elif event_type == "tool_use":
        tool_name = data.get("tool", "")
        bridge.state["running"] = max(0, bridge.state["running"] - 1)
        bridge.state["msg"] = f"completed: {tool_name}"

    elif event_type == "tool_start":
        tool_name = data.get("tool", "")
        bridge.state["running"] += 1
        bridge.state["msg"] = f"starting: {tool_name}"

    elif event_type == "tool_done":
        bridge.state["running"] = max(0, bridge.state["running"] - 1)
        bridge.state["msg"] = "working..."

    elif event_type == "waiting":
        bridge.state["waiting"] += 1
        bridge.state["msg"] = data.get("msg", "waiting for approval")

    elif event_type == "approved":
        bridge.state["waiting"] = max(0, bridge.state["waiting"] - 1)
        bridge.state["msg"] = "approved!"

    elif event_type == "error":
        bridge.state["msg"] = f"error: {data.get('msg', '')}"

    # すぐにデバイスに送信
    await bridge.send_heartbeat()

    return web.json_response({"ok": True})


async def handle_status(request: web.Request) -> web.Response:
    """ブリッジのステータス確認"""
    return web.json_response(
        {
            "connected": bridge.connected,
            "state": bridge.state,
        }
    )


async def handle_send(request: web.Request) -> web.Response:
    """任意のJSONをデバイスに直接送信"""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid json"}, status=400)

    ok = await bridge.send_to_device(data)
    return web.json_response({"ok": ok})


# --- アプリケーション起動 ---


async def start_ble(app):
    """BLE接続をバックグラウンドで開始"""
    app["ble_task"] = asyncio.create_task(bridge.scan_and_connect())
    app["heartbeat_task"] = asyncio.create_task(bridge.heartbeat_loop())


async def cleanup(app):
    """終了時のクリーンアップ"""
    if bridge.client and bridge.connected:
        await bridge.client.disconnect()
    app["ble_task"].cancel()
    app["heartbeat_task"].cancel()


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
