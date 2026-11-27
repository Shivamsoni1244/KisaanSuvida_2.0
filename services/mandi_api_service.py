"""
services/mandi_api_service.py - data.gov.in AGMARKNET API client

Communicates with the official Government of India data.gov.in AGMARKNET
resource to fetch mandi price records.

Implements:
- Paginated API requests (offset / limit) with a small page size
- Request timeouts (raised to 60s) and retry logic with exponential backoff
- Rate-limit and failed-request handling (HTTP 429 / 5xx)
- Response validation and malformed-JSON handling
- Short-lived in-memory cache to avoid repeated unnecessary requests
- Record normalisation and validation (never invents prices)
"""

import logging
import os
import time
from datetime import datetime
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

MANDI_BASE_URL = "https://api.data.gov.in/resource/"
DEFAULT_TIMEOUT = 60
DEFAULT_LIMIT = 100
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2
CACHE_TTL_SECONDS = 60


class MandiApiError(Exception):
    """Raised when the data.gov.in API cannot be used."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _get_mandi_config() -> Dict[str, Optional[str]]:
    """Retrieve data.gov.in configuration from environment variables."""
    return {
        "api_key": os.environ.get("MANDI_API_KEY"),
        "resource_id": os.environ.get(
            "MANDI_RESOURCE_ID", "9ef84268-d588-465a-a308-a864a43d0070"
        ),
    }


# ---------------------------------------------------------------------------
# Record normalisation
# ---------------------------------------------------------------------------

def _normalize_record(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalise and validate a single AGMARKNET record.

    Returns None for malformed/invalid records. Price fields are coerced to
    float where possible; missing values are left as None (never invented).
    """
    try:
        state = str(raw.get("state") or "").strip()
        district = str(raw.get("district") or "").strip()
        market = str(raw.get("market") or "").strip()
        commodity = str(raw.get("commodity") or "").strip()
        variety = raw.get("variety")
        grade = raw.get("grade")
        arrival_date = raw.get("arrival_date")

        if not state or not district or not market or not commodity:
            return None
        if not arrival_date:
            return None

        # Normalise arrival date to YYYY-MM-DD.
        arrival_date_str = _parse_arrival_date(arrival_date)
        if arrival_date_str is None:
            return None

        def _to_price(value) -> Optional[float]:
            if value is None or value == "":
                return None
            try:
                return round(float(value), 2)
            except (TypeError, ValueError):
                return None

        min_price = _to_price(raw.get("min_price"))
        max_price = _to_price(raw.get("max_price"))
        modal_price = _to_price(raw.get("modal_price"))

        # Validation: minimum must not exceed maximum when both are present.
        if min_price is not None and max_price is not None and min_price > max_price:
            logger.debug("Rejecting record: min_price > max_price (%s)", raw)
            return None

        return {
            "state": state,
            "district": district,
            "market": market,
            "commodity": commodity,
            "variety": variety.strip() if isinstance(variety, str) else variety,
            "grade": grade.strip() if isinstance(grade, str) else grade,
            "arrival_date": arrival_date_str,
            "min_price": min_price,
            "max_price": max_price,
            "modal_price": modal_price,
            "source": "data.gov.in AGMARKNET",
        }
    except Exception as e:
        logger.debug("Failed to normalise record: %s", e)
        return None


def _parse_arrival_date(value: Any) -> Optional[str]:
    """Parse an arrival date value into YYYY-MM-DD.

    AGMARKNET may return dates in several string formats. We only accept
    parsable dates and never invent one.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if not text:
        return None
    formats = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d %B %Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Try ISO-like prefix (first 10 chars).
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Short-lived cache to avoid repeated unnecessary API requests
# ---------------------------------------------------------------------------

_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_cache_lock = RLock()


def _cache_key(resource_id: str, filters: Dict[str, str], offset: int, limit: int) -> str:
    filter_part = "|".join(f"{k}={v}" for k, v in sorted(filters.items()) if v)
    return f"{resource_id}|{filter_part}|{offset}|{limit}"


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expiry, data = entry
        if time.time() > expiry:
            _cache.pop(key, None)
            return None
        return data


def _cache_set(key: str, data: Dict[str, Any]) -> None:
    with _cache_lock:
        _cache[key] = (time.time() + CACHE_TTL_SECONDS, data)


def clear_cache() -> None:
    """Clear the API response cache (mainly for tests)."""
    with _cache_lock:
        _cache.clear()


# ---------------------------------------------------------------------------
# HTTP client with retry
# ---------------------------------------------------------------------------

def _build_session() -> requests.Session:
    """Build a requests session with automatic retry on transient errors.

    Retries on connection errors, read timeouts, HTTP 429 and 5xx responses
    using exponential backoff.
    """
    session = requests.Session()
    retry = Retry(
        total=MAX_RETRIES,
        connect=MAX_RETRIES,
        read=MAX_RETRIES,
        backoff_factor=BACKOFF_BASE_SECONDS,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = _build_session()
    return _session


# ---------------------------------------------------------------------------
# Page fetch
# ---------------------------------------------------------------------------

def _fetch_page(
    api_key: str,
    resource_id: str,
    filters: Dict[str, str],
    offset: int,
    limit: int,
) -> Dict[str, Any]:
    """Fetch a single page of records from data.gov.in.

    Implements retry with exponential backoff for connection errors, read
    timeouts, HTTP 429 and HTTP 5xx responses. Validates the JSON response.
    """
    cache_key = _cache_key(resource_id, filters, offset, limit)
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("Cache hit for mandi page offset=%s limit=%s", offset, limit)
        return cached

    params: Dict[str, Any] = {
        "api-key": api_key,
        "format": "json",
        "offset": offset,
        "limit": limit,
    }
    for key, value in filters.items():
        if value:
            params[f"filters[{key}]"] = value

    session = _get_session()
    last_error: Optional[str] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(
                "Fetching mandi page (attempt %s/%s): offset=%s limit=%s",
                attempt, MAX_RETRIES, offset, limit,
            )
            response = session.get(
                MANDI_BASE_URL + resource_id,
                params=params,
                timeout=DEFAULT_TIMEOUT,
            )

            if response.status_code == 401 or response.status_code == 403:
                raise MandiApiError("data.gov.in API authentication failed (invalid API key).")
            if response.status_code == 429:
                raise MandiApiError("data.gov.in API rate limit exceeded.")
            if response.status_code >= 500:
                raise MandiApiError(
                    f"data.gov.in API server error (HTTP {response.status_code})."
                )
            response.raise_for_status()

            try:
                data = response.json()
            except ValueError as e:
                raise MandiApiError(f"data.gov.in API returned malformed JSON: {e}")

            if not isinstance(data, dict):
                raise MandiApiError("Unexpected API response format (not an object).")

            _cache_set(cache_key, data)
            return data

        except MandiApiError:
            # Authentication / rate-limit / server errors are not retried
            # beyond the built-in Retry for 5xx; re-raise immediately.
            raise
        except requests.exceptions.Timeout as e:
            last_error = f"request timed out after {DEFAULT_TIMEOUT}s: {e}"
            logger.warning("Mandi page timeout (attempt %s/%s): %s", attempt, MAX_RETRIES, e)
        except requests.exceptions.ConnectionError as e:
            last_error = f"connection error: {e}"
            logger.warning("Mandi page connection error (attempt %s/%s): %s", attempt, MAX_RETRIES, e)
        except requests.exceptions.RequestException as e:
            last_error = f"request error: {e}"
            logger.warning("Mandi page request error (attempt %s/%s): %s", attempt, MAX_RETRIES, e)

        if attempt < MAX_RETRIES:
            delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            logger.info("Retrying mandi fetch in %s seconds...", delay)
            time.sleep(delay)

    raise MandiApiError(
        f"data.gov.in API request failed after {MAX_RETRIES} attempts. Last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# Public fetch
# ---------------------------------------------------------------------------

def fetch_records(
    filters: Optional[Dict[str, str]] = None,
    max_records: int = 5000,
) -> List[Dict[str, Any]]:
    """Fetch and validate mandi price records with pagination.

    Args:
        filters: Optional dict of AGMARKNET filter keys (state, district,
            market, commodity, etc.).
        max_records: Hard cap on the number of records fetched.

    Returns:
        A list of normalised, valid record dicts.

    Raises:
        MandiApiError: If the API key is missing or the API cannot be reached.
    """
    config = _get_mandi_config()
    api_key = config["api_key"]
    resource_id = config["resource_id"]

    if not api_key or api_key == "your_data_gov_in_api_key_here":
        raise MandiApiError(
            "MANDI_API_KEY is not configured. Set it in .env to use live mandi prices."
        )

    filters = filters or {}
    all_records: List[Dict[str, Any]] = []
    offset = 0

    while offset < max_records:
        limit = min(DEFAULT_LIMIT, max_records - offset)
        try:
            data = _fetch_page(api_key, resource_id, filters, offset, limit)
        except MandiApiError:
            raise

        records_raw = data.get("records", [])
        if not isinstance(records_raw, list):
            break

        for raw in records_raw:
            normalised = _normalize_record(raw)
            if normalised is not None:
                all_records.append(normalised)

            if len(all_records) >= max_records:
                break

        total = data.get("count", len(records_raw))
        count = len(records_raw)
        if count == 0 or offset + count >= total or len(all_records) >= max_records:
            break

        offset += count

    logger.info(
        "Mandi fetch complete: %s valid records (offset cap %s, page size %s)",
        len(all_records), max_records, DEFAULT_LIMIT,
    )
    return all_records
