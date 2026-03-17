from flask import Blueprint

suppliers_bp = Blueprint("suppliers", __name__)
po_bp = Blueprint("purchase_orders", __name__)

from . import routes  # noqa: E402, F401
