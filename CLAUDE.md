# Find Item — Project Context

Thai e-commerce price comparison tool. Monitors prices across Lazada, Kaidee, Shopee, JIB, BNN, Priceza.
รันบน private home server — ไม่ใช่ cloud/production scale

## Global Agent Roles & Delegation Rules
- **Main Session / Orchestrator**: วางแผน, จัดการ `STATUS.md`, กระจายงาน — ห้ามเขียน/แก้โค้ดเอง
- เมื่อต้องแก้โค้ด → เรียก `coder` agent
- เมื่อต้องสำรวจเว็บใหม่ → เรียก `scraper-research` agent
- เมื่อ coder เสร็จ → เรียก `code-reviewer` agent เสมอ
- เมื่อ code-reviewer APPROVED → เรียก `qa` agent เสมอ (ทั้ง FE และ BE)
- **qa agent** เป็น gate สุดท้าย: รัน test scripts + visual check (FE) + mark STATUS.md done
- **qa agent รับผิดชอบ test scripts** ใน `tests/` — เขียน/อัพเดต tests เมื่อ feature เปลี่ยน

## Stack
| Layer | Tech |
|-------|------|
| Backend API | FastAPI + SQLAlchemy async (Python 3.11) |
| Worker | Celery + Redis (broker DB1, cache DB0) |
| Scrapers | curl_cffi + Playwright (Headless / Headed) |
| LLM parser | Gemini 2.0 Flash → Typhoon v2.5 → Regex |
| DB | PostgreSQL 16 + pgvector |
| Frontend | React + nginx (port 3001 → proxies to API:8000) |

## Running the project
```bash
docker compose up -d
docker compose logs -f worker
```
Frontend: http://localhost:3001
API docs: http://localhost:8000/docs (port 8000 exposed to host)
psql: `docker exec find-item-postgres-1 psql -U finditem -d finditem`

## No Paid APIs & Anti-Bot Strategy
- **ห้ามใช้ Paid Scraping APIs** (Scrapfly, ZenRows, ฯลฯ) — private project รันเอง
- **Anti-bot ระดับกลาง** (JS rendering): ใช้ Playwright แบบ `browser_headless`
- **Anti-bot โหดๆ** (Akamai, Cloudflare Enterprise, CAPTCHA): ใช้ Playwright แบบ `browser_headed` (เปิดหน้าจอ) หรือ Persistent Context ให้ user แก้ CAPTCHA / login เองได้
- ห้าม hardcode API keys — โหลดผ่าน `.env` เสมอ

## Key Files
```
backend/shared/scraper/base.py           # AbstractScraper
backend/shared/scraper/types.py          # StructuredQuery, RawListing
backend/shared/scraper/manager.py        # get_scraper() factory
backend/shared/scraper/plugins/          # drop *.py here — auto-discovered
backend/shared/services/query_parser.py
backend/worker/tasks/scrape_task.py
backend/api/routes/dashboard.py
frontend/src/components/ResultsDashboard.tsx
frontend/src/components/ProductCard.tsx
frontend/src/i18n/en.json  th.json
```

## Architecture: How a Search Works
1. `POST /api/searches` → parse_query → Redis cache → Gemini/Typhoon/Regex → store parsed_query
2. `POST /api/searches/{id}/run` → Celery run_search → dispatch scrape_source per enabled source
3. scrape_source → reads parsed_query → builds StructuredQuery → calls plugin
4. Plugin → Playwright (headless/headed) or curl_cffi → relevance filter → upsert listings
5. Redis pubsub → frontend SSE live updates

## Scraper Design Pattern
```python
class MyScraper(AbstractScraper):
    source_id = "mysource"; display_name = "My Source"
    base_url = "https://example.com"
    config = ScraperConfig(tier="direct", rate_limit_rps=0.3)
    async def search(self, query: StructuredQuery, limit=50) -> AsyncIterator[RawListing]:
        keyword = self.normalize_keywords(query)
        yield self._normalize(item)
    async def get_detail(self, url: str) -> RawListing | None: ...
```

**Tiers:**
- `direct` — curl_cffi สำหรับเว็บทั่วไป
- `browser_headless` — Playwright ซ่อนจอ สำหรับเว็บที่ต้องการ JS rendering
- `browser_headed` — Playwright เปิดหน้าจอ สำหรับ anti-bot โหดๆ ที่ต้องการ user interaction

## Database Quick Reference
```sql
SELECT id, enabled, tier FROM sources;
UPDATE sources SET enabled=true WHERE id='priceza';
SELECT source_id, status, items_found, started_at FROM scrape_runs ORDER BY id DESC LIMIT 10;
UPDATE scrape_runs SET status='failed', finished_at=NOW()
  WHERE status='running' AND started_at < NOW() - INTERVAL '30 minutes';
```

## Database Migrations
```bash
# สร้าง migration
docker exec find-item-api-1 alembic revision --autogenerate -m "description"
# apply
docker exec find-item-api-1 alembic upgrade head
```

## Debug Commands
```bash
curl -X POST http://localhost:8000/api/searches/4/run -H "Content-Type: application/json" -d '{}'
curl -X POST http://localhost:8000/api/searches/parse -H "Content-Type: application/json" -d '{"raw_query":"used DDR4 16gb"}'
docker compose logs -f worker | grep -E "(jib|bnn|priceza|lazada|kaidee|error|items_found)"
docker exec find-item-redis-1 redis-cli -n 0 KEYS "qparse:*"
```

## Docker Gotchas
- `docker compose restart` ไม่ reload env vars → ใช้ `docker compose up -d --force-recreate <service>`
- แก้ `plugins/*.py` → `docker compose restart worker` (ไม่ต้อง rebuild)
- แก้ `requirements.txt` → `docker compose build worker && docker compose up -d worker`
- แก้ `frontend/src/` → `docker compose build frontend && docker compose up -d frontend`
- Thai chars ใน Git Bash curl → corrupt เป็น `???` → ใช้ browser/Postman แทน
