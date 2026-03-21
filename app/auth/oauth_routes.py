import bcrypt
from flask import Blueprint, g, jsonify, redirect, request

from app import db, limiter
from app.auth.decorators import require_auth
from app.auth.oauth import (
    generate_auth_code,
    generate_oauth_tokens,
    refresh_oauth_token,
    verify_auth_code,
    verify_client_credentials,
)
from app.auth.utils import format_response
from app.models import Developer, DeveloperApplication, User

oauth_bp = Blueprint("oauth", __name__)


@oauth_bp.route("/authorize", methods=["GET", "POST"])
@require_auth
def authorize():
    """
    Authorization endpoint where the user (merchant) grants permission to the app.
    """
    client_id = request.args.get("client_id")
    redirect_uri = request.args.get("redirect_uri")
    scope = request.args.get("scope", "")
    state = request.args.get("state")

    if not client_id or not redirect_uri:
        return format_response(False, error={"code": "INVALID_REQUEST", "message": "Missing client_id or redirect_uri"})
    app = db.session.query(DeveloperApplication).filter_by(client_id=client_id).first()
    if not app:
        return format_response(success=False, error={"code": "INVALID_CLIENT", "message": "Invalid client_id"})
    # In a real app, we would verify redirect_uri against app.redirect_uris
    # And show a consent screen (render_template).
    # For this implementation, we'll auto-approve if it's a POST or just a simplified GET.

    if request.method == "GET":
        return format_response(
            True,
            data={
                "client_id": client_id,
                "app_name": app.name,
                "description": app.description,
                "redirect_uri": redirect_uri,
                "scopes": scope.split(" "),
                "state": state,
                "message": "Please POST to this endpoint with 'confirm=true' to authorize.",
            },
        )

    # POST processing
    confirm = request.form.get("confirm") or (request.json.get("confirm") if request.is_json else None)
    if str(confirm).lower() != "true":
        return format_response(success=False, error={"code": "ACCESS_DENIED", "message": "User denied access"})
    user_id = g.current_user["user_id"]
    code = generate_auth_code(client_id, user_id, scope.split(" "))

    # Redirect back to developer app
    separator = "&" if "?" in redirect_uri else "?"
    redirect_url = f"{redirect_uri}{separator}code={code}"
    if state:
        redirect_url += f"&state={state}"

    if request.is_json:
        return format_response(
            True,
            data={
                "redirect_url": redirect_url,
                "code": code,
                "state": state,
            },
        )

    return redirect(redirect_url)


@oauth_bp.route("/token", methods=["POST"])
def token():
    """
    Token exchange endpoint (Authorization Code or Client Credentials).
    """
    if request.is_json:
        data = request.json
    else:
        data = request.form

    grant_type = data.get("grant_type")
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")

    if not grant_type:
        return jsonify({"error": "invalid_request", "error_description": "Missing grant_type"}), 400

    # Verify Client Credentials for all grant types
    app_obj = verify_client_credentials(client_id, client_secret)
    if not app_obj:
        return jsonify({"error": "invalid_client", "error_description": "Invalid client credentials"}), 401

    if grant_type == "authorization_code":
        code = data.get("code")
        if not code:
            return jsonify({"error": "invalid_request", "error_description": "Missing code"}), 400
        auth_data = verify_auth_code(code, client_id)
        if not auth_data:
            return jsonify({"error": "invalid_grant", "error_description": "Invalid or expired code"}), 401
        tokens = generate_oauth_tokens(app_obj.id, user_id=auth_data["user_id"], scopes=auth_data["scopes"])
        return jsonify(tokens)

    elif grant_type == "client_credentials":
        # Scopes from request or default to app scopes
        req_scopes = data.get("scope")
        scopes = req_scopes.split(" ") if req_scopes else app_obj.scopes

        tokens = generate_oauth_tokens(app_obj.id, scopes=scopes)
        return jsonify(tokens)

    elif grant_type == "refresh_token":
        rt = data.get("refresh_token")
        if not rt:
            return jsonify({"error": "invalid_request", "error_description": "Missing refresh_token"}), 400
        tokens = refresh_oauth_token(rt, client_id, client_secret)
        if not tokens:
            return jsonify({"error": "invalid_grant", "error_description": "Invalid or expired refresh token"}), 401
        return jsonify(tokens)

    return jsonify({"error": "unsupported_grant_type"}), 400
