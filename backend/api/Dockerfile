FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (no playwright/torch/sentence-transformers — keeps image small)
COPY requirements.txt .
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    pydantic \
    pydantic-settings \
    python-multipart \
    "sqlalchemy[asyncio]" \
    asyncpg \
    alembic \
    pgvector \
    "redis==5.2.*" \
    "celery[redis]" \
    httpx \
    structlog \
    python-dotenv \
    cryptography \
    prometheus-client \
    "google-genai>=1.0.0" \
    "openai>=1.58.0"

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY api/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
