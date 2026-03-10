from flask import Blueprint

finance_bp = Blueprint("finance", __name__)

from . import routes  # Import routes to register them with the blueprint
