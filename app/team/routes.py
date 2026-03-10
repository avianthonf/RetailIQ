from flask import jsonify

from . import team_bp


@team_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify(success=True)
