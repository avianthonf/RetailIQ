from flask import Blueprint

api_v2_bp = Blueprint("api_v2", __name__)

from . import routes
