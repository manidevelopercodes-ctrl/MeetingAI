"""Meeting REST endpoints."""

import json
import logging
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal, get_db
from app.models.meeting import Meeting, MeetingStatus, MeetingSummary, TranscriptSegment
from app.schemas.meeting import (
    ChatRequest,
    ChatResponse,
    MeetingRead,
    SearchHit,
    SearchResponse,
    SummaryRead,
    TranscriptResponse,
)
from app.services.embeddings import EmbeddingService
from app.services.meeting_processor import MeetingProcessor
from app.services.rag import RagError, RagService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meetings", tags=["meetings"])

# Statuses in which a new processing run must not be started.
BUSY_STATUSES = {
    MeetingStatus.TRANSCRIBING,
    MeetingStatus.SUMMARIZING,
    MeetingStatus.INDEXING,
}


# -- dependencies -------------------------------------------------------
# Declared as functions so tests can replace them via app.dependency_overrides.


def get_processor(settings: Settings = Depends(get_settings)) -> MeetingProcessor:
    return MeetingProcessor(settings)


def get_rag_service(settings: Settings = Depends(get_settings)) -> RagService:
    return RagService(settings)


def get_embedding_service(settings: Settings = Depends(get_settings)) -> EmbeddingService:
    return EmbeddingService(settings)


def _get_meeting_or_404(db: Session, meeting_id: int) -> Meeting:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail=f"Meeting {meeting_id} was not found.")
    return meeting


# -- endpoints ----------------------------------------------------------


@router.post("", response_model=MeetingRead, status_code=201)
async def create_meeting(
    title: str = Form(...),
    description: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Meeting:
    """Upload an audio recording and create a meeting in UPLOADED status."""
    if not title.strip():
        raise HTTPException(status_code=400, detail="A meeting title is required.")

    original_name = file.filename or ""
    extension = Path(original_name).suffix.lower()
    if extension not in settings.allowed_extensions:
        allowed = ", ".join(sorted(ext.lstrip(".") for ext in settings.allowed_extensions))
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported audio format '{extension or original_name}'. "
                f"Allowed formats: {allowed}."
            ),
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded audio file is empty.")
    if len(contents) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"The audio file is {len(contents) / 1024 / 1024:.1f} MB, which exceeds the "
                f"{settings.max_upload_size_mb} MB limit."
            ),
        )

    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    stored_path = settings.audio_dir / f"{uuid.uuid4().hex}{extension}"
    stored_path.write_bytes(contents)

    meeting = Meeting(
        title=title.strip(),
        description=(description or "").strip() or None,
        audio_path=str(stored_path),
        status=MeetingStatus.UPLOADED,
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    logger.info(
        "Meeting uploaded: id=%s size=%.2fMB format=%s",
        meeting.id,
        len(contents) / 1024 / 1024,
        extension,
    )
    return meeting


@router.get("", response_model=list[MeetingRead])
def list_meetings(
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[Meeting]:
    """List meetings, newest first."""
    return (
        db.query(Meeting)
        .order_by(Meeting.created_at.desc(), Meeting.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/search", response_model=SearchResponse)
def search_transcripts(
    q: str = Query(..., min_length=2, description="Text to look for in transcripts"),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SearchResponse:
    """Keyword search across all stored transcripts and meeting titles."""
    pattern = f"%{q.lower()}%"
    rows = (
        db.query(TranscriptSegment, Meeting)
        .join(Meeting, Meeting.id == TranscriptSegment.meeting_id)
        .filter(
            or_(
                func.lower(TranscriptSegment.text).like(pattern),
                func.lower(Meeting.title).like(pattern),
            )
        )
        .order_by(Meeting.id.desc(), TranscriptSegment.start_time)
        .limit(limit)
        .all()
    )
    hits = [
        SearchHit(
            meeting_id=meeting.id,
            meeting_title=meeting.title,
            segment_id=segment.id,
            speaker=segment.speaker,
            start_time=segment.start_time,
            end_time=segment.end_time,
            text=segment.text,
        )
        for segment, meeting in rows
    ]
    logger.info("Transcript search for %r returned %d hits", q, len(hits))
    return SearchResponse(query=q, hits=hits)


@router.get("/{meeting_id}", response_model=MeetingRead)
def get_meeting(meeting_id: int, db: Session = Depends(get_db)) -> Meeting:
    return _get_meeting_or_404(db, meeting_id)


@router.post("/{meeting_id}/process", response_model=MeetingRead, status_code=202)
def process_meeting(
    meeting_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    processor: MeetingProcessor = Depends(get_processor),
) -> Meeting:
    """Start transcription, summarisation and indexing in the background."""
    meeting = _get_meeting_or_404(db, meeting_id)
    if meeting.status in BUSY_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Meeting {meeting_id} is already being processed "
                f"(status: {meeting.status.value})."
            ),
        )
    if not meeting.audio_path or not Path(meeting.audio_path).exists():
        raise HTTPException(
            status_code=400,
            detail=(
                f"The audio file for meeting {meeting_id} is missing. "
                "Upload the recording again."
            ),
        )

    meeting.status = MeetingStatus.TRANSCRIBING
    meeting.error_message = None
    db.commit()
    db.refresh(meeting)

    background_tasks.add_task(run_pipeline, processor, meeting_id)
    logger.info("Processing queued for meeting %s", meeting_id)
    return meeting


def run_pipeline(processor: MeetingProcessor, meeting_id: int) -> None:
    """Background entrypoint; opens its own session since the request one is closed."""
    db = SessionLocal()
    try:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            logger.warning("Meeting %s disappeared before processing started", meeting_id)
            return
        processor.process(db, meeting)
    finally:
        db.close()


@router.get("/{meeting_id}/transcript", response_model=TranscriptResponse)
def get_transcript(meeting_id: int, db: Session = Depends(get_db)) -> TranscriptResponse:
    meeting = _get_meeting_or_404(db, meeting_id)
    return TranscriptResponse(
        meeting_id=meeting.id,
        status=meeting.status,
        segments=meeting.segments,
    )


@router.get("/{meeting_id}/summary", response_model=SummaryRead)
def get_summary(meeting_id: int, db: Session = Depends(get_db)) -> SummaryRead:
    meeting = _get_meeting_or_404(db, meeting_id)
    summary = (
        db.query(MeetingSummary).filter(MeetingSummary.meeting_id == meeting_id).one_or_none()
    )
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Meeting {meeting_id} has no summary yet (status: {meeting.status.value}). "
                "Run the processing step first."
            ),
        )

    def load(raw: str) -> list:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return value if isinstance(value, list) else []

    return SummaryRead(
        meeting_id=meeting_id,
        summary=summary.summary,
        key_points=load(summary.key_points),
        decisions=load(summary.decisions),
        action_items=load(summary.action_items),
        created_at=summary.created_at,
    )


@router.post("/{meeting_id}/chat", response_model=ChatResponse)
def chat_with_meeting(
    meeting_id: int,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    rag: RagService = Depends(get_rag_service),
) -> ChatResponse:
    """Ask a question about a meeting; answered only from its transcript."""
    meeting = _get_meeting_or_404(db, meeting_id)
    if meeting.status != MeetingStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Meeting {meeting_id} is not ready for questions "
                f"(status: {meeting.status.value}). Wait until processing is COMPLETED."
            ),
        )

    try:
        answer, sources = rag.answer(meeting_id, payload.question, payload.top_k)
    except RagError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ChatResponse(
        meeting_id=meeting_id,
        question=payload.question,
        answer=answer,
        sources=sources,
    )


@router.delete("/{meeting_id}", status_code=204)
def delete_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    embeddings: EmbeddingService = Depends(get_embedding_service),
) -> None:
    """Delete a meeting, its audio file and its vectors."""
    meeting = _get_meeting_or_404(db, meeting_id)

    if meeting.audio_path:
        try:
            Path(meeting.audio_path).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not delete audio file for meeting %s: %s", meeting_id, exc)

    embeddings.delete_meeting(meeting_id)
    db.delete(meeting)
    db.commit()
    logger.info("Meeting %s deleted", meeting_id)


@router.get("/{meeting_id}/audio")
def get_meeting_audio(meeting_id: int, db: Session = Depends(get_db)):
    """Stream the stored recording so the frontend can play it."""
    from fastapi.responses import FileResponse

    meeting = _get_meeting_or_404(db, meeting_id)
    if not meeting.audio_path or not Path(meeting.audio_path).exists():
        raise HTTPException(
            status_code=404, detail=f"No audio file is stored for meeting {meeting_id}."
        )
    return FileResponse(meeting.audio_path)
