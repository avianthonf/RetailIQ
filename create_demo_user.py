#!/usr/bin/env python3
"""
Create a demo user for testing the frontend
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import Store, User


def create_demo_user():
    app = create_app()

    with app.app_context():
        # Check if user already exists
        existing_user = db.session.query(User).filter_by(mobile_number="9876543210").first()
        if existing_user:
            print("Demo user already exists. Activating if needed...")
            if not existing_user.is_active:
                existing_user.is_active = True
                db.session.commit()
                print("Demo user activated!")
            return

        # Create demo user
        demo_user = User(
            mobile_number="9876543210",
            password_hash=generate_password_hash("demo123"),
            full_name="Demo User",
            email="demo@retailiq.com",
            role="owner",
            is_active=True,  # Skip OTP requirement
        )

        db.session.add(demo_user)
        db.session.flush()  # Get user_id

        # Create a store for the user
        demo_store = Store(
            store_name="Demo Store",
            owner_user_id=demo_user.user_id,
            email="demo@retailiq.com",
            phone="9876543210",
            address="123 Demo Street",
            city="Demo City",
            state="Demo State",
            country="Demo Country",
            postal_code="12345",
        )

        db.session.add(demo_store)
        demo_user.store_id = demo_store.store_id

        db.session.commit()

        print("✅ Demo user created successfully!")
        print("   Mobile: 9876543210")
        print("   Password: demo123")
        print(f"   User ID: {demo_user.user_id}")
        print(f"   Store ID: {demo_store.store_id}")


if __name__ == "__main__":
    create_demo_user()
