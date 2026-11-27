"""
services/mandi_service.py - Mandi prices business logic

Retrieves current prices, filters crop/market records, stores and retrieves
historical records from MySQL, and handles data synchronisation with the
data.gov.in AGMARKNET API.

Never invents prices. Falls back to cached database records when the external
API is unavailable.
"""

import logging
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from data.db import get_db
from mysql.connector import Error
from services.mandi_api_service import MandiApiError, clear_cache, fetch_records

logger = logging.getLogger(__name__)

TABLE = "mandi_prices"
SYNC_STATUS_TABLE = "mandi_sync_status"

# In-memory guard to prevent concurrent manual synchronisations.
_sync_lock = threading.Lock()
_sync_job_threads: Dict[str, threading.Thread] = {}


def _iso_date(value) -> Optional[str]:
    """Return a date/datetime value as an ISO YYYY-MM-DD string, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    # Already ISO-like? Return first 10 chars.
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text[:10] if len(text) >= 10 else None

# Fields inserted into / selected from the mandi_prices table.
_INSERT_FIELDS = (
    "state, district, market, commodity, variety, grade, arrival_date, "
    "min_price, max_price, modal_price, source"
)


def _dict_row(row: tuple, columns: List[str]) -> Dict[str, Any]:
    return dict(zip(columns, row))


def _get_connection():
    return get_db()


def _ensure_sync_status_table() -> None:
    """Create the mandi_sync_status table if it does not exist (idempotent)."""
    conn = None
    cur = None
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {SYNC_STATUS_TABLE} (
                job_id VARCHAR(64) PRIMARY KEY,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                filters TEXT,
                max_records INT DEFAULT 5000,
                fetched INT DEFAULT 0,
                inserted INT DEFAULT 0,
                updated INT DEFAULT 0,
                error TEXT,
                started_at TIMESTAMP NULL DEFAULT NULL,
                completed_at TIMESTAMP NULL DEFAULT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.commit()
    except Error as e:
        logger.error("Failed to ensure mandi_sync_status table: %s", e)
        raise
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _iso_sync_ts(value) -> Optional[str]:
    """Return a timestamp/datetime value as an ISO string, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    text = str(value).strip()
    return text or None


def create_sync_job(
    filters: Optional[Dict[str, str]] = None,
    max_records: int = 5000,
) -> str:
    """Insert a pending sync job and return its job_id."""
    _ensure_sync_status_table()
    job_id = uuid.uuid4().hex
    conn = None
    cur = None
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(
            f"""
            INSERT INTO {SYNC_STATUS_TABLE}
                (job_id, status, filters, max_records, created_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            """,
            (
                job_id,
                "pending",
                __import__("json").dumps(filters or {}),
                int(max_records),
            ),
        )
        conn.commit()
        return job_id
    except Error as e:
        logger.error("Failed to create sync job: %s", e)
        raise
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def update_sync_job(job_id: str, **fields: Any) -> None:
    """Update fields of a sync job."""
    if not fields:
        return
    _ensure_sync_status_table()
    columns = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [job_id]
    conn = None
    cur = None
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE {SYNC_STATUS_TABLE} SET {columns} WHERE job_id = %s",
            tuple(values),
        )
        conn.commit()
    except Error as e:
        logger.error("Failed to update sync job %s: %s", job_id, e)
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_sync_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Return a sync job record by job_id, or None if not found."""
    _ensure_sync_status_table()
    conn = None
    cur = None
    try:
        conn = _get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            f"""
            SELECT job_id, status, filters, max_records, fetched, inserted, updated,
                   error, started_at, completed_at, created_at
            FROM {SYNC_STATUS_TABLE}
            WHERE job_id = %s
            """,
            (job_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        for ts_field in ("started_at", "completed_at", "created_at"):
            row[ts_field] = _iso_sync_ts(row.get(ts_field))
        return row
    except Error as e:
        logger.error("Failed to get sync job %s: %s", job_id, e)
        return None
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_latest_sync_job() -> Optional[Dict[str, Any]]:
    """Return the most recent sync job, regardless of status."""
    _ensure_sync_status_table()
    conn = None
    cur = None
    try:
        conn = _get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            f"""
            SELECT job_id, status, filters, max_records, fetched, inserted, updated,
                   error, started_at, completed_at, created_at
            FROM {SYNC_STATUS_TABLE}
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            return None
        for ts_field in ("started_at", "completed_at", "created_at"):
            row[ts_field] = _iso_sync_ts(row.get(ts_field))
        return row
    except Error as e:
        logger.error("Failed to get latest sync job: %s", e)
        return None
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _run_sync(app, job_id: str, filters: Optional[Dict[str, str]], max_records: int) -> None:
    """Background worker: fetch records and store them, then update job status.

    Runs inside the Flask application context so database access works.
    Previously stored records are never deleted, so a failed sync preserves
    the existing cache.
    """
    with app.app_context():
        update_sync_job(job_id, status="running", started_at=datetime.utcnow())
        try:
            result = sync_mandi_prices(filters=filters, max_records=max_records)
            update_sync_job(
                job_id,
                status="completed" if result["success"] else "failed",
                fetched=result.get("fetched", 0),
                inserted=result.get("inserted", 0),
                updated=result.get("updated", 0),
                error=result.get("error"),
                completed_at=datetime.utcnow(),
            )
            if result["success"]:
                logger.info(
                    "Background sync %s completed: %s fetched, %s inserted, %s updated",
                    job_id, result.get("fetched"), result.get("inserted"),
                    result.get("updated"),
                )
            else:
                logger.warning(
                    "Background sync %s failed: %s", job_id, result.get("error")
                )
        except Exception as e:
            logger.error("Background sync %s raised: %s", job_id, e)
            update_sync_job(
                job_id,
                status="failed",
                error=str(e),
                completed_at=datetime.utcnow(),
            )
        finally:
            with _sync_lock:
                _sync_job_threads.pop(job_id, None)


def start_sync(
    app,
    filters: Optional[Dict[str, str]] = None,
    max_records: int = 5000,
) -> str:
    """Start a background synchronisation and return the job_id.

    The heavy API fetch runs in a daemon thread so the caller (and the
    frontend) does not block. A job row is created with status "pending".
    """
    _ensure_sync_status_table()
    with _sync_lock:
        # Prevent concurrent manual synchronisations.
        latest = get_latest_sync_job()
        if latest and latest.get("status") in ("pending", "running"):
            return latest["job_id"]
        # Clean up stale finished threads.
        for jid, t in list(_sync_job_threads.items()):
            if not t.is_alive():
                _sync_job_threads.pop(jid, None)

        job_id = create_sync_job(filters=filters, max_records=max_records)
        thread = threading.Thread(
            target=_run_sync, args=(app, job_id, filters, max_records),
            daemon=True, name=f"mandi-sync-{job_id[:8]}",
        )
        _sync_job_threads[job_id] = thread
        thread.start()
        return job_id


def store_records(records: List[Dict[str, Any]]) -> Dict[str, int]:
    """Insert or update mandi price records.

    Uses the unique constraint on (market, commodity, variety, grade,
    arrival_date) to avoid duplicates and to update revised records.

    Returns a dict with inserted and updated counts.
    """
    if not records:
        return {"inserted": 0, "updated": 0}

    inserted = 0
    updated = 0
    conn = None
    cur = None
    try:
        conn = _get_connection()
        cur = conn.cursor()
        for record in records:
            values = (
                record.get("state"),
                record.get("district"),
                record.get("market"),
                record.get("commodity"),
                record.get("variety"),
                record.get("grade"),
                record.get("arrival_date"),
                record.get("min_price"),
                record.get("max_price"),
                record.get("modal_price"),
                record.get("source", "data.gov.in AGMARKNET"),
            )
            cur.execute(
                f"""
                INSERT INTO {TABLE} ({_INSERT_FIELDS})
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    min_price = VALUES(min_price),
                    max_price = VALUES(max_price),
                    modal_price = VALUES(modal_price),
                    source = VALUES(source),
                    fetched_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                """,
                values,
            )
            if cur.rowcount == 1:
                inserted += 1
            else:
                updated += 1
        conn.commit()
    except Error as e:
        logger.error("Failed to store mandi records: %s", e)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    return {"inserted": inserted, "updated": updated}


def get_distinct_values(
    column: str,
    state: Optional[str] = None,
    district: Optional[str] = None,
    market: Optional[str] = None,
    commodity: Optional[str] = None,
) -> List[str]:
    """Return distinct non-null values for a column, optionally filtered.

    Used to populate the cascading filter dropdowns (state -> district ->
    market -> commodity).
    """
    allowed = {
        "state", "district", "market", "commodity", "variety", "grade",
    }
    if column not in allowed:
        raise ValueError(f"Invalid column: {column}")

    conditions: List[str] = [f"{column} IS NOT NULL AND TRIM({column}) <> ''"]
    params: List[Any] = []

    if state:
        conditions.append("state = %s")
        params.append(state)
    if district:
        conditions.append("district = %s")
        params.append(district)
    if market:
        conditions.append("market = %s")
        params.append(market)
    if commodity:
        conditions.append("commodity = %s")
        params.append(commodity)

    sql = f"SELECT DISTINCT {column} FROM {TABLE} WHERE " + " AND ".join(conditions)
    sql += f" ORDER BY {column}"

    conn = None
    cur = None
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
        return [r[0] for r in rows if r[0]]
    except Error as e:
        logger.error("Failed to get distinct %s: %s", column, e)
        return []
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_current_prices(
    state: Optional[str] = None,
    district: Optional[str] = None,
    market: Optional[str] = None,
    commodity: Optional[str] = None,
    variety: Optional[str] = None,
    grade: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the latest available price records for the selected filters.

    Prices are read from the local historical archive (the cache). The
    "latest" record is the one with the most recent arrival_date.
    """
    conditions: List[str] = []
    params: List[Any] = []

    if state:
        conditions.append("state = %s")
        params.append(state)
    if district:
        conditions.append("district = %s")
        params.append(district)
    if market:
        conditions.append("market = %s")
        params.append(market)
    if commodity:
        conditions.append("commodity = %s")
        params.append(commodity)
    if variety:
        conditions.append("variety = %s")
        params.append(variety)
    if grade:
        conditions.append("grade = %s")
        params.append(grade)

    where = " AND ".join(conditions) if conditions else "1=1"

    sql = f"""
        SELECT state, district, market, commodity, variety, grade,
               arrival_date, min_price, max_price, modal_price, source
        FROM {TABLE}
        WHERE {where}
        ORDER BY arrival_date DESC, fetched_at DESC
    """

    conn = None
    cur = None
    try:
        conn = _get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    except Error as e:
        logger.error("Failed to get current prices: %s", e)
        return {"records": [], "latest_date": None, "source": None, "stale": True}
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    if not rows:
        return {"records": [], "latest_date": None, "source": None, "stale": True}

    latest_date = rows[0]["arrival_date"]
    latest_date = _iso_date(latest_date)

    source = rows[0].get("source")

    # Stale warning: if the latest data is older than 7 days.
    stale = False
    try:
        latest_dt = datetime.strptime(latest_date, "%Y-%m-%d").date()
        if latest_dt < date.today() - timedelta(days=7):
            stale = True
    except (ValueError, TypeError):
        stale = True

    formatted = []
    for row in rows:
        row["arrival_date"] = _iso_date(row.get("arrival_date"))
        formatted.append(row)

    return {
        "records": formatted,
        "latest_date": latest_date,
        "source": source,
        "stale": stale,
    }


def get_history(
    state: Optional[str] = None,
    district: Optional[str] = None,
    market: Optional[str] = None,
    commodity: Optional[str] = None,
    variety: Optional[str] = None,
    grade: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    days: int = 15,
) -> List[Dict[str, Any]]:
    """Return historical price records ordered by arrival_date ascending.

    Missing dates are not synthesised - only actual stored records are
    returned, so gaps remain visible to the caller.
    """
    conditions: List[str] = []
    params: List[Any] = []

    if state:
        conditions.append("state = %s")
        params.append(state)
    if district:
        conditions.append("district = %s")
        params.append(district)
    if market:
        conditions.append("market = %s")
        params.append(market)
    if commodity:
        conditions.append("commodity = %s")
        params.append(commodity)
    if variety:
        conditions.append("variety = %s")
        params.append(variety)
    if grade:
        conditions.append("grade = %s")
        params.append(grade)

    if start_date:
        conditions.append("arrival_date >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("arrival_date <= %s")
        params.append(end_date)
    elif days:
        conditions.append("arrival_date >= %s")
        params.append((date.today() - timedelta(days=days - 1)).isoformat())

    where = " AND ".join(conditions) if conditions else "1=1"

    sql = f"""
        SELECT arrival_date, min_price, max_price, modal_price
        FROM {TABLE}
        WHERE {where}
        ORDER BY arrival_date ASC, market ASC
    """

    conn = None
    cur = None
    try:
        conn = _get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    except Error as e:
        logger.error("Failed to get mandi history: %s", e)
        return []
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    for row in rows:
        row["arrival_date"] = _iso_date(row.get("arrival_date"))
    return rows


def get_summary(
    state: Optional[str] = None,
    district: Optional[str] = None,
    market: Optional[str] = None,
    commodity: Optional[str] = None,
    variety: Optional[str] = None,
    grade: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    days: int = 15,
) -> Dict[str, Any]:
    """Return highest max and lowest min prices with their dates."""
    rows = get_history(
        state=state,
        district=district,
        market=market,
        commodity=commodity,
        variety=variety,
        grade=grade,
        start_date=start_date,
        end_date=end_date,
        days=days,
    )

    highest = None  # (max_price, date)
    lowest = None   # (min_price, date)

    for row in rows:
        max_price = row.get("max_price")
        min_price = row.get("min_price")
        d = row.get("arrival_date")

        if max_price is not None:
            if highest is None or max_price > highest[0]:
                highest = (max_price, d)
        if min_price is not None:
            if lowest is None or min_price < lowest[0]:
                lowest = (min_price, d)

    return {
        "highest_max_price": highest[0] if highest else None,
        "highest_max_date": highest[1] if highest else None,
        "lowest_min_price": lowest[0] if lowest else None,
        "lowest_min_date": lowest[1] if lowest else None,
    }


def sync_mandi_prices(
    filters: Optional[Dict[str, str]] = None,
    max_records: int = 5000,
) -> Dict[str, Any]:
    """Fetch records from data.gov.in and store them locally.

    Returns a summary dict with success/failure info and counts.
    On API failure, returns an error summary (no exception raised) so the
    scheduled job can continue running.
    """
    result: Dict[str, Any] = {
        "success": False,
        "fetched": 0,
        "inserted": 0,
        "updated": 0,
        "error": None,
    }

    try:
        records = fetch_records(filters=filters, max_records=max_records)
    except MandiApiError as e:
        logger.error("Mandi sync API error: %s", e)
        result["error"] = str(e)
        return result
    except Exception as e:
        logger.error("Mandi sync unexpected error: %s", e)
        result["error"] = str(e)
        return result

    result["fetched"] = len(records)

    try:
        counts = store_records(records)
        result["inserted"] = counts.get("inserted", 0)
        result["updated"] = counts.get("updated", 0)
        result["success"] = True
    except Exception as e:
        logger.error("Mandi sync store error: %s", e)
        result["error"] = str(e)

    return result


def get_last_sync_info() -> Dict[str, Any]:
    """Return the most recent fetch timestamp and record count."""
    conn = None
    cur = None
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(
            f"SELECT MAX(fetched_at), COUNT(*) FROM {TABLE}"
        )
        row = cur.fetchone()
        fetched_at = row[0] if row else None
        count = row[1] if row else 0
        if fetched_at is not None and not isinstance(fetched_at, str):
            fetched_at = fetched_at.isoformat()
        return {"last_fetched_at": fetched_at, "record_count": count or 0}
    except Error as e:
        logger.error("Failed to get last sync info: %s", e)
        return {"last_fetched_at": None, "record_count": 0}
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
