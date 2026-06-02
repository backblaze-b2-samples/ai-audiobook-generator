<!-- last_verified: 2026-06-02 -->
# Feature: Library

## Purpose
A scoped explorer of your audiobooks (everything under the `audiobooks/` prefix) with
an inline streaming player, master download, and delete.

## Used By
- UI: `/library` page
- API: `GET /books`, `GET /books/{id}`, `GET /books/{id}/chapters/{n}/stream`,
  `GET /books/{id}/master/download`, `DELETE /books/{id}`

## Core Functions
- `apps/web/src/components/library/audiobook-grid.tsx` — grid of audiobooks
- `apps/web/src/components/library/audiobook-detail.tsx` — selected-book detail panel
- `apps/web/src/components/library/chapter-player.tsx` — chapter list + `<audio>` player
- `apps/web/src/components/library/status-badge.tsx` — narration status badge
- `services/api/app/service/books.py` — `list_books()`, `get_book()`, `chapter_stream_url()`, `master_download_url()`, `delete_book()`
- `services/api/app/repo/books_store.py` — `list_prefixes()`, `get_stream_url()`, `delete_prefix()`

## Canonical Files
- Streaming player: `apps/web/src/components/library/chapter-player.tsx`
- Scoped listing logic: `services/api/app/service/books.py` (`list_books`)

## Inputs
- Optional `?book=<id>` query param to pre-select a book

## Outputs
- `GET /books` → `BookSummary[]` (scanned from `audiobooks/` via `list_objects_v2` + `Delimiter="/"`)
- `GET /books/{id}/chapters/{n}/stream` → presigned **inline** (non-attachment) URL
- `GET /books/{id}/master/download` → presigned **attachment** URL
- `DELETE /books/{id}` → removes the entire `audiobooks/<id>/` prefix

## Flow
- Grid lists audiobooks (scoped to `audiobooks/`); `useBooks()` polls every 3s while
  any book is in flight
- Selecting a card opens the detail panel; `useBook(id)` polls every 2s while in flight
- Playing a chapter fetches a presigned inline URL and points the `<audio>` element at
  it — the browser streams the MP3 from B2 with HTTP Range reads
- Master download opens the presigned attachment URL; delete removes the whole prefix

## Edge Cases
- Master not assembled yet → download disabled / `404`
- Chapter not yet rendered → its play button is disabled
- API unavailable → inline `ErrorState` with retry
- Empty library → empty state pointing to New Audiobook

## UX States
- Loading: skeleton grid / detail
- Empty: "No audiobooks yet"
- In flight: status badge + `GeneratingLoader`
- Complete: playable chapters + enabled master download

## Verification
- Test files: `services/api/tests/test_books.py` (listing, key layout, presign helpers via narration tests)
- Required cases: list scoped to prefix, stream/download URL helpers, delete removes prefix
- Quick verify command: `pnpm test:api`
- Full verify command: `pnpm lint && pnpm lint:api && pnpm test:api && pnpm check:structure`
- Pass criteria: pytest green, ruff clean, frontend builds

## Related Docs
- [Chapter Narration](narration.md)
- [Master Assembly](master-assembly.md)
- [docs/SECURITY.md](../SECURITY.md)
