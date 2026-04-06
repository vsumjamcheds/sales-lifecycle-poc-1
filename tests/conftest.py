from __future__ import annotations

import os

os.environ["PYTEST_RUNNING"] = "1"

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-skipped")
os.environ.setdefault("CHROMA_PATH", "./data/test_chroma")

from src.database.models import Base, HCP, Rep
from src.database.session import get_db
from src.api.main import app


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    r_ga = Rep(code="RepGA", territory_code="GA", weekly_visit_cap=10, max_new_targets_per_week=5, travel_friction_score=0.2)
    r_nj = Rep(code="RepNJ", territory_code="NJ", weekly_visit_cap=10, max_new_targets_per_week=5, travel_friction_score=0.2)
    session.add_all([r_ga, r_nj])
    session.flush()
    session.add_all(
        [
            HCP(display_name="Dr. GA One", specialty="Cardiology", territory_code="GA"),
            HCP(display_name="Dr. GA Two", specialty="Neurology", territory_code="GA"),
            HCP(display_name="Dr. NJ One", specialty="Orthopedics", territory_code="NJ"),
        ]
    )
    session.commit()

    def _get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db
    yield session
    app.dependency_overrides.clear()
    session.close()


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    return TestClient(app)
