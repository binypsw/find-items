> ⚠️ HISTORICAL DOCUMENT — Initial design only.
> Reality has diverged. Do not use as reference.
> See STATUS.md for current state.

---

# Find-Item: Thai E-Commerce Multi-Source Scraper (v2 — Production-Ready)

## Context

ผู้ใช้ต้องการ app ดึงข้อมูลสินค้าจากหลายแหล่งตลาดไทย (Shopee, Lazada, Facebook Marketplace, AliExpress, Kaidee ฯลฯ) เน้น IT มือสอง + สินค้าทั่วไป มีระบบ schedule, price history, top-10 ranked dashboard, Discord + in-app notifications, AI parse natural language query (free LLMs only), UI 2 ภาษา (ไทย/อังกฤษ)

**Deployment:**
- **Production**: Linux server
- **Development**: Docker Desktop บน Windows 11
- **Constraint**: ต้องไม่ใช้ home IP ยิง Shopee/Lazada/FB ตรงๆ เพราะติด anti-bot (Akamai, Cloudflare, Datadome) ภายในไม่กี่ชั่วโมง

**v2 review เพิ่ม 8 จุดสำคัญ:**
1. Anti-bot: web scraping APIs + proxy rotation + retry
2. Worker แยกจาก API (Celery + Redis)
3. browserless/chrome เป็น service แยก
4. pgvector + embeddings สำหรับ deduplication
5. account_sessions table สำหรับ FB cookies
6. Data retention + listing status lifecycle
7. Image handling + currency conversion
8. Observability (logs, metrics, cost tracking)

---

## Tech Stack (Updated)

| Layer | Choice | Notes |
|---|---|---|
| API | **FastAPI** + Python 3.11 | API + WebSocket only — ไม่รัน scraper |
| Task Queue | **Celery 5.x** + **Redis 7** | แยก worker process; Redis ใช้ทั้ง broker + pub/sub สำหรับ live updates |
| Scraper Worker | Python 3.11 (Celery worker) | container แยกจาก API |
| Browser | **browserless/chrome** (Docker image) | Playwright connect ผ่าน WebSocket CDP |
| Scraping APIs (managed) | **ZenRows** หรือ **ScrapingBee** | ใช้กับเว็บ anti-bot สูง: Shopee, Lazada, FB |
| HTTP | **curl_cffi** (Chrome TLS impersonation) + **tenacity** | bypass JA3/JA4 fingerprint detection (Cloudflare/Akamai); async API; retry on 403/429/timeout |
| Proxy | **proxy_manager** layer | ใช้กับ self-hosted scraping (Kaidee, AliExpress) |
| DB | **PostgreSQL 16** + **pgvector** + SQLAlchemy 2 + Alembic | semantic dedup + time-series |
| Embeddings | **sentence-transformers** (`paraphrase-multilingual-MiniLM-L12-v2`) | local, รองรับไทย, ฟรี |
| NL Parsing | **Multi-tier (100% free)**: Gemini 2.0 Flash (primary) → Typhoon v2 (fallback, Thai-tuned) → regex (deterministic) | provider abstraction; ที่ scale 200-300 parses/เดือน free tier เหลือเฟือ |
| Image Storage | **MinIO** (S3-compatible) หรือ store URLs only | optional - phase 4 |
| Frontend | **React + Vite + TypeScript** + nginx | served as static |
| State | **TanStack Query** + **Zustand** | |
| Charts | **Recharts** | price history |
| i18n | **react-i18next** | th.json + en.json |
| Notifications | **Discord Webhooks** + WebSocket toast | |
| Observability | **structlog** (JSON logs) + Prometheus metrics endpoint + **OpenTelemetry SDK** (correlation ID FastAPI→Celery) | trace backend: Jaeger (dev) / SigNoz (prod) — minimal, single container |
| Time zone | `Asia/Bangkok` ทุก datetime ใน scheduler | |

**Dev/Prod parity:** ทุก service เป็น Docker image — Windows Docker Desktop รัน image เดียวกับ Linux production. Bind-mount source code with `:cached` flag for performance, use `.gitattributes` (`* text=auto eol=lf`) ให้ line endings ตรงกัน

---

## Docker Compose Services (Final)

```yaml
services:
  postgres:        # postgres:16 + pgvector extension
  redis:           # redis:7-alpine — Celery broker + pubsub
  browserless:     # browserless/chrome — remote Playwright
  api:             # FastAPI + WebSocket (ไม่มี Playwright/Chromium)
  worker:          # Celery worker — รัน scraper plugins
  beat:            # Celery beat — schedule trigger (แทน APScheduler)
  frontend:        # nginx serve React build + proxy /api → api
  minio:           # (optional, phase 4) S3-compatible image storage
```

**ทำไมเปลี่ยนจาก APScheduler → Celery beat:**
- Worker container แยก → ต้องมี broker ส่งงานข้าม process อยู่แล้ว
- Celery beat รัน schedule แล้วโยน task เข้า Redis queue → worker หยิบไปทำ
- API container เบาลงมาก ไม่มี playwright/chromium

**ทำไม browserless:**
- Memory leak isolation — restart browserless service ก็ได้โดยไม่กระทบ worker
- Worker container ไม่ต้อง install chromium → image เล็กลง
- รองรับหลาย Playwright client ต่อเข้ามาพร้อมกัน
- Free tier ของ browserless image รองรับ 10 concurrent sessions

---

## Anti-Bot Strategy (Hybrid 3-Tier)

แต่ละ plugin เลือก tier ได้ผ่าน config (`SCRAPING_MODE` env var):

### Tier 1 — Direct API Interception (เร็ว/ฟรี)
- ใช้กับ source ที่ anti-bot อ่อน: Kaidee, JIB, Advice, Priceza
- **`curl_cffi.requests.AsyncSession(impersonate="chrome131")`** — TLS/JA3 fingerprint = Chrome จริง, bypass Cloudflare basic + Akamai
  - **ห้ามใช้ httpx ตรงๆ** — Python stdlib ssl เปิด JA3 = "Python/Requests" → ติด bot-score ทันที
  - หาก source ไม่มี Cloudflare ก็ยังใช้ curl_cffi (overhead ~0) เพื่อ consistency
- rotating user agents + tenacity retry (jitter + exponential backoff)
- ผ่าน proxy_manager (residential proxy pool) ถ้ามี
- **คาดหวัง**: success rate Tier 1 ขยับจาก ~50% (httpx) → ~85% (curl_cffi) → ลดงานที่ต้อง escalate ไป Tier 3 ตรงๆ = ประหยัด credit

```python
# backend/shared/scraper/http_client.py
from curl_cffi.requests import AsyncSession

async def fetch(url: str, *, headers: dict | None = None, timeout: int = 20) -> str:
    async with AsyncSession(impersonate="chrome131") as s:
        r = await s.get(url, headers=headers or {}, timeout=timeout)
        r.raise_for_status()
        return r.text
```

### Tier 2 — browserless + Playwright (กลาง)
- ใช้กับ AliExpress, Pantip, Line Shopping
- playwright-stealth + cookie persistence
- Connect ผ่าน `ws://browserless:3000` แทน launch local

### Tier 3 — Managed Scraping API (ปลอดภัย/มี cost) — **CREDIT-OPTIMIZED**
- ใช้กับ **Shopee, Lazada, Facebook Marketplace** (anti-bot ดุ)
- **Provider candidates** (Phase 3 benchmark ทั้ง 3):
  - **Scrapfly** — 200k starter @ $30, 1M Pro @ $100, ASP auto-tiering, geo-Thailand
  - **ZenRows** — 250k starter @ $69, well-known FB success
  - **Apify** — Actor marketplace, จ่ายตาม compute unit; free $5/เดือน; เหมาะกับ FB เพราะ prebuilt actors
  - **ScrapingBee ตัด** — stealth proxy 75 credits/req แพงเกินไป
- Phase 3 trial: 100 requests × 3 sites × 3 providers → log success rate + cost per success → เลือก primary ต่อ source (อาจไม่ใช่ตัวเดียวกัน)
- **Provider abstraction layer** — plugin เลือก provider ผ่าน config ได้ ไม่ผูกตัวเดียว

#### ทำไม Official APIs ใช้ไม่ได้กับ use case นี้
- **Lazada Affiliate API**: สำหรับ affiliate marketers, ขอเพื่อ price tracker = reject; **ไม่มีของมือสอง** (เฉพาะ Lazada Mall + registered shops)
- **Shopee Open Platform**: สำหรับ sellers / ERP partners, ค้น listings ทั้งหมดไม่ได้, **ไม่มี API mode มือสอง**
- **Facebook Marketplace**: **ไม่มี public API** ตั้งแต่ Meta block ปี 2018
- → **scraping เป็นทางเดียว** สำหรับ buyer-side aggregation ของของมือสอง

#### Credit Economics — Mandatory Optimizations
**Naive math:** 5 searches × 3 sites × 12 runs/day × 50 detail requests × 25 credits = 6.75M credits/month ❌

**Realistic budget target:** < 200k credits/เดือน (= Scrapfly starter)

#### กลยุทธ์ลด credit (ต้องทำทุกข้อ)

1. **Search-driven, NOT listing-driven**:
   - ดึงเฉพาะ search/list pages — ราคามาในผลลัพธ์อยู่แล้ว
   - **ดึง detail pages เฉพาะตอน first-seen** หรือเมื่อ list บอกว่าราคาเปลี่ยน
   - ลด req per session จาก ~50 → 1-3

2. **Adaptive Credit Tiering (Lazy Premium)**:
   ```python
   async def adaptive_fetch(url):
       # Try basic first (1 credit)
       r = await api.get(url, render_js=False, premium_proxy=False)
       if is_blocked_or_invalid(r):
           # Upgrade JS render (5 credits)
           r = await api.get(url, render_js=True)
           if is_blocked_or_invalid(r):
               # Full premium (~25 credits)
               r = await api.get(url, render_js=True, premium_proxy=True, asp=True)
       return r
   ```
   Expected: 60-70% pass at basic, 20% at JS, 10% premium → avg **4-6 credits/req** (vs 25)

3. **Adaptive Polling Frequency** per listing:
   | Listing state | Poll interval | Field on listings table |
   |---|---|---|
   | New (< 24h, price moved) | ทุก 4-6 ชม. | `next_poll_at` |
   | Active (1-7d) | ทุก 12 ชม. | |
   | Stable (>7d, no price change) | วันละครั้ง | |
   | Cold (>30d static) | สัปดาห์ละครั้ง | |
   | Stale (missing 3 runs) | หยุด poll | status=`stale` |

   เพิ่ม `next_poll_at` + `poll_priority` columns ใน `listings` table — beat task ดึงเฉพาะ listings ถึงเวลา

4. **Hash & Skip**: hash response payload → ถ้าเหมือนรอบก่อน skip processing (insert price_snapshot อย่างเดียว)

5. **Free-tier sites ทำงานหนัก**: Kaidee + JIB + Advice + Priceza = 0 credits, ดึงข้อมูลได้ 60-70% ของ catalog

6. **AliExpress Open API** (ถ้า approval ได้) = ฟรี
   - **Lazada / Shopee / FB official APIs ใช้ไม่ได้** (ไม่ครอบคลุม listings มือสอง — ดู section บน)

7. **FB Marketplace = ใช้น้อยที่สุด**:
   - Schedule แค่ **2-3 ครั้ง/วัน** ต่อ search (เทียบกับ Shopee 4-6 ครั้ง)
   - Disable by default ใน new search — user opt-in เป็น checkbox

#### Updated Realistic Math
- 10 active searches × 3 anti-bot sites × **4 runs/วัน** × **1-2 list requests** × **5 credits avg**
- = **600-1,200 credits/วัน = 18k-36k credits/เดือน**
- Worst case (20 searches, sale season): **~170k/เดือน** — ยังพอกับ Scrapfly starter ($30)

#### Cost-aware Tracking (Required)
- เก็บ `credits_used` per request → log ลง `scrape_runs.api_credits_used`
- Daily budget per source (configurable ใน sources table)
- Alert (Discord) ที่ 70%, 90%, 100% ของ monthly budget
- Auto-pause anti-bot scraping เมื่อหมด budget — Kaidee/Priceza ยังทำต่อได้

**Plugin config schema:**
```python
class ScraperConfig:
    tier: Literal["direct", "browserless", "managed_api"]
    rate_limit: float  # requests per second
    use_proxy: bool
    api_provider: Optional[str]  # "zenrows" | "scrapingbee"
    retry_max_attempts: int = 5
```

### Retry / Backoff (tenacity)
```python
@retry(
    retry=retry_if_exception_type((HTTPStatusError, TimeoutError)),
    wait=wait_exponential_jitter(initial=2, max=60),
    stop=stop_after_attempt(5),
    before_sleep=log_retry,
)
```
- 403/429/503 → retry with jitter
- Permanent 404/410 → ไม่ retry, mark listing as `deleted`

---

## Updated Project Structure

```
find-item/
├── backend/
│   ├── api/                          # FastAPI service (light)
│   │   ├── main.py
│   │   ├── routes/
│   │   │   ├── searches.py
│   │   │   ├── products.py
│   │   │   ├── dashboard.py
│   │   │   ├── sources.py
│   │   │   ├── sessions.py           # CRUD account_sessions (FB cookies)
│   │   │   └── websocket.py          # subscribe Redis pubsub → push to client
│   │   └── Dockerfile
│   ├── worker/                       # Celery worker service (heavy)
│   │   ├── celery_app.py
│   │   ├── tasks/
│   │   │   ├── scrape_task.py        # main scrape entrypoint
│   │   │   ├── retention_task.py     # cleanup old snapshots
│   │   │   ├── session_health_task.py # check FB cookies
│   │   │   └── notification_task.py  # Discord push
│   │   ├── beat_schedule.py          # Celery beat cron config
│   │   └── Dockerfile                # includes Playwright client (no browser)
│   ├── shared/                       # ใช้ทั้ง api และ worker
│   │   ├── config.py                 # Pydantic Settings
│   │   ├── database.py
│   │   ├── models/
│   │   │   ├── source.py
│   │   │   ├── search.py
│   │   │   ├── product.py            # + embedding: Vector(384)
│   │   │   ├── listing.py            # + status, last_seen_at, currency
│   │   │   ├── price_snapshot.py
│   │   │   ├── scrape_run.py         # + scraping_api_credits_used
│   │   │   ├── account_session.py    # ★ NEW
│   │   │   └── notification.py
│   │   ├── schemas/
│   │   ├── core/
│   │   │   ├── proxy_manager.py      # ★ NEW — rotate proxies
│   │   │   ├── browserless_client.py # connect to browserless
│   │   │   ├── scraping_api/
│   │   │   │   ├── zenrows.py
│   │   │   │   └── scrapingbee.py
│   │   │   ├── retry.py              # tenacity decorators
│   │   │   ├── cookie_store.py       # load/save session cookies
│   │   │   ├── currency.py           # USD→THB conversion
│   │   │   ├── embeddings.py         # sentence-transformers wrapper
│   │   │   └── pubsub.py             # Redis pub/sub helpers
│   │   ├── scraper/
│   │   │   ├── base.py               # AbstractScraper
│   │   │   ├── manager.py
│   │   │   ├── deduplicator.py       # pgvector cosine similarity
│   │   │   ├── query_parser.py       # Multi-tier LLM (Gemini → Typhoon → regex)
│   │   │   └── plugins/
│   │   │       ├── shopee.py         # tier=managed_api
│   │   │       ├── lazada.py         # tier=managed_api
│   │   │       ├── facebook.py       # tier=managed_api + cookies
│   │   │       ├── aliexpress.py     # tier=browserless
│   │   │       ├── kaidee.py         # tier=direct
│   │   │       ├── priceza.py        # tier=direct (price anchor)
│   │   │       ├── jib.py            # tier=direct (price anchor)
│   │   │       └── advice.py         # tier=direct (price anchor)
│   │   └── services/
│   │       ├── ranking.py
│   │       ├── price_history.py
│   │       ├── reference_product.py  # ★ ตอน user paste URL
│   │       └── notifications.py
│   ├── alembic/
│   ├── tests/
│   │   ├── plugins/                  # VCR cassettes ของ HTTP responses
│   │   └── conftest.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── SearchBar/            # NL / keyword / URL input
│   │   │   ├── ResultsDashboard/
│   │   │   ├── ProductCard/
│   │   │   ├── PriceHistoryChart/
│   │   │   ├── ScheduleManager/
│   │   │   ├── SessionManager/       # ★ จัดการ FB cookies upload
│   │   │   ├── SourceHealth/         # แสดง status ของแต่ละ source
│   │   │   └── RunStatus/
│   │   ├── hooks/
│   │   ├── i18n/{th,en}.json
│   │   └── api/client.ts
│   ├── nginx.conf
│   └── Dockerfile
├── docker-compose.yml                # dev (Windows 11 + Docker Desktop)
├── docker-compose.prod.yml           # prod (Linux) overlay
├── .env.example
├── .gitattributes                    # eol=lf for cross-platform
└── .gitignore
```

---

## Database Schema (Updated)

```sql
sources(id, name, base_url, tier, enabled, health_status, last_success_at,
        monthly_credit_budget INT,                                   -- ★ per-source quota
        credits_used_this_month INT DEFAULT 0,                       -- ★ reset monthly
        api_provider VARCHAR(32))                                    -- ★ scrapfly | zenrows | none

saved_searches(id, name, raw_query, parsed_query_jsonb, schedule_cron,
               max_price, min_price, condition, location, source_filter,
               last_run_at, owner_id, is_active)

products(id, canonical_title, category, embedding VECTOR(384),
         first_seen_at, dedup_group_id)
        -- pgvector index: ivfflat (embedding vector_cosine_ops)

listings(id, product_id, source_id, external_id, url, title, description,
         current_price, currency, condition, seller_id, seller_rating,
         seller_review_count, location, image_urls JSONB, raw_payload JSONB,
         status ENUM('active','sold','deleted','stale','error'),    -- ★
         first_seen_at, last_seen_at,                                -- ★
         consecutive_missing_count INT DEFAULT 0,                    -- ★ mark stale ถ้าหายไปหลายรอบ
         next_poll_at TIMESTAMPTZ,                                   -- ★ adaptive polling — beat picks ที่ถึงเวลา
         poll_interval_minutes INT,                                  -- ★ ปรับตาม listing activity
         last_payload_hash VARCHAR(64),                              -- ★ hash & skip — เหมือนเดิมไม่ process ซ้ำ
         price_change_count INT DEFAULT 0)                           -- ★ ใช้ปรับ poll_interval

price_snapshots(id, listing_id, price_thb, price_original, currency,
                fx_rate, scraped_at, scrape_run_id)
                -- partition by month, drop old partitions automatically
                -- index: (listing_id, scraped_at DESC)

scrape_runs(id, search_id, source_id, started_at, finished_at, status,
            items_found, items_new, items_updated, errors JSONB,
            api_credits_used)                                        -- ★

account_sessions(id, source_id, label, cookies JSONB, expires_at,
                 status ENUM('active','expired','banned','needs_refresh'),
                 last_used_at, last_health_check_at)                 -- ★ NEW

notifications(id, type, payload JSONB, channels TEXT[],
              sent_at, error)
```

### Listing Status Lifecycle
- New listing scraped → `active`
- Scraped but seen `consecutive_missing_count >= 3` → `stale` (ลบจาก ranking)
- HTTP 404/410 ที่ URL → `deleted`
- Mark `sold` ถ้า site บอกว่า sold out (Shopee มี field "sold")
- Job retention: ลบ listing `stale`/`deleted` > 90 วัน

### Data Retention Policy
- `price_snapshots` < 30 วัน: เก็บทุก snapshot (รายชั่วโมง)
- `price_snapshots` 30-90 วัน: downsample เหลือวันละ 1 record (เลือก min/max/last ของวัน)
- `price_snapshots` > 90 วัน: เหลือสัปดาห์ละ 1 record
- > 365 วัน: hard delete
- รัน via Celery beat cron daily 03:00 Asia/Bangkok
- ใช้ partitioning ของ Postgres (monthly partitions) เพื่อ DROP PARTITION เร็ว

---

## Cross-Platform Deduplication (pgvector)

**ปัญหา:** Title ต่าง source ไม่เหมือนกัน
- Kaidee: "ขายด่วน การ์ดจอ 1080 สภาพดี"
- Facebook: "VGA Zotac GTX 1080 8GB มือ 2"
- Shopee: "GTX 1080 มือสอง รับประกัน 7 วัน"

**⚠️ Vector-only dedup ไม่พอสำหรับสินค้า IT** — embedding model จับ semantic ดี แต่ token discriminator (Ti, Super, X3D, capacity) ทำให้ false positive สูง:
| Title A | Title B | cosine | จริงๆ |
|---|---|---|---|
| RTX 4070 12GB | RTX 4070 Ti 12GB | ~0.93 | คนละรุ่น |
| Ryzen 5 5600 | Ryzen 5 5600X | ~0.95 | คนละ SKU |
| DDR4 3200 16GB | DDR4 3600 16GB | ~0.94 | คนละ speed |

**Solution flow (3-stage hybrid):**
1. ทุกครั้งที่ insert listing ใหม่:
   - คำนวณ embedding ของ `title + key_specs` ด้วย `paraphrase-multilingual-MiniLM-L12-v2` (384-dim)
   - Extract `spec_tokens` ด้วย regex (Ti/Super/XT/XTX/X3D/KF/F/LE/OC, capacity 8GB/12GB/1TB, mem gen DDR4/DDR5, speed 3200MHz, PCIe gen)
2. **Stage 1 — Spec gate (เร็วสุด, GIN index)**: filter candidate ที่ `spec_tokens && new.spec_tokens` (overlap)
3. **Stage 2 — Vector gate**: ใน candidate set, query pgvector หา cosine > 0.85
4. **Stage 3 — Spec equality + price sanity**: spec_tokens ต้อง **เท่ากันเป๊ะ** + ราคาต่างไม่เกิน 50%
5. ถ้าผ่านทั้ง 3 stage → join เป็น product เดียวกัน; ไม่ผ่าน → สร้าง product ใหม่
6. Background task: re-cluster ทุกสัปดาห์ (ดึง orphan products มาลอง match ใหม่)

```python
# backend/shared/scraper/deduplicator.py
import re

IT_DISCRIMINATORS = re.compile(
    r"\b(ti|super|xt|xtx|x3d|kf|f|le|oc|"
    r"\d+gb|\d+tb|"
    r"ddr[3-5]|"
    r"\d{3,4}mhz|"
    r"pcie\s?[3-5])\b",
    re.I,
)

def extract_spec_tokens(title: str) -> list[str]:
    return sorted({m.group(0).lower() for m in IT_DISCRIMINATORS.finditer(title)})

def is_duplicate(a: Listing, b: Listing) -> bool:
    if set(a.spec_tokens) != set(b.spec_tokens):     # Stage 3: must match exactly
        return False
    if cosine(a.embedding, b.embedding) < 0.85:      # Stage 2: vector
        return False
    if abs(float(a.current_price_thb) - float(b.current_price_thb)) \
       / min(float(a.current_price_thb), float(b.current_price_thb)) > 0.5:
        return False
    return True
```

```sql
-- Schema additions
ALTER TABLE listings ADD COLUMN spec_tokens TEXT[] DEFAULT '{}';
CREATE INDEX listings_spec_gin ON listings USING GIN (spec_tokens);

-- pgvector index บน products.embedding
CREATE INDEX listings_product_dedup ON products
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

**ทำไมไม่ใช้ paid API ทำ embedding:**
- sentence-transformers รัน local ฟรี + เร็ว (~50ms ต่อ batch 32)
- ไม่ต้องเสีย API cost
- multilingual model รองรับไทย+อังกฤษผสมในประโยคเดียว

---

## Reference Product Flow (Paste URL + Criteria)

เมื่อ user paste Shopee link + พิมพ์ "มือสอง รับในกรุงเทพ":

1. Detect URL → route ไป `extract_from_url()` ของ plugin ที่ตรง domain
2. Scrape สินค้าต้นทาง → ได้ `RawListing` (title, specs, image, price)
3. Service `reference_product.py`:
   - ใช้ LLM (Gemini/Typhoon) ดึง **canonical product attributes** (brand, model, specs)
   - Combine กับ user criteria → สร้าง `StructuredQuery`
4. Search ทุก source อื่นด้วย query นั้น
5. Reference listing แสดงเป็น "ราคาอ้างอิง" บน dashboard เพื่อเทียบ

---

## Account Session Management (Facebook etc.)

### Bootstrap Flow
1. User กด "เพิ่ม Facebook account" บน UI → SessionManager component
2. Login manually บน browser ส่วนตัว → export cookies (extension เช่น "EditThisCookie") → JSON
3. Upload JSON → API `/sessions` → เก็บใน `account_sessions` table (encrypted at rest with Fernet)
4. Worker ก่อนจะ scrape FB → load cookies → inject ใน Playwright context

### Health Check (Celery beat)
- ทุก 6 ชม. รัน `session_health_task`:
  - Test request ไป FB เปล่าๆ
  - ถ้า redirect → login → mark `expired` + Discord alert "Cookie หมดอายุ กรุณา re-login"
  - ถ้าเจอ checkpoint/captcha → mark `banned`
- มี multi-account rotation: ถ้ามี active session > 1 → round-robin

### Cookie Storage Security
- Encrypt cookies field with Fernet (key ใน env var `FERNET_KEY`)
- ไม่ log cookies ใน structlog (ใส่ใน redact list)

---

## Updated Implementation Phases

### Phase 1 — Infrastructure Foundation
- Docker Compose: postgres (with pgvector), redis, api skeleton, worker skeleton, browserless, frontend scaffold
- Alembic migrations: ทุก table รวม account_sessions
- shared/core: proxy_manager, browserless_client, retry decorators
- AbstractScraper interface + plugin registry
- Health check endpoints ทุก service

### Phase 2 — First Plugin End-to-End
- Kaidee plugin (tier=direct, ง่ายสุด, ไม่มี anti-bot จัดเต็ม)
- Celery task `scrape_task` + `beat` schedule
- Manual run via API → Celery → Kaidee → DB
- Redis pubsub → WebSocket → frontend live progress
- Simple results table UI

### Phase 3 — Anti-Bot Plugins (Credit-Optimized)
- **Provider benchmark**: ยิง 100 requests ทดลอง **Scrapfly + ZenRows + Apify** กับ Shopee/Lazada/FB → log success rate + cost per success → เลือก primary **ต่อ source** (อาจต่างกันตาม site)
- Scrapfly + ZenRows + Apify clients + **provider abstraction layer** (ไม่ผูกตัวเดียว)
- **Adaptive tiering wrapper** — basic → JS render → premium upgrade ladder (เฉพาะ Scrapfly/ZenRows; Apify จ่ายตาม actor run)
- Shopee/Lazada plugin (tier=managed_api, ใช้ provider ที่ benchmark ดีสุด)
- FB Marketplace อาจเริ่มด้วย **Apify prebuilt actor** ก่อนเขียน custom (ประหยัดเวลา)
- **Per-listing polling scheduler** — listings มี `next_poll_at`, beat ดึงเฉพาะที่ถึงเวลา
- **Hash-and-skip** — เทียบ payload hash ก่อน process
- **Credit ledger + budget guard** — log credits ทุก request, auto-pause source ถ้าเกิน budget
- Tenacity retry policies + structured error logging
- Discord alerts: 70%, 90%, 100% budget + daily summary
- AliExpress Open API ลอง apply (free) — Lazada/Shopee/FB official APIs **ไม่ใช้** เพราะไม่ตอบ use case ของมือสอง

### Phase 4 — Intelligence Layer
- Multi-tier LLM parser (100% free): Gemini (primary) → Typhoon (Thai fallback) → regex (deterministic)
- Provider abstraction `LLMProvider` interface, redis cache 30 วัน per raw_query hash
- pgvector embeddings + deduplication
- Reference product flow (paste URL)
- Ranking algorithm + pros/cons labels
- Currency conversion (AliExpress USD→THB via daily fx rate)

### Phase 5 — Dashboard & UX
- Top-10 ResultsDashboard
- PriceHistoryChart
- ScheduleManager UI
- SessionManager (FB cookies upload)
- SourceHealth dashboard
- i18n th/en toggle

### Phase 6 — Hardening
- Facebook Marketplace plugin + session management
- AliExpress plugin
- Priceza/JIB/Advice price anchor plugins
- Data retention jobs + partition rotation
- Discord notifications (price drop, new listing, session expire, quota warning)
- Re-cluster dedup background job
- Backup script (pg_dump → mounted volume daily)

### Phase 7 — Production Deployment
- docker-compose.prod.yml overlay (Linux)
- Reverse proxy (Caddy หรือ Traefik) + Let's Encrypt
- structlog → file rotation; optional Loki+Grafana
- Prometheus metrics endpoint (`/metrics`)
- Cost dashboard: LLM API call counts (Gemini/Typhoon free tier usage), scraping API credits used per day
- Single-user authentication (basic auth หรือ Cloudflare Access)

---

## Critical Files

- `backend/shared/scraper/base.py` — AbstractScraper interface
- `backend/shared/core/browserless_client.py` — Playwright remote connection
- `backend/shared/core/proxy_manager.py` — proxy rotation layer
- `backend/shared/core/scraping_api/zenrows.py` — managed API client
- `backend/shared/core/retry.py` — tenacity policies (apply ทุก HTTP call)
- `backend/shared/models/listing.py` — listing + status lifecycle
- `backend/shared/models/account_session.py` — FB cookie storage
- `backend/shared/scraper/deduplicator.py` — pgvector cosine matching
- `backend/shared/scraper/query_parser.py` — multi-tier LLM (Gemini→Typhoon→regex) + Redis cache
- `backend/worker/tasks/scrape_task.py` — main task entry
- `backend/worker/beat_schedule.py` — Celery beat cron config
- `backend/worker/tasks/retention_task.py` — data retention
- `frontend/src/components/SessionManager/` — cookie upload UI
- `docker-compose.yml` + `docker-compose.prod.yml`

---

## Environment Variables (.env.example)

```
# Database
POSTGRES_USER=finditem
POSTGRES_PASSWORD=changeme
POSTGRES_DB=finditem
DATABASE_URL=postgresql+asyncpg://finditem:changeme@postgres:5432/finditem

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# Browserless
BROWSERLESS_URL=ws://browserless:3000

# LLM providers (100% free, multi-tier fallback chain)
# Tier 1 (primary, free 1500/day): Gemini 2.0 Flash
GOOGLE_API_KEY=AIza...
GEMINI_MODEL=gemini-2.0-flash

# Tier 2 (fallback, free, Thai-specialized): Typhoon by SCB 10X
TYPHOON_API_KEY=...
TYPHOON_BASE_URL=https://api.opentyphoon.ai/v1
TYPHOON_MODEL=typhoon-v2-70b-instruct

# Tier 3: regex parser (no API key needed — deterministic local)

# Scraping API providers (Phase 3 benchmark all 3)
SCRAPFLY_API_KEY=...
ZENROWS_API_KEY=...
APIFY_API_TOKEN=...                 # Apify actor marketplace
SCRAPING_API_MONTHLY_BUDGET=180000  # credits — alert ที่ 70%, 90%
# per-source provider mapping (override ต่อ plugin):
#   shopee=scrapfly, lazada=scrapfly, facebook=apify (prebuilt actor มักดีกว่า)
ADAPTIVE_TIERING_ENABLED=true       # try basic → JS → premium ตามลำดับ
FB_MARKETPLACE_DAILY_RUNS=3         # FB กิน credit แพง ลด schedule
DEFAULT_POLL_INTERVAL_MINUTES=720   # 12h default; ปรับ adaptive ต่อ listing

# Proxy (optional, สำหรับ tier=direct)
PROXY_POOL_URLS=http://user:pass@proxy1:port,http://...

# Discord
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Security
FERNET_KEY=...                      # generate: Fernet.generate_key()
SESSION_SECRET=...

# Misc
TZ=Asia/Bangkok
LOG_LEVEL=INFO
```

---

## Verification (E2E)

### Dev (Windows 11 + Docker Desktop)
1. `docker compose up --build` — ทุก service healthy (`docker compose ps`)
2. `docker compose exec api alembic upgrade head` — migrations สำเร็จ + pgvector extension installed
3. เปิด `http://localhost:3000` — UI โหลด, toggle ภาษา TH/EN ได้
4. สร้าง search "การ์ดจอมือสอง ราคาไม่เกิน 5000" → Gemini parse → เห็น structured filter
5. กด "ค้นหาเลย" → Celery worker pickup → live progress ผ่าน WebSocket → ผลลัพธ์โผล่
6. ตรวจ DB: listings มี embedding, price_snapshots ถูกบันทึก, scrape_runs.api_credits_used > 0
7. สร้าง scheduled search (cron `0 */2 * * *`) → ตรวจ Celery beat schedule
8. Mock listing หาย 3 รอบ → status เปลี่ยนเป็น `stale`
9. Upload FB cookies → SessionManager → ตรวจ encrypted storage → trigger FB scrape
10. ปรับราคา 2 snapshot → PriceHistoryChart แสดงเส้น + badge "ราคาลด X%"
11. Trigger price drop → Discord webhook ส่ง embed มี image + link

### Prod (Linux)
12. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`
13. Caddy reverse proxy + Let's Encrypt cert
14. Backup script: `pg_dump` → mounted volume daily
15. Prometheus `/metrics` endpoint accessible
16. Run 24 ชม. — ตรวจ memory ของ browserless, worker, api ไม่ leak (`docker stats`)
17. Trigger session expire → Discord alert + UI badge แดง

---

## Open Questions / Decisions ที่ยังไม่ตัดสิน (ถามตอน implement)

- **Scraping API provider**: ZenRows vs ScrapingBee vs ScraperAPI — ขึ้นกับ trial credits และราคา (สามารถเริ่มด้วย free tier ของทั้งคู่แล้วเทียบ success rate กับ Shopee/Lazada/FB)
- **Authentication**: single-user (basic auth) เพียงพอไหม หรือต้องการ multi-user (OAuth)? — สมมติ single-user ใน v1
- **Proxy provider**: ใช้ตัวฟรี (รอวัวคุกขาวค่ะ) หรือเสียเงิน BrightData/Smartproxy? — เริ่มไม่มี proxy, เพิ่มเมื่อจำเป็น
- **Image storage**: เก็บแค่ URL (cheap, แต่ตาย ถ้า source ลบรูป) vs MinIO (เปลือง storage แต่ historical) — เริ่ม URL only, MinIO เป็น phase 4
- **Legal/ToS**: scraping ขัดกับ ToS ของ Shopee/Lazada/FB — ใช้งานส่วนตัว rate limit ต่ำ, ไม่ resell ข้อมูล, ไม่ public site

---

# Implementation Reference (สำหรับ Sonnet ตอน implement)

ส่วนนี้เป็น concrete contracts, code skeletons, exact configs ที่ implementer ใช้ direct ได้ — ไม่ต้องเดา

---

## A. Python Dependencies (`backend/requirements.txt`)

```
# API
fastapi==0.115.*
uvicorn[standard]==0.32.*
pydantic==2.9.*
pydantic-settings==2.6.*
python-multipart==0.0.12

# Database
sqlalchemy[asyncio]==2.0.*
asyncpg==0.30.*
alembic==1.13.*
pgvector==0.3.*

# Task queue
celery[redis]==5.4.*
redis==5.2.*
flower==2.0.*  # optional: Celery monitoring UI

# Scraping
playwright==1.48.*
playwright-stealth==1.0.*
curl-cffi==0.7.*           # primary HTTP client — Chrome TLS impersonation (JA3/JA4 bypass)
httpx[http2]==0.27.*       # used for Discord webhook / internal API calls only (ไม่ใช่ scraping)
tenacity==9.0.*
beautifulsoup4==4.12.*
lxml==5.3.*
zenrows==1.3.*  # หรือ scrapingbee==2.0

# AI / NLP
google-genai==0.3.*       # Gemini 2.0 Flash (primary LLM, free tier)
openai==1.54.*            # used for Typhoon (OpenAI-compatible)
sentence-transformers==3.2.*  # multilingual embeddings
torch==2.5.*  # CPU-only ใน Dockerfile

# Utils
structlog==24.4.*
python-dotenv==1.0.*
cryptography==43.0.*  # Fernet
forex-python==1.8  # currency conversion
prometheus-client==0.21.*

# Testing
pytest==8.3.*
pytest-asyncio==0.24.*
pytest-vcr==1.0.*
httpx-mock==0.4.*
```

`worker/Dockerfile` ใช้ `requirements.txt` เดียวกัน + ไม่ install playwright browsers (ต่อ browserless แทน).
`api/Dockerfile` ตัด `playwright`, `sentence-transformers`, `torch` ออกได้ (ลด image size 2GB+).

---

## B. Core Type Definitions

### `backend/shared/scraper/types.py`

```python
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, HttpUrl

class Condition(str, Enum):
    NEW = "new"
    USED = "used"
    REFURBISHED = "refurbished"
    UNKNOWN = "unknown"

class Currency(str, Enum):
    THB = "THB"
    USD = "USD"
    CNY = "CNY"

class StructuredQuery(BaseModel):
    """Output ของ LLM query parser (Gemini/Typhoon/regex)"""
    keywords: list[str]
    keywords_th: list[str] = []           # คำค้นภาษาไทย
    keywords_en: list[str] = []           # คำค้นภาษาอังกฤษ
    category: Optional[str] = None        # "gpu", "cpu", "ram", "ssd", "mainboard", "phone", "shoes", ...
    condition: Condition = Condition.UNKNOWN
    min_price_thb: Optional[Decimal] = None
    max_price_thb: Optional[Decimal] = None
    location: Optional[str] = None        # "Bangkok", "Chonburi"
    exclude_keywords: list[str] = []      # "wanted", "ต้องการซื้อ"
    source_filter: list[str] = []         # ["shopee","lazada"]; empty = all
    extra_criteria: dict = {}             # free-form จาก user (เช่น {"warranty": True})

class SellerInfo(BaseModel):
    name: Optional[str] = None
    rating: Optional[float] = None        # 0-5
    review_count: Optional[int] = None
    sold_count: Optional[int] = None
    is_verified: bool = False

class RawListing(BaseModel):
    """ผลลัพธ์จาก plugin scraper — ก่อน normalize เข้า DB"""
    source_id: str                        # "shopee", "lazada", ...
    external_id: str                      # ID ที่ source ใช้
    url: HttpUrl
    title: str
    description: Optional[str] = None
    price: Decimal
    currency: Currency
    condition: Condition = Condition.UNKNOWN
    seller: SellerInfo = SellerInfo()
    location: Optional[str] = None
    image_urls: list[HttpUrl] = []
    posted_at: Optional[datetime] = None
    scraped_at: datetime
    raw_payload: dict = {}                # raw JSON เก็บไว้ debug
```

---

## C. AbstractScraper Interface (concrete)

### `backend/shared/scraper/base.py`

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, Literal, Optional
from .types import StructuredQuery, RawListing

ScraperTier = Literal["direct", "browserless", "managed_api"]

class ScraperConfig(BaseModel):
    tier: ScraperTier
    rate_limit_rps: float = 0.5           # request per second
    use_proxy: bool = False
    api_provider: Optional[Literal["zenrows", "scrapingbee"]] = None
    retry_max_attempts: int = 5
    requires_session: bool = False        # FB
    cookies_source_id: Optional[str] = None

class AbstractScraper(ABC):
    source_id: str                        # class attr — "shopee"
    display_name: str                     # "Shopee Thailand"
    base_url: str
    config: ScraperConfig

    def __init__(self, deps: "ScraperDependencies"):
        """deps มี: db_session, http_client, browserless, scraping_api, proxy_mgr,
                   cookie_store, logger"""
        self.deps = deps

    @abstractmethod
    async def search(self, query: StructuredQuery, limit: int = 50) -> AsyncIterator[RawListing]:
        """yield RawListing ทีละตัว — ไม่เก็บใน list ใน memory ทั้งหมด"""
        ...

    @abstractmethod
    async def get_detail(self, url: str) -> RawListing:
        """ใช้ตอน user paste URL — ดึงรายละเอียดจาก URL เดียว"""
        ...

    async def health_check(self) -> bool:
        """Default: HTTP HEAD ที่ base_url"""
        ...

    def normalize_keywords(self, query: StructuredQuery) -> str:
        """แปลง StructuredQuery → search string ที่ source ยอมรับ
        Default impl join keywords ด้วย space — override ใน plugin ที่ syntax พิเศษ"""
        ...
```

**Plugin registration**: `plugins/__init__.py` ทำ `pkgutil.walk_packages` + `inspect.getmembers` หา subclass ของ `AbstractScraper` แล้วลง dict `{source_id: class}`.

---

## D. Database Schema (SQLAlchemy 2 — แบบเฉพาะ)

### `backend/shared/models/listing.py` (excerpt)

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, ENUM as PgEnum
from sqlalchemy import String, Numeric, Integer, DateTime, ForeignKey
from pgvector.sqlalchemy import Vector

class ListingStatus(str, Enum):
    ACTIVE = "active"
    SOLD = "sold"
    DELETED = "deleted"
    STALE = "stale"
    ERROR = "error"

class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(32), ForeignKey("sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(2048), unique=True)
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column()
    current_price_thb: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    price_original: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    condition: Mapped[str] = mapped_column(String(16))
    seller_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    location: Mapped[str | None] = mapped_column(String(128), index=True)
    image_urls: Mapped[list] = mapped_column(JSONB, default=list)
    spec_tokens: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, index=False)  # GIN index ใน Alembic
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[ListingStatus] = mapped_column(
        PgEnum(ListingStatus, name="listing_status"), default=ListingStatus.ACTIVE, index=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consecutive_missing_count: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_source_external"),
    )

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_title: Mapped[str] = mapped_column(String(512))
    category: Mapped[str | None] = mapped_column(String(64), index=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # pgvector index ใน Alembic: CREATE INDEX ... USING ivfflat (embedding vector_cosine_ops)
```

### Alembic migration เริ่มต้นต้อง

```sql
CREATE EXTENSION IF NOT EXISTS vector;
-- partition: price_snapshots by RANGE (scraped_at) monthly
```

---

## E. Celery Tasks (signatures)

### `backend/celery_app.py` — global config (production-grade defaults)

```python
celery_app = Celery("finditem", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    # --- Reliability: ห้าม task หาย เมื่อ worker ถูก SIGKILL/OOM ---
    task_acks_late=True,                    # ack หลัง task เสร็จ (ไม่ใช่หลัง prefetch)
    task_reject_on_worker_lost=True,        # SIGKILL → requeue ไป worker อื่น
    task_acks_on_failure_or_timeout=False,  # exception → requeue ไม่ ack
    worker_prefetch_multiplier=1,           # บังคับคู่กับ acks_late — ห้าม prefetch หลาย task
    broker_transport_options={
        "visibility_timeout": 3600,         # Redis: 1ชม. ก่อน redeliver (ใหญ่กว่า longest task)
    },
    # --- Idempotency: pair กับ Q4 Redis lock per search_id ---
    # acks_late = task อาจรัน 2 ครั้งได้ → plugin ทุกตัวต้อง idempotent
    # ใช้ lock_key = f"lock:scrape:search:{search_id}" + INSERT ... ON CONFLICT
    # --- Tracing: OTel propagation (Q21) ---
    task_protocol=2,
    task_send_sent_event=True,
    worker_send_task_events=True,
    # --- Serialization ---
    task_serializer="json",
    accept_content=["json"],
    timezone="Asia/Bangkok",
    enable_utc=True,
)
```

### `backend/worker/tasks/scrape_task.py`

```python
# acks_late + reject_on_worker_lost ครอบทุก task ผ่าน config ด้านบน
# (ไม่ต้องซ้ำใน decorator ทุกตัว)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_search(self, search_id: int, source_filter: list[str] | None = None,
               triggered_by: Literal["manual", "schedule"] = "schedule") -> dict:
    """Orchestrate scraping ของ saved search หนึ่งตัว
    1. Acquire Redis lock f"lock:scrape:search:{search_id}" (Q4) — exit ถ้าซ้ำ
    2. Load SavedSearch + StructuredQuery
    3. ตัดสินใจ sources จาก source_filter หรือ all enabled
    4. Spawn sub-task per source (Celery group)
    5. รวมผล + dedup + ranking
    6. Push WebSocket event 'run_completed'
    หมายเหตุ: acks_late = task อาจรันซ้ำ → Redis lock + DB upsert ป้องกัน double-charge credit
    """

@celery_app.task(bind=True, max_retries=5, retry_backoff=True, retry_jitter=True)
def scrape_source(self, search_id: int, source_id: str, run_id: int) -> dict:
    """Scrape source เดียว — รัน plugin.search() + insert listings + price_snapshots
    Idempotent: ใช้ INSERT ... ON CONFLICT (source_id, external_id) DO UPDATE
    """
```

### `backend/worker/beat_schedule.py`

```python
# Celery beat config — load saved_searches แบบ dynamic จาก DB
# ใช้ celery-sqlalchemy-scheduler หรือ custom scheduler ที่ poll saved_searches table
beat_schedule = {
    "session-health-check": {
        "task": "session_health.check_all",
        "schedule": crontab(minute=0, hour="*/6"),  # ทุก 6 ชม.
    },
    "data-retention": {
        "task": "retention.run",
        "schedule": crontab(minute=0, hour=3),  # 03:00 daily
    },
    "fx-rate-update": {
        "task": "currency.update_rates",
        "schedule": crontab(minute=30, hour=0),
    },
    "dedup-recluster": {
        "task": "dedup.recluster_orphans",
        "schedule": crontab(minute=0, hour=4, day_of_week=0),  # Sunday 04:00
    },
}
```

---

## F. API Endpoints (exact)

| Method | Path | Body / Query | Response |
|---|---|---|---|
| POST | `/api/searches` | `{name, raw_query, schedule_cron?, filters?}` | `Search` object |
| GET | `/api/searches` | `?active=true` | `Search[]` |
| GET | `/api/searches/{id}` | | `Search + recent_runs[]` |
| PATCH | `/api/searches/{id}` | partial | updated `Search` |
| DELETE | `/api/searches/{id}` | | 204 |
| POST | `/api/searches/{id}/run` | `{source_filter?: string[]}` | `{run_id, task_id}` |
| POST | `/api/searches/parse` | `{raw_query}` | `StructuredQuery` (LLM parse preview, no save) |
| POST | `/api/searches/from-url` | `{url, criteria}` | `{reference_listing, structured_query}` |
| GET | `/api/dashboard/{search_id}/top` | `?limit=10` | `RankedListing[]` |
| GET | `/api/listings/{id}/price-history` | `?range=30d` | `PricePoint[]` |
| GET | `/api/listings/{id}` | | `Listing + product + similar[]` |
| GET | `/api/sources` | | `Source[]` (พร้อม health) |
| PATCH | `/api/sources/{id}` | `{enabled, tier, ...}` | updated `Source` |
| GET | `/api/sessions` | | `AccountSession[]` (cookies redacted) |
| POST | `/api/sessions` | `{source_id, label, cookies_json}` | created session |
| DELETE | `/api/sessions/{id}` | | 204 |
| POST | `/api/sessions/{id}/test` | | `{status, message}` |
| GET | `/api/runs/{id}` | | `ScrapeRun + items[]` |
| WS | `/ws/runs` | subscribe `{run_id?, search_id?}` | events: `progress`, `item_found`, `error`, `completed` |
| GET | `/api/notifications` | `?unread=true` | `Notification[]` |
| GET | `/metrics` | | Prometheus format |
| GET | `/health` | | `{api: ok, db: ok, redis: ok, browserless: ok}` |

---

## G. LLM Query Parser (prompt template)

### `backend/shared/scraper/query_parser.py`

```python
SYSTEM_PROMPT = """You are a search query parser for a Thai e-commerce aggregator.
Given a user's natural language query (Thai or English or mixed), extract structured
search parameters. Return ONLY valid JSON matching the StructuredQuery schema.

Rules:
- Extract product keywords in BOTH Thai and English when possible (improves multi-source
  search recall). E.g. "การ์ดจอ" → also include "graphics card", "GPU"
- Recognize Thai location names (กรุงเทพ, เชียงใหม่, ชลบุรี → Bangkok, Chiang Mai, Chonburi)
- "มือสอง"/"second hand"/"ใช้แล้ว" → condition: "used"
- "มือ 1"/"ของใหม่"/"new" → condition: "new"
- Price: detect "ไม่เกิน X", "under X", "ต่ำกว่า", "X-Y" (range)
- All prices in THB unless explicitly stated otherwise
- Category: gpu | cpu | ram | mainboard | ssd | hdd | psu | case | monitor |
            phone | tablet | laptop | shoes | clothing | toys | baby | other
- Output schema:
{
  "keywords": ["..."],          // primary search terms (mixed lang)
  "keywords_th": ["..."],
  "keywords_en": ["..."],
  "category": "gpu" | null,
  "condition": "new"|"used"|"refurbished"|"unknown",
  "min_price_thb": number | null,
  "max_price_thb": number | null,
  "location": "Bangkok" | null,
  "exclude_keywords": ["..."],  // signals user does NOT want
  "source_filter": [],          // explicit source mentions
  "extra_criteria": {}          // anything else relevant
}"""

# Multi-tier parser — 100% free, no paid APIs
# Order: Gemini (free, primary) → Typhoon (free, Thai fallback) → regex (deterministic)

class LLMProvider(Protocol):
    async def parse(self, raw: str, schema: dict) -> dict: ...

# Tier 1: Gemini 2.0 Flash (free 1500 req/day, structured output)
class GeminiProvider:
    async def parse(self, raw: str, schema: dict) -> dict:
        response = await self.client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[SYSTEM_PROMPT, raw],
            config={
                "response_mime_type": "application/json",
                "response_schema": schema,  # strict JSON schema enforcement
                "temperature": 0.1,
            },
        )
        return json.loads(response.text)

# Tier 2: Typhoon v2 (free, Thai-specialized — SCB 10X)
# Endpoint: https://api.opentyphoon.ai/v1 (OpenAI-compatible)
class TyphoonProvider:
    async def parse(self, raw: str, schema: dict) -> dict:
        response = await self.openai_client.chat.completions.create(
            model="typhoon-v2-70b-instruct",
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": raw}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        return json.loads(response.choices[0].message.content)

# Orchestrator with fallback chain (no paid tier)
async def parse_query(raw: str) -> StructuredQuery:
    # Check cache first (Q1 optimization)
    cache_key = f"parsed:{hashlib.sha256(raw.encode()).hexdigest()}"
    if cached := await redis.get(cache_key):
        return StructuredQuery.model_validate_json(cached)

    chain = [GeminiProvider(), TyphoonProvider()]
    for provider in chain:
        try:
            data = await asyncio.wait_for(provider.parse(raw, SCHEMA), timeout=10)
            sq = StructuredQuery.model_validate(data)
            await redis.setex(cache_key, 86400 * 30, sq.model_dump_json())  # cache 30 days
            return sq
        except Exception as e:
            log.warning(f"{provider.__class__.__name__} failed: {e}")
            continue
    # All LLM providers failed → regex (deterministic, always works)
    return regex_parse(raw)
```

### Regex fallback (เมื่อ ทุก AI provider fail):
```python
PRICE_PATTERNS = [
    r"ไม่เกิน\s*([\d,]+)",       # max
    r"under\s*([\d,]+)",
    r"ต่ำกว่า\s*([\d,]+)",
    r"([\d,]+)\s*-\s*([\d,]+)",   # range
]
CONDITION_KEYWORDS = {"used": ["มือสอง", "มือ 2", "second hand", "used"],
                      "new": ["มือ 1", "ของใหม่", "new"]}
LOCATION_MAP = {"Bangkok": ["กรุงเทพ", "กทม", "bkk", "bangkok"], ...}
```

---

## H. Plugin Implementation Templates

### Tier=direct: `kaidee.py` skeleton

```python
class KaideeScraper(AbstractScraper):
    source_id = "kaidee"
    display_name = "Kaidee.com"
    base_url = "https://www.kaidee.com"
    config = ScraperConfig(tier="direct", rate_limit_rps=0.5)

    async def search(self, query, limit=50):
        params = {"q": " ".join(query.keywords), "page": 1}
        if query.max_price_thb:
            params["price_max"] = int(query.max_price_thb)
        async with self.deps.http_client as client:
            for page in range(1, math.ceil(limit / 30) + 1):
                params["page"] = page
                r = await self.deps.retry(
                    lambda: client.get(f"{self.base_url}/api/listings", params=params,
                                        headers={"User-Agent": random_ua()})
                )
                data = r.json()
                for item in data["listings"]:
                    yield self._normalize(item)
                await asyncio.sleep(1 / self.config.rate_limit_rps)

    def _normalize(self, item: dict) -> RawListing:
        return RawListing(
            source_id=self.source_id,
            external_id=str(item["id"]),
            url=item["web_url"],
            title=item["title"],
            price=Decimal(str(item["price"])),
            currency=Currency.THB,
            condition=self._parse_condition(item.get("condition_label", "")),
            location=item.get("location", {}).get("province_name"),
            image_urls=[img["url"] for img in item.get("images", [])],
            seller=SellerInfo(
                name=item.get("member", {}).get("display_name"),
                rating=item.get("member", {}).get("rating"),
            ),
            posted_at=parse_iso(item.get("inserted_at")),
            scraped_at=datetime.now(BANGKOK_TZ),
            raw_payload=item,
        )
```

### Tier=managed_api: `shopee.py` skeleton

```python
class ShopeeScraper(AbstractScraper):
    source_id = "shopee"
    config = ScraperConfig(tier="managed_api", api_provider="zenrows", rate_limit_rps=0.3)

    async def search(self, query, limit=50):
        target = (f"https://shopee.co.th/api/v4/search/search_items"
                  f"?keyword={quote(' '.join(query.keywords))}&limit={limit}")
        if query.max_price_thb:
            target += f"&price_max={int(query.max_price_thb * 100000)}"
        # ZenRows handles proxy + JS render + anti-bot
        r = await self.deps.scraping_api.get(target, params={"js_render": "false"})
        data = r.json()
        for item in data.get("items", []):
            item_basic = item.get("item_basic", {})
            yield RawListing(...)
```

### Tier=browserless + cookies: `facebook.py` skeleton

```python
class FacebookMarketplaceScraper(AbstractScraper):
    source_id = "facebook"
    config = ScraperConfig(tier="browserless", requires_session=True,
                           cookies_source_id="facebook")

    async def search(self, query, limit=50):
        cookies = await self.deps.cookie_store.get_active(self.config.cookies_source_id)
        if not cookies:
            raise NoActiveSessionError(self.source_id)
        async with self.deps.browserless.context(cookies=cookies) as ctx:
            page = await ctx.new_page()
            url = f"https://www.facebook.com/marketplace/bangkok/search?query={quote(...)}"
            await page.goto(url, wait_until="domcontentloaded")
            # scroll + extract via XPath/JS evaluate
            # ...
```

---

## I. Ranking Service (formula concrete)

### `backend/shared/services/ranking.py`

```python
def score(listing: Listing, peer_stats: PeerStats, query: StructuredQuery) -> float:
    """Return 0-100 composite score"""
    # 1. Price score (35%): how much below peer median
    price_pct_below = (peer_stats.median_price - listing.current_price_thb) / peer_stats.median_price
    price_score = clamp(50 + price_pct_below * 100, 0, 100)

    # 2. Price trend score (20%): slope of last-7-days snapshots
    trend_score = ...  # lower slope (falling) = higher score

    # 3. Recency score (20%): hours since last_seen_at
    hours = (now - listing.last_seen_at).total_seconds() / 3600
    recency_score = clamp(100 - hours, 0, 100)

    # 4. Seller trust (15%)
    seller_score = (listing.seller_rating or 0) / 5 * 50 + min(listing.review_count or 0, 100) / 2

    # 5. Location match (10%)
    location_score = 100 if query.location and query.location in (listing.location or "") else 50

    return (price_score * 0.35 + trend_score * 0.20 + recency_score * 0.20
            + seller_score * 0.15 + location_score * 0.10)

def generate_pros_cons(listing, score_breakdown) -> tuple[list[str], list[str]]:
    """Auto-derive pros/cons labels จาก score components สูง/ต่ำ
    Pros: ราคาถูกกว่าค่ากลาง 18%, ผู้ขายเรตติ้ง 4.9, กรุงเทพ
    Cons: post นานแล้ว 5 วัน, รีวิวน้อย"""
```

---

## J. Discord Webhook Format

### `backend/shared/services/notifications.py`

```python
async def send_discord_price_drop(listing: Listing, old_price: Decimal, new_price: Decimal):
    drop_pct = (old_price - new_price) / old_price * 100
    embed = {
        "title": f"💰 ราคาลด {drop_pct:.1f}%: {listing.title[:80]}",
        "url": listing.url,
        "color": 0x22c55e,  # green
        "thumbnail": {"url": listing.image_urls[0] if listing.image_urls else None},
        "fields": [
            {"name": "ราคาเดิม", "value": f"฿{old_price:,.0f}", "inline": True},
            {"name": "ราคาใหม่", "value": f"฿{new_price:,.0f}", "inline": True},
            {"name": "แหล่งที่มา", "value": listing.source_id, "inline": True},
            {"name": "ผู้ขาย", "value": listing.seller_payload.get("name", "-"), "inline": True},
            {"name": "ที่อยู่", "value": listing.location or "-", "inline": True},
        ],
        "timestamp": datetime.now(BANGKOK_TZ).isoformat(),
    }
    await httpx_client.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})
```

Notification types: `price_drop`, `new_listing_match`, `session_expired`, `quota_warning`, `scrape_failed`.

---

## K. docker-compose.yml (dev — Windows 11)

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
      TZ: Asia/Bangkok
    volumes: [postgres_data:/var/lib/postgresql/data]
    ports: ["5432:5432"]
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "${POSTGRES_USER}"]

  redis:
    image: redis:7-alpine
    volumes: [redis_data:/data]
    healthcheck: { test: ["CMD","redis-cli","ping"] }

  browserless:
    image: ghcr.io/browserless/chromium:latest
    environment:
      MAX_CONCURRENT_SESSIONS: 5
      CONNECTION_TIMEOUT: 60000
      TOKEN: ${BROWSERLESS_TOKEN}
    ports: ["3000:3000"]

  api:
    build: { context: ./backend, dockerfile: api/Dockerfile }
    env_file: .env
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    ports: ["8000:8000"]
    volumes:
      - ./backend:/app:cached  # bind mount เฉพาะ dev
    command: uvicorn api.main:app --host 0.0.0.0 --reload

  worker:
    build: { context: ./backend, dockerfile: worker/Dockerfile }
    env_file: .env
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
      browserless: { condition: service_started }
    volumes:
      - ./backend:/app:cached
      - hf_cache:/root/.cache/huggingface  # cache embedding model
    command: celery -A worker.celery_app worker -l info -Q default,scrape

  beat:
    build: { context: ./backend, dockerfile: worker/Dockerfile }
    env_file: .env
    depends_on: [redis, postgres]
    command: celery -A worker.celery_app beat -l info

  frontend:
    build: { context: ./frontend }
    depends_on: [api]
    ports: ["3001:80"]

volumes:
  postgres_data:
  redis_data:
  hf_cache:
```

`docker-compose.prod.yml` overlay: ลบ `volumes: ./backend:/app:cached`, ลบ `--reload`, ใส่ Caddy reverse proxy + restart policy `unless-stopped`.

---

## L. Frontend API Client (TypeScript types)

### `frontend/src/types/index.ts`

```typescript
export interface StructuredQuery {
  keywords: string[];
  keywords_th: string[];
  keywords_en: string[];
  category: string | null;
  condition: "new" | "used" | "refurbished" | "unknown";
  min_price_thb: number | null;
  max_price_thb: number | null;
  location: string | null;
  exclude_keywords: string[];
  source_filter: string[];
  extra_criteria: Record<string, unknown>;
}

export interface Listing { /* mirror backend */ }
export interface RankedListing extends Listing {
  score: number;
  rank: number;
  pros: string[];
  cons: string[];
  price_change_7d_pct: number | null;
}
export interface PricePoint { ts: string; price: number; }
export interface Search {
  id: number;
  name: string;
  raw_query: string;
  parsed_query: StructuredQuery;
  schedule_cron: string | null;
  is_active: boolean;
  last_run_at: string | null;
}
export interface RunEvent {
  type: "progress" | "item_found" | "error" | "completed";
  run_id: number;
  search_id: number;
  source_id?: string;
  payload: unknown;
}
```

### `frontend/src/api/client.ts` ใช้ axios + TanStack Query, base URL = `/api`. WebSocket = `new WebSocket(\`ws://${host}/ws/runs?token=...\`)`

---

## M. Per-Phase File Checklist (Implementer's Map)

### Phase 1 — Infrastructure
- [ ] `docker-compose.yml`, `docker-compose.prod.yml`, `.env.example`, `.gitattributes`, `.gitignore`
- [ ] `backend/api/Dockerfile`, `backend/worker/Dockerfile`, `backend/requirements.txt`
- [ ] `backend/shared/config.py` (Pydantic Settings)
- [ ] `backend/shared/database.py` (async engine + session factory)
- [ ] `backend/shared/models/{__init__,source,search,product,listing,price_snapshot,scrape_run,account_session,notification}.py`
- [ ] `backend/alembic/` init + first migration (CREATE EXTENSION vector)
- [ ] `backend/api/main.py` skeleton + `/health`, `/metrics`
- [ ] `backend/worker/celery_app.py`
- [ ] `backend/shared/scraper/types.py`, `base.py` (interface)
- [ ] `backend/shared/core/{retry,proxy_manager,browserless_client,scraping_api/zenrows,pubsub,embeddings,currency,cookie_store}.py` skeletons
- [ ] `frontend/` Vite scaffold + `Dockerfile` + `nginx.conf`

### Phase 2 — Kaidee end-to-end
- [ ] `backend/shared/scraper/plugins/kaidee.py`
- [ ] `backend/shared/scraper/manager.py`
- [ ] `backend/worker/tasks/scrape_task.py` (`run_search`, `scrape_source`)
- [ ] `backend/api/routes/searches.py` (POST /searches, POST /searches/{id}/run)
- [ ] `backend/api/routes/websocket.py`
- [ ] `frontend/src/components/SearchBar/`, `RunStatus/`
- [ ] Test: `tests/plugins/test_kaidee.py` with VCR cassette

### Phase 3 — Anti-bot Plugins
- [ ] `backend/shared/core/scraping_api/zenrows.py` full client
- [ ] `backend/shared/scraper/plugins/shopee.py`, `lazada.py`
- [ ] Quota tracking ใน `scrape_runs.api_credits_used`
- [ ] Discord notification: quota warning at 80%

### Phase 4 — Intelligence
- [ ] `backend/shared/scraper/query_parser.py` (Gemini + Typhoon + regex fallback)
- [ ] `backend/shared/core/embeddings.py` (sentence-transformers wrapper)
- [ ] `backend/shared/scraper/deduplicator.py` (pgvector cosine)
- [ ] `backend/shared/services/reference_product.py` (paste URL flow)
- [ ] `backend/shared/services/ranking.py` (formula above)
- [ ] `backend/shared/core/currency.py` (USD→THB daily rate)

### Phase 5 — Dashboard UI
- [ ] `frontend/src/components/{ResultsDashboard,ProductCard,PriceHistoryChart,ScheduleManager,SourceHealth}/`
- [ ] `frontend/src/i18n/{th,en}.json`
- [ ] `frontend/src/hooks/{useSearch,usePriceHistory,useRunSocket}.ts`

### Phase 6 — FB + Hardening
- [ ] `backend/shared/scraper/plugins/{facebook,aliexpress,priceza,jib,advice}.py`
- [ ] `backend/api/routes/sessions.py` (cookie CRUD)
- [ ] `frontend/src/components/SessionManager/`
- [ ] `backend/worker/tasks/{retention_task,session_health_task,notification_task}.py`
- [ ] `backend/shared/services/notifications.py` (Discord embed builder)
- [ ] partition rotation script

### Phase 7 — Production
- [ ] Caddy/Traefik config + Let's Encrypt
- [ ] `pg_dump` cron backup script
- [ ] structlog config (redact list: cookies, api_keys)
- [ ] Prometheus metric definitions (`scrapes_total`, `scrape_duration_seconds`, `llm_calls_total{provider}`, `api_credits_used_total`)
- [ ] Authentication middleware (basic auth or Cloudflare Access)
- [ ] Smoke test script (`scripts/e2e_smoke.sh`)

---

## N. Cross-Platform Dev Gotchas (Windows 11 + Docker Desktop)

- **Line endings**: ใส่ `.gitattributes`:
  ```
  * text=auto eol=lf
  *.sh text eol=lf
  *.py text eol=lf
  ```
- **Bind mount performance**: ใช้ `:cached` flag, อย่า bind mount `node_modules` หรือ `.venv` (named volumes แทน)
- **Path separators**: ทุก path ใน Python ใช้ `pathlib.Path`, ไม่ hardcode `\\` หรือ `/`
- **Time zone**: container ทุกตัวต้อง set `TZ=Asia/Bangkok`; SQLAlchemy ใช้ `DateTime(timezone=True)` เสมอ
- **Playwright on dev machine**: ไม่ต้อง install — worker ใช้ `browserless` service ทั้งหมด
- **Hot reload**: API ใช้ `uvicorn --reload`, worker ใช้ `watchmedo auto-restart` (`watchdog` package)

---

## O. Testing Strategy

- **Unit tests** (pytest): pure functions (ranking score, currency convert, query parser regex fallback)
- **Plugin tests** (pytest-vcr): record HTTP responses ครั้งเดียว → replay; ทุก plugin ต้องมี cassette
- **Integration tests**: spin postgres + redis ใน test compose, run full scrape_task ด้วย mock plugin
- **Frontend** (Vitest + React Testing Library): component snapshots + user interaction
- **E2E** (Playwright test): smoke flow ใน dev compose — สร้าง search → run → ดู result

---

## P. Decision Log (สำหรับ implementer)

| Decision | Choice | เหตุผล |
|---|---|---|
| Web framework | FastAPI | async, type hints, OpenAPI |
| Task queue | Celery (ไม่ใช่ APScheduler) | scale-out, isolation, monitoring (Flower) |
| Browser strategy | browserless service | memory leak isolation |
| Anti-bot strategy | Hybrid (managed API + direct) | balance cost / reliability |
| Scraping API providers | **Benchmark Scrapfly + ZenRows + Apify ต่อ source** | Scrapfly เน้น Shopee/Lazada (ASP), Apify เหมาะ FB (prebuilt actor); ตัด ScrapingBee (75 creds/req แพง); **ไม่ใช้ official APIs** เพราะ Lazada/Shopee/FB official ไม่มี marketplace มือสอง |
| Scraping pattern | **List-page only, no detail polling** | ลด credit 50× — ราคาอยู่ใน list อยู่แล้ว |
| Polling | **Adaptive interval per listing** | active items poll ถี่, cold items poll นาน — ลด credit 5-10× |
| Premium features | **Adaptive tiering (basic → JS → premium)** | 60-70% pass at basic = avg 4-6 creds/req แทน 25 |
| FB Marketplace | **Opt-in, max 3 runs/day** | กิน credit แพงสุด + cookies หมดอายุง่าย |
| Embeddings | sentence-transformers local | ฟรี + เร็ว + multilingual |
| Dedup signal | **3-stage hybrid**: spec_tokens overlap (GIN) → cosine > 0.85 → spec_tokens equality + price ±50% | vector-only false positive สูงในสินค้า IT (Ti/Super/X3D/capacity) |
| Image storage | URLs only (v1) | minimum viable |
| Auth | single-user (v1) | personal use, scope creep prevention |
| Currency | daily fx rate cache | AliExpress USD ต้องแปลง |
| Time zone | Asia/Bangkok everywhere | local schedules |
| Monthly credit target | **< 200k credits = Scrapfly starter $30** | กับ 10-20 active searches |

---

# Q. Production Optimization Checklist (Beyond Scraping Credits)

หลังจากวาง credit optimization แล้ว ยังมีอีก ~20 จุดที่ต้อง optimize เพื่อไม่ให้มีปัญหา production จริง — แบ่งตาม priority

## 🔥 Critical (จะมีปัญหาใน 1 เดือนแรก)

### Q1. LLM API Quota Control (cache aggressively)

**ปัญหา**: ถ้า re-parse query ทุก scheduled run × 50 searches × 24 ครั้ง/วัน = 1,200 calls/วัน → เกิน free tier ของ Gemini (1,500/วัน) + Typhoon fallback

**Implementation**:
- **Parse ครั้งเดียวตอนสร้าง search** เก็บใน `saved_searches.parsed_query_jsonb`
  - User edit `raw_query` → bump `parsed_query_version` + re-parse
  - Schedule run ใช้ cached parsed_query เสมอ → 0 LLM calls ต่อ scheduled run ปกติ
- **Reference product extraction (paste URL)**: cache ตาม URL hash 30 วัน ใน Redis
  ```python
  # backend/shared/cache/query_cache.py
  cache_key = f"refprod:{hashlib.sha256(url.encode()).hexdigest()}"
  if cached := await redis.get(cache_key): return cached
  ```
- **Redis parse cache**: `parse_query()` แล้วเก็บ result 30 วัน — query เดิมไม่ยิง LLM ซ้ำ
  ```python
  cache_key = f"parsed:{hashlib.sha256(raw.encode()).hexdigest()}"
  if cached := await redis.get(cache_key): return StructuredQuery.model_validate_json(cached)
  await redis.setex(cache_key, 86400 * 30, sq.model_dump_json())
  ```
- **LLM waterfall**: Gemini 2.0 Flash (1,500/วัน ฟรี) → Typhoon v2-70B (ฟรี, Thai-specialized) → regex (deterministic)
- **Track ใน `cost_ledger`**: log `(provider, model, input_tokens, output_tokens, calls_count)` ต่อ call — ไม่มี cost_usd เพราะทุกอย่างฟรี

### Q2. Embedding Recomputation Cache

**ปัญหา**: re-scrape listing เดิม → re-embed title เดิม → 50ms × 1000 listings = 50s ต่อ run + เปลือง CPU

**Implementation**:
- เพิ่ม `listings.title_hash` (SHA-256 ของ normalized title) → ถ้า hash เดิม → skip embed
- เพิ่ม `embeddings_cache` table: `(title_hash PRIMARY KEY, embedding VECTOR(384), created_at)`
- **Pre-load model ตอน worker init**:
  ```python
  from celery.signals import worker_process_init
  @worker_process_init.connect
  def init_worker(**kwargs):
      from shared.core.embeddings import get_model
      get_model()  # warm up
  ```
- **Batch embedding**: รวม 32 titles ต่อ batch call → 5-10× faster

### Q3. raw_payload JSONB Bloat

**ปัญหา**: 1MB × 100k listings = 100GB ใน 6 เดือน → DB IO ช้า, backup ใหญ่

**Implementation**:
- **Drop raw_payload หลัง 30 วัน** ใน retention task:
  ```sql
  UPDATE listings SET raw_payload = '{}'::jsonb
  WHERE last_seen_at < NOW() - INTERVAL '30 days'
    AND raw_payload != '{}'::jsonb;
  ```
- หรือ archive ไป MinIO (S3): `s3://archive/payloads/{listing_id}.json.gz`
- เก็บแค่ structured columns (title, price, location, etc.) เป็นหลัก

### Q4. Idempotency / Duplicate Job Prevention

**ปัญหา**: User กด "Run now" 5 ครั้ง → 5 jobs queue ซ้ำ → กิน credit 5×

**Implementation**:
- **API debounce**: `POST /searches/{id}/run` ตรวจ `scrape_runs` ที่ status=`running` กับ search_id เดียวกัน → return existing run_id
- **Celery task lock** (Redis):
  ```python
  lock_key = f"lock:scrape:search:{search_id}"
  with redis.lock(lock_key, timeout=600, blocking_timeout=0) as acquired:
      if not acquired: return {"status": "already_running"}
      # ... run ...
  ```
- **DB unique constraint** บน listings `(source_id, external_id)` + ใช้ `INSERT ... ON CONFLICT DO UPDATE` (PostgreSQL upsert) — มีอยู่แล้วแต่ต้อง implement ใช้ `pg_insert.on_conflict_do_update()`

### Q5. Per-Source Global Rate Limit (ไม่ใช่ per-task)

**ปัญหา**: rate_limit=0.5 rps × 3 tasks parallel = 1.5 rps → ติด ban

**Implementation**: Redis token bucket ที่ใช้ร่วมข้าม tasks
```python
# backend/shared/core/rate_limiter.py
async def acquire(source_id: str, rps: float):
    """Token bucket per source — ใช้ Redis Lua script atomic"""
    bucket_key = f"ratelimit:{source_id}"
    # Lua: refill bucket, decrement if available, sleep otherwise
    while not await _try_consume(bucket_key, rps):
        await asyncio.sleep(0.1)
```
- ทุก HTTP/scraper call ผ่าน `rate_limiter.acquire(source_id)` ก่อน
- Plugin config `rate_limit_rps` = global limit ไม่ใช่ per-instance

---

## ⚠️ Important (ปัญหาภายใน 3-6 เดือน)

### Q6. Manual Run Quota
- Limit `max 10 manual runs/hour/search` (Redis counter, expire 1h)
- แสดง remaining quota ใน UI ก่อนกด button
- API: `GET /api/searches/{id}/quota`

### Q7. Notification Throttling (anti-fatigue)
- **Threshold filter**: alert เฉพาะ price drop > 5% หรือ > 500 บาท
- **Per-search alert sensitivity** ใน `saved_searches.alert_config JSONB`
- **Digest mode**: รวบ alerts รายวัน ส่ง 18:00 (configurable)
- **Rate limit per channel**: max 5 Discord posts/hour/search

### Q8. WebSocket Auth + Limit
- **JWT token in query**: `ws://host/ws/runs?token=<jwt>` — verify ก่อน accept
- **Connection limit**: max 10 concurrent connections per user
- **Auto-disconnect** ถ้า idle > 5 นาที

### Q9. Browserless Lifecycle
```yaml
browserless:
  environment:
    MAX_CONCURRENT_SESSIONS: 5
    CONNECTION_TIMEOUT: 60000
    MAX_QUEUE_LENGTH: 10
    PREBOOT_CHROME: true
    KEEP_ALIVE: 30000
    DEFAULT_USER_DATA_DIR: /tmp/browserless
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:3000/pressure"]
    interval: 30s
```
- **Auto-restart**: cron task restart browserless container ทุก 6 ชม. (ป้องกัน memory leak)
- **Pressure monitor**: ถ้า `cpu > 80%` หรือ `memory > 80%` → defer scrape

### Q10. Long-Running Task Timeouts
```python
@celery_app.task(soft_time_limit=300, time_limit=360, bind=True)
def scrape_source(self, search_id, source_id, run_id):
    try:
        # ...
    except SoftTimeLimitExceeded:
        # cleanup: close browser, mark run as 'timeout', log partial results
        raise self.retry(exc=..., countdown=120, max_retries=2)
```
- Per-source override: FB อาจต้อง 600s, Kaidee 60s

### Q11. DB Connection Pool Tuning
```python
# backend/shared/database.py
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20, max_overflow=10, pool_pre_ping=True,
    pool_recycle=3600,  # recycle connections ทุก 1 ชม.
)
```
- **Production**: ใส่ **PgBouncer** ระหว่าง app กับ postgres (transaction pooling) — ลด connection count
- Monitor `pg_stat_activity` ถ้าใกล้ `max_connections` → alert

### Q12. Per-Source Health & Auto-Pause
- `sources` table เพิ่มคอลัมน์: `health_status`, `success_rate_24h`, `consecutive_failures`, `paused_until`
- Background task ทุก 15 นาที:
  - คำนวณ success rate จาก `scrape_runs` 24h ล่าสุด
  - ถ้า < 50% → mark `degraded` + Discord alert
  - ถ้า fail 5 ครั้งติด → `paused_until = now + 1h` (auto-pause) + Discord alert
- `/health` API:
  ```json
  {
    "api": "ok",
    "db": "ok",
    "redis": "ok",
    "browserless": "ok",
    "sources": {
      "shopee": "healthy",
      "lazada": "degraded",
      "facebook": "paused"
    }
  }
  ```

---

## 📊 Should Do (long-term hygiene)

### Q13. Cost Observability Dashboard
- Table `cost_ledger`: `(date, category, provider, units, cost_usd)`
  - categories: `gemini_calls`, `typhoon_calls`, `scraping_credit`, `apify_compute`, `embedding_cpu_seconds`
  - `cost_usd` = 0 สำหรับ gemini/typhoon (free tier), ใส่ค่าจริงเฉพาะ Scrapfly/Apify
- Daily Discord report 09:00:
  ```
  📊 Daily Cost Report (2026-05-01)
  Gemini API:        0 calls billed (1,200/1,500 free quota used)
  Typhoon API:       38 fallback calls (free tier)
  Scrapfly:          12,450 credits ($1.87)
  Apify:             3 actor runs ($0.18)
  Total: $2.05 | Month-to-date: $61 / $100 budget
  ```
- API endpoint `/api/cost/summary?range=30d` for UI dashboard

### Q14. Backup Verification
- Daily `pg_dump` to mounted volume (already in plan)
- **Weekly restore test**: Sunday 04:00, restore to scratch DB, run sanity queries:
  ```sql
  SELECT COUNT(*) FROM listings;       -- > 0
  SELECT MAX(scraped_at) FROM price_snapshots;  -- recent
  ```
- Discord alert on restore failure
- Keep last 7 daily + 4 weekly + 12 monthly backups

### Q15. First-Run UX
- Empty state component: "ยังไม่มี search — สร้างตัวแรกเลย"
- "Try Demo" button: pre-fill "การ์ดจอมือสอง ราคาไม่เกิน 5000 บาท" + run

### Q16. Search Edit → Re-rank
- เมื่อ user edit `max_price` หรือ filter → trigger background re-rank (ไม่ scrape ใหม่):
  ```python
  @celery_app.task
  def rerank_search(search_id):
      # filter existing listings ตาม new query, recompute scores
  ```
- Don't re-scrape (ประหยัด credit) — แค่กรอง + reorder

### Q17. Bot/Scam Heuristic
- Rule-based flag listings ที่:
  - `price < median × 0.3` → "ราคาถูกผิดปกติ — ระวัง"
  - title มี keywords: "ขายด่วน รับโอนก่อน", "ไม่รับเก็บเงินปลายทาง"
  - seller_rating < 3 + sold_count = 0 → "ผู้ขายใหม่"
- แสดง warning badge บน ProductCard

### Q18. Price Parsing Robustness
```python
# backend/shared/core/price_parser.py
def parse_thai_price(s: str) -> Decimal | None:
    """Handle: '1,290.00', '฿1290', '1.290,00', 'Negotiable', '-'"""
    s = re.sub(r'[฿$\s,บาทbahtTHB]', '', s, flags=re.I)
    if not s or s.lower() in {'negotiable', 'free', '-'}: return None
    try: return Decimal(s)
    except: return None
```
- Unit tests ทุก variation ของ Shopee/Lazada/FB price format

### Q19. Embedding Model Pre-load
- ใน `worker_process_init` signal (above)
- Cache HuggingFace model ใน named volume `hf_cache` (in compose) — ไม่ download ใหม่ทุก rebuild

### Q20. Secret Rotation (Fernet)
- รองรับ multi-key:
  ```python
  # FERNET_KEYS=key_v2:key_v1  (current first, fallback after)
  fernet_v2 = Fernet(b'key_v2')
  fernet_v1 = Fernet(b'key_v1')
  multi = MultiFernet([fernet_v2, fernet_v1])
  multi.decrypt(token)   # tries each in order
  multi.encrypt(data)    # uses first (v2)
  ```
- Re-encrypt all sessions task (admin-triggered)

### Q21. Distributed Tracing (FastAPI → Celery → DB)

**ปัญหา**: เมื่อ task ค้าง/fail ผ่าน 3 service (API → Redis → Worker → DB) ไม่มี correlation ID → debug ลำบาก ไม่รู้คอขวดอยู่ที่ provider, network, หรือ DB

**Implementation** (minimal stack — 1 trace container, ไม่ใช่ LGTM):

```python
# backend/shared/observability/tracing.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

def init_tracing(service_name: str, otlp_endpoint: str):
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
    trace.set_tracer_provider(provider)
    CeleryInstrumentor().instrument()      # auto-propagate trace_id ผ่าน Celery headers
    SQLAlchemyInstrumentor().instrument()
    RedisInstrumentor().instrument()
    # FastAPIInstrumentor() เรียกหลัง app = FastAPI()

# backend/api/main.py
init_tracing("finditem-api", OTEL_ENDPOINT)
app = FastAPI()
FastAPIInstrumentor().instrument_app(app)

# backend/worker/celery_app.py
init_tracing("finditem-worker", OTEL_ENDPOINT)
```

**Bind trace_id เข้า structlog**:
```python
@app.middleware("http")
async def trace_logger(request: Request, call_next):
    span = trace.get_current_span()
    trace_id = format(span.get_span_context().trace_id, "032x")
    structlog.contextvars.bind_contextvars(trace_id=trace_id)
    return await call_next(request)
```

**Stack เลือก (ไม่ใช่ LGTM full)**:
| Env | Backend | Container count | UI |
|---|---|---|---|
| dev (Win11) | **Jaeger all-in-one** | 1 | localhost:16686 |
| prod (Linux) | **SigNoz self-hosted** หรือ Grafana Cloud free tier | 1 docker-compose | built-in |

```yaml
# docker-compose.dev.yml
jaeger:
  image: jaegertracing/all-in-one:1.62
  ports: ["16686:16686", "4317:4317"]   # UI + OTLP gRPC
  environment:
    COLLECTOR_OTLP_ENABLED: "true"
```

**requirements.txt** (เพิ่ม):
```
opentelemetry-api==1.27.*
opentelemetry-sdk==1.27.*
opentelemetry-exporter-otlp==1.27.*
opentelemetry-instrumentation-fastapi==0.48b0
opentelemetry-instrumentation-celery==0.48b0
opentelemetry-instrumentation-sqlalchemy==0.48b0
opentelemetry-instrumentation-redis==0.48b0
```

**ดู span chain ตัวอย่าง**:
```
POST /searches/42/run         (FastAPI, 12ms)
 └─ celery.send_task          (Redis, 2ms)
     └─ run_search            (Worker, 8.4s)
         ├─ scrape_source[shopee]   (4.2s)
         │   └─ scrapfly.api        (3.9s)  ← คอขวด!
         ├─ scrape_source[kaidee]   (1.1s)
         └─ dedup.cluster           (0.6s)
             └─ pgvector.knn        (0.4s)
```

---

## 🔒 Security Hardening (เพิ่มจาก v2)

| Risk | Mitigation |
|---|---|
| API keys leaked in logs | structlog redact list: `["api_key","token","cookies","password"]` |
| Cookie upload XSS | Validate JSON schema strict, reject if non-cookie shape |
| WebSocket flood | Token + connection limit + idle disconnect |
| SQL injection | SQLAlchemy ORM only, ห้าม raw query ที่ใส่ user input |
| Auth on prod | Single-user basic auth ใน Caddy, หรือ Cloudflare Access |
| Docker secrets | ใช้ Docker secrets หรือ HashiCorp Vault ใน prod (ไม่ใช่ .env file) |
| Audit log | Log ทุก write API call → `audit_log` table |

---

## 📋 Implementation Priority Map

| Phase | Add to checklist |
|---|---|
| Phase 1 | Q11 (DB pool), Q19 (embedding preload), Q20 (fernet multi-key) |
| Phase 2 | Q4 (idempotency), Q5 (rate limiter), Q10 (timeouts), Q18 (price parser) |
| Phase 3 | Q1 (LLM quota), Q9 (browserless lifecycle), Q12 (source health), Q13 (cost ledger) |
| Phase 4 | Q2 (embedding cache), Q3 (raw_payload retention), Q16 (rerank), Q17 (scam filter) |
| Phase 5 | Q6 (manual quota), Q15 (first-run UX) |
| Phase 6 | Q7 (notification throttle), Q8 (WS auth) |
| Phase 7 | Q14 (backup verify), Q21 (distributed tracing), security hardening |

---

## 🎯 Production Readiness Gates

ก่อน deploy prod ต้องผ่าน checklist:

- [ ] Run smoke test 24 ชม. — ตรวจ memory leak (`docker stats` stable)
- [ ] Run 1 full week schedule — ตรวจ credit usage ใกล้ projection
- [ ] Trigger 5 manual runs พร้อมกัน — ไม่ duplicate, ไม่ติด rate limit
- [ ] Kill browserless container — worker recover graceful, retry สำเร็จ
- [ ] Restore backup ไป test DB — query OK
- [ ] Rotate FERNET key — sessions ทั้งหมดยัง decrypt ได้
- [ ] Trigger price drop > 5% — Discord alert ส่ง
- [ ] Cost dashboard แสดงตัวเลขครบทุก provider
- [ ] Source auto-pause: simulate 5 fails → ตรวจ source paused + alert
- [ ] WebSocket auth: ส่ง invalid JWT → reject 401
- [ ] **Tier 1 TLS test**: scrape Cloudflare-protected source ด้วย curl_cffi → success; ตรวจ JA3 ใน wireshark = Chrome
- [ ] **Worker SIGKILL test**: `docker kill` worker กลาง task → task กลับเข้า queue + รันใหม่จนเสร็จ (acks_late)
- [ ] **Trace propagation**: trigger `/searches/X/run` → เห็น span chain ครบใน Jaeger (FastAPI → Celery → DB → external API)
- [ ] **Dedup precision**: insert listing "RTX 4070" + "RTX 4070 Ti" → ระบบแยก product_id ไม่ merge (spec_tokens gate)

