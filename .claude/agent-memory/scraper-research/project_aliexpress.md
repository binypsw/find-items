---
name: aliexpress-research
description: AliExpress TH (th.aliexpress.com) scraper research — bxpunish anti-bot, DOM selectors, pagination confirmed
metadata:
  type: project
---

AliExpress uses Alibaba's custom **bxpunish** anti-bot system (not Cloudflare/Akamai/DataDome).

**Why:** Plain HTTP requests almost always trigger bxpunish=1 → redirect to `/punish` JS challenge page with x5secdata token. Real content requires JS execution and valid browser session cookies.

**How to apply:** Must use `browser_headless` (Playwright) tier. Cannot use `direct` curl_cffi for this site. Browser session works because it executes the JS challenge on first load.

## Key Facts

- **Base URL:** `https://th.aliexpress.com/w/wholesale-{keyword-slug}.html`
  - Keyword format: hyphen-separated English, e.g., `wholesale-DDR4-16GB.html`
  - Legacy URL `aliexpress.com/wholesale?SearchText=...` redirects to the new pattern
- **Locale:** `th.aliexpress.com` auto-detects TH locale, shows THB prices
- **Page param:** `?page=2` for pagination, 12 items per page

## Anti-Bot: bxpunish System

- `bxpunish: 1` response header = redirect to `/punish?x5secdata=...` JS challenge
- Triggered on nearly every plain HTTP request (urllib, requests, etc.)
- Triggers even with: proper User-Agent, full browser headers, Referer, session cookies from homepage
- Does NOT trigger in Playwright headless browser (browser executes JS challenges automatically)
- Akamai is present at edge/CDN layer (X-Akamai-Fwd-Auth headers) but not the primary blocker
- Server: Tengine/Aserver (Alibaba's custom nginx)

## DOM Selectors (browser-rendered HTML, confirmed working)

- **Card container:** `.search-item-card-wrapper-gallery` (12 per page)
- **Title:** `h3.k7_kw` (text content)
- **Price (current):** `div.k7_ea[aria-label]` → aria-label="THB1,013.03"
- **Price (original/crossed):** `span` with `text-decoration:line-through` inside `.k7_lx`
- **Discount %:** `span.k7_lz`
- **URL:** `a.search-card-item[href]` → `//th.aliexpress.com/item/{id}.html`
- **Image:** `img.product-img[src]` → `//ae-pic-a1.aliexpress-media.com/...`
- **Rating:** `span.k7_kg` (numeric e.g. "4.9")
- **Sold count:** `span.k7_km` (e.g. "2,000+ ขายแล้ว")

## Pagination

- Pattern: `?page={n}`, starts at 1
- Items per page: 12 (from DOM), pageSize=60 found in HTML (unclear which is actual)
- Confirmed: page=2 and page=3 return different products

## Browser Cookies Required

Key cookies set by JS challenge execution:
- `_baxia_sec_cookie_` — Alibaba security cookie (long encrypted value)
- `_m_h5_tk` + `_m_h5_tk_enc` — MTOP API auth tokens
- `cna` — device fingerprint
- `xman_us_f` / `xman_t` / `xman_f` — locale/session
- `aep_usuc_f` — currency/locale preferences (c_tp=THB ensures THB prices)

## Recommended Implementation

- **Tier:** `browser_headless` (Playwright)
- **Strategy:** Playwright navigates to search URL → waits for `.search-item-card-wrapper-gallery` → extracts DOM
- **Rate limit:** Max 0.2 RPS (1 request per 5s) to avoid triggering bxpunish; browser session helps
- **Items per search:** ~12 per page, ~3-5 pages = 36-60 items realistic
- **Condition:** AliExpress is new-only marketplace (no used items)

## Related

- [[fb-marketplace-research]] — another browser_headless source
