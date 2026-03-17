import os
import sys

# Ensure current dir is in path
sys.path.insert(0, os.getcwd())

from app import create_retail_app

print(f"DEBUG: create_retail_app imported from {create_retail_app.__module__}")

os.environ["FLASK_ENV"] = "development"
if "ENVIRONMENT" in os.environ:
    del os.environ["ENVIRONMENT"]
os.environ["SECRET_KEY"] = "test-secret"

config = {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}

print("DEBUG: Calling create_retail_app...")
app = create_retail_app(config)
print(f"DEBUG: app returned: {app}")

if app is None:
    print("FAILURE: app is None")
    sys.exit(1)
else:
    print("SUCCESS: app is not None")
