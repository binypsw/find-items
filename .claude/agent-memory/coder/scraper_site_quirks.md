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
- Error 90309999 = bot detection. Needs real session cookies: SPC_F, SPC_EC, SPC_U, SPC_CDS, SPC_ST
- `ShopeeScraper` reads `self.deps.cookie_store.get_active("shopee")` and injects via `ctx.add_cookies()` before navigation — skips homepage warmup when cookies present
- If cookies loaded but 90309999 still fires → cookies expired; re-extract from browser and re-POST to `/api/sessions`
- To seed: extract cookies from logged-in Shopee session in browser, POST to `POST /api/sessions` with `source_id="shopee"`, `label="<date>"`, `cookies_json="<Playwright-format JSON array>"` — cookies **must** include `"domain": ".shopee.co.th"` on each entry (Playwright scopes injected cookies by domain before any navigation)
- Still disabled in DB (`enabled=false`) — enable after seeding cookies: `UPDATE sources SET enabled=true WHERE id='shopee'`

## ResultsDashboard (frontend)
- `newRefPrices` uses majority-token filter on `parsed_query.keywords_en` to avoid wrong "new" items (e.g. Canon printer when searching DDR4)
