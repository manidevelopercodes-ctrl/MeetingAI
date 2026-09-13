"""Turn a transcript into a structured summary using a local Ollama model."""

import json
import logging
import re

from pydantic import ValidationError

from app.config import Settings, get_settings
from app.schemas.meeting import ActionItem, SummaryPayload
from app.services.ollama import OllamaClient, OllamaError

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT_CHARS = 12000
MAX_ATTEMPTS = 2

SYSTEM_PROMPT = (
    "You are a meeting analyst. You read meeting transcripts and reply with a single "
    "JSON object and nothing else. Never invent facts that are not in the transcript."
)

PROMPT_TEMPLATE = """Analyse the meeting transcript below and reply with ONE JSON object.

Required shape (use exactly these keys):
{{
  "summary": "a short paragraph summarising the meeting",
  "key_points": ["short bullet", "..."],
  "decisions": ["a decision that was made", "..."],
  "action_items": [{{"task": "what must be done", "owner": "person or null", "due_date": "date or null"}}]
}}

Rules:
- Reply with JSON only. No markdown fences, no commentary.
- Use null (not "unknown") when an owner or due date is not stated.
- Use empty lists when there are no key points, decisions or action items.

TRANSCRIPT:
{transcript}
"""


class SummarizationError(RuntimeError):
    """Raised when a usable summary could not be produced."""


def _extract_json(text: str) -> dict:
    """Pull a JSON object out of an LLM reply, tolerating fences and stray prose."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object at the top level")
    return parsed


def _coerce(raw: dict) -> SummaryPayload:
    """Normalise a loosely-shaped LLM object into a validated SummaryPayload."""

    def as_str_list(value: object) -> list[str]:
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    def as_action_items(value: object) -> list[ActionItem]:
        items: list[ActionItem] = []
        if not isinstance(value, list):
            return items
        for entry in value:
            if isinstance(entry, str) and entry.strip():
                items.append(ActionItem(task=entry.strip()))
                continue
            if not isinstance(entry, dict):
                continue
            task = str(entry.get("task") or entry.get("action") or "").strip()
            if not task:
                continue

            def clean(value: object) -> str | None:
                text = str(value).strip() if value is not None else ""
                if not text or text.lower() in {"null", "none", "n/a", "unknown", "tbd", ""}:
                    return None
                return text

            items.append(
                ActionItem(
                    task=task,
                    owner=clean(entry.get("owner") or entry.get("assignee")),
                    due_date=clean(entry.get("due_date") or entry.get("due")),
                )
            )
        return items

    return SummaryPayload(
        summary=str(raw.get("summary") or "").strip(),
        key_points=as_str_list(raw.get("key_points")),
        decisions=as_str_list(raw.get("decisions")),
        action_items=as_action_items(raw.get("action_items")),
    )


class SummarizationService:
    def __init__(
        self,
        settings: Settings | None = None,
        ollama_client: OllamaClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.ollama = ollama_client or OllamaClient(self.settings)

    def summarize(self, transcript: str) -> SummaryPayload:
        """Generate a validated summary. Retries once if the model returns bad JSON."""
        if not transcript.strip():
            raise SummarizationError("Cannot summarise an empty transcript.")

        excerpt = transcript[:MAX_TRANSCRIPT_CHARS]
        if len(transcript) > MAX_TRANSCRIPT_CHARS:
            logger.info("Transcript truncated to %d characters for summarisation", MAX_TRANSCRIPT_CHARS)

        prompt = PROMPT_TEMPLATE.format(transcript=excerpt)
        last_error: Exception | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            logger.info("Summary generation started (attempt %d/%d)", attempt, MAX_ATTEMPTS)
            try:
                reply = self.ollama.generate(prompt, system=SYSTEM_PROMPT, json_mode=True)
            except OllamaError as exc:
                raise SummarizationError(str(exc)) from exc

            try:
                payload = _coerce(_extract_json(reply))
            except (json.JSONDecodeError, ValueError, ValidationError) as exc:
                last_error = exc
                logger.warning("Model returned invalid JSON on attempt %d: %s", attempt, exc)
                prompt = (
                    "Your previous reply was not valid JSON. Reply again with ONLY the JSON "
                    "object described below.\n\n" + PROMPT_TEMPLATE.format(transcript=excerpt)
                )
                continue

            if not payload.summary:
                # Fall back to a usable summary rather than failing the whole pipeline.
                payload.summary = excerpt[:500].strip()
            logger.info(
                "Summary generation completed (%d key points, %d decisions, %d action items)",
                len(payload.key_points),
                len(payload.decisions),
                len(payload.action_items),
            )
            return payload

        raise SummarizationError(
            f"The model '{self.settings.ollama_model}' did not return valid JSON after "
            f"{MAX_ATTEMPTS} attempts. Last error: {last_error}"
        )
