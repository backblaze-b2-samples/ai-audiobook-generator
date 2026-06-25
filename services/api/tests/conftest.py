import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers():
    return {"X-Book-Owner": "local-dev", "X-Book-Token": "dev-book-token"}


@pytest.fixture(autouse=True)
def configure_book_auth(monkeypatch):
    from app.config import settings
    from app.runtime import book_auth

    monkeypatch.setattr(settings, "book_auth_tokens", "local-dev:dev-book-token")
    book_auth._configured_tokens.cache_clear()
    yield
    book_auth._configured_tokens.cache_clear()


@pytest.fixture(autouse=True)
def isolate_download_counter(tmp_path, monkeypatch):
    """Redirect the persisted download counter to a temp file per test and
    reset the in-memory counter to 0. Keeps tests hermetic and prevents
    stray writes to services/api/data/."""
    from app.config import settings
    from app.service import files as files_service

    counter_path = tmp_path / "download_count.json"
    monkeypatch.setattr(settings, "download_count_file", str(counter_path))
    monkeypatch.setattr(files_service, "_download_count", 0)
    yield
