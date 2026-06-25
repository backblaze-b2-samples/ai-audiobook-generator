"""Narration job orchestration — single narrator voice.

The B2 manifest is the durable job record. Redis/RQ only queues book ids; the
worker resumes from per-chapter manifest state and skips completed chapters.
"""

import logging
import uuid
from datetime import UTC, datetime

from app.repo import (
    AudioAssemblyError,
    JobLeaseError,
    TTSError,
    acquire_book_lease,
    assemble_master,
    cancel_job,
    current_job_retries_left,
    enqueue_job,
    get_provider,
    is_book_tombstoned,
    put_bytes,
    read_object,
    tombstone_book,
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
NARRATION_JOB_TARGET = "app.service.narration.run_narration"


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


def narration_job_id(book_id: str) -> str:
    books_service.validate_book_id(book_id)
    return f"narration:{book_id}"


def validate_narration_job(args: tuple | list, kwargs: dict) -> None:
    if kwargs or len(args) != 1:
        raise ValueError("Narration jobs must pass exactly one book id argument.")
    book_id = args[0]
    if not isinstance(book_id, str):
        raise ValueError("Narration job book id must be a string.")
    books_service.validate_book_id(book_id)


def enqueue_narration_job(book_id: str) -> str:
    """Queue a durable narration job for a persisted book manifest."""
    books_service.validate_book_id(book_id)
    return enqueue_job(
        NARRATION_JOB_TARGET,
        (book_id,),
        narration_job_id(book_id),
    )


def enqueue_resume_candidates(limit: int | None = None) -> int:
    """Requeue incomplete books found in B2 when a worker starts."""
    queued = 0
    for book_id in books_service.list_book_ids(limit=limit):
        try:
            book = books_service.load_manifest(book_id)
        except Exception as e:
            logger.warning("Skipping resume candidate %s: %s", book_id, e)
            continue
        if book.status not in INCOMPLETE_STATUSES:
            continue
        enqueue_narration_job(book.id)
        queued += 1
    return queued


def cancel_narration_for_book(book_id: str) -> None:
    """Stop future queued/running narration writes for a book being deleted."""
    books_service.validate_book_id(book_id)
    tombstone_book(book_id)
    cancel_job(narration_job_id(book_id))


class BookDeletedDuringNarration(Exception):
    """Raised when DELETE has tombstoned a book while narration was running."""


def _ensure_not_deleted(book_id: str) -> None:
    if is_book_tombstoned(book_id):
        raise BookDeletedDuringNarration(book_id)


def _touch(book: Book, lease=None) -> None:
    _ensure_not_deleted(book.id)
    book.updated_at = _now()
    books_service.save_manifest(book)
    if lease:
        lease.refresh()


def _put_book_bytes(book: Book, data: bytes, key: str, content_type: str, lease) -> None:
    _ensure_not_deleted(book.id)
    put_bytes(data, key, content_type)
    lease.refresh()


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
    try:
        lease = acquire_book_lease(book_id)
    except JobLeaseError as e:
        logger.info("Narration lease unavailable for book %s: %s", book_id, e)
        return

    try:
        _run_narration_with_lease(book_id, lease)
    finally:
        lease.release()


def _run_narration_with_lease(book_id: str, lease) -> None:
    try:
        _ensure_not_deleted(book_id)
        book = books_service.load_manifest(book_id)
    except BookDeletedDuringNarration:
        logger.info("Narration skipped for deleted book %s", book_id)
        return
    except books_service.BookNotFoundError:
        logger.info("Narration skipped for missing book %s", book_id)
        return

    if book.status == NarrationStatus.COMPLETE:
        logger.info("Narration already complete for book %s", book_id)
        return

    book.status = NarrationStatus.RENDERING
    book.error = None
    _touch(book, lease)

    try:
        provider = get_provider()
        _repopulate_chapter_text(book)
        for chapter in book.chapters:
            if chapter.status == NarrationStatus.COMPLETE and chapter.audio_key:
                continue
            chapter.status = NarrationStatus.RENDERING
            chapter.error = None
            _touch(book, lease)
            audio = provider.synthesize(chapter.text, book.voice_id)
            key = books_service.chapter_key(book_id, chapter.index)
            _put_book_bytes(book, audio, key, "audio/mpeg", lease)
            meta = _extract_audio_metadata(audio)
            chapter.audio_key = key
            chapter.duration_seconds = meta.get("duration_seconds")
            chapter.status = NarrationStatus.COMPLETE
            chapter.error = None
            _touch(book, lease)
    except TTSError as e:
        if _should_retry_current_job():
            book.status = NarrationStatus.RENDERING
            book.error = f"Retrying narration after transient failure: {e}"
            _touch(book, lease)
            logger.warning("Narration will retry for book %s: %s", book_id, e)
            raise
        _mark_failed(book, str(e), lease)
        logger.error("Narration failed permanently for book %s: %s", book_id, e)
        return
    except BookDeletedDuringNarration:
        logger.info("Narration stopped for deleted book %s", book_id)
        return

    _assemble(book, lease)


def _should_retry_current_job() -> bool:
    retries_left = current_job_retries_left()
    return retries_left is not None and retries_left > 0


def _mark_failed(book: Book, error: str, lease) -> None:
    current = next(
        (c for c in book.chapters if c.status == NarrationStatus.RENDERING),
        None,
    )
    if current:
        current.status = NarrationStatus.FAILED
        current.error = error
    book.status = NarrationStatus.FAILED
    book.error = error
    _touch(book, lease)


def _assemble(book: Book, lease) -> None:
    book.status = NarrationStatus.ASSEMBLING
    _touch(book, lease)
    try:
        audio_blobs: list[bytes] = []
        meta: list[tuple[str, float]] = []
        for chapter in book.chapters:
            _ensure_not_deleted(book.id)
            data = read_object(chapter.audio_key) if chapter.audio_key else None
            if data is None:
                raise AudioAssemblyError(
                    f"Missing audio for chapter {chapter.index} during assembly."
                )
            lease.refresh()
            audio_blobs.append(data)
            meta.append((chapter.title, chapter.duration_seconds or 0.0))
        master = assemble_master(audio_blobs, meta)
        _put_book_bytes(book, master, books_service.master_key(book.id), "audio/mp4", lease)
        book.master_key = books_service.master_key(book.id)
        book.status = NarrationStatus.COMPLETE
        book.error = None
        _touch(book, lease)
        logger.info("Book %s complete (%d chapters)", book.id, book.chapter_count)
    except AudioAssemblyError as e:
        # Chapters rendered fine; only the master failed. Surface a partial
        # success: chapters are playable, master is unavailable.
        book.status = NarrationStatus.COMPLETE
        book.master_key = None
        book.error = f"Chapters narrated; master assembly skipped: {e}"
        _touch(book, lease)
        logger.warning("Master assembly skipped for book %s: %s", book.id, e)
    except BookDeletedDuringNarration:
        logger.info("Master assembly stopped for deleted book %s", book.id)


def get_book_detail(book_id: str) -> BookDetail:
    return books_service.get_book(book_id)


def list_voices() -> list[Voice]:
    """Narrator voices offered by the active TTS provider (single-voice pick)."""
    return get_provider().list_voices()
