from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.config import settings

# Ensure ./data directory exists if using local SQLite file
if settings.sqlite_db_url.startswith("sqlite:///./"):
    db_file_path = Path(settings.sqlite_db_url.replace("sqlite:///./", ""))
    db_file_path.parent.mkdir(parents=True, exist_ok=True)

connect_args = (
    {"check_same_thread": False}
    if settings.sqlite_db_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.sqlite_db_url,
    connect_args=connect_args,
    future=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all database tables registered on Base.metadata."""
    import backend.models.library_models  # noqa: F401
    Base.metadata.create_all(bind=engine)
