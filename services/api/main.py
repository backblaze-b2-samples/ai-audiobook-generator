import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Single source of truth: repo-root .env. Anchored to this file's path so it
# resolves correctly regardless of where uvicorn is invoked from (local
# `cd services/api && uvicorn`, Docker WORKDIR, etc.).
REPO_ROOT_ENV = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(REPO_ROOT_ENV)

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402

from app.config import settings  # noqa: E402
from app.config.book_auth_tokens import book_auth_tokens_are_valid  # noqa: E402
from app.config.logging import configure_logging  # noqa: E402
from app.runtime import books, files, health, metrics, upload  # noqa: E402

# --- Startup validation ---
# Required B2 settings are declared with empty-string defaults so that
# `Settings()` instantiation (and therefore `from main import app`) never
# raises during test collection. We instead fail fast at server startup
# with a human-readable message — uvicorn surfaces this as the first log
# line, so misconfiguration is obvious within seconds rather than turning
# into mysterious 500s on the first request.
REQUIRED_B2_SETTINGS = (
    ("b2_application_key_id", "B2_APPLICATION_KEY_ID"),
    ("b2_application_key", "B2_APPLICATION_KEY"),
    ("b2_bucket_name", "B2_BUCKET_NAME"),
    ("b2_region", "B2_REGION"),
)
REQUIRED_AUTH_SETTINGS = (("book_auth_tokens", "BOOK_AUTH_TOKENS"),)

# Exact placeholder strings shipped in .env.example. If a user copied
# the example and didn't edit it, Settings will pass the "non-empty"
# check above but every B2 call will still 403. Catch that here.
PLACEHOLDER_VALUES = frozenset({
    "your_b2_region",
    "your_application_key_id",
    "your_application_key",
    "your-bucket-name",
    "local-dev:replace-with-a-random-token",
})
BOOK_AUTH_TOKEN_PLACEHOLDER = "replace-with-a-random-token"


def _has_book_auth_placeholder(value: str) -> bool:
    for item in value.split(","):
        if ":" in item:
            token = item.split(":", 1)[1]
        elif "=" in item:
            token = item.split("=", 1)[1]
        else:
            token = item
        if token.strip() == BOOK_AUTH_TOKEN_PLACEHOLDER:
            return True
    return False


@asynccontextmanager
async def lifespan(_app: "FastAPI"):
    missing = [
        env_name
        for attr, env_name in REQUIRED_B2_SETTINGS + REQUIRED_AUTH_SETTINGS
        if not getattr(settings, attr)
    ]
    if missing:
        raise RuntimeError(
            "Missing required configuration: "
            + ", ".join(missing)
            + f". Add them to {REPO_ROOT_ENV} (see .env.example) and restart."
        )

    placeholders = [
        env_name
        for attr, env_name in REQUIRED_B2_SETTINGS + REQUIRED_AUTH_SETTINGS
        if getattr(settings, attr) in PLACEHOLDER_VALUES
        or (attr == "book_auth_tokens" and _has_book_auth_placeholder(getattr(settings, attr)))
    ]
    if placeholders:
        raise RuntimeError(
            "Configuration still has placeholder values: "
            + ", ".join(placeholders)
            + f". Edit {REPO_ROOT_ENV} with your real configuration values and restart."
        )

    if not book_auth_tokens_are_valid(settings.book_auth_tokens):
        raise RuntimeError(
            "Invalid BOOK_AUTH_TOKENS format. Set at least one owner:token "
            + f"entry in {REPO_ROOT_ENV} and restart."
        )
    yield


configure_logging()

logger = logging.getLogger("api")


# --- App setup ---

app = FastAPI(
    title="AI Audiobook Generator API",
    description="Manuscript-to-audiobook narration API backed by Backblaze B2",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Optional regex (empty by default). When set, any origin matching
    # the pattern is allowed in addition to the explicit allowlist.
    allow_origin_regex=settings.api_cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Book-Owner", "X-Book-Token"],
)

# Request ID + timing middleware
app.add_middleware(BaseHTTPMiddleware, dispatch=metrics.timing_middleware)

app.include_router(health.router, tags=["health"])
app.include_router(upload.router, tags=["upload"])
app.include_router(books.router, tags=["books"])
app.include_router(files.router, tags=["files"])
app.include_router(metrics.router, tags=["metrics"])
