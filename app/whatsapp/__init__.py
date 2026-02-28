from flask import Blueprint

whatsapp_bp = Blueprint('whatsapp', __name__)

from . import routes  # noqa: E402, F401
