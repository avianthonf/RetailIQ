"""
Locale Engine for RetailIQ

Handles:
- Language translations
- Multi-currency formatting
- Date/Time formatting
- Number formatting (e.g. 1,234.56 vs 1.234,56)
"""

from datetime import date, datetime
from typing import Any, Dict

from babel.dates import format_date, format_datetime, format_time
from babel.numbers import format_currency, format_decimal
from cachetools import TTLCache, cached

from .. import db
from ..models.expansion_models import SupportedCurrency, Translation

# Cache translations for 1 hour to avoid DB hits on every string
translation_cache = TTLCache(maxsize=10000, ttl=3600)


@cached(translation_cache)
def get_translated_string(key: str, locale: str, fallback: str = "") -> str:
    """Fetch a translated string from the DB, falling back to English or the provided string."""
    translation = db.session.query(Translation).filter(
        Translation.key_id == db.text(f"(SELECT id FROM translation_keys WHERE key = '{key}')"),
        Translation.locale == locale,
        Translation.is_approved == True
    ).first()

    if translation:
        return translation.value

    # Fallback to English
    if locale != "en":
        en_translation = db.session.query(Translation).filter(
            Translation.key_id == db.text(f"(SELECT id FROM translation_keys WHERE key = '{key}')"),
            Translation.locale == "en",
            Translation.is_approved == True
        ).first()
        if en_translation:
            return en_translation.value

    return fallback or key


def t(key: str, locale: str, **kwargs) -> str:
    """Translate and interpolate a string."""
    text = get_translated_string(key, locale)
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text


def format_money(amount: float, currency_code: str, locale: str) -> str:
    """Format monetary values according to standard locale and currency rules."""
    return format_currency(amount, currency_code, locale=locale)


def format_number(number: float, locale: str) -> str:
    """Format a decimal/float number according to locale (e.g., 1.234,56 vs 1,234.56)."""
    return format_decimal(number, locale=locale)


def format_locale_date(dt: datetime | date, locale: str, format: str = "medium") -> str:
    """Format a date according to the user's locale."""
    return format_date(dt, format=format, locale=locale)


def format_locale_datetime(dt: datetime, locale: str, format: str = "medium", tzinfo=None) -> str:
    """Format a datetime according to the user's locale and timezone."""
    return format_datetime(dt, format=format, tzinfo=tzinfo, locale=locale)
