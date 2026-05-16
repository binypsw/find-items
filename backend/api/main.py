import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from shared.config import get_settings
from shared.database import engine
from api.routes.searches import router as searches_router
from api.routes.websocket import router as ws_router
from api.routes.listings import router as listings_router
from api.routes.dashboard import router as dashboard_router
from api.routes.sources import router as sources_router
from api.routes.sessions import router as sessions_router
from api.routes.runs import router as runs_router
from api.routes.alerts import router as alerts_router
from api.routes.config import router as config_router

settings = get_settings()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("api.startup", database_url=settings.database_url.split("@")[-1])
    yield
    await engine.dispose()
    log.info("api.shutdown")


app = FastAPI(
    title="Find-Item API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(searches_router)
app.include_router(ws_router)
app.include_router(listings_router)
app.include_router(dashboard_router)
app.include_router(sources_router)
app.include_router(sessions_router)
app.include_router(runs_router)
app.include_router(alerts_router)
app.include_router(config_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    from sqlalchemy import text
    import redis.asyncio as aioredis

    db_ok = False
    redis_ok = False

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        log.warning("health.db_fail", error=str(e))

    try:
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        redis_ok = True
    except Exception as e:
        log.warning("health.redis_fail", error=str(e))

    status = "ok" if (db_ok and redis_ok) else "degraded"
    return {
        "status": status,
        "api": "ok",
        "db": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
