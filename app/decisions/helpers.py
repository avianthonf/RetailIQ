import collections
from datetime import date, timedelta


def get_zero_filled_history(raw_data: list[dict], today: date, window: int = 30, metric: str = "units_sold") -> list[float]:
    """
    Returns exactly `window` days of history ending yesterday (today - 1 day).
    Missing days are filled with 0.0.
    """
    start_date = today - timedelta(days=window)
    end_date = today - timedelta(days=1)

    # Fast map date -> value
    data_map = {row["date"]: float(row.get(metric, 0.0) or 0.0) for row in raw_data}

    filled = []
    curr = start_date
    while curr <= end_date:
        filled.append(data_map.get(curr, 0.0))
        curr += timedelta(days=1)

    return filled
