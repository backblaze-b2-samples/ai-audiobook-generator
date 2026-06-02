"""Tests for narration orchestration with a mocked TTS adapter and B2 store."""

from datetime import UTC, datetime

from app.repo.tts.base import TTSProvider
from app.service import narration as narration_service
from app.types import CreateBookRequest, NarrationStatus, Voice


class FakeProvider(TTSProvider):
    def list_voices(self):
        return [Voice(id="alloy", name="Alloy", description="test")]

    def default_voice_id(self):
        return "alloy"

    def synthesize(self, text, voice_id):
        return f"AUDIO[{voice_id}]:{text[:8]}".encode()


def _install_fakes(monkeypatch):
    """Wire narration + books to an in-memory B2 store and fake TTS/ffmpeg."""
    objects: dict[str, bytes] = {}
    manifests: dict[str, dict] = {}

    monkeypatch.setattr(narration_service, "get_provider", lambda: FakeProvider())
    monkeypatch.setattr(
        narration_service, "put_bytes", lambda data, key, ct: objects.__setitem__(key, data)
    )
    monkeypatch.setattr(narration_service, "_extract_audio_metadata", lambda data: {"duration_seconds": 12.0})
    # Master assembly: pretend ffmpeg produced bytes.
    monkeypatch.setattr(narration_service, "assemble_master", lambda blobs, meta: b"M4B")
    monkeypatch.setattr(narration_service, "read_object", lambda key: objects.get(key))

    from app.service import books as books_service

    monkeypatch.setattr(books_service, "write_json", lambda k, o: manifests.__setitem__(k, o))
    monkeypatch.setattr(books_service, "read_json", lambda k: manifests.get(k))
    monkeypatch.setattr(books_service, "get_presigned_url", lambda key, filename=None: "url")
    monkeypatch.setattr(books_service, "get_stream_url", lambda key, expires_in=600: "stream")
    return objects, manifests


def test_create_book_writes_source_and_manifest(monkeypatch):
    objects, manifests = _install_fakes(monkeypatch)
    req = CreateBookRequest(
        title="Test Book",
        text="Chapter 1\nFirst.\n\nChapter 2\nSecond.",
    )
    book = narration_service.create_book(req)
    assert book.status == NarrationStatus.PENDING
    assert book.chapter_count == 2
    assert book.voice_id == "alloy"
    # source.txt written, manifest written.
    assert any(k.endswith("source.txt") for k in objects)
    assert any(k.endswith("manifest.json") for k in manifests)


def test_run_narration_renders_all_chapters_and_master(monkeypatch):
    objects, _ = _install_fakes(monkeypatch)
    req = CreateBookRequest(title="Run", text="Chapter 1\nA.\n\nChapter 2\nB.")
    book = narration_service.create_book(req)

    narration_service.run_narration(book.id)

    final = narration_service.get_book_detail(book.id)
    assert final.status == NarrationStatus.COMPLETE
    assert final.chapters_rendered == 2
    assert final.master_key is not None
    assert final.duration_seconds == 24.0  # 2 chapters * 12s
    # Each chapter wrote an mp3 + a master.
    assert sum(1 for k in objects if k.endswith(".mp3")) == 2
    assert any(k.endswith("master.m4b") for k in objects)


def test_run_narration_marks_failed_on_tts_error(monkeypatch):
    _install_fakes(monkeypatch)

    class BoomProvider(FakeProvider):
        def synthesize(self, text, voice_id):
            from app.repo.tts.base import TTSError

            raise TTSError("provider down")

    req = CreateBookRequest(title="Boom", text="Chapter 1\nA.")
    book = narration_service.create_book(req)
    monkeypatch.setattr(narration_service, "get_provider", lambda: BoomProvider())

    narration_service.run_narration(book.id)
    final = narration_service.get_book_detail(book.id)
    assert final.status == NarrationStatus.FAILED
    assert "provider down" in (final.error or "")


def test_list_voices_uses_provider(monkeypatch):
    monkeypatch.setattr(narration_service, "get_provider", lambda: FakeProvider())
    voices = narration_service.list_voices()
    assert voices[0].id == "alloy"


def test_created_at_is_timestamp(monkeypatch):
    _install_fakes(monkeypatch)
    book = narration_service.create_book(
        CreateBookRequest(title="Ts", text="Chapter 1\nA.")
    )
    assert isinstance(book.created_at, datetime)
    assert book.created_at.tzinfo is UTC
