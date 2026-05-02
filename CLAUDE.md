# Find Item — Project Context for Claude

Thai e-commerce price comparison tool. Monitors prices across Lazada, Kaidee, Shopee.

## Stack

| Layer | Tech |
|-------|------|
| Backend API | FastAPI + SQLAlchemy async (Python 3.11) |
| Worker | Celery + Redis (scraping tasks) |
| Scrapers | curl_cffi + Playwright via Browserless |
| LLM parser | Gemini 2.0 Flash → Typhoon v2.5 → Regex (fallback chain) |
| DB | PostgreSQL 16 + pgvector |
| Cache | Redis (Celery broker on DB1, query cache on DB0) |
| Frontend | React + nginx (port 3001 → proxies to API:8000) |

## Running the project

```bash
cd C:/Users/binsg/Desktop/workspace/find-item
docker compose up -d          # start all services
docker compose logs -f worker # watch scraper logs
```

Frontend: http://localhost:3001  
API docs: http://localhost:8000/docs  
psql: `docker exec find-item-postgres-1 psql -U finditem -d finditem`

## Current Status

### ✅ Working
- **Lazada**: Browserless (Playwright) intercepts AJAX catalog response. Returns ~37 relevant items. Relevance filter applied.
- **Kaidee**: Browserless + Next.js SSR endpoint. Returns 0 items for DDR4 3600 (real data gap, not a bug). Relevance filter and condition-word stripping in place.
- **Query parser**: Multi-tier LLM fallback + Redis 24h cache (prevents quota waste). `_post_process` fixes Thai condition/keyword gaps.
- **nginx**: Docker DNS resolver fix prevents 502 on container restart.

### ❌ Known Issues
- **Shopee**: API returns error 90309999 (bot detection). Requires real Shopee session cookies (SPC_F, SPC_EC, SPC_U). Scraper is in place but yields 0 items without cookies.
- **Gemini quota**: Free tier exhausted daily (20 req/day for 2.5-flash, ~1500/day for 2.0-flash). Typhoon handles fallback.
- **advice / jib / priceza / aliexpress**: Disabled in DB (no scraper plugin). Status set to `enabled=false`.

## Key Files

```
backend/
  shared/
    scraper/
      base.py              # AbstractScraper — normalize_keywords uses raw_query first
      types.py             # StructuredQuery (has raw_query field), RawListing
      manager.py           # get_scraper() factory, injects BrowserlessClient
      plugins/
        lazada.py          # Browserless AJAX intercept + relevance filter
        kaidee.py          # Browserless Next.js SSR + condition-word strip + relevance filter
        shopee.py          # Browserless + route interception (blocked by 90309999)
    services/
      query_parser.py      # 3-tier LLM parse + Redis cache + _post_process
    core/
      browserless_client.py  # Playwright CDP client, stealth=true enabled
  worker/
    tasks/
      scrape_task.py       # run_search → scrape_source Celery tasks
frontend/
  nginx.conf               # Docker DNS resolver, variable proxy_pass (prevents 502)
.env                       # API keys, DB creds, GEMINI_MODEL=gemini-2.0-flash
```

## Architecture: How a Search Works

1. User creates search via frontend → `POST /api/searches`
2. API calls `parse_query(raw_query)` → Redis cache check → Gemini/Typhoon/Regex → stores `parsed_query` in DB
3. User triggers run → `POST /api/searches/{id}/run`
4. Celery `run_search` task dispatches `scrape_source` sub-tasks per enabled source
5. Each `scrape_source` reads `search.parsed_query` from DB, builds `StructuredQuery`, calls scraper plugin
6. Scraper plugin uses Browserless or curl_cffi, applies relevance filter, upserts to `listings` table
7. Live events published via Redis pubsub → frontend SSE

## Scraper Design Pattern

```python
class MyScraper(AbstractScraper):
    source_id = "mysource"
    config = ScraperConfig(tier="browserless", rate_limit_rps=0.3)

    async def search(self, query: StructuredQuery, limit=50) -> AsyncIterator[RawListing]:
        keyword = self.normalize_keywords(query)  # returns raw_query first
        async with self.deps.browserless.context(locale="th-TH") as ctx:
            page = await ctx.new_page()
            # ... intercept API or scrape DOM
            yield self._normalize(item)
```

## Database Quick Reference

```sql
-- Check sources
SELECT id, enabled, tier FROM sources;

-- Re-enable a source
UPDATE sources SET enabled=true WHERE id='shopee';

-- Check recent scrape runs
SELECT source_id, status, items_found, started_at FROM scrape_runs ORDER BY id DESC LIMIT 10;

-- Fix stuck RUNNING runs
UPDATE scrape_runs SET status='failed', finished_at=NOW()
WHERE status='running' AND started_at < NOW() - INTERVAL '30 minutes';

-- Check listings quality
SELECT source_id, COUNT(*) FROM listings GROUP BY source_id;
```

## Pending / Next Steps

1. **Shopee session cookies**: Login to Shopee in Chrome → export SPC_F, SPC_EC, SPC_U, SPC_CDS, SPC_ST cookies → store in cookie_store table → Shopee scraper will use them via `self.deps.cookie_store`.

2. **Add more Thai sources**: JIB (jib.co.th), Advice (advice.co.th), IT24hrs — these tech stores likely have less bot-protection than Lazada/Shopee.

3. **Facebook Marketplace**: Needs Facebook session cookies stored in cookie_store. BrowserlessClient supports cookie injection: `async with client.context(cookies=[...])`.

4. **Product clustering**: `recluster_orphan_products` Celery task already written — links listings to product entities via pgvector cosine similarity. Needs pgvector extension verified.

5. **Push to GitHub**: `git push origin main` (must be done by user, not Claude — safety policy blocks pushing to main).

## Common Debug Commands

```bash
# Trigger manual search run
curl -X POST http://localhost:8000/api/searches/3/run -H "Content-Type: application/json" -d '{}'

# Test query parser (use browser or Postman — curl on Git Bash corrupts Thai chars)
curl -X POST http://localhost:8000/api/searches/parse -H "Content-Type: application/json" -d '{"raw_query":"used DDR4 16gb"}'

# Watch worker logs filtered
docker compose logs -f worker | grep -E "(shopee|lazada|kaidee|error|items_found)"

# Check Redis query cache
docker exec find-item-redis-1 redis-cli -n 0 KEYS "qparse:*"

# Clear query cache (force re-parse)
docker exec find-item-redis-1 redis-cli -n 0 FLUSHDB
```

## Known Gotchas

- **Thai chars in Git Bash curl**: Shell corrupts Thai to `???`. Use browser/Postman for Thai queries.
- **`docker compose restart` doesn't reload env vars**: Use `docker compose up -d --force-recreate <service>` instead.
- **Shopee error 90309999**: Not a code bug — Shopee actively blocks automation. Need real session.
- **Lazada bot protection (`/punish` tmd page)**: Already fixed — using Browserless avoids this.
- **Kaidee buildId cache**: `KaideeScraper._build_id` is class-level. Stale ID triggers auto-refresh on 404.
- **`normalize_keywords` priority**: raw_query → keywords_th → keywords_en → keywords (prevents doubling Thai+English).
