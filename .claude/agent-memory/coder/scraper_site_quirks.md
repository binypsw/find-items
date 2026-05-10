---
name: Scraper Site Quirks
description: Site-specific bugs, selector pitfalls, and behavioral quirks for each scraper plugin
type: project
---

## Lazada
- AJAX response has no condition field → all listings stored as `condition="unknown"`
- "Used" filter intentionally includes `condition="unknown"` so Lazada results appear
- Bot protection (`/punish` tmd page): already fixed — Browserless avoids it

## Kaidee
- `KaideeScraper._build_id` is class-level cache. Stale ID auto-refreshes on 404.
- Returns 0 items for DDR4 3600 — real data gap, not a bug

## BNN (bnn.in.th)
- Override `normalize_keywords` to prefer `keywords_en` — Thai stores index in English
- Progressive fallback: drops trailing tokens until results found
- **Critical**: relevance filter always checks against **original full tokens**, NOT the broadened fallback. Prevents flooding from broadened search.

## Priceza (priceza.com)
- Override `normalize_keywords` to prefer `keywords_en`
- Price selector: use `.pz-pdb-price` (base class ONLY)
- **Critical**: do NOT use `.pz-pdb-price.pd-group` — `.pd-group` only matches range-price items; single-price items use `.pz-pdb-price` without subclass → selecting both classes misses them

## Shopee
- Error 90309999 = bot detection. Root cause: `SPC_CDS` is a device-fingerprint token generated on-demand by Shopee's JS library (`spc_cds_lib.js`) for each API call — it is NOT a persistent extractable cookie.
- **Confirmed**: Browserless + valid session cookies (SPC_F, SPC_EC, SPC_U, SPC_ST) + UA override + stealth=true ALL still return 90309999. Even direct curl_cffi with all cookies returns 90309999.
- **Fix requires Scrapfly tier 3** (managed scraping API, ~$30/month) — it provides a real browser fingerprint + residential proxy that passes Shopee's detection.
- Cookie injection code IS implemented (`ShopeeScraper` reads `self.deps.cookie_store.get_active("shopee")` and injects via `ctx.add_cookies()`) but is insufficient alone.
- Shopee is disabled in DB (`enabled=false`). Do NOT enable until Scrapfly is integrated.

## ResultsDashboard (frontend)
- `newRefPrices` uses majority-token filter on `parsed_query.keywords_en` to avoid wrong "new" items (e.g. Canon printer when searching DDR4)
