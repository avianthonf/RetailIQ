from flask import Blueprint

store_bp = Blueprint("store", __name__)

from . import routes  # noqa: E402, F401
