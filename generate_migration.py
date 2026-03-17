import os

from alembic import command
from alembic.config import Config

# Use a temporary sqlite file for autogeneration
os.environ["DATABASE_URL"] = "sqlite:///temp_migration.db"
alembic_cfg = Config("alembic.ini")
# Stamp the temp DB as being at the current head so we can generate the next revision
command.stamp(alembic_cfg, "head")

command.revision(alembic_cfg, message="align loan applications model drift", autogenerate=True)
print("Migration generated successfully.")
