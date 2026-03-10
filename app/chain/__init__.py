from flask import Blueprint

chain_bp = Blueprint("chain_bp", __name__)

from . import routes
