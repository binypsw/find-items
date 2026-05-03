# Find Item — Project Context for Claude

> **⚠️ DO NOT read PLAN.md** — it is 1,400+ lines and will waste your context.
> Start with the "NEXT SESSION: DO THIS FIRST" block below, then work through it.

Thai e-commerce price comparison tool. Monitors prices across Lazada, Kaidee, Shopee, JIB, BNN, Priceza.

---

## 🚀 NEXT SESSION: DO THIS FIRST

**Immediately execute these tasks in order — no need to re-read PLAN.md:**

### 1. 🔑 Shopee cookies (NEEDS USER ACTION — skip if user hasn't provided)
The user must log into Shopee in Chrome, export cookies `SPC_F, SPC_EC, SPC_U, SPC_CDS, SPC_ST`,
and paste them. Then store in DB:
```sql
INSERT INTO account_sessions (source_id, label, cookies_encrypted, status)
VALUES ('shopee', 'main', '<encrypted>', 'active');
```
The `ShopeeScraper` already reads from `self.deps.cookie_store` — no code changes needed.

### 2. 🔑 Facebook Marketplace (NEEDS USER ACTION — skip if user hasn't provided)
`backend/shared/scraper/plugins/facebook.py` — scraper skeleton exists but needs real FB cookies.
BrowserlessClient supports cookie injection: `async with client.context(cookies=[...])`.
User must log into Facebook in Chrome and export session cookies.

### 3. 🔧 More Thai IT stores (direct HTML scrapers — optional)
BNN and Priceza patterns work well. Remaining candidates (both have access issues):
- **Comquest** (comquest.co.th) — DNS fails from Docker; check if site is live first
- **IT City** (itcity.co.th) — SSL cert issue; search URL pattern still unclear
- **banana.co.th** is a software company, NOT a hardware store — do not scrape
- **BNN (bnn.in.th)** is the BaNANA IT hardware store (Com7 group) — already done ✅
- **it24hrs.com** is a TECH BLOG, not an IT store — do not scrape

### 4. ✅ Product clustering — DONE
`sentence_transformers 3.3.1` installed in worker image. `recluster_orphan_products` ran:
`processed=166, matched=130, created=36`. Products table populated.

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
API docs: http://localhost:3001/api/docs  ← use nginx proxy (port 8000 NOT exposed to host)  
psql: `docker exec find-item-postgres-1 psql -U finditem -d finditem`

---

## Current Status

### ✅ Working
- **Lazada**: Browserless (Playwright) intercepts AJAX catalog response. Returns ~37 relevant items. Relevance filter applied. All items stored as `condition="unknown"` (AJAX response has no condition field).
- **Kaidee**: Browserless + Next.js SSR endpoint. Returns 0 items for DDR4 3600 (real data gap, not a bug).
- **JIB Computer**: curl_cffi + BeautifulSoup HTML parser. Returns ~31 items per search. `enabled=true` in DB.
- **BNN** (bnn.in.th): curl_cffi + BeautifulSoup. English keywords preferred. Progressive fallback (drops tokens until results found). Relevance filter vs original full tokens. Returns ~18 items. `enabled=true` in DB.
- **Priceza** (priceza.com): Thai price aggregator — covers JIB, BNN, Advice, IT City, Power Buy etc. in one request. curl_cffi + BeautifulSoup. English keywords, majority-token relevance filter. Returns ~24 items. `enabled=true` in DB.
- **Query parser**: Multi-tier LLM fallback + Redis 24h cache (prevents quota waste).
- **Dashboard UI**: Sort (score / price ↑↓), condition filter (All/New/Used), result count, auto-refresh every 8s, Run Now button. Auto-sets condition filter from `parsed_query.condition`.
- **New-vs-used comparison UI**: Blue reference bar showing cheapest new price per source (JIB/BNN/Priceza) when `condFilter="used"`. Uses majority-token relevance filter on `parsed_query.keywords_en` to avoid wrong products (e.g. Canon printer instead of DDR4). "ถูกกว่ามือ 1 X%" badge on used cards.
- **Product clustering**: `sentence_transformers 3.3.1` installed in worker. `recluster_orphan_products` ran successfully (processed=166).
- **Ranking**: Improved — uses search's condition preference, percentile-clipped price normalization, recency bonus.
- **nginx**: Docker DNS resolver fix prevents 502 on container restart.

### ❌ Known Issues
- **Shopee**: API returns error 90309999 (bot detection). Needs real session cookies (SPC_F, SPC_EC, SPC_U). Disabled in DB.
- **Facebook Marketplace**: Scraper skeleton exists; needs real FB session cookies. Disabled in DB.
- **Aliexpress**: No scraper yet. Disabled in DB.
- **Advice** (advice.co.th): Blocked by Cloudflare challenge — needs managed scraping API (Scrapfly/ZenRows). Disabled in DB.
- **Gemini quota**: Free tier exhausted daily. Typhoon handles fallback.

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
        jib.py             # curl_cffi + BeautifulSoup HTML scraper
        bnn.py             # curl_cffi + BeautifulSoup, English keywords, progressive fallback
        priceza.py         # curl_cffi + BeautifulSoup, Thai price aggregator (covers many stores)
        facebook.py        # skeleton only — needs real FB cookies
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
      ResultsDashboard.tsx # Sort/filter controls, auto-refresh, Run Now button, new-vs-used reference bar
      ProductCard.tsx      # Source colour badges (Lazada/Kaidee/JIB/Shopee/BNN/Advice/Priceza), % vs new badge
    i18n/
      en.json              # English translations incl. new_ref_label, new_ref_hint
      th.json              # Thai translations incl. new_ref_label, new_ref_hint
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
UPDATE sources SET enabled=true WHERE id='priceza';

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
# Trigger manual search run (use nginx proxy — port 8000 not exposed)
curl -X POST http://localhost:3001/api/searches/4/run -H "Content-Type: application/json" -d '{}'

# Test query parser
curl -X POST http://localhost:3001/api/searches/parse -H "Content-Type: application/json" -d '{"raw_query":"used DDR4 16gb"}'

# Watch worker logs filtered
docker compose logs -f worker | grep -E "(jib|bnn|priceza|lazada|kaidee|error|items_found)"

# Check Redis query cache
docker exec find-item-redis-1 redis-cli -n 0 KEYS "qparse:*"

# Trigger product clustering
docker exec find-item-worker-1 python3 -c "from worker.celery_app import celery_app; celery_app.send_task('worker.tasks.scrape_task.recluster_orphan_products')"
```

## Known Gotchas

- **Thai chars in Git Bash curl**: Shell corrupts Thai to `???`. Use browser/Postman for Thai queries.
- **`docker compose restart` doesn't reload env vars**: Use `docker compose up -d --force-recreate <service>` instead.
- **`docker compose restart worker` needed after plugin edits**: Worker doesn't hot-reload. After editing any `plugins/*.py`, run `docker compose restart worker` (no rebuild needed unless you changed requirements).
- **API port 8000 NOT exposed to host**: Always use `localhost:3001/api/...` through nginx. Direct `localhost:8000` will be refused.
- **Shopee error 90309999**: Not a code bug — Shopee actively blocks automation. Need real session.
- **Lazada `condition="unknown"`**: Lazada AJAX response has no condition field → all Lazada listings stored as `condition="unknown"`. The "Used" filter intentionally includes `condition="unknown"` items so Lazada results still appear when user filters by used.
- **Lazada bot protection (`/punish` tmd page)**: Already fixed — using Browserless avoids this.
- **Kaidee buildId cache**: `KaideeScraper._build_id` is class-level. Stale ID triggers auto-refresh on 404.
- **`normalize_keywords` priority in BNN/Priceza**: These scrapers override `normalize_keywords` to prefer `keywords_en` first (most Thai stores index in English). Base class uses raw_query first.
- **BNN progressive fallback**: Drops trailing tokens until results are found, but relevance filter always checks against the **original full keyword tokens** (not the broadened fallback). This prevents flooding results from the broadened search.
- **Priceza price selector**: Use `.pz-pdb-price` (base class only), NOT `.pz-pdb-price.pd-group`. The `.pd-group` subclass only matches range-price items; single-price items use `.pz-pdb-price` only — selecting both classes misses them.
- **Reference bar wrong products**: `newRefPrices` in ResultsDashboard uses majority-token filter on `parsed_query.keywords_en` to avoid returning unrelated "new" items (e.g. Canon printer when searching for DDR4).
- **banana.co.th**: This is a SOFTWARE COMPANY, not an IT hardware store. Do not attempt to scrape it.
- **it24hrs.com**: This is a TECH BLOG, not an IT store. Do not attempt to scrape it.
- **Worker rebuild needed**: After adding packages to `requirements.txt`, run `docker compose build worker && docker compose up -d worker`.
- **Frontend rebuild needed**: After editing `frontend/src/`, run `docker compose build frontend && docker compose up -d frontend`.
- **Worktree vs main**: Changes in `.claude/worktrees/dreamy-raman-ddf764/` are the git-tracked branch. Docker containers bind-mount from `C:/Users/binsg/Desktop/workspace/find-item/` (main). Keep both in sync with `cp`.
