from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import Settings


class Base(DeclarativeBase):
    pass


def _prepare_sqlite_directory(database_url: str) -> None:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix) or database_url.endswith(":memory:"):
        return
    database_path = Path(database_url.removeprefix(prefix))
    database_path.parent.mkdir(parents=True, exist_ok=True)


def build_engine(settings: Settings) -> Engine:
    _prepare_sqlite_directory(settings.database_url)
    connect_args = (
        {"check_same_thread": False}
        if settings.database_url.startswith("sqlite")
        else {}
    )
    return create_engine(settings.database_url, connect_args=connect_args)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def session_dependency(
    session_factory: sessionmaker[Session],
) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()

