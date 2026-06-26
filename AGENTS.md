<!-- last_verified: 2026-06-25 -->
# AGENTS.md

This is the authoritative control surface for all coding agents. Read this first.

## 1. Repository Map

```
apps/web/          Next.js 16 frontend (App Router, Tailwind v4, shadcn/ui)
  src/app/create/    New Audiobook studio (manuscript -> chapters -> generate)
  src/app/library/   Scoped audiobook explorer + inline streaming player
  src/components/studio/   New-audiobook form, voice picker, chapter preview
  src/components/library/  Audiobook grid, detail, chapter player, status badge
  src/components/dashboard/  Audiobook + narration metrics
  src/components/files/    Full-bucket File Explorer (kept B2 scaffolding)
  src/components/upload/   Generic upload (kept B2 scaffolding)
services/api/      FastAPI backend (layered: types/config/repo/service/runtime)
  app/repo/tts/        Provider-agnostic TTS adapter (openai default, elevenlabs alt)
  app/repo/audio_master.py  ffmpeg M4B assembler (subprocess)
  app/repo/job_queue.py    Redis/RQ durable narration queue adapter
  app/repo/books_store.py   B2 access for the audiobook domain
  app/service/         chapters (split), narration (job), books (manifest CRUD)
packages/shared/   Shared TypeScript types (mirror the Pydantic models)
docs/              System of record (features, workflows, security, reliability)
docs/exec-plans/   Execution plans and tech debt tracker
infra/railway/     Deployment config
```

## 2. App Structure

This **is** the AI Audiobook Generator (forked from `vibe-coding-starter-kit`). The
pieces below are where the app's behavior lives, plus the B2 scaffolding kept from
the starter.

**App surfaces (the audiobook feature set)**
- **New Audiobook studio** — `/create`, `apps/web/src/app/create/` +
  `apps/web/src/components/studio/`. Paste/upload a manuscript, preview detected
  chapters, pick a narrator voice, `POST /books` to start narration.
- **Library** — `/library`, `apps/web/src/app/library/` +
  `apps/web/src/components/library/`. Scoped explorer of `audiobooks/`, an inline
  `<audio>` player streaming chapters from presigned B2 URLs, master download, delete.
- **Dashboard** — `/`, `apps/web/src/components/dashboard/`. Audiobook metrics
  (total audiobooks, chapters rendered, hours narrated, storage used), an
  audio-hours-per-day chart, and recent audiobooks.
- **Backend** — narration job flow in `service/narration.py`, chapter splitting in
  `service/chapters.py`, manifest CRUD in `service/books.py`, the TTS adapter in
  `repo/tts/`, and the ffmpeg master assembler in `repo/audio_master.py`. The book
  router is `runtime/books.py`. **B2 is the sole datastore** — `manifest.json` per
  book; there is no database.

**Kept B2 scaffolding (do not strip, rename, or replace)**
- **UI kit / design system.** `apps/web/src/components/ui/` (shadcn primitives), the
  design tokens in `apps/web/src/app/globals.css`, and the `/design` reference page.
  Build new screens with these primitives; never edit the generated `components/ui/`
  files directly. Restyling happens through tokens in `globals.css`.
- **File Explorer.** `/files` route, `apps/web/src/app/files/`, and
  `apps/web/src/components/files/` — full-bucket browse. The Files sidebar entry stays.
- **Upload.** `/upload` route + `apps/web/src/components/upload/` — generic
  drag-and-drop upload to `uploads/`. The Upload sidebar entry stays.
- The sidebar nav (Dashboard, New Audiobook, Library, Upload, Files, Settings, plus
  the Design System utility link).

**Why the scaffolding stays**
- The UI kit, Files, and Upload pages are the reusable B2-backed surface inherited
  from the starter. New aggregations and screens must flow through the same
  `runtime -> service -> repo` layering and be exposed via TanStack Query hooks in
  `apps/web/src/lib/queries.ts` — no bare `useEffect + fetch`. Update
  `docs/features/<feature>.md` in the same PR as any feature change (see §9).

## 3. Architectural Invariants

**Backend layering**: `types` -> `config` -> `repo` -> `service` -> `runtime`

- No backward imports across layers
- No `boto3` outside `repo/`
- No business logic in route handlers (`runtime/`)
- All external APIs wrapped in `repo/` adapters
- All request/response data validated at boundary (Pydantic models)
- No shared mutable state across layers

**Frontend**: shadcn/ui components in `src/components/ui/` are generated — never modify them.

**Data fetching**: every API call flows through TanStack Query hooks in `apps/web/src/lib/queries.ts`. No bare `useEffect + fetch` patterns. New endpoints touch three files: `runtime/<router>.py`, `lib/api-client.ts`, `lib/queries.ts`.

## 4. Quality Expectations

- **DRY** — do not duplicate logic, types, or constants. Extract shared code only when used in 2+ places.
- Structured JSON logging only — no `print()` statements
- No raw SDK calls outside `repo/` layer
- Files stay under 300 lines
- Tests added or updated for every behavior change
- Docs updated in same PR as code changes
- Lint clean before merge
- Prefer boring, composable libraries over clever abstractions
- No implicit type assumptions — use typed models

## 5. Mechanical Enforcement

| Rule | Enforced by |
|------|-------------|
| No backward imports | `tests/test_structure.py::test_no_backward_imports` |
| No boto3 outside repo/ | `tests/test_structure.py::test_boto3_only_in_repo` |
| File size < 300 lines | `tests/test_structure.py::test_file_size_limits` |
| All layers exist | `tests/test_structure.py::test_all_layers_exist` |
| No bare print() | `ruff` rule T20 |
| Import ordering | `ruff` rule I001 |
| Frontend strict equality | `eslint` rule eqeqeq |
| No unused vars | `eslint` + `ruff` rules |

## 6. Commands

```bash
# Run
pnpm dev               # start frontend, backend, and narration worker
pnpm dev:web           # frontend only
pnpm dev:api           # backend only
pnpm dev:worker        # narration worker only

# Test & Lint
pnpm lint              # frontend lint (eslint)
pnpm build             # frontend type check + build
pnpm lint:api          # backend lint (ruff)
pnpm test:api          # backend tests (pytest)
pnpm check:structure   # structural boundary tests
pnpm test:e2e          # Playwright e2e tests
```

## 7. Agent Workflow

1. Read this file first.
2. Review [ARCHITECTURE.md](ARCHITECTURE.md) before structural changes.
3. For non-trivial changes, create a plan in `docs/exec-plans/active/`.
4. Implement the smallest coherent change.
5. Run: `pnpm lint && pnpm lint:api && pnpm test:api && pnpm check:structure`
6. Update docs in the same PR (see §9).
7. Move completed plans to `docs/exec-plans/completed/`.
8. Only change files relevant to the task. No drive-by improvements.

## 8. Frontend Conventions

See [docs/dev-workflows.md](docs/dev-workflows.md) for full details.

## 9. Doc Update Mapping

| Change Type | Update Location |
|-------------|-----------------|
| Feature logic, inputs, outputs, tests | `docs/features/<feature>.md` |
| User journeys | `docs/app-workflows.md` |
| System layout, deployments | `ARCHITECTURE.md` |
| Dev or testing process | `docs/dev-workflows.md` |
| Setup or scope changes | `README.md` |
| Security changes | `docs/SECURITY.md` |
| Reliability changes | `docs/RELIABILITY.md` |
| Active work plans | `docs/exec-plans/active/` |
| Known tech debt | `docs/exec-plans/tech-debt-tracker.md` |

If documentation and implementation conflict, update docs in the same PR. Documentation rot destroys agent reliability.

## 10. Doc Map

| Topic | Location |
|-------|----------|
| System layout, data flows, boundaries | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Feature docs | [docs/features/](docs/features/) |
| Chapter narration job | [docs/features/narration.md](docs/features/narration.md) |
| Library + streaming player | [docs/features/library.md](docs/features/library.md) |
| Chapter detection rules | [docs/features/chapter-detection.md](docs/features/chapter-detection.md) |
| M4B master assembly | [docs/features/master-assembly.md](docs/features/master-assembly.md) |
| User journeys | [docs/app-workflows.md](docs/app-workflows.md) |
| Engineering workflows and testing | [docs/dev-workflows.md](docs/dev-workflows.md) |
| Security principles | [docs/SECURITY.md](docs/SECURITY.md) |
| Reliability expectations | [docs/RELIABILITY.md](docs/RELIABILITY.md) |
| Execution plans | [docs/exec-plans/](docs/exec-plans/) |
| Tech debt | [docs/exec-plans/tech-debt-tracker.md](docs/exec-plans/tech-debt-tracker.md) |

## 11. When Unsure

- Prefer boring, stable libraries
- Prefer small PRs over large changes
- Add tests with every change
- Never bypass lint rules without explicit instruction
- Ask before making destructive or irreversible changes
