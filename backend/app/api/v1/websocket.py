"""
WebSocket and SSE endpoints for real-time alert streaming.
Handles local in-memory fallback gracefully if Redis is unavailable.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.db.redis_client import get_redis, ALERT_STREAM_KEY
from app.core.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)

# Active WebSocket connections
_ws_clients: set = set()


@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """WebSocket endpoint — push new alerts in real time."""
    await websocket.accept()
    _ws_clients.add(websocket)
    logger.info("ws_client_connected", clients=len(_ws_clients))

    try:
        r = await get_redis()
        if r is not None:
            pubsub = r.pubsub()
            await pubsub.subscribe(ALERT_STREAM_KEY)
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    await websocket.send_text(data)
        else:
            # Fallback: keep connection open, wait for broadcast
            while True:
                await asyncio.sleep(5)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("ws_error", error=str(e))
    finally:
        _ws_clients.discard(websocket)
        logger.info("ws_client_disconnected", clients=len(_ws_clients))


@router.get("/events/alerts")
async def sse_alerts():
    """Server-Sent Events endpoint — alternative to WebSocket for alert streaming."""

    async def event_generator():
        # Send initial connected signal
        yield "data: {\"type\": \"connected\"}\n\n"

        r = await get_redis()
        if r is not None:
            try:
                pubsub = r.pubsub()
                await pubsub.subscribe(ALERT_STREAM_KEY)
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        data = message["data"]
                        if isinstance(data, bytes):
                            data = data.decode()
                        yield f"data: {data}\n\n"
                    await asyncio.sleep(0)
            except Exception as e:
                logger.warning("sse_redis_error_using_ping_fallback", error=str(e))
                # Fallback to keep-alive comments
                while True:
                    yield ": ping\n\n"
                    await asyncio.sleep(15)
        else:
            # Fallback: keep-alive comments to prevent timeout
            while True:
                yield ": ping\n\n"
                await asyncio.sleep(15)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def broadcast_alert(alert_data: dict) -> None:
    """Broadcast an alert to all connected WebSocket clients directly (used in fallback)."""
    val = json.dumps(alert_data, default=str)
    disconnected = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(val)
        except Exception:
            disconnected.add(ws)
    _ws_clients.difference_update(disconnected)
