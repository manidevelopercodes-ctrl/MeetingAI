"""Shared pytest fixtures.

Every test runs against a temporary SQLite database and a temporary audio
directory. The AI services (Whisper, Ollama, ChromaDB) are never touched:
tests inject fakes through the application's dependency overrides.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.meetings import (  # noqa: E402
    get_embedding_service,
    get_processor,
    get_rag_service,
)
from app.config import Settings, get_settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="sqlite://",
        audio_dir=tmp_path / "audio",
        chroma_dir=tmp_path / "chroma",
        max_upload_size_mb=1,
    )


@pytest.fixture
def db_session(settings: Settings):
    """In-memory SQLite session shared across the whole test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class FakeEmbeddingService:
    """Stands in for ChromaDB + sentence-transformers."""

    def __init__(self) -> None:
        self.indexed: dict[int, list] = {}
        self.deleted: list[int] = []
        self.hits: list[dict] = []

    def index_meeting(self, meeting_id: int, segments) -> int:
        self.indexed[meeting_id] = list(segments)
        return len(self.indexed[meeting_id])

    def query(self, meeting_id: int, question: str, top_k: int = 5) -> list[dict]:
        return self.hits[:top_k]

    def delete_meeting(self, meeting_id: int) -> None:
        self.deleted.append(meeting_id)


@pytest.fixture
def fake_embeddings() -> FakeEmbeddingService:
    return FakeEmbeddingService()


@pytest.fixture
def client(settings: Settings, db_session, fake_embeddings, tmp_path: Path):
    """TestClient wired to the temporary database and fake AI services."""
    settings.audio_dir.mkdir(parents=True, exist_ok=True)

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_embedding_service] = lambda: fake_embeddings

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def wav_bytes() -> bytes:
    """A tiny but structurally valid WAV payload."""
    return b"RIFF$\x00\x00\x00WAVEfmt " + b"\x00" * 32


def upload_meeting(
    client: TestClient,
    wav_bytes: bytes,
    title: str = "Sprint planning",
    description: str | None = "Weekly planning session",
    filename: str = "meeting.wav",
):
    data = {"title": title}
    if description is not None:
        data["description"] = description
    return client.post(
        "/api/meetings",
        data=data,
        files={"file": (filename, wav_bytes, "audio/wav")},
    )
