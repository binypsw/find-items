# Find Item — Current Status

_Last updated: 2026-05-10 — verified on new machine after docker compose up_
_Tested with: DDR4 16GB search, scrape run triggered, results confirmed from DB_

## Infrastructure

| Component | Status | Notes |
|---|---|---|
| Docker compose | ✅ All 7 containers up | postgres, redis, api, worker, beat, frontend, browserless |
| DB migrations | ✅ Run manually required | `docker exec find-items-api-1 alembic upgrade head` — DB was empty on first boot |
| nginx proxy (3001) | ✅ Working | `/api/*` routes proxy correctly after migrations |
| API docs (direct) | ✅ Working | http://localhost:8000/docs accessible |
| Frontend | ✅ Working | http://localhost:3001 returns 200 |

## Sources

| Source | Status | Items (DDR4 16GB) | Notes |
|---|---|---|---|
| JIB | ✅ Working | 41 | curl_cffi + BeautifulSoup, fast (~8s) |
| Priceza | ✅ Working | 23 | curl_cffi aggregator, fast (~2s) |
| Lazada | ✅ Working | 40 | Browserless AJAX intercept (~10s) |
| Kaidee | ✅ Working | 0 | Real data gap — no DDR4 listings on Kaidee |
| Shopee | ❌ Bot blocked | 0 | error 90309999 — needs SPC_F, SPC_EC, SPC_U cookies; still enabled in DB |
| Advice | ❌ Failed | 0 | Cloudflare block confirmed; Priceza covers it |
| AliExpress | ❌ Failed | 0 | No real scraper — only stub; should be disabled |
| Facebook | ❌ Disabled | — | Needs FB session cookies |

## Features

| Feature | Status | Notes |
|---|---|---|
| Query parser (Gemini→Typhoon→Regex) | ✅ Working | Regex fallback confirmed (Gemini/Typhoon may be quota-limited) |
| Redis cache for query parser | ✅ Working | Celery + Redis both healthy |
| JIB / Priceza / Lazada scrapers | ✅ Working | Confirmed with live scrape run |
| Kaidee scraper | ✅ Working | Returns 0 = real data gap, not a bug |
| Dashboard API (`/api/dashboard/{id}/top`) | ✅ Working | Returns 10 ranked listings |
| Celery worker + pubsub events | ✅ Working | item_found events published correctly |
| Dashboard UI (sort, filter, auto-refresh, Run Now) | ✅ Expected working | Frontend up; not manually clicked |
| New-vs-used comparison bar | ✅ Expected working | Code unchanged from last known working state |
| Product clustering (sentence-transformers) | ⚠️ Not yet run | products table = 0; need to trigger recluster after scrape |
| Ranking (condition preference, percentile price norm) | ✅ Working | Dashboard returns ordered results |
| Price history charts | ❌ Not implemented | |
| Discord notifications | ❌ Not implemented | |
| Shopee scraper | ❌ Blocked | Bot detection 90309999 — needs cookies |
| Facebook scraper | ❌ Blocked | Needs FB session cookies |

## Data State

| Table | Count | Notes |
|---|---|---|
| listings | 104 | After 1 scrape run (JIB=41, Lazada=40, Priceza=23) |
| products | 0 | Need to run `recluster_orphan_products` task |
| searches | 1 | DDR4 16GB test search |
| scrape_runs | 7 | 1 run × 7 sources |

## Next Tasks

- [x] สร้าง .env บนเครื่องนี้ และ verify docker compose up ทำงานได้
- [x] Verify all sources ด้วย scrape run จริง แล้วอัพ status table นี้
- [ ] **รัน `alembic upgrade head` เป็น startup step** (DB ว่างทุกครั้งที่ postgres volume ถูก reset)
- [ ] **Disable Shopee, AliExpress, Advice ใน DB** — ยัง `enabled=true` แต่ล้มเหลวทุกครั้ง
- [ ] รัน product clustering: `docker exec find-items-worker-1 python3 -c "from worker.celery_app import celery_app; celery_app.send_task('worker.tasks.scrape_task.recluster_orphan_products')"`
- [ ] Shopee cookies (user action required)
- [ ] Facebook cookies + scraper (user action required)
- [ ] Verify agent memory is loaded correctly in coder agent session

## Known Issues on This Machine

- **DB empty on first boot**: Migrations must be run manually — `docker exec find-items-api-1 alembic upgrade head`. Consider adding this to docker-compose healthcheck or entrypoint.
- **Shopee, AliExpress, Advice still `enabled=true` in DB seed**: These run on every scrape but always fail. Should be set to `enabled=false` to avoid wasted Browserless credits.
- **nginx `/api/docs` returns 404**: Normal — FastAPI serves docs at `/docs` not `/api/docs`. Use `http://localhost:8000/docs` directly.
