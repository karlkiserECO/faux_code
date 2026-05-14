"""SQLite session management via SQLModel."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from ..settings import get_settings

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        db_path: Path = settings.data_dir / "faux.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path.resolve()}"
        _engine = create_engine(
            url,
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _engine


def init_db() -> None:
    from . import models  # noqa: F401 ensure tables registered

    SQLModel.metadata.create_all(_get_engine())


def get_session() -> Iterator[Session]:
    with Session(_get_engine()) as session:
        yield session
