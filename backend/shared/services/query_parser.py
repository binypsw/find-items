"""LLM-powered search query parser for Thai e-commerce.

Multi-tier strategy:
  Tier 1 — Gemini Flash (primary, free 1500/day)
  Tier 2 — Typhoon v2 70B (fallback, Thai-specialised)
  Tier 3 — Regex heuristics (always available)

Redis caching: parsed results are cached for 24 h using a SHA-256 key derived
from the normalised query string, so repeated searches skip the LLM entirely.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import structlog

from shared.config import get_settings

log = structlog.get_logger()

_PROMPT_TEMPLATE = """\
You are a search query parser for a Thai e-commerce price comparison tool.
Parse the following search query and return ONLY a valid JSON object (no markdown, no explanation).

Query: {raw_query}

Return JSON with these fields:
- keywords: array of INDIVIDUAL product search tokens (NOT full phrases). Split the product name/model into separate meaningful tokens. E.g. "แรม DDR4 3600 16gb มือสอง" → ["แรม", "DDR4", "3600", "16GB"]. Exclude condition/price/location words from this array (those go in their own fields). Do NOT repeat the same term in both Thai and English in this array.
- keywords_th: array of INDIVIDUAL Thai-language product tokens only (e.g. ["แรม"] for RAM, ["โน๊ตบุ๊ค"] for notebook, ["มือถือ"] for phone). Exclude condition words (มือสอง/ใหม่) and price words. If the product name has no Thai translation, leave this empty.
- keywords_en: array of INDIVIDUAL English/model tokens only (brand names, model numbers, spec codes like DDR4/16GB/3600MHz/RTX3080)
- category: product category string or null (e.g. "ram", "gpu", "laptop", "smartphone")
- condition: "new", "used", "refurbished", or "unknown". Thai condition mappings: มือสอง/สภาพมือสอง/second hand → "used"; ใหม่/ของใหม่/brand new → "new"; รีเฟิร์บ/refurb → "refurbished"
- min_price_thb: minimum price in THB (number) or null
- max_price_thb: maximum price in THB (number) or null
- location: Thai province/area name or null
- exclude_keywords: terms to exclude from results
- source_filter: specific marketplaces to search (shopee, lazada, kaidee) or empty array for all
- extra_criteria: any other specific requirements as key-value pairs
"""

_EXAMPLE_SCHEMA = {
    "keywords": ["search term 1", "search term 2"],
    "keywords_th": ["Thai terms"],
    "keywords_en": ["English terms"],
    "category": "electronics",
    "condition": "used",
    "min_price_thb": None,
    "max_price_thb": 5000,
    "location": None,
    "exclude_keywords": [],
    "source_filter": [],
    "extra_criteria": {},
}

_DEFAULT_RESULT: dict[str, Any] = {
    "keywords": [],
    "keywords_th": [],
    "keywords_en": [],
    "category": None,
    "condition": "unknown",
    "min_price_thb": None,
    "max_price_thb": None,
    "location": None,
    "exclude_keywords": [],
    "source_filter": [],
    "extra_criteria": {},
}

_CACHE_TTL = 86400  # 24 hours


def _cache_key(raw_query: str) -> str:
    digest = hashlib.sha256(raw_query.lower().strip().encode()).hexdigest()[:16]
    return f"qparse:{digest}"


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of an LLM response."""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()
    # Find first { … }
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(text[start:end])


def _coerce_result(raw: dict) -> dict:
    """Ensure result has all expected keys with correct types."""
    result = dict(_DEFAULT_RESULT)
    result.update({k: v for k, v in raw.items() if k in _DEFAULT_RESULT})
    # Normalise condition
    cond = str(result.get("condition") or "unknown").lower()
    if cond not in ("new", "used", "refurbished"):
        cond = "unknown"
    result["condition"] = cond
    # Ensure lists
    for key in ("keywords", "keywords_th", "keywords_en", "exclude_keywords", "source_filter"):
        if not isinstance(result[key], list):
            result[key] = []
    # Ensure dict
    if not isinstance(result.get("extra_criteria"), dict):
        result["extra_criteria"] = {}
    # Coerce prices
    for price_key in ("min_price_thb", "max_price_thb"):
        val = result.get(price_key)
        try:
            result[price_key] = float(val) if val is not None else None
        except (TypeError, ValueError):
            result[price_key] = None
    return result


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

async def _redis_get(key: str) -> dict | None:
    """Fetch a cached parse result. Returns None on miss or Redis error."""
    try:
        import redis.asyncio as aioredis

        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        async with client:
            raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        log.debug("query_parser.redis_get_error", error=str(exc))
        return None


async def _redis_set(key: str, value: dict) -> None:
    """Store a parse result in Redis. Silently ignores errors."""
    try:
        import redis.asyncio as aioredis

        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        async with client:
            await client.setex(key, _CACHE_TTL, json.dumps(value))
    except Exception as exc:
        log.debug("query_parser.redis_set_error", error=str(exc))


# ---------------------------------------------------------------------------
# Tier 1 — Gemini Flash
# ---------------------------------------------------------------------------

async def _parse_with_gemini(raw_query: str) -> dict:
    from google import genai
    from google.genai import types

    settings = get_settings()
    if not settings.google_api_key:
        raise RuntimeError("google_api_key not configured")

    client = genai.Client(api_key=settings.google_api_key)
    prompt = _PROMPT_TEMPLATE.format(raw_query=raw_query)

    # Build config — thinking_budget is only supported by gemini-2.5-* models;
    # omit it for 2.0-flash to avoid an API error.
    model = settings.gemini_model or "gemini-2.0-flash"
    gen_cfg_kwargs: dict[str, Any] = {
        "temperature": 0.1,
        "max_output_tokens": 1024,
    }
    if "2.5" in model:
        # Disable thinking for 2.5 Flash — saves tokens, faster for structured output
        gen_cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)

    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(**gen_cfg_kwargs),
    )
    data = _extract_json(response.text)
    return _coerce_result(data)


# ---------------------------------------------------------------------------
# Tier 2 — Typhoon v2 (OpenAI-compatible)
# ---------------------------------------------------------------------------

async def _parse_with_typhoon(raw_query: str) -> dict:
    import openai

    settings = get_settings()
    if not settings.typhoon_api_key:
        raise RuntimeError("typhoon_api_key not configured")

    client = openai.AsyncOpenAI(
        api_key=settings.typhoon_api_key,
        base_url=settings.typhoon_base_url,
    )
    prompt = _PROMPT_TEMPLATE.format(raw_query=raw_query)
    completion = await client.chat.completions.create(
        model=settings.typhoon_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=512,
    )
    text = completion.choices[0].message.content or ""
    data = _extract_json(text)
    return _coerce_result(data)


# ---------------------------------------------------------------------------
# Tier 3 — Regex heuristics
# ---------------------------------------------------------------------------

_PRICE_PATTERNS = [
    # Thai: ไม่เกิน 5000, ราคาไม่เกิน 5,000
    r"(?:ไม่เกิน|ราคาไม่เกิน)\s*([\d,]+)",
    # English: under 5000, max 5000, < 5000
    r"(?:under|max(?:imum)?|below|<)\s*([\d,]+)",
    # Pattern: 5000 บาท or 5,000 THB at sentence boundary
    r"([\d,]+)\s*(?:บาท|thb)\b",
]

_MIN_PRICE_PATTERNS = [
    r"(?:ราคาเกิน|มากกว่า|over|above|min(?:imum)?|>)\s*([\d,]+)",
]

_USED_PATTERNS = re.compile(
    r"\b(?:มือสอง|used|second[\s-]?hand|pre[\s-]?owned|สภาพมือสอง)\b", re.IGNORECASE
)
_NEW_PATTERNS = re.compile(
    r"\b(?:ใหม่|ของใหม่|new|brand[\s-]?new)\b", re.IGNORECASE
)
_REFURB_PATTERNS = re.compile(
    r"\b(?:refurb(?:ished)?|รีเฟิร์บ|renovated)\b", re.IGNORECASE
)

_SOURCE_MAP = {
    "shopee": re.compile(r"\bshopee\b", re.IGNORECASE),
    "lazada": re.compile(r"\blazada\b", re.IGNORECASE),
    "kaidee": re.compile(r"\bkaidee\b", re.IGNORECASE),
}


def _parse_regex_fallback(raw_query: str) -> dict:
    result = dict(_DEFAULT_RESULT)

    # Price — max
    max_price = None
    for pat in _PRICE_PATTERNS:
        m = re.search(pat, raw_query, re.IGNORECASE)
        if m:
            try:
                max_price = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                pass
    result["max_price_thb"] = max_price

    # Price — min
    min_price = None
    for pat in _MIN_PRICE_PATTERNS:
        m = re.search(pat, raw_query, re.IGNORECASE)
        if m:
            try:
                min_price = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                pass
    result["min_price_thb"] = min_price

    # Condition
    if _REFURB_PATTERNS.search(raw_query):
        result["condition"] = "refurbished"
    elif _USED_PATTERNS.search(raw_query):
        result["condition"] = "used"
    elif _NEW_PATTERNS.search(raw_query):
        result["condition"] = "new"
    else:
        result["condition"] = "unknown"

    # Source filter
    sources = [src for src, pat in _SOURCE_MAP.items() if pat.search(raw_query)]
    result["source_filter"] = sources

    # Keywords — just split; let downstream handle Thai segmentation
    result["keywords"] = raw_query.split()
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _post_process(result: dict, raw_query: str) -> dict:
    """Fix common LLM gaps with deterministic checks on the raw query.

    Covers cases where the LLM misses Thai condition words or leaves
    keywords_th empty even when Thai text is clearly present.

    Uses direct substring checks (not regex \b) to avoid word-boundary
    issues with Thai Unicode in Python's re module.
    """
    # --- Condition fix — use direct substring matching for Thai words ---
    if result.get("condition", "unknown") == "unknown":
        rq_lower = raw_query.lower()
        if "รีเฟิร์บ" in raw_query or "refurb" in rq_lower:
            result["condition"] = "refurbished"
        elif "มือสอง" in raw_query or "สภาพมือสอง" in raw_query or "second hand" in rq_lower:
            result["condition"] = "used"
        elif "ของใหม่" in raw_query or "brand new" in rq_lower:
            result["condition"] = "new"

    # --- keywords_th fix ---
    # If LLM left keywords_th empty, extract Thai tokens from raw_query.
    # Use explicit Unicode escape for Thai block (U+0E00–U+0E7F) to avoid
    # potential encoding issues with literal Thai chars in the regex range.
    _CONDITION_TH = {"มือสอง", "ใหม่", "ของใหม่", "สภาพมือสอง", "มือหนึ่ง", "รีเฟิร์บ"}
    if not result.get("keywords_th"):
        # U+0E00–U+0E7F = full Thai Unicode block
        thai_tokens = re.findall(r"[฀-๿]+", raw_query)
        filtered = [t for t in thai_tokens if t not in _CONDITION_TH]
        if filtered:
            result["keywords_th"] = filtered

    return result


async def parse_query(raw_query: str) -> dict:
    """Parse a natural-language search query into structured fields.

    Results are cached in Redis for 24 h. On a cache hit the LLM is bypassed
    entirely. Redis errors are silently ignored (graceful degradation).

    Returns dict with keys:
        keywords: list[str]      — main search terms (Thai or English)
        keywords_th: list[str]   — Thai keywords
        keywords_en: list[str]   — English keywords
        category: str | None     — product category (electronics, clothing, etc)
        condition: str           — "new" | "used" | "refurbished" | "unknown"
        min_price_thb: float | None
        max_price_thb: float | None
        location: str | None     — Bangkok area, province name
        exclude_keywords: list[str]
        source_filter: list[str] — ["shopee", "lazada", "kaidee"] or []
        extra_criteria: dict
    """
    if not raw_query or not raw_query.strip():
        return dict(_DEFAULT_RESULT)

    # --- Redis cache check ---
    cache_key = _cache_key(raw_query)
    cached = await _redis_get(cache_key)
    if cached is not None:
        log.info("parse_query.cache_hit", query_len=len(raw_query))
        return cached

    result: dict | None = None

    # Tier 1 — Gemini Flash
    try:
        result = await _parse_with_gemini(raw_query)
        log.info("parse_query.tier1_gemini_success", query_len=len(raw_query))
    except Exception as exc:
        log.warning("parse_query.tier1_gemini_failed", error=str(exc))

    # Tier 2 — Typhoon v2
    if result is None:
        try:
            result = await _parse_with_typhoon(raw_query)
            log.info("parse_query.tier2_typhoon_success", query_len=len(raw_query))
        except Exception as exc:
            log.warning("parse_query.tier2_typhoon_failed", error=str(exc))

    # Tier 3 — Regex
    if result is None:
        log.info("parse_query.tier3_regex_fallback", query_len=len(raw_query))
        result = _parse_regex_fallback(raw_query)

    final = _post_process(result, raw_query)

    # --- Cache the result ---
    await _redis_set(cache_key, final)

    return final
