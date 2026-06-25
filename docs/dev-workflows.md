<!-- last_verified: 2026-06-25 -->
# Dev Workflows

Engineering workflows for this repo.

## Prerequisites

- Node.js >= 20, pnpm >= 9, Python >= 3.11
- **Redis** reachable at `REDIS_URL` (default `redis://localhost:6379/0`) for the
  durable narration queue.
- **ffmpeg** on PATH (M4B master assembly). Per-chapter MP3s render without it;
  `pnpm doctor` warns when it's missing.
- A TTS provider key in `.env` (OpenAI by default: `OPENAI_API_KEY`).

## New Feature

- [ ] Read `AGENTS.md` and `ARCHITECTURE.md`
- [ ] Read the relevant feature doc in `docs/features/`
- [ ] For non-trivial changes, create a plan in `docs/exec-plans/active/`
- [ ] Implement the smallest coherent change
- [ ] Add or update tests
- [ ] Run: `pnpm typecheck && pnpm lint && pnpm lint:api && pnpm test:api && pnpm check:structure`
- [ ] Update docs in the same PR (see AGENTS.md §8)
- [ ] Move plan to `docs/exec-plans/completed/` after validation

## Bugfix

- [ ] Add a failing test that reproduces the bug
- [ ] Confirm the test fails
- [ ] Implement the fix
- [ ] Rerun tests until green
- [ ] Update docs if behavior changed

## Refactor

- [ ] Read `ARCHITECTURE.md` — respect layering rules
- [ ] Ensure structural tests still pass: `pnpm check:structure`
- [ ] No behavior changes without updating feature docs

## Documentation Update

- [ ] Update only the canonical location (see AGENTS.md §8 doc update mapping)
- [ ] Never duplicate content — link instead
- [ ] Update `<!-- last_verified: YYYY-MM-DD -->` header

## Pull Request

- [ ] One coherent change per PR
- [ ] Run full lint + test suite before submitting
- [ ] Docs updated in the same PR as code changes
- [ ] Only change files relevant to the task — no drive-by improvements

## Testing

### Test types
- **Unit**: pure logic (service layer — chapter splitting, narration orchestration)
- **Integration**: HTTP handlers, B2 connectivity (`tests/`)
- **Structural**: layering rules, import boundaries (`tests/test_structure.py`)
- **E2E**: Playwright browser-driven smoke tests

### Testing narration without a real TTS provider or ffmpeg
Narration tests **mock at the repo boundary** — never call OpenAI/ElevenLabs or run
ffmpeg in CI. See `tests/test_narration.py`: monkeypatch `narration.get_provider`
with a fake `TTSProvider`, and monkeypatch `put_bytes`/`read_object`/`assemble_master`
plus `books.write_json`/`read_json` to an in-memory store. This keeps the suite
hermetic and fast. The same pattern applies to metadata (`_extract_audio_metadata`)
and book stats.

### Test placement
- Backend: `services/api/tests/`
- E2E: project root (Playwright)

### Commands
- Quick (backend): `pnpm test:api`
- Structure: `pnpm check:structure`
- Frontend typecheck: `pnpm typecheck`
- Frontend lint: `pnpm lint`
- Backend lint: `pnpm lint:api`
- Worker: `pnpm dev:worker`
- Full suite: `pnpm typecheck && pnpm lint && pnpm lint:api && pnpm test:api && pnpm check:structure`
- E2E: `pnpm test:e2e` (run `pnpm --filter @ai-audiobook-generator/web exec playwright install chromium` once first)

### When to run
- After behavior change: run relevant subset
- Before PR: run full suite

## Frontend Conventions

- Tailwind v4: config via CSS `@theme` blocks, NOT `tailwind.config.ts`
- Colors: OKLch format
- Dark mode: `next-themes` with `@custom-variant dark (&:is(.dark *))`
- Animations: `tw-animate-css` (not `tailwindcss-animate`)
- shadcn/ui components in `src/components/ui/` are generated — never modify them

## Data Fetching

All API reads/writes flow through TanStack Query hooks in
`apps/web/src/lib/queries.ts`. Don't add bare `useEffect + fetch` patterns
to components.

**Read** — use the hooks directly:

```tsx
const { data: books, isLoading, error, refetch } = useBooks();
const { data: book } = useBook(id); // polls while the job is in flight
const { data: stats } = useBookStats();
```

`useBooks()` and `useBook(id)` set `refetchInterval` while a book's status is
`pending` / `rendering` / `assembling`, so progress updates without manual refresh.

Surface errors via `<ErrorState error={error} onRetry={() => refetch()} />`
rather than silently rendering empty UI.

**Write** — wrap mutations with `useMutation` and invalidate on success:

```tsx
const createBook = useCreateBook();
createBook.mutate({ title, text, voice_id }, {
  onSuccess: (book) => router.push(`/library?book=${book.id}`),
});
```

`useCreateBook()` / `useDeleteBook()` invalidate the relevant query keys on success
(books list + stats), so every consumer re-fetches lazily. The kept Files surface
uses the same pattern via `useDeleteFile()`.

**Add a new endpoint** — three places to touch:
1. `services/api/app/runtime/<router>.py` — FastAPI route
2. `apps/web/src/lib/api-client.ts` — typed fetch wrapper
3. `apps/web/src/lib/queries.ts` — `useQuery` / `useMutation` hook + entry in `qk`

Defaults (in `apps/web/src/lib/query-client.tsx`):
- `staleTime: 30s` — library / stats don't change second-to-second (in-flight books
  override this with their own `refetchInterval`)
- `retry: 1` for transient errors; never retry 4xx (won't get better)
- `refetchOnWindowFocus`: on (TanStack default) — dashboard self-heals
  when the user comes back to the tab
