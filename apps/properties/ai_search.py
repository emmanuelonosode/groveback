"""
Hybrid AI search — natural-language query → structured filters via Gemini.

Only invoked for queries the cheap regex parser can't confidently handle.
Fails safe: returns None on missing key, network error, timeout, or bad output,
so the caller falls back to the regex `q` parser. Results are cached in
django.core.cache so repeat queries never hit the API.

Uses the stable Gemini REST API directly (via `requests`) — no extra SDK.
"""
import json
import logging
import hashlib

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.0-flash"        # cheap, fast, generous free tier
CACHE_TTL     = 7 * 24 * 60 * 60          # 7 days — identical queries served free
TIMEOUT_S     = 4.0                        # hard cap; fall back to regex if slower
MAX_LEN       = 300                        # don't spend tokens on absurd input
ENDPOINT      = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_SYSTEM = """You convert a renter's natural-language home search into structured JSON filters for a US rental site.
Extract ONLY fields you are confident the user stated or clearly implied. Omit everything else — do not guess.

Return a single JSON object with any of these optional keys:
- city: US city name only, e.g. "Atlanta" (never invent one not in the query)
- state: 2-letter US state code, e.g. "GA"
- beds: integer, minimum bedrooms ("2 bed", "three bedroom" -> 2 / 3)
- baths: integer, minimum bathrooms
- minPrice: integer monthly minimum
- maxPrice: integer monthly maximum ("under 2000", "below $2k", "max 1500" -> maxPrice)
- type: one of "residential" (house or apartment), "condo", "townhouse"
- pets: true only if pets/dogs/cats are mentioned
- listing_type: "for-rent" or "for-sale" (omit if unclear)
- sort: "price_asc" only if they ask for cheap/affordable/budget
- keywords: short leftover descriptive terms ("downtown", "garage", "fenced yard", "near schools")

Output JSON only — no prose, no markdown, no code fences."""


def parse_query(text):
    """Return a dict of structured filters, or None to signal regex fallback."""
    text = (text or "").strip()
    if not text or len(text) > MAX_LEN:
        return None

    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not api_key:
        return None

    cache_key = "ai_search:" + hashlib.sha256(text.lower().encode("utf-8")).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        # Empty dict is a valid "parsed, nothing extracted" result — collapse to None.
        return cached or None

    model = (getattr(settings, "GEMINI_MODEL", "") or DEFAULT_MODEL).strip()
    payload = {
        "systemInstruction": {"parts": [{"text": _SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0,
            "maxOutputTokens": 512,
        },
    }

    try:
        resp = requests.post(
            ENDPOINT.format(model=model),
            params={"key": api_key},
            json=payload,
            timeout=TIMEOUT_S,
        )
        if resp.status_code != 200:
            logger.warning("ai_search gemini HTTP %s: %s", resp.status_code, resp.text[:200])
            return None

        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Defensive: strip ``` / ```json fences if the model adds them anyway.
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw[:4].lower() == "json":
                raw = raw[4:].strip()

        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return None
        result = {k: v for k, v in parsed.items() if v not in (None, "", [], {})}
        cache.set(cache_key, result, CACHE_TTL)
        return result or None
    except Exception as e:  # noqa: BLE001 — never let search break on AI failure
        logger.warning("ai_search.parse_query failed: %s", e)
        return None
