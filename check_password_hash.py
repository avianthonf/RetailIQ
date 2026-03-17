#!/usr/bin/env python3
"""
Check password hash format
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User


def check_hash():
    app = create_app()

    with app.app_context():
        # Find the demo user
        demo_user = db.session.query(User).filter_by(mobile_number="9876543210").first()

        if not demo_user:
            print("Demo user not found!")
            return

        print(f"Password hash: {demo_user.password_hash}")
        print(f"Hash starts with bcrypt: {demo_user.password_hash.startswith('$2')}")

        # Check if it's werkzeug format
        if demo_user.password_hash.startswith("pbkdf2:"):
            print("This is Werkzeug PBKDF2 format")
        elif demo_user.password_hash.startswith("$2"):
            print("This is bcrypt format")
        else:
            print("Unknown hash format")


if __name__ == "__main__":
    check_hash()
