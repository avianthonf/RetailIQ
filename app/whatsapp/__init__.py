from flask import Blueprint

whatsapp_bp = Blueprint("whatsapp", __name__)

from . import routes  # noqa: E402, F401
from .client import get_redis_client
