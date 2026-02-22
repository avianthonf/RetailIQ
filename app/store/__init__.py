from app.store.routes import store_bp

def init_app(app):
    app.register_blueprint(store_bp)
