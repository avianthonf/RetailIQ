"""RetailIQ Analytics Helpers."""

import json
import logging
from collections import defaultdict
from datetime import date, timedelta
from functools import wraps

from flask import g, request

logger = logging.getLogger(__name__)


def parse_date(value, default: date) -> date:
    if not value:
        return default
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return default


def bucket_date(d: str, period: str) -> str:
    dt = date.fromisoformat(d)
    if period == "week":
        monday = dt - timedelta(days=dt.weekday())
        return str(monday)
    if period == "month":
        return dt.strftime("%Y-%m")
    return d


def aggregate_by_period(rows: list[dict], period: str, sum_keys: list[str]) -> list[dict]:
    buckets = defaultdict(lambda: defaultdict(float))
    for row in rows:
        bucket = bucket_date(row["date"], period)
        for k in sum_keys:
            buckets[bucket][k] += row.get(k, 0)
    result = []
    for bucket in sorted(buckets):
        entry = {"date": bucket}
        entry.update(buckets[bucket])
        result.append(entry)
    return result


def compute_7d_moving_avg(rows: list[dict], value_key: str = "revenue") -> list[dict]:
    window = 7
    for i, row in enumerate(rows):
        values = [rows[j].get(value_key, 0) for j in range(max(0, i - window + 1), i + 1)]
        row["moving_avg_7d"] = round(sum(values) / len(values), 4) if values else 0
    return rows


def zero_fill_date_range(rows: list[dict], start: date, end: date, zero_keys: list[str]) -> list[dict]:
    by_date = {r["date"]: r for r in rows}
    result = []
    d = start
    while d <= end:
        key = str(d)
        if key in by_date:
            result.append(by_date[key])
        else:
            entry = {"date": key}
            entry.update({k: 0 for k in zero_keys})
            result.append(entry)
        d += timedelta(days=1)
    return result


def build_7d_revenue_series(rows: list[dict], today: date) -> list[dict]:
    return [{"date": r["date"], "revenue": r.get("revenue", 0), "profit": r.get("profit", 0)} for r in rows]


def cache_response(ttl: int = 60):
    """Redis-backed response cache decorator. Falls back to no-cache on Redis failure."""

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            try:
                from app.auth.utils import get_redis_client

                redis = get_redis_client()
                store_id = g.current_user.get("store_id")
                cache_key = f"analytics:{store_id}:{request.path}:{request.query_string.decode()}"
                cached = redis.get(cache_key)
                if cached:
                    import json

                    from flask import jsonify, make_response

                    return make_response(jsonify(json.loads(cached)), 200)

                response = f(*args, **kwargs)

                try:
                    data = json.loads(response.get_data(as_text=True))
                    redis.setex(cache_key, ttl, json.dumps(data))
                except Exception:
                    pass

                return response
            except Exception:
                # Redis unavailable — just run without cache
                return f(*args, **kwargs)

        return decorated

    return decorator
