import asyncio

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.core.pubsub import RedisPubSub

log = structlog.get_logger()
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/runs")
async def ws_runs(websocket: WebSocket, run_id: int | None = None):
    """WebSocket endpoint for live scrape run events.

    Client sends: {"subscribe": <run_id>} for a specific run, or {"subscribe": "all"} for global feed.
    Server sends: RunEvent JSON objects (progress, item_found, error, completed)
    """
    await websocket.accept()
    pubsub = RedisPubSub()

    subscribed_run_id: int | str | None = run_id

    try:
        if not subscribed_run_id:
            msg = await asyncio.wait_for(websocket.receive_json(), timeout=10)
            subscribed_run_id = msg.get("subscribe")

        if not subscribed_run_id:
            await websocket.send_json({"error": "No run_id provided"})
            await websocket.close()
            return

        if subscribed_run_id == "all":
            log.info("ws.subscribed_global")
            async for event in pubsub.subscribe_global():
                await websocket.send_json(event)
        else:
            log.info("ws.subscribed", run_id=subscribed_run_id)
            async for event in pubsub.subscribe(int(subscribed_run_id)):
                await websocket.send_json(event)
                if event.get("type") == "completed":
                    break

    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception as e:
        log.warning("ws.error", error=str(e))
    finally:
        await pubsub.close()
