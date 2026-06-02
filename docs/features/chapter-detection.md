<!-- last_verified: 2026-06-02 -->
# Feature: Chapter Detection

## Purpose
Split a long manuscript into ordered chapters — honoring explicit markers where they
exist, falling back to size-based chunking where they don't.

## Used By
- API: `POST /books` (via `service.narration.create_book`)
- UI: `/create` chapter preview (a client-side estimate using the same rules)

## Core Functions
- `services/api/app/service/chapters.py` — `split_into_chapters()`
- `apps/web/src/lib/chapter-preview.ts` — client-side estimate (labelled as such)

## Canonical Files
- Splitting logic (source of truth): `services/api/app/service/chapters.py`

## Inputs
- text: string (the manuscript)

## Outputs
- ordered `Chapter[]` — `{ index, title, text, char_count }` (text is excluded from the
  serialized manifest; the full source lives in `source.txt`)

## Flow
1. **Marker-aware split** — a line is treated as a chapter boundary if it is:
   - a `Chapter N` / `CHAPTER IV` / `Part`/`Book`/`Section` line (short, standalone),
   - a Markdown heading (`#`, `##`, `###`), or
   - a horizontal rule (`---`, `***`, `___`, unnamed boundary)
2. **Size fallback** — if no markers are found (a single oversized chapter), chunk by
   paragraph into pieces under ~8,000 characters, never splitting mid-paragraph
3. Chapters are re-indexed contiguously and unnamed ones auto-titled `Chapter N`

## Edge Cases
- No markers, short text → a single chapter
- No markers, long text → size-based chunks
- Prose that merely starts with "Chapter" → not treated as a marker (length guard ≤ 80 chars)
- Empty/whitespace text → no chapters (create returns `400`)

## UX States
- Studio preview shows the estimated chapter list live as the user edits; it is clearly
  labelled as an estimate, with the server re-splitting on the same rules at generate time

## Verification
- Test files: `services/api/tests/test_chapters.py`
- Required cases: explicit markers, Markdown headings, rules, size fallback, short text, empty text
- Quick verify command: `pnpm test:api`
- Full verify command: `pnpm lint && pnpm lint:api && pnpm test:api && pnpm check:structure`
- Pass criteria: pytest green, ruff clean

## Related Docs
- [Chapter Narration](narration.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
