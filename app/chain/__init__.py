from flask import Blueprint

chain_bp = Blueprint("chain", __name__)

from . import routes  # noqa: E402, F401
