---
name: Known Pre-existing Issues in find-items
description: Pre-existing code issues found during review — not introduced by recent commits but worth flagging when relevant files are touched
type: project
---

## alembic.ini hardcodes DB credentials

`backend/alembic.ini` has `sqlalchemy.url = postgresql+asyncpg://finditem:changeme@postgres:5432/finditem` as a literal string, not read from `.env`.

**Why:** Was set up early in project without env-var support for alembic. The actual password `changeme` suggests it was intended as a placeholder.

**How to apply:** Flag this when reviewing any commit that touches `alembic.ini`, `alembic/env.py`, or DB connection setup. Recommend overriding via `alembic/env.py` reading `os.environ` or using `--config` option.

---

## --reload flag in docker-compose api service

`docker-compose.yml` api service command includes `--reload` (uvicorn hot-reload). This is dev-only behavior — degrades performance and should not be used in production.

**Why:** Project is dev-only for now so it was acceptable. No separate prod compose file exists.

**How to apply:** Flag if user asks about production deployment or creates a prod compose file. Recommend either removing `--reload` or creating `docker-compose.prod.yml` override.

---

## Port 8000 exposed to host in docker-compose

`api` service exposes `8000:8000` directly. The intended access pattern is nginx proxy on port 3001. Exposing 8000 bypasses nginx and any middleware it provides.

**Why:** Convenience for local debugging (direct API docs access at localhost:8000/docs).

**How to apply:** Flag if user asks about production hardening — recommend removing the port mapping in prod.
