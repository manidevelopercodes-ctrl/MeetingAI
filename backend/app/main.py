"""MeetingAI FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import meetings_router
from app.config import Settings, get_settings
from app.database import init_db
from app.schemas.meeting import HealthResponse

APP_NAME = "MeetingAI"
APP_VERSION = "0.1.0"

logger = logging.getLogger("meetingai")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Starting %s v%s", APP_NAME, APP_VERSION)
    logger.info(
        "Configuration: whisper=%s (%s), ollama=%s, embeddings=%s",
        settings.whisper_model,
        settings.whisper_device,
        settings.ollama_model,
        settings.embedding_model,
    )
    init_db()
    yield
    logger.info("Shutting down %s", APP_NAME)


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="A local AI meeting assistant: transcription, summaries and RAG chat.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meetings_router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness check that also reports which local models are configured."""
    return HealthResponse(
        status="healthy",
        app=APP_NAME,
        version=APP_VERSION,
        database=settings.database_url,
        whisper_model=settings.whisper_model,
        ollama_model=settings.ollama_model,
        embedding_model=settings.embedding_model,
    )
