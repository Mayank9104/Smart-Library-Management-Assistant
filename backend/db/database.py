import os
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import StaticPool
from backend.config import settings

Base = declarative_base()

_engines = {}


def _resolve_db_url() -> str:
    """Resolve the SQLite database URL from settings safely."""
    if getattr(settings, "environment", "development") == "test":
        return "sqlite:///:memory:"
    if hasattr(settings, "database_url") and settings.database_url:
        return settings.database_url
    if hasattr(settings, "sqlite_db_path") and settings.sqlite_db_path:
        db_path = settings.sqlite_db_path
        if db_path.startswith("sqlite:"):
            return db_path
        return f"sqlite:///{db_path}"
    return "sqlite:///./data/library.db"


def get_engine():
    """Return a SQLAlchemy engine for the current environment."""
    db_url = _resolve_db_url()
    if db_url not in _engines:
        if db_url == "sqlite:///:memory:":
            _engines[db_url] = create_engine(
                db_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            if db_url.startswith("sqlite:///"):
                db_path = db_url.replace("sqlite:///", "")
                db_dir = os.path.dirname(db_path)
                if db_dir:
                    os.makedirs(db_dir, exist_ok=True)
            _engines[db_url] = create_engine(
                db_url,
                connect_args={"check_same_thread": False}
                if "sqlite" in db_url
                else {},
            )
    return _engines[db_url]


# Module-level exports expected by backend/db/__init__.py
engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all database tables registered on Base metadata."""
    import backend.models  # noqa: F401
    current_engine = get_engine()
    Base.metadata.create_all(bind=current_engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a SQLAlchemy database session with initialized tables."""
    init_db()
    current_engine = get_engine()
    CurrentSession = sessionmaker(autocommit=False, autoflush=False, bind=current_engine)
    db = CurrentSession()
    try:
        yield db
    finally:
        db.close()
