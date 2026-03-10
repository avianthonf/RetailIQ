from flask import Blueprint
from flask_restx import Api

market_intelligence_bp = Blueprint("market_intelligence", __name__)
market_api = Api(market_intelligence_bp, version="2.0", title="Market Intelligence API")

from . import routes, tasks, websocket

market_api.add_namespace(routes.api, path="")
