"""
Analytics helpers — shared utilities for all analytics endpoints.
"""

from __future__ import annotations

import functools
import json
from datetime import date, timedelta
from typing import Any

from flask import current_app, g

# ── Redis cache ───────────────────────────────────────────────────────────────


def _redis():
    try:
        import redis as redis_lib

        url = current_app.config.get("CELERY_BROKER_URL", "redis://redis:6379/1")
        return redis_lib.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def cache_response(ttl: int = 60):
    """
    Decorator: cache the JSON-serialisable return value of a view function
    in Redis for *ttl* seconds. Key is built from store_id + full request path+qs.
    Falls back to no-caching if Redis is unavailable.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            from flask import request

            if current_app.config.get("TESTING"):
                return fn(*args, **kwargs)
            store_id = getattr(g, "current_user", {}).get("store_id", 0)
            cache_key = f"analytics:{store_id}:{request.full_path}"
            r = _redis()
            if r:
                try:
                    hit = r.get(cache_key)
                    if hit:
                        from flask import jsonify

                        return jsonify(json.loads(hit))
                except Exception:
                    pass
            result = fn(*args, **kwargs)
            if r:
                try:
                    # result may be a Response — grab its JSON data
                    data = result.get_json() if hasattr(result, "get_json") else result
                    r.setex(cache_key, ttl, json.dumps(data, default=str))
                except Exception:
                    pass
            return result

        return wrapper

    return decorator


# ── Date helpers ──────────────────────────────────────────────────────────────


def parse_date(s: str | None, fallback: date) -> date:
    if not s:
        return fallback
    try:
        return date.fromisoformat(s)
    except ValueError:
        return fallback


def bucket_date(d: date, group_by: str) -> str:
    """Return ISO string for the *start* of the period the date belongs to."""
    if group_by == "week":
        # ISO Monday
        return (d - timedelta(days=d.weekday())).isoformat()
    if group_by == "month":
        return d.replace(day=1).isoformat()
    return d.isoformat()  # 'day' default


# ── Moving average ────────────────────────────────────────────────────────────


def compute_7d_moving_avg(rows: list[dict], value_key: str = "revenue") -> list[dict]:
    """
    Given a list of dicts sorted by 'date' (ascending), compute trailing 7-day
    moving average. Partial averages (< 7 points) are used for early rows.
    Returns the same list with an extra 'moving_avg_7d' key on each row.
    """
    values = [r[value_key] or 0.0 for r in rows]
    for i, row in enumerate(rows):
        window = values[max(0, i - 6) : i + 1]
        row["moving_avg_7d"] = round(sum(window) / len(window), 4)
    return rows


# ── Grouping / aggregation ────────────────────────────────────────────────────


def aggregate_by_period(rows: list[dict], group_by: str, numeric_keys: list[str]) -> list[dict]:
    """
    Collapse daily rows into period buckets.
    rows must contain a 'date' key (str or date).
    Returns list sorted by period.
    """
    from collections import defaultdict

    buckets: dict[str, dict] = defaultdict(lambda: {k: 0.0 for k in numeric_keys})
    counts: dict[str, int] = defaultdict(int)

    for row in rows:
        d = row["date"] if isinstance(row["date"], date) else date.fromisoformat(str(row["date"]))
        bucket = bucket_date(d, group_by)
        for k in numeric_keys:
            buckets[bucket][k] += float(row.get(k) or 0.0)
        counts[bucket] += 1

    result = []
    for period in sorted(buckets):
        entry = {"date": period, **{k: round(buckets[period][k], 4) for k in numeric_keys}}
        result.append(entry)
    return result


# ── Zero-fill helpers ─────────────────────────────────────────────────────────


def zero_fill_date_range(
    rows: list[dict],
    start: date,
    end: date,
    value_keys: list[str],
    date_key: str = "date",
) -> list[dict]:
    """
    Ensure every calendar day in [start, end] is present, filling missing days
    with 0 for every key in *value_keys*.

    rows: list of dicts with a string or date under *date_key*.
    Returns list sorted by date ascending.
    """
    existing: dict[str, dict] = {}
    for row in rows:
        d = row[date_key]
        if not isinstance(d, str):
            d = str(d)
        existing[d] = row

    result = []
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        entry = dict(existing[key]) if key in existing else {date_key: key, **{k: 0.0 for k in value_keys}}
        result.append(entry)
        cursor += timedelta(days=1)
    return result


def build_7d_revenue_series(rows: list[dict], today: date) -> list[dict]:
    """
    From DB rows (may be sparse), build an array of exactly 7 dicts
    [{date: 'YYYY-MM-DD', revenue: float}] covering the last 7 days
    (today-6 .. today), zero-filling any missing days.
    """
    week_start = today - timedelta(days=6)
    filled = zero_fill_date_range(rows, week_start, today, ["revenue"], date_key="date")
    # Keep only the date and revenue fields
    return [{"date": r["date"], "revenue": float(r.get("revenue") or 0.0)} for r in filled]
