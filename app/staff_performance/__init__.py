from flask import Blueprint

staff_performance_bp = Blueprint("staff_performance", __name__)

from . import routes
