from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from celery import Celery
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import os
import logging
import redis as redis_lib
from sqlalchemy import text

db = SQLAlchemy()
limiter = Limiter(key_func=get_remote_address)
celery_app = Celery()

def _generate_rsa_keys():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private_pem.decode('utf-8'), public_pem.decode('utf-8')


def create_app(config=None):
    app = Flask(__name__)
    
    if config:
        app.config.update(config)

    is_production = os.environ.get('FLASK_ENV', 'development') == 'production'
    
    # Secret key (required in production)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', app.config.get('SECRET_KEY', 'dev-secret-key'))
    if is_production and app.config['SECRET_KEY'] in ('dev-secret-key', 'yoursecretkey', ''):
        raise RuntimeError('SECRET_KEY must be set to a strong random value in production')
    
    # Defaults — only applied when not already overridden by the caller
    if not app.config.get('SQLALCHEMY_DATABASE_URI'):
        app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://retailiq:retailiq@postgres:5432/retailiq')
    if not app.config.get('CELERY_BROKER_URL'):
        app.config['CELERY_BROKER_URL'] = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/1')

    # JWT RSA keys — mandatory in production, auto-generated only in dev/test
    jwt_private = os.environ.get('JWT_PRIVATE_KEY', '')
    jwt_public = os.environ.get('JWT_PUBLIC_KEY', '')
    if not app.config.get('JWT_PRIVATE_KEY'):
        if jwt_private and jwt_public:
            app.config['JWT_PRIVATE_KEY'] = jwt_private.replace('\\n', '\n')
            app.config['JWT_PUBLIC_KEY'] = jwt_public.replace('\\n', '\n')
        elif is_production:
            raise RuntimeError('JWT_PRIVATE_KEY and JWT_PUBLIC_KEY must be set in production')
        else:
            priv, pub = _generate_rsa_keys()
            app.config['JWT_PRIVATE_KEY'] = priv
            app.config['JWT_PUBLIC_KEY'] = pub
        
    app.config['RATELIMIT_STORAGE_URI'] = os.environ.get('REDIS_URL', 'redis://redis:6379/0')

    # Disable debug in production
    if is_production:
        app.config['DEBUG'] = False
        app.config['TESTING'] = False

    # CORS
    cors_origins = os.environ.get('CORS_ORIGINS', '')
    if cors_origins:
        CORS(app, origins=cors_origins.split(','), supports_credentials=True)
    elif not is_production:
        CORS(app)  # permissive in development only

    db.init_app(app)
    limiter.init_app(app)
    
    # Configure Celery (support both legacy upper-case and Celery native lower-case keys)
    celery_conf = {
        'broker_url': app.config.get('CELERY_BROKER_URL'),
        'result_backend': app.config.get('CELERY_RESULT_BACKEND', app.config.get('CELERY_BROKER_URL')),
        'task_always_eager': bool(app.config.get('task_always_eager', app.config.get('CELERY_ALWAYS_EAGER', False))),
        'task_eager_propagates': bool(app.config.get('task_eager_propagates', app.config.get('CELERY_EAGER_PROPAGATES_EXCEPTIONS', True))),
    }
    celery_app.conf.update(celery_conf)
    celery_app.conf.update(app.config)

    # Register blueprints (stubs)
    from .auth import auth_bp
    from .team import team_bp
    from .store import store_bp
    from .transactions import transactions_bp
    from .inventory import inventory_bp
    from .customers import customers_bp
    from app.analytics import analytics_bp
    from app.forecasting import forecasting_bp
    from app.decisions import decisions_bp
    from app.nlp import nlp_bp
    from .models import models_bp
    from .receipts import receipts_bp
    from .suppliers.routes import suppliers_bp
    from .staff_performance import staff_performance_bp
    from .offline import offline_bp
    from .loyalty import loyalty_bp
    from .gst import gst_bp
    from .whatsapp import whatsapp_bp
    from .chain import chain_bp

    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(team_bp, url_prefix='/api/v1/team')
    app.register_blueprint(store_bp, url_prefix='/api/v1/store')
    app.register_blueprint(transactions_bp, url_prefix='/api/v1/transactions')
    app.register_blueprint(inventory_bp, url_prefix='/api/v1/inventory')
    app.register_blueprint(customers_bp, url_prefix='/api/v1/customers')
    app.register_blueprint(analytics_bp, url_prefix='/api/v1/analytics')
    app.register_blueprint(forecasting_bp, url_prefix='/api/v1/forecasting')
    app.register_blueprint(forecasting_bp, url_prefix='/api/v1/forecast', name='forecasting_alias1')
    app.register_blueprint(forecasting_bp, url_prefix='/api/v1', name='forecasting_alias2')
    app.register_blueprint(decisions_bp, url_prefix='/api/v1/recommendations')
    app.register_blueprint(nlp_bp, url_prefix='/api/v1/query')
    app.register_blueprint(models_bp, url_prefix='/api/v1/models')
    app.register_blueprint(receipts_bp, url_prefix='/api/v1')
    app.register_blueprint(suppliers_bp, url_prefix='/api/v1')
    app.register_blueprint(staff_performance_bp, url_prefix='/api/v1/staff')
    app.register_blueprint(offline_bp, url_prefix='/api/v1/offline')
    app.register_blueprint(loyalty_bp, url_prefix='/api/v1')
    app.register_blueprint(gst_bp, url_prefix='/api/v1')
    app.register_blueprint(whatsapp_bp, url_prefix='/api/v1')
    app.register_blueprint(chain_bp, url_prefix='/api/v1/chain')

    def _check_health():
        """Run actual DB and Redis connectivity checks."""
        health = {'status': 'ok', 'db': 'unknown', 'redis': 'unknown'}
        http_status = 200

        # Check PostgreSQL
        try:
            with db.engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            health['db'] = 'ok'
        except Exception as exc:
            health['db'] = 'error'
            health['db_error'] = str(exc)
            health['status'] = 'degraded'
            http_status = 503
            app.logger.error('Health check: DB unreachable: %s', exc)

        # Check Redis
        try:
            redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
            r = redis_lib.Redis.from_url(redis_url, socket_timeout=3)
            r.ping()
            health['redis'] = 'ok'
        except Exception as exc:
            health['redis'] = 'error'
            health['redis_error'] = str(exc)
            health['status'] = 'degraded'
            http_status = 503
            app.logger.error('Health check: Redis unreachable: %s', exc)

        return jsonify(health), http_status

    # ALB / container orchestrator health probe (short path)
    @app.route('/health')
    def health_root():
        return _check_health()

    # API-namespaced health endpoint (backward compat)
    @app.route('/api/v1/health')
    def health_api():
        return _check_health()

    return app
