#!/bin/sh
set -e

echo "[entrypoint] Running alembic migrations..."
if ! alembic upgrade head; then
    echo "[entrypoint] ERROR: alembic migration failed — aborting startup" >&2
    exit 1
fi
echo "[entrypoint] Migrations complete."

exec "$@"
