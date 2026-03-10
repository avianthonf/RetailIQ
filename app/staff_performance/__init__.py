from flask import Blueprint

staff_performance_bp = Blueprint("staff_performance", __name__, url_prefix="/api/v1/staff")

from . import routes
