<!-- last_verified: 2026-06-25 -->
# Reliability

Reliability expectations and practices for this project.

## Narration Jobs (durable queue)

- Narration runs through Redis/RQ. `POST /books` writes `source.txt` and
  `manifest.json`, then enqueues a stable `narration:<book-id>` job for the worker.
- The API process no longer owns in-flight work. If the API restarts, queued jobs
  remain in Redis and the worker keeps using the manifest in B2 as the source of truth.
- Worker startup scans manifests for books in `pending`, `rendering`, and
  `assembling` under a Redis scan lease, then re-enqueues them. The scan is bounded
  and isolated in a background thread so queue consumption can start immediately.
- `run_narration` skips chapters already marked `complete` with an `audio_key`; pending,
  rendering, or failed chapters are retried from the durable source manuscript.
- Workers acquire a per-book Redis lease before rendering and refresh it after each
  manifest/object write. Duplicate jobs exit when the lease is busy.
- TTS failures raise back to RQ while retries remain; only the final exhausted attempt
  marks the book `failed`.
- DELETE writes a short-lived Redis tombstone and cancels any queued job before
  removing B2 objects. Running workers check the tombstone before writes.
- **What survives**: everything already written to B2 — `source.txt`, the manifest, and
  every chapter MP3 rendered so far. Reruns resume from that per-chapter state rather
  than starting over.

## Manifest Durability

- `manifest.json` is the single record of truth and is rewritten (a full `put_object`)
  after every step, so a crash leaves a consistent, readable snapshot of progress.
- If ffmpeg is unavailable, chapters still complete and the book is marked `complete`
  with a note in `book.error`; the master can be assembled later once ffmpeg is present.

## Rollout Safety

- Deploy the API version that enqueues Redis/RQ jobs and remove old API instances that
  can still start FastAPI `BackgroundTasks` before enabling worker resume scans.
- Keep Redis private to the API and worker network and require authenticated
  `REDIS_URL`; Redis is part of the trusted control plane for queue metadata.

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
