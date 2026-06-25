"""Runtime tests for audiobook routes."""

import logging

import pytest

from app.config import settings
from app.repo import JobQueueError
from app.runtime import books as books_runtime
from app.service import books as books_service
from app.service import narration as narration_service
from app.types import Book, Chapter, NarrationStatus
from tests.test_narration import _install_fakes

VALID_ID = "12345678-1234-1234-1234-123456789abc"


@pytest.mark.asyncio
async def test_book_routes_require_auth(client):
    response = await client.get("/books")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_book_routes_enforce_owner_scope(client, monkeypatch):
    _, manifests = _install_fakes(monkeypatch)
    monkeypatch.setattr(settings, "book_auth_tokens", "user-a:token-a,user-b:token-b")
    other_id = "abcdef12-1234-1234-1234-123456789abc"
    mine = Book(
        id=VALID_ID,
        owner_id="user-a",
        title="Mine",
        voice_id="alloy",
        status=NarrationStatus.COMPLETE,
        chapters=[Chapter(index=0, title="One", char_count=5)],
        created_at=narration_service._now(),
        updated_at=narration_service._now(),
    )
    other = Book(
        id=other_id,
        owner_id="user-b",
        title="Other",
        voice_id="alloy",
        status=NarrationStatus.COMPLETE,
        chapters=[
            Chapter(
                index=0,
                title="One",
                char_count=5,
                audio_key=books_service.chapter_key(other_id, 0),
            )
        ],
        master_key=books_service.master_key(other_id),
        created_at=narration_service._now(),
        updated_at=narration_service._now(),
    )
    manifests[books_service.manifest_key(VALID_ID)] = mine.model_dump(mode="json")
    manifests[books_service.manifest_key(other_id)] = other.model_dump(mode="json")
    monkeypatch.setattr(
        books_service,
        "list_prefixes",
        lambda prefix, limit=None: [
            books_service.book_prefix(VALID_ID),
            books_service.book_prefix(other_id),
        ],
    )

    headers = {"X-Book-Owner": "user-a", "X-Book-Token": "token-a"}

    list_response = await client.get("/books", headers=headers)
    read_response = await client.get(f"/books/{other_id}", headers=headers)
    master_response = await client.get(
        f"/books/{other_id}/master/download", headers=headers
    )
    stream_response = await client.get(
        f"/books/{other_id}/chapters/0/stream", headers=headers
    )
    delete_response = await client.delete(f"/books/{other_id}", headers=headers)

    assert list_response.status_code == 200
    assert [book["id"] for book in list_response.json()] == [VALID_ID]
    assert read_response.status_code == 404
    assert master_response.status_code == 404
    assert stream_response.status_code == 404
    assert delete_response.status_code == 404
    assert books_service.manifest_key(other_id) in manifests


@pytest.mark.asyncio
async def test_create_book_queue_error_cleans_persisted_book(client, monkeypatch, caplog):
    objects, manifests = _install_fakes(monkeypatch)
    monkeypatch.setattr(books_runtime, "create_book", narration_service.create_book)
    monkeypatch.setattr(
        books_runtime,
        "enqueue_narration_job",
        lambda book_id: (_ for _ in ()).throw(
            JobQueueError("redis://private-host:6379 timed out")
        ),
    )

    with caplog.at_level(logging.ERROR, logger=books_runtime.logger.name):
        response = await client.post(
            "/books",
            json={"title": "Queue Down", "text": "Chapter 1\nSecret text."},
            headers={"X-Book-Owner": "local-dev", "X-Book-Token": "dev-book-token"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Narration queue unavailable"
    assert "private-host" not in response.text
    assert "private-host" not in caplog.text
    assert "JobQueueError" in caplog.text
    assert objects == {}
    assert manifests == {}


@pytest.mark.asyncio
async def test_delete_book_cancels_narration_before_deleting(client, monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        books_runtime,
        "get_book",
        lambda book_id, owner_id=None: type("Book", (), {"status": "rendering"})(),
    )
    monkeypatch.setattr(
        books_runtime,
        "cancel_narration_for_book",
        lambda book_id: calls.append(("cancel", book_id)),
    )
    monkeypatch.setattr(
        books_runtime,
        "delete_book",
        lambda book_id, owner_id=None: calls.append(("delete", book_id)) or 3,
    )

    response = await client.delete(
        f"/books/{VALID_ID}",
        headers={"X-Book-Owner": "local-dev", "X-Book-Token": "dev-book-token"},
    )

    assert response.status_code == 200
    assert calls == [("cancel", VALID_ID), ("delete", VALID_ID)]


@pytest.mark.asyncio
async def test_delete_book_queue_error_logs_safely(client, monkeypatch, caplog):
    monkeypatch.setattr(
        books_runtime,
        "get_book",
        lambda book_id, owner_id=None: type("Book", (), {"status": "rendering"})(),
    )
    monkeypatch.setattr(
        books_runtime,
        "cancel_narration_for_book",
        lambda book_id: (_ for _ in ()).throw(
            JobQueueError("redis://private-host:6379 timed out")
        ),
    )

    with caplog.at_level(logging.ERROR, logger=books_runtime.logger.name):
        response = await client.delete(
            f"/books/{VALID_ID}",
            headers={"X-Book-Owner": "local-dev", "X-Book-Token": "dev-book-token"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Narration queue unavailable"
    assert "private-host" not in response.text
    assert "private-host" not in caplog.text
    assert "JobQueueError" in caplog.text


@pytest.mark.asyncio
async def test_delete_completed_book_skips_queue_cancel(client, monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        books_runtime,
        "get_book",
        lambda book_id, owner_id=None: type("Book", (), {"status": "complete"})(),
    )
    monkeypatch.setattr(
        books_runtime,
        "cancel_narration_for_book",
        lambda book_id: (_ for _ in ()).throw(JobQueueError("redis down")),
    )
    monkeypatch.setattr(
        books_runtime,
        "delete_book",
        lambda book_id, owner_id=None: calls.append(("delete", book_id)) or 2,
    )

    response = await client.delete(
        f"/books/{VALID_ID}",
        headers={"X-Book-Owner": "local-dev", "X-Book-Token": "dev-book-token"},
    )

    assert response.status_code == 200
    assert calls == [("delete", VALID_ID)]
