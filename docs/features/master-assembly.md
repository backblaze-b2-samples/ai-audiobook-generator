<!-- last_verified: 2026-06-02 -->
# Feature: Master Assembly

## Purpose
Concatenate the per-chapter MP3 renders into a single chapterized **M4B** master with
embedded chapter markers, using ffmpeg.

## Used By
- Job: `service.narration.run_narration` (after every chapter renders)
- UI: `/library` master download button

## Core Functions
- `services/api/app/repo/audio_master.py` — `assemble_master()`, `ffmpeg_available()`
- `services/api/app/service/narration.py` — `_assemble()` orchestrates the call
- `services/api/app/service/books.py` — `master_download_url()`

## Canonical Files
- ffmpeg adapter: `services/api/app/repo/audio_master.py`

## Inputs
- `chapter_audio: list[bytes]` — ordered per-chapter MP3 bytes
- `chapter_meta: list[tuple[title, duration_seconds]]` — parallel ordered list

## Outputs
- M4B (MP4/AAC) bytes with a chapter metadata track, written to `audiobooks/<id>/master.m4b`

## Flow
- After all chapters complete, `_assemble()` reads each chapter MP3 back from B2
- `assemble_master()` writes the MP3s to a temp dir, builds an ffmpeg `concat` list and a
  `;FFMETADATA1` chapter file (TIMEBASE 1/1000, cumulative START/END per chapter), then
  runs `ffmpeg -f concat ... -map_metadata 1 -c:a aac -f mp4 master.m4b` via subprocess
- The resulting bytes are written to B2 and `master_key` is set on the manifest

## Why M4B
M4B is the de-facto audiobook container: players show the chapter list and support
seeking between chapters. The per-chapter MP3s remain in B2 for inline streaming.

## Edge Cases
- ffmpeg not installed → `AudioAssemblyError`; the book is still `complete` (chapters
  playable) with a "master assembly skipped" note in `book.error`
- Missing chapter audio during assembly → `AudioAssemblyError`
- ffmpeg non-zero exit → stderr tail logged, `AudioAssemblyError` raised

## UX States
- Library detail: master download disabled until `master_key` is present

## Verification
- Test files: `services/api/tests/test_narration.py` (master assembly mocked at the repo boundary)
- Required cases: full render assembles a master; assembly is the final step before `complete`
- Quick verify command: `pnpm test:api`
- Full verify command: `pnpm lint && pnpm lint:api && pnpm test:api && pnpm check:structure`
- Pass criteria: pytest green, ruff clean; `pnpm doctor` warns if ffmpeg is missing

## Related Docs
- [Chapter Narration](narration.md)
- [docs/RELIABILITY.md](../RELIABILITY.md)
