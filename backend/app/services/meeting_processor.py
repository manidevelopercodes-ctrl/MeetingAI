"""Orchestrates the meeting pipeline: transcribe -> summarise -> index."""

import json
import logging

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.meeting import Meeting, MeetingStatus, MeetingSummary, TranscriptSegment
from app.services.embeddings import EmbeddingService
from app.services.summarization import SummarizationService
from app.services.transcription import TranscriptionService

logger = logging.getLogger(__name__)


class MeetingProcessor:
    """Services are injected so tests can substitute lightweight fakes."""

    def __init__(
        self,
        settings: Settings | None = None,
        transcription_service: TranscriptionService | None = None,
        summarization_service: SummarizationService | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.transcription = transcription_service or TranscriptionService(self.settings)
        self.summarization = summarization_service or SummarizationService(self.settings)
        self.embeddings = embedding_service or EmbeddingService(self.settings)

    def process(self, db: Session, meeting: Meeting) -> Meeting:
        """Run the full pipeline. Failures are recorded on the meeting, not raised."""
        logger.info("Processing started for meeting %s", meeting.id)
        try:
            self._transcribe(db, meeting)
            self._summarize(db, meeting)
            self._index(db, meeting)
        except Exception as exc:  # noqa: BLE001 - the status field is the error channel
            logger.exception("Processing failed for meeting %s", meeting.id)
            meeting.status = MeetingStatus.FAILED
            meeting.error_message = str(exc)
            db.commit()
            db.refresh(meeting)
            return meeting

        meeting.status = MeetingStatus.COMPLETED
        meeting.error_message = None
        db.commit()
        db.refresh(meeting)
        logger.info("Processing completed for meeting %s", meeting.id)
        return meeting

    # -- pipeline stages ------------------------------------------------

    def _set_status(self, db: Session, meeting: Meeting, status: MeetingStatus) -> None:
        meeting.status = status
        db.commit()

    def _transcribe(self, db: Session, meeting: Meeting) -> None:
        if not meeting.audio_path:
            raise ValueError("This meeting has no audio file to transcribe.")
        self._set_status(db, meeting, MeetingStatus.TRANSCRIBING)

        result = self.transcription.transcribe(meeting.audio_path)
        if not result.segments:
            raise ValueError(
                "No speech was detected in the audio file. Check that the recording is not silent."
            )

        # Deleted through the ORM (not a bulk delete) so the session's identity map
        # stays consistent when a meeting is processed more than once.
        for stale in (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.meeting_id == meeting.id)
            .all()
        ):
            db.delete(stale)
        db.flush()

        db.add_all(
            TranscriptSegment(
                meeting_id=meeting.id,
                speaker=segment.speaker,
                start_time=segment.start_time,
                end_time=segment.end_time,
                text=segment.text,
            )
            for segment in result.segments
        )
        meeting.duration = result.duration
        db.commit()

    def _summarize(self, db: Session, meeting: Meeting) -> None:
        self._set_status(db, meeting, MeetingStatus.SUMMARIZING)

        segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.meeting_id == meeting.id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )
        transcript = "\n".join(f"{s.speaker}: {s.text}" for s in segments)
        payload = self.summarization.summarize(transcript)

        existing = (
            db.query(MeetingSummary).filter(MeetingSummary.meeting_id == meeting.id).one_or_none()
        )
        if existing is not None:
            db.delete(existing)
            db.flush()

        db.add(
            MeetingSummary(
                meeting_id=meeting.id,
                summary=payload.summary,
                key_points=json.dumps(payload.key_points),
                decisions=json.dumps(payload.decisions),
                action_items=json.dumps([item.model_dump() for item in payload.action_items]),
            )
        )
        db.commit()

    def _index(self, db: Session, meeting: Meeting) -> None:
        self._set_status(db, meeting, MeetingStatus.INDEXING)

        segments = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.meeting_id == meeting.id)
            .order_by(TranscriptSegment.start_time)
            .all()
        )
        self.embeddings.index_meeting(meeting.id, segments)
