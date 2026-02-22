import time
import requests
from app import create_app, db
from app.models import User, Store, ForecastCache
from app.tasks.tasks import run_batch_forecasting
from app.auth.utils import generate_access_token

app = create_app()

with app.app_context():
    store = db.session.query(Store).first()
    if not store:
        store = Store(name='Perf Store')
        db.session.add(store)
        db.session.commit()
    import bcrypt
    pwd_hash = bcrypt.hashpw('password'.encode('utf-8'), bcrypt.gensalt(12)).decode('utf-8')
    user = db.session.query(User).filter_by(mobile_number='1234567890').first()
    if not user:
        user = User(mobile_number='1234567890', email='perf@test.com', store_id=store.store_id, role='owner', is_active=True, full_name='Perf Owner')
        user.password_hash = pwd_hash
        db.session.add(user)
        db.session.commit()
    else:
        user.password_hash = pwd_hash
        user.mobile_number = '1234567890'
        user.is_active = True
        db.session.commit()
    store_id = store.store_id
    user_id = user.user_id

    # Seed historical data for forecasting and dashboard
    from app.models import DailyStoreSummary, DailySkuSummary, Product
    from datetime import date as dt_date, timedelta
    today = dt_date.today()
    if not db.session.query(DailyStoreSummary).filter_by(store_id=store_id).first():
        print("Seeding history...")
        product = Product(name='Perf Product', store_id=store_id, sku_code='PERF', category_id=1, cost_price=10.0, selling_price=20.0, current_stock=100)
        db.session.add(product)
        db.session.commit()
        for i in range(70):
            d = today - timedelta(days=69 - i)
            db.session.add(DailyStoreSummary(store_id=store_id, date=d, revenue=100.0, profit=20.0, transaction_count=10))
            db.session.add(DailySkuSummary(store_id=store_id, product_id=product.product_id, date=d, revenue=100.0, profit=20.0, units_sold=5))
        db.session.commit()

    # Get actual token from the API server!
    resp = requests.post('http://localhost:5000/api/v1/auth/login', json={'mobile_number': '1234567890', 'password': 'password'})
    if resp.status_code == 200:
        token = resp.json()['data']['access_token']
        print("Logged in successfully via API.")
    else:
        print(f"Login failed: {resp.text}")
        token = "INVALID"

headers = {'Authorization': f'Bearer {token}'}

# Warmup request
requests.get('http://localhost:5000/api/v1/analytics/dashboard', headers=headers)

# Measure speed
start = time.time()
resp = requests.get('http://localhost:5000/api/v1/analytics/dashboard', headers=headers)
end = time.time()
duration = (end - start) * 1000
print(f"Dashboard GET /api/v1/analytics/dashboard speed: {duration:.2f}ms. Status: {resp.status_code}")
if resp.status_code != 200:
    print(resp.json())

with app.app_context():
    # Clear Redis lock
    from app.auth.utils import get_redis_client
    r = get_redis_client()
    keys = r.keys('lock:batch_forecast:*') + r.keys(f'lock:forecast:{store_id}:*')
    for k in keys:
        r.delete(k)
        
    before_count = db.session.query(ForecastCache).count()
    print(f"Forecast cache before batch job: {before_count}")
    from app.tasks.tasks import forecast_store
    forecast_store(store_id)
    after_count = db.session.query(ForecastCache).count()
    print(f"Forecast cache after batch job: {after_count}")
