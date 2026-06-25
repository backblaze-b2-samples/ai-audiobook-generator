"""Tests for book manifest round-trips and key-prefix validation."""

from datetime import UTC, datetime

import pytest

from app.service import books as books_service
from app.service.books import (
    BookAccessError,
    BookKeyError,
    BookNotFoundError,
    chapter_key,
    manifest_key,
    master_key,
    source_key,
    validate_book_id,
)
from app.types import Book, Chapter, NarrationStatus

VALID_ID = "12345678-1234-1234-1234-123456789abc"


def test_key_layout():
    assert source_key(VALID_ID) == f"audiobooks/{VALID_ID}/source.txt"
    assert manifest_key(VALID_ID) == f"audiobooks/{VALID_ID}/manifest.json"
    assert chapter_key(VALID_ID, 0) == f"audiobooks/{VALID_ID}/chapters/ch-001.mp3"
    assert chapter_key(VALID_ID, 41) == f"audiobooks/{VALID_ID}/chapters/ch-042.mp3"
    assert master_key(VALID_ID) == f"audiobooks/{VALID_ID}/master.m4b"


def test_validate_book_id_rejects_injection():
    for bad in ["", "../secrets", "not-a-uuid", "audiobooks/x", VALID_ID + "/.."]:
        with pytest.raises(BookKeyError):
            validate_book_id(bad)
    validate_book_id(VALID_ID)  # valid one passes


def test_manifest_round_trip(monkeypatch):
    store: dict[str, dict] = {}
    monkeypatch.setattr(books_service, "write_json", lambda k, o: store.__setitem__(k, o))
    monkeypatch.setattr(books_service, "read_json", lambda k: store.get(k))

    now = datetime.now(UTC)
    book = Book(
        id=VALID_ID,
        title="My Book",
        status=NarrationStatus.RENDERING,
        voice_id="alloy",
        chapters=[
            Chapter(index=0, title="One", char_count=10, text="hello world"),
            Chapter(
                index=1,
                title="Two",
                char_count=12,
                status=NarrationStatus.COMPLETE,
                audio_key=chapter_key(VALID_ID, 1),
                duration_seconds=42.0,
            ),
        ],
        created_at=now,
        updated_at=now,
    )
    books_service.save_manifest(book)

    loaded = books_service.load_manifest(VALID_ID)
    assert loaded.id == VALID_ID
    assert loaded.title == "My Book"
    assert loaded.chapter_count == 2
    assert loaded.chapters_rendered == 1
    assert loaded.duration_seconds == 42.0
    # Manifest never stores chapter text.
    assert "text" not in store[manifest_key(VALID_ID)]["chapters"][0]


def test_load_missing_manifest_raises(monkeypatch):
    monkeypatch.setattr(books_service, "read_json", lambda k: None)
    with pytest.raises(BookNotFoundError):
        books_service.load_manifest(VALID_ID)


def test_book_detail_exposes_derived_fields(monkeypatch):
    now = datetime.now(UTC)
    book = Book(
        id=VALID_ID,
        title="Derived",
        voice_id="alloy",
        chapters=[
            Chapter(
                index=0,
                title="One",
                char_count=5,
                status=NarrationStatus.COMPLETE,
                duration_seconds=3661.0,
            )
        ],
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(books_service, "read_json", lambda k: book.model_dump(mode="json"))
    detail = books_service.get_book(VALID_ID)
    assert detail.chapter_count == 1
    assert detail.chapters_rendered == 1
    assert detail.duration_human == "1h 1m"
    assert detail.chapters[0].duration_seconds == 3661.0


def test_legacy_manifest_defaults_to_local_owner(monkeypatch):
    now = datetime.now(UTC)
    legacy_manifest = {
        "id": VALID_ID,
        "title": "Legacy",
        "voice_id": "alloy",
        "chapters": [],
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    monkeypatch.setattr(books_service, "read_json", lambda k: legacy_manifest)

    detail = books_service.get_book(VALID_ID, owner_id="local-dev")

    assert detail.id == VALID_ID


def test_book_owner_authorization_filters_and_denies(monkeypatch):
    now = datetime.now(UTC)
    other_id = "abcdef12-1234-1234-1234-123456789abc"
    mine = Book(
        id=VALID_ID,
        owner_id="user-a",
        title="Mine",
        voice_id="alloy",
        chapters=[Chapter(index=0, title="One", char_count=5)],
        created_at=now,
        updated_at=now,
    )
    other = Book(
        id=other_id,
        owner_id="user-b",
        title="Other",
        voice_id="alloy",
        chapters=[Chapter(index=0, title="One", char_count=5, audio_key="chapter.mp3")],
        master_key="master.m4b",
        created_at=now,
        updated_at=now,
    )
    manifests = {
        manifest_key(VALID_ID): mine.model_dump(mode="json"),
        manifest_key(other_id): other.model_dump(mode="json"),
    }
    monkeypatch.setattr(books_service, "read_json", lambda k: manifests.get(k))
    monkeypatch.setattr(
        books_service,
        "list_prefixes",
        lambda prefix, limit=None: [
            f"audiobooks/{VALID_ID}/",
            f"audiobooks/{other_id}/",
        ],
    )
    monkeypatch.setattr(books_service, "delete_prefix", lambda prefix: 1)

    assert [b.id for b in books_service.list_books(owner_id="user-a")] == [VALID_ID]
    with pytest.raises(BookAccessError):
        books_service.get_book(other_id, owner_id="user-a")
    with pytest.raises(BookAccessError):
        books_service.master_download_url(other_id, owner_id="user-a")
    with pytest.raises(BookAccessError):
        books_service.chapter_stream_url(other_id, 0, owner_id="user-a")
    with pytest.raises(BookAccessError):
        books_service.delete_book(other_id, owner_id="user-a")


def test_book_stats_reuses_loaded_owned_ids_for_size(monkeypatch):
    now = datetime.now(UTC)
    other_id = "abcdef12-1234-1234-1234-123456789abc"
    mine = Book(
        id=VALID_ID,
        owner_id="user-a",
        title="Mine",
        voice_id="alloy",
        chapters=[
            Chapter(
                index=0,
                title="One",
                char_count=5,
                status=NarrationStatus.COMPLETE,
                duration_seconds=10.0,
            )
        ],
        created_at=now,
        updated_at=now,
    )
    other = Book(
        id=other_id,
        owner_id="user-b",
        title="Other",
        voice_id="alloy",
        chapters=[Chapter(index=0, title="One", char_count=5)],
        created_at=now,
        updated_at=now,
    )
    manifests = {
        manifest_key(VALID_ID): mine.model_dump(mode="json"),
        manifest_key(other_id): other.model_dump(mode="json"),
    }
    reads: list[str] = []
    sized_prefixes: list[str] = []
    monkeypatch.setattr(
        books_service,
        "list_prefixes",
        lambda prefix, limit=None: [
            f"audiobooks/{VALID_ID}/",
            f"audiobooks/{other_id}/",
        ],
    )

    def read_json(key):
        reads.append(key)
        return manifests.get(key)

    def prefix_size(prefix):
        sized_prefixes.append(prefix)
        return 7

    monkeypatch.setattr(books_service, "read_json", read_json)
    monkeypatch.setattr(books_service, "prefix_size", prefix_size)

    stats = books_service.book_stats(owner_id="user-a")

    assert stats.total_books == 1
    assert stats.total_chapters == 1
    assert stats.total_duration_seconds == 10.0
    assert stats.total_size_bytes == 7
    assert reads == [manifest_key(VALID_ID), manifest_key(other_id)]
    assert sized_prefixes == [books_service.book_prefix(VALID_ID)]
