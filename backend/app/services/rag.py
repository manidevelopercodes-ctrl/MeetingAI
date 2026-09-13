"""Retrieval-augmented question answering over a single meeting transcript."""

import logging

from app.config import Settings, get_settings
from app.schemas.meeting import ChatSource
from app.services.embeddings import EmbeddingService
from app.services.ollama import OllamaClient, OllamaError

logger = logging.getLogger(__name__)

NO_ANSWER = "I couldn't find that information in this meeting."

SYSTEM_PROMPT = (
    "You answer questions about a meeting using only the transcript excerpts you are given. "
    "You never use outside knowledge and you never guess."
)

PROMPT_TEMPLATE = """Answer the question using ONLY the transcript excerpts below.

If the excerpts do not contain the answer, reply with exactly this sentence and nothing else:
{no_answer}

TRANSCRIPT EXCERPTS:
{context}

QUESTION: {question}

ANSWER:"""


class RagError(RuntimeError):
    """Raised when a RAG answer could not be produced."""


class RagService:
    def __init__(
        self,
        settings: Settings | None = None,
        embedding_service: EmbeddingService | None = None,
        ollama_client: OllamaClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.embeddings = embedding_service or EmbeddingService(self.settings)
        self.ollama = ollama_client or OllamaClient(self.settings)

    def answer(
        self, meeting_id: int, question: str, top_k: int | None = None
    ) -> tuple[str, list[ChatSource]]:
        """Answer a question about one meeting and return the supporting chunks."""
        k = top_k or self.settings.rag_top_k
        logger.info("RAG query for meeting %s (top_k=%d)", meeting_id, k)

        hits = self.embeddings.query(meeting_id, question, top_k=k)
        if not hits:
            logger.info("RAG query for meeting %s found no relevant chunks", meeting_id)
            return NO_ANSWER, []

        sources = [ChatSource(**hit) for hit in hits]
        context = "\n\n".join(
            f"[{self._timestamp(hit['start_time'])} - {self._timestamp(hit['end_time'])}] "
            f"{hit['speaker']}: {hit['text']}"
            for hit in hits
        )
        prompt = PROMPT_TEMPLATE.format(
            no_answer=NO_ANSWER, context=context, question=question.strip()
        )

        try:
            answer = self.ollama.generate(prompt, system=SYSTEM_PROMPT)
        except OllamaError as exc:
            raise RagError(str(exc)) from exc

        answer = answer.strip() or NO_ANSWER
        return answer, sources

    @staticmethod
    def _timestamp(seconds: float) -> str:
        total = int(seconds)
        return f"{total // 60:02d}:{total % 60:02d}"
