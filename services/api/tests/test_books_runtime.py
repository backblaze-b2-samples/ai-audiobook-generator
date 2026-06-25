"""Runtime tests for audiobook routes."""

import logging

import pytest

from app.repo import JobQueueError
from app.runtime import books as books_runtime
from app.service import narration as narration_service
from tests.test_narration import _install_fakes

VALID_ID = "12345678-1234-1234-1234-123456789abc"


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
    monkeypatch.setattr(books_runtime, "get_book", lambda book_id: object())
    monkeypatch.setattr(
        books_runtime,
        "cancel_narration_for_book",
        lambda book_id: calls.append(("cancel", book_id)),
    )
    monkeypatch.setattr(
        books_runtime,
        "delete_book",
        lambda book_id: calls.append(("delete", book_id)) or 3,
    )

    response = await client.delete(f"/books/{VALID_ID}")

    assert response.status_code == 200
    assert calls == [("cancel", VALID_ID), ("delete", VALID_ID)]


@pytest.mark.asyncio
async def test_delete_book_queue_error_logs_safely(client, monkeypatch, caplog):
    monkeypatch.setattr(books_runtime, "get_book", lambda book_id: object())
    monkeypatch.setattr(
        books_runtime,
        "cancel_narration_for_book",
        lambda book_id: (_ for _ in ()).throw(
            JobQueueError("redis://private-host:6379 timed out")
        ),
    )

    with caplog.at_level(logging.ERROR, logger=books_runtime.logger.name):
        response = await client.delete(f"/books/{VALID_ID}")

    assert response.status_code == 503
    assert response.json()["detail"] == "Narration queue unavailable"
    assert "private-host" not in response.text
    assert "private-host" not in caplog.text
    assert "JobQueueError" in caplog.text
