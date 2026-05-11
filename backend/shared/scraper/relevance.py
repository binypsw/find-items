"""Shared relevance-filtering helpers for scraper plugins.

Centralises the majority-token matching logic and bundle-exclusion rules so
every plugin applies the same criteria consistently.
"""
import math
import re

# Component tokens: when the query contains one of these we know the user is
# looking for a specific hardware component, not a full system.
_COMPONENT_TOKENS = frozenset({
    "ddr4", "ddr5", "ssd", "nvme", "hdd", "cpu", "gpu", "vga",
    "ram", "dimm", "sodimm",
})

# Matches "computer set", "pc set", or the Thai equivalent "ชุดคอม"
_BUNDLE_RE = re.compile(r"\bcomputer\s*set\b|\bpc\s*set\b|\bชุดคอม", re.IGNORECASE)

# Merge "16 GB" → "16gb", "3200 MHz" → "3200mhz" so token matching works
# regardless of whether the source omits or includes the space.
_UNIT_RE = re.compile(r"(\d+)\s+(gb|mb|tb|mhz|ghz|w)\b", re.IGNORECASE)


def normalize_title(text: str) -> str:
    """Lowercase and merge number+unit pairs for consistent token matching."""
    return _UNIT_RE.sub(lambda m: m.group(1) + m.group(2).lower(), text.lower())


def calc_min_match(tokens: list[str]) -> int:
    """Return minimum token matches required for relevance.

    Uses majority-token threshold: ceil(n/2) tokens must appear in
    the title. This prevents single generic tokens (e.g. 'samsung')
    from matching unrelated categories while still allowing partial
    matches for multi-word queries.
    """
    return max(1, math.ceil(len(tokens) / 2))


def is_bundle_excluded(title: str, query_tokens: list[str]) -> bool:
    """Return True if this listing should be excluded as an irrelevant bundle.

    Rejects computer-set/PC-bundle listings when the query is for a
    specific component (RAM, SSD, CPU, GPU, etc.).
    title should already be lowercased/normalized.
    """
    if not any(t in _COMPONENT_TOKENS for t in query_tokens):
        return False
    return bool(_BUNDLE_RE.search(title))
