"""Narration job orchestration — single narrator voice.

create_book() splits the manuscript, writes source.txt + the initial manifest
(status pending), and returns immediately. enqueue_narration_job() places the
book id on the durable Redis/RQ queue. run_narration() is the long-running
worker function: per chapter it synthesizes audio, writes the chapter MP3,
reads its duration, and rewrites the manifest; when every chapter is rendered
it assembles the M4B master and marks the book complete.

The manifest in B2 is the record of truth and is rewritten after each step.
Queue workers can safely restart the same book because complete chapters are
skipped and pending/rendering/failed chapters are resumed from manifest state.
"""

import logging
import uuid
from datetime import UTC, datetime

from app.repo import (
    AudioAssemblyError,
    TTSError,
    assemble_master,
    enqueue_narration,
    get_provider,
    put_bytes,
    read_object,
)
from app.service import books as books_service
from app.service.chapters import split_into_chapters
from app.service.metadata import _extract_audio_metadata
from app.types import Book, BookDetail, CreateBookRequest, NarrationStatus, Voice

logger = logging.getLogger(__name__)

INCOMPLETE_STATUSES = {
    NarrationStatus.PENDING,
    NarrationStatus.RENDERING,
    NarrationStatus.ASSEMBLING,
}


def _now() -> datetime:
    return datetime.now(UTC)


def create_book(request: CreateBookRequest) -> Book:
    """Create a book, persist source + initial manifest, return the Book.

    Does NOT render audio — enqueue the returned id with enqueue_narration_job().
    """
    chapters = split_into_chapters(request.text)
    if not chapters:
        raise ValueError("Manuscript produced no chapters (empty text).")

    provider = get_provider()
    voice_id = request.voice_id or provider.default_voice_id()

    book_id = str(uuid.uuid4())
    now = _now()
    book = Book(
        id=book_id,
        title=request.title.strip(),
        status=NarrationStatus.PENDING,
        voice_id=voice_id,
        chapters=chapters,
        created_at=now,
        updated_at=now,
    )
    # Persist source text and the initial manifest. source.txt is the durable
    # copy of the manuscript; manifest.json is the job record of truth.
    put_bytes(request.text.encode("utf-8"), books_service.source_key(book_id), "text/plain")
    books_service.save_manifest(book)
    return book


def enqueue_narration_job(book_id: str) -> str:
    """Queue a durable narration job for a persisted book manifest."""
    books_service.validate_book_id(book_id)
    return enqueue_narration(book_id)


def enqueue_resume_candidates() -> int:
    """Requeue incomplete books found in B2 when a worker starts."""
    queued = 0
    for book in books_service.list_books():
        if book.status not in INCOMPLETE_STATUSES:
            continue
        enqueue_narration_job(book.id)
        queued += 1
    return queued


def _touch(book: Book) -> None:
    book.updated_at = _now()
    books_service.save_manifest(book)


def _repopulate_chapter_text(book: Book) -> None:
    """Restore per-chapter text from the durable source.txt.

    The manifest excludes chapter text (it lives only in source.txt), so a
    book loaded from the manifest has empty `chapter.text`. Re-read the
    manuscript and re-run the deterministic split, matching by contiguous
    index, so synthesize() receives the real chapter text rather than "".
    """
    raw = read_object(books_service.source_key(book.id))
    if raw is None:
        raise TTSError(f"Source manuscript missing for book {book.id}.")
    source_chapters = split_into_chapters(raw.decode("utf-8"))
    by_index = {c.index: c.text for c in source_chapters}
    for chapter in book.chapters:
        chapter.text = by_index.get(chapter.index, "")


def run_narration(book_id: str) -> None:
    """Render every chapter, then assemble the master.

    Re-runs skip chapters already marked complete.
    """
    book = books_service.load_manifest(book_id)
    if book.status == NarrationStatus.COMPLETE:
        logger.info("Narration already complete for book %s", book_id)
        return

    provider = get_provider()

    book.status = NarrationStatus.RENDERING
    book.error = None
    _touch(book)

    try:
        _repopulate_chapter_text(book)
        for chapter in book.chapters:
            if chapter.status == NarrationStatus.COMPLETE and chapter.audio_key:
                continue
            chapter.status = NarrationStatus.RENDERING
            chapter.error = None
            _touch(book)
            audio = provider.synthesize(chapter.text, book.voice_id)
            key = books_service.chapter_key(book_id, chapter.index)
            put_bytes(audio, key, "audio/mpeg")
            meta = _extract_audio_metadata(audio)
            chapter.audio_key = key
            chapter.duration_seconds = meta.get("duration_seconds")
            chapter.status = NarrationStatus.COMPLETE
            chapter.error = None
            _touch(book)
    except TTSError as e:
        current = next(
            (c for c in book.chapters if c.status == NarrationStatus.RENDERING),
            None,
        )
        if current:
            current.status = NarrationStatus.FAILED
            current.error = str(e)
        book.status = NarrationStatus.FAILED
        book.error = str(e)
        _touch(book)
        logger.error("Narration failed for book %s: %s", book_id, e)
        return

    _assemble(book)


def _assemble(book: Book) -> None:
    book.status = NarrationStatus.ASSEMBLING
    _touch(book)
    try:
        audio_blobs: list[bytes] = []
        meta: list[tuple[str, float]] = []
        for chapter in book.chapters:
            data = read_object(chapter.audio_key) if chapter.audio_key else None
            if data is None:
                raise AudioAssemblyError(
                    f"Missing audio for chapter {chapter.index} during assembly."
                )
            audio_blobs.append(data)
            meta.append((chapter.title, chapter.duration_seconds or 0.0))
        master = assemble_master(audio_blobs, meta)
        put_bytes(master, books_service.master_key(book.id), "audio/mp4")
        book.master_key = books_service.master_key(book.id)
        book.status = NarrationStatus.COMPLETE
        book.error = None
        _touch(book)
        logger.info("Book %s complete (%d chapters)", book.id, book.chapter_count)
    except AudioAssemblyError as e:
        # Chapters rendered fine; only the master failed. Surface a partial
        # success: chapters are playable, master is unavailable.
        book.status = NarrationStatus.COMPLETE
        book.master_key = None
        book.error = f"Chapters narrated; master assembly skipped: {e}"
        _touch(book)
        logger.warning("Master assembly skipped for book %s: %s", book.id, e)


def get_book_detail(book_id: str) -> BookDetail:
    return books_service.get_book(book_id)


def list_voices() -> list[Voice]:
    """Narrator voices offered by the active TTS provider (single-voice pick)."""
    return get_provider().list_voices()
