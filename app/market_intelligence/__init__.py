from flask import Blueprint

market_intelligence_bp = Blueprint("market_intelligence", __name__)

from . import routes  # noqa: E402, F401
