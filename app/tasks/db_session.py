"""
Standalone SQLAlchemy session factory for Celery tasks.

Tasks run outside a Flask request context.
"""

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_engine = None
_Session = None


def _get_session_factory():
    global _engine, _Session
    if _Session is None:
        db_url = os.environ.get("DATABASE_URL", "postgresql://retailiq:retailiq@postgres:5432/retailiq")
        kwargs = {"pool_pre_ping": True}
        if not db_url.startswith("sqlite"):
            kwargs["pool_size"] = 5
            kwargs["max_overflow"] = 10
        _engine = create_engine(db_url, **kwargs)
        _Session = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    return _Session


@contextmanager
def task_session(isolation_level=None):
    """
    Yield a SQLAlchemy Session for use inside a Celery task.
    """
    Session = _get_session_factory()
    session = Session()
    if isolation_level:
        session.connection(execution_options={"isolation_level": isolation_level})
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
