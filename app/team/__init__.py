from flask import Blueprint

team_bp = Blueprint('team', __name__)

from . import routes
