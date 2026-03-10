from flask import Blueprint

developer_bp = Blueprint("developer", __name__)

from . import routes
