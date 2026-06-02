<!-- last_verified: 2026-06-02 -->
# Feature: Dashboard

## Purpose
Give an at-a-glance overview of the audiobook library and narration activity.

## Used By
- UI: `/` page (dashboard home)
- API: `GET /books/stats`, `GET /books`, `GET /books/stats/activity`

## Core Functions
- `apps/web/src/components/dashboard/stats-cards.tsx` — 4 stat cards
- `apps/web/src/components/dashboard/recent-audiobooks-table.tsx` — recent audiobooks
- `apps/web/src/components/dashboard/narration-chart.tsx` — audio hours per day
- `apps/web/src/lib/queries.ts` — `useBookStats()`, `useBooks()`, `useBookActivity()`
- `services/api/app/runtime/books.py` — `GET /books/stats`, `GET /books/stats/activity`
- `services/api/app/service/books.py` — `book_stats()`, `book_activity()`

## Canonical Files
- Stats service logic: `services/api/app/service/books.py`
- Dashboard composition: `apps/web/src/app/page.tsx`

## Inputs
- None (dashboard loads data automatically)

## Outputs
- `GET /books/stats` → `BookStats` (total_books, total_chapters, total_duration_*, total_size_*)
- `GET /books` → `BookSummary[]` (recent audiobooks, sorted newest-first)
- `GET /books/stats/activity?days=7` → `DailyNarrationHours[]` for the chart

## Flow
- Page loads → parallel hooks fetch book stats, recent books, narration activity
- Stat cards: total audiobooks, chapters rendered, hours narrated, storage used
- Chart: audio hours generated per day for the last 7 days (book duration attributed
  to its creation day)
- Recent audiobooks table: title · chapters rendered/total · duration · status · created
- `useBooks()` polls every 3s while any book is still being narrated

## Edge Cases
- API unavailable → inline `ErrorState` with retry (not silent zeros)
- No audiobooks → empty chart + empty table states
- Large library → stats/activity paginate through `audiobooks/` manifests

## UX States
- Loading: skeleton placeholders for cards and table
- Empty: "No narration yet" / "No audiobooks yet"
- Loaded: populated cards, chart, table

## Verification
- Test files: `services/api/tests/test_books.py`
- Required cases: stats with books, empty library, derived-field correctness
- Quick verify command: `pnpm test:api`
- Full verify command: `pnpm lint && pnpm lint:api && pnpm test:api && pnpm check:structure`
- Pass criteria: pytest green, ruff clean, frontend builds

## Related Docs
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [App Workflows](../app-workflows.md)
- [Chapter Narration](narration.md)
