"""
Internationalization and Localization API Routes
"""

from flask import g, request

from ..auth.decorators import require_auth
from ..auth.utils import format_response
from . import i18n_bp
from .engine import get_translated_string


@i18n_bp.route("/i18n/translations", methods=["GET"])
def get_translations():
    """Fetch translation catalog for a specific module and language."""
    locale = request.args.get("locale", "en")
    module = request.args.get("module")

    from .. import db
    from ..models.expansion_models import Translation, TranslationKey

    query = (
        db.session.query(TranslationKey.key, Translation.value)
        .join(Translation, Translation.key_id == TranslationKey.id)
        .filter(Translation.locale == locale, Translation.is_approved == True)
    )

    if module:
        query = query.filter(TranslationKey.module == module)

    results = query.all()

    catalog = {key: value for key, value in results}

    return format_response(success=True, data={"locale": locale, "catalog": catalog})


@i18n_bp.route("/i18n/currencies", methods=["GET"])
def get_supported_currencies():
    """List actively supported currencies with formatting info."""
    from .. import db
    from ..models.expansion_models import SupportedCurrency

    currencies = db.session.query(SupportedCurrency).filter_by(is_active=True).all()

    data = [
        {
            "code": c.code,
            "name": c.name,
            "symbol": c.symbol,
            "decimal_places": c.decimal_places,
            "symbol_position": c.symbol_position,
        }
        for c in currencies
    ]

    return format_response(success=True, data=data)


@i18n_bp.route("/i18n/countries", methods=["GET"])
def get_supported_countries():
    """List countries RetailIQoperates in with locale defaults."""
    from .. import db
    from ..models.expansion_models import Country

    countries = db.session.query(Country).filter_by(is_active=True).all()

    data = [
        {
            "code": c.code,
            "name": c.name,
            "default_currency": c.default_currency,
            "default_locale": c.default_locale,
            "timezone": c.timezone,
            "phone_code": c.phone_code,
            "date_format": c.date_format,
        }
        for c in countries
    ]

    return format_response(success=True, data=data)
