import asyncio
import json
import time

import websockets


async def main():
    uri = "ws://127.0.0.1:8666/ws/stream"
    got = []
    async with websockets.connect(uri) as ws:
        async def recv():
            try:
                async for msg in ws:
                    got.append(json.loads(msg))
                    if len(got) >= 1:
                        break
            except Exception as e:
                print("recv err:", e)
        task = asyncio.create_task(recv())
        # 等一轮采集广播（间隔 10s），最多 25s
        deadline = time.time() + 95
        while not got and time.time() < deadline:
            await asyncio.sleep(1)
        task.cancel()
    if got:
        first = got[0]
        print("WS 收到消息: type=%s items=%d" % (first.get("type"), len(first.get("items", []))))
        if first.get("items"):
            it = first["items"][0]
            print("  sample: module=%s ts=%s content=%.60s" % (it.get("module"), it.get("ts_text"), it.get("content", "")))
    else:
        print("WS 25s 内未收到推送")


asyncio.run(main())
