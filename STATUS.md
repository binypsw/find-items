# Find Item — Current Status

_Last updated: 2026-05-10 — Shopee bot-detection diagnosis: Akamai Bot Manager redirects to verify/traffic/error (90309999); playwright-stealth navigator_user_agent fix merged; wait_until="commit" prevents timeout_
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
| Shopee | ❌ Akamai blocked | 0 | Akamai requires `_abck` cookie (JS challenge token) — not in stored cookies; tried Camoufox Firefox + curl_cffi; all fail 90309999; needs Scrapfly or `_abck` refresh cycle |
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
| Shopee scraper | ❌ Akamai `_abck` | All approaches tried: Browserless+stealth, Camoufox Firefox, curl_cffi+cookies — all get 90309999; root cause = `_abck` (Akamai JS challenge token) missing from cookies; Scrapfly solves this; OR user can seed fresh `_abck` + cookies for short-lived access |
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
- [ ] Shopee: Akamai `_abck` cookie is the hard blocker (JS challenge token, not in stored cookies); all free approaches exhausted (Browserless, Camoufox, curl_cffi); options: (1) Scrapfly $30/mo, (2) user manually seeds `_abck` for short-lived access, (3) skip Shopee
- [ ] Facebook cookies + scraper (user action required)
- [x] Add alembic migration failure handling in entrypoint — `backend/api/entrypoint.sh` ใช้ `set -e` + explicit exit 1; Dockerfile ใช้ ENTRYPOINT + CMD แยกกัน
- [x] Remove `--reload` flag in production — prod ใช้ `--workers 2` ผ่าน `docker-compose.prod.yml`; dev ยังคง `--reload` ใน `docker-compose.yml`
- [x] **Fix tier mismatch ใน DB**: lazada/shopee ใช้ `browserless` จริง แต่ DB บอก `managed_api` → แก้ทั้ง DB (SQL) และ `0001_initial.py` seed
- [x] **Fix ฟีดสด (LiveFeed)**: pubsub เพิ่ม global channel `finditem:runs:global`; frontend ส่ง `{"subscribe":"all"}`; backend `/ws/runs` รองรับ subscribe all → live feed ทำงานได้แล้ว
- [x] **Fix `last_success_at`**: อัปเดต `source.last_success_at` และ `health_status="healthy"` ใน scrape complete handler
- [x] **Fix `health_status`**: เพิ่ม `update_source_health` beat task รันทุกชั่วโมง — healthy (<24h), degraded (24-72h), down (>72h)

---

## Roadmap: Frontend Redesign + New Features

### UX Fixes

- [x] **[UX] Implement Sessions tab** — `SessionsPanel.tsx` สร้างแล้ว; App.tsx เพิ่ม "sessions" tab; แสดง AccountSession table + delete
- [x] **[UX] Score tooltip** — `title` + `cursor:help` บน score label และ bar: "Score = keyword relevance (50%) + price vs. market avg (30%) + condition match (20%)"
- [x] **[UX] Show parsed query in Results header** — parsed query chip เหนือ controls row: 🔍 keywords · condition · ≤฿price
- [x] **[UX] Persist filter + sort ข้าม tab switch** — App.tsx เปลี่ยนเป็น always-mounted + CSS `display:none`; filter/sort ไม่ reset
- [x] **[UX] Reference bar ทำให้เด่นชัด** — แสดงสำหรับทุก condFilter; label = "ราคามือ 1 เปรียบเทียบ:"
- [x] **[UX] Run button consolidate** — ลบ "Run Now" จาก ResultsDashboard; sidebar-only; refetchInterval:8000 auto-refresh
- [x] **[UX] Fix Live Feed autoscroll** — scroll ภายใน container; scroll เฉพาะเมื่อ user ห่างจากล่าง < 100px
- [x] **[UX] Error toasts** — SavedSearches: runError/deleteError + auto-clear 5s; SourcesPanel: toggleErrors map + auto-clear 4s
- [x] **[UX] Credit budget tooltip** — `title="1 credit = 1 API request per listing scraped"` + `cursor:help`
- [x] **[UX] Sidebar split: Searches vs Watchlist** — Watchlist section placeholder (Coming soon) รองรับ F4 Watchlist
- [ ] **[UX] Inline price sparkline บน card** — แทน toggle "Price Chart"; mini 7-day sparkline บน card โดยตรง; click ขยาย full chart

### F1: Smart Price Tracking & Drop Alerts

- [ ] **[BE] `price_alerts` model + migration** — fields: `listing_id`, `target_price`, `comparison` (lte/pct_drop), `notify_channels`, `is_active`, `triggered_at`
- [ ] **[BE] Alert evaluation ใน `poll_task.py`** — เช็ค active alerts หลัง upsert; fire notification ถ้า price ≤ target
- [ ] **[BE] API: `/api/alerts` CRUD** — create/list/delete price alerts
- [ ] **[FE] "Set Alert" button บน ProductCard** — modal ใส่ target price หรือ "แจ้งเมื่อลด X%"
- [ ] **[FE] Alerts management tab/panel** — active alerts, triggered history, delete
- [ ] **[FE] Notification settings** — Discord webhook URL, email — เก็บใน localStorage หรือ backend

### F2: Historical Price Transparency (กราฟจับโกหกโปรโมชัน)

- [ ] **[BE] Price stats endpoint** — `GET /api/listings/{id}/price-stats` → `{avg_30d, min_30d, max_30d, current, pct_vs_avg}`
- [ ] **[BE] Flash sale detection logic** — current < avg_30d×0.85 → "genuine_drop"; ราคาพึ่งเพิ่มแล้วลด → "fake_sale"
- [ ] **[FE] Full price history chart modal** — ย้ายออกจาก toggle; annotate min/max/avg; "ราคาปกติ ฿X" line
- [ ] **[FE] "Fake sale" warning badge** — ⚠ badge ถ้า detect fake_sale
- [ ] **[FE] Price trend indicator บน card** — "+12% จาก 30d avg" หรือ "-8% ต่ำสุด 90 วัน"

### F3: Review Aggregation & Seller Warning

- [ ] **[BE] Seller signal extraction** — normalize `rating`, `review_count`, `sold_count` จาก `seller_payload` JSONB
- [ ] **[BE] Seller warning classifier** — rating < 4.0, review_count < 10 + high price, seller_age < 30d → warn
- [ ] **[BE] `GET /api/listings/{id}/seller`** — normalized seller profile + warning flags
- [ ] **[FE] Review badge บน ProductCard** — "★4.2 (234)"; สีแดงถ้า rating < 4.0
- [ ] **[FE] Seller warning banner** — ⚠ banner ถ้ามี warning flags
- [ ] **[FE] Seller drill-down panel** — click seller name → side panel rating/reviews/history

### F4: Rare Item Sniper / Used Market Watch

- [ ] **[BE] `SavedSearch` watchlist mode** — เพิ่ม `search_type: "search"|"watch"` + `notify_on_new_listing: bool`
- [ ] **[BE] Watchlist beat task** — รันทุก 30 นาที; dispatch scrape เฉพาะ used sources (Kaidee, Facebook, Shopee)
- [ ] **[BE] New listing notification** — ถ้า INSERT (ไม่ใช่ update) + match watchlist → fire "new_listing_match"
- [ ] **[FE] Watchlist section ใน sidebar** — แยกจาก Search history; แสดง criteria + last match + badge new items
- [ ] **[FE] "Watch this" toggle บน search** — เปลี่ยน search → watchlist mode; ตั้ง max price + condition
- [ ] **[FE] New match highlight** — badge "NEW" บน card + timestamp ถ้า listing เพิ่งพบใน watchlist run

---

## New Sources (Scrapers to Build)

| Source | Priority | Approach | Blocker |
|--------|----------|----------|---------|
| **PowerBuy** (powerbuy.co.th) | 🔴 High | curl_cffi + JSON API | ไม่มี |
| **IT City** (itcity.co.th) | 🔴 High | curl_cffi + BeautifulSoup (คล้าย JIB) | ไม่มี |
| **Central Online** (central.co.th) | 🟠 Med | curl_cffi + JSON search API | ไม่มี |
| **Advice** (advice.co.th) | 🟠 Med | Scrapfly หรือ skip (Priceza ครอบบางส่วน) | Cloudflare |
| **AliExpress** | 🟠 Med | curl_cffi + API; แทน stub ที่มีอยู่ | Rate limiting |
| **OLX Thailand** (olx.co.th) | 🟡 Low | curl_cffi + REST API | ไม่มี |
| **Temu** (temu.com) | 🟡 Low | curl_cffi + JSON API + proxy | Geo-block |
| **Shopee** | ⏸ Blocked | Scrapfly $30/mo หรือ seed `_abck` | Akamai |
| **Facebook Marketplace** | ⏸ Blocked | ต้องการ FB session cookies | Auth |

- [ ] **[Scraper] PowerBuy** — เพิ่ม source + plugin; tier: direct
- [ ] **[Scraper] IT City** — เพิ่ม source + plugin; tier: direct
- [ ] **[Scraper] Central Online** — เพิ่ม source + plugin; tier: direct
- [ ] **[Scraper] OLX Thailand** — used items; tier: direct; useful สำหรับ F4 Sniper
- [ ] **[Scraper] Advice** — ประเมิน Scrapfly vs skip; tier: managed_api ถ้าใช้ Scrapfly
- [ ] **[Scraper] AliExpress** — แทน stub; tier: direct + rate limiting

---

## Known Issues on This Machine

- **DB empty on first boot**: Resolved — `alembic upgrade head` now runs automatically in api container entrypoint before uvicorn starts.
- **alembic.ini hardcodes DB URL**: `sqlalchemy.url` in `backend/alembic.ini` is a literal string (`finditem:changeme@postgres`), not read from `.env`. Pre-existing issue — override via `alembic/env.py` or env var to fix properly.
- **`--reload` in production**: api service uses `--reload` which is dev-only. Acceptable for now (dev project), but should be removed or overridden in a prod compose file.
- **nginx `/api/docs` returns 404**: Normal — FastAPI serves docs at `/docs` not `/api/docs`. Use `http://localhost:8000/docs` directly.
