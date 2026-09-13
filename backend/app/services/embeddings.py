"""Transcript chunking, sentence-transformers embeddings and the ChromaDB store."""

import logging
from dataclasses import dataclass
from typing import Sequence

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """Raised when embeddings could not be created or stored."""


@dataclass
class TranscriptChunk:
    text: str
    speaker: str
    start_time: float
    end_time: float


def chunk_segments(
    segments: Sequence[object],
    chunk_size: int = 5,
    overlap: int = 1,
) -> list[TranscriptChunk]:
    """Group consecutive transcript segments into overlapping chunks.

    Accepts anything with ``speaker``/``start_time``/``end_time``/``text`` attributes,
    so it works with both ORM segments and transcription results.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    step = max(1, chunk_size - max(0, overlap))

    chunks: list[TranscriptChunk] = []
    for start in range(0, len(segments), step):
        window = segments[start : start + chunk_size]
        if not window:
            break
        text = " ".join(str(getattr(s, "text", "")).strip() for s in window).strip()
        if not text:
            continue
        chunks.append(
            TranscriptChunk(
                text=text,
                speaker=str(getattr(window[0], "speaker", "Speaker 1")),
                start_time=float(getattr(window[0], "start_time", 0.0)),
                end_time=float(getattr(window[-1], "end_time", 0.0)),
            )
        )
        if start + chunk_size >= len(segments):
            break
    return chunks


class EmbeddingService:
    """Owns the embedding model and the ChromaDB collection."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._model = None
        self._collection = None

    # -- lazy resources -------------------------------------------------

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover
            raise EmbeddingError(
                "sentence-transformers is not installed. Run: pip install -r requirements.txt"
            ) from exc
        logger.info("Loading embedding model '%s'", self.settings.embedding_model)
        try:
            self._model = SentenceTransformer(self.settings.embedding_model)
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(
                f"Could not load the embedding model '{self.settings.embedding_model}'. "
                f"It is downloaded automatically on first use. Original error: {exc}"
            ) from exc
        return self._model

    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover
            raise EmbeddingError(
                "chromadb is not installed. Run: pip install -r requirements.txt"
            ) from exc
        try:
            client = chromadb.PersistentClient(path=str(self.settings.chroma_dir))
            self._collection = client.get_or_create_collection(
                name=self.settings.chroma_collection,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(
                f"Could not open the ChromaDB store at {self.settings.chroma_dir}: {exc}"
            ) from exc
        return self._collection

    # -- public API -----------------------------------------------------

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of texts."""
        model = self._get_model()
        vectors = model.encode(list(texts), show_progress_bar=False)
        return [list(map(float, vector)) for vector in vectors]

    def index_meeting(self, meeting_id: int, segments: Sequence[object]) -> int:
        """Chunk, embed and store a meeting's transcript. Returns the chunk count."""
        chunks = chunk_segments(
            segments,
            chunk_size=self.settings.rag_chunk_size,
            overlap=self.settings.rag_chunk_overlap,
        )
        if not chunks:
            logger.warning("Meeting %s produced no indexable chunks", meeting_id)
            return 0

        logger.info("Embedding started for meeting %s (%d chunks)", meeting_id, len(chunks))
        self.delete_meeting(meeting_id)

        collection = self._get_collection()
        embeddings = self.embed([chunk.text for chunk in chunks])
        collection.add(
            ids=[f"meeting-{meeting_id}-chunk-{index}" for index in range(len(chunks))],
            documents=[chunk.text for chunk in chunks],
            embeddings=embeddings,
            metadatas=[
                {
                    "meeting_id": meeting_id,
                    "speaker": chunk.speaker,
                    "start_time": chunk.start_time,
                    "end_time": chunk.end_time,
                }
                for chunk in chunks
            ],
        )
        logger.info("Embedding completed for meeting %s (%d chunks)", meeting_id, len(chunks))
        return len(chunks)

    def query(self, meeting_id: int, question: str, top_k: int = 5) -> list[dict]:
        """Retrieve the most relevant chunks of one meeting for a question."""
        collection = self._get_collection()
        query_embedding = self.embed([question])[0]
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"meeting_id": meeting_id},
        )

        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        hits: list[dict] = []
        for index, document in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) else {}
            distance = distances[index] if index < len(distances) else None
            hits.append(
                {
                    "text": document,
                    "speaker": str(metadata.get("speaker", "Speaker 1")),
                    "start_time": float(metadata.get("start_time", 0.0)),
                    "end_time": float(metadata.get("end_time", 0.0)),
                    "score": None if distance is None else round(1.0 - float(distance), 4),
                }
            )
        return hits

    def delete_meeting(self, meeting_id: int) -> None:
        """Remove every vector belonging to a meeting. Never raises."""
        try:
            self._get_collection().delete(where={"meeting_id": meeting_id})
        except Exception as exc:  # noqa: BLE001 - deletion must not break the caller
            logger.warning("Could not delete vectors for meeting %s: %s", meeting_id, exc)
