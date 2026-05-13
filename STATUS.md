> **AI Assistant Directive:** Every time you complete a task from the 'Next Tasks' or 'Roadmap' sections, you MUST update this `STATUS.md` file to reflect the new state (move [ ] to [x], update counts, dates, etc.) before finishing your response.

# Find Item — Current Status

_Last updated: 2026-05-13 — Lazada migrated to direct Playwright headless (browser_headless tier); removed Browserless CDP dependency from Lazada_
_Tested with: DDR4 16GB + S24 Ultra มือสอง (11 clean results, no fakes) + แก้วน้ำ richell มือสอง (37 results, all legitimate cups)_

## Infrastructure

| Component | Status | Notes |
|---|---|---|
| Docker compose | ✅ All 6 containers up | postgres, redis, api, worker, beat, frontend |
| Browserless | ✅ Removed | ลบออกจาก docker-compose + codebase แล้ว; shopee ใช้ Camoufox โดยตรง |
| DB migrations | ✅ Auto-run on startup | `alembic upgrade head` runs before uvicorn in api entrypoint |
| nginx proxy (3001) | ✅ Working | `/api/*` routes proxy correctly |
| API docs (direct) | ✅ Working | http://localhost:8000/docs (port 8000 exposed to host) |
| Frontend | ✅ Working | http://localhost:3001 returns 200 |

## Sources

| Source | Status | Items (DDR4 16GB) | Notes |
|---|---|---|---|
| JIB | ✅ Working | 41 | curl_cffi + BeautifulSoup, fast (~8s) |
| BNN | ✅ Working | ~18 | curl_cffi + English keywords |
| Priceza | ✅ Working | 23 | curl_cffi aggregator, fast (~2s) |
| Lazada | ✅ Working | 29 | Direct Playwright headless (`browser_headless`) + AJAX intercept |
| Kaidee | ✅ Working | 0 | Browserless Next.js SSR — pending migration; 0 = real data gap not bug |
| Shopee | ⚠️ Needs cookies | 0 | รัน `python tools/capture_shopee_session.py` บน Windows host เพื่อ capture session cookies ก่อน |
| Advice | ⏸ Skipped | 0 | Cloudflare block; Priceza ครอบคลุมแล้ว; disabled in DB |
| AliExpress | ❌ Disabled | 0 | Stub only; disabled in DB |
| Facebook | ⏸ Disabled in DB | — | Plugin ready (`browser_headless`, SSR no-login, 24 items) — enable ด้วย SQL ข้างบน |

## Features

| Feature | Status | Notes |
|---|---|---|
| Query parser (Gemini→Typhoon→Regex) | ✅ Working | Regex fallback confirmed |
| Redis cache for query parser | ✅ Working | Celery + Redis both healthy |
| JIB / Priceza / Lazada scrapers | ✅ Working | Confirmed with live scrape run |
| Kaidee scraper | ✅ Working | Returns 0 = real data gap, not a bug |
| Dashboard API (`/api/dashboard/{id}/top`) | ✅ Working | Returns up to 200 ranked listings; uses latest run per source only |
| Celery worker + pubsub events | ✅ Working | item_found events published correctly |
| Dashboard UI (sort, filter, auto-refresh, Run Now) | ✅ Working | Verified with S24 Ultra search |
| New-vs-used comparison bar | ✅ Working | Accessory exclusion filter active |
| Product clustering (sentence-transformers) | ✅ Done | products table populated (16 products) |
| Ranking (condition preference, percentile price norm) | ✅ Working | Dashboard returns ordered results |
| Price history charts | ❌ Not implemented | |
| Discord notifications | ❌ Not implemented | |
| Shopee scraper | ❌ Akamai blocked | Strategy: `browser_headed` ให้ user แก้ challenge เอง (no paid APIs) |
| Facebook scraper | ❌ Blocked | Strategy: `browser_headed` + persistent context สำหรับ session cookies |

## Data State

| Table | Count | Notes |
|---|---|---|
| listings | 104 | After 1 scrape run (JIB=41, Lazada=40, Priceza=23) |
| products | 16 | Clustered via `recluster_orphan_products` |
| searches | 1 | DDR4 16GB test search |
| scrape_runs | 7 | 1 run × 7 sources |

## Next Tasks

- [x] สร้าง .env บนเครื่องนี้ และ verify docker compose up ทำงานได้
- [x] Verify all sources ด้วย scrape run จริง แล้วอัพ status table นี้
- [x] **รัน `alembic upgrade head` เป็น startup step**
- [x] **Disable Shopee, AliExpress, Advice ใน DB**
- [x] รัน product clustering
- [x] Verify agent memory is loaded correctly in coder agent session
- [x] Fix Lazada relevance filter
- [x] Fix dashboard API stale run bug
- [x] Fix reference bar accessory contamination
- [x] Fix JIB relevance filter
- [x] Fix frontend: filter accessories from main results display; price floor for used results
- [x] Switch coder/code-reviewer/scraper-research agent model
- [x] Fix clone/fake phone detection
- [x] Verified non-electronics search (แก้วน้ำ richell)
- [x] Add alembic migration failure handling in entrypoint
- [x] Remove `--reload` flag in production
- [x] Fix tier mismatch ใน DB
- [x] Fix ฟีดสด (LiveFeed)
- [x] Fix `last_success_at`
- [x] Fix `health_status`
- [x] Arch shift: private home server, No Paid APIs, browser_headed strategy — updated CLAUDE.md + STATUS.md
- [x] **[Arch] Migrate Lazada scraper**: Browserless CDP → direct Playwright headless (`browser_headless` tier)
- [x] **[Arch] Migrate Kaidee scraper**: Already uses curl_cffi (AsyncSession) directly — no Browserless, tier="direct" ✅
- [x] **[Arch] Remove Browserless container** — docker-compose.yml, manager.py, base.py, config.py, browserless_client.py; migration 0002 updates tier in DB
- [x] **[Shopee] Implement `browser_headed`** — `tools/capture_shopee_session.py` เปิด Chromium headed บน Windows host, user แก้ Akamai challenge, cookies saved via `/api/sessions`
- [x] **[Facebook] Implement scraper** — `facebook.py` scrapes Bangkok SSR Relay JSON (no login, 24 listings/search); enable via DB: `INSERT INTO sources (id, display_name, enabled, tier) VALUES ('facebook', 'Facebook Marketplace', true, 'browser_headless') ON CONFLICT (id) DO UPDATE SET enabled=true`

---

## Roadmap: Frontend Redesign + New Features

### UX Fixes

- [x] **[UX] Implement Sessions tab**
- [x] **[UX] Score tooltip**
- [x] **[UX] Show parsed query in Results header**
- [x] **[UX] Persist filter + sort ข้าม tab switch**
- [x] **[UX] Reference bar ทำให้เด่นชัด**
- [x] **[UX] Run button consolidate**
- [x] **[UX] Fix Live Feed autoscroll**
- [x] **[UX] Error toasts**
- [x] **[UX] Credit budget tooltip**
- [x] **[UX] Sidebar split: Searches vs Watchlist**
- [ ] **[UX] Inline price sparkline บน card**

### F1: Smart Price Tracking & Drop Alerts

- [ ] **[BE] `price_alerts` model + migration** — fields: `listing_id`, `target_price`, `comparison` (lte/pct_drop), `notify_channels`, `is_active`, `triggered_at`
- [ ] **[BE] Alert evaluation ใน `poll_task.py`**
- [ ] **[BE] API: `/api/alerts` CRUD**
- [ ] **[FE] "Set Alert" button บน ProductCard**
- [ ] **[FE] Alerts management tab/panel**
- [ ] **[FE] Notification settings** — Discord webhook URL, email

### F2: Historical Price Transparency (กราฟจับโกหกโปรโมชัน)

- [ ] **[BE] Price stats endpoint** — `GET /api/listings/{id}/price-stats`
- [ ] **[BE] Flash sale detection logic**
- [ ] **[FE] Full price history chart modal**
- [ ] **[FE] "Fake sale" warning badge**
- [ ] **[FE] Price trend indicator บน card**

### F3: Review Aggregation & Seller Warning

- [ ] **[BE] Seller signal extraction**
- [ ] **[BE] Seller warning classifier**
- [ ] **[BE] `GET /api/listings/{id}/seller`**
- [ ] **[FE] Review badge บน ProductCard**
- [ ] **[FE] Seller warning banner**
- [ ] **[FE] Seller drill-down panel**

### F4: Rare Item Sniper / Used Market Watch

- [ ] **[BE] `SavedSearch` watchlist mode**
- [ ] **[BE] Watchlist beat task** — รันทุก 30 นาที; dispatch scrape เฉพาะ used sources
- [ ] **[BE] New listing notification**
- [ ] **[FE] Watchlist section ใน sidebar**
- [ ] **[FE] "Watch this" toggle บน search**
- [ ] **[FE] New match highlight**

---

## New Sources (Scrapers to Build)

| Source | Priority | Approach | Blocker |
|--------|----------|----------|---------|
| **PowerBuy** (powerbuy.co.th) | 🔴 High | `direct` curl_cffi + JSON API | ไม่มี |
| **IT City** (itcity.co.th) | 🔴 High | `direct` curl_cffi + BeautifulSoup | ไม่มี |
| **Central Online** (central.co.th) | 🟠 Med | `direct` curl_cffi + JSON API | ไม่มี |
| **Advice** (advice.co.th) | 🟠 Med | Skip — Priceza ครอบคลุมแล้ว | Cloudflare |
| **AliExpress** | 🟠 Med | `direct` curl_cffi + API | Rate limiting |
| **OLX Thailand** (olx.co.th) | 🟡 Low | `direct` curl_cffi + REST API | ไม่มี |
| **Temu** (temu.com) | 🟡 Low | `direct` curl_cffi + JSON API | Geo-block |
| **Shopee** | ⏳ Planned | `browser_headed` — user แก้ Akamai challenge เอง | Akamai |
| **Facebook Marketplace** | ⏳ Planned | `browser_headed` + persistent context — user login ครั้งเดียว | Auth |

- [ ] **[Scraper] PowerBuy** — เพิ่ม source + plugin; tier: direct
- [ ] **[Scraper] IT City** — เพิ่ม source + plugin; tier: direct
- [ ] **[Scraper] Central Online** — เพิ่ม source + plugin; tier: direct
- [ ] **[Scraper] OLX Thailand** — used items; tier: direct
- [ ] **[Scraper] AliExpress** — แทน stub; tier: direct + rate limiting

---

## Known Issues on This Machine

- **DB empty on first boot**: Resolved — `alembic upgrade head` runs automatically in api entrypoint.
- **alembic.ini hardcodes DB URL**: `sqlalchemy.url` is a literal string — override via `alembic/env.py` or env var to fix properly.
- **`--reload` in dev**: api service uses `--reload` — acceptable for home server dev use.
- **nginx `/api/docs` returns 404**: Normal — use `http://localhost:8000/docs` directly.
