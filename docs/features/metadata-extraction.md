<!-- last_verified: 2026-06-02 -->
# Feature: Metadata Extraction

## Purpose
Extract metadata from uploaded files and return it alongside upload results.

## Used By
- API: `POST /upload` (called after B2 upload)
- UI: upload results, file metadata panel

## Core Functions
- `services/api/app/service/metadata.py` — `extract_metadata()`, `_extract_pdf_metadata()`, `_extract_audio_metadata()`
- `apps/web/src/components/files/file-metadata-panel.tsx` — displays metadata in a structured card

## Canonical Files
- Metadata extraction pattern: `services/api/app/service/metadata.py`
- Metadata display component: `apps/web/src/components/files/file-metadata-panel.tsx`

## Inputs
- file_data: bytes
- filename: string
- content_type: string

## Outputs
- `FileMetadataDetail`: filename, size_bytes, size_human, mime_type, extension, md5, sha256, uploaded_at
- PDF-specific (optional): pdf_pages, pdf_author, pdf_title — for ebook manuscript sources
- Audio (optional): duration_seconds, codec, bitrate — for chapter renders and the master

## Flow
- Upload route receives a file and stores it in B2
- `extract_metadata()` is called with the file bytes, filename, and content type
- Always computes MD5 and SHA-256 checksums
- If PDF: opens with PyPDF2 → page count, author, title
- If audio/video: reads container headers with **mutagen** (no decoding, no ffmpeg) →
  duration, codec, bitrate
- Returns `FileMetadataDetail`; the frontend renders it in the file metadata panel

## Why no image branch
This is an audiobook app: it ingests text and emits audio. Image dimension/EXIF
extraction (and the `Pillow` dependency) were trimmed from the starter — the
`image_width` / `image_height` / `exif` fields no longer exist on the model. PDF
metadata is kept for ebook sources; audio metadata is added via mutagen.

## Edge Cases
- Corrupt PDF → PyPDF2 fails silently, PDF fields remain null
- Corrupt/short audio → mutagen returns no info, audio fields remain null
- Unknown content type → only common fields populated (hashes, size, extension)
- Large file → hashing is in-memory and may be slow

## UX States
- Not applicable (metadata is part of the upload response and file preview)

## Verification
- Test files: `services/api/tests/test_metadata.py`
- Required cases: checksums always present, audio path, PDF path, no image fields on model
- Quick verify command: `pnpm test:api`
- Full verify command: `pnpm lint && pnpm lint:api && pnpm test:api && pnpm check:structure`
- Pass criteria: pytest green, ruff clean

## Related Docs
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [File Upload](file-upload.md)
- [Master Assembly](master-assembly.md)
