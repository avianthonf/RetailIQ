#!/usr/bin/env python3
"""
Test login directly
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import bcrypt

from app import create_app, db
from app.models import User


def test_login():
    app = create_app()

    with app.app_context():
        # Find the demo user
        demo_user = db.session.query(User).filter_by(mobile_number="9876543210").first()

        if not demo_user:
            print("Demo user not found!")
            return

        # Test password
        password = "demo123"
        is_valid = bcrypt.checkpw(password.encode("utf-8"), demo_user.password_hash.encode("utf-8"))

        print(f"Password check result: {is_valid}")

        if is_valid:
            print("✅ Password is correct!")
            # Try to generate token
            try:
                from app.auth.utils import generate_access_token

                token = generate_access_token(demo_user.user_id, demo_user.store_id, demo_user.role)
                print(f"✅ Token generated successfully: {token[:50]}...")
            except Exception as e:
                print(f"❌ Token generation failed: {e}")
        else:
            print("❌ Password is incorrect!")


if __name__ == "__main__":
    test_login()
