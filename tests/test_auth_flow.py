import bcrypt

from app import db
from app.models import Store, User


class FakeRedis:
    def __init__(self):
        self.data = {}

    def setex(self, key, ttl, value):
        self.data[key] = str(value)

    def get(self, key):
        return self.data.get(key)

    def delete(self, key):
        self.data.pop(key, None)


def test_refresh_token_rotation_and_logout(client, app, monkeypatch):
    fake = FakeRedis()

    monkeypatch.setattr("app.auth.utils.get_redis_client", lambda: fake)
    monkeypatch.setattr("app.auth.routes.get_redis_client", lambda: fake)

    with app.app_context():
        store = Store(store_name="Auth Test Store", store_type="grocery")
        db.session.add(store)
        db.session.flush()

        password_hash = bcrypt.hashpw(b"secret123", bcrypt.gensalt(12)).decode("utf-8")
        user = User(
            mobile_number="9111111111",
            password_hash=password_hash,
            full_name="Auth User",
            role="owner",
            store_id=store.store_id,
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"mobile_number": "9111111111", "password": "secret123"},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.get_json()["data"]

    refresh_token = login_data["refresh_token"]
    assert fake.get(f"refresh_token:{refresh_token}") is not None

    refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 200
    rotated = refresh_resp.get_json()["data"]["refresh_token"]

    assert fake.get(f"refresh_token:{refresh_token}") is None
    assert fake.get(f"refresh_token:{rotated}") is not None

    access = refresh_resp.get_json()["data"]["access_token"]
    logout_resp = client.delete(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
        json={"refresh_token": rotated},
    )
    assert logout_resp.status_code == 200
    assert fake.get(f"refresh_token:{rotated}") is None

    replay_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": rotated})
    assert replay_resp.status_code == 401


def test_verify_otp_returns_auth_tokens(client, app, monkeypatch):
    """After registration + OTP verification the endpoint returns JWT tokens (auto-login)."""
    fake = FakeRedis()

    monkeypatch.setattr("app.auth.utils.get_redis_client", lambda: fake)
    monkeypatch.setattr("app.auth.routes.get_redis_client", lambda: fake)

    # 1. Register a new user
    register_resp = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "OTP Test User",
            "mobile_number": "9222222222",
            "password": "secret123",
            "store_name": "OTP Store",
            "email": "otp_test@example.com",
        },
    )
    assert register_resp.status_code == 201

    # Grab the OTP from the fake redis
    otp = fake.get("otp:9222222222")
    assert otp is not None

    # 2. Verify OTP
    verify_resp = client.post(
        "/api/v1/auth/verify-otp",
        json={
            "mobile_number": "9222222222",
            "otp": otp,
        },
    )
    assert verify_resp.status_code == 200

    data = verify_resp.get_json()
    assert data["success"] is True

    # 3. Verify the response contains auth tokens (auto-login)
    verify_data = data["data"]
    assert "access_token" in verify_data
    assert "refresh_token" in verify_data
    assert "user_id" in verify_data
    assert "role" in verify_data
    assert verify_data["role"] == "owner"
    assert "store_id" in verify_data
    assert verify_data["store_id"] is not None

    # 4. The access token should be valid for authenticated requests
    access = verify_data["access_token"]
    # Try hitting a protected endpoint (e.g. logout)
    protected_resp = client.delete(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
        json={"refresh_token": verify_data["refresh_token"]},
    )
    assert protected_resp.status_code == 200
