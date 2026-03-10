from flask import Blueprint

gst_bp = Blueprint("gst", __name__)

from . import routes  # noqa: E402, F401
