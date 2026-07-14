from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker[Session]] = None
_schema_initialized = False


def database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def sqlalchemy_url() -> str:
    url = database_url()
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def is_enabled() -> bool:
    return bool(database_url())


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = sqlalchemy_url()
        if not url:
            raise RuntimeError("DATABASE_URL is not configured")
        _engine = create_engine(url, pool_pre_ping=True, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, future=True)
    return _session_factory


def init_db() -> None:
    global _schema_initialized
    if _schema_initialized:
        return
    from app.db.base import Base
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())
    _schema_initialized = True


@contextmanager
def session_scope() -> Iterator[Session]:
    init_db()
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
