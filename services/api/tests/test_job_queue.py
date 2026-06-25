"""Tests for Redis/RQ queue hardening."""

import pytest
from redis.exceptions import RedisError
from rq import Worker
from rq.job import JobStatus

from app.repo import job_queue as job_queue_repo
from app.repo.job_queue import (
    JobLeaseError,
    JobQueueError,
    JobSecurityError,
    RedisLease,
    RestrictedWorker,
)
from app.service import narration as narration_service
from app.service.books import BookKeyError


class FakeJob:
    def __init__(self, func_name, args=(), kwargs=None):
        self.func_name = func_name
        self.args = args
        self.kwargs = kwargs or {}


def test_restricted_worker_rejects_forged_target(monkeypatch):
    called = False

    def fake_perform_job(self, job, queue):
        nonlocal called
        called = True
        return True

    worker = object.__new__(RestrictedWorker)
    worker.allowed_targets = {
        narration_service.NARRATION_JOB_TARGET: narration_service.validate_narration_job
    }
    monkeypatch.setattr(Worker, "perform_job", fake_perform_job)

    with pytest.raises(JobSecurityError):
        RestrictedWorker.perform_job(
            worker,
            FakeJob("os.system", args=("echo nope",)),
            object(),
        )

    assert called is False


def test_narration_queue_target_resolves_to_runner():
    module_name, func_name = narration_service.NARRATION_JOB_TARGET.rsplit(".", 1)

    import importlib

    target = getattr(importlib.import_module(module_name), func_name)
    assert target is narration_service.run_narration


def test_narration_job_rejects_non_uuid_argument():
    with pytest.raises(BookKeyError):
        narration_service.validate_narration_job(("not-a-uuid",), {})


def test_narration_job_rejects_non_string_argument():
    with pytest.raises(ValueError, match="book id must be a string"):
        narration_service.validate_narration_job(({"id": "not-a-string"},), {})


def test_redis_lease_refresh_error_is_sanitized():
    class FakeLock:
        def reacquire(self):
            raise RedisError("redis://private-host:6379 timed out")

    with pytest.raises(JobLeaseError) as exc_info:
        RedisLease(FakeLock()).refresh()

    assert "private-host" not in str(exc_info.value)
    assert "RedisError" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, RedisError)


def test_enqueue_job_redis_error_is_sanitized(monkeypatch):
    class FakeQueue:
        def fetch_job(self, job_id):
            raise RedisError("redis://private-host:6379 timed out")

    monkeypatch.setattr(job_queue_repo, "_connection", lambda: object())
    monkeypatch.setattr(job_queue_repo, "_queue", lambda connection: FakeQueue())

    with pytest.raises(JobQueueError) as exc_info:
        job_queue_repo.enqueue_job("app.service.narration.run_narration", (), "job")

    assert "private-host" not in str(exc_info.value)
    assert "RedisError" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, RedisError)


def test_enqueue_job_uses_rq_2_compatible_options(monkeypatch):
    class FakeJob:
        id = "job"

    class FakeQueue:
        enqueue_kwargs = None

        def fetch_job(self, job_id):
            return None

        def enqueue_call(self, **kwargs):
            self.enqueue_kwargs = kwargs
            return FakeJob()

    queue = FakeQueue()
    monkeypatch.setattr(job_queue_repo, "_connection", lambda: object())
    monkeypatch.setattr(job_queue_repo, "_queue", lambda connection: queue)

    assert job_queue_repo.enqueue_job("app.service.narration.run_narration", (), "job") == "job"
    assert queue.enqueue_kwargs is not None
    assert "unique" not in queue.enqueue_kwargs


def test_enqueue_job_reuses_valid_queued_job(monkeypatch):
    class ExistingJob:
        id = "narration:book-id"
        func_name = "app.service.narration.run_narration"
        args = ("book-id",)

        def __init__(self):
            self.kwargs = {}

        def get_status(self, refresh=False):
            return JobStatus.QUEUED

    class FakeQueue:
        def fetch_job(self, job_id):
            return ExistingJob()

    monkeypatch.setattr(job_queue_repo, "_connection", lambda: object())
    monkeypatch.setattr(job_queue_repo, "_queue", lambda connection: FakeQueue())

    job_id = job_queue_repo.enqueue_job(
        "app.service.narration.run_narration",
        ("book-id",),
        "narration:book-id",
    )

    assert job_id == "narration:book-id"


@pytest.mark.parametrize(
    ("status", "func_name", "args", "existing_id"),
    [
        (JobStatus.STARTED, "app.service.narration.run_narration", ("book-id",), "narration:book-id"),
        (JobStatus.QUEUED, "os.system", ("book-id",), "narration:book-id"),
        (JobStatus.QUEUED, "app.service.narration.run_narration", ("other",), "narration:book-id"),
        (JobStatus.QUEUED, "app.service.narration.run_narration", ("book-id",), "narration:other"),
    ],
)
def test_enqueue_job_replaces_stale_or_poisoned_active_jobs(
    monkeypatch, status, func_name, args, existing_id
):
    class ExistingJob:
        id = existing_id

        def __init__(self):
            self.func_name = func_name
            self.args = args
            self.kwargs = {}
            self.deleted = False
            self.canceled = False

        def get_status(self, refresh=False):
            return status

        def cancel(self):
            self.canceled = True

        def delete(self):
            self.deleted = True

    class NewJob:
        id = "narration:book-id"

    class FakeQueue:
        existing = ExistingJob()

        def fetch_job(self, job_id):
            return self.existing

        def enqueue_call(self, **kwargs):
            return NewJob()

    queue = FakeQueue()
    monkeypatch.setattr(job_queue_repo, "_connection", lambda: object())
    monkeypatch.setattr(job_queue_repo, "_queue", lambda connection: queue)

    job_id = job_queue_repo.enqueue_job(
        "app.service.narration.run_narration",
        ("book-id",),
        "narration:book-id",
    )

    assert job_id == "narration:book-id"
    assert queue.existing.canceled is True
    assert queue.existing.deleted is True
