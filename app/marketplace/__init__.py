from flask import Blueprint

marketplace_bp = Blueprint("marketplace", __name__)

from . import routes  # noqa: E402, F401
