import logging
from pathlib import Path
from threading import Thread

from dotenv import load_dotenv

REPO_ROOT_ENV = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(REPO_ROOT_ENV)

from app.config import settings  # noqa: E402
from app.config.logging import configure_logging  # noqa: E402
from app.repo import (  # noqa: E402
    JobLeaseError,
    JobQueueError,
    acquire_resume_scan_lease,
    run_worker,
)
from app.service.narration import (  # noqa: E402
    NARRATION_JOB_TARGET,
    enqueue_resume_candidates,
    validate_narration_job,
)

configure_logging()
logger = logging.getLogger("worker")


ALLOWED_TARGETS = {NARRATION_JOB_TARGET: validate_narration_job}


def _resume_existing_books() -> None:
    try:
        lease = acquire_resume_scan_lease()
    except JobLeaseError as e:
        logger.info("Skipping resume scan: %s", e)
        return

    try:
        queued = enqueue_resume_candidates(limit=settings.narration_resume_scan_limit)
        logger.info("Queued %d incomplete narration jobs", queued)
    except Exception:
        logger.exception("Resume scan failed")
    finally:
        lease.release()


def main() -> None:
    Thread(target=_resume_existing_books, name="resume-scan", daemon=True).start()
    try:
        run_worker(ALLOWED_TARGETS)
    except JobQueueError as e:
        logger.error("Narration worker failed: %s", e)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
