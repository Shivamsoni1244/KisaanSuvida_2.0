"""
routes/mandi_routes.py - Mandi Prices module endpoints

Page route:
- GET /mandi  -> Mandi Prices dashboard page

API routes (all under /api/mandi):
- GET  /api/mandi/prices      current prices for selected crop & mandi
- GET  /api/mandi/history     historical prices (last 15 days by default)
- GET  /api/mandi/summary     highest max / lowest min with dates
- GET  /api/mandi/states      available states
- GET  /api/mandi/districts   districts for a state
- GET  /api/mandi/markets     markets for state + district
- GET  /api/mandi/commodities available commodities
- POST /api/mandi/sync        manual synchronisation with data.gov.in
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from flask import Blueprint, jsonify, render_template, request, current_app
from auth.decorators import login_required
from services.mandi_service import (
    _sync_lock,
    get_current_prices,
    get_distinct_values,
    get_history,
    get_last_sync_info,
    get_latest_sync_job,
    get_sync_job,
    get_summary,
    start_sync,
    sync_mandi_prices,
)
from services.mandi_analytics import prepare_graph_data

logger = logging.getLogger(__name__)

mandi_bp = Blueprint("mandi", __name__)


# ---------------------------------------------------------------------------
# Page route
# ---------------------------------------------------------------------------

@mandi_bp.route("/mandi")
@login_required
def mandi_dashboard():
    """Render the Mandi Prices dashboard page."""
    sync_info = get_last_sync_info()
    return render_template(
        "mandi/dashboard.html",
        active_page="mandi",
        last_sync=sync_info.get("last_fetched_at"),
        record_count=sync_info.get("record_count", 0),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_param(name: str) -> Optional[str]:
    value = request.args.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_date_param(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _filter_args() -> dict:
    return {
        "state": _get_param("state"),
        "district": _get_param("district"),
        "market": _get_param("market"),
        "commodity": _get_param("commodity"),
        "variety": _get_param("variety"),
        "grade": _get_param("grade"),
    }


def _json_response(payload, status=200):
    return jsonify(payload), status


# ---------------------------------------------------------------------------
# Current prices
# ---------------------------------------------------------------------------

@mandi_bp.route("/api/mandi/prices", methods=["GET"])
@login_required
def api_prices():
    filters = _filter_args()
    result = get_current_prices(**filters)
    if not result["records"]:
        return _json_response(
            {
                "success": True,
                "data": [],
                "latest_date": None,
                "source": None,
                "stale": True,
                "message": "No price records available for the selected filters.",
            }
        )
    return _json_response(
        {
            "success": True,
            "data": result["records"],
            "latest_date": result["latest_date"],
            "source": result["source"],
            "stale": result["stale"],
        }
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@mandi_bp.route("/api/mandi/history", methods=["GET"])
@login_required
def api_history():
    filters = _filter_args()
    start_date = _parse_date_param(_get_param("start_date"))
    end_date = _parse_date_param(_get_param("end_date"))
    try:
        days = int(request.args.get("days", 15))
    except (TypeError, ValueError):
        days = 15
    if days < 1 or days > 365:
        days = 15

    rows = get_history(
        start_date=start_date,
        end_date=end_date,
        days=days,
        **filters,
    )
    return _json_response({"success": True, "data": rows, "count": len(rows)})


# ---------------------------------------------------------------------------
# Summary (highest max / lowest min)
# ---------------------------------------------------------------------------

@mandi_bp.route("/api/mandi/summary", methods=["GET"])
@login_required
def api_summary():
    filters = _filter_args()
    start_date = _parse_date_param(_get_param("start_date"))
    end_date = _parse_date_param(_get_param("end_date"))
    try:
        days = int(request.args.get("days", 15))
    except (TypeError, ValueError):
        days = 15
    if days < 1 or days > 365:
        days = 15

    summary = get_summary(
        start_date=start_date,
        end_date=end_date,
        days=days,
        **filters,
    )
    return _json_response({"success": True, "data": summary})


# ---------------------------------------------------------------------------
# Filter options (from the local cache / archive)
# ---------------------------------------------------------------------------

@mandi_bp.route("/api/mandi/states", methods=["GET"])
@login_required
def api_states():
    rows = get_distinct_values("state")
    return _json_response({"success": True, "data": [{"name": r} for r in rows]})


@mandi_bp.route("/api/mandi/districts", methods=["GET"])
@login_required
def api_districts():
    state = _get_param("state")
    if not state:
        return _json_response(
            {"success": False, "error": "validation_error", "message": "state is required."},
            400,
        )
    rows = get_distinct_values("district", state=state)
    return _json_response({"success": True, "data": [{"name": r} for r in rows]})


@mandi_bp.route("/api/mandi/markets", methods=["GET"])
@login_required
def api_markets():
    state = _get_param("state")
    district = _get_param("district")
    rows = get_distinct_values("market", state=state, district=district)
    return _json_response({"success": True, "data": [{"name": r} for r in rows]})


@mandi_bp.route("/api/mandi/commodities", methods=["GET"])
@login_required
def api_commodities():
    state = _get_param("state")
    district = _get_param("district")
    market = _get_param("market")
    rows = get_distinct_values("commodity", state=state, district=district, market=market)
    return _json_response({"success": True, "data": [{"name": r} for r in rows]})


# ---------------------------------------------------------------------------
# Graph data
# ---------------------------------------------------------------------------

@mandi_bp.route("/api/mandi/graph", methods=["GET"])
@login_required
def api_graph():
    filters = _filter_args()
    start_date = _parse_date_param(_get_param("start_date"))
    end_date = _parse_date_param(_get_param("end_date"))
    try:
        days = int(request.args.get("days", 15))
    except (TypeError, ValueError):
        days = 15
    if days < 1 or days > 365:
        days = 15
    use_modal = request.args.get("use_modal", "true").lower() != "false"

    graph = prepare_graph_data(
        start_date=start_date,
        end_date=end_date,
        days=days,
        use_modal=use_modal,
        **filters,
    )
    return _json_response({"success": True, "data": graph})


# ---------------------------------------------------------------------------
# Manual synchronisation
# ---------------------------------------------------------------------------

@mandi_bp.route("/api/mandi/sync", methods=["POST"])
@login_required
def api_sync():
    """Trigger a manual synchronisation with data.gov.in.

    The lengthy API fetch runs in a background thread so the request returns
    immediately (HTTP 202). The client polls /api/mandi/sync/status?job_id=
    for progress and completion.
    """
    with _sync_lock:
        latest = get_latest_sync_job()
        if latest and latest.get("status") in ("pending", "running"):
            return _json_response(
                {
                    "success": False,
                    "status": latest.get("status"),
                    "job_id": latest.get("job_id"),
                    "message": "A mandi price synchronisation is already in progress.",
                    "error": "sync_in_progress",
                },
                409,
            )

    job_id = start_sync(current_app._get_current_object())
    return _json_response(
        {
            "success": True,
            "status": "pending",
            "job_id": job_id,
            "message": "Mandi price synchronisation started in the background.",
        },
        202,
    )


@mandi_bp.route("/api/mandi/sync/status", methods=["GET"])
@login_required
def api_sync_status():
    """Return the status of a synchronisation job."""
    job_id = request.args.get("job_id", type=str)
    if not job_id:
        return _json_response(
            {"success": False, "error": "validation_error", "message": "job_id is required."},
            400,
        )
    job = get_sync_job(job_id)
    if not job:
        return _json_response(
            {"success": False, "error": "not_found", "message": "Sync job not found."},
            404,
        )
    return _json_response(
        {
            "success": True,
            "job_id": job.get("job_id"),
            "status": job.get("status"),
            "fetched": job.get("fetched", 0),
            "inserted": job.get("inserted", 0),
            "updated": job.get("updated", 0),
            "error": job.get("error"),
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
            "created_at": job.get("created_at"),
        }
    )

