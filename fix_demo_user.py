#!/usr/bin/env python3
"""
Fix the demo user password
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import User


def fix_demo_user():
    app = create_app()

    with app.app_context():
        # Find the demo user
        demo_user = db.session.query(User).filter_by(mobile_number="9876543210").first()

        if not demo_user:
            print("Demo user not found!")
            return

        # Update password
        demo_user.password_hash = generate_password_hash("demo123")
        demo_user.is_active = True

        db.session.commit()

        print("✅ Demo user password updated!")
        print(f"   Mobile: {demo_user.mobile_number}")
        print(f"   Active: {demo_user.is_active}")
        print(f"   User ID: {demo_user.user_id}")


if __name__ == "__main__":
    fix_demo_user()
