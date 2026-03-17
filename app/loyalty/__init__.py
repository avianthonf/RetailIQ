from flask import Blueprint

loyalty_bp = Blueprint("loyalty", __name__)
credit_bp = Blueprint("credit", __name__)

from . import routes  # noqa: E402, F401
