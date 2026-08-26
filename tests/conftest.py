from collections.abc import Callable, Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.domain.models import Base
from app.scripts.seed import seed_database
from app.security import Role, create_access_token


@pytest.fixture(autouse=True)
def isolate_rag_provider(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Keep tests deterministic even when the developer .env enables DashScope."""
    monkeypatch.setenv("RAG_PROVIDER", "deterministic")
    monkeypatch.setenv("LLM_PROVIDER", "deterministic")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-at-least-thirty-two-bytes")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def seeded_db(db: Session) -> Session:
    seed_database(db, product_count=120, days=30, reset=True)
    return db


@pytest.fixture
def auth_headers() -> Callable[[Role, str], dict[str, str]]:
    def build(role: Role = "analyst", subject: str = "test-user") -> dict[str, str]:
        token = create_access_token(subject, {role}, Settings())
        return {"Authorization": f"Bearer {token}"}

    return build
