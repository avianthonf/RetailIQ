from flask import Blueprint

ai_v2_bp = Blueprint("ai_v2", __name__)

from . import routes  # noqa: E402, F401
