from flask import Blueprint

einvoicing_bp = Blueprint("einvoicing", __name__)

from . import routes  # noqa: E402, F401
