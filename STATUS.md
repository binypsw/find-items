# Find Item — Current Status

_Last updated: 2026-05-10 — documentation restructure complete_
_Next update: after first successful docker compose up + scrape run_

## Sources

| Source | Status | Notes |
|---|---|---|
| Lazada | ✅ Last known working | Browserless AJAX intercept, ~37 items |
| Kaidee | ✅ Last known working | Next.js SSR, 0 items for DDR4 3600 = real data gap |
| JIB | ✅ Last known working | curl_cffi + BeautifulSoup, ~31 items |
| BNN | ✅ Last known working | curl_cffi + progressive fallback, ~18 items |
| Priceza | ✅ Last known working | curl_cffi aggregator (covers Advice/IT City), ~24 items |
| Shopee | ❌ Disabled | Bot detection 90309999 — needs SPC_F, SPC_EC, SPC_U cookies |
| Facebook | ❌ Disabled | Needs FB session cookies |
| Advice | ⏸ Skipped | Cloudflare block — Priceza covers it already |
| AliExpress | ❌ No scraper | Not started |

## Features

| Feature | Status |
|---|---|
| Query parser (Gemini→Typhoon→Regex) + Redis cache | ✅ Working |
| Lazada / Kaidee / JIB / BNN / Priceza scrapers | ✅ Working |
| Dashboard UI (sort, filter, auto-refresh, Run Now) | ✅ Working |
| New-vs-used comparison bar | ✅ Working |
| Product clustering (sentence-transformers) | ✅ Done — processed=166 |
| Ranking (condition preference, percentile price norm) | ✅ Working |
| Price history charts | ❌ Not implemented |
| Discord notifications | ❌ Not implemented |
| Shopee scraper | ❌ Blocked — needs cookies |
| Facebook scraper | ❌ Blocked — needs cookies |

## Next Tasks

- [ ] สร้าง .env บนเครื่องนี้ และ verify docker compose up ทำงานได้
- [ ] Verify all sources ด้วย scrape run จริง แล้วอัพ status table นี้
- [ ] Shopee cookies (user action required)
- [ ] Facebook cookies + scraper (user action required)
- [ ] Verify agent memory is loaded correctly in coder agent session
