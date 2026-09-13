# MeetingAI

A small, fully local AI meeting assistant. Upload a meeting recording and MeetingAI
transcribes it, writes a structured summary, pulls out decisions and action items, and
lets you ask questions about what was said — all on your own machine.

No cloud services. No API keys. Nothing leaves your computer.

---

## Table of contents

1. [Project overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Technology stack](#3-technology-stack)
4. [Prerequisites](#4-prerequisites)
5. [Installing Python](#5-installing-python)
6. [Installing Node.js](#6-installing-nodejs)
7. [Installing Ollama](#7-installing-ollama)
8. [Installing the Ollama model](#8-installing-the-ollama-model)
9. [Backend setup](#9-backend-setup)
10. [Frontend setup](#10-frontend-setup)
11. [How to run](#11-how-to-run)
12. [How to upload a meeting](#12-how-to-upload-a-meeting)
13. [How transcription works](#13-how-transcription-works)
14. [How RAG works](#14-how-rag-works)
15. [API endpoints](#15-api-endpoints)
16. [Testing](#16-testing)
17. [Troubleshooting](#17-troubleshooting)
18. [Configuration reference](#18-configuration-reference)
19. [Docker (optional)](#19-docker-optional)

---

## 1. Project overview

MeetingAI lets you:

- Upload an audio recording of a meeting (mp3, wav, m4a, mp4, webm).
- Transcribe it locally with faster-whisper.
- Store the transcript in SQLite.
- Generate an AI summary with a local Ollama model.
- Extract key points, decisions and action items (with owner and due date).
- Search across every meeting transcript.
- Ask questions about a meeting using local retrieval-augmented generation (RAG),
  with the supporting transcript excerpts shown alongside each answer.
- Do all of the above through a simple React dashboard.

This is a learning and demo application. The architecture is deliberately small.

---

## 2. Architecture

```
React (Vite)
    |
    v
FastAPI
    |
    v
Meeting Service
    |
    +--> SQLite           meetings, transcript segments, summaries
    +--> faster-whisper   local speech to text
    +--> Ollama           local LLM
    +--> ChromaDB         local vector store
```

Processing flow:

```
Audio upload -> Save audio file -> Transcription -> Store transcript
    -> Generate summary -> Key points -> Decisions -> Action items
    -> Create embeddings -> Store vectors in ChromaDB
    -> Meeting ready for RAG chat
```

Meeting status moves through:

```
UPLOADED -> TRANSCRIBING -> SUMMARIZING -> INDEXING -> COMPLETED
                                                   \-> FAILED
```

A failure at any stage sets `FAILED` and records a readable message on the meeting,
which the UI shows. See [`docs/architecture.md`](docs/architecture.md) for detail.

---

## 3. Technology stack

**Backend** — Python 3.11+, FastAPI, SQLAlchemy, SQLite, Pydantic, faster-whisper,
Ollama, sentence-transformers, ChromaDB, pytest.

**Frontend** — React, Vite, JavaScript, CSS. No UI framework, no router, no state library.

---

## 4. Prerequisites

| Requirement | Version | Needed for |
|---|---|---|
| Python | 3.11 or 3.12 | Backend |
| Node.js | 18 or newer | Frontend |
| Ollama | latest | Summaries and chat |

> **Python 3.13 and 3.14 are not supported.** `faster-whisper`, `chromadb` and
> `sentence-transformers` do not publish wheels for them yet. Use 3.11 or 3.12.

Check what you have:

```powershell
py -0p
node --version
ollama --version
```

---

## 5. Installing Python

Download Python 3.12 from <https://www.python.org/downloads/> and tick
**"Add python.exe to PATH"** during installation, or use winget:

```powershell
winget install --id Python.Python.3.12 -e
```

Verify:

```powershell
py -3.12 --version
```

---

## 6. Installing Node.js

Download the LTS build from <https://nodejs.org/>, or:

```powershell
winget install --id OpenJS.NodeJS.LTS -e
```

Verify:

```powershell
node --version
npm --version
```

---

## 7. Installing Ollama

Download from <https://ollama.com/download>, or:

```powershell
winget install --id Ollama.Ollama -e
```

Ollama runs as a background service on `http://localhost:11434`. Verify:

```powershell
ollama --version
```

---

## 8. Installing the Ollama model

```powershell
ollama pull llama3.2
```

Confirm it is available:

```powershell
ollama list
```

MeetingAI starts and transcribes fine without Ollama — only the summary and chat
features need it.

---

## 9. Backend setup

```powershell
cd D:\Projects\MeetingAI\backend
```

Create the virtual environment with Python 3.11 or 3.12 specifically:

```powershell
py -3.12 -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\Activate.ps1
```

> If PowerShell blocks the activation script, run
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.

Install dependencies (this downloads PyTorch, so it takes a few minutes):

```powershell
pip install -r requirements.txt
```

Create your local configuration file:

```powershell
Copy-Item .env.example .env
```

The defaults work as-is. The SQLite database and all tables are created
automatically the first time the application starts.

---

## 10. Frontend setup

```powershell
cd D:\Projects\MeetingAI\frontend
```

```powershell
npm install
```

---

## 11. How to run

### Option A — the startup script (easiest)

From the repository root:

```powershell
cd D:\Projects\MeetingAI
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
```

The script creates the virtual environment if it is missing, installs backend and
frontend dependencies, warns you if Ollama is not running, and opens the backend and
frontend in two new PowerShell windows.

Useful switches:

```powershell
.\scripts\start-dev.ps1 -SkipInstall
```

```powershell
.\scripts\start-dev.ps1 -BackendOnly
```

### Option B — start each service yourself

**Ollama** (usually already running as a service; this runs it in the foreground):

```powershell
ollama serve
```

**Backend:**

```powershell
cd D:\Projects\MeetingAI\backend
```

```powershell
.venv\Scripts\Activate.ps1
```

```powershell
uvicorn app.main:app --reload --port 8000
```

**Frontend** (in a second PowerShell window):

```powershell
cd D:\Projects\MeetingAI\frontend
```

```powershell
npm run dev
```

### URLs

| What | URL |
|---|---|
| Frontend | <http://localhost:5173> |
| Backend | <http://localhost:8000> |
| Health check | <http://localhost:8000/health> |
| Interactive API docs | <http://localhost:8000/docs> |

Confirm the backend is up:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

---

## 12. How to upload a meeting

1. Open <http://localhost:5173>.
2. Click **New meeting**.
3. Enter a title, an optional description, and choose an audio file
   (mp3, wav, m4a, mp4 or webm; up to 200 MB by default).
4. Click **Upload and process**.

The meeting appears in the list and its status badge updates automatically as it moves
through `TRANSCRIBING`, `SUMMARIZING` and `INDEXING`. Click the meeting to open it.

The details page shows the audio player, the AI summary with key points, decisions and
action items, a chat panel, and the full transcript with timestamps.

The first upload is slow: the Whisper model (~500 MB for `small`) and the embedding
model (~90 MB) are downloaded on first use. Later runs reuse the cached models.

You can also upload from PowerShell:

```powershell
curl.exe -F "title=Sprint planning" -F "description=Weekly sync" -F "file=@C:\path\to\meeting.mp3" http://localhost:8000/api/meetings
```

---

## 13. How transcription works

`app/services/transcription.py` wraps **faster-whisper**, a CTranslate2 reimplementation
of OpenAI's open-source Whisper model. The model weights are downloaded once and run
entirely on your machine.

- The default model is `small`, set by `WHISPER_MODEL`. Options, smallest to largest:
  `tiny`, `base`, `small`, `medium`, `large-v3`. Bigger is more accurate and slower.
- The default device is CPU with `int8` quantisation. For an NVIDIA GPU set
  `WHISPER_DEVICE=cuda` and `WHISPER_COMPUTE_TYPE=float16`.
- The model is loaded lazily on first transcription, so the API starts immediately.
- Voice activity detection is enabled, which skips silence.

Each segment is stored with a speaker, a start time, an end time and text.

**Speaker diarization is not implemented.** Telling speakers apart reliably requires a
heavy and fragile extra dependency, so every segment is attributed to `Speaker 1`.
The database column exists, so diarization can be added later without a migration.

---

## 14. How RAG works

Asking a question never sends the whole transcript to the model. Instead:

```
User question
    -> create query embedding        (sentence-transformers)
    -> retrieve relevant chunks      (ChromaDB, filtered to this meeting)
    -> build context
    -> send context + question       (Ollama)
    -> return answer + sources
```

In detail:

1. **Chunking.** After transcription, consecutive transcript segments are grouped into
   overlapping chunks — 5 segments per chunk with 1 segment of overlap by default, so a
   sentence spanning a boundary is not lost.
2. **Embedding.** Each chunk is turned into a vector with `all-MiniLM-L6-v2`, a small,
   fast local model.
3. **Storage.** Vectors go into a persistent ChromaDB collection under `data/chroma`.
   Every vector carries `meeting_id`, `speaker`, `start_time` and `end_time`.
4. **Retrieval.** Your question is embedded and the 5 nearest chunks are fetched, with
   the query filtered by `meeting_id` so one meeting can never leak into another.
5. **Answering.** Only those chunks are given to Ollama, with instructions to use
   nothing else.

If the transcript does not contain the answer, the reply is exactly:

> I couldn't find that information in this meeting.

Every answer is returned with the transcript excerpts it was based on, each with its
speaker and timestamp, so you can check it.

Questions that work well:

- "What were the main topics?"
- "What decisions were made?"
- "What action items were assigned?"
- "Why was this approach selected?"
- "Give me a short summary."

---

## 15. API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check; reports the configured models |
| `POST` | `/api/meetings` | Upload audio and create a meeting (multipart: `title`, `description`, `file`) |
| `GET` | `/api/meetings` | List meetings, newest first |
| `GET` | `/api/meetings/search?q=...` | Keyword search across all transcripts |
| `GET` | `/api/meetings/{meeting_id}` | Get one meeting |
| `POST` | `/api/meetings/{meeting_id}/process` | Start transcription, summary and indexing (returns `202`) |
| `GET` | `/api/meetings/{meeting_id}/transcript` | Transcript segments |
| `GET` | `/api/meetings/{meeting_id}/summary` | Summary, key points, decisions, action items |
| `GET` | `/api/meetings/{meeting_id}/audio` | Stream the stored recording |
| `POST` | `/api/meetings/{meeting_id}/chat` | Ask a question (body: `{"question": "..."}`) |
| `DELETE` | `/api/meetings/{meeting_id}` | Delete the meeting, its audio and its vectors |

Notable status codes:

| Code | When |
|---|---|
| `400` | Unsupported audio format, empty file, or missing audio on disk |
| `404` | Unknown meeting, or no summary generated yet |
| `409` | Processing already running, or chat attempted before `COMPLETED` |
| `413` | File larger than `MAX_UPLOAD_SIZE_MB` |
| `503` | Ollama is unreachable during a chat request |

Full interactive documentation is at <http://localhost:8000/docs>.

---

## 16. Testing

```powershell
cd D:\Projects\MeetingAI\backend
```

```powershell
.venv\Scripts\Activate.ps1
```

```powershell
pytest -q
```

The suite covers the health endpoint, meeting creation, listing, retrieval and
deletion, invalid uploads (wrong extension, empty file, oversized file), database
operations and the status lifecycle, transcript search, transcript chunking, the
summarisation service (including invalid-JSON retry and fallback), the RAG service
(including the no-answer case) and the full processing pipeline.

**The tests never require Ollama or Whisper to be running.** Every AI service is
mocked, and each test uses a temporary in-memory SQLite database and a temporary
audio directory.

Run a single file or test:

```powershell
pytest tests/test_rag.py -v
```

---

## 17. Troubleshooting

**`pip install` fails with "no matching distribution" for faster-whisper or chromadb**
You are on Python 3.13 or 3.14. Recreate the environment with 3.11 or 3.12:

```powershell
Remove-Item -Recurse -Force .venv; py -3.12 -m venv .venv; .venv\Scripts\Activate.ps1; pip install -r requirements.txt
```

**`.venv\Scripts\Activate.ps1` cannot be loaded — running scripts is disabled**

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**Summary or chat fails with "Could not reach the Ollama model"**
Ollama is not running or the model is missing:

```powershell
ollama serve
```

```powershell
ollama pull llama3.2
```

**The meeting status is FAILED**
Open the meeting — the exact error is shown on the page and stored in
`meetings.error_message`. Use **Run processing again** after fixing the cause.

**The first upload takes a very long time**
Model weights are being downloaded (~500 MB for Whisper `small`, ~90 MB for the
embedding model). This happens once. Use a smaller model to speed things up:

```powershell
$env:WHISPER_MODEL = "base"
```

**"No speech was detected in the audio file"**
The recording is silent or unreadable. Try converting it to wav first.

**Transcription is very slow on CPU**
Use a smaller Whisper model (`base` or `tiny`), or switch to GPU by setting
`WHISPER_DEVICE=cuda` and `WHISPER_COMPUTE_TYPE=float16` in `backend\.env`.

**Port 8000 or 5173 already in use**

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object OwningProcess
```

Then stop that process, or start uvicorn with `--port 8001`.

**Frontend loads but every request fails**
The backend is not running. Vite proxies `/api` and `/health` to
`http://localhost:8000`; start the backend and reload.

**Chat says it cannot find the information even though it was discussed**
The relevant chunk was not retrieved. Rephrase using words actually spoken, or raise
`RAG_TOP_K` in `backend\.env`.

**Reset everything**

```powershell
cd D:\Projects\MeetingAI; Remove-Item backend\meetingai.db -ErrorAction Ignore; Remove-Item -Recurse -Force data\chroma\* -ErrorAction Ignore; Remove-Item -Recurse -Force storage\audio\* -ErrorAction Ignore
```

---

## 18. Configuration reference

Settings live in `backend\.env` (copy `backend\.env.example`). Environment variables
override the file. `.env` is git-ignored.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./meetingai.db` | SQLAlchemy connection string |
| `WHISPER_MODEL` | `small` | `tiny`, `base`, `small`, `medium`, `large-v3` |
| `WHISPER_DEVICE` | `cpu` | Set to `cuda` for an NVIDIA GPU |
| `WHISPER_COMPUTE_TYPE` | `int8` | Use `float16` on CUDA |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server address |
| `OLLAMA_MODEL` | `llama3.2` | Any model you have pulled |
| `OLLAMA_TIMEOUT_SECONDS` | `300` | Per-request timeout |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model |
| `CHROMA_COLLECTION` | `meeting_transcripts` | ChromaDB collection name |
| `RAG_CHUNK_SIZE` | `5` | Transcript segments per chunk |
| `RAG_CHUNK_OVERLAP` | `1` | Overlapping segments between chunks |
| `RAG_TOP_K` | `5` | Chunks retrieved per question |
| `MAX_UPLOAD_SIZE_MB` | `200` | Upload size limit |
| `ALLOWED_AUDIO_EXTENSIONS` | `mp3,wav,m4a,mp4,webm` | Accepted formats |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated allowed origins |

---

## 19. Docker (optional)

Docker is **not** required — local Windows development is the primary setup.

A `docker-compose.yml` is provided that containerises the backend only. Ollama stays on
the host, because containerising it complicates GPU access and model management for no
benefit here; the backend reaches it through `host.docker.internal`.

```powershell
cd D:\Projects\MeetingAI
```

```powershell
docker compose up --build
```

Run the frontend on the host as usual with `npm run dev`.

---

## Project structure

```
MeetingAI/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app, /health, startup
│   │   ├── config.py            Pydantic settings
│   │   ├── database.py          Engine, session, init_db()
│   │   ├── models/meeting.py    SQLAlchemy models and MeetingStatus
│   │   ├── schemas/meeting.py   Pydantic request/response models
│   │   ├── api/meetings.py      All meeting endpoints
│   │   └── services/
│   │       ├── transcription.py      faster-whisper
│   │       ├── ollama.py             reusable Ollama client
│   │       ├── summarization.py      structured summary + validation
│   │       ├── embeddings.py         chunking, embeddings, ChromaDB
│   │       ├── rag.py                retrieval and grounded answering
│   │       └── meeting_processor.py  pipeline orchestration
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/    MeetingList, MeetingUpload, Transcript, Summary, Chat
│   │   ├── pages/         Dashboard, MeetingDetails
│   │   ├── services/      api.js
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css
│   ├── package.json
│   └── vite.config.js
├── storage/audio/         uploaded recordings (git-ignored)
├── data/chroma/           vector store (git-ignored)
├── docs/architecture.md
├── scripts/start-dev.ps1
├── docker-compose.yml
└── README.md
```
