from flask import Blueprint

i18n_bp = Blueprint("i18n", __name__)

from . import routes  # noqa: E402, F401
