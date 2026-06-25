"""Audiobook manifest CRUD over B2.

B2 is the sole datastore. Each book lives under `audiobooks/<book-id>/`:

    audiobooks/<id>/source.txt      uploaded/pasted manuscript
    audiobooks/<id>/manifest.json   job + chapter state (the record of truth)
    audiobooks/<id>/chapters/ch-001.mp3 ...
    audiobooks/<id>/master.m4b      final chapterized master

The manifest *is* the Book model serialized to JSON. There is no database.
"""

import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from app.repo import (
    delete_prefix,
    get_presigned_url,
    get_stream_url,
    list_prefixes,
    prefix_size,
    read_json,
    write_json,
)
from app.types import (
    Book,
    BookDetail,
    BookStats,
    BookSummary,
    ChapterDetail,
    DailyNarrationHours,
)
from app.types.formatting import humanize_bytes, humanize_duration

ROOT_PREFIX = "audiobooks/"
_BOOK_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class BookKeyError(Exception):
    """Raised when a book id is malformed (guards against key injection)."""

    def __init__(self, detail: str = "Invalid book id"):
        self.detail = detail
        super().__init__(detail)


class BookNotFoundError(Exception):
    def __init__(self, detail: str = "Audiobook not found"):
        self.detail = detail
        super().__init__(detail)


class BookAccessError(Exception):
    def __init__(self, detail: str = "Audiobook not found"):
        self.detail = detail
        super().__init__(detail)


def validate_book_id(book_id: str) -> None:
    if not book_id or not _BOOK_ID_RE.match(book_id):
        raise BookKeyError()


def book_prefix(book_id: str) -> str:
    return f"{ROOT_PREFIX}{book_id}/"


def source_key(book_id: str) -> str:
    return f"{book_prefix(book_id)}source.txt"


def manifest_key(book_id: str) -> str:
    return f"{book_prefix(book_id)}manifest.json"


def chapter_key(book_id: str, index: int) -> str:
    return f"{book_prefix(book_id)}chapters/ch-{index + 1:03d}.mp3"


def master_key(book_id: str) -> str:
    return f"{book_prefix(book_id)}master.m4b"


def save_manifest(book: Book) -> None:
    """Persist the Book manifest to B2 (the single write that records state)."""
    write_json(manifest_key(book.id), book.model_dump(mode="json"))


def load_manifest(book_id: str) -> Book:
    validate_book_id(book_id)
    raw = read_json(manifest_key(book_id))
    if raw is None:
        raise BookNotFoundError()
    return Book.model_validate(raw)


def _require_owner(book: Book, owner_id: str | None) -> None:
    if owner_id is not None and book.owner_id != owner_id:
        raise BookAccessError()


def _to_detail(book: Book) -> BookDetail:
    return BookDetail(
        id=book.id,
        title=book.title,
        status=book.status,
        voice_id=book.voice_id,
        chapter_count=book.chapter_count,
        chapters_rendered=book.chapters_rendered,
        duration_seconds=book.duration_seconds,
        duration_human=humanize_duration(book.duration_seconds),
        master_key=book.master_key,
        created_at=book.created_at,
        updated_at=book.updated_at,
        error=book.error,
        chapters=[
            ChapterDetail(
                index=c.index,
                title=c.title,
                char_count=c.char_count,
                status=c.status,
                audio_key=c.audio_key,
                duration_seconds=c.duration_seconds,
                error=c.error,
            )
            for c in book.chapters
        ],
    )


def get_book(book_id: str, owner_id: str | None = None) -> BookDetail:
    book = load_manifest(book_id)
    _require_owner(book, owner_id)
    return _to_detail(book)


def master_download_url(book_id: str, owner_id: str | None = None) -> str:
    """Presigned attachment URL for the M4B master. Raises if not assembled."""
    book = load_manifest(book_id)
    _require_owner(book, owner_id)
    if not book.master_key:
        raise BookNotFoundError("Master not available for this audiobook yet")
    return get_presigned_url(book.master_key, filename=f"{book.title}.m4b")


def chapter_stream_url(book_id: str, index: int, owner_id: str | None = None) -> str:
    """Presigned inline (non-attachment) URL for streaming a chapter render."""
    book = load_manifest(book_id)
    _require_owner(book, owner_id)
    match = next((c for c in book.chapters if c.index == index), None)
    if match is None or not match.audio_key:
        raise BookNotFoundError("Chapter audio not available yet")
    return get_stream_url(match.audio_key)


def _id_from_prefix(prefix: str) -> str:
    # "audiobooks/<id>/" -> "<id>"
    return prefix[len(ROOT_PREFIX):].rstrip("/")


def list_book_ids(limit: int | None = None) -> list[str]:
    return [_id_from_prefix(prefix) for prefix in list_prefixes(ROOT_PREFIX, limit=limit)]


def list_books(limit: int | None = None, owner_id: str | None = None) -> list[BookSummary]:
    """Scan `audiobooks/` folders and read each manifest into a summary."""
    summaries: list[BookSummary] = []
    for book_id in list_book_ids(limit=limit):
        raw = read_json(manifest_key(book_id))
        if raw is None:
            continue
        book = Book.model_validate(raw)
        if owner_id is not None and book.owner_id != owner_id:
            continue
        summaries.append(
            BookSummary(
                id=book.id,
                title=book.title,
                status=book.status,
                chapter_count=book.chapter_count,
                chapters_rendered=book.chapters_rendered,
                duration_seconds=book.duration_seconds,
                duration_human=humanize_duration(book.duration_seconds),
                created_at=book.created_at,
            )
        )
    summaries.sort(key=lambda b: b.created_at, reverse=True)
    return summaries


def delete_book(book_id: str, owner_id: str | None = None) -> int:
    validate_book_id(book_id)
    # Ensure it exists first so a bad id 404s rather than silently no-ops.
    _require_owner(load_manifest(book_id), owner_id)
    return delete_prefix(book_prefix(book_id))


def book_stats(owner_id: str | None = None) -> BookStats:
    """Aggregate counts across every audiobook for the dashboard."""
    total_books = 0
    total_chapters = 0
    total_duration = 0.0
    owned_book_ids: list[str] = []
    for prefix in list_prefixes(ROOT_PREFIX):
        book_id = _id_from_prefix(prefix)
        raw = read_json(manifest_key(book_id))
        if raw is None:
            continue
        book = Book.model_validate(raw)
        if owner_id is not None and book.owner_id != owner_id:
            continue
        total_books += 1
        total_chapters += book.chapters_rendered
        total_duration += book.duration_seconds
        owned_book_ids.append(book.id)
    total_size = (
        prefix_size(ROOT_PREFIX)
        if owner_id is None
        else sum(prefix_size(book_prefix(book_id)) for book_id in owned_book_ids)
    )
    return BookStats(
        total_books=total_books,
        total_chapters=total_chapters,
        total_duration_seconds=total_duration,
        total_duration_human=humanize_duration(total_duration),
        total_size_bytes=total_size,
        total_size_human=humanize_bytes(total_size),
    )


def book_activity(days: int = 7, owner_id: str | None = None) -> list[DailyNarrationHours]:
    """Hours of audio narrated per day over the last N days (dashboard chart).

    Attributes each book's total duration to its creation day — a simple,
    explainable proxy for "audio generated per day" without per-chapter
    timestamps.
    """
    today = datetime.now(UTC).date()
    cutoff = today - timedelta(days=days - 1)
    hours_by_day: dict[str, float] = defaultdict(float)
    for prefix in list_prefixes(ROOT_PREFIX):
        book_id = _id_from_prefix(prefix)
        raw = read_json(manifest_key(book_id))
        if raw is None:
            continue
        book = Book.model_validate(raw)
        if owner_id is not None and book.owner_id != owner_id:
            continue
        d = book.created_at.date()
        if d >= cutoff:
            hours_by_day[d.isoformat()] += book.duration_seconds / 3600.0
    return [
        DailyNarrationHours(
            date=(cutoff + timedelta(days=i)).isoformat(),
            hours=round(hours_by_day.get((cutoff + timedelta(days=i)).isoformat(), 0.0), 2),
        )
        for i in range(days)
    ]
