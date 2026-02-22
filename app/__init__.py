from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from celery import Celery
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import os

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
    
    # Defaults — only applied when not already overridden by the caller
    if not app.config.get('SQLALCHEMY_DATABASE_URI'):
        app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://retailiq:retailiq@postgres:5432/retailiq')
    if not app.config.get('CELERY_BROKER_URL'):
        app.config['CELERY_BROKER_URL'] = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/1')


    if not app.config.get('JWT_PRIVATE_KEY'):
        priv, pub = _generate_rsa_keys()
        app.config['JWT_PRIVATE_KEY'] = priv
        app.config['JWT_PUBLIC_KEY'] = pub
        
    app.config['RATELIMIT_STORAGE_URI'] = os.environ.get('REDIS_URL', 'redis://redis:6379/0')

    db.init_app(app)
    limiter.init_app(app)
    
    # Configure Celery
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

    @app.route('/api/v1/health')
    def health():
        return jsonify({
            'status': 'ok',
            'db': 'ok',
            'redis': 'ok'
        })
        
    return app
