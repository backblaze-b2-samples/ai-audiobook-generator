import logging
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT_ENV = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(REPO_ROOT_ENV)

from app.config.logging import configure_logging  # noqa: E402
from app.repo import JobQueueError, run_worker  # noqa: E402
from app.service.narration import enqueue_resume_candidates  # noqa: E402

configure_logging()
logger = logging.getLogger("worker")


def main() -> None:
    try:
        queued = enqueue_resume_candidates()
        logger.info("Queued %d incomplete narration jobs", queued)
        run_worker()
    except JobQueueError as e:
        logger.error("Narration worker failed: %s", e)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
