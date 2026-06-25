<!-- last_verified: 2026-06-25 -->
# Security

Security principles and implementation for the AI Audiobook Generator.

## Trust Boundaries

- **Frontend -> API**: CORS-restricted to configured origins, scoped to `GET/POST/DELETE/OPTIONS`
- **Audiobook route auth**: `/books` list, create, read, stream, download, and delete
  require `X-Book-Owner` plus `X-Book-Token`. The API validates the token against
  `BOOK_AUTH_TOKENS` and only returns manifests whose stored `owner_id` matches the
  authenticated owner. Legacy manifests without `owner_id` load as `local-dev` for
  local backwards compatibility.
- **API -> B2**: Authenticated via `B2_APPLICATION_KEY_ID` + `B2_APPLICATION_KEY`, signature v4
- **API -> TTS provider**: provider key (`OPENAI_API_KEY` / `ELEVENLABS_API_KEY`) read
  from env and used **only** in `repo/tts/`. It never reaches the client and never
  enters a B2 object or manifest.
- **API / worker -> Redis**: `REDIS_URL` is read from env and used only by the
  queue adapter in `repo/job_queue.py`. It carries job ids, not manuscript text.
- **Client -> B2 (download)**: presigned URLs forcing `Content-Disposition: attachment`
  (master M4B, file downloads)
- **Client -> B2 (stream)**: presigned URLs **without** forced disposition for inline
  `<audio>` chapter playback (see Streaming Safety)

## Upload Validation

- Filename sanitization: path traversal, null bytes, unsafe chars stripped
- MIME/extension consistency check against allowlist
- Chunked streaming with size enforcement (100MB default)
- Content-type allowlist (images, PDFs, text, archives, audio/video)
- Empty file rejection

## Key / ID Validation

- File keys: empty keys rejected; path-traversal patterns rejected (`../`, `%2e%2e`,
  backslashes, null bytes) in `service/files.py::validate_key`
- Book ids: validated against a strict UUID pattern in `service/books.py::validate_book_id`
  **before** they are interpolated into any B2 key, so a request can never escape the
  `audiobooks/<id>/` prefix
- Book ownership is enforced before returning manifest data, issuing presigned
  chapter/master URLs, tombstoning queued work, or deleting an audiobook prefix.
- The bucket is still shared infrastructure. Add B2 application-key prefix scoping if
  your deployment shares the bucket with other workloads.

## Download Safety

- Master / file downloads use presigned URLs that force `Content-Disposition: attachment`,
  preventing inline rendering of user content (XSS mitigation)

## Streaming Safety

- Chapter playback uses presigned URLs **without** forced attachment disposition so the
  browser can stream the MP3 inline into an `<audio>` element (HTTP Range reads).
- This is intentional and safe: the streamed objects are app-generated audio under
  `audiobooks/<id>/chapters/`, not arbitrary user-uploaded HTML/SVG. The generic Upload
  surface still forces attachment on download. URLs are short-lived (10-min expiry).

## Secrets Management

- All secrets (B2 keys, TTS provider keys, Redis credentials) loaded via environment
  variables (pydantic-settings)
- Never committed to source control
- `.env.example` documents required variables with placeholder values only

## Dependency Integrity

- Production installs use `services/api/requirements.lock` with `--require-hashes`.
- Redis/RQ queue dependencies are pinned and hash-locked to avoid unreviewed resolver
  upgrades in API and worker deploys.

## Agent Security Rules

- Never commit `.env`, credentials, or API keys
- Never weaken validation without explicit instruction
- Never bypass CORS, auth, or input sanitization
- Always validate at system boundaries
