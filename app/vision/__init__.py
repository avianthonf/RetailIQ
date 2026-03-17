from flask import Blueprint

vision_bp = Blueprint("vision", __name__)

from . import routes  # noqa: E402, F401
