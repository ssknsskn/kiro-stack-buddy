"""BLEテスト: M5Stackに接続してデータ送信"""
import asyncio
from bleak import BleakClient, BleakScanner

NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


async def test():
    print("スキャン (10秒)...")
    devices = await BleakScanner.discover(timeout=10.0)
    device = None
    for d in devices:
        if d.name and ("KiroBuddy" in d.name or "MPY" in d.name):
            device = d
            print(f"発見: {d.name} ({d.address})")
    if not device:
        print("NOT FOUND - M5Stackがアドバタイズしているか確認")
        return

    print("接続中...")
    client = BleakClient(device.address, timeout=20.0)
    await client.connect()
    print(f"CONNECTED: {client.is_connected}")

    # notify callback
    def on_notify(sender, data):
        print(f"[NOTIFY] {data}")

    await client.start_notify(NUS_TX_UUID, on_notify)
    await asyncio.sleep(2)

    # 状態スナップショット送信。Bridgeと同じく20バイト単位に分割する。
    msg = b'{"v":1,"type":"state","state":"in_progress","message":"Working","sequence":1}\n'
    print(f"送信: {msg}")
    for index in range(0, len(msg), 20):
        await client.write_gatt_char(
            NUS_RX_UUID,
            msg[index : index + 20],
            response=False,
        )

    await asyncio.sleep(5)
    await client.disconnect()
    print("DONE")


asyncio.run(test())
