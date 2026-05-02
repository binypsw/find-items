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
RUN pip install --no-cache-dir -r requirements.txt

# ML packages installed separately with CPU-only torch index (uncomment when reaching Phase 4)
# RUN pip install --no-cache-dir -r requirements-ml.txt \
#     --extra-index-url https://download.pytorch.org/whl/cpu

# Playwright browser drivers are NOT needed — worker connects to browserless service via CDP

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Default: Celery worker (override in docker-compose for beat)
CMD ["celery", "-A", "worker.celery_app", "worker", "-l", "info", "-Q", "default,scrape"]
