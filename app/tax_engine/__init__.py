from flask import Blueprint

tax_engine_bp = Blueprint("tax_engine", __name__)

from . import routes  # noqa: E402, F401
