"""Reusable client for a local Ollama server.

Kept deliberately generic: no prompt or model specific logic belongs here.
"""

import json
import logging

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    """Raised when the local Ollama server is unreachable or returns an error."""


class OllamaClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.ollama_base_url.rstrip("/")
        self.model = self.settings.ollama_model
        self.timeout = self.settings.ollama_timeout_seconds

    def is_available(self) -> bool:
        """True when the Ollama server answers. Never raises."""
        try:
            with httpx.Client(timeout=3.0) as client:
                return client.get(f"{self.base_url}/api/tags").status_code == 200
        except httpx.HTTPError:
            return False

    def generate(self, prompt: str, *, system: str | None = None, json_mode: bool = False) -> str:
        """Send a single-turn prompt to Ollama and return the raw text response."""
        payload: dict[str, object] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise OllamaError(
                f"Could not reach the Ollama model '{self.model}' at {self.base_url}. "
                f"Make sure Ollama is running and the model is installed "
                f"(ollama pull {self.model}). Original error: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise OllamaError(f"Ollama returned a malformed response: {exc}") from exc

        return str(data.get("response", "")).strip()
