"""Pydantic request/response models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.meeting import MeetingStatus


class MeetingCreate(BaseModel):
    """Metadata sent alongside the uploaded audio file."""

    title: str = Field(min_length=1, max_length=255)
    description: str | None = None


class MeetingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    audio_path: str | None = None
    duration: float | None = None
    status: MeetingStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class TranscriptSegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    speaker: str
    start_time: float
    end_time: float
    text: str


class TranscriptResponse(BaseModel):
    meeting_id: int
    status: MeetingStatus
    segments: list[TranscriptSegmentRead]


class ActionItem(BaseModel):
    task: str
    owner: str | None = None
    due_date: str | None = None


class SummaryPayload(BaseModel):
    """The structured object the LLM is asked to produce."""

    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)


class SummaryRead(SummaryPayload):
    meeting_id: int
    created_at: datetime | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class ChatSource(BaseModel):
    text: str
    speaker: str
    start_time: float
    end_time: float
    score: float | None = None


class ChatResponse(BaseModel):
    meeting_id: int
    question: str
    answer: str
    sources: list[ChatSource] = Field(default_factory=list)


class SearchHit(BaseModel):
    meeting_id: int
    meeting_title: str
    segment_id: int
    speaker: str
    start_time: float
    end_time: float
    text: str


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    database: str
    whisper_model: str
    ollama_model: str
    embedding_model: str
