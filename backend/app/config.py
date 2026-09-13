"""Application settings, loaded from environment variables / .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/ -> project root
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime configuration. Every value can be overridden via the environment."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Storage
    database_url: str = "sqlite:///./meetingai.db"
    audio_dir: Path = PROJECT_ROOT / "storage" / "audio"
    chroma_dir: Path = PROJECT_ROOT / "data" / "chroma"

    # Transcription
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout_seconds: int = 300

    # Embeddings / RAG
    embedding_model: str = "all-MiniLM-L6-v2"
    chroma_collection: str = "meeting_transcripts"
    rag_chunk_size: int = 5          # transcript segments per chunk
    rag_chunk_overlap: int = 1       # segments of overlap between chunks
    rag_top_k: int = 5               # chunks retrieved per question

    # Uploads
    max_upload_size_mb: int = 200
    allowed_audio_extensions: str = "mp3,wav,m4a,mp4,webm"

    # Misc
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def allowed_extensions(self) -> set[str]:
        """Allowed upload extensions, normalised to lowercase with a leading dot."""
        return {
            "." + ext.strip().lstrip(".").lower()
            for ext in self.allowed_audio_extensions.split(",")
            if ext.strip()
        }

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance, used as a FastAPI dependency."""
    settings = Settings()
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    return settings
