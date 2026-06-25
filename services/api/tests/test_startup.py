"""Startup validation tests."""

import pytest

from app.config import settings
from main import lifespan


def _set_required_b2(monkeypatch):
    monkeypatch.setattr(settings, "b2_application_key_id", "key-id")
    monkeypatch.setattr(settings, "b2_application_key", "key")
    monkeypatch.setattr(settings, "b2_bucket_name", "bucket")
    monkeypatch.setattr(settings, "b2_endpoint", "https://s3.example.com")
    monkeypatch.setattr(settings, "b2_region", "us-west-004")


@pytest.mark.asyncio
async def test_startup_requires_book_auth_tokens(monkeypatch):
    _set_required_b2(monkeypatch)
    monkeypatch.setattr(settings, "book_auth_tokens", "")

    with pytest.raises(RuntimeError, match="BOOK_AUTH_TOKENS"):
        async with lifespan(None):
            pass


@pytest.mark.asyncio
async def test_startup_rejects_book_auth_placeholder(monkeypatch):
    _set_required_b2(monkeypatch)
    monkeypatch.setattr(
        settings,
        "book_auth_tokens",
        "prod:strong-token,local-dev:replace-with-a-random-token",
    )

    with pytest.raises(RuntimeError, match="BOOK_AUTH_TOKENS"):
        async with lifespan(None):
            pass
