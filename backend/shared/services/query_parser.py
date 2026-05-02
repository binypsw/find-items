"""LLM-powered search query parser for Thai e-commerce.

Multi-tier strategy:
  Tier 1 — Gemini Flash (primary, free 1500/day)
  Tier 2 — Typhoon v2 70B (fallback, Thai-specialised)
  Tier 3 — Regex heuristics (always available)
"""
from __future__ import annotations

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
- keywords: array of main search terms (include both Thai and romanized versions if applicable)
- keywords_th: array of Thai-language keywords only
- keywords_en: array of English keywords only
- category: product category string or null
- condition: "new", "used", "refurbished", or "unknown"
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

    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=1024,
            # Disable thinking for 2.5 Flash — saves tokens, faster for structured output
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
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

async def parse_query(raw_query: str) -> dict:
    """Parse a natural-language search query into structured fields.

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

    # Tier 1 — Gemini Flash
    try:
        result = await _parse_with_gemini(raw_query)
        log.info("parse_query.tier1_gemini_success", query_len=len(raw_query))
        return result
    except Exception as exc:
        log.warning("parse_query.tier1_gemini_failed", error=str(exc))

    # Tier 2 — Typhoon v2
    try:
        result = await _parse_with_typhoon(raw_query)
        log.info("parse_query.tier2_typhoon_success", query_len=len(raw_query))
        return result
    except Exception as exc:
        log.warning("parse_query.tier2_typhoon_failed", error=str(exc))

    # Tier 3 — Regex
    log.info("parse_query.tier3_regex_fallback", query_len=len(raw_query))
    return _parse_regex_fallback(raw_query)
