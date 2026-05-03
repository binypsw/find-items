# Find Item — Project Context for Claude

> **⚠️ DO NOT read PLAN.md** — it is 1,400+ lines and will waste your context.
> Start with the "NEXT SESSION: DO THIS FIRST" block below, then work through it.

Thai e-commerce price comparison tool. Monitors prices across Lazada, Kaidee, Shopee, JIB.

---

## 🚀 NEXT SESSION: DO THIS FIRST

**Immediately execute these tasks in order — no need to re-read PLAN.md:**

### 1. ✅ Shopee cookies (NEEDS USER ACTION — skip if user hasn't provided)
The user must log into Shopee in Chrome, export cookies `SPC_F, SPC_EC, SPC_U, SPC_CDS, SPC_ST`,
and paste them. Then store in DB:
```sql
INSERT INTO account_sessions (source_id, label, cookies_encrypted, status)
VALUES ('shopee', 'main', '<encrypted>', 'active');
```
The `ShopeScraper` already reads from `self.deps.cookie_store` — no code changes needed.

### 2. 🔧 Add IT24hrs scraper (next free source to try)
IT24hrs.com (it24hrs.com) is a Thai IT store. Its search page renders client-side.
Try: Browserless + intercept XHR pattern (same as Lazada). Use `source_id = "it24hrs"`.
The source row exists in DB (`enabled=false`) — enable after scraper works.

### 3. 🔧 Facebook Marketplace (needs FB session cookies)
`backend/shared/scraper/plugins/facebook.py` — scraper skeleton exists but needs real FB cookies.
BrowserlessClient supports cookie injection: `async with client.context(cookies=[...])`.
User must log into Facebook in Chrome and export session cookies.

### 4. ✅ Product clustering — verify it works
`sentence_transformers 3.3.1` is now installed in the worker image.
Run: `docker exec find-item-worker-1 python3 -c "from worker.celery_app import celery_app; celery_app.send_task('worker.tasks.scrape_task.recluster_orphan_products')"`
Then check: `docker exec find-item-postgres-1 psql -U finditem -d finditem -c "SELECT COUNT(*) FROM products;"`

---

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

---

## Current Status

### ✅ Working
- **Lazada**: Browserless (Playwright) intercepts AJAX catalog response. Returns ~37 relevant items. Relevance filter applied.
- **Kaidee**: Browserless + Next.js SSR endpoint. Returns 0 items for DDR4 3600 (real data gap, not a bug).
- **JIB Computer** (NEW): curl_cffi + BeautifulSoup HTML parser. Returns ~31 items per search. `enabled=true` in DB.
- **Query parser**: Multi-tier LLM fallback + Redis 24h cache (prevents quota waste).
- **Dashboard UI**: Sort (score / price ↑↓), condition filter (All/New/Used), result count, auto-refresh every 8s, Run Now button.
- **Product clustering**: `sentence_transformers 3.3.1` installed in worker. `recluster_orphan_products` Celery task ready.
- **Ranking**: Improved — uses search's condition preference, percentile-clipped price normalization, recency bonus.
- **nginx**: Docker DNS resolver fix prevents 502 on container restart.

### ❌ Known Issues
- **Shopee**: API returns error 90309999 (bot detection). Needs real session cookies (SPC_F, SPC_EC, SPC_U).
- **Advice** (advice.co.th): Blocked by Cloudflare challenge — needs managed scraping API (Scrapfly/ZenRows).
- **Gemini quota**: Free tier exhausted daily. Typhoon handles fallback.
- **facebook / aliexpress / priceza / it24hrs**: Disabled in DB (no working scraper yet).

---

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
        jib.py             # curl_cffi + BeautifulSoup HTML scraper (NEW)
    services/
      query_parser.py      # 3-tier LLM parse + Redis cache + _post_process
    core/
      browserless_client.py  # Playwright CDP client, stealth=true enabled
      embeddings.py          # sentence-transformers wrapper (paraphrase-multilingual-MiniLM-L12-v2)
  worker/
    tasks/
      scrape_task.py       # run_search, scrape_source, recluster_orphan_products Celery tasks
  api/
    routes/
      dashboard.py         # GET /api/dashboard/{id}/top — scoring uses search condition preference
frontend/
  src/
    components/
      ResultsDashboard.tsx # Sort/filter controls, auto-refresh, Run Now button
      ProductCard.tsx      # Source colour badges (Lazada/Kaidee/JIB/Shopee/Advice/Priceza)
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

## Database Quick Reference

```sql
-- Check sources
SELECT id, enabled, tier FROM sources;

-- Enable a source
UPDATE sources SET enabled=true WHERE id='jib';

-- Check recent scrape runs
SELECT source_id, status, items_found, started_at FROM scrape_runs ORDER BY id DESC LIMIT 10;

-- Fix stuck RUNNING runs
UPDATE scrape_runs SET status='failed', finished_at=NOW()
WHERE status='running' AND started_at < NOW() - INTERVAL '30 minutes';

-- Check listings quality
SELECT source_id, COUNT(*), MIN(current_price_thb), MAX(current_price_thb) FROM listings GROUP BY source_id;

-- Check products (after clustering)
SELECT COUNT(*) FROM products;
```

## Scraper Design Pattern

```python
class MyScraper(AbstractScraper):
    source_id = "mysource"
    display_name = "My Source"
    base_url = "https://example.com"
    config = ScraperConfig(tier="direct", rate_limit_rps=0.3)

    async def search(self, query: StructuredQuery, limit=50) -> AsyncIterator[RawListing]:
        keyword = self.normalize_keywords(query)  # returns raw_query first
        # curl_cffi for direct, or self.deps.browserless.context() for browser
        yield self._normalize(item)

    async def get_detail(self, url: str) -> RawListing | None:
        ...
```

Plugin is auto-discovered — just drop `mysource.py` in `backend/shared/scraper/plugins/`.

## Common Debug Commands

```bash
# Trigger manual search run
curl -X POST http://localhost:8000/api/searches/4/run -H "Content-Type: application/json" -d '{}'

# Test query parser (use browser/Postman for Thai chars — curl on Git Bash corrupts them)
curl -X POST http://localhost:8000/api/searches/parse -H "Content-Type: application/json" -d '{"raw_query":"used DDR4 16gb"}'

# Watch worker logs filtered
docker compose logs -f worker | grep -E "(jib|lazada|kaidee|error|items_found)"

# Check Redis query cache
docker exec find-item-redis-1 redis-cli -n 0 KEYS "qparse:*"

# Trigger product clustering
docker exec find-item-worker-1 python3 -c "from worker.celery_app import celery_app; celery_app.send_task('worker.tasks.scrape_task.recluster_orphan_products')"
```

## Known Gotchas

- **Thai chars in Git Bash curl**: Shell corrupts Thai to `???`. Use browser/Postman for Thai queries.
- **`docker compose restart` doesn't reload env vars**: Use `docker compose up -d --force-recreate <service>` instead.
- **Shopee error 90309999**: Not a code bug — Shopee actively blocks automation. Need real session.
- **Lazada bot protection (`/punish` tmd page)**: Already fixed — using Browserless avoids this.
- **Kaidee buildId cache**: `KaideeScraper._build_id` is class-level. Stale ID triggers auto-refresh on 404.
- **`normalize_keywords` priority**: raw_query → keywords_th → keywords_en → keywords (prevents doubling Thai+English).
- **Worker rebuild needed**: After adding packages to `requirements.txt`, run `docker compose build worker && docker compose up -d worker`.
- **Frontend rebuild needed**: After editing `frontend/src/`, run `docker compose build frontend && docker compose up -d frontend`.
- **Worktree vs main**: Changes in `.claude/worktrees/dreamy-raman-ddf764/` are the git-tracked branch. Docker containers bind-mount from `C:/Users/binsg/Desktop/workspace/find-item/` (main). Keep both in sync.
