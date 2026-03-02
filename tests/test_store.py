import pytest

from app.database import db
from app.models import Category, Product, Store


def test_get_store_profile(client, owner_headers, test_store):
    response = client.get('/api/v1/store/profile', headers=owner_headers)
    assert response.status_code == 200
    data = response.json['data']
    assert data['store_name'] == test_store.store_name

def test_update_store_profile_and_seed_categories(client, owner_headers, test_store, app):
    # Ensure store has no type initially for the seed to work
    with app.app_context():
        store = db.session.get(Store, test_store.store_id)
        store.store_type = None
        # Remove any existing categories
        db.session.query(Category).delete()
        db.session.commit()

    payload = {
        "store_name": "Updated Supermart",
        "store_type": "grocery",
        "currency_symbol": "USD"
    }

    response = client.put('/api/v1/store/profile', headers=owner_headers, json=payload)
    assert response.status_code == 200
    assert response.json['data']['store_name'] == "Updated Supermart"

    # Verify categories were seeded
    with app.app_context():
        categories = db.session.query(Category).filter_by(store_id=test_store.store_id).all()
        assert len(categories) == 6 # 'Beverages', 'Dairy', 'Snacks', 'Staples', 'Household', 'Personal Care'
        names = [c.name for c in categories]
        assert 'Dairy' in names

def test_staff_cannot_update_profile(client, staff_headers):
    payload = {"store_name": "Hacked Store"}
    response = client.put('/api/v1/store/profile', headers=staff_headers, json=payload)
    assert response.status_code == 403

def test_create_category(client, owner_headers):
    payload = {"name": "Fresh Produce", "gst_rate": 5.0}
    response = client.post('/api/v1/store/categories', headers=owner_headers, json=payload)
    assert response.status_code == 201
    assert response.json['data']['name'] == "Fresh Produce"

def test_max_categories_limit(client, owner_headers, app, test_store):
    # Create 50 dummy categories
    with app.app_context():
        for i in range(50):
            db.session.add(Category(name=f"Cat {i}", store_id=test_store.store_id))
        db.session.commit()

    payload = {"name": "Overflow Category", "gst_rate": 0}
    response = client.post('/api/v1/store/categories', headers=owner_headers, json=payload)
    assert response.status_code == 400
    assert "Maximum of 50 categories" in response.json['message']

def test_get_categories(client, owner_headers, test_category):
    response = client.get('/api/v1/store/categories', headers=owner_headers)
    assert response.status_code == 200
    assert len(response.json['data']) >= 1
    assert response.json['data'][0]['name'] == test_category.name

def test_update_category(client, owner_headers, test_category):
    payload = {"name": "Updated Cat name", "gst_rate": 8.0}
    response = client.put(f'/api/v1/store/categories/{test_category.category_id}', headers=owner_headers, json=payload)
    assert response.status_code == 200
    assert response.json['data']['name'] == "Updated Cat name"

def test_delete_category_with_products(client, owner_headers, test_category, test_product):
    # Try deleting it while product is assigned
    response = client.delete(f'/api/v1/store/categories/{test_category.category_id}', headers=owner_headers)
    assert response.status_code == 422
    assert "assigned products" in response.json['message']

def test_delete_category_success(client, owner_headers, test_category, app):
    # Ensure no products are assigned
    with app.app_context():
        db.session.query(Product).delete()
        db.session.commit()

    response = client.delete(f'/api/v1/store/categories/{test_category.category_id}', headers=owner_headers)
    assert response.status_code == 200

    # Verify it is deactivated
    with app.app_context():
        cat = db.session.get(Category, test_category.category_id)
        assert cat.is_active is False

def test_update_tax_config(client, owner_headers, test_category, app):
    # create a second category
    with app.app_context():
        cat2 = Category(store_id=test_category.store_id, name="Cat 2", gst_rate=12)
        db.session.add(cat2)
        db.session.commit()
        cat2_id = cat2.category_id

    payload = {
        "taxes": [
            {"category_id": test_category.category_id, "gst_rate": 18.0},
            {"category_id": cat2_id, "gst_rate": 5.0} # this might be 0 randomly based on tests so map it explicitly
        ]
    }

    response = client.put('/api/v1/store/tax-config', headers=owner_headers, json=payload)
    assert response.status_code == 200

    # Verify rates
    with app.app_context():
        cat1 = db.session.get(Category, test_category.category_id)
        c2 = db.session.get(Category, cat2_id)
        assert cat1.gst_rate == 18.0
        assert c2.gst_rate == 5.0
