"""Durable queue and leases backed by Redis + RQ."""

from collections.abc import Callable
from dataclasses import dataclass

from redis import Redis
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, RedisError, TimeoutError
from redis.lock import Lock
from redis.retry import Retry as RedisRetry
from rq import Queue, Retry, Worker
from rq.exceptions import DuplicateJobError
from rq.job import JobStatus
from rq.serializers import JSONSerializer

from app.config import settings

ACTIVE_STATUSES = {
    JobStatus.CREATED,
    JobStatus.QUEUED,
    JobStatus.STARTED,
    JobStatus.DEFERRED,
    JobStatus.SCHEDULED,
}
DEDUPABLE_STATUSES = ACTIVE_STATUSES - {JobStatus.STARTED}
TASK_SERIALIZER = JSONSerializer
JobValidator = Callable[[tuple, dict], None]
RESUME_SCAN_CURSOR_KEY = "narration:resume-scan:last-book-id"


class JobQueueError(Exception):
    """Raised when Redis/RQ cannot accept or run narration work."""


class JobSecurityError(Exception):
    """Raised when a queued job is not part of the supported task contract."""


class JobLeaseError(Exception):
    """Raised when a book lease cannot be acquired or refreshed."""


def _redis_error_detail(e: RedisError) -> str:
    return f"Redis error: {type(e).__name__}"


@dataclass
class RedisLease:
    lock: Lock

    def refresh(self) -> None:
        try:
            self.lock.reacquire()
        except RedisError as e:
            raise JobLeaseError(_redis_error_detail(e)) from e

    def release(self) -> None:
        try:
            self.lock.release()
        except RedisError:
            # The TTL may have expired or another process may have released it.
            # The lease is best-effort after work has stopped.
            return


def _connection() -> Redis:
    retry = RedisRetry(
        ExponentialBackoff(
            base=settings.redis_retry_backoff_base_seconds,
            cap=settings.redis_retry_backoff_cap_seconds,
        ),
        settings.redis_retry_count,
        supported_errors=(ConnectionError, TimeoutError),
    )
    return Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=settings.redis_socket_connect_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
        retry=retry,
    )


def _queue(connection: Redis | None = None) -> Queue:
    return Queue(
        settings.narration_queue_name,
        connection=connection or _connection(),
        serializer=TASK_SERIALIZER,
    )


def _job_matches(job, target: str, args: tuple, job_id: str) -> bool:
    return (
        getattr(job, "id", None) == job_id
        and getattr(job, "func_name", None) == target
        and tuple(getattr(job, "args", ())) == tuple(args)
        and not getattr(job, "kwargs", {})
    )


def _discard_existing_job(job) -> None:
    if getattr(job, "cancel", None):
        job.cancel()
    job.delete()


def enqueue_job(target: str, args: tuple, job_id: str) -> str:
    """Queue a durable job and return the stable RQ job id."""
    connection = _connection()
    queue = _queue(connection)

    try:
        existing = queue.fetch_job(job_id)
        if existing:
            status = existing.get_status(refresh=True)
            if (
                status in DEDUPABLE_STATUSES
                and _job_matches(existing, target, args, job_id)
            ):
                return existing.id
            _discard_existing_job(existing)

        job = queue.enqueue_call(
            func=target,
            args=args,
            job_id=job_id,
            timeout=settings.narration_job_timeout_seconds,
            result_ttl=settings.narration_job_result_ttl_seconds,
            failure_ttl=settings.narration_job_failure_ttl_seconds,
            retry=Retry(max=3, interval=[30, 300, 900]),
        )
    except DuplicateJobError:
        return job_id
    except RedisError as e:
        raise JobQueueError(_redis_error_detail(e)) from e
    return job.id


def cancel_job(job_id: str) -> None:
    try:
        job = _queue().fetch_job(job_id)
        if job and job.get_status(refresh=True) in ACTIVE_STATUSES:
            job.cancel()
    except RedisError as e:
        raise JobQueueError(_redis_error_detail(e)) from e


def acquire_book_lease(book_id: str) -> RedisLease:
    return _acquire_lease(
        f"narration:lease:{book_id}",
        settings.narration_lease_ttl_seconds,
        "book lease unavailable",
    )


def acquire_resume_scan_lease() -> RedisLease:
    return _acquire_lease(
        "narration:resume-scan",
        settings.narration_resume_scan_lease_ttl_seconds,
        "resume scan lease unavailable",
    )


def _acquire_lease(name: str, ttl_seconds: int, detail: str) -> RedisLease:
    connection = _connection()
    lock = connection.lock(
        name,
        timeout=ttl_seconds,
        blocking_timeout=0,
        thread_local=False,
    )
    try:
        acquired = lock.acquire(blocking=False)
    except RedisError as e:
        raise JobLeaseError(_redis_error_detail(e)) from e
    if not acquired:
        raise JobLeaseError(detail)
    return RedisLease(lock)


def get_resume_scan_cursor() -> str | None:
    try:
        value = _connection().get(RESUME_SCAN_CURSOR_KEY)
    except RedisError as e:
        raise JobQueueError(_redis_error_detail(e)) from e
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def set_resume_scan_cursor(book_id: str | None) -> None:
    try:
        connection = _connection()
        if book_id is None:
            connection.delete(RESUME_SCAN_CURSOR_KEY)
        else:
            connection.set(RESUME_SCAN_CURSOR_KEY, book_id)
    except RedisError as e:
        raise JobQueueError(_redis_error_detail(e)) from e


def tombstone_book(book_id: str) -> None:
    try:
        _connection().set(
            _tombstone_key(book_id),
            "1",
            ex=settings.narration_tombstone_ttl_seconds,
        )
    except RedisError as e:
        raise JobQueueError(_redis_error_detail(e)) from e


def is_book_tombstoned(book_id: str) -> bool:
    try:
        return bool(_connection().exists(_tombstone_key(book_id)))
    except RedisError as e:
        raise JobQueueError(_redis_error_detail(e)) from e


def _tombstone_key(book_id: str) -> str:
    return f"narration:deleted:{book_id}"


def current_job_retries_left() -> int | None:
    from rq import get_current_job

    job = get_current_job()
    if job is None:
        return None
    return job.retries_left


def validate_allowed_job(job, allowed_targets: dict[str, JobValidator]) -> None:
    validator = allowed_targets.get(job.func_name)
    if validator is None:
        raise JobSecurityError(f"Unsupported queue target: {job.func_name}")
    validator(job.args, job.kwargs)


class RestrictedWorker(Worker):
    def __init__(self, *args, allowed_targets: dict[str, JobValidator], **kwargs):
        self.allowed_targets = allowed_targets
        super().__init__(*args, **kwargs)

    def perform_job(self, job, queue) -> bool:
        validate_allowed_job(job, self.allowed_targets)
        return super().perform_job(job, queue)


def run_worker(allowed_targets: dict[str, JobValidator]) -> None:
    connection = _connection()
    try:
        connection.ping()
    except RedisError as e:
        raise JobQueueError(_redis_error_detail(e)) from e
    queue = _queue(connection)
    RestrictedWorker(
        [queue],
        connection=connection,
        serializer=TASK_SERIALIZER,
        allowed_targets=allowed_targets,
    ).work()
