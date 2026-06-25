"""Tests for narration orchestration with a mocked TTS adapter and B2 store."""

from datetime import UTC, datetime

from app.repo.tts.base import TTSProvider
from app.service import narration as narration_service
from app.types import BookSummary, CreateBookRequest, NarrationStatus, Voice


class FakeProvider(TTSProvider):
    def list_voices(self):
        return [Voice(id="alloy", name="Alloy", description="test")]

    def default_voice_id(self):
        return "alloy"

    def synthesize(self, text, voice_id):
        # Mirror the real provider's contract: empty input is rejected. This
        # guards against the manifest-reload regression where chapter.text was
        # "" because it is excluded from manifest.json.
        if not text:
            from app.repo.tts.base import TTSError

            raise TTSError("empty TTS input")
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


def test_run_narration_synthesizes_real_chapter_text(monkeypatch):
    """run_narration must repopulate chapter text from source.txt before
    synthesize. The manifest excludes `text`, so after the load_manifest
    reload the provider would otherwise receive empty input (HTTP 400)."""
    _install_fakes(monkeypatch)
    captured: list[str] = []

    class CapturingProvider(FakeProvider):
        def synthesize(self, text, voice_id):
            captured.append(text)
            return super().synthesize(text, voice_id)

    req = CreateBookRequest(
        title="RealText",
        text="Chapter 1\nFirst body.\n\nChapter 2\nSecond body.",
    )
    book = narration_service.create_book(req)
    monkeypatch.setattr(narration_service, "get_provider", lambda: CapturingProvider())

    narration_service.run_narration(book.id)

    final = narration_service.get_book_detail(book.id)
    assert final.status == NarrationStatus.COMPLETE
    # Each chapter's actual (non-empty) body reached the provider.
    assert len(captured) == 2
    assert all(text for text in captured)
    assert "First body." in captured[0]
    assert "Second body." in captured[1]


def test_run_narration_resumes_from_chapter_status(monkeypatch):
    objects, _ = _install_fakes(monkeypatch)
    captured: list[str] = []

    class CapturingProvider(FakeProvider):
        def synthesize(self, text, voice_id):
            captured.append(text)
            return super().synthesize(text, voice_id)

    req = CreateBookRequest(
        title="Resume",
        text="Chapter 1\nAlready rendered.\n\nChapter 2\nNeeds render.",
    )
    book = narration_service.create_book(req)
    book.chapters[0].status = NarrationStatus.COMPLETE
    book.chapters[0].audio_key = "audiobooks/fake/chapters/ch-001.mp3"
    book.chapters[0].duration_seconds = 3.0
    objects[book.chapters[0].audio_key] = b"ALREADY_RENDERED"

    from app.service import books as books_service

    books_service.save_manifest(book)
    monkeypatch.setattr(narration_service, "get_provider", lambda: CapturingProvider())

    narration_service.run_narration(book.id)

    final = narration_service.get_book_detail(book.id)
    assert final.status == NarrationStatus.COMPLETE
    assert final.chapters_rendered == 2
    assert captured == ["Needs render."]


def test_run_narration_fails_when_source_missing(monkeypatch):
    """If source.txt is gone the job fails cleanly rather than sending empty
    text to the provider."""
    objects, _ = _install_fakes(monkeypatch)
    req = CreateBookRequest(title="NoSource", text="Chapter 1\nA.")
    book = narration_service.create_book(req)
    # Drop the source so repopulation cannot find it.
    for key in [k for k in objects if k.endswith("source.txt")]:
        del objects[key]

    narration_service.run_narration(book.id)
    final = narration_service.get_book_detail(book.id)
    assert final.status == NarrationStatus.FAILED
    assert "source" in (final.error or "").lower()


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
    assert final.chapters[0].status == NarrationStatus.FAILED
    assert "provider down" in (final.chapters[0].error or "")


def test_enqueue_resume_candidates_queues_only_incomplete_books(monkeypatch):
    now = datetime.now(UTC)
    summaries = [
        BookSummary(
            id="12345678-1234-1234-1234-123456789abc",
            title="Pending",
            status=NarrationStatus.PENDING,
            chapter_count=1,
            chapters_rendered=0,
            duration_seconds=0.0,
            duration_human="0s",
            created_at=now,
        ),
        BookSummary(
            id="22345678-1234-1234-1234-123456789abc",
            title="Rendering",
            status=NarrationStatus.RENDERING,
            chapter_count=2,
            chapters_rendered=1,
            duration_seconds=12.0,
            duration_human="12s",
            created_at=now,
        ),
        BookSummary(
            id="32345678-1234-1234-1234-123456789abc",
            title="Complete",
            status=NarrationStatus.COMPLETE,
            chapter_count=1,
            chapters_rendered=1,
            duration_seconds=12.0,
            duration_human="12s",
            created_at=now,
        ),
    ]

    from app.service import books as books_service

    queued: list[str] = []
    monkeypatch.setattr(books_service, "list_books", lambda: summaries)
    monkeypatch.setattr(
        narration_service,
        "enqueue_narration",
        lambda book_id: queued.append(book_id),
    )

    count = narration_service.enqueue_resume_candidates()

    assert count == 2
    assert queued == [
        "12345678-1234-1234-1234-123456789abc",
        "22345678-1234-1234-1234-123456789abc",
    ]


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
