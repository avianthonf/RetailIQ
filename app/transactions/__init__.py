from flask import Blueprint

transactions_bp = Blueprint("transactions", __name__)

from . import routes  # noqa: E402, F401
