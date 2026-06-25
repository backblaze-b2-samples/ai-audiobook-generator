"""Tests for Redis/RQ queue hardening."""

import pytest
from rq import Worker

from app.repo.job_queue import JobSecurityError, RestrictedWorker
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
