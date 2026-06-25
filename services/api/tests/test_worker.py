"""Tests for worker startup error handling."""

import logging

import pytest

import worker


def test_resume_scan_lease_error_logs_safely(monkeypatch, caplog):
    monkeypatch.setattr(
        worker,
        "acquire_resume_scan_lease",
        lambda: (_ for _ in ()).throw(
            worker.JobLeaseError("redis://private-host:6379 timed out")
        ),
    )

    with caplog.at_level(logging.INFO, logger=worker.logger.name):
        worker._resume_existing_books()

    assert "private-host" not in caplog.text
    assert "JobLeaseError" in caplog.text


def test_worker_queue_error_logs_safely(monkeypatch, caplog):
    class NoopThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(worker, "Thread", NoopThread)
    monkeypatch.setattr(
        worker,
        "run_worker",
        lambda allowed_targets: (_ for _ in ()).throw(
            worker.JobQueueError("redis://private-host:6379 timed out")
        ),
    )

    with (
        caplog.at_level(logging.ERROR, logger=worker.logger.name),
        pytest.raises(SystemExit),
    ):
        worker.main()

    assert "private-host" not in caplog.text
    assert "JobQueueError" in caplog.text


def test_resume_scan_queue_error_logs_safely(monkeypatch, caplog):
    class FakeLease:
        released = False

        def release(self):
            self.released = True

    lease = FakeLease()
    monkeypatch.setattr(worker, "acquire_resume_scan_lease", lambda: lease)
    monkeypatch.setattr(
        worker,
        "enqueue_resume_candidates",
        lambda limit: (_ for _ in ()).throw(
            worker.JobQueueError("redis://private-host:6379 timed out")
        ),
    )

    with caplog.at_level(logging.ERROR, logger=worker.logger.name):
        worker._resume_existing_books()

    assert lease.released is True
    assert "private-host" not in caplog.text
    assert "JobQueueError" in caplog.text
