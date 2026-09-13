"""Local speech-to-text using faster-whisper.

Speaker diarization is intentionally not implemented: it would require a heavy,
fragile extra dependency. Every segment is attributed to DEFAULT_SPEAKER.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_SPEAKER = "Speaker 1"


class TranscriptionError(RuntimeError):
    """Raised when audio could not be transcribed."""


@dataclass
class TranscribedSegment:
    speaker: str
    start_time: float
    end_time: float
    text: str


@dataclass
class TranscriptionResult:
    segments: list[TranscribedSegment]
    duration: float
    language: str | None = None


class TranscriptionService:
    """Wraps faster-whisper. The model is loaded lazily on first use."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise TranscriptionError(
                "faster-whisper is not installed. Run: pip install -r requirements.txt"
            ) from exc

        logger.info(
            "Loading Whisper model '%s' (device=%s, compute_type=%s)",
            self.settings.whisper_model,
            self.settings.whisper_device,
            self.settings.whisper_compute_type,
        )
        try:
            self._model = WhisperModel(
                self.settings.whisper_model,
                device=self.settings.whisper_device,
                compute_type=self.settings.whisper_compute_type,
            )
        except Exception as exc:  # noqa: BLE001 - surface any model/download failure clearly
            raise TranscriptionError(
                f"Could not load the Whisper model '{self.settings.whisper_model}'. "
                f"The model is downloaded automatically on first use, so check your "
                f"internet connection and available disk space. Original error: {exc}"
            ) from exc
        return self._model

    def transcribe(self, audio_path: str | Path) -> TranscriptionResult:
        """Transcribe an audio file into timed segments."""
        path = Path(audio_path)
        if not path.exists():
            raise TranscriptionError(f"Audio file not found: {path}")

        model = self._load_model()
        logger.info("Transcription started for %s", path.name)
        try:
            raw_segments, info = model.transcribe(str(path), beam_size=5, vad_filter=True)
            segments = [
                TranscribedSegment(
                    speaker=DEFAULT_SPEAKER,
                    start_time=float(segment.start),
                    end_time=float(segment.end),
                    text=segment.text.strip(),
                )
                for segment in raw_segments
                if segment.text and segment.text.strip()
            ]
        except Exception as exc:  # noqa: BLE001
            raise TranscriptionError(
                f"Transcription failed for '{path.name}'. The file may be corrupt or in an "
                f"unsupported format. Original error: {exc}"
            ) from exc

        duration = float(getattr(info, "duration", 0.0) or 0.0)
        if not duration and segments:
            duration = segments[-1].end_time

        logger.info("Transcription completed for %s (%d segments)", path.name, len(segments))
        return TranscriptionResult(
            segments=segments,
            duration=duration,
            language=getattr(info, "language", None),
        )
