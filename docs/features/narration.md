<!-- last_verified: 2026-06-03 -->
# Feature: Chapter Narration

## Purpose
Turn a manuscript into a chapterized audiobook: split it into chapters, render each
chapter with a TTS provider, and assemble a final master — all stored in B2.

## Used By
- UI: `/create` (New Audiobook studio), `/library` (progress + playback)
- API: `POST /books` (create + kick off), `GET /books/{id}` (poll progress)
- Job: `service.narration.run_narration` (FastAPI BackgroundTask, in-process)

## Core Functions
- `services/api/app/service/narration.py` — `create_book()`, `run_narration()`, `list_voices()`
- `services/api/app/service/chapters.py` — `split_into_chapters()`
- `services/api/app/repo/tts/` — provider-agnostic synthesis (`get_provider().synthesize()`)
- `services/api/app/repo/books_store.py` — `put_bytes`, `read_json`/`write_json`
- `services/api/app/runtime/books.py` — book router

## Canonical Files
- Job orchestration: `services/api/app/service/narration.py`

## Inputs
- `CreateBookRequest`: title (1–200 chars), text (manuscript), voice_id (optional)

## Outputs
- `audiobooks/<id>/source.txt`, `audiobooks/<id>/manifest.json`,
  `audiobooks/<id>/chapters/ch-NNN.mp3`, `audiobooks/<id>/master.m4b`
- `BookDetail` (status, chapters, durations, master_key) via `GET /books/{id}`
- Side effects: many B2 writes; the manifest is rewritten after each step

## Flow
- `POST /books` → split into chapters, pick voice, write `source.txt` + initial
  manifest (status `pending`), return `202`, schedule `run_narration` in the background
- `run_narration`: status `rendering` → repopulate each chapter's text by re-reading
  `source.txt` and re-running the deterministic `split_into_chapters` (the manifest
  excludes chapter `text`, so it is `""` after a manifest reload) → per chapter:
  `synthesize` → write MP3 → read duration (mutagen) → rewrite manifest
- All chapters done → status `assembling` → assemble M4B → write `master.m4b` →
  status `complete`
- A single narrator voice narrates the whole book (multi-voice is out of scope for v1)

## Edge Cases
- Empty manuscript → `400` (no chapters produced)
- Missing/invalid TTS key → `502` on create or chapter marked failed at render time
- TTS failure mid-job → book status `failed` with the error recorded in the manifest
- ffmpeg missing → chapters still complete; book is `complete` with a "master skipped" note
- Missing `source.txt` at narration time → book status `failed` (text cannot be repopulated)
- Server restart → in-flight job is lost (chapters already in B2 survive; see RELIABILITY)

## UX States
- Studio: form validation, "Starting…" on submit
- Library detail: `GeneratingLoader` while in flight; status badge; per-chapter status

## Verification
- Test files: `services/api/tests/test_narration.py`, `services/api/tests/test_chapters.py`, `services/api/tests/test_books.py`
- Required cases: create writes source+manifest, full render+master, chapter text
  repopulated from source.txt before synthesize (non-empty), missing source → failed,
  TTS failure → failed, voice listing
- Quick verify command: `pnpm test:api`
- Full verify command: `pnpm lint && pnpm lint:api && pnpm test:api && pnpm check:structure`
- Pass criteria: pytest green, ruff clean

## Related Docs
- [Chapter Detection](chapter-detection.md)
- [Master Assembly](master-assembly.md)
- [Library](library.md)
- [docs/RELIABILITY.md](../RELIABILITY.md)
