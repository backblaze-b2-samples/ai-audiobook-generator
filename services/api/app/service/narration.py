"""Narration job orchestration for durable single-voice audiobook jobs."""

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
    get_resume_scan_cursor,
    is_book_tombstoned,
    put_bytes,
    read_object,
    set_resume_scan_cursor,
    tombstone_book,
)
from app.service import books as books_service
from app.service.chapters import split_into_chapters
from app.service.metadata import _extract_audio_metadata
from app.types import Book, BookDetail, CreateBookRequest, NarrationStatus, Voice

logger = logging.getLogger(__name__)

INCOMPLETE_STATUSES = {NarrationStatus.PENDING, NarrationStatus.RENDERING, NarrationStatus.ASSEMBLING}
NARRATION_JOB_TARGET = "app.service.narration.run_narration"


class PermanentNarrationError(TTSError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def create_book(request: CreateBookRequest, owner_id: str = "local-dev") -> Book:
    chapters = split_into_chapters(request.text)
    if not chapters:
        raise ValueError("Manuscript produced no chapters (empty text).")

    provider = get_provider()
    voice_id = request.voice_id or provider.default_voice_id()

    book_id = str(uuid.uuid4())
    now = _now()
    book = Book(
        id=book_id,
        owner_id=owner_id,
        title=request.title.strip(),
        status=NarrationStatus.PENDING,
        voice_id=voice_id,
        chapters=chapters,
        created_at=now,
        updated_at=now,
    )
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
    books_service.validate_book_id(book_id)
    return enqueue_job(NARRATION_JOB_TARGET, (book_id,), narration_job_id(book_id))


def enqueue_resume_candidates(batch_size: int | None = None, max_manifests: int | None = None) -> int:
    queued = 0
    checked = 0
    cursor = get_resume_scan_cursor() if max_manifests else None
    kwargs = {"limit": max_manifests, "start_after_id": cursor} if max_manifests else {}
    ids = books_service.list_book_ids(**kwargs)
    last_book_id = None
    for book_id in ids:
        checked += 1
        last_book_id = book_id
        try:
            book = books_service.load_manifest(book_id)
        except Exception as e:
            logger.warning("Skipping resume candidate %s: %s", book_id, e)
            continue
        if book.status not in INCOMPLETE_STATUSES:
            continue
        enqueue_narration_job(book.id)
        queued += 1
        if batch_size and checked % batch_size == 0:
            logger.info("Resume scan checked %d manifests", checked)
    if max_manifests:
        set_resume_scan_cursor(last_book_id if checked >= max_manifests else None)
    logger.info("Resume scan checked %d manifests total", checked)
    return queued


def cancel_narration_for_book(book_id: str) -> None:
    books_service.validate_book_id(book_id)
    tombstone_book(book_id)
    cancel_job(narration_job_id(book_id))


class BookDeletedDuringNarration(Exception):
    pass


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
    raw = read_object(books_service.source_key(book.id))
    if raw is None:
        raise PermanentNarrationError(f"Source manuscript missing for book {book.id}.")
    source_chapters = split_into_chapters(raw.decode("utf-8"))
    by_index = {c.index: c.text for c in source_chapters}
    for chapter in book.chapters:
        chapter.text = by_index.get(chapter.index, "")


def run_narration(book_id: str) -> None:
    try:
        lease = acquire_book_lease(book_id)
    except JobLeaseError as e:
        logger.info(
            "Narration lease unavailable for book %s: error_type=%s",
            book_id,
            type(e).__name__,
        )
        raise

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
    except PermanentNarrationError as e:
        _mark_failed(book, str(e), lease)
        logger.error(
            "Narration failed permanently for book %s: error_type=%s",
            book_id,
            type(e).__name__,
        )
        return
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
    except Exception as e:
        error = f"Worker failure: {type(e).__name__}"
        if _should_retry_current_job():
            book.status = NarrationStatus.RENDERING
            book.error = f"Retrying narration after {error}"
            _touch(book, lease)
            logger.warning("Narration will retry for book %s: %s", book_id, error)
            raise
        _mark_failed(book, error, lease)
        logger.exception("Narration failed permanently for book %s", book_id)
        return

    _assemble(book, lease)


def _should_retry_current_job() -> bool:
    retries_left = current_job_retries_left()
    return retries_left is not None and retries_left > 0


def _mark_failed(book: Book, error: str, lease) -> None:
    current = next((c for c in book.chapters if c.status == NarrationStatus.RENDERING), None)
    current = current or next((c for c in book.chapters if c.status != NarrationStatus.COMPLETE), None)
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
                raise AudioAssemblyError(f"Missing audio for chapter {chapter.index}.")
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
