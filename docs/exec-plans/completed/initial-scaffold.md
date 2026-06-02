# Scaffold Plan — `ai-audiobook-generator`

> Fork of **vibe-coding-starter-kit** (`backblaze-b2-samples/vibe-coding-starter-kit`,
> commit `8fc490f`). Source of truth for the build is the fresh clone at
> `.claude/scratch/vcsk-33c93cb0-5516-47ee-b868-aae7fcd02c66/`.
> Stack: pnpm monorepo — Next.js 16 / React 19 / Tailwind v4 / shadcn (`apps/web`)
> + FastAPI / Pydantic v2 / boto3, layered `types→config→repo→service→runtime`
> (`services/api`) + shared TS types (`packages/shared`). This matches the
> "Genblaze (Next.js + FastAPI)" stack the concept asked for.

---

## 1. Purpose

`ai-audiobook-generator` turns a long manuscript (book, blog series, ebook, or
pasted text) into a narrated audiobook: it splits the text into chapters,
renders each chapter with a high-quality TTS provider, and assembles a final
chapterized master — storing the **source text, the per-chapter audio renders,
and the final master all in one Backblaze B2 bucket**. It is built for
developers evaluating B2 as the durable home for large, long-lived AI media
assets. It is a deliberately strong B2 demo because audiobooks are big,
persistent, multi-artifact workloads: it exercises **long-running generation
jobs**, **many-object writes under a per-book prefix**, **B2 as the sole
datastore** (a JSON manifest per book — no database), and **streaming/range
reads** (the browser plays chapter audio straight from presigned B2 URLs).

---

## 2. Architecture delta from vibe-coding-starter-kit

The starter kit is the ceiling. We **keep** all reusable B2 scaffolding,
**trim** what an audiobook app genuinely doesn't need, and **add** the
narration pipeline + a scoped Library explorer.

### KEEP (as-is — do not strip, rename, or replace)
- **UI kit / design system** — `apps/web/src/components/ui/` (shadcn primitives),
  design tokens in `apps/web/src/app/globals.css`, the `/design` page, the
  blaze generating loader. *(starter contract + skill non-negotiable)*
- **File Explorer / full-bucket browse** — `/files` route,
  `apps/web/src/app/files/`, `apps/web/src/components/files/`, and the Files
  sidebar entry. **This is the non-negotiable bucket explorer — it stays.**
- **Upload** — `/upload` route + `apps/web/src/components/upload/` (generic
  drag-and-drop file → `uploads/` prefix). Part of the reusable B2 surface.
- **FastAPI layered architecture** — `types→config→repo→service→runtime`,
  the structural tests (`tests/test_structure.py`: no backward imports, boto3
  only in `repo/`, 300-line file cap, all layers exist), ruff/eslint config.
- **B2 S3 client** — `services/api/app/repo/b2_client.py` (extended, see §ADD;
  stays S3-only, single client, custom UA).
- **Observability** — `/health` (B2 connectivity), `/metrics` (Prometheus),
  JSON logging + request-id timing middleware (`runtime/health.py`,
  `runtime/metrics.py`).
- **Data layer pattern** — TanStack Query hooks in `apps/web/src/lib/queries.ts`,
  `api-client.ts`, `query-client.tsx`, `refresh-context.tsx`. No bare
  `useEffect+fetch`.
- **App shell** — sidebar (`layout/app-sidebar.tsx`), header, theme provider,
  command palette, health banner, error/empty states, Settings page.
- **Tooling** — `scripts/doctor.mjs` (preflight, extended), `scripts/dev.sh`,
  `scripts/pick-port.mjs`, `.pre-commit-config.yaml`, Railway infra config,
  Playwright e2e harness, AGENTS.md control-surface + `docs/exec-plans/` layout.

### TRIM (remove from the starter)
- **Image/EXIF metadata extraction** — drop `_extract_image_metadata()` and the
  `Pillow` dependency from `services/api/requirements.txt`; remove
  `image_width` / `image_height` / `exif` from `FileMetadataDetail`
  (`packages/shared/src/types.ts` + `services/api/app/types/files.py`) and the
  image block in `components/files/file-metadata-panel.tsx`. *(An audiobook app
  ingests text and emits audio; image EXIF is dead weight.)* **Keep** PDF
  metadata (ebook sources) and checksums.
- **Demo dashboard widgets** — the generic "uploads today / upload activity by
  file count / recent uploads" framing in `components/dashboard/` is replaced
  (see ADAPT). Charts/cards/table components are reused as shells.
- **Starter screenshots** — `docs/images/b2-starterkit-dashboard1.png` and
  `b2-starterkit-fileview2.png`, plus their README references. New screenshots
  are **binary assets → deferred** per skill rule (do not generate; README gets
  a short "screenshots coming" note / text-only intro).
- **Starter exec-plan history** — delete `docs/exec-plans/completed/2026-02-*`
  and `2026-02-14-*` (starter-kit history, not ours); keep the
  `docs/exec-plans/` + `completed/` + `tech-debt-tracker.md` structure (reset
  tracker to a clean state). The scaffold plan lands in `completed/` at
  finalize (Phase 5).

### ADAPT (rewrite for the new use case)
- **Dashboard** (`/`, `components/dashboard/`) — replace metrics with:
  *Total Audiobooks*, *Chapters Rendered*, *Hours Narrated*, *Storage Used*
  (stats-cards); *Audio hours generated / day* (chart, reuse `upload-chart`
  shell via a new `/books/stats/activity` endpoint); *Recent Audiobooks*
  (title · chapters · duration · status · created) replacing recent-uploads.
  All aggregations flow through `runtime→service→repo` and TanStack Query.

### ADD (new for `ai-audiobook-generator`)

**B2 key layout (single bucket, per-book prefix):**
```
uploads/<file>                          # generic Upload page (kept, unchanged)
audiobooks/<book-id>/source.txt         # uploaded/pasted manuscript
audiobooks/<book-id>/manifest.json      # job + chapter state  →  B2 IS the datastore
audiobooks/<book-id>/chapters/ch-001.mp3 … ch-NNN.mp3   # per-chapter renders
audiobooks/<book-id>/master.m4b         # final chapterized master (format per decision)
```

**Backend — `services/api/`**
- `repo/b2_client.py` (extend, S3-only): add `read_object(key)->bytes`,
  `write_json(key, obj)` / `read_json(key)->dict` (manifest + source via
  `put_object`/`get_object`), `get_stream_url(key)` (presigned GET **without**
  forced-attachment disposition, for inline `<audio>` streaming → exercises B2
  Range reads), `delete_prefix(prefix)` (list + `delete_objects` batch, for
  "delete audiobook"), `list_prefixes(prefix)` (list with `Delimiter="/"` →
  `CommonPrefixes` = book folders). Pass `region_name=settings.b2_region`.
- `repo/tts/` — **provider-agnostic TTS adapter** (external SDK contained in
  `repo/`, mirroring the boto3 rule): `base.py` (`Voice`, `synthesize()` iface),
  **`openai.py` (default)**, `elevenlabs.py` (alt), selected by `TTS_PROVIDER`
  (default `openai`). SDKs are **lazy-imported per adapter** (like the starter's
  Pillow/PyPDF2), so only the active provider's package needs installing.
  `list_voices()` + `synthesize(text, voice_id) -> bytes`.
- `repo/audio_master.py` — ffmpeg adapter (external tool contained in `repo/`):
  concat per-chapter audio + embed chapter markers → **chapterized M4B master**.
  Invoked via `subprocess`.
- `service/chapters.py` — split source text into chapters: honor explicit
  markers (`Chapter N`, `# Heading`, `---`) and fall back to size-based
  chunking; produce ordered `[{index,title,text,char_count}]`.
- `service/narration.py` — orchestrate a job with a **single narrator voice**:
  write `source.txt` + initial `manifest.json` (status `pending`), then per
  chapter → `tts.synthesize` → `b2.put_object` → extract duration → update +
  rewrite manifest; on all-done → `audio_master.assemble` → write `master.m4b`
  → status `complete`. Run via FastAPI `BackgroundTasks` (in-process;
  documented limitation in RELIABILITY).
- `service/books.py` — manifest CRUD over B2: `create_book`, `get_book`,
  `list_books` (scan `audiobooks/` prefixes → read each manifest),
  `delete_book`, `book_stats` / `book_activity` (dashboard).
- `runtime/books.py` (new router) — `POST /books` (create + kick off narration),
  `GET /books`, `GET /books/{id}`, `DELETE /books/{id}`,
  `GET /books/{id}/master/download` (presigned attachment),
  `GET /books/{id}/chapters/{n}/stream` (presigned inline), `GET /voices`,
  `GET /books/stats` + `GET /books/stats/activity`. Register in `main.py`.
- `types/books.py` — Pydantic models: `Book`, `Chapter`, `NarrationStatus`
  (enum), `Voice`, `CreateBookRequest`, `BookStats`. Reuse
  `types/formatting.humanize_bytes`.
- `service/metadata.py` — add `_extract_audio_metadata()` via **`mutagen`**
  (populate `duration_seconds`/`codec`/`bitrate`; lightweight, no ffmpeg needed
  to read headers); remove image branch (see TRIM).
- `config/settings.py` — add `b2_region`, `tts_provider`, `tts_api_key`,
  `tts_default_voice`; rename `b2_key_id`→`b2_application_key_id` (see §3).
- Tests: `test_chapters.py` (chunking + markers),
  `test_narration.py` (orchestration with a mocked TTS adapter),
  `test_books.py` (manifest round-trip, key-prefix validation), update
  `test_metadata.py` (audio path, image removed). Keep all structural tests green.

**Frontend — `apps/web/`**
- `app/create/page.tsx` + `components/studio/` — **New Audiobook** flow: paste or
  upload manuscript, detected-chapter preview/edit, **narrator-voice picker**
  (`/voices`), "Generate" → `POST /books` → progress via polling.
- `app/library/page.tsx` + `components/library/` — **scoped asset explorer**
  (skill non-negotiable ADD): grid of audiobooks (scoped to `audiobooks/`),
  per-book detail with chapter list + HTML5 `<audio>` player streaming from
  presigned B2 URLs, job-status badges, master download, delete.
- `lib/api-client.ts` + `lib/queries.ts` — add `useBooks`, `useBook(id)`,
  `useCreateBook`, `useDeleteBook`, `useVoices`, book-stats hooks (polling for
  in-flight jobs).
- `packages/shared/src/types.ts` — add `Book`, `Chapter`, `Voice`,
  `NarrationStatus`, `BookStats`, `CreateBookRequest` (mirror Pydantic).
- `components/layout/app-sidebar.tsx` — nav becomes **Dashboard · New Audiobook
  (`/create`) · Library (`/library`) · Upload · Files · Settings**; Reference:
  Design System. Header brand → "AI Audiobook Generator".

---

## 3. B2 surface (S3 operations)

All operations are **S3-compatible — no b2-native API anywhere** (Standard #1 ✓).

| Operation | S3 call | Used for |
|-----------|---------|----------|
| connectivity | `head_bucket` | `/health` |
| write source/manifest/audio | `put_object` | source.txt, manifest.json, chapter mp3, master |
| read source/manifest | `get_object` | manifest + source (new `read_object`/`read_json`) |
| list (paginated) | `list_objects_v2` | Files explorer, stats, library scan |
| list book folders | `list_objects_v2` + `Delimiter="/"` | Library (CommonPrefixes) |
| object metadata | `head_object` | file detail |
| presigned download | `generate_presigned_url` (attachment) | master/chapter download |
| presigned stream | `generate_presigned_url` (inline) | `<audio>` chapter playback (Range reads) |
| delete one | `delete_object` | file delete |
| delete a book | `delete_objects` (batch) | delete all keys under `audiobooks/<id>/` |

- **Single boto3 S3 client** (`functools.lru_cache`), `signature_version="s3v4"`,
  `region_name=settings.b2_region`, **`user_agent_extra="b2ai-audiobook-generator"`**
  (custom UA on every client — Standard #2 ✓; see §6 for tag rationale).
- boto3 stays **only** in `repo/` (structural test enforces). TTS SDK + ffmpeg
  are likewise contained in `repo/`.

---

## 4. Key features (seed README + `docs/features/*`)

1. **Chapter narration** — manuscript → chapters → per-chapter TTS audio in B2.
2. **Library** — scoped explorer of your audiobooks with an inline streaming
   player and one-click master download.
3. **Chapter detection** — marker-aware + size-based splitting of long text.
4. **Voice selection** — pick a narrator voice from the provider's catalog
   (`GET /voices`); the whole book is narrated in that voice. (Multi-voice is a
   documented future enhancement.)
5. **Master assembly** — chapterized **M4B** master via ffmpeg.
6. **File Upload + Explorer** — the kept B2 scaffolding (generic upload +
   full-bucket browse), unchanged.

---

## 5. Doc transforms

| Starter doc | Action |
|-------------|--------|
| `README.md` | **Rewrite** — audiobook concept, features, setup (B2 + TTS key + ffmpeg), quick start. Drop screenshot refs (binary assets deferred). |
| `AGENTS.md` | **Rewrite §1 map + §2** (this *is* the app now; §2 documents app structure & the keep/adapt surfaces). Invariants (§3–5) stay. Add audiobook feature pointers. |
| `ARCHITECTURE.md` | **Rewrite** — add narration-job flow, TTS adapter, manifest-as-datastore, master assembly, B2 key layout; keep layering section. |
| `docs/features/file-upload.md` | **Keep**, light edit. |
| `docs/features/file-browser.md` | **Keep** (Files explorer retained). |
| `docs/features/dashboard.md` | **Rewrite** for audiobook metrics. |
| `docs/features/metadata-extraction.md` | **Rewrite** — drop image, keep PDF, add audio. |
| `docs/features/narration.md` | **New** (text→chapters→TTS→audio). |
| `docs/features/library.md` | **New** (scoped explorer + player). |
| `docs/features/chapter-detection.md` | **New** (chunking rules). |
| `docs/features/master-assembly.md` | **New** (format + ffmpeg). |
| `docs/app-workflows.md` | **Rewrite** journeys (create → listen → download). |
| `docs/dev-workflows.md` | **Edit** — TTS-mock testing, ffmpeg note, updated e2e cmd. |
| `docs/SECURITY.md` | **Edit** — TTS key handling, presigned inline-stream URLs. |
| `docs/RELIABILITY.md` | **Edit** — in-process job limitation + manifest durability. |
| `docs/design-system.md` | **Keep**. |
| `CODE_REVIEW.md` | **Keep**, light branding edit. |
| `infra/railway/README.md` | **Edit** — service names, TTS env vars, ffmpeg buildpack note. |
| `docs/exec-plans/completed/*` (starter) | **Delete**; keep structure + reset `tech-debt-tracker.md`. |
| `docs/features/_template.md` | **Keep** (template). |

---

## 6. Rename table

| Form | From | To |
|------|------|----|
| kebab slug | `vibe-coding-starter-kit` | `ai-audiobook-generator` |
| npm scope (web) | `@vibe-coding-starter-kit/web` | `@ai-audiobook-generator/web` |
| npm scope (shared) | `@vibe-coding-starter-kit/shared` | `@ai-audiobook-generator/shared` |
| Title Case display | `Vibe Coding Starter Kit` | `AI Audiobook Generator` |
| sidebar brand text | `OSS Starter Kit` | `AI Audiobook Generator` |
| header breadcrumb | `oss-starter-kit` | `ai-audiobook-generator` |
| FastAPI `title` | `OSS Starter Kit API` | `AI Audiobook Generator API` |
| clone URL in README | `…/vibe-coding-starter-kit.git` | `…/ai-audiobook-generator.git` |
| **UA `user_agent_extra`** | `b2ai-oss-start` | **`b2ai-audiobook-generator`** |
| **UTM `utm_content`** (all links) | `b2ai-oss-start` | **`b2ai-audiobook-generator`** |
| snake_case package | *(none — no Python package name declared)* | n/a |
| Docker/image tags | *(none present)* | n/a |
| GitHub workflow slugs | *(no `.github/` present)* | n/a |

Files touched by the rename (from the identifier sweep): root `package.json`
(name + 6 filter scripts), `packages/shared/package.json`, `apps/web/package.json`
(name + dep), `apps/web/next.config.ts` (transpilePackages), 8 TS import sites of
`@vibe-coding-starter-kit/shared`, `README.md`, `docs/dev-workflows.md`,
`docs/SECURITY.md`, `services/api/main.py` (FastAPI title + the `B2_KEY_ID`
reference, see below), `services/api/app/repo/b2_client.py` (UA),
`app-sidebar.tsx` (brand + UTM), `header.tsx` (breadcrumb), `scripts/doctor.mjs` (UTM).

**UA/UTM tag rationale:** the parent convention is `b2ai-<name>`; the starter's
value `b2ai-oss-start` uses a short descriptive name, not the repo slug. I use
**`b2ai-audiobook-generator`** (short, descriptive, no redundant double-"ai").
*Flagged for confirmation.*

---

## 7. Deliberate deviation from the starter — env-var standardization (needs sign-off)

The starter uses `B2_KEY_ID` and has no `B2_REGION`. The **parent CLAUDE.md
Standard #3** mandates `B2_APPLICATION_KEY_ID`, `B2_APPLICATION_KEY`,
`B2_BUCKET_NAME`, `B2_REGION`, `B2_ENDPOINT`, and `/b2-doctor` audits for exactly
those. To pass review, the new sample will:
- rename `B2_KEY_ID` → **`B2_APPLICATION_KEY_ID`** (`.env.example`, `settings.py`,
  `main.py` required-settings + placeholder lists, `b2_client.py`, README,
  `doctor.mjs`);
- add **`B2_REGION`** (passed as `region_name` to the boto3 client);
- keep `B2_ENDPOINT`, `B2_APPLICATION_KEY`, `B2_BUCKET_NAME`; keep optional
  `B2_PUBLIC_URL`.
- App-specific new env: `TTS_PROVIDER` (default `openai`), `OPENAI_API_KEY`
  (default provider), `ELEVENLABS_API_KEY` (optional alt), `TTS_DEFAULT_VOICE`.

---

## 8. Decisions (RESOLVED — confirmed by user)

1. **TTS provider** — ✅ **OpenAI TTS default**, provider-agnostic adapter with
   ElevenLabs as a drop-in alt (SDKs lazy-imported per adapter).
2. **Output format** — ✅ per-chapter **MP3 + a chapterized M4B master**
   (requires ffmpeg).
3. **Multi-voice dialogue** — ✅ **single narrator only**; multi-voice /
   per-speaker narration is **out of scope for v1** (documented as future).
4. **UA/UTM tag** — ✅ `b2ai-audiobook-generator`.

---

## 9. New dependencies

- **add (Python):** `openai` (default TTS provider), `mutagen` (audio duration
  metadata). `httpx` already present. `elevenlabs` is the optional alt provider
  — **not** in `requirements.txt`; lazy-imported, documented as
  `pip install elevenlabs` if you set `TTS_PROVIDER=elevenlabs`.
- **remove (Python):** `Pillow` (image metadata trimmed).
- **system prereq:** `ffmpeg` (M4B master assembly) — documented in README +
  checked by `doctor.mjs`.

---

## 10. Out of scope for v1
- Multi-voice / per-speaker narration (single narrator only; future enhancement).
- Durable job queue (in-process `BackgroundTasks`; restart loses in-flight jobs).
- Generating screenshots / logos (binary assets — deferred per skill rule).
- Auth / multi-tenant (single bucket, single user, like the starter).
