from flask import Blueprint

receipts_bp = Blueprint('receipts', __name__)

from . import routes  # noqa: E402, F401
