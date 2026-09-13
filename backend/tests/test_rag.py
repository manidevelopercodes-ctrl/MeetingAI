"""Tests for the AI services. Whisper and Ollama are always mocked."""

import json

import pytest

from app.config import Settings
from app.models.meeting import Meeting, MeetingStatus, MeetingSummary, TranscriptSegment
from app.services.embeddings import chunk_segments
from app.services.meeting_processor import MeetingProcessor
from app.services.rag import NO_ANSWER, RagError, RagService
from app.services.summarization import SummarizationError, SummarizationService
from app.services.transcription import (
    DEFAULT_SPEAKER,
    TranscribedSegment,
    TranscriptionError,
    TranscriptionResult,
    TranscriptionService,
)
from tests.conftest import FakeEmbeddingService


class FakeOllama:
    """Stands in for a running Ollama server."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, system=None, json_mode=False) -> str:
        self.prompts.append(prompt)
        return self.replies.pop(0) if self.replies else ""

    def is_available(self) -> bool:
        return True


class Segment:
    """Minimal transcript segment stand-in for chunking tests."""

    def __init__(self, text: str, start: float, end: float, speaker: str = "Speaker 1") -> None:
        self.text = text
        self.start_time = start
        self.end_time = end
        self.speaker = speaker


# -- chunking -----------------------------------------------------------


def test_chunking_groups_segments_and_keeps_the_time_span():
    segments = [Segment(f"line {i}", float(i), float(i) + 1) for i in range(6)]

    chunks = chunk_segments(segments, chunk_size=3, overlap=0)

    assert len(chunks) == 2
    assert chunks[0].text == "line 0 line 1 line 2"
    assert chunks[0].start_time == 0.0
    assert chunks[0].end_time == 3.0


def test_chunking_overlaps_consecutive_chunks():
    segments = [Segment(f"line {i}", float(i), float(i) + 1) for i in range(5)]

    chunks = chunk_segments(segments, chunk_size=3, overlap=1)

    assert "line 2" in chunks[0].text
    assert "line 2" in chunks[1].text


def test_chunking_skips_empty_text():
    chunks = chunk_segments([Segment("   ", 0.0, 1.0)], chunk_size=2, overlap=0)

    assert chunks == []


# -- RAG ----------------------------------------------------------------


@pytest.fixture
def rag(settings: Settings, fake_embeddings: FakeEmbeddingService):
    def build(*replies: str) -> tuple[RagService, FakeOllama]:
        ollama = FakeOllama(*replies)
        return RagService(settings, fake_embeddings, ollama), ollama

    return build


def test_rag_says_it_cannot_find_the_answer_when_nothing_is_retrieved(rag, fake_embeddings):
    service, ollama = rag("should not be used")
    fake_embeddings.hits = []

    answer, sources = service.answer(1, "What did we decide about pricing?")

    assert answer == NO_ANSWER
    assert sources == []
    assert ollama.prompts == []


def test_rag_answers_from_retrieved_context_and_returns_sources(rag, fake_embeddings):
    fake_embeddings.hits = [
        {
            "text": "We decided to delay the launch to March.",
            "speaker": "Speaker 1",
            "start_time": 12.0,
            "end_time": 18.0,
            "score": 0.91,
        }
    ]
    service, ollama = rag("The launch was delayed to March.")

    answer, sources = service.answer(1, "When is the launch?")

    assert answer == "The launch was delayed to March."
    assert len(sources) == 1
    assert sources[0].speaker == "Speaker 1"
    assert sources[0].start_time == 12.0


def test_rag_sends_only_the_retrieved_chunks_as_context(rag, fake_embeddings):
    fake_embeddings.hits = [
        {
            "text": "Budget approved at 40k.",
            "speaker": "Speaker 1",
            "start_time": 0.0,
            "end_time": 5.0,
            "score": 0.8,
        }
    ]
    service, ollama = rag("40k")

    service.answer(1, "What is the budget?")

    prompt = ollama.prompts[0]
    assert "Budget approved at 40k." in prompt
    assert "What is the budget?" in prompt
    assert NO_ANSWER in prompt  # the model is told how to decline


def test_rag_falls_back_to_the_no_answer_sentence_on_an_empty_reply(rag, fake_embeddings):
    fake_embeddings.hits = [
        {"text": "Anything", "speaker": "Speaker 1", "start_time": 0.0, "end_time": 1.0, "score": 0.5}
    ]
    service, _ = rag("   ")

    answer, _ = service.answer(1, "Who owns the migration?")

    assert answer == NO_ANSWER


def test_rag_raises_a_useful_error_when_ollama_is_unreachable(settings, fake_embeddings):
    from app.services.ollama import OllamaError

    class BrokenOllama(FakeOllama):
        def generate(self, prompt, *, system=None, json_mode=False):
            raise OllamaError("Could not reach the Ollama model 'llama3.2'. Run: ollama pull llama3.2")

    fake_embeddings.hits = [
        {"text": "x", "speaker": "Speaker 1", "start_time": 0.0, "end_time": 1.0, "score": 0.5}
    ]
    service = RagService(settings, fake_embeddings, BrokenOllama())

    with pytest.raises(RagError, match="ollama pull llama3.2"):
        service.answer(1, "anything")


# -- summarisation ------------------------------------------------------


VALID_SUMMARY = json.dumps(
    {
        "summary": "The team agreed the release plan.",
        "key_points": ["Release moves to March"],
        "decisions": ["Delay the launch"],
        "action_items": [{"task": "Update the roadmap", "owner": "Priya", "due_date": "2026-03-01"}],
    }
)


def test_summarization_parses_a_valid_response(settings):
    service = SummarizationService(settings, FakeOllama(VALID_SUMMARY))

    payload = service.summarize("Speaker 1: we should delay the launch.")

    assert payload.summary == "The team agreed the release plan."
    assert payload.key_points == ["Release moves to March"]
    assert payload.decisions == ["Delay the launch"]
    assert payload.action_items[0].owner == "Priya"


def test_summarization_strips_markdown_fences(settings):
    fenced = "```json\n" + VALID_SUMMARY + "\n```"
    service = SummarizationService(settings, FakeOllama(fenced))

    assert service.summarize("transcript").summary == "The team agreed the release plan."


def test_summarization_retries_once_after_invalid_json(settings):
    ollama = FakeOllama("this is not json at all", VALID_SUMMARY)
    service = SummarizationService(settings, ollama)

    payload = service.summarize("transcript")

    assert payload.summary == "The team agreed the release plan."
    assert len(ollama.prompts) == 2


def test_summarization_fails_with_a_clear_error_after_repeated_bad_json(settings):
    service = SummarizationService(settings, FakeOllama("nope", "still nope"))

    with pytest.raises(SummarizationError, match="did not return valid JSON"):
        service.summarize("transcript")


def test_summarization_uses_null_when_owner_and_due_date_are_missing(settings):
    reply = json.dumps(
        {
            "summary": "s",
            "key_points": [],
            "decisions": [],
            "action_items": [{"task": "Follow up", "owner": "unknown", "due_date": None}],
        }
    )
    service = SummarizationService(settings, FakeOllama(reply))

    item = service.summarize("transcript").action_items[0]

    assert item.task == "Follow up"
    assert item.owner is None
    assert item.due_date is None


def test_summarization_rejects_an_empty_transcript(settings):
    service = SummarizationService(settings, FakeOllama(VALID_SUMMARY))

    with pytest.raises(SummarizationError, match="empty transcript"):
        service.summarize("   ")


# -- transcription ------------------------------------------------------


def test_transcription_reports_a_missing_file_clearly(settings, tmp_path):
    service = TranscriptionService(settings)

    with pytest.raises(TranscriptionError, match="Audio file not found"):
        service.transcribe(tmp_path / "does-not-exist.wav")


def test_transcription_uses_the_configured_model(settings):
    assert TranscriptionService(settings).settings.whisper_model == "small"


def test_transcribed_segments_default_to_a_single_speaker():
    segment = TranscribedSegment(
        speaker=DEFAULT_SPEAKER, start_time=0.0, end_time=1.0, text="Hello"
    )

    assert segment.speaker == "Speaker 1"


# -- pipeline -----------------------------------------------------------


class FakeTranscription:
    def __init__(self, *, fail: bool = False, segments=None) -> None:
        self.fail = fail
        self.segments = segments if segments is not None else [
            TranscribedSegment(DEFAULT_SPEAKER, 0.0, 5.0, "We will delay the launch to March."),
            TranscribedSegment(DEFAULT_SPEAKER, 5.0, 9.0, "Priya updates the roadmap."),
        ]

    def transcribe(self, audio_path):
        if self.fail:
            raise TranscriptionError("The audio file is corrupt.")
        return TranscriptionResult(segments=self.segments, duration=9.0, language="en")


def _make_meeting(db_session, tmp_path):
    audio = tmp_path / "meeting.wav"
    audio.write_bytes(b"RIFF")
    meeting = Meeting(title="Planning", audio_path=str(audio), status=MeetingStatus.UPLOADED)
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(meeting)
    return meeting


def test_pipeline_completes_and_stores_everything(settings, db_session, tmp_path, fake_embeddings):
    meeting = _make_meeting(db_session, tmp_path)
    processor = MeetingProcessor(
        settings,
        FakeTranscription(),
        SummarizationService(settings, FakeOllama(VALID_SUMMARY)),
        fake_embeddings,
    )

    processor.process(db_session, meeting)

    assert meeting.status == MeetingStatus.COMPLETED
    assert meeting.error_message is None
    assert meeting.duration == 9.0
    assert db_session.query(TranscriptSegment).count() == 2

    summary = db_session.query(MeetingSummary).one()
    assert summary.summary == "The team agreed the release plan."
    assert json.loads(summary.action_items)[0]["owner"] == "Priya"
    assert fake_embeddings.indexed[meeting.id]


def test_pipeline_marks_the_meeting_failed_with_the_error_message(
    settings, db_session, tmp_path, fake_embeddings
):
    meeting = _make_meeting(db_session, tmp_path)
    processor = MeetingProcessor(
        settings,
        FakeTranscription(fail=True),
        SummarizationService(settings, FakeOllama(VALID_SUMMARY)),
        fake_embeddings,
    )

    processor.process(db_session, meeting)

    assert meeting.status == MeetingStatus.FAILED
    assert "corrupt" in meeting.error_message


def test_pipeline_fails_clearly_when_no_speech_is_detected(
    settings, db_session, tmp_path, fake_embeddings
):
    meeting = _make_meeting(db_session, tmp_path)
    processor = MeetingProcessor(
        settings,
        FakeTranscription(segments=[]),
        SummarizationService(settings, FakeOllama(VALID_SUMMARY)),
        fake_embeddings,
    )

    processor.process(db_session, meeting)

    assert meeting.status == MeetingStatus.FAILED
    assert "No speech was detected" in meeting.error_message


def test_reprocessing_replaces_the_previous_transcript_and_summary(
    settings, db_session, tmp_path, fake_embeddings
):
    meeting = _make_meeting(db_session, tmp_path)
    processor = MeetingProcessor(
        settings,
        FakeTranscription(),
        SummarizationService(settings, FakeOllama(VALID_SUMMARY, VALID_SUMMARY)),
        fake_embeddings,
    )

    processor.process(db_session, meeting)
    processor.process(db_session, meeting)

    assert db_session.query(TranscriptSegment).count() == 2
    assert db_session.query(MeetingSummary).count() == 1
