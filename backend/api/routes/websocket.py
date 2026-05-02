import asyncio

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.core.pubsub import RedisPubSub

log = structlog.get_logger()
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/runs")
async def ws_runs(websocket: WebSocket, run_id: int | None = None):
    """WebSocket endpoint for live scrape run events.

    Client sends: {"subscribe": <run_id>}
    Server sends: RunEvent JSON objects (progress, item_found, error, completed)
    """
    await websocket.accept()
    pubsub = RedisPubSub()

    subscribed_run_id: int | None = run_id

    try:
        # Wait for initial subscribe message if run_id not in query params
        if not subscribed_run_id:
            msg = await asyncio.wait_for(websocket.receive_json(), timeout=10)
            subscribed_run_id = msg.get("subscribe")

        if not subscribed_run_id:
            await websocket.send_json({"error": "No run_id provided"})
            await websocket.close()
            return

        log.info("ws.subscribed", run_id=subscribed_run_id)

        async for event in pubsub.subscribe(subscribed_run_id):
            await websocket.send_json(event)
            if event.get("type") == "completed":
                break

    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception as e:
        log.warning("ws.error", error=str(e))
    finally:
        await pubsub.close()
