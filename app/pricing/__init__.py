from flask import Blueprint

pricing_bp = Blueprint("pricing", __name__)

from . import routes  # noqa: E402, F401
