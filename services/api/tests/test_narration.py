"""Tests for narration orchestration with a mocked TTS adapter and B2 store."""

from datetime import UTC, datetime

import pytest

from app.repo.tts.base import TTSProvider
from app.service import narration as narration_service
from app.types import BookSummary, CreateBookRequest, NarrationStatus, Voice

VALID_ID = "12345678-1234-1234-1234-123456789abc"


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


class FakeLease:
    def __init__(self):
        self.refreshes = 0
        self.released = False

    def refresh(self):
        self.refreshes += 1

    def release(self):
        self.released = True


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
    monkeypatch.setattr(narration_service, "acquire_book_lease", lambda book_id: FakeLease())
    monkeypatch.setattr(narration_service, "is_book_tombstoned", lambda book_id: False)
    monkeypatch.setattr(narration_service, "current_job_retries_left", lambda: None)

    from app.service import books as books_service

    monkeypatch.setattr(books_service, "write_json", lambda k, o: manifests.__setitem__(k, o))
    monkeypatch.setattr(books_service, "read_json", lambda k: manifests.get(k))
    monkeypatch.setattr(books_service, "get_presigned_url", lambda key, filename=None: "url")
    monkeypatch.setattr(books_service, "get_stream_url", lambda key, expires_in=600: "stream")
    monkeypatch.setattr(books_service, "delete_prefix", _delete_from(objects, manifests))
    return objects, manifests


def _delete_from(objects, manifests):
    def delete_prefix(prefix):
        deleted = 0
        for store in (objects, manifests):
            for key in [k for k in store if k.startswith(prefix)]:
                del store[key]
                deleted += 1
        return deleted

    return delete_prefix


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
    assert final.chapters[0].status == NarrationStatus.FAILED
    assert "source" in (final.chapters[0].error or "").lower()


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


def test_run_narration_retries_transient_tts_error(monkeypatch):
    _install_fakes(monkeypatch)
    attempts = 0

    class FlakyProvider(FakeProvider):
        def synthesize(self, text, voice_id):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                from app.repo.tts.base import TTSError

                raise TTSError("temporary provider outage")
            return super().synthesize(text, voice_id)

    req = CreateBookRequest(title="Retry", text="Chapter 1\nA.")
    book = narration_service.create_book(req)
    monkeypatch.setattr(narration_service, "get_provider", lambda: FlakyProvider())
    monkeypatch.setattr(narration_service, "current_job_retries_left", lambda: 1)

    from app.repo.tts.base import TTSError

    with pytest.raises(TTSError):
        narration_service.run_narration(book.id)

    mid = narration_service.get_book_detail(book.id)
    assert mid.status == NarrationStatus.RENDERING
    assert mid.chapters[0].status == NarrationStatus.RENDERING

    monkeypatch.setattr(narration_service, "current_job_retries_left", lambda: 0)
    narration_service.run_narration(book.id)

    final = narration_service.get_book_detail(book.id)
    assert final.status == NarrationStatus.COMPLETE
    assert attempts == 2


def test_run_narration_marks_failed_on_final_worker_error(monkeypatch):
    _install_fakes(monkeypatch)
    req = CreateBookRequest(title="B2 Fail", text="Chapter 1\nA.")
    book = narration_service.create_book(req)
    monkeypatch.setattr(narration_service, "current_job_retries_left", lambda: 0)
    monkeypatch.setattr(
        narration_service,
        "put_bytes",
        lambda data, key, content_type: (_ for _ in ()).throw(
            RuntimeError("redis://private-host should not leak")
        ),
    )

    narration_service.run_narration(book.id)

    final = narration_service.get_book_detail(book.id)
    assert final.status == NarrationStatus.FAILED
    assert final.error == "Worker failure: RuntimeError"
    assert "private-host" not in final.error


def test_run_narration_does_not_retry_missing_source(monkeypatch):
    objects, _ = _install_fakes(monkeypatch)
    req = CreateBookRequest(title="Missing Source", text="Chapter 1\nA.")
    book = narration_service.create_book(req)
    for key in list(objects):
        if key.endswith("source.txt"):
            del objects[key]
    monkeypatch.setattr(narration_service, "current_job_retries_left", lambda: 2)

    narration_service.run_narration(book.id)

    final = narration_service.get_book_detail(book.id)
    assert final.status == NarrationStatus.FAILED
    assert final.error is not None
    assert "Source manuscript missing" in final.error
    assert "Retrying narration" not in final.error


def test_run_narration_exits_when_book_lease_unavailable(monkeypatch, caplog):
    objects, _ = _install_fakes(monkeypatch)
    req = CreateBookRequest(title="Lease", text="Chapter 1\nA.")
    book = narration_service.create_book(req)

    from app.repo import JobLeaseError

    monkeypatch.setattr(
        narration_service,
        "acquire_book_lease",
        lambda book_id: (_ for _ in ()).throw(
            JobLeaseError("redis://private-host:6379 timed out")
        ),
    )

    with (
        caplog.at_level("INFO", logger=narration_service.logger.name),
        pytest.raises(JobLeaseError),
    ):
        narration_service.run_narration(book.id)

    final = narration_service.get_book_detail(book.id)
    assert final.status == NarrationStatus.PENDING
    assert sum(1 for key in objects if key.endswith(".mp3")) == 0
    assert "private-host" not in caplog.text
    assert "JobLeaseError" in caplog.text


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

    queued: list[tuple[str, tuple, str]] = []
    by_id = {summary.id: summary for summary in summaries}
    monkeypatch.setattr(books_service, "list_book_ids", lambda: list(by_id))
    monkeypatch.setattr(books_service, "load_manifest", lambda book_id: by_id[book_id])
    monkeypatch.setattr(
        narration_service,
        "enqueue_job",
        lambda target, args, job_id: queued.append((target, args, job_id)),
    )

    count = narration_service.enqueue_resume_candidates()

    assert count == 2
    assert queued == [
        (
            narration_service.NARRATION_JOB_TARGET,
            ("12345678-1234-1234-1234-123456789abc",),
            "narration:12345678-1234-1234-1234-123456789abc",
        ),
        (
            narration_service.NARRATION_JOB_TARGET,
            ("22345678-1234-1234-1234-123456789abc",),
            "narration:22345678-1234-1234-1234-123456789abc",
        ),
    ]


def test_enqueue_resume_candidates_scans_beyond_first_batch(monkeypatch):
    now = datetime.now(UTC)
    ids = [f"{i:08x}-1234-1234-1234-123456789abc" for i in range(150)]
    pending_id = ids[-1]

    from app.service import books as books_service

    def load_manifest(book_id):
        return BookSummary(
            id=book_id,
            title=book_id,
            status=(
                NarrationStatus.PENDING
                if book_id == pending_id
                else NarrationStatus.COMPLETE
            ),
            chapter_count=1,
            chapters_rendered=0,
            duration_seconds=0.0,
            duration_human="0s",
            created_at=now,
        )

    queued: list[str] = []
    monkeypatch.setattr(books_service, "list_book_ids", lambda: ids)
    monkeypatch.setattr(books_service, "load_manifest", load_manifest)
    monkeypatch.setattr(
        narration_service,
        "enqueue_job",
        lambda target, args, job_id: queued.append(job_id),
    )

    count = narration_service.enqueue_resume_candidates(batch_size=100)

    assert count == 1
    assert queued == [f"narration:{pending_id}"]


def test_enqueue_resume_candidates_advances_bounded_cursor(monkeypatch):
    now = datetime.now(UTC)
    ids = [
        "22345678-1234-1234-1234-123456789abc",
        "32345678-1234-1234-1234-123456789abc",
    ]

    from app.service import books as books_service

    calls: list[tuple[int | None, str | None]] = []
    cursor_updates: list[str | None] = []
    queued: list[str] = []

    def list_book_ids(limit=None, start_after_id=None):
        calls.append((limit, start_after_id))
        return ids

    def load_manifest(book_id):
        return BookSummary(
            id=book_id,
            title=book_id,
            status=NarrationStatus.PENDING,
            chapter_count=1,
            chapters_rendered=0,
            duration_seconds=0.0,
            duration_human="0s",
            created_at=now,
        )

    monkeypatch.setattr(narration_service, "get_resume_scan_cursor", lambda: VALID_ID)
    monkeypatch.setattr(narration_service, "set_resume_scan_cursor", cursor_updates.append)
    monkeypatch.setattr(books_service, "list_book_ids", list_book_ids)
    monkeypatch.setattr(books_service, "load_manifest", load_manifest)
    monkeypatch.setattr(
        narration_service,
        "enqueue_job",
        lambda target, args, job_id: queued.append(job_id),
    )

    count = narration_service.enqueue_resume_candidates(max_manifests=2)

    assert count == 2
    assert calls == [(2, VALID_ID)]
    assert cursor_updates == [ids[-1]]
    assert queued == [f"narration:{book_id}" for book_id in ids]


def test_enqueue_resume_candidates_clears_cursor_at_end(monkeypatch):
    now = datetime.now(UTC)
    book_id = "22345678-1234-1234-1234-123456789abc"

    from app.service import books as books_service

    cursor_updates: list[str | None] = []
    monkeypatch.setattr(narration_service, "get_resume_scan_cursor", lambda: VALID_ID)
    monkeypatch.setattr(narration_service, "set_resume_scan_cursor", cursor_updates.append)
    monkeypatch.setattr(
        books_service,
        "list_book_ids",
        lambda limit=None, start_after_id=None: [book_id],
    )
    monkeypatch.setattr(
        books_service,
        "load_manifest",
        lambda loaded_id: BookSummary(
            id=loaded_id,
            title=loaded_id,
            status=NarrationStatus.COMPLETE,
            chapter_count=1,
            chapters_rendered=1,
            duration_seconds=0.0,
            duration_human="0s",
            created_at=now,
        ),
    )

    count = narration_service.enqueue_resume_candidates(max_manifests=2)

    assert count == 0
    assert cursor_updates == [None]


def test_enqueue_resume_candidates_zero_limit_does_not_scan(monkeypatch):
    from app.service import books as books_service

    monkeypatch.setattr(
        books_service,
        "list_book_ids",
        lambda limit=None, start_after_id=None: pytest.fail("should not scan"),
    )

    assert narration_service.enqueue_resume_candidates(max_manifests=0) == 0


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
