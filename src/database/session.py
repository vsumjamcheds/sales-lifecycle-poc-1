from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import settings
from src.database.models import Base


def _resolved_database_url() -> str:
    url = settings.database_url
    if url.startswith("sqlite:///./"):
        rel = url.removeprefix("sqlite:///./")
        abs_path = (settings.project_root / rel).resolve()
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{abs_path}"
    return url


_engine_url = _resolved_database_url()
engine = create_engine(
    _engine_url,
    connect_args={"check_same_thread": False} if _engine_url.startswith("sqlite") else {},
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
