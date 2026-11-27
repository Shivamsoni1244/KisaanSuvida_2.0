"""
services/mandi_analytics.py - Mandi price analytics

Calculates historical maximum and minimum prices with their dates, and
prepares 15-day graph data from actual stored records. Missing dates are
represented as gaps (null values), never converted to zero.
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from services.mandi_service import get_history, get_summary


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _parse_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def compute_summary(
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
    """Return highest max and lowest min prices with dates within the period."""
    return get_summary(
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


def prepare_graph_data(
    state: Optional[str] = None,
    district: Optional[str] = None,
    market: Optional[str] = None,
    commodity: Optional[str] = None,
    variety: Optional[str] = None,
    grade: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    days: int = 15,
    use_modal: bool = True,
) -> Dict[str, Any]:
    """Prepare 15-day graph data series.

    Returns labels (dates) and three datasets: max_price, min_price, and the
    third line which is modal_price when available/source-based, otherwise a
    calculated midpoint clearly identified as such.

    Missing dates within the range appear as null (gaps) - lines are not
    connected across missing records.
    """
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

    # Build a date-indexed map of actual records. If multiple records exist
    # for the same date (e.g. multiple varieties/grades), keep the first.
    by_date: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        d = row.get("arrival_date")
        if not d:
            continue
        if d not in by_date:
            by_date[d] = row

    # Determine the date range.
    if start_date and end_date:
        range_start = _parse_date(start_date)
        range_end = _parse_date(end_date)
    else:
        range_end = date.today()
        range_start = range_end - timedelta(days=days - 1)

    if not range_start or not range_end:
        range_end = date.today()
        range_start = range_end - timedelta(days=days - 1)

    labels: List[str] = []
    max_prices: List[Optional[float]] = []
    min_prices: List[Optional[float]] = []
    third_prices: List[Optional[float]] = []
    third_label = "Modal Price" if use_modal else "Average (Calculated)"

    current = range_start
    while current <= range_end:
        label = current.isoformat()
        labels.append(label)

        record = by_date.get(label)
        if record:
            max_prices.append(_to_float(record.get("max_price")))
            min_prices.append(_to_float(record.get("min_price")))

            modal = _to_float(record.get("modal_price"))
            if use_modal:
                third_prices.append(modal)  # None preserved as gap
            else:
                min_p = _to_float(record.get("min_price"))
                max_p = _to_float(record.get("max_price"))
                if min_p is not None and max_p is not None:
                    third_prices.append(round((min_p + max_p) / 2, 2))
                else:
                    third_prices.append(None)
        else:
            # Missing date: gap, never zero.
            max_prices.append(None)
            min_prices.append(None)
            third_prices.append(None)

        current += timedelta(days=1)

    return {
        "labels": labels,
        "datasets": {
            "max_price": max_prices,
            "min_price": min_prices,
            "modal_price": third_prices,
        },
        "third_label": third_label,
        "use_modal": use_modal,
        "start_date": range_start.isoformat(),
        "end_date": range_end.isoformat(),
        "record_count": len(rows),
    }


def compute_extrema(
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
    """Convenience wrapper returning the historical summary."""
    return compute_summary(
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
