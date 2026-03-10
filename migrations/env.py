import os
import sys
from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context
from sqlalchemy import engine_from_config, pool

# Add project root to path so app models can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import Base  # noqa
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(sa.sql.elements.TextClause, "sqlite")
def compile_text_sqlite(element, compiler, **kw):
    text = element.text
    if "now()" in text.lower():
        text = text.replace("now()", "CURRENT_TIMESTAMP")
    return text


from sqlalchemy.types import UUID as SA_UUID


@compiles(SA_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "TEXT"


# Patch UUID process_bind_param for SQLite strings (safely)
def patch_uuid_if_possible():
    try:
        from sqlalchemy.types import UUID as SA_UUID

        # Some versions might have it differently, let's be careful
        if hasattr(SA_UUID, "bind_processor"):
            orig_bind = SA_UUID.bind_processor

            def patched_bind(self, dialect):
                if dialect.name == "sqlite":
                    return lambda value: value  # Just return the string
                return orig_bind(self, dialect)

            SA_UUID.bind_processor = patched_bind
    except Exception:
        pass


patch_uuid_if_possible()

# Alembic Config object
config = context.config

# Set database URL from environment variable if available
db_url = os.environ.get("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# Setup logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True if url and url.startswith("sqlite") else False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if connection.dialect.name == "sqlite":
            from alembic.operations import Operations

            Operations.bulk_insert = lambda *a, **kw: None
            Operations.create_foreign_key = lambda *a, **kw: None
            Operations.drop_constraint = lambda *a, **kw: None
            Operations.create_unique_constraint = lambda *a, **kw: None

            orig_invoke = Operations.invoke

            def patched_invoke(self, op):
                # Aggressively skip unsupported SQLite DDL
                op_name = type(op).__name__
                sql_str = ""
                if hasattr(op, "sqltext"):
                    sql_str = str(op.sqltext).upper()
                elif hasattr(op, "column_name"):
                    sql_str = "ALTER COLUMN " + str(op.column_name).upper()

                if "EXTENSION" in sql_str:
                    return None
                if "ALTER COLUMN" in sql_str or "TYPE" in sql_str and "ALTER TABLE" in sql_str:
                    return None
                if "DROP CONSTRAINT" in sql_str:
                    return None
                if "ExecuteSQLOp" in op_name and ("ALTER COLUMN" in sql_str or "TYPE" in sql_str):
                    return None

                try:
                    return orig_invoke(self, op)
                except Exception as e:
                    if "sqlite" in str(e).lower():
                        return None
                    raise e

            Operations.invoke = patched_invoke

        def include_object(object, name, type_, reflected, compare_to):
            if type_ == "index":
                return False
            return True

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True if connection.dialect.name == "sqlite" else False,
            compare_type=False if connection.dialect.name == "sqlite" else True,
            compare_server_default=False if connection.dialect.name == "sqlite" else True,
            include_object=include_object if connection.dialect.name == "sqlite" else None,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
