from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json
from typing import Set

_clients: Set[WebSocket] = set()


async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    _clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _clients.discard(websocket)
    except Exception:
        _clients.discard(websocket)


async def _async_broadcast(data: dict):
    msg = json.dumps(data)
    dead = []
    for client in _clients:
        try:
            await client.send_text(msg)
        except Exception:
            dead.append(client)
    for d in dead:
        _clients.discard(d)


def broadcast_sync(data: dict):
    """Fire-and-forget broadcast usable from sync route handlers."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_async_broadcast(data))
        else:
            loop.run_until_complete(_async_broadcast(data))
    except RuntimeError:
        pass
