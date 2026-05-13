---
name: fb-marketplace-research
description: Facebook Marketplace Thailand scraping research — SSR Relay JSON, no login needed for initial 24 results, DOM selectors confirmed
metadata:
  type: project
---

Facebook Marketplace Thailand scraping research completed 2026-05-13.

**Key findings:**
- Listings load via SSR (Relay preloaded cache) in `script[type="application/json"]` tags — no login needed for first 24 results
- Bangkok URL: `https://www.facebook.com/marketplace/bangkok/search/?query={keyword}`
- location_id for Bangkok: `"bangkok"` (used in URL path and Relay variables)
- Data lives in script tag containing `CometMarketplaceSearchContentContainerQueryRelayPreloader` (script index varies — search by content not index)
- JSON path: `marketplace_search.feed_units.edges[].node.listing`
- Pagination: cursor-based via `page_info.end_cursor` + `has_next_page`; 24 items/page
- GraphQL queryID for content query: `26739105855731997` (may rotate with FB deploys)
- Price field: `listing_price.formatted_amount` (e.g. "฿1,700") or `listing_price.amount` (numeric string)
- Title field: `marketplace_listing_title`
- Image field: `primary_listing_photo.image.uri`
- Item URL: `/marketplace/item/{listing.id}/`
- Location: `location.reverse_geocode.city` + `.state`
- All GraphQL network requests during unauthenticated session = QR login polling loop — NOT search data
- Listing condition: NOT present in SSR data (all marketplace = used/second-hand by nature)

**Why:** Login wall pops up as dialog but page still renders 24 SSR listings underneath — Facebook does this for SEO
**How to apply:** Implement as browser_headed with persistent profile; use DOM parsing of SSR JSON (not GraphQL intercept) for unauthenticated first page; for pagination/more results need logged-in GraphQL intercept
