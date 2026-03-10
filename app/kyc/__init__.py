from flask import Blueprint

kyc_bp = Blueprint("kyc", __name__)

from . import routes  # noqa: E402, F401
