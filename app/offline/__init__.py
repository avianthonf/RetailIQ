from flask import Blueprint

offline_bp = Blueprint("offline", __name__)

from . import routes
