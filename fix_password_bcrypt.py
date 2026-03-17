#!/usr/bin/env python3
"""
Fix the demo user password with bcrypt
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import bcrypt

from app import create_app, db
from app.models import User


def fix_password():
    app = create_app()

    with app.app_context():
        # Find the demo user
        demo_user = db.session.query(User).filter_by(mobile_number="9876543210").first()

        if not demo_user:
            print("Demo user not found!")
            return

        # Generate bcrypt hash
        password = "demo123"
        salt = bcrypt.gensalt()
        password_hash = bcrypt.hashpw(password.encode("utf-8"), salt)

        # Update user
        demo_user.password_hash = password_hash.decode("utf-8")
        demo_user.is_active = True

        db.session.commit()

        print("✅ Password updated with bcrypt!")
        print(f"  New hash: {demo_user.password_hash[:50]}...")

        # Test it
        test_valid = bcrypt.checkpw(password.encode("utf-8"), demo_user.password_hash.encode("utf-8"))
        print(f"  Password check: {test_valid}")


if __name__ == "__main__":
    fix_password()
