"""WebSocket 实时增量推送。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/stream")
async def stream(ws: WebSocket):
    await ws.accept()
    collector = ws.app.state.collector
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    collector.subscribe(queue)
    try:
        while True:
            msg = await queue.get()
            await ws.send_json(msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        collector.unsubscribe(queue)
        try:
            await ws.close()
        except Exception:
            pass
