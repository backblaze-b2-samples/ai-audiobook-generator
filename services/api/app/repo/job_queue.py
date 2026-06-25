"""Durable narration queue backed by Redis + RQ."""

from redis import Redis
from redis.exceptions import RedisError
from rq import Queue, Retry, Worker
from rq.exceptions import DuplicateJobError
from rq.job import JobStatus

from app.config import settings

NARRATION_JOB_TARGET = "app.service.narration.run_narration"
ACTIVE_STATUSES = {
    JobStatus.CREATED,
    JobStatus.QUEUED,
    JobStatus.STARTED,
    JobStatus.DEFERRED,
    JobStatus.SCHEDULED,
}


class JobQueueError(Exception):
    """Raised when Redis/RQ cannot accept or run narration work."""


def narration_job_id(book_id: str) -> str:
    return f"narration:{book_id}"


def _connection() -> Redis:
    return Redis.from_url(settings.redis_url)


def _queue(connection: Redis | None = None) -> Queue:
    return Queue(settings.narration_queue_name, connection=connection or _connection())


def enqueue_narration(book_id: str) -> str:
    """Queue a durable narration job and return the stable RQ job id."""
    connection = _connection()
    queue = _queue(connection)
    job_id = narration_job_id(book_id)

    try:
        existing = queue.fetch_job(job_id)
        if existing and existing.get_status(refresh=True) in ACTIVE_STATUSES:
            return existing.id
        if existing:
            existing.delete()

        job = queue.enqueue_call(
            func=NARRATION_JOB_TARGET,
            args=(book_id,),
            job_id=job_id,
            timeout=settings.narration_job_timeout_seconds,
            result_ttl=settings.narration_job_result_ttl_seconds,
            failure_ttl=settings.narration_job_failure_ttl_seconds,
            retry=Retry(max=3, interval=[30, 300, 900]),
            unique=True,
        )
    except DuplicateJobError:
        return job_id
    except RedisError as e:
        raise JobQueueError(str(e)) from e
    return job.id


def check_queue_connectivity() -> None:
    try:
        _connection().ping()
    except RedisError as e:
        raise JobQueueError(str(e)) from e


def run_worker() -> None:
    connection = _connection()
    try:
        connection.ping()
    except RedisError as e:
        raise JobQueueError(str(e)) from e
    queue = _queue(connection)
    Worker([queue], connection=connection).work()
