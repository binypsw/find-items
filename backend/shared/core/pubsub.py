import json
from typing import Any

import structlog
import redis.asyncio as aioredis

from shared.config import get_settings

log = structlog.get_logger()

_CHANNEL_PREFIX = "finditem:runs:"


class RedisPubSub:
    """Thin wrapper for Redis pub/sub used to push live scrape events to the API WebSocket layer."""

    def __init__(self, redis_url: str | None = None):
        settings = get_settings()
        self._url = redis_url or settings.redis_url
        self._client: aioredis.Redis | None = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self._url, decode_responses=True)
        return self._client

    def _channel(self, run_id: int) -> str:
        return f"{_CHANNEL_PREFIX}{run_id}"

    async def publish(self, run_id: int, event: dict[str, Any]) -> None:
        client = await self._get_client()
        channel = self._channel(run_id)
        await client.publish(channel, json.dumps(event))
        log.debug("pubsub.published", run_id=run_id, event_type=event.get("type"))

    async def subscribe(self, run_id: int):
        """Async generator yielding events for a run_id channel."""
        client = await self._get_client()
        pubsub = client.pubsub()
        await pubsub.subscribe(self._channel(run_id))
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield json.loads(message["data"])
        finally:
            await pubsub.unsubscribe(self._channel(run_id))
            await pubsub.aclose()

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
