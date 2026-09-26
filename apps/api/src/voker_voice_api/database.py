from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from voker_voice_api.config import get_settings


class Base(DeclarativeBase):
    """Base class for all Voker Voice persistence models."""


def _build_engine() -> Engine:
    database_url = get_settings().database_url
    engine_options: dict[str, object] = {"pool_pre_ping": True}
    if database_url.startswith("postgresql"):
        # Supabase's transaction pooler (PgBouncer) cannot safely reuse
        # psycopg's named prepared statements across pooled connections.
        engine_options["connect_args"] = {"prepare_threshold": None}
    return create_engine(database_url, **engine_options)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
