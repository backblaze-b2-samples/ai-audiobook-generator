<!-- last_verified: 2026-06-25 -->
# Reliability

Reliability expectations and practices for this project.

## Narration Jobs (durable queue)

- Narration runs through Redis/RQ. `POST /books` writes `source.txt` and
  `manifest.json`, then enqueues a stable `narration:<book-id>` job for the worker.
- The API process no longer owns in-flight work. If the API restarts, queued jobs
  remain in Redis and the worker keeps using the manifest in B2 as the source of truth.
- Worker startup scans manifests for books in `pending`, `rendering`, and
  `assembling`, then re-enqueues them. This covers deploys or worker restarts where
  Redis no longer has an active job but B2 still shows incomplete work.
- `run_narration` skips chapters already marked `complete` with an `audio_key`; pending,
  rendering, or failed chapters are retried from the durable source manuscript.
- **What survives**: everything already written to B2 — `source.txt`, the manifest, and
  every chapter MP3 rendered so far. Reruns resume from that per-chapter state rather
  than starting over.

## Manifest Durability

- `manifest.json` is the single record of truth and is rewritten (a full `put_object`)
  after every step, so a crash leaves a consistent, readable snapshot of progress.
- If ffmpeg is unavailable, chapters still complete and the book is marked `complete`
  with a note in `book.error`; the master can be assembled later once ffmpeg is present.

## Health Checks

- `GET /health` verifies B2 connectivity and returns `healthy` or `degraded`
- Health endpoint is always available, even when B2 is down

## Error Handling

- HTTP handlers return structured error responses with appropriate status codes
- External service failures (B2) are caught and surfaced as 500/503 responses
- No unhandled exceptions leak stack traces to clients

## Logging

- Structured JSON logging via Python stdlib
- Every request gets a `request_id` for tracing
- Log levels: ERROR for failures, WARNING for degraded state, INFO for requests

## Observability

- Request timing middleware logs duration for every request
- `/metrics` endpoint exposes basic Prometheus-format counters
- Upload success/failure counts tracked

## Graceful Degradation

- Listing returns an empty list (not an error) when B2 has no objects
- Metadata extraction failures don't block upload (return partial metadata)
- A single chapter TTS failure marks the book `failed` with the error recorded; chapters
  already rendered remain in B2 and playable
- Missing ffmpeg degrades to "chapters only" rather than failing the whole job
- Frontend shows skeleton states while loading and inline `ErrorState` on failure

## Deployment

- Railway health checks on `/health`
- Zero-downtime deploys via rolling updates
- Environment-specific configuration via env vars (no config files in prod)
