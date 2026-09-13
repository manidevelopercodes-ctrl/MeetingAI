# MeetingAI architecture

MeetingAI is a small, single-machine application. Everything — speech recognition,
the language model and the vector store — runs locally. No cloud or paid API is used.

## Components

```
React (Vite, port 5173)
        |
        v
FastAPI (port 8000)
        |
        v
  Meeting Service
        |
        +--> SQLite            meetings, transcript segments, summaries
        +--> faster-whisper    local speech to text
        +--> Ollama            local LLM for summaries and chat answers
        +--> ChromaDB          local vector store for retrieval
```

| Layer | Module | Responsibility |
|---|---|---|
| API | `app/main.py` | Application setup, CORS, `/health`, startup logging, schema creation |
| API | `app/api/meetings.py` | All meeting endpoints; validation and HTTP status codes |
| Schemas | `app/schemas/meeting.py` | Request and response models |
| Models | `app/models/meeting.py` | `Meeting`, `TranscriptSegment`, `MeetingSummary`, `MeetingStatus` |
| Data | `app/database.py` | Engine, session factory, `init_db()` |
| Service | `app/services/transcription.py` | faster-whisper wrapper |
| Service | `app/services/ollama.py` | Generic Ollama HTTP client, reused by every LLM feature |
| Service | `app/services/summarization.py` | Prompting, JSON extraction, validation, retry |
| Service | `app/services/embeddings.py` | Chunking, sentence-transformers, ChromaDB |
| Service | `app/services/rag.py` | Retrieval, context building, grounded answering |
| Service | `app/services/meeting_processor.py` | Orchestrates the pipeline and owns status transitions |

Every AI integration is confined to `app/services/`. The API layer never imports
faster-whisper, ChromaDB or the Ollama client directly — it depends on the service
classes, which are injected through FastAPI dependencies so tests can substitute fakes.

## Processing flow

```
Audio upload            POST /api/meetings          status: UPLOADED
        |
        v
Save audio file         storage/audio/<uuid>.<ext>
        |
        v
Transcription           faster-whisper              status: TRANSCRIBING
        |
        v
Store transcript        transcript_segments
        |
        v
Generate summary        Ollama                      status: SUMMARIZING
  key points
  decisions
  action items
        |
        v
Create embeddings       sentence-transformers       status: INDEXING
        |
        v
Store vectors           ChromaDB (tagged meeting_id)
        |
        v
Meeting ready for RAG chat                          status: COMPLETED
```

Processing runs in a FastAPI background task, so `POST /api/meetings/{id}/process`
returns `202` immediately. The frontend polls the meeting until the status leaves
the in-progress set.

If any stage raises, `MeetingProcessor.process` catches it, sets the status to
`FAILED` and stores the message on `meetings.error_message`, which the UI displays.

## Status lifecycle

```
UPLOADED -> TRANSCRIBING -> SUMMARIZING -> INDEXING -> COMPLETED
                 |               |             |
                 +---------------+-------------+--> FAILED (error_message set)
```

## Retrieval-augmented chat

1. Consecutive transcript segments are grouped into overlapping chunks
   (`RAG_CHUNK_SIZE` segments, `RAG_CHUNK_OVERLAP` of overlap).
2. Each chunk is embedded with sentence-transformers and stored in ChromaDB with
   metadata: `meeting_id`, `speaker`, `start_time`, `end_time`.
3. A question is embedded and the nearest `RAG_TOP_K` chunks **for that meeting only**
   are retrieved (the ChromaDB query filters on `meeting_id`).
4. Those chunks become the entire context sent to Ollama, with instructions to answer
   only from them and otherwise reply with a fixed sentence.
5. The answer and the source chunks are both returned, so answers stay auditable.

## Design choices

- **No speaker diarization.** Reliable diarization needs a heavy, fragile dependency.
  Every segment is attributed to `Speaker 1`, and the schema already carries a
  `speaker` column so diarization can be added later without a migration.
- **Lists stored as JSON strings.** `key_points`, `decisions` and `action_items` are
  JSON text in SQLite. This keeps the schema to three tables for a demo application.
- **Lazy model loading.** Whisper, sentence-transformers and ChromaDB are imported and
  loaded on first use, so the API starts instantly and the test suite never touches them.
- **Retry then fall back.** If the LLM returns invalid JSON the prompt is repeated once;
  if the summary text is still missing, a transcript excerpt is stored rather than
  failing the whole pipeline.
