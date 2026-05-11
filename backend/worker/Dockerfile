FROM python:3.11-slim

WORKDIR /app

# System deps for Playwright client (no browser), torch CPU, lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Base requirements (no heavy ML — those are in requirements-ml.txt, added in Phase 4)
COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir --timeout 300 --retries 5 -r requirements.txt

# Camoufox in its own layer so requirements.txt changes don't bust its cache
RUN pip install --no-cache-dir "camoufox[geoip]==0.4.*"

# Firefox system deps for Camoufox — placed after pip install to preserve pip cache layers
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libx11-xcb1 \
    libxt6 \
    libxss1 \
    libglib2.0-0 \
    libnspr4 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libpangocairo-1.0-0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxext6 \
    libdrm2 \
    libgbm1 \
    fonts-liberation \
    libasound2t64 \
    && rm -rf /var/lib/apt/lists/*

# Pre-download Camoufox patched Firefox binary (cached in Docker layer)
RUN python -m camoufox fetch

# Playwright browser drivers are NOT needed — worker connects to browserless service via CDP

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Default: Celery worker (override in docker-compose for beat)
CMD ["celery", "-A", "worker.celery_app", "worker", "-l", "info", "-Q", "default,scrape"]
