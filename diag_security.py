import os

from flask import Flask

from app.utils.security import check_production_readiness

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://retailiq:retailiq@localhost:5432/retailiq"
app.config["SECRET_KEY"] = "strong-random-string"
app.config["ENVIRONMENT"] = "production"

with app.app_context():
    try:
        check_production_readiness()
    except RuntimeError as e:
        print(f"EXCEPTION_MESSAGE: {str(e)}")
    except Exception as e:
        print(f"OTHER_EXCEPTION: {type(e)} {str(e)}")
