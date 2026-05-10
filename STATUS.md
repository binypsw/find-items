# Find Item — Current Status

_Last updated: 2026-05-10 — model-number filter + 35% price floor catches clone phones; tested Richell non-electronics search_
_Tested with: DDR4 16GB + S24 Ultra มือสอง (11 clean results, no fakes) + แก้วน้ำ richell มือสอง (37 results, all legitimate cups)_

## Infrastructure

| Component | Status | Notes |
|---|---|---|
| Docker compose | ✅ All 7 containers up | postgres, redis, api, worker, beat, frontend, browserless |
| DB migrations | ✅ Auto-run on startup | `alembic upgrade head` runs before uvicorn in api entrypoint — no manual step needed |
| nginx proxy (3001) | ✅ Working | `/api/*` routes proxy correctly after migrations |
| API docs (direct) | ✅ Working | http://localhost:8000/docs accessible |
| Frontend | ✅ Working | http://localhost:3001 returns 200 |

## Sources

| Source | Status | Items (DDR4 16GB) | Notes |
|---|---|---|---|
| JIB | ✅ Working | 41 | curl_cffi + BeautifulSoup, fast (~8s) |
| BNN | ✅ Working | ~18 | curl_cffi + English keywords; seeded into DB manually (was missing on new machine) |
| Priceza | ✅ Working | 23 | curl_cffi aggregator, fast (~2s) |
| Lazada | ✅ Working | 29 | Browserless AJAX intercept; majority-token relevance filter (keywords_en) |
| Kaidee | ✅ Working | 0 | Real data gap — no DDR4 listings on Kaidee |
| Shopee | ❌ Disabled | 0 | error 90309999 — needs SPC_F, SPC_EC, SPC_U cookies; disabled in DB |
| Advice | ⏸ Skipped | 0 | Cloudflare block confirmed; Priceza covers it; disabled in DB |
| AliExpress | ❌ Disabled | 0 | No real scraper — only stub; disabled in DB |
| Facebook | ❌ Disabled | — | Needs FB session cookies |

## Features

| Feature | Status | Notes |
|---|---|---|
| Query parser (Gemini→Typhoon→Regex) | ✅ Working | Regex fallback confirmed (Gemini/Typhoon may be quota-limited) |
| Redis cache for query parser | ✅ Working | Celery + Redis both healthy |
| JIB / Priceza / Lazada scrapers | ✅ Working | Confirmed with live scrape run |
| Kaidee scraper | ✅ Working | Returns 0 = real data gap, not a bug |
| Dashboard API (`/api/dashboard/{id}/top`) | ✅ Working | Returns up to 200 ranked listings; uses latest run per source only |
| Celery worker + pubsub events | ✅ Working | item_found events published correctly |
| Dashboard UI (sort, filter, auto-refresh, Run Now) | ✅ Working | Verified with S24 Ultra search |
| New-vs-used comparison bar | ✅ Working | Accessory exclusion filter active; shows ฿21,000 for S24 Ultra |
| Product clustering (sentence-transformers) | ✅ Done — processed=104, matched=88, created=16 | products table populated (16 products) |
| Ranking (condition preference, percentile price norm) | ✅ Working | Dashboard returns ordered results |
| Price history charts | ❌ Not implemented | |
| Discord notifications | ❌ Not implemented | |
| Shopee scraper | ❌ Blocked | Bot detection 90309999 — needs cookies |
| Facebook scraper | ❌ Blocked | Needs FB session cookies |

## Data State

| Table | Count | Notes |
|---|---|---|
| listings | 104 | After 1 scrape run (JIB=41, Lazada=40, Priceza=23) |
| products | 16 | Clustered via `recluster_orphan_products` (processed=104, matched=88, created=16) |
| searches | 1 | DDR4 16GB test search |
| scrape_runs | 7 | 1 run × 7 sources |

## Next Tasks

- [x] สร้าง .env บนเครื่องนี้ และ verify docker compose up ทำงานได้
- [x] Verify all sources ด้วย scrape run จริง แล้วอัพ status table นี้
- [x] **รัน `alembic upgrade head` เป็น startup step** — done in docker-compose.yml entrypoint
- [x] **Disable Shopee, AliExpress, Advice ใน DB** — confirmed `enabled=false` in DB
- [x] รัน product clustering — processed=104, matched=88, created=16
- [x] Verify agent memory is loaded correctly in coder agent session
- [x] Fix Lazada relevance filter — majority-token using keywords_en (fixed Nokia 3310 contamination)
- [x] Fix dashboard API stale run bug — use latest completed run per source, not all runs
- [x] Fix reference bar accessory contamination — ACCESSORY_TERMS at module level + "casing" + multi-model detection (≥3 S-model numbers)
- [x] Fix JIB relevance filter — majority-token on keywords_en + normalize_keywords prefers keywords_en
- [x] Fix frontend: filter accessories from main results display; price floor for used results (< 15% of cheapest new = filtered)
- [x] Switch coder/code-reviewer/scraper-research agent model to opus, then reverted to sonnet
- [x] Fix clone/fake phone detection: model-number filter (keywords_en token like "s24" must appear in title) + raise price floor 15%→35% (catches ฿7,018 clone + ฿10,000 S26 Ultra)
- [x] Verified non-electronics search (แก้วน้ำ richell): model-number filter doesn't affect non-model-number queries; 37 clean results
- [ ] Shopee cookies (user action required)
- [ ] Facebook cookies + scraper (user action required)
- [ ] Add alembic migration failure handling in entrypoint (exit code propagation)
- [ ] Consider removing --reload flag in production docker-compose

## Known Issues on This Machine

- **DB empty on first boot**: Resolved — `alembic upgrade head` now runs automatically in api container entrypoint before uvicorn starts.
- **alembic.ini hardcodes DB URL**: `sqlalchemy.url` in `backend/alembic.ini` is a literal string (`finditem:changeme@postgres`), not read from `.env`. Pre-existing issue — override via `alembic/env.py` or env var to fix properly.
- **`--reload` in production**: api service uses `--reload` which is dev-only. Acceptable for now (dev project), but should be removed or overridden in a prod compose file.
- **nginx `/api/docs` returns 404**: Normal — FastAPI serves docs at `/docs` not `/api/docs`. Use `http://localhost:8000/docs` directly.
