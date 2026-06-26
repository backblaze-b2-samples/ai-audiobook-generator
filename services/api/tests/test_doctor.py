"""Tests for doctor preflight redaction helpers."""

import os
import subprocess
from pathlib import Path


def test_doctor_invalid_redis_url_message_redacts_credentials():
    repo_root = Path(__file__).resolve().parents[3]
    env = {**os.environ, "DOCTOR_SKIP_MAIN": "1"}
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            (
                "import { redisUrlInvalidMessage } from './scripts/doctor.mjs';"
                "console.log(redisUrlInvalidMessage('redis://user:secret@bad host'));"
            ),
        ],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "secret" not in result.stdout
    assert "user" not in result.stdout
    assert result.stdout.strip() == "REDIS_URL is invalid"


def test_doctor_detects_placeholder_book_auth_entry():
    repo_root = Path(__file__).resolve().parents[3]
    env = {**os.environ, "DOCTOR_SKIP_MAIN": "1"}
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            (
                "import { hasBookAuthPlaceholder } from './scripts/doctor.mjs';"
                "process.stdout.write(String(hasBookAuthPlaceholder("
                "'prod:strong,local-dev:replace-with-a-random-token'"
                ")));"
            ),
        ],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout.strip() == "true"


def test_doctor_rejects_malformed_book_auth_tokens():
    repo_root = Path(__file__).resolve().parents[3]
    env = {**os.environ, "DOCTOR_SKIP_MAIN": "1"}
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            (
                "import { bookAuthTokensAreValid } from './scripts/doctor.mjs';"
                "process.stdout.write(String(bookAuthTokensAreValid('garbage,owner:')));"
            ),
        ],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout.strip() == "false"
