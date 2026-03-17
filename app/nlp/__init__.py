from flask import Blueprint

nlp_bp = Blueprint("nlp", __name__)

from . import routes  # noqa: E402, F401
