# Issue 1: Durable Narration Jobs

## Goal

Replace in-process FastAPI background narration with a durable Redis/RQ queue so
jobs survive API restarts and can resume from the manifest's per-chapter status.

## Scope

- Add a queue adapter in the repo layer and settings for Redis/RQ.
- Enqueue narration jobs from `POST /books` instead of `BackgroundTasks`.
- Add a worker entrypoint that re-enqueues incomplete books before processing.
- Keep `run_narration` idempotent by skipping complete chapters and persisting
  chapter state before each render.
- Update tests and docs for the new worker/queue flow.

## Verification

- `pnpm lint`
- `pnpm lint:api`
- `pnpm test:api`
- `pnpm check:structure`

## Result

Implemented Redis/RQ narration queueing, worker startup resume scanning, and
manifest-based chapter resume behavior for issue #1.
