import collections
import os
import sys
from datetime import date, timedelta

import pandas as pd

# Need to append the app path to sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.forecasting.engine import run_forecast

# Mock history
dates = [date.today() - timedelta(days=90) + timedelta(days=i) for i in range(90)]
values = [15.0] * 90

events = [
    {
        "id": "event_123",
        "event_name": "Diwali Sale",
        "start_date": date.today() + timedelta(days=2),
        "end_date": date.today() + timedelta(days=4),
        "expected_impact_pct": 40.0,
        "event_type": "FESTIVAL",
    }
]

result = run_forecast(dates, values, horizon=14, events=events)
print("Model returned:", result.model_type)
