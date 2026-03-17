import os
import sys

# Ensure the app is importable
sys.path.insert(0, os.getcwd())

from app import create_app


def dump_routes():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    print("\n" + "=" * 80)
    print("RETAILIQ APPLICATION URL MAP")
    print("=" * 80)

    # Sort by rule path
    rules = sorted(app.url_map.iter_rules(), key=lambda r: str(r))

    for rule in rules:
        methods = ", ".join(sorted(rule.methods - {"OPTIONS", "HEAD"}))
        print(f"{str(rule):<50} | {methods:<20} | {rule.endpoint}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    dump_routes()
