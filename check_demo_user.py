#!/usr/bin/env python3
"""
Check the demo user details
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import Store, User


def check_demo_user():
    app = create_app()

    with app.app_context():
        # Find the demo user
        demo_user = db.session.query(User).filter_by(mobile_number="9876543210").first()

        if not demo_user:
            print("Demo user not found!")
            return

        print("Demo User Details:")
        print(f"  User ID: {demo_user.user_id}")
        print(f"  Mobile: {demo_user.mobile_number}")
        print(f"  Email: {demo_user.email}")
        print(f"  Full Name: {demo_user.full_name}")
        print(f"  Role: {demo_user.role}")
        print(f"  Store ID: {demo_user.store_id}")
        print(f"  Is Active: {demo_user.is_active}")
        print(f"  Created: {demo_user.created_at}")

        # Check if store exists
        if demo_user.store_id:
            store = db.session.query(Store).filter_by(store_id=demo_user.store_id).first()
            if store:
                print("\nStore Details:")
                print(f"  Store ID: {store.store_id}")
                print(f"  Store Name: {store.store_name}")
            else:
                print(f"\nStore with ID {demo_user.store_id} not found!")


if __name__ == "__main__":
    check_demo_user()
