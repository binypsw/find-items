---
name: Docker Compose Patterns in find-items
description: Verified patterns for how docker-compose services are wired in this project
type: project
---

## api service entrypoint pattern

As of commit 3326413, the api service uses:
```
command: sh -c "alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload"
```

- `alembic upgrade head` runs first — idempotent, no-op if schema is current
- `&&` ensures uvicorn only starts if alembic succeeds (fail-fast)
- WORKDIR is `/app` (set in `backend/api/Dockerfile`), `alembic.ini` is at `/app/alembic.ini`
- `script_location = alembic` in alembic.ini means migrations are at `/app/alembic/`

**How to apply:** When reviewing entrypoint changes, verify: (1) alembic runs before uvicorn, (2) `&&` not `;` is used so failures propagate, (3) WORKDIR matches where alembic.ini is.

---

## Health check dependencies

- `api` depends on `postgres` (healthy) and `redis` (healthy)
- `worker` depends on `postgres` (healthy), `redis` (healthy), `browserless` (started)
- `beat` depends on `redis` and `postgres` (no health condition — loose dependency)
- `frontend` depends on `api` (no health condition)

**How to apply:** Flag if a new service is added without appropriate `condition: service_healthy` on its postgres/redis dependencies.

---

## Sources enabled state (as of 2026-05-10)

| source_id | enabled |
|-----------|---------|
| jib | true |
| kaidee | true |
| lazada | true |
| priceza | true |
| advice | false |
| aliexpress | false |
| facebook | false |
| shopee | false |

Disabled sources: Shopee (bot block), AliExpress (stub only), Advice (Cloudflare block), Facebook (needs cookies).
