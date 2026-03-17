from flask import Blueprint

receipts_bp = Blueprint("receipts", __name__)
barcode_bp = Blueprint("barcodes", __name__)

from . import routes  # noqa: E402, F401
