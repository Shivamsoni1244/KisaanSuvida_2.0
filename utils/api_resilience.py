"""
utils/api_resilience.py - Thread-safe caching, pacing, and 429 retry helper.

Provides:
- A size-bounded, thread-safe in-memory TTL cache keyed by normalized URL +
  sorted query parameters (max 500 entries, default TTL 1800s / 30 min).
- cached_get_json(): GET + JSON with a descriptive User-Agent header,
  per-host minimum call spacing, and exponential-backoff retry on HTTP 429
  (honoring the Retry-After header). Returns the raw JSON dict/list so
  downstream code sees zero schema difference.
- pace_mistral_call(): thread-locked pacing guaranteeing >= 1.2s spacing
  between consecutive Mistral API calls.

Only uses the Python standard library plus the existing `requests` package.
No new dependencies are introduced.
"""

import logging
import random
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-safe, size-bounded TTL cache
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_cache: Dict[str, tuple] = {}          # key -> (expiry_ts, value)
_cache_order: List[str] = []           # insertion order for bounded eviction

MAX_CACHE_ENTRIES = 500
DEFAULT_TTL = 1800                     # 30 minutes


def _normalize_key(url: str, params: Optional[Dict[str, Any]]) -> str:
    """Normalize URL + sorted query parameters into a stable cache key."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path

    query_items: List[tuple] = []
    if parsed.query:
        query_items.extend(parse_qsl(parsed.query, keep_blank_values=True))
    if params:
        for key, value in params.items():
            if value is None:
                continue
            query_items.append((str(key), str(value)))
    query_items.sort()
    query = urlencode(query_items)

    return urlunparse((scheme, netloc, path, "", query, ""))


def _evict_if_needed() -> None:
    """Evict oldest entries while cache exceeds max size."""
    while len(_cache) > MAX_CACHE_ENTRIES and _cache_order:
        oldest = _cache_order.pop(0)
        _cache.pop(oldest, None)


def cache_get(key: str) -> Optional[Any]:
    """Return cached value for key, or None if missing/expired."""
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expiry, value = entry
        if time.time() > expiry:
            _cache.pop(key, None)
            if key in _cache_order:
                _cache_order.remove(key)
            return None
        return value


def cache_set(key: str, value: Any, ttl: float) -> None:
    """Store value in cache with TTL, evicting if over capacity."""
    with _cache_lock:
        now = time.time()
        _cache[key] = (now + ttl, value)
        _cache_order.append(key)
        _evict_if_needed()


# ---------------------------------------------------------------------------
# Per-host minimum call spacing
# ---------------------------------------------------------------------------

_pacing_lock = threading.Lock()
_last_call_by_host: Dict[str, float] = {}   # host -> last call start timestamp


def _wait_for_host_spacing(host: str, min_interval: float) -> None:
    """Block until min_interval has elapsed since the last call to host."""
    with _pacing_lock:
        now = time.time()
        last = _last_call_by_host.get(host, 0.0)
        elapsed = now - last
        if elapsed < min_interval:
            sleep_for = min_interval - elapsed
        else:
            sleep_for = 0.0
        _last_call_by_host[host] = now + sleep_for
    if sleep_for > 0:
        time.sleep(sleep_for)


# ---------------------------------------------------------------------------
# cached_get_json
# ---------------------------------------------------------------------------

def cached_get_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    ttl: float = DEFAULT_TTL,
    min_interval: float = 0.4,
    max_retries: int = 3,
    timeout: float = 10,
) -> Optional[Any]:
    """
    GET JSON from a URL with caching, per-host pacing, and 429 retry.

    Args:
        url: Target URL.
        params: Optional query parameters (merged & sorted into cache key).
        ttl: Cache TTL in seconds (default 1800 / 30 min).
        min_interval: Minimum seconds between calls to the same host.
        max_retries: Number of 429 retry attempts (total attempts = max_retries + 1).
        timeout: Request timeout in seconds.

    Returns:
        The raw JSON dict/list from the API, or None on failure.
    """
    key = _normalize_key(url, params)

    cached = cache_get(key)
    if cached is not None:
        return cached

    host = urlparse(url).netloc.lower()
    headers = {"User-Agent": "KisaanSuvidha/1.0"}

    last_error: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        _wait_for_host_spacing(host, min_interval)

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout,
            )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                wait: Optional[float] = None
                if retry_after is not None:
                    try:
                        wait = float(retry_after)
                    except (TypeError, ValueError):
                        wait = None
                if wait is None:
                    wait = min(1.5 * (2 ** attempt), 10.0)
                    wait = wait + random.uniform(0, 1.0)
                wait = min(wait, 10.0)

                logger.warning(
                    "HTTP 429 for %s (attempt %d/%d): retrying after %.2fs",
                    url, attempt + 1, max_retries + 1, wait,
                )
                last_error = Exception(f"HTTP 429 for {url}")
                time.sleep(wait)
                continue

            response.raise_for_status()
            data = response.json()
            cache_set(key, data, ttl)
            return data

        except requests.exceptions.HTTPError as e:
            last_error = e
            if e.response is not None and e.response.status_code == 429:
                continue
            logger.error("HTTP error fetching %s: %s", url, e)
            return None
        except Exception as e:
            last_error = e
            logger.error("Error fetching %s: %s", url, e)
            return None

    logger.error("Exhausted retries for %s: %s", url, last_error)
    return None


# ---------------------------------------------------------------------------
# pace_mistral_call
# ---------------------------------------------------------------------------

_mistral_pacing_lock = threading.Lock()
_mistral_last_call: float = 0.0


def pace_mistral_call(min_interval: float = 1.2) -> None:
    """
    Guarantee at least min_interval seconds between consecutive Mistral API calls.

    Must be called immediately before any Mistral chat/embedding invocation so
    back-to-back RAG embedding + LLM calls never breach Mistral's free-tier
    1 RPS limit on shared outbound IPs.
    """
    global _mistral_last_call
    with _mistral_pacing_lock:
        now = time.time()
        elapsed = now - _mistral_last_call
        if elapsed < min_interval:
            sleep_for = min_interval - elapsed
        else:
            sleep_for = 0.0
        _mistral_last_call = now + sleep_for
    if sleep_for > 0:
        time.sleep(sleep_for)
