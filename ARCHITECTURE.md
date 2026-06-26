<!-- last_verified: 2026-06-25 -->
# Architecture

## Components

- **apps/web/** — Next.js 16 frontend (App Router, Tailwind v4, shadcn/ui)
  - New Audiobook studio (`/create`): manuscript input, chapter preview, voice picker
  - Library (`/library`): scoped audiobook explorer + inline `<audio>` streaming player
  - Dashboard (`/`): audiobook + narration metrics, audio-hours chart, recent audiobooks
  - File upload (`/upload`) and full-bucket File browser (`/files`) — kept B2 scaffolding
  - Dark mode via `next-themes`
- **services/api/** — FastAPI backend (layered architecture)
  - Narration job orchestration (split → TTS per chapter → master assembly)
  - Manifest CRUD over B2 (B2 is the sole datastore — no database)
  - Durable Redis/RQ queue for narration workers
  - Provider-agnostic TTS adapter (OpenAI default, ElevenLabs alt)
  - ffmpeg M4B master assembler (subprocess)
  - B2 S3 integration via boto3 (S3-compatible only — no b2-native API)
  - Metadata extraction (PDF info + audio duration/codec/bitrate; checksums)
  - Health check, structured JSON logging, Prometheus-format metrics
- **packages/shared/** — TypeScript type definitions mirroring the Pydantic models

## B2 Key Layout (single bucket, per-book prefix)

```
audiobooks/<book-id>/source.txt          uploaded/pasted manuscript
audiobooks/<book-id>/manifest.json       job + chapter state — the record of truth
audiobooks/<book-id>/chapters/ch-001.mp3 per-chapter TTS renders (ch-NNN.mp3)
audiobooks/<book-id>/master.m4b          final chapterized master (ffmpeg)
uploads/<file>                           generic Upload page (kept, unchanged)
```

There is **no database**. Each book's `manifest.json` is the durable record of job
and chapter state; the API reads and rewrites it after every step.

## Backend Layering

The API follows a strict layered architecture:

```
types/     Pydantic models — no logic, no imports from other layers
  |
config/    Settings (pydantic-settings) — depends only on types
  |
repo/      Data access / external tools (boto3 B2, TTS SDKs, ffmpeg) — no business logic
  |
service/   Business logic — calls repo, returns types
  |
runtime/   FastAPI routes — calls service, never repo directly
```

### Layering Rules

1. Dependencies flow downward only: `types` -> `config` -> `repo` -> `service` -> `runtime`
2. No backward imports (e.g., service must not import from runtime)
3. `boto3` only allowed in `repo/` layer — and so are the TTS SDKs and ffmpeg
4. All boundary data uses Pydantic models (no raw dicts across layers)
5. Each file stays under 300 lines

### External-tool containment

Every external dependency is wrapped in a `repo/` adapter, mirroring the boto3 rule:

- **boto3 / B2** — `repo/b2_client.py` (single S3 client) and `repo/books_store.py`
- **TTS SDKs** — `repo/tts/` (`base.py` interface, `openai_provider.py` default,
  `elevenlabs_provider.py` alt). Each adapter **lazy-imports its own SDK**, so only
  the active provider's package needs installing. Selected by `TTS_PROVIDER`.
- **ffmpeg** — `repo/audio_master.py`, invoked via `subprocess` to build the M4B master.
- **Redis/RQ** — `repo/job_queue.py`, used only for durable narration job enqueueing
  and worker execution. Jobs use RQ's JSON serializer and a restricted worker that
  accepts only the stable narration target with a UUID book id.

### Directory Structure

```
services/api/
  main.py                  App entrypoint, middleware, router registration
  app/
    types/                 Pydantic models (Book, Chapter, Voice, BookStats, FileMetadata, ...)
    config/                Settings loaded from environment
    repo/                  B2 client + books_store + tts/ + audio_master (data access / tools)
    service/               Business logic (chapters, narration, books, upload, files, metadata)
    runtime/               FastAPI route handlers (books, files, upload, health, metrics)
  tests/                   pytest tests (structural + unit + integration)
```

## Narration Job Flow

1. `POST /books` → `service.narration.create_book`: split manuscript into chapters
   (`service.chapters`), pick the narrator voice, write `source.txt` + an initial
   `manifest.json` (status `pending`), enqueue `run_narration(book.id)` in Redis/RQ,
   return `202`.
2. An RQ worker validates the job target and UUID argument, acquires a per-book
   Redis lease, then runs `run_narration`: status → `rendering`; for each incomplete
   chapter, mark it `rendering`, `tts.synthesize` → `books_store.put_bytes`
   (chapter MP3) → extract duration (mutagen) → mark the chapter `complete` and
   rewrite the manifest. Reruns skip chapters already marked `complete`.
3. All chapters done → status `assembling` → `audio_master.assemble_master` (ffmpeg
   concat + chapter markers) → write `master.m4b` → status `complete`.
4. If ffmpeg is unavailable, chapters remain playable and the book is marked
   `complete` with a note that master assembly was skipped.
5. Worker startup starts queue consumption immediately and runs a bounded, lease-held
   resume scan for `pending`, `rendering`, and `assembling` books.

The frontend polls `GET /books/{id}` (and `GET /books`) via TanStack Query while a
job is in flight, and plays finished chapters from presigned, non-attachment B2 URLs
(`GET /books/{id}/chapters/{n}/stream`), which exercises B2 Range reads.

## Boundary Invariants

- **No external SDK leakage**: `boto3`, the TTS SDKs, and ffmpeg are only used in
  `app/repo/`. Other layers go through repo adapters.
- **No raw dicts at boundaries**: data crossing layers uses typed Pydantic models.
- **No mutable globals**: configuration is read-only after init.
- **Validated inputs**: HTTP inputs validated by FastAPI/Pydantic. File keys validated
  against traversal patterns; book ids validated against a strict UUID pattern before
  forming any B2 key.

## Deployment

- **Local dev** — `pnpm dev` runs web, API, and worker (Web: `localhost:3000`,
  API: `localhost:8000`; Redis is required at `REDIS_URL`)
- **Railway** — web, API, worker, and Redis services; see `infra/railway/README.md`
  (the worker needs the ffmpeg buildpack/apt package for master assembly)

## Data Stores

- **Backblaze B2** — object storage (S3-compatible API), the sole data store
  - Per-book prefix holds source, manifest, chapter audio, and master
  - Listing / metadata via `list_objects_v2` (with `Delimiter` for book folders) /
    `head_object`; reads via `get_object`; writes via `put_object`; batch delete via
    `delete_objects`

## External Services

- **Backblaze B2 S3 API** — storage, retrieval, deletion, presigned URLs
- **Redis** — durable RQ queue for narration jobs
- **TTS provider** — OpenAI (default) or ElevenLabs (alt) for chapter narration

## Trust Boundaries

See [docs/SECURITY.md](docs/SECURITY.md) for full security documentation.

- **Frontend -> API** — CORS-restricted to configured origins
- **API -> B2** — authenticated via application keys, signature v4
- **API -> TTS provider** — provider key read from env, used only in `repo/tts/`
- **Client -> B2** — presigned URLs: attachment for master download, inline (no
  forced disposition) for chapter streaming

## Data Flows

- **Create**: Browser -> `POST /books` -> split + write source/manifest -> enqueue
  RQ job -> 202 -> worker renders chapters and assembles master, rewriting the manifest
- **List / detail**: Browser -> `GET /books` / `GET /books/{id}` -> read manifests
- **Stream**: Browser -> `GET /books/{id}/chapters/{n}/stream` -> presigned inline URL
  -> `<audio>` streams from B2 (Range reads)
- **Download master**: Browser -> `GET /books/{id}/master/download` -> presigned attachment URL
- **Delete**: Browser -> `DELETE /books/{id}` -> `delete_objects` removes the whole prefix

## Observability

- Structured JSON logging on all requests with `request_id`
- Request timing middleware
- `/metrics` endpoint (Prometheus format)
- `/health` endpoint (B2 connectivity check)

## Canonical Files

- Narration orchestration: `services/api/app/service/narration.py`
- Chapter splitting: `services/api/app/service/chapters.py`
- Manifest CRUD: `services/api/app/service/books.py`
- Durable queue adapter: `services/api/app/repo/job_queue.py`
- Worker entrypoint: `services/api/worker.py`
- TTS adapter: `services/api/app/repo/tts/` (`base.py`, `openai_provider.py`, `elevenlabs_provider.py`)
- ffmpeg assembler: `services/api/app/repo/audio_master.py`
- B2 data access (repo layer): `services/api/app/repo/b2_client.py`, `services/api/app/repo/books_store.py`
- Book router: `services/api/app/runtime/books.py`
- Pydantic models: `services/api/app/types/` (`books.py`, `files.py`, `formatting.py`, ...)
- Config (pydantic-settings): `services/api/app/config/settings.py`
- Structural tests: `services/api/tests/test_structure.py`
- Frontend API client: `apps/web/src/lib/api-client.ts`
- Data hooks: `apps/web/src/lib/queries.ts`
- Shared TypeScript types: `packages/shared/src/types.ts`

## Core Features

- [Chapter Narration](docs/features/narration.md)
- [Library](docs/features/library.md)
- [Chapter Detection](docs/features/chapter-detection.md)
- [Master Assembly](docs/features/master-assembly.md)
- [Dashboard](docs/features/dashboard.md)
- [Metadata Extraction](docs/features/metadata-extraction.md)
- [File Upload](docs/features/file-upload.md)
- [File Browser](docs/features/file-browser.md)

## References

- [docs/SECURITY.md](docs/SECURITY.md) — security principles and implementation
- [docs/RELIABILITY.md](docs/RELIABILITY.md) — reliability expectations
- [AGENTS.md](AGENTS.md) — architectural invariants and agent instructions
